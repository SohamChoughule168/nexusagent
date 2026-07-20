"""Azure OpenAI provider.

Azure exposes the OpenAI chat API behind a deployment-scoped URL that carries
the API version as a query parameter, and authenticates with an ``api-key``
header rather than ``Authorization: Bearer``. Otherwise the wire format is
identical to OpenAI, so we reuse :class:`OpenAICompatibleProvider`.
"""
from typing import Dict, Optional

from app.ai.providers.base import ProviderType
from app.ai.providers.openai_compatible import OpenAICompatibleProvider


class AzureOpenAIProvider(OpenAICompatibleProvider):
    """Azure OpenAI chat provider (OpenAI-compatible wire format)."""

    MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4": 8192,
        "gpt-35-turbo": 16385,
    }
    MODEL_PRICING: Dict[str, tuple] = {}

    def __init__(
        self,
        api_key: str,
        *,
        endpoint: str,
        deployment: str,
        api_version: str = "2024-02-15-preview",
        base_url: Optional[str] = None,
    ):
        # ``base_url`` is computed per-request from endpoint + deployment.
        base_url = base_url or f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        self.api_version = api_version
        self.deployment = deployment
        super().__init__(api_key, base_url)

    @property
    def provider_type(self):
        return ProviderType.AZURE

    def _auth_headers(self) -> Dict[str, str]:
        return {"api-key": self.api_key}

    def _chat_completions_path(self) -> str:
        return f"/chat/completions?api-version={self.api_version}"
