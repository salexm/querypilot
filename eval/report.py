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
    llm_calls: int = 1


@dataclass(frozen=True)
class RunInfo:
    dataset: str
    started_at: str
    model: str
    effort: str
    prompt: str
    input_price: float | None
    output_price: float | None
    max_retries: int = 0


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


def estimated_cost(results: list[QuestionResult], info: RunInfo) -> float | None:
    if info.input_price is None or info.output_price is None:
        return None
    input_cost = sum(result.input_tokens for result in results) * info.input_price
    output_cost = sum(result.output_tokens for result in results) * info.output_price
    return (input_cost + output_cost) / 1_000_000


def cost_line(results: list[QuestionResult], info: RunInfo) -> str:
    input_tokens = sum(result.input_tokens for result in results)
    output_tokens = sum(result.output_tokens for result in results)
    tokens = f"{input_tokens:,} input and {output_tokens:,} output tokens"
    cost = estimated_cost(results, info)
    if cost is None:
        return f"- **Usage:** {tokens}"
    return f"- **Usage:** {tokens}, about ${cost:.2f} at list prices"


def llm_error_count(results: list[QuestionResult]) -> int:
    return sum(result.outcome == "llm_error" for result in results)


def outage_warning(*runs: list[QuestionResult]) -> list[str]:
    """Stop provider failures from reading as model accuracy."""
    errors = sum(llm_error_count(results) for results in runs)
    if not errors:
        return []
    return [
        f"> **Invalid run:** {errors} questions failed with LLM provider errors, so these "
        "numbers measure an outage, not the model. Fix the cause and run again.",
        "",
    ]


def correction_label(info: RunInfo) -> str:
    return f"on, up to {info.max_retries} retries" if info.max_retries else "off"


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
        *outage_warning(results),
        f"- **Dataset:** {info.dataset} ({len(results)} questions)",
        f"- **Run:** {info.started_at}",
        f"- **Model:** {info.model} at {info.effort} effort",
        f"- **Prompt:** {info.prompt}",
        f"- **Self-correction:** {correction_label(info)}",
        cost_line(results, info),
        "",
        "Accuracy is execution accuracy: generated SQL counts as correct when its result set "
        "matches the gold result set. See `eval/scoring.py` for the rules. Each question ran "
        "once.",
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


def correct_count(results: list[QuestionResult]) -> int:
    return sum(result.outcome == CORRECT for result in results)


def comparison_row(
    label: str, baseline: list[QuestionResult], corrected: list[QuestionResult]
) -> str:
    before, after = correct_count(baseline), correct_count(corrected)
    change = 100 * (after - before) / len(baseline)
    return (
        f"| {label} | {len(baseline)} | {before} ({percent(before, len(baseline))}) "
        f"| {after} ({percent(after, len(corrected))}) | {change:+.1f} pts |"
    )


def ids_where(
    baseline: list[QuestionResult],
    corrected: list[QuestionResult],
    was_correct: bool,
) -> list[str]:
    """Return questions whose result flipped from was_correct to the opposite."""
    after = {result.id: result.outcome == CORRECT for result in corrected}
    return [
        result.id
        for result in baseline
        if (result.outcome == CORRECT) == was_correct and after[result.id] != was_correct
    ]


def id_list(ids: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in ids) if ids else "none"


def cost_text(results: list[QuestionResult], info: RunInfo) -> str:
    cost = estimated_cost(results, info)
    return "n/a" if cost is None else f"${cost:.2f}"


def retry_summary(corrected: list[QuestionResult]) -> str:
    retried = select(corrected, lambda result: result.llm_calls > 1)
    recovered = select(retried, lambda result: result.outcome == CORRECT)
    noun = "question" if len(retried) == 1 else "questions"
    return f"{len(retried)} {noun} retried, and {len(recovered)} of those ended correct"


def render_comparison(
    baseline: list[QuestionResult],
    baseline_info: RunInfo,
    corrected: list[QuestionResult],
    corrected_info: RunInfo,
) -> str:
    groups = zip(difficulty_groups(baseline), difficulty_groups(corrected), strict=True)
    rows = [
        comparison_row(label, before, after) for (label, before), (_, after) in groups if before
    ]
    calls = sum(result.llm_calls for result in corrected)
    lines = [
        "# Self-correction comparison",
        "",
        *outage_warning(baseline, corrected),
        f"- **Dataset:** {baseline_info.dataset} ({len(baseline)} questions)",
        f"- **Model:** {baseline_info.model} at {baseline_info.effort} effort",
        f"- **Self-correction:** {correction_label(corrected_info)}",
        "",
        "Each mode ran each question once, and the LLM's answers vary between runs. A small "
        "change here can be noise rather than an effect of self-correction.",
        "",
        "Self-correction only reacts to SQL errors and empty results. It can't catch SQL that "
        "runs and returns the wrong answer.",
        "",
        "## Accuracy",
        "",
        "| Difficulty | Questions | Without | With | Change |",
        "|---|---:|---:|---:|---:|",
        *rows,
        "",
        "## What changed",
        "",
        f"- **Retries:** {retry_summary(corrected)}",
        f"- **Wrong without, correct with:** {id_list(ids_where(baseline, corrected, False))}",
        f"- **Correct without, wrong with:** {id_list(ids_where(baseline, corrected, True))}",
        "",
        "## Cost and speed",
        "",
        "| Measure | Without | With |",
        "|---|---:|---:|",
        f"| LLM calls | {sum(result.llm_calls for result in baseline)} | {calls} |",
        f"| Estimated cost | {cost_text(baseline, baseline_info)} "
        f"| {cost_text(corrected, corrected_info)} |",
        f"| Median latency | {median(result.latency_seconds for result in baseline):.1f}s "
        f"| {median(result.latency_seconds for result in corrected):.1f}s |",
    ]
    return "\n".join(lines) + "\n"
