"""Provider selection."""

from __future__ import annotations

import logging

from careerx.ai.providers.base import LLMProvider, ProviderNotConfigured
from careerx.config.settings import Settings, get_settings

logger = logging.getLogger(__name__)


def build_provider(settings: Settings | None = None) -> LLMProvider:
    """Instantiate the provider named by ``settings.llm_provider``.

    Raises:
        ProviderNotConfigured: if the selected provider has no API key.
    """
    settings = settings or get_settings()

    if settings.llm_provider == "gemini":
        from careerx.ai.providers.gemini import GeminiProvider

        provider: LLMProvider = GeminiProvider(settings)
    elif settings.llm_provider == "openai":
        from careerx.ai.providers.openai_provider import OpenAIProvider

        provider = OpenAIProvider(settings)
    else:  # pragma: no cover - Literal type makes this unreachable
        raise ProviderNotConfigured(f"Unknown LLM provider: {settings.llm_provider!r}")

    logger.info("LLM provider ready: %s (%s)", provider.name, provider.chat_model)
    return provider
