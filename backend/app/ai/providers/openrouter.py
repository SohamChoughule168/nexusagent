from typing import List, Optional

from app.ai.providers.base import (
    GenerationRequest,
    GenerationResponse,
    StreamChunk,
    ProviderError,
)
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter LLM provider (OpenAI-compatible API)."""

    # Model context windows (in tokens)
    MODEL_CONTEXT_WINDOWS = {
        "anthropic/claude-3.5-sonnet": 200000,
        "anthropic/claude-3.5-haiku": 200000,
        "anthropic/claude-3-opus": 200000,
        "openai/gpt-4o": 128000,
        "openai/gpt-4o-mini": 128000,
        "openai/gpt-4-turbo": 128000,
        "openai/gpt-3.5-turbo": 16385,
        "google/gemini-pro-1.5": 2000000,
        "google/gemini-flash-1.5": 1000000,
        "meta-llama/llama-3.1-405b": 128000,
        "meta-llama/llama-3.1-70b": 128000,
        "meta-llama/llama-3.1-8b": 128000,
    }

    # Pricing per 1M tokens (input, output) in USD
    MODEL_PRICING = {
        "anthropic/claude-3.5-sonnet": (3.00, 15.00),
        "anthropic/claude-3.5-haiku": (0.25, 1.25),
        "anthropic/claude-3-opus": (15.00, 75.00),
        "openai/gpt-4o": (2.50, 10.00),
        "openai/gpt-4o-mini": (0.15, 0.60),
        "openai/gpt-4-turbo": (10.00, 30.00),
        "openai/gpt-3.5-turbo": (0.50, 1.50),
        "google/gemini-pro-1.5": (1.25, 5.00),
        "google/gemini-flash-1.5": (0.075, 0.30),
        "meta-llama/llama-3.1-405b": (3.00, 3.00),
        "meta-llama/llama-3.1-70b": (0.90, 0.90),
        "meta-llama/llama-3.1-8b": (0.06, 0.06),
    }

    DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        default_headers: Optional[dict] = None,
    ):
        super().__init__(
            api_key,
            base_url,
            default_headers={
                "HTTP-Referer": "https://nexusagent.ai",
                "X-Title": "NexusAgent AI",
            },
        )

    @property
    def provider_type(self):
        from app.ai.providers.base import ProviderType

        return ProviderType.OPENROUTER


class OpenRouterProviderWithFallback:
    """OpenRouter provider with automatic fallback to alternative models."""

    def __init__(self, primary_provider: OpenRouterProvider):
        self.primary = primary_provider

    async def generate_with_fallback(
        self,
        request: GenerationRequest,
        fallback_models: List[str] = None,
    ) -> GenerationResponse:
        models_to_try = [request.model]
        if fallback_models:
            models_to_try.extend(fallback_models)
        last_error = None
        for model in models_to_try:
            try:
                request.model = model
                return await self.primary.generate(request)
            except ProviderError as e:
                last_error = e
                if not e.retryable:
                    break
                continue
        raise last_error

    async def stream_with_fallback(
        self,
        request: GenerationRequest,
        fallback_models: List[str] = None,
    ):
        models_to_try = [request.model]
        if fallback_models:
            models_to_try.extend(fallback_models)
        last_error = None
        for model in models_to_try:
            try:
                request.model = model
                async for chunk in self.primary.stream(request):
                    yield chunk
                return
            except ProviderError as e:
                last_error = e
                if not e.retryable:
                    raise
                continue
        raise last_error
