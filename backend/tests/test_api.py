from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_pipeline
from app.llm.base import GeneratedSql, LLMConfigurationError, LLMError
from app.main import app
from app.pipeline.errors import DatabaseUnavailableError, QueryTimeoutError, SqlExecutionError
from app.pipeline.execute import QueryResult
from app.pipeline.orchestrator import QueryPipeline
from tests.fakes import FakeLLM, chartable_result, sample_result, sample_tables


class FailingLLM:
    def __init__(self, error: LLMError) -> None:
        self.error = error

    def generate_sql(self, system_prompt: str, question: str) -> GeneratedSql:
        raise self.error


def failing_executor(error: Exception) -> Callable[[str], QueryResult]:
    def execute(sql: str) -> QueryResult:
        raise error

    return execute


def succeed(sql: str) -> QueryResult:
    return sample_result()


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_pipeline(pipeline: QueryPipeline) -> None:
    app.dependency_overrides[get_pipeline] = lambda: pipeline


def test_query_returns_sql_and_rows(client: TestClient) -> None:
    use_pipeline(QueryPipeline(FakeLLM("SELECT 42 AS total"), sample_tables, succeed))

    response = client.post("/query", json={"question": "How many?"})

    assert response.status_code == 200
    assert response.json() == {
        "question": "How many?",
        "sql": "SELECT 42 AS total",
        "columns": ["total"],
        "rows": [[42]],
        "row_count": 1,
        "truncated": False,
        "chart": None,
    }


def test_query_returns_a_chart_when_one_fits(client: TestClient) -> None:
    pipeline = QueryPipeline(FakeLLM("SELECT 1"), sample_tables, lambda _: chartable_result())
    use_pipeline(pipeline)

    response = client.post("/query", json={"question": "Orders by state?"})

    assert response.json()["chart"] == {"type": "bar", "x_column": 0, "y_column": 1}


@pytest.mark.parametrize("body", [{}, {"question": ""}, {"question": "x" * 1001}])
def test_query_rejects_bad_requests(client: TestClient, body: dict[str, str]) -> None:
    use_pipeline(QueryPipeline(FakeLLM("SELECT 1"), sample_tables, succeed))

    assert client.post("/query", json=body).status_code == 422


@pytest.mark.parametrize(
    "sql",
    ["DROP TABLE orders", "SELECT 1; DROP TABLE orders", "SELECT 1; -- x\nDELETE FROM orders"],
)
def test_malicious_sql_is_blocked_and_reported(client: TestClient, sql: str) -> None:
    use_pipeline(QueryPipeline(FakeLLM(sql), sample_tables, failing_executor(AssertionError())))

    response = client.post("/query", json={"question": "Drop it"})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_sql"
    assert response.json()["sql"] == sql


def test_unanswerable_question(client: TestClient) -> None:
    use_pipeline(QueryPipeline(FakeLLM(""), sample_tables, succeed))

    response = client.post("/query", json={"question": "Weather?"})

    assert response.status_code == 422
    assert response.json()["code"] == "unanswerable_question"


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (SqlExecutionError("column x does not exist", "SELECT 1"), 422, "query_failed"),
        (QueryTimeoutError("too slow", "SELECT 1"), 504, "query_timeout"),
        (DatabaseUnavailableError("down"), 503, "database_unavailable"),
    ],
)
def test_execution_errors(client: TestClient, error: Exception, status: int, code: str) -> None:
    use_pipeline(QueryPipeline(FakeLLM("SELECT 1"), sample_tables, failing_executor(error)))

    response = client.post("/query", json={"question": "How many?"})

    assert response.status_code == status
    assert response.json()["code"] == code


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (LLMError("rate limited"), 502, "llm_failed"),
        (LLMConfigurationError("key rejected"), 503, "llm_not_configured"),
    ],
)
def test_llm_errors(client: TestClient, error: LLMError, status: int, code: str) -> None:
    use_pipeline(QueryPipeline(FailingLLM(error), sample_tables, succeed))

    response = client.post("/query", json={"question": "How many?"})

    assert response.status_code == status
    assert response.json()["code"] == code
