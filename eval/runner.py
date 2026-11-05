"""Run the benchmark. Use `docker compose exec api python -m eval.runner`.

Each run calls the real LLM once per question, which costs money. Use
`--check-gold` to validate the dataset without any LLM calls.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import sqlglot
from sqlglot import exp

from app.config import Settings
from app.llm.base import LLMClient, LLMError, LLMOutput
from app.llm.factory import create_llm_client
from app.pipeline.errors import (
    DatabaseUnavailableError,
    PipelineError,
    QueryTimeoutError,
    SqlExecutionError,
    SqlValidationError,
    UnanswerableQuestionError,
)
from app.pipeline.execute import QueryResult, execute_query, readonly_connection
from app.pipeline.orchestrator import PROMPT_PATH, QueryPipeline
from app.pipeline.validate import validate_sql
from app.schema.introspect import Table, load_tables
from eval.dataset import DIFFICULTIES, Question, load_dataset
from eval.report import CORRECT, QuestionResult, RunInfo, render_report
from eval.scoring import compare_results

EVAL_DIR = Path(__file__).resolve().parent
REPORT_DIR = EVAL_DIR / "reports"
RUN_DIR = EVAL_DIR / "runs"

# Far above any gold result, so the product's row cap can't decide a score.
EVAL_MAX_ROWS = 10_000

# USD per million tokens, for the cost estimate in the report.
MODEL_PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

OUTCOME_BY_ERROR: dict[type[Exception], str] = {
    UnanswerableQuestionError: "unanswerable",
    SqlValidationError: "blocked",
    SqlExecutionError: "sql_error",
    QueryTimeoutError: "timeout",
    DatabaseUnavailableError: "database_error",
}


class RecordingLLM:
    """Keeps what the LLM returned, so failed queries still show their SQL."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm
        self.output: LLMOutput | None = None

    def generate_sql(self, system_prompt: str, question: str) -> LLMOutput:
        self.output = self._llm.generate_sql(system_prompt, question)
        return self.output


def score(
    question: Question,
    gold: QueryResult,
    tables: list[Table],
    llm: LLMClient,
    settings: Settings,
) -> QuestionResult:
    recorder = RecordingLLM(llm)
    pipeline = QueryPipeline(recorder, lambda: tables, lambda sql: execute_query(sql, settings))
    outcome, reason = CORRECT, ""
    started = time.perf_counter()
    try:
        result = pipeline.run(question.question)
        comparison = compare_results(gold.rows, result.rows, question.ordered)
        if result.truncated:
            outcome = "truncated"
        elif not comparison.matched:
            outcome, reason = "wrong_result", comparison.reason
    except LLMError as error:
        outcome, reason = "llm_error", str(error)
    except PipelineError as error:
        outcome, reason = OUTCOME_BY_ERROR[type(error)], error.message
    output = recorder.output
    return QuestionResult(
        id=question.id,
        difficulty=question.difficulty,
        tags=question.tags,
        question=question.question,
        gold_sql=question.gold_sql,
        outcome=outcome,
        reason=reason,
        generated_sql=output.sql if output else None,
        latency_seconds=time.perf_counter() - started,
        input_tokens=output.input_tokens if output else 0,
        output_tokens=output.output_tokens if output else 0,
    )


def limit_of(sql: str) -> int | None:
    limit = sqlglot.parse_one(sql, dialect="postgres").args.get("limit")
    return int(limit.expression.name) if limit else None


def sort_expression(root: exp.Select) -> exp.Expression:
    """Return the first ORDER BY term, following it to its definition if it's an alias."""
    term = root.args["order"].expressions[0].this
    for selected in root.selects:
        if isinstance(selected, exp.Alias) and selected.alias == term.name:
            return selected.this.copy()
    return term.copy()


def tie_at_limit(sql: str, settings: Settings) -> bool:
    """A tie at the cutoff means the right rows depend on an arbitrary choice."""
    limit = limit_of(sql)
    if limit is None:
        return False
    # Gold rankings often select only labels, so the sort value has to be made visible.
    root = sqlglot.parse_one(sql, dialect="postgres")
    assert isinstance(root, exp.Select)
    ranked = root.copy().select(exp.alias_(sort_expression(root), "sort_value"))
    ranked.set("limit", None)
    rows = execute_query(ranked.sql(dialect="postgres"), settings).rows
    return len(rows) > limit and rows[limit - 1][-1] == rows[limit][-1]


def check_question(question: Question, tables: frozenset[str], settings: Settings) -> str | None:
    try:
        validate_sql(question.gold_sql, tables)
        rows = execute_query(question.gold_sql, settings)
    except PipelineError as error:
        return f"{question.id}: {error.message}"
    if not rows.rows or rows.truncated:
        return f"{question.id}: returned {len(rows.rows)} rows, truncated={rows.truncated}"
    if all(value is None for row in rows.rows for value in row):
        return f"{question.id}: returned only NULL"
    if tie_at_limit(question.gold_sql, settings):
        return f"{question.id}: tie at the LIMIT boundary"
    return None


def check_gold(questions: list[Question], tables: list[Table], settings: Settings) -> list[str]:
    names = frozenset(table.name for table in tables)
    problems = [check_question(question, names, settings) for question in questions]
    return [problem for problem in problems if problem]


def load_schema(settings: Settings) -> list[Table]:
    with readonly_connection(settings) as connection:
        return load_tables(connection)


def run_all(
    questions: list[Question],
    tables: list[Table],
    llm: LLMClient,
    settings: Settings,
    concurrency: int,
) -> list[QuestionResult]:
    def run_one(question: Question) -> QuestionResult:
        gold = execute_query(question.gold_sql, settings)
        result = score(question, gold, tables, llm, settings)
        print(f"{result.id}: {result.outcome} {result.reason}", flush=True)
        return result

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        return list(pool.map(run_one, questions))


def save_outputs(results: list[QuestionResult], info: RunInfo) -> Path:
    stamp = info.started_at.replace(":", "").replace("-", "")
    REPORT_DIR.mkdir(exist_ok=True)
    RUN_DIR.mkdir(exist_ok=True)
    report_path = REPORT_DIR / f"{info.dataset}-{stamp}.md"
    report_path.write_text(render_report(results, info), encoding="utf-8")
    raw = json.dumps([asdict(result) for result in results], indent=2)
    (RUN_DIR / f"{info.dataset}-{stamp}.json").write_text(raw, encoding="utf-8")
    return report_path


def select_questions(questions: list[Question], args: argparse.Namespace) -> list[Question]:
    selected = [
        question
        for question in questions
        if (not args.difficulty or question.difficulty == args.difficulty)
        and (not args.ids or question.id in args.ids)
    ]
    return selected[: args.limit] if args.limit else selected


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Measure execution accuracy.")
    parser.add_argument("--dataset", default="olist_v1")
    parser.add_argument("--difficulty", choices=DIFFICULTIES)
    parser.add_argument("--ids", nargs="+", help="run only these question IDs")
    parser.add_argument("--limit", type=int, help="run only the first N questions")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--check-gold", action="store_true", help="check gold SQL, without an LLM")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings().model_copy(update={"query_max_rows": EVAL_MAX_ROWS})
    questions = select_questions(load_dataset(args.dataset), args)
    tables = load_schema(settings)
    problems = check_gold(questions, tables, settings)
    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} of {len(questions)} gold queries have problems.")
        return 1
    print(f"All {len(questions)} gold queries passed.")
    if args.check_gold:
        return 0
    started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = run_all(questions, tables, create_llm_client(settings), settings, args.concurrency)
    input_price, output_price = MODEL_PRICES.get(settings.llm_model, (None, None))
    info = RunInfo(
        dataset=args.dataset,
        started_at=started_at,
        model=settings.llm_model,
        effort=settings.llm_effort,
        prompt=PROMPT_PATH.stem,
        input_price=input_price,
        output_price=output_price,
    )
    print(f"Report saved to {save_outputs(results, info)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
