import pytest

from app.config import Settings
from app.llm.base import LLMError, LLMOutput
from app.pipeline.errors import (
    DatabaseUnavailableError,
    QueryTimeoutError,
    SqlExecutionError,
    SqlValidationError,
    UnanswerableQuestionError,
)
from app.pipeline.execute import QueryResult
from app.pipeline.orchestrator import NO_ROWS_PROBLEM, QueryPipeline
from tests.fakes import sample_result, sample_tables

EMPTY = QueryResult(columns=["total"], column_types=["int8"], rows=[], truncated=False)


class ScriptedLLM:
    """Returns each scripted answer in turn and records the prompts it received."""

    def __init__(self, *answers: str | Exception) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []

    def generate_sql(self, system_prompt: str, question: str) -> LLMOutput:
        self.prompts.append(question)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return LLMOutput(sql=answer)


class ScriptedExecutor:
    """Maps SQL to a result or error, and records what actually ran."""

    def __init__(self, outcomes: dict[str, QueryResult | Exception]) -> None:
        self.outcomes = outcomes
        self.calls: list[str] = []

    def __call__(self, sql: str) -> QueryResult:
        self.calls.append(sql)
        outcome = self.outcomes.get(sql, sample_result())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def pipeline(llm: ScriptedLLM, executor: ScriptedExecutor, max_retries: int = 2) -> QueryPipeline:
    return QueryPipeline(llm, sample_tables, executor, max_retries)


BAD = "SELECT missing FROM orders"
BAD_TWO = "SELECT also_missing FROM orders"
BAD_THREE = "SELECT still_missing FROM orders"
GOOD = "SELECT count(*) FROM orders"
NO_SUCH_COLUMN = SqlExecutionError('column "missing" does not exist', BAD)


def test_sql_error_is_sent_back_and_the_fix_is_used() -> None:
    llm = ScriptedLLM(BAD, GOOD)
    executor = ScriptedExecutor({BAD: NO_SUCH_COLUMN})

    result = pipeline(llm, executor).run("How many orders?")

    assert result.sql == GOOD
    assert result.rows == [[42]]
    assert [attempt.sql for attempt in result.attempts] == [BAD, GOOD]
    assert result.attempts[0].problem == 'column "missing" does not exist'
    assert result.attempts[1].problem is None


def test_retry_prompt_contains_the_question_sql_and_error() -> None:
    llm = ScriptedLLM(BAD, GOOD)

    pipeline(llm, ScriptedExecutor({BAD: NO_SUCH_COLUMN})).run("How many orders?")

    assert llm.prompts[0] == "How many orders?"
    assert "How many orders?" in llm.prompts[1]
    assert BAD in llm.prompts[1]
    assert 'column "missing" does not exist' in llm.prompts[1]


def test_retry_prompt_survives_braces_in_the_inputs() -> None:
    llm = ScriptedLLM(BAD, GOOD)

    pipeline(llm, ScriptedExecutor({BAD: NO_SUCH_COLUMN})).run("What is {sql} {0}?")

    assert "What is {sql} {0}?" in llm.prompts[1]


def test_empty_result_triggers_a_retry() -> None:
    llm = ScriptedLLM(BAD, GOOD)
    executor = ScriptedExecutor({BAD: EMPTY})

    result = pipeline(llm, executor).run("How many orders?")

    assert result.sql == GOOD
    assert NO_ROWS_PROBLEM in llm.prompts[1]


@pytest.mark.parametrize(
    "error",
    [
        QueryTimeoutError("too slow", BAD),
        SqlExecutionError("syntax error", BAD),
    ],
)
def test_query_failures_are_retried(error: Exception) -> None:
    llm = ScriptedLLM(BAD, GOOD)

    assert pipeline(llm, ScriptedExecutor({BAD: error})).run("Q").sql == GOOD


def test_validator_rejection_is_retried_without_running_the_sql() -> None:
    llm = ScriptedLLM("DROP TABLE orders", GOOD)
    executor = ScriptedExecutor({})

    result = pipeline(llm, executor).run("Q")

    assert result.sql == GOOD
    assert executor.calls == [GOOD]


def test_stops_after_two_retries_and_raises_the_last_error() -> None:
    llm = ScriptedLLM(BAD, BAD_TWO, BAD_THREE, GOOD)
    executor = ScriptedExecutor(
        {
            BAD: NO_SUCH_COLUMN,
            BAD_TWO: SqlExecutionError("second error", BAD_TWO),
            BAD_THREE: SqlExecutionError("third error", BAD_THREE),
        }
    )

    with pytest.raises(SqlExecutionError, match="third error") as caught:
        pipeline(llm, executor).run("Q")

    assert caught.value.sql == BAD_THREE
    assert len(llm.prompts) == 3
    assert executor.calls == [BAD, BAD_TWO, BAD_THREE]


def test_disabled_correction_makes_one_call_and_raises() -> None:
    llm = ScriptedLLM(BAD, GOOD)

    with pytest.raises(SqlExecutionError):
        pipeline(llm, ScriptedExecutor({BAD: NO_SUCH_COLUMN}), max_retries=0).run("Q")

    assert len(llm.prompts) == 1


def test_disabled_correction_returns_empty_results() -> None:
    llm = ScriptedLLM(BAD, GOOD)

    result = pipeline(llm, ScriptedExecutor({BAD: EMPTY}), max_retries=0).run("Q")

    assert result.rows == []
    assert len(llm.prompts) == 1


def test_success_on_the_first_try_makes_one_call() -> None:
    llm = ScriptedLLM(GOOD, BAD)

    result = pipeline(llm, ScriptedExecutor({})).run("Q")

    assert len(llm.prompts) == 1
    assert len(result.attempts) == 1


def test_repeating_empty_sql_accepts_zero_rows_without_rerunning() -> None:
    llm = ScriptedLLM(BAD, BAD)
    executor = ScriptedExecutor({BAD: EMPTY})

    result = pipeline(llm, executor).run("Q")

    assert result.rows == []
    assert executor.calls == [BAD]
    assert len(llm.prompts) == 2


def test_empty_results_stay_the_answer_when_every_retry_returns_nothing() -> None:
    llm = ScriptedLLM(BAD, BAD_TWO, BAD_THREE)
    executor = ScriptedExecutor({BAD: EMPTY, BAD_TWO: EMPTY, BAD_THREE: EMPTY})

    result = pipeline(llm, executor).run("Q")

    assert result.rows == []
    assert len(result.attempts) == 3


def test_valid_empty_result_beats_a_retry_that_errors() -> None:
    llm = ScriptedLLM(BAD, BAD_TWO, BAD_THREE)
    executor = ScriptedExecutor(
        {
            BAD: EMPTY,
            BAD_TWO: SqlExecutionError("broken", BAD_TWO),
            BAD_THREE: SqlExecutionError("broken", BAD_THREE),
        }
    )

    result = pipeline(llm, executor).run("Q")

    assert result.sql == BAD
    assert result.rows == []


def test_repeating_failed_sql_stops_early_and_raises() -> None:
    llm = ScriptedLLM(BAD, BAD, GOOD)
    executor = ScriptedExecutor({BAD: NO_SUCH_COLUMN})

    with pytest.raises(SqlExecutionError):
        pipeline(llm, executor).run("Q")

    assert executor.calls == [BAD]
    assert len(llm.prompts) == 2


def test_giving_up_on_a_retry_raises_the_real_error() -> None:
    llm = ScriptedLLM(BAD, "")

    with pytest.raises(SqlExecutionError):
        pipeline(llm, ScriptedExecutor({BAD: NO_SUCH_COLUMN})).run("Q")


def test_unanswerable_questions_are_not_retried() -> None:
    llm = ScriptedLLM("", GOOD)

    with pytest.raises(UnanswerableQuestionError):
        pipeline(llm, ScriptedExecutor({})).run("What's the weather?")

    assert len(llm.prompts) == 1


def test_llm_errors_are_not_retried() -> None:
    llm = ScriptedLLM(LLMError("rate limited"), GOOD)

    with pytest.raises(LLMError):
        pipeline(llm, ScriptedExecutor({})).run("Q")

    assert len(llm.prompts) == 1


def test_database_outages_are_not_retried() -> None:
    llm = ScriptedLLM(BAD, GOOD)
    executor = ScriptedExecutor({BAD: DatabaseUnavailableError("down")})

    with pytest.raises(DatabaseUnavailableError):
        pipeline(llm, executor).run("Q")

    assert len(llm.prompts) == 1


@pytest.mark.parametrize(
    "malicious",
    [
        "DROP TABLE orders",
        "SELECT 1; DROP TABLE orders",
        "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
        "SELECT pg_sleep(100)",
        "SELECT * FROM pg_user",
    ],
)
def test_retried_sql_is_validated_like_any_other(malicious: str) -> None:
    llm = ScriptedLLM(BAD, malicious, malicious)
    executor = ScriptedExecutor({BAD: NO_SUCH_COLUMN})

    with pytest.raises(SqlValidationError):
        pipeline(llm, executor).run("Q")

    assert executor.calls == [BAD]


def test_every_attempt_blocked_never_touches_the_database() -> None:
    llm = ScriptedLLM("DROP TABLE orders", "DELETE FROM orders", "TRUNCATE orders")
    executor = ScriptedExecutor({})

    with pytest.raises(SqlValidationError):
        pipeline(llm, executor).run("Q")

    assert executor.calls == []
    assert len(llm.prompts) == 3


@pytest.mark.parametrize(
    ("enabled", "retries", "expected"),
    [(True, 2, 2), (False, 2, 0), (True, 0, 0), (True, 1, 1)],
)
def test_settings_toggle(enabled: bool, retries: int, expected: int) -> None:
    settings = Settings(self_correction_enabled=enabled, self_correction_max_retries=retries)

    assert settings.correction_retries == expected


def test_settings_default_to_two_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SELF_CORRECTION_ENABLED", raising=False)
    monkeypatch.delenv("SELF_CORRECTION_MAX_RETRIES", raising=False)

    assert Settings().correction_retries == 2
