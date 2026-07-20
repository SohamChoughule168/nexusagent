"""Provider status/configuration endpoint.

Lists every LLM and embedding backend the platform supports and, for the active
configuration, which are configured (credentials present). This is what a
provider-setup UI consumes to show "connected / not connected" without exposing
any secret values.
"""
from fastapi import APIRouter, Depends

from app.ai.providers.factory import (
    LLM_PROVIDER_META,
    active_llm_provider_name,
    list_llm_provider_specs,
)
from app.core.config import settings
from app.core.auth_dependencies import get_tenant_context
from app.services.tenant_context import TenantContext
from app.schemas.provider import ProviderInfo, ProvidersResponse

router = APIRouter(prefix="/providers", tags=["providers"])


_EMBEDDING_PROVIDERS = {
    "local": {"label": "Local (offline)", "requires_key": False, "description": "Deterministic offline embedder."},
    "openai": {"label": "OpenAI", "requires_key": True, "description": "OpenAI text-embedding models."},
    "openrouter": {"label": "OpenRouter", "requires_key": True, "description": "OpenAI-compatible via OpenRouter."},
    "azure": {"label": "Azure OpenAI", "requires_key": True, "description": "Azure-hosted OpenAI embeddings."},
    "gemini": {"label": "Google Gemini", "requires_key": True, "description": "Google Gemini embeddings."},
    "ollama": {"label": "Ollama (local)", "requires_key": False, "description": "Self-hosted local embeddings."},
}


def _embedding_configured(name: str) -> bool:
    if name in ("local", "ollama"):
        return True
    key_attr = {
        "openai": "OPENAI_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "azure": "AZURE_OPENAI_API_KEY",
    }.get(name)
    if key_attr and not getattr(settings, key_attr):
        return False
    if name == "azure" and not (settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_DEPLOYMENT):
        return False
    return True


@router.get("", response_model=ProvidersResponse)
def list_providers(_tenant: TenantContext = Depends(get_tenant_context)):
    active_llm = active_llm_provider_name(settings)
    active_emb = (getattr(settings, "EMBEDDINGS_PROVIDER", "local") or "local").lower()

    llm = list_llm_provider_specs(settings)

    emb = [
        ProviderInfo(
            name=name,
            label=meta["label"],
            description=meta["description"],
            requires_key=meta["requires_key"],
            configured=_embedding_configured(name),
            active=name == active_emb,
        )
        for name, meta in _EMBEDDING_PROVIDERS.items()
    ]

    return ProvidersResponse(
        active_llm=active_llm,
        active_embeddings=active_emb,
        llm_providers=llm,
        embedding_providers=emb,
    )
