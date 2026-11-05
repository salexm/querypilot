from typing import Any

import anthropic

from app.llm.base import GeneratedSql, LLMConfigurationError, LLMError

MAX_TOKENS = 16_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Haiku has no server-side fallback, and sending the parameter would fail.
MODELS_WITH_FALLBACK = ("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5-5")


def supports_fallback(model: str) -> bool:
    return model.startswith(MODELS_WITH_FALLBACK)


class AnthropicClient:
    def __init__(self, api_key: str, model: str, effort: str, timeout_seconds: float) -> None:
        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._effort = effort

    def generate_sql(self, system_prompt: str, question: str) -> GeneratedSql:
        try:
            response = self._send(system_prompt, question)
        except anthropic.AuthenticationError as error:
            raise LLMConfigurationError("The LLM provider rejected the API key.") from error
        except anthropic.NotFoundError as error:
            raise LLMConfigurationError(f"Unknown LLM model: {self._model}.") from error
        except anthropic.RateLimitError as error:
            raise LLMError("The LLM provider is rate limiting requests.") from error
        except anthropic.APIStatusError as error:
            raise LLMError(f"The LLM provider returned status {error.status_code}.") from error
        except anthropic.APIConnectionError as error:
            raise LLMError("Couldn't reach the LLM provider.") from error
        return parsed_result(response)

    def _send(self, system_prompt: str, question: str) -> Any:
        request: dict[str, Any] = {
            "model": self._model,
            "max_tokens": MAX_TOKENS,
            "system": system_prompt,
            "messages": [{"role": "user", "content": question}],
            "output_format": GeneratedSql,
            "output_config": {"effort": self._effort},
        }
        if supports_fallback(self._model):
            return self._client.beta.messages.parse(
                betas=[FALLBACK_BETA], fallbacks="default", **request
            )
        return self._client.messages.parse(**request)


def parsed_result(response: Any) -> GeneratedSql:
    """Check why generation stopped before trusting the output."""
    if response.stop_reason == "refusal":
        raise LLMError("The LLM declined this question.")
    if response.stop_reason == "max_tokens":
        raise LLMError("The LLM ran out of output space.")
    if response.parsed_output is None:
        raise LLMError("The LLM returned output in an unexpected format.")
    return response.parsed_output
