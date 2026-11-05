from app.llm.base import GeneratedSql
from app.pipeline.execute import QueryResult
from app.schema.introspect import Column, Table


class FakeLLM:
    """Returns fixed SQL and records what it was asked."""

    def __init__(self, sql: str) -> None:
        self.sql = sql
        self.system_prompts: list[str] = []
        self.questions: list[str] = []

    def generate_sql(self, system_prompt: str, question: str) -> GeneratedSql:
        self.system_prompts.append(system_prompt)
        self.questions.append(question)
        return GeneratedSql(sql=self.sql)


def sample_tables() -> list[Table]:
    column = Column("order_id", "text", True, True, "Unique order.")
    foreign_key = "FOREIGN KEY (customer_id) REFERENCES customers(customer_id)"
    return [Table("orders", "All orders.", [column], [foreign_key])]


def sample_result() -> QueryResult:
    return QueryResult(columns=["total"], rows=[[42]], truncated=False)
