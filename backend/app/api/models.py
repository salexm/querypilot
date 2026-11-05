from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)


class QueryResponse(BaseModel):
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool


class ErrorResponse(BaseModel):
    code: str
    message: str
    sql: str | None = None


class HealthResponse(BaseModel):
    status: str
