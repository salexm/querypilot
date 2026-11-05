import pytest

from app.pipeline.errors import SqlValidationError
from app.pipeline.validate import validate_sql

TABLES = frozenset({"orders", "customers"})

WRITE_STATEMENTS = [
    "DROP TABLE orders",
    "drop table orders",
    "DrOp TaBlE orders",
    "DROP DATABASE analytics",
    "INSERT INTO orders VALUES ('x')",
    "UPDATE orders SET order_status = 'x'",
    "DELETE FROM orders",
    "TRUNCATE orders",
    "ALTER TABLE orders ADD COLUMN x int",
    "CREATE TABLE t (i int)",
    "CREATE ROLE attacker SUPERUSER",
    "GRANT ALL ON orders TO PUBLIC",
    "COPY orders TO '/tmp/x'",
    "COPY orders FROM PROGRAM 'id'",
    "SET ROLE postgres",
    "SET statement_timeout = 0",
    "EXPLAIN ANALYZE DELETE FROM orders",
    "DO $$ BEGIN DELETE FROM orders; END $$",
    "VACUUM orders",
    "CALL some_procedure()",
]

MULTI_STATEMENT_INJECTIONS = [
    "SELECT 1; SELECT 2",
    "SELECT 1; DROP TABLE orders",
    "SELECT 1; DROP TABLE orders;",
    "SELECT 1;; DROP TABLE orders",
    "SELECT * FROM orders; DELETE FROM orders; --",
    "SELECT 1; -- harmless\nDROP TABLE orders",
    "SELECT 1 /* harmless */; DROP TABLE orders",
    "SELECT 1;\n\n\tTRUNCATE orders",
    "SELECT 1; COMMIT; DROP TABLE orders",
    "BEGIN; DROP TABLE orders; COMMIT",
]

HIDDEN_WRITES = [
    "WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d",
    "WITH u AS (UPDATE orders SET order_status = 'x' RETURNING *) SELECT * FROM u",
    "WITH i AS (INSERT INTO orders VALUES ('x') RETURNING *) SELECT * FROM i",
    "SELECT * INTO copied FROM orders",
    "SELECT * FROM orders FOR UPDATE",
    "SELECT * FROM orders FOR SHARE",
]

DANGEROUS_FUNCTIONS = [
    "SELECT pg_sleep(100)",
    "SELECT pg_catalog.pg_sleep(100)",
    'SELECT "pg_sleep"(100)',
    "SELECT PG_READ_FILE('/etc/passwd')",
    "SELECT pg_terminate_backend(1)",
    "SELECT set_config('statement_timeout', '0', false)",
    "SELECT current_setting('server_version')",
    "SELECT query_to_xml('DELETE FROM orders', true, true, '')",
    "SELECT nextval('some_sequence')",
    "SELECT lo_import('/etc/passwd')",
    "SELECT * FROM orders WHERE pg_sleep(100) IS NULL",
]

OUTSIDE_TABLES = [
    "SELECT * FROM secrets",
    "SELECT * FROM pg_user",
    "SELECT * FROM pg_catalog.pg_settings",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM orders o JOIN pg_catalog.pg_user u ON true",
    "SELECT (SELECT count(*) FROM pg_user)",
    "SELECT 1 UNION SELECT usename FROM pg_user",
    "WITH pg_user AS (SELECT 1) SELECT * FROM pg_catalog.pg_user",
]

NOT_SELECTS = [
    "",
    ";",
    "   ",
    "not sql at all (",
    "';DROP TABLE orders;--",
    "VALUES (1)",
    "TABLE orders",
]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "select count(*) from public.orders",
        "SELECT 1 UNION SELECT 2",
        "(SELECT 1)",
        "WITH recent AS (SELECT * FROM orders) SELECT * FROM recent",
        "SELECT o.* FROM orders o JOIN customers c USING (customer_id)",
        "SELECT date_trunc('month', order_purchase_timestamp) FROM orders",
        "SELECT * FROM generate_series(1, 3)",
        "SELECT * FROM customers WHERE customer_city LIKE '%rio%'",
        "SELECT 'DROP TABLE orders; --' AS harmless_text",
        "SELECT order_id AS delete_me FROM orders",
    ],
)
def test_allows_read_queries(sql: str) -> None:
    assert validate_sql(sql, TABLES) == sql


def test_strips_whitespace_and_trailing_semicolon() -> None:
    assert validate_sql("  SELECT 1;  \n", TABLES) == "SELECT 1"


@pytest.mark.parametrize(
    "sql",
    WRITE_STATEMENTS
    + MULTI_STATEMENT_INJECTIONS
    + HIDDEN_WRITES
    + DANGEROUS_FUNCTIONS
    + OUTSIDE_TABLES
    + NOT_SELECTS,
)
def test_rejects_malicious_sql(sql: str) -> None:
    with pytest.raises(SqlValidationError):
        validate_sql(sql, TABLES)


@pytest.mark.parametrize("sql", MULTI_STATEMENT_INJECTIONS)
def test_multi_statement_injection_is_rejected_as_multiple_statements(sql: str) -> None:
    with pytest.raises(SqlValidationError, match="one SQL statement"):
        validate_sql(sql, TABLES)


def test_error_keeps_the_rejected_sql() -> None:
    with pytest.raises(SqlValidationError) as caught:
        validate_sql("DELETE FROM orders", TABLES)

    assert caught.value.sql == "DELETE FROM orders"
