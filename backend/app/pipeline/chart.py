"""Rule-based chart selection. Returns no chart whenever one would mislead."""

import re
from dataclasses import dataclass
from typing import Any, Literal

NUMERIC_TYPES = frozenset({"int2", "int4", "int8", "float4", "float8", "numeric"})
TEMPORAL_TYPES = frozenset({"date", "timestamp", "timestamptz"})

# The lookbehind keeps rates such as orders_per_day from reading as time columns.
TIME_PART_NAME = re.compile(r"(^|_)(?<!per_)(year|quarter|month|week|day)($|_)", re.IGNORECASE)
IDENTIFIER_NAME = re.compile(r"(^|_)id$", re.IGNORECASE)
DATE_TEXT = re.compile(r"^\d{4}-\d{2}(-\d{2})?")

MAX_BARS = 30


@dataclass(frozen=True)
class ChartSpec:
    """Columns are positions, because SQL results can repeat a column name."""

    type: Literal["bar", "line"]
    x_column: int
    y_column: int


def is_date_text(values: list[Any]) -> bool:
    return all(isinstance(value, str) and DATE_TEXT.match(value) for value in values)


def is_time_column(name: str, data_type: str, values: list[Any]) -> bool:
    if data_type in TEMPORAL_TYPES:
        return True
    if data_type in NUMERIC_TYPES:
        return bool(TIME_PART_NAME.search(name))
    return is_date_text(values)


def find_time_column(columns: list[str], types: list[str], rows: list[list[Any]]) -> int | None:
    for index, (name, data_type) in enumerate(zip(columns, types, strict=True)):
        if is_time_column(name, data_type, [row[index] for row in rows]):
            return index
    return None


def find_category_column(types: list[str]) -> int | None:
    for index, data_type in enumerate(types):
        if data_type not in NUMERIC_TYPES and data_type not in TEMPORAL_TYPES:
            return index
    return None


def find_measure_column(columns: list[str], types: list[str], x_column: int) -> int | None:
    for index, (name, data_type) in enumerate(zip(columns, types, strict=True)):
        if index != x_column and data_type in NUMERIC_TYPES and not IDENTIFIER_NAME.search(name):
            return index
    return None


def has_unique_values(rows: list[list[Any]], column: int) -> bool:
    values = [row[column] for row in rows]
    return len(set(values)) == len(values)


def select_chart(
    columns: list[str],
    types: list[str],
    rows: list[list[Any]],
    truncated: bool,
) -> ChartSpec | None:
    """Pick a line for values over time and a bar for values by category.

    A partial result, a single row, or an x column with repeats (which means
    the rows have a second grouping) can't be drawn honestly as one series.
    """
    if truncated or len(rows) < 2:
        return None
    time_column = find_time_column(columns, types, rows)
    x_column = time_column if time_column is not None else find_category_column(types)
    if x_column is None or not has_unique_values(rows, x_column):
        return None
    y_column = find_measure_column(columns, types, x_column)
    if y_column is None:
        return None
    if time_column is not None:
        return ChartSpec("line", x_column, y_column)
    return ChartSpec("bar", x_column, y_column) if len(rows) <= MAX_BARS else None
