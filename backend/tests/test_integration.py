"""Runs against the seeded database. Use `docker compose exec api pytest`.

The attack tests call the executor directly, skipping the validator, to prove
that the read-only role protects the data on its own.
"""

import psycopg
import pytest
from psycopg import errors as pg_errors

from app.config import Settings
from app.pipeline.errors import DatabaseUnavailableError, QueryTimeoutError, SqlExecutionError
from app.pipeline.execute import execute_query, readonly_connection
from app.pipeline.orchestrator import QueryPipeline
from app.schema.introspect import Table, format_schema, load_tables
from tests.fakes import FakeLLM

pytestmark = pytest.mark.integration

SELLER_COUNT = 3_095


@pytest.fixture(scope="module")
def settings() -> Settings:
    settings = Settings(query_timeout_ms=500, query_max_rows=5)
    try:
        with readonly_connection(settings) as connection:
            if not load_tables(connection):
                pytest.skip("The analytics database hasn't been seeded.")
    except DatabaseUnavailableError:
        pytest.skip("The analytics database isn't reachable.")
    return settings


def seller_count(settings: Settings) -> int:
    return execute_query("SELECT count(*) FROM sellers", settings).rows[0][0]


def raw_connection(settings: Settings, dbname: str) -> psycopg.Connection:
    """Connect as the read-only role without the executor's read-only mode."""
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=dbname,
        user=settings.analytics_readonly_user,
        password=settings.analytics_readonly_password.get_secret_value(),
        autocommit=True,
    )


def test_introspection_finds_seeded_tables(settings: Settings) -> None:
    with readonly_connection(settings) as connection:
        tables = load_tables(connection)

    assert {table.name for table in tables} >= {"orders", "customers", "order_items"}
    text = format_schema(tables)
    assert "customer_unique_id" in text
    assert "REFERENCES customers" in text


def test_row_cap_is_enforced_and_reported(settings: Settings) -> None:
    result = execute_query("SELECT order_id FROM orders", settings)

    assert len(result.rows) == 5
    assert result.truncated is True


def test_exact_row_cap_is_not_reported_as_truncated(settings: Settings) -> None:
    result = execute_query("SELECT order_id FROM orders LIMIT 5", settings)

    assert len(result.rows) == 5
    assert result.truncated is False


def test_statement_timeout_is_enforced(settings: Settings) -> None:
    with pytest.raises(QueryTimeoutError):
        execute_query("SELECT pg_sleep(5)", settings)


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE sellers",
        "DELETE FROM sellers",
        "UPDATE sellers SET seller_city = 'x'",
        "INSERT INTO sellers VALUES ('x', '1', 'c', 'SP')",
        "TRUNCATE sellers",
        "CREATE TABLE public.t (i int)",
        "SELECT 1; DROP TABLE sellers",
        "SELECT 1; DELETE FROM sellers",
        "SELECT 1; COMMIT; DELETE FROM sellers",
        "WITH d AS (DELETE FROM sellers RETURNING *) SELECT * FROM d",
        "SELECT * INTO public.copied FROM sellers",
    ],
)
def test_attacks_fail_without_the_validator(settings: Settings, sql: str) -> None:
    with pytest.raises(SqlExecutionError):
        execute_query(sql, settings)

    assert seller_count(settings) == SELLER_COUNT


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM sellers",
        "DROP TABLE sellers",
        "TRUNCATE sellers",
        "CREATE TABLE public.t (i int)",
    ],
)
def test_role_has_no_write_privilege_even_in_read_write_mode(settings: Settings, sql: str) -> None:
    with raw_connection(settings, settings.analytics_db_name) as connection:
        connection.execute("SET default_transaction_read_only = off")
        with pytest.raises(pg_errors.InsufficientPrivilege):
            connection.execute(sql)

    assert seller_count(settings) == SELLER_COUNT


@pytest.mark.parametrize("dbname", ["postgres"])
def test_role_cannot_connect_to_other_databases(settings: Settings, dbname: str) -> None:
    with pytest.raises(psycopg.OperationalError):
        raw_connection(settings, dbname)


def test_duplicate_column_names_are_returned(settings: Settings) -> None:
    sql = "SELECT o.order_id, i.order_id FROM orders o JOIN order_items i USING (order_id) LIMIT 1"

    assert execute_query(sql, settings).columns == ["order_id", "order_id"]


def test_like_with_percent_runs_without_parameters(settings: Settings) -> None:
    sql = "SELECT customer_city FROM customers WHERE customer_city LIKE '%rio%' LIMIT 1"

    assert len(execute_query(sql, settings).rows) == 1


def test_pipeline_runs_end_to_end_with_a_fake_llm(settings: Settings) -> None:
    def load_schema() -> list[Table]:
        with readonly_connection(settings) as connection:
            return load_tables(connection)

    llm = FakeLLM("SELECT count(*) AS total FROM orders")
    pipeline = QueryPipeline(llm, load_schema, lambda sql: execute_query(sql, settings))

    result = pipeline.run("How many orders are there?")

    assert result.rows == [[99_441]]
    assert "TABLE orders" in llm.system_prompts[0]
