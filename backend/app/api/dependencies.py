from functools import partial
from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.llm.factory import create_llm_client
from app.pipeline.execute import execute_query, readonly_connection
from app.pipeline.orchestrator import QueryPipeline
from app.schema.introspect import Table, load_tables


def load_schema(settings: Settings) -> list[Table]:
    with readonly_connection(settings) as connection:
        return load_tables(connection)


def get_pipeline(settings: Annotated[Settings, Depends(get_settings)]) -> QueryPipeline:
    return QueryPipeline(
        llm=create_llm_client(settings),
        load_schema=partial(load_schema, settings),
        execute=partial(execute_query, settings=settings),
        max_retries=settings.correction_retries,
    )
