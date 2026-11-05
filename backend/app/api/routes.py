from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_pipeline
from app.api.models import (
    ChartResponse,
    ErrorResponse,
    HealthResponse,
    QueryRequest,
    QueryResponse,
)
from app.api.rate_limit import enforce_query_limits
from app.config import Settings, get_settings
from app.pipeline.execute import readonly_connection
from app.pipeline.orchestrator import QueryPipeline

router = APIRouter()


@router.get("/health")
def health() -> HealthResponse:
    """Say the process is up. The platform calls this often, so it skips the database."""
    return HealthResponse(status="ok")


@router.get("/health/ready", responses={503: {"model": ErrorResponse}})
def ready(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Check the database too, for humans and deploy checks."""
    with readonly_connection(settings) as connection:
        connection.execute("SELECT 1")
    return HealthResponse(status="ok")


@router.post(
    "/query",
    dependencies=[Depends(enforce_query_limits)],
    responses={status: {"model": ErrorResponse} for status in (422, 429, 502, 503, 504)},
)
def query(
    request: QueryRequest,
    pipeline: Annotated[QueryPipeline, Depends(get_pipeline)],
) -> QueryResponse:
    result = pipeline.run(request.question)
    chart = result.chart
    return QueryResponse(
        chart=ChartResponse(**asdict(chart)) if chart else None,
        attempts=len(result.attempts),
        question=result.question,
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=len(result.rows),
        truncated=result.truncated,
    )
