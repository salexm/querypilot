from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.dependencies import get_pipeline
from app.api.models import ErrorResponse, HealthResponse, QueryRequest, QueryResponse
from app.config import Settings, get_settings
from app.pipeline.execute import readonly_connection
from app.pipeline.orchestrator import QueryPipeline

router = APIRouter()


@router.get("/health", responses={503: {"model": ErrorResponse}})
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    with readonly_connection(settings) as connection:
        connection.execute("SELECT 1")
    return HealthResponse(status="ok")


@router.post(
    "/query",
    responses={status: {"model": ErrorResponse} for status in (422, 502, 503, 504)},
)
def query(
    request: QueryRequest,
    pipeline: Annotated[QueryPipeline, Depends(get_pipeline)],
) -> QueryResponse:
    result = pipeline.run(request.question)
    return QueryResponse(
        question=result.question,
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=len(result.rows),
        truncated=result.truncated,
    )
