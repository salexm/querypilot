import pytest

from app.pipeline.chart import ChartSpec, select_chart


def test_values_over_time_make_a_line() -> None:
    chart = select_chart(
        ["month", "orders"],
        ["timestamp", "int8"],
        [["2017-01-01T00:00:00", 800], ["2017-02-01T00:00:00", 1780]],
        False,
    )

    assert chart == ChartSpec("line", 0, 1)


@pytest.mark.parametrize(
    ("columns", "types", "rows"),
    [
        (["year", "revenue"], ["int4", "numeric"], [[2017, 10.5], [2018, 20.5]]),
        (["order_month", "total"], ["int4", "int8"], [[1, 5], [2, 6]]),
        (["month", "total"], ["text", "int8"], [["2017-01", 5], ["2017-02", 6]]),
        (["day", "total"], ["date", "int8"], [["2017-01-01", 5], ["2017-01-02", 6]]),
    ],
)
def test_time_columns_are_recognised(
    columns: list[str], types: list[str], rows: list[list[object]]
) -> None:
    assert select_chart(columns, types, rows, False) == ChartSpec("line", 0, 1)


def test_values_by_category_make_a_bar() -> None:
    chart = select_chart(["state", "orders"], ["text", "int8"], [["SP", 9], ["RJ", 4]], False)

    assert chart == ChartSpec("bar", 0, 1)


def test_measure_can_come_before_the_label() -> None:
    chart = select_chart(["orders", "state"], ["int8", "text"], [[9, "SP"], [4, "RJ"]], False)

    assert chart == ChartSpec("bar", 1, 0)


def test_first_measure_is_used_so_scales_are_never_mixed() -> None:
    chart = select_chart(
        ["state", "avg_score", "orders"],
        ["text", "numeric", "int8"],
        [["PR", 4.18, 5045], ["SP", 4.17, 41746]],
        False,
    )

    assert chart == ChartSpec("bar", 0, 1)


def test_rates_are_not_time_columns() -> None:
    chart = select_chart(
        ["state", "orders_per_day"], ["text", "numeric"], [["SP", 9.5], ["RJ", 4.5]], False
    )

    assert chart == ChartSpec("bar", 0, 1)


def test_numeric_identifiers_are_not_measures() -> None:
    chart = select_chart(
        ["name", "seller_id", "orders"],
        ["text", "int8", "int8"],
        [["a", 1, 9], ["b", 2, 4]],
        False,
    )

    assert chart == ChartSpec("bar", 0, 2)


@pytest.mark.parametrize(
    ("columns", "types", "rows", "truncated"),
    [
        (["total"], ["int8"], [[99441]], False),
        (["state", "orders"], ["text", "int8"], [["SP", 9]], False),
        (["state", "orders"], ["text", "int8"], [], False),
        (["state", "orders"], ["text", "int8"], [["SP", 9], ["RJ", 4]], True),
        (["order_id", "city"], ["text", "text"], [["a", "x"], ["b", "y"]], False),
        (["a", "b"], ["int8", "int8"], [[1, 2], [3, 4]], False),
        (
            ["state", "status", "orders"],
            ["text", "text", "int8"],
            [["SP", "a", 1], ["SP", "b", 2]],
            False,
        ),
        (
            ["year", "state", "orders"],
            ["int4", "text", "int8"],
            [[2017, "SP", 1], [2017, "RJ", 2]],
            False,
        ),
    ],
)
def test_no_chart_when_it_would_mislead(
    columns: list[str],
    types: list[str],
    rows: list[list[object]],
    truncated: bool,
) -> None:
    assert select_chart(columns, types, rows, truncated) is None


def test_too_many_categories_get_no_bar_chart() -> None:
    rows = [[f"seller {index}", index] for index in range(31)]

    assert select_chart(["seller", "orders"], ["text", "int8"], rows, False) is None


def test_the_bar_limit_is_inclusive() -> None:
    rows = [[f"seller {index}", index] for index in range(30)]

    assert select_chart(["seller", "orders"], ["text", "int8"], rows, False) == ChartSpec(
        "bar", 0, 1
    )


def test_long_time_series_still_makes_a_line() -> None:
    rows = [[f"2017-{month:02d}-01", month] for month in range(1, 13)]
    rows += [[f"2018-{month:02d}-01", month] for month in range(1, 13)]
    rows += [[f"2019-{month:02d}-01", month] for month in range(1, 13)]

    assert select_chart(["day", "orders"], ["text", "int8"], rows, False) == ChartSpec("line", 0, 1)
