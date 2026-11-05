"""Execution accuracy: compare what two queries return, never their SQL text.

The comparison accepts differences that don't change the answer:

- Column order and column names don't matter.
- The generated query may return extra columns, but every gold column must appear.
- Row order matters only when the question asks for it.
- Numbers match within a small tolerance, so rounding for display isn't a miss.
- A year can be 2017 or 2017.0, and a month can be '2017-01' or '2017-01-01T00:00:00'.
"""

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

ABSOLUTE_TOLERANCE = 0.01
RELATIVE_TOLERANCE = 0.001

MONTH_TEXT = re.compile(r"^(\d{4}-\d{2})(-01)?([T ]00:00:00)?$")
MIDNIGHT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ]00:00:00$")

Row = Sequence[Any]


@dataclass(frozen=True)
class Comparison:
    matched: bool
    reason: str = ""


def normalize(value: Any) -> Any:
    """Reduce a cell to a number, normalized text, or None."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    month = MONTH_TEXT.match(text)
    if month:
        return month.group(1)
    midnight = MIDNIGHT.match(text)
    return midnight.group(1) if midnight else text.lower()


def cells_match(left: Any, right: Any) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return math.isclose(left, right, rel_tol=RELATIVE_TOLERANCE, abs_tol=ABSOLUTE_TOLERANCE)
    return left == right


def sort_key(row: Sequence[Any]) -> tuple[tuple[int, Any], ...]:
    """Give mixed rows a stable order: nulls, then booleans, numbers, and text."""

    def cell_key(cell: Any) -> tuple[int, Any]:
        if cell is None:
            return (0, 0)
        if isinstance(cell, bool):
            return (1, cell)
        return (2, cell) if isinstance(cell, float) else (3, cell)

    return tuple(cell_key(cell) for cell in row)


def rows_match(gold: list[list[Any]], candidate: list[list[Any]], ordered: bool) -> bool:
    left = gold if ordered else sorted(gold, key=sort_key)
    right = candidate if ordered else sorted(candidate, key=sort_key)
    return all(
        cells_match(gold_cell, candidate_cell)
        for gold_row, candidate_row in zip(left, right, strict=True)
        for gold_cell, candidate_cell in zip(gold_row, candidate_row, strict=True)
    )


def column_values(rows: list[list[Any]], column: int) -> list[Any]:
    return [row[column] for row in rows]


def could_match(gold_values: list[Any], candidate_values: list[Any], ordered: bool) -> bool:
    """Cheap per-column check that prunes the search for a column mapping."""
    return rows_match(
        [[value] for value in gold_values],
        [[value] for value in candidate_values],
        ordered,
    )


def find_mapping(
    gold: list[list[Any]],
    candidate: list[list[Any]],
    options: list[list[int]],
    ordered: bool,
    chosen: tuple[int, ...] = (),
) -> bool:
    """Try each assignment of gold columns to distinct candidate columns."""
    if len(chosen) == len(options):
        projected = [[row[column] for column in chosen] for row in candidate]
        return rows_match(gold, projected, ordered)
    return any(
        find_mapping(gold, candidate, options, ordered, (*chosen, column))
        for column in options[len(chosen)]
        if column not in chosen
    )


def compare_results(
    gold_rows: Sequence[Row], candidate_rows: Sequence[Row], ordered: bool
) -> Comparison:
    gold = [[normalize(cell) for cell in row] for row in gold_rows]
    candidate = [[normalize(cell) for cell in row] for row in candidate_rows]
    if len(gold) != len(candidate):
        return Comparison(False, f"expected {len(gold)} rows, got {len(candidate)}")
    if not gold:
        return Comparison(True)
    gold_width, candidate_width = len(gold[0]), len(candidate[0])
    if candidate_width < gold_width:
        return Comparison(False, f"expected {gold_width} columns, got {candidate_width}")
    options = [
        [
            column
            for column in range(candidate_width)
            if could_match(
                column_values(gold, gold_column), column_values(candidate, column), ordered
            )
        ]
        for gold_column in range(gold_width)
    ]
    for gold_column, matches in enumerate(options):
        if not matches:
            return Comparison(False, f"no column matches gold column {gold_column + 1}")
    if find_mapping(gold, candidate, options, ordered):
        return Comparison(True)
    return Comparison(False, "columns match separately, but rows don't line up")
