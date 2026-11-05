from app.config import Settings
from app.llm.anthropic_adapter import AnthropicClient
from app.llm.base import LLMClient, LLMConfigurationError


def create_llm_client(settings: Settings) -> LLMClient:
    api_key = settings.llm_api_key.get_secret_value()
    if not api_key:
        raise LLMConfigurationError("LLM_API_KEY isn't set.")
    if settings.llm_provider != "anthropic":
        raise LLMConfigurationError(f"Unsupported LLM provider: {settings.llm_provider}.")
    return AnthropicClient(
        api_key=api_key,
        model=settings.llm_model,
        effort=settings.llm_effort,
        timeout_seconds=settings.llm_timeout_seconds,
    )
