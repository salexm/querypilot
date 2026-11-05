class PipelineError(Exception):
    """A query failed in a way the API can report to the user."""

    def __init__(self, message: str, sql: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.sql = sql


class UnanswerableQuestionError(PipelineError):
    """The LLM found no way to answer the question from the schema."""


class SqlValidationError(PipelineError):
    """Generated SQL broke a safety rule."""


class SqlExecutionError(PipelineError):
    """Postgres rejected otherwise valid SQL."""


class QueryTimeoutError(PipelineError):
    """The query ran past the statement timeout."""


class DatabaseUnavailableError(PipelineError):
    """The analytics database can't be reached or has no tables."""
