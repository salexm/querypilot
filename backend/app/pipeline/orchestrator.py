from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.llm.base import LLMClient
from app.pipeline.chart import ChartSpec, select_chart
from app.pipeline.errors import DatabaseUnavailableError, UnanswerableQuestionError
from app.pipeline.execute import QueryResult
from app.pipeline.validate import validate_sql
from app.schema.introspect import Table, format_schema

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "generate_sql_v1.md"


@dataclass(frozen=True)
class PipelineResult:
    question: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    chart: ChartSpec | None


def build_system_prompt(tables: list[Table]) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return template.replace("{schema}", format_schema(tables))


class QueryPipeline:
    """Headless path from question to rows, shared by the API and the benchmark."""

    def __init__(
        self,
        llm: LLMClient,
        load_schema: Callable[[], list[Table]],
        execute: Callable[[str], QueryResult],
    ) -> None:
        self._llm = llm
        self._load_schema = load_schema
        self._execute = execute

    def run(self, question: str) -> PipelineResult:
        tables = self._load_schema()
        if not tables:
            raise DatabaseUnavailableError("The analytics database has no tables. Run the seed.")
        generated = self._llm.generate_sql(build_system_prompt(tables), question)
        if not generated.sql.strip():
            raise UnanswerableQuestionError("This question can't be answered from the data.")
        allowed_tables = frozenset(table.name for table in tables)
        sql = validate_sql(generated.sql, allowed_tables)
        result = self._execute(sql)
        chart = select_chart(result.columns, result.column_types, result.rows, result.truncated)
        return PipelineResult(question, sql, result.columns, result.rows, result.truncated, chart)
