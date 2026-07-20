"""Ollama provider.

Ollama runs locally and exposes an OpenAI-compatible API at
``{base_url}/v1``. No API key is required. This is the offline / on-premises
LLM option — it lets the full RAG pipeline run entirely on the user's hardware.
"""
from typing import Dict

from app.ai.providers.base import ProviderType
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama chat provider via its OpenAI-compatible ``/v1`` endpoint."""

    DEFAULT_BASE_URL = "http://localhost:11434/v1"
    DEFAULT_MODEL = "llama3"
    MODEL_CONTEXT_WINDOWS: Dict[str, int] = {}
    MODEL_PRICING: Dict[str, tuple] = {}

    def __init__(
        self,
        api_key: str = "",
        base_url: str = DEFAULT_BASE_URL,
        default_model: str = DEFAULT_MODEL,
    ):
        super().__init__(api_key, base_url)
        self.default_model = default_model

    @property
    def provider_type(self):
        return ProviderType.OLLAMA

    def _auth_headers(self) -> Dict[str, str]:
        # Ollama requires no credentials on a trusted local network.
        return {}
