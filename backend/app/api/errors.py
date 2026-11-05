from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.models import ErrorResponse
from app.llm.base import LLMConfigurationError, LLMError
from app.pipeline.errors import (
    DatabaseUnavailableError,
    PipelineError,
    QueryTimeoutError,
    SqlExecutionError,
    SqlValidationError,
    UnanswerableQuestionError,
)

PIPELINE_ERRORS: dict[type[PipelineError], tuple[int, str]] = {
    UnanswerableQuestionError: (422, "unanswerable_question"),
    SqlValidationError: (422, "invalid_sql"),
    SqlExecutionError: (422, "query_failed"),
    QueryTimeoutError: (504, "query_timeout"),
    DatabaseUnavailableError: (503, "database_unavailable"),
}


def error_response(status: int, code: str, message: str, sql: str | None = None) -> JSONResponse:
    body = ErrorResponse(code=code, message=message, sql=sql)
    return JSONResponse(status_code=status, content=body.model_dump())


def handle_pipeline_error(_: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, PipelineError)
    status, code = PIPELINE_ERRORS[type(error)]
    return error_response(status, code, error.message, error.sql)


def handle_llm_error(_: Request, error: Exception) -> JSONResponse:
    if isinstance(error, LLMConfigurationError):
        return error_response(503, "llm_not_configured", str(error))
    return error_response(502, "llm_failed", str(error))


def register_error_handlers(app: FastAPI) -> None:
    for error_type in PIPELINE_ERRORS:
        app.add_exception_handler(error_type, handle_pipeline_error)
    app.add_exception_handler(LLMError, handle_llm_error)
