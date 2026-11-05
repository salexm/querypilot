"""Second layer of protection for generated SQL. The read-only role is the first."""

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.pipeline.errors import SqlValidationError

ALLOWED_ROOTS = (exp.Select, exp.SetOperation, exp.Subquery)

FORBIDDEN_NODES = (
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Create,
    exp.Delete,
    exp.Drop,
    exp.Insert,
    exp.Into,
    exp.Lock,
    exp.Merge,
    exp.Set,
    exp.TruncateTable,
    exp.Update,
)

FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink")

# set_config could lift the statement timeout, and the *_to_xml functions run
# SQL passed as a string, which would hide it from this validator.
FORBIDDEN_FUNCTIONS = frozenset(
    {
        "current_setting",
        "cursor_to_xml",
        "database_to_xml",
        "nextval",
        "query_to_xml",
        "query_to_xml_and_xmlschema",
        "query_to_xmlschema",
        "schema_to_xml",
        "set_config",
        "setval",
        "table_to_xml",
    }
)


def parse_single_statement(sql: str) -> exp.Expression:
    try:
        statements = [statement for statement in sqlglot.parse(sql, dialect="postgres") if statement]
    except SqlglotError as error:
        raise SqlValidationError("The generated SQL couldn't be parsed.", sql) from error
    if len(statements) != 1:
        raise SqlValidationError("Only one SQL statement is allowed.", sql)
    return statements[0]


def check_nodes(root: exp.Expression, sql: str) -> None:
    for node in root.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise SqlValidationError(f"{type(node).__name__} isn't allowed.", sql)


def function_name(function: exp.Func) -> str:
    name = function.name if isinstance(function, exp.Anonymous) else function.sql_name()
    return name.lower()


def check_functions(root: exp.Expression, sql: str) -> None:
    for function in root.find_all(exp.Func):
        name = function_name(function)
        if name in FORBIDDEN_FUNCTIONS or name.startswith(FORBIDDEN_FUNCTION_PREFIXES):
            raise SqlValidationError(f"The function {name} isn't allowed.", sql)


def check_tables(root: exp.Expression, allowed_tables: frozenset[str], sql: str) -> None:
    cte_names = {cte.alias.lower() for cte in root.find_all(exp.CTE)}
    for table in root.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            continue  # Set-returning functions such as generate_series.
        name = table.name.lower()
        if table.db and table.db.lower() != "public":
            raise SqlValidationError(f"The schema {table.db} isn't allowed.", sql)
        if name not in allowed_tables and not (name in cte_names and not table.db):
            raise SqlValidationError(f"The table {table.name} isn't allowed.", sql)


def validate_sql(sql: str, allowed_tables: frozenset[str]) -> str:
    """Return the SQL ready to run, or raise SqlValidationError."""
    cleaned = sql.strip().rstrip(";").rstrip()
    if not cleaned:
        raise SqlValidationError("The generated SQL was empty.", sql)
    root = parse_single_statement(cleaned)
    if not isinstance(root, ALLOWED_ROOTS):
        raise SqlValidationError("Only SELECT statements are allowed.", sql)
    check_nodes(root, sql)
    check_functions(root, sql)
    check_tables(root, allowed_tables, sql)
    return cleaned
