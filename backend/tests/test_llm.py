from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm.anthropic_adapter import parsed_result, provider_message, supports_fallback
from app.llm.base import GeneratedSql, LLMConfigurationError, LLMError, LLMOutput
from app.llm.factory import create_llm_client


def response(stop_reason: str, parsed: GeneratedSql | None) -> SimpleNamespace:
    usage = SimpleNamespace(input_tokens=100, output_tokens=20)
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=parsed, usage=usage)


def test_parsed_result_returns_sql_and_usage() -> None:
    output = parsed_result(response("end_turn", GeneratedSql(sql="SELECT 1")))

    assert output == LLMOutput(sql="SELECT 1", input_tokens=100, output_tokens=20)


@pytest.mark.parametrize(
    "item",
    [response("refusal", None), response("max_tokens", None), response("end_turn", None)],
)
def test_parsed_result_rejects_unusable_responses(item: SimpleNamespace) -> None:
    with pytest.raises(LLMError):
        parsed_result(item)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"error": {"message": "Your credit balance is too low."}}, "credit balance is too low"),
        ({"error": {}}, "no reason given"),
        ("not a dict", "no reason given"),
        (None, "no reason given"),
    ],
)
def test_provider_message_explains_rejected_requests(body: object, expected: str) -> None:
    assert expected in provider_message(body)


@pytest.mark.parametrize(
    ("model", "expected"),
    [("claude-opus-5-5", True), ("claude-sonnet-5-5", True), ("claude-haiku-5-5", False)],
)
def test_supports_fallback(model: str, expected: bool) -> None:
    assert supports_fallback(model) is expected


def test_factory_requires_an_api_key() -> None:
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        create_llm_client(Settings(llm_api_key=""))


def test_factory_rejects_unknown_provider() -> None:
    with pytest.raises(LLMConfigurationError, match="Unsupported"):
        create_llm_client(Settings(llm_api_key="test-key", llm_provider="other"))
