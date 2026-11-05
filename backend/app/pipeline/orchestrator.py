from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.base import LLMClient
from app.pipeline.chart import ChartSpec, select_chart
from app.pipeline.errors import (
    DatabaseUnavailableError,
    PipelineError,
    QueryTimeoutError,
    SqlExecutionError,
    SqlValidationError,
    UnanswerableQuestionError,
)
from app.pipeline.execute import QueryResult
from app.pipeline.validate import validate_sql
from app.schema.introspect import Table, format_schema

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
PROMPT_PATH = PROMPT_DIR / "generate_sql_v1.md"
RETRY_PROMPT_PATH = PROMPT_DIR / "retry_sql_v1.md"

NO_ROWS_PROBLEM = "The query ran but returned no rows."

# Failures the LLM can fix by rewriting the SQL. Outages and LLM errors can't be.
CORRECTABLE_ERRORS = (SqlValidationError, SqlExecutionError, QueryTimeoutError)


@dataclass(frozen=True)
class Attempt:
    sql: str
    problem: str | None


@dataclass(frozen=True)
class PipelineResult:
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    chart: ChartSpec | None
    attempts: tuple[Attempt, ...]


def build_system_prompt(tables: list[Table]) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{schema}", format_schema(tables))


def build_retry_prompt(question: str, sql: str, problem: str) -> str:
    template = RETRY_PROMPT_PATH.read_text(encoding="utf-8")
    return template.format(question=question, sql=sql, problem=problem)


class QueryPipeline:
    """Headless path from question to rows, shared by the API and the benchmark.

    Self-correction is a bounded loop: every attempt, including retries, goes
    through the same validator and read-only executor.
    """

    def __init__(
        self,
        llm: LLMClient,
        load_schema: Callable[[], list[Table]],
        execute: Callable[[str], QueryResult],
        max_retries: int = 0,
    ) -> None:
        self._llm = llm
        self._load_schema = load_schema
        self._execute = execute
        self._max_retries = max_retries

    def run(self, question: str) -> PipelineResult:
        tables = self._load_schema()
        if not tables:
            raise DatabaseUnavailableError("The analytics database has no tables. Run the seed.")
        system_prompt = build_system_prompt(tables)
        allowed_tables = frozenset(table.name for table in tables)
        attempts: list[Attempt] = []
        empty_result: tuple[str, QueryResult] | None = None
        last_error: PipelineError | None = None
        prompt = question

        for _ in range(self._max_retries + 1):
            generated = self._llm.generate_sql(system_prompt, prompt).sql.strip()
            # A blank or repeated answer means the LLM has nothing better to offer.
            if not generated or generated in {attempt.sql for attempt in attempts}:
                break
            try:
                sql = validate_sql(generated, allowed_tables)
                result = self._execute(sql)
            except CORRECTABLE_ERRORS as error:
                last_error = error
                attempts.append(Attempt(generated, error.message))
                prompt = build_retry_prompt(question, generated, error.message)
                continue
            if result.rows:
                attempts.append(Attempt(generated, None))
                return self._finish(question, sql, result, attempts)
            empty_result = (sql, result)
            attempts.append(Attempt(generated, NO_ROWS_PROBLEM))
            prompt = build_retry_prompt(question, generated, NO_ROWS_PROBLEM)

        # An empty result is a valid answer, so it beats a retry that failed.
        if empty_result:
            return self._finish(question, *empty_result, attempts)
        if last_error:
            raise last_error
        raise UnanswerableQuestionError("This question can't be answered from the data.")

    @staticmethod
    def _finish(
        question: str, sql: str, result: QueryResult, attempts: list[Attempt]
    ) -> PipelineResult:
        chart = select_chart(result.columns, result.column_types, result.rows, result.truncated)
        return PipelineResult(
            question,
            sql,
            result.columns,
            result.rows,
            result.truncated,
            chart,
            tuple(attempts),
        )
