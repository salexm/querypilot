"""Turn question results into a markdown report."""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from statistics import median

from eval.dataset import DIFFICULTIES

CORRECT = "correct"

OUTCOME_LABELS = {
    CORRECT: "Correct",
    "wrong_result": "Wrong result",
    "sql_error": "SQL error",
    "blocked": "Blocked by validator",
    "unanswerable": "Declined to answer",
    "timeout": "Timeout",
    "truncated": "Hit the row cap",
    "llm_error": "LLM error",
    "database_error": "Database error",
}


@dataclass(frozen=True)
class QuestionResult:
    id: str
    difficulty: str
    tags: tuple[str, ...]
    question: str
    gold_sql: str
    outcome: str
    reason: str
    generated_sql: str | None
    latency_seconds: float
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class RunInfo:
    dataset: str
    started_at: str
    model: str
    effort: str
    prompt: str
    input_price: float | None
    output_price: float | None


def percent(part: int, whole: int) -> str:
    return f"{100 * part / whole:.1f}%" if whole else "n/a"


def accuracy_row(label: str, results: list[QuestionResult]) -> str:
    correct = sum(result.outcome == CORRECT for result in results)
    latency = median(result.latency_seconds for result in results)
    return (
        f"| {label} | {len(results)} | {correct} | {percent(correct, len(results))} "
        f"| {latency:.1f}s |"
    )


def accuracy_table(
    heading: str,
    groups: Iterable[tuple[str, list[QuestionResult]]],
) -> list[str]:
    return [
        f"| {heading} | Questions | Correct | Accuracy | Median latency |",
        "|---|---:|---:|---:|---:|",
        *(accuracy_row(label, results) for label, results in groups if results),
    ]


def select(
    results: list[QuestionResult], keep: Callable[[QuestionResult], bool]
) -> list[QuestionResult]:
    return [result for result in results if keep(result)]


def difficulty_groups(results: list[QuestionResult]) -> list[tuple[str, list[QuestionResult]]]:
    groups = [
        (
            level.capitalize(),
            select(results, lambda result, level=level: result.difficulty == level),
        )
        for level in DIFFICULTIES
    ]
    return [*groups, ("**Overall**", results)]


def tag_groups(results: list[QuestionResult]) -> list[tuple[str, list[QuestionResult]]]:
    tags = sorted({tag for result in results for tag in result.tags})
    return [
        (f"`{tag}`", select(results, lambda result, tag=tag: tag in result.tags)) for tag in tags
    ]


def outcome_table(results: list[QuestionResult]) -> list[str]:
    counts = Counter(result.outcome for result in results)
    rows = [
        f"| {label} | {counts[outcome]} | {percent(counts[outcome], len(results))} |"
        for outcome, label in OUTCOME_LABELS.items()
        if counts[outcome]
    ]
    return ["| Outcome | Questions | Share |", "|---|---:|---:|", *rows]


def cost_line(results: list[QuestionResult], info: RunInfo) -> str:
    input_tokens = sum(result.input_tokens for result in results)
    output_tokens = sum(result.output_tokens for result in results)
    tokens = f"{input_tokens:,} input and {output_tokens:,} output tokens"
    if info.input_price is None or info.output_price is None:
        return f"- **Usage:** {tokens}"
    cost = (input_tokens * info.input_price + output_tokens * info.output_price) / 1_000_000
    return f"- **Usage:** {tokens}, about ${cost:.2f} at list prices"


def failure_section(result: QuestionResult) -> list[str]:
    generated = result.generated_sql or "(none)"
    reason = f" ({result.reason})" if result.reason else ""
    return [
        f"### {result.id} ({result.difficulty}): {OUTCOME_LABELS[result.outcome]}{reason}",
        "",
        result.question,
        "",
        "Gold SQL:",
        "",
        f"```sql\n{result.gold_sql}\n```",
        "",
        "Generated SQL:",
        "",
        f"```sql\n{generated}\n```",
        "",
    ]


def render_report(results: list[QuestionResult], info: RunInfo) -> str:
    failures = select(results, lambda result: result.outcome != CORRECT)
    lines = [
        "# QueryPilot evaluation",
        "",
        f"- **Dataset:** {info.dataset} ({len(results)} questions)",
        f"- **Run:** {info.started_at}",
        f"- **Model:** {info.model} at {info.effort} effort",
        f"- **Prompt:** {info.prompt}",
        cost_line(results, info),
        "",
        "Accuracy is execution accuracy: generated SQL counts as correct when its result set "
        "matches the gold result set. See `eval/scoring.py` for the rules. Each question ran "
        "once, without self-correction.",
        "",
        "## Accuracy by difficulty",
        "",
        *accuracy_table("Difficulty", difficulty_groups(results)),
        "",
        "## Outcomes",
        "",
        *outcome_table(results),
        "",
        "## Accuracy by tag",
        "",
        "A question can have several tags, so these rows overlap.",
        "",
        *accuracy_table("Tag", tag_groups(results)),
        "",
        f"## Failures ({len(failures)})",
        "",
    ]
    for failure in failures:
        lines += failure_section(failure)
    return "\n".join(lines).rstrip() + "\n"
