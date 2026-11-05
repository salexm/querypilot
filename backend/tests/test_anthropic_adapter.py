"""Exercises the adapter with a fake SDK client, so no test calls a real LLM."""

from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest

from app.llm.anthropic_adapter import FALLBACK_BETA, AnthropicClient
from app.llm.base import GeneratedSql, LLMConfigurationError, LLMError, LLMOutput

REQUEST = httpx.Request("POST", "https://api.test/v1/messages")


def status_error(error_type: type[anthropic.APIStatusError], status: int, body: object = None):
    response = httpx.Response(status, request=REQUEST)
    return error_type("provider error", response=response, body=body)


class FakeEndpoint:
    def __init__(self, outcome: Any) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def success() -> SimpleNamespace:
    return SimpleNamespace(
        stop_reason="end_turn",
        parsed_output=GeneratedSql(sql="SELECT 1"),
        usage=SimpleNamespace(input_tokens=10, output_tokens=2),
    )


def adapter(model: str, outcome: Any) -> tuple[AnthropicClient, FakeEndpoint, FakeEndpoint]:
    client = AnthropicClient("test-key", model, "medium", 5.0)
    stable, beta = FakeEndpoint(outcome), FakeEndpoint(outcome)
    client._client = SimpleNamespace(  # type: ignore[assignment]
        messages=stable, beta=SimpleNamespace(messages=beta)
    )
    return client, stable, beta


def test_request_carries_the_prompt_schema_and_effort() -> None:
    client, stable, _ = adapter("claude-haiku-5-5", success())

    output = client.generate_sql("system prompt", "How many?")

    assert output == LLMOutput(sql="SELECT 1", input_tokens=10, output_tokens=2)
    request = stable.calls[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["system"] == "system prompt"
    assert request["messages"] == [{"role": "user", "content": "How many?"}]
    assert request["output_format"] is GeneratedSql
    assert request["output_config"] == {"effort": "medium"}


def test_models_with_fallback_use_the_beta_endpoint() -> None:
    client, stable, beta = adapter("claude-opus-5-5", success())

    client.generate_sql("system prompt", "How many?")

    assert stable.calls == []
    assert beta.calls[0]["betas"] == [FALLBACK_BETA]
    assert beta.calls[0]["fallbacks"] == "default"


def test_models_without_fallback_never_send_the_parameter() -> None:
    client, stable, beta = adapter("claude-haiku-5-5", success())

    client.generate_sql("system prompt", "How many?")

    assert beta.calls == []
    assert "fallbacks" not in stable.calls[0]


@pytest.mark.parametrize(
    ("error", "expected_type", "message"),
    [
        (
            status_error(anthropic.AuthenticationError, 401),
            LLMConfigurationError,
            "rejected the API key",
        ),
        (status_error(anthropic.NotFoundError, 404), LLMConfigurationError, "Unknown LLM model"),
        (status_error(anthropic.RateLimitError, 429), LLMError, "rate limiting"),
        (status_error(anthropic.InternalServerError, 500), LLMError, "status 500"),
        (
            status_error(
                anthropic.BadRequestError,
                400,
                {"error": {"message": "Your credit balance is too low."}},
            ),
            LLMError,
            "credit balance is too low",
        ),
        (anthropic.APIConnectionError(request=REQUEST), LLMError, "Couldn't reach"),
        (anthropic.APITimeoutError(request=REQUEST), LLMError, "Couldn't reach"),
    ],
)
def test_provider_errors_become_llm_errors(
    error: Exception, expected_type: type[LLMError], message: str
) -> None:
    client, _, _ = adapter("claude-haiku-5-5", error)

    with pytest.raises(expected_type, match=message):
        client.generate_sql("system prompt", "How many?")


def test_api_key_never_appears_in_error_messages() -> None:
    client, _, _ = adapter("claude-haiku-5-5", status_error(anthropic.AuthenticationError, 401))

    with pytest.raises(LLMConfigurationError) as caught:
        client.generate_sql("system prompt", "How many?")

    assert "test-key" not in str(caught.value)
