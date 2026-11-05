from app.schema.introspect import Column, Table, format_column, format_schema
from tests.fakes import sample_tables


def test_format_column_marks_keys_and_comments() -> None:
    column = Column("order_id", "text", True, True, "Unique order.")

    assert format_column(column) == "  order_id text PRIMARY KEY -- Unique order."


def test_format_column_marks_not_null_without_comment() -> None:
    assert format_column(Column("status", "text", True, False, None)) == "  status text NOT NULL"


def test_format_schema_includes_comments_and_foreign_keys() -> None:
    text = format_schema(sample_tables())

    assert "TABLE orders -- All orders." in text
    assert "FOREIGN KEY (customer_id) REFERENCES customers(customer_id)" in text


def test_format_schema_separates_tables() -> None:
    text = format_schema([Table("a", None), Table("b", None)])

    assert text == "TABLE a\n\nTABLE b"
