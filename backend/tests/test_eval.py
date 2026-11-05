from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest

from app.config import Settings
from app.llm.base import LLMOutput
from app.pipeline.errors import SqlExecutionError
from app.pipeline.execute import QueryResult
from eval.dataset import DIFFICULTIES, Question, load_dataset
from eval.report import QuestionResult, RunInfo, render_comparison, render_report
from eval.runner import limit_of, retry_modes, score
from eval.scoring import compare_results, normalize
from tests.fakes import FakeLLM, sample_tables


def matches(gold: list[list[object]], candidate: list[list[object]], ordered: bool = False) -> bool:
    return compare_results(gold, candidate, ordered).matched


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (2017, 2017.0),
        ("2017", 2017.0),
        ("12.50", 12.5),
        (None, None),
        (True, True),
        ("SP ", "sp"),
        ("2017-01", "2017-01"),
        ("2017-01-01", "2017-01"),
        ("2017-01-01T00:00:00", "2017-01"),
        ("2017-01-15T00:00:00", "2017-01-15"),
        ("2017-01-15T10:30:00", "2017-01-15t10:30:00"),
    ],
)
def test_normalize(value: object, expected: object) -> None:
    assert normalize(value) == expected


def test_identical_results_match() -> None:
    assert matches([["SP", 9], ["RJ", 4]], [["SP", 9], ["RJ", 4]])


def test_row_order_is_ignored_unless_required() -> None:
    gold, candidate = [["SP", 9], ["RJ", 4]], [["RJ", 4], ["SP", 9]]

    assert matches(gold, candidate)
    assert not matches(gold, candidate, ordered=True)


def test_column_order_and_names_are_ignored() -> None:
    assert matches([["SP", 9], ["RJ", 4]], [[9, "SP"], [4, "RJ"]])


def test_extra_columns_are_allowed() -> None:
    assert matches([["SP"], ["RJ"]], [["SP", 9], ["RJ", 4]])


def test_missing_columns_fail() -> None:
    result = compare_results([["SP", 9]], [["SP"]], False)

    assert not result.matched
    assert "columns" in result.reason


def test_extra_rows_fail() -> None:
    result = compare_results([["SP"]], [["SP"], ["RJ"]], False)

    assert not result.matched
    assert "expected 1 rows" in result.reason


def test_different_values_fail() -> None:
    assert not matches([["SP", 9]], [["SP", 10]])


def test_columns_must_line_up_row_by_row() -> None:
    gold = [["SP", 1], ["RJ", 2]]
    swapped_pairs = [["SP", 2], ["RJ", 1]]

    assert not matches(gold, swapped_pairs)


def test_duplicate_rows_are_counted() -> None:
    assert not matches([["SP"], ["SP"], ["RJ"]], [["SP"], ["RJ"], ["RJ"]])


@pytest.mark.parametrize(
    ("gold", "candidate", "expected"),
    [
        (4.0861, 4.09, True),
        (1412089.534, 1412089.53, True),
        (1000.0, 1000.5, True),
        (4.08, 4.2, False),
        (100.0, 101.0, False),
    ],
)
def test_number_tolerance(gold: float, candidate: float, expected: bool) -> None:
    assert matches([[gold]], [[candidate]]) is expected


def test_nulls_match_only_nulls() -> None:
    assert matches([[None, 1]], [[None, 1]])
    assert not matches([[None]], [[0]])


def test_mixed_types_in_a_column_can_be_sorted() -> None:
    assert matches([[None], [1], ["a"], [True]], [["a"], [True], [1], [None]])


def test_equal_empty_results_match() -> None:
    assert matches([], [])


def test_nonempty_gold_never_matches_empty_results() -> None:
    assert not matches([["SP"]], [])


def question(**overrides: object) -> Question:
    values: dict[str, object] = {
        "id": "t1",
        "difficulty": "easy",
        "tags": ("aggregation",),
        "question": "How many?",
        "gold_sql": "SELECT 1",
    }
    return Question.model_validate(values | overrides)


GOLD = QueryResult(["total"], ["int8"], [[42]], False)


def settings_stub() -> object:
    return object()


@pytest.fixture
def stub_execute(monkeypatch: pytest.MonkeyPatch) -> list[QueryResult | Exception]:
    responses: list[QueryResult | Exception] = []

    def execute(sql: str, settings: object) -> QueryResult:
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("eval.runner.execute_query", execute)
    return responses


def test_score_marks_matching_results_correct(stub_execute: list) -> None:
    stub_execute.append(QueryResult(["n"], ["int8"], [[42]], False))

    result = score(question(), GOLD, sample_tables(), FakeLLM("SELECT 42"), settings_stub())

    assert result.outcome == "correct"
    assert result.generated_sql == "SELECT 42"
    assert result.input_tokens == 100


def test_score_marks_different_results_wrong(stub_execute: list) -> None:
    stub_execute.append(QueryResult(["n"], ["int8"], [[41]], False))

    result = score(question(), GOLD, sample_tables(), FakeLLM("SELECT 41"), settings_stub())

    assert result.outcome == "wrong_result"


def test_score_never_rewards_truncated_results(stub_execute: list) -> None:
    stub_execute.append(QueryResult(["n"], ["int8"], [[42]], True))

    result = score(question(), GOLD, sample_tables(), FakeLLM("SELECT 42"), settings_stub())

    assert result.outcome == "truncated"


def test_score_keeps_sql_that_failed_to_run(stub_execute: list) -> None:
    stub_execute.append(SqlExecutionError("no such column", "SELECT x"))

    result = score(question(), GOLD, sample_tables(), FakeLLM("SELECT x"), settings_stub())

    assert result.outcome == "sql_error"
    assert result.generated_sql == "SELECT x"


@pytest.mark.parametrize(
    ("sql", "outcome"),
    [("DROP TABLE orders", "blocked"), ("", "unanswerable")],
)
def test_score_classifies_pipeline_failures(sql: str, outcome: str) -> None:
    result = score(question(), GOLD, sample_tables(), FakeLLM(sql), settings_stub())

    assert result.outcome == outcome


@pytest.mark.parametrize(
    ("sql", "expected"),
    [("SELECT 1", None), ("SELECT a FROM t ORDER BY a LIMIT 5", 5)],
)
def test_limit_of(sql: str, expected: int | None) -> None:
    assert limit_of(sql) == expected


def test_real_dataset_is_balanced_and_large_enough() -> None:
    questions = load_dataset("olist_v1")

    assert len(questions) >= 100
    assert {item.difficulty for item in questions} == set(DIFFICULTIES)
    assert all(sum(item.difficulty == level for item in questions) >= 30 for level in DIFFICULTIES)


def test_dataset_rejects_duplicate_ids(tmp_path: Path) -> None:
    line = question().model_dump_json()
    (tmp_path / "sample_a.jsonl").write_text(f"{line}\n{line}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate"):
        load_dataset("sample", tmp_path)


def test_dataset_rejects_unknown_fields(tmp_path: Path) -> None:
    line = '{"id":"a","difficulty":"easy","tags":[],"question":"q","gold_sql":"s","typo":1}'
    (tmp_path / "sample_a.jsonl").write_text(line, encoding="utf-8")

    with pytest.raises(ValueError):
        load_dataset("sample", tmp_path)


def result_row(id_: str, difficulty: str, outcome: str) -> QuestionResult:
    return QuestionResult(
        id=id_,
        difficulty=difficulty,
        tags=("join",),
        question="How many?",
        gold_sql="SELECT 1",
        outcome=outcome,
        reason="",
        generated_sql="SELECT 2" if outcome != "correct" else "SELECT 1",
        latency_seconds=2.0,
        input_tokens=1_000_000,
        output_tokens=100_000,
    )


def test_report_breaks_accuracy_down_by_difficulty() -> None:
    results = [
        result_row("e1", "easy", "correct"),
        result_row("e2", "easy", "correct"),
        result_row("m1", "medium", "correct"),
        result_row("m2", "medium", "wrong_result"),
        result_row("h1", "hard", "sql_error"),
    ]
    info = RunInfo("olist_v1", "2026-11-05T00:00:00Z", "model", "medium", "v1", 4.0, 20.0)

    report = render_report(results, info)

    assert "| Easy | 2 | 2 | 100.0% | 2.0s |" in report
    assert "| Medium | 2 | 1 | 50.0% | 2.0s |" in report
    assert "| Hard | 1 | 0 | 0.0% | 2.0s |" in report
    assert "| **Overall** | 5 | 3 | 60.0% | 2.0s |" in report
    assert "## Failures (2)" in report
    assert "### m2 (medium): Wrong result" in report
    assert "about $30.00" in report


def correction_info(max_retries: int) -> RunInfo:
    return RunInfo(
        "olist_v1", "2026-11-05T00:00:00Z", "model", "medium", "v1", 4.0, 20.0, max_retries
    )


def retried(result: QuestionResult, calls: int) -> QuestionResult:
    return replace(result, llm_calls=calls)


def test_comparison_shows_change_by_difficulty_and_flipped_questions() -> None:
    baseline = [
        result_row("e1", "easy", "correct"),
        result_row("h1", "hard", "sql_error"),
        result_row("h2", "hard", "correct"),
    ]
    corrected = [
        result_row("e1", "easy", "correct"),
        retried(result_row("h1", "hard", "correct"), 2),
        retried(result_row("h2", "hard", "wrong_result"), 3),
    ]

    report = render_comparison(baseline, correction_info(0), corrected, correction_info(2))

    assert "| Easy | 1 | 1 (100.0%) | 1 (100.0%) | +0.0 pts |" in report
    assert "| Hard | 2 | 1 (50.0%) | 1 (50.0%) | +0.0 pts |" in report
    assert "**Wrong without, correct with:** `h1`" in report
    assert "**Correct without, wrong with:** `h2`" in report
    assert "2 questions retried, and 1 of those ended correct" in report
    assert "| LLM calls | 3 | 6 |" in report


def test_comparison_reports_a_real_gain() -> None:
    baseline = [result_row("h1", "hard", "sql_error"), result_row("h2", "hard", "correct")]
    corrected = [
        retried(result_row("h1", "hard", "correct"), 2),
        result_row("h2", "hard", "correct"),
    ]

    report = render_comparison(baseline, correction_info(0), corrected, correction_info(2))

    assert "| **Overall** | 2 | 1 (50.0%) | 2 (100.0%) | +50.0 pts |" in report


def test_provider_outage_is_flagged_as_an_invalid_run() -> None:
    results = [result_row("e1", "easy", "llm_error")]

    assert "**Invalid run:** 1 questions" in render_report(results, correction_info(0))
    comparison = render_comparison(results, correction_info(0), results, correction_info(2))
    assert "**Invalid run:** 2 questions" in comparison


def test_healthy_runs_have_no_outage_warning() -> None:
    results = [result_row("e1", "easy", "wrong_result")]

    assert "Invalid run" not in render_report(results, correction_info(0))


def test_report_states_the_correction_mode() -> None:
    results = [result_row("e1", "easy", "correct")]

    assert "**Self-correction:** off" in render_report(results, correction_info(0))
    assert "on, up to 2 retries" in render_report(results, correction_info(2))


@pytest.mark.parametrize(
    ("compare", "mode", "enabled", "expected"),
    [
        (True, None, True, [0, 2]),
        (True, None, False, [0, 2]),
        (False, "on", False, [2]),
        (False, "off", True, [0]),
        (False, None, True, [2]),
        (False, None, False, [0]),
    ],
)
def test_retry_modes(compare: bool, mode: str | None, enabled: bool, expected: list[int]) -> None:
    args = Namespace(compare=compare, self_correction=mode)
    settings = Settings(self_correction_enabled=enabled, self_correction_max_retries=2)

    assert retry_modes(args, settings) == expected


def test_score_adds_up_usage_across_retries(stub_execute: list) -> None:
    stub_execute.append(SqlExecutionError("no such column", "SELECT x"))
    stub_execute.append(QueryResult(["n"], ["int8"], [[42]], False))

    class TwoAnswers(FakeLLM):
        def generate_sql(self, system_prompt: str, question: str) -> LLMOutput:
            output = super().generate_sql(system_prompt, question)
            return replace(output, sql=f"SELECT {len(self.questions)}")

    result = score(
        question(), GOLD, sample_tables(), TwoAnswers("unused"), settings_stub(), max_retries=2
    )

    assert result.outcome == "correct"
    assert result.llm_calls == 2
    assert result.input_tokens == 200
    assert result.output_tokens == 40


def test_report_omits_cost_for_unknown_prices() -> None:
    info = RunInfo("olist_v1", "2026-11-05T00:00:00Z", "model", "medium", "v1", None, None)

    report = render_report([result_row("e1", "easy", "correct")], info)

    assert "tokens" in report
    assert "$" not in report
