from functools import lru_cache, partial
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.llm.base import LLMClient
from app.llm.factory import create_llm_client
from app.pipeline.execute import execute_query, readonly_connection
from app.pipeline.orchestrator import QueryPipeline
from app.schema.introspect import Table, load_tables


def load_schema(settings: Settings) -> list[Table]:
    with readonly_connection(settings) as connection:
        return load_tables(connection)


@lru_cache
def get_llm_client() -> LLMClient:
    return create_llm_client(get_settings())


def get_pipeline(
    settings: Annotated[Settings, Depends(get_settings)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> QueryPipeline:
    return QueryPipeline(
        llm=llm,
        load_schema=partial(load_schema, settings),
        execute=partial(execute_query, settings=settings),
        max_retries=settings.correction_retries,
    )
