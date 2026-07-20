"""LLM provider abstraction package.

Public surface: the :class:`BaseLLMProvider` contract, the concrete providers,
and the config-driven :mod:`factory` used to select one at runtime.
"""
from app.ai.providers.base import (
    BaseLLMProvider,
    ProviderType,
    Message,
    MessageRole,
    TokenUsage,
    GenerationRequest,
    GenerationResponse,
    StreamChunk,
    ProviderError,
    RateLimitError,
    ContextLengthError,
    AuthenticationError,
    ModelNotFoundError,
)
from app.ai.providers.openai_compatible import OpenAICompatibleProvider, OpenAIProvider
from app.ai.providers.openrouter import OpenRouterProvider, OpenRouterProviderWithFallback
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.azure_openai import AzureOpenAIProvider
from app.ai.providers.ollama import OllamaProvider

__all__ = [
    "BaseLLMProvider",
    "ProviderType",
    "Message",
    "MessageRole",
    "TokenUsage",
    "GenerationRequest",
    "GenerationResponse",
    "StreamChunk",
    "ProviderError",
    "RateLimitError",
    "ContextLengthError",
    "AuthenticationError",
    "ModelNotFoundError",
    "OpenAICompatibleProvider",
    "OpenAIProvider",
    "OpenRouterProvider",
    "OpenRouterProviderWithFallback",
    "AnthropicProvider",
    "GeminiProvider",
    "AzureOpenAIProvider",
    "OllamaProvider",
]
