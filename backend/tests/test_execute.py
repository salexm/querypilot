from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.pipeline.execute import to_json_value


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("12.50"), 12.5),
        (datetime(2018, 1, 2, 3, 4, 5), "2018-01-02T03:04:05"),
        (date(2018, 1, 2), "2018-01-02"),
        (timedelta(days=1), 86400.0),
        (None, None),
        (True, True),
        (7, 7),
        ("text", "text"),
        (UUID(int=0), "00000000-0000-0000-0000-000000000000"),
    ],
)
def test_to_json_value(value: object, expected: object) -> None:
    assert to_json_value(value) == expected
