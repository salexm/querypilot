from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_pipeline
from app.api.rate_limit import (
    MAX_TRACKED_KEYS,
    QueryLimits,
    RateLimitExceededError,
    SlidingWindowLimiter,
    client_ip,
    get_query_limits,
)
from app.main import app
from app.pipeline.errors import DatabaseUnavailableError
from app.pipeline.orchestrator import QueryPipeline
from tests.fakes import FakeLLM, sample_result, sample_tables


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_limiter_allows_up_to_the_limit_then_blocks() -> None:
    limiter = SlidingWindowLimiter(2, 60, Clock())

    assert limiter.wait_seconds("a") == 0
    assert limiter.wait_seconds("a") == 0
    assert limiter.wait_seconds("a") == 60


def test_limiter_tracks_each_key_separately() -> None:
    limiter = SlidingWindowLimiter(1, 60, Clock())

    assert limiter.wait_seconds("a") == 0
    assert limiter.wait_seconds("b") == 0
    assert limiter.wait_seconds("a") > 0


def test_limiter_frees_capacity_as_hits_expire() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(2, 60, clock)
    limiter.wait_seconds("a")
    clock.now += 30
    limiter.wait_seconds("a")

    clock.now += 20
    assert limiter.wait_seconds("a") == 10

    clock.now += 10
    assert limiter.wait_seconds("a") == 0


def test_blocked_requests_do_not_extend_the_wait() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(1, 60, clock)
    limiter.wait_seconds("a")

    for _ in range(5):
        clock.now += 10
        limiter.wait_seconds("a")
    clock.now += 10

    assert limiter.wait_seconds("a") == 0


def test_limiter_memory_stays_bounded() -> None:
    clock = Clock()
    limiter = SlidingWindowLimiter(1, 60, clock)
    for index in range(MAX_TRACKED_KEYS):
        limiter.wait_seconds(str(index))

    clock.now += 61
    limiter.wait_seconds("new")

    assert len(limiter._hits) == 1


def test_per_ip_blocks_do_not_use_the_daily_budget() -> None:
    limits = QueryLimits(per_minute=1, per_day=2)
    limits.check("1.1.1.1")
    for _ in range(5):
        with pytest.raises(RateLimitExceededError) as caught:
            limits.check("1.1.1.1")
        assert caught.value.code == "rate_limited"

    limits.check("2.2.2.2")


def test_daily_limit_covers_all_visitors_together() -> None:
    limits = QueryLimits(per_minute=10, per_day=2)
    limits.check("1.1.1.1")
    limits.check("2.2.2.2")

    with pytest.raises(RateLimitExceededError) as caught:
        limits.check("3.3.3.3")

    assert caught.value.code == "daily_limit_reached"


def fake_request(forwarded: str | None, host: str = "10.0.0.1") -> Any:
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


@pytest.mark.parametrize(
    ("forwarded", "hops", "expected"),
    [
        (None, 0, "10.0.0.1"),
        ("1.1.1.1", 0, "10.0.0.1"),
        ("1.1.1.1", 1, "1.1.1.1"),
        ("6.6.6.6, 1.1.1.1", 1, "1.1.1.1"),
        ("6.6.6.6, 1.1.1.1, 2.2.2.2", 2, "1.1.1.1"),
        ("1.1.1.1", 2, "10.0.0.1"),
        (None, 1, "10.0.0.1"),
        ("", 1, "10.0.0.1"),
    ],
)
def test_client_ip_counts_from_the_right(forwarded: str | None, hops: int, expected: str) -> None:
    assert client_ip(fake_request(forwarded), hops) == expected


def test_forged_forwarded_entries_cannot_change_the_identity() -> None:
    first = client_ip(fake_request("6.6.6.6, 1.1.1.1"), 1)
    second = client_ip(fake_request("7.7.7.7, 1.1.1.1"), 1)

    assert first == second == "1.1.1.1"


def test_client_ip_handles_a_missing_client() -> None:
    request = SimpleNamespace(headers={}, client=None)

    assert client_ip(request, 0) == "unknown"  # type: ignore[arg-type]


@pytest.fixture
def client() -> Iterator[TestClient]:
    pipeline = QueryPipeline(FakeLLM("SELECT 1"), sample_tables, lambda _: sample_result())
    app.dependency_overrides[get_pipeline] = lambda: pipeline
    limits = QueryLimits(per_minute=2, per_day=100)
    app.dependency_overrides[get_query_limits] = lambda: limits
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_endpoint_returns_a_friendly_429_with_retry_after(client: TestClient) -> None:
    for _ in range(2):
        assert client.post("/query", json={"question": "Q"}).status_code == 200

    response = client.post("/query", json={"question": "Q"})

    assert response.status_code == 429
    assert response.json()["code"] == "rate_limited"
    assert "try again" in response.json()["message"]
    assert int(response.headers["retry-after"]) > 0


def test_blocked_requests_never_reach_the_llm(client: TestClient) -> None:
    llm = FakeLLM("SELECT 1")
    pipeline = QueryPipeline(llm, sample_tables, lambda _: sample_result())
    app.dependency_overrides[get_pipeline] = lambda: pipeline

    for _ in range(5):
        client.post("/query", json={"question": "Q"})

    assert len(llm.questions) == 2


def test_health_is_not_rate_limited(client: TestClient) -> None:
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_health_does_not_touch_the_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("health must not connect")

    monkeypatch.setattr("app.api.routes.readonly_connection", fail)

    assert client.get("/health").json() == {"status": "ok"}


def test_ready_reports_a_working_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    connection = SimpleNamespace(execute=lambda sql: None)

    @contextmanager
    def working(settings: object) -> Iterator[SimpleNamespace]:
        yield connection

    monkeypatch.setattr("app.api.routes.readonly_connection", working)

    assert client.get("/health/ready").json() == {"status": "ok"}


def test_ready_reports_a_database_outage(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(settings: object) -> None:
        raise DatabaseUnavailableError("Couldn't connect to the analytics database.")

    monkeypatch.setattr("app.api.routes.readonly_connection", down)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


@pytest.mark.parametrize("length", [501, 5000])
def test_long_questions_get_a_friendly_error(client: TestClient, length: int) -> None:
    response = client.post("/query", json={"question": "x" * length})

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_question"
    assert "500 characters" in response.json()["message"]


def test_questions_at_the_limit_are_accepted(client: TestClient) -> None:
    assert client.post("/query", json={"question": "x" * 500}).status_code == 200
