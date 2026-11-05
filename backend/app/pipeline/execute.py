from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

import psycopg
from psycopg import errors as pg_errors

from app.config import Settings
from app.pipeline.errors import DatabaseUnavailableError, QueryTimeoutError, SqlExecutionError

CONNECT_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    column_types: list[str]
    rows: list[list[Any]]
    truncated: bool


@contextmanager
def readonly_connection(settings: Settings) -> Iterator[psycopg.Connection]:
    """Connect as the read-only role, the only role generated SQL may use."""
    try:
        connection = psycopg.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.analytics_db_name,
            user=settings.analytics_readonly_user,
            password=settings.analytics_readonly_password.get_secret_value(),
            sslmode=settings.postgres_sslmode,
            connect_timeout=CONNECT_TIMEOUT_SECONDS,
        )
    except psycopg.OperationalError as error:
        raise DatabaseUnavailableError("Couldn't connect to the analytics database.") from error
    with connection:
        connection.read_only = True
        yield connection


def to_json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date | time):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


def type_name(connection: psycopg.Connection, type_code: int) -> str:
    info = connection.adapters.types.get(type_code)
    return info.name if info else "unknown"


def fetch_capped(connection: psycopg.Connection, sql: str, max_rows: int) -> QueryResult:
    """Fetch through a server-side cursor, so the cap holds whatever the SQL says."""
    with connection.cursor(name="generated_query") as cursor:
        cursor.execute(sql)
        fetched = cursor.fetchmany(max_rows + 1)
        description = cursor.description or []
    columns = [column.name for column in description]
    column_types = [type_name(connection, column.type_code) for column in description]
    rows = [[to_json_value(value) for value in row] for row in fetched[:max_rows]]
    return QueryResult(columns, column_types, rows, truncated=len(fetched) > max_rows)


def execute_query(sql: str, settings: Settings) -> QueryResult:
    with readonly_connection(settings) as connection:
        try:
            connection.execute(
                "SELECT set_config('statement_timeout', %s, true)",
                (str(settings.query_timeout_ms),),
            )
            return fetch_capped(connection, sql, settings.query_max_rows)
        except pg_errors.QueryCanceled as error:
            message = f"The query ran longer than {settings.query_timeout_ms} ms."
            raise QueryTimeoutError(message, sql) from error
        except psycopg.OperationalError as error:
            raise DatabaseUnavailableError(
                "Lost the analytics database connection.", sql
            ) from error
        except psycopg.Error as error:
            detail = error.diag.message_primary or "The database rejected the query."
            raise SqlExecutionError(detail, sql) from error
