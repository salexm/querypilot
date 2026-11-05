from typing import Protocol

from pydantic import BaseModel, Field


class GeneratedSql(BaseModel):
    """Structured LLM output. An empty string means the question can't be answered."""

    sql: str = Field(description="One PostgreSQL SELECT statement, or an empty string.")


class LLMError(Exception):
    """The provider couldn't produce SQL."""


class LLMConfigurationError(LLMError):
    """The provider, model, or API key isn't set up."""


class LLMClient(Protocol):
    def generate_sql(self, system_prompt: str, question: str) -> GeneratedSql: ...
