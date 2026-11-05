from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)


class ChartResponse(BaseModel):
    type: Literal["bar", "line"]
    x_column: int
    y_column: int


class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    chart: ChartResponse | None
    attempts: int


class ErrorResponse(BaseModel):
    code: str
    message: str
    sql: str | None = None


class HealthResponse(BaseModel):
    status: str
