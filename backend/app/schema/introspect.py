from dataclasses import dataclass, field

import psycopg

COLUMNS_QUERY = """
SELECT
  c.relname,
  obj_description(c.oid, 'pg_class'),
  a.attname,
  format_type(a.atttypid, a.atttypmod),
  a.attnotnull,
  EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.oid AND i.indisprimary AND a.attnum = ANY (i.indkey)
  ),
  col_description(c.oid, a.attnum)
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid
WHERE n.nspname = 'public'
  AND c.relkind IN ('r', 'p', 'v', 'm')
  AND a.attnum > 0
  AND NOT a.attisdropped
  AND has_table_privilege(c.oid, 'SELECT')
ORDER BY c.relname, a.attnum
"""

FOREIGN_KEYS_QUERY = """
SELECT c.relname, pg_get_constraintdef(k.oid)
FROM pg_constraint k
JOIN pg_class c ON c.oid = k.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE k.contype = 'f' AND n.nspname = 'public'
ORDER BY c.relname, k.conname
"""


@dataclass(frozen=True)
class Column:
    name: str
    data_type: str
    not_null: bool
    primary_key: bool
    comment: str | None


@dataclass
class Table:
    name: str
    comment: str | None
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[str] = field(default_factory=list)


def load_tables(connection: psycopg.Connection) -> list[Table]:
    tables: dict[str, Table] = {}
    for name, comment, column, data_type, not_null, primary_key, column_comment in (
        connection.execute(COLUMNS_QUERY).fetchall()
    ):
        table = tables.setdefault(name, Table(name, comment))
        table.columns.append(Column(column, data_type, not_null, primary_key, column_comment))
    for name, definition in connection.execute(FOREIGN_KEYS_QUERY).fetchall():
        if name in tables:
            tables[name].foreign_keys.append(definition)
    return list(tables.values())


def format_column(column: Column) -> str:
    line = f"  {column.name} {column.data_type}"
    if column.primary_key:
        line += " PRIMARY KEY"
    elif column.not_null:
        line += " NOT NULL"
    return f"{line} -- {column.comment}" if column.comment else line


def format_table(table: Table) -> str:
    header = f"TABLE {table.name}"
    lines = [f"{header} -- {table.comment}" if table.comment else header]
    lines += [format_column(column) for column in table.columns]
    lines += [f"  {definition}" for definition in table.foreign_keys]
    return "\n".join(lines)


def format_schema(tables: list[Table]) -> str:
    return "\n\n".join(format_table(table) for table in tables)
