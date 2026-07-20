"""Provider factory & registry.

This is the single dispatch point that lets operators switch the LLM / embedding
backend purely through configuration (``RAG_LLM_PROVIDER`` / ``EMBEDDINGS_PROVIDER``
and the provider-specific API keys/endpoints). Adding a new backend never
requires touching calling code — register it in ``LLM_PROVIDER_REGISTRY`` (or
``EMBEDDING_PROVIDER_REGISTRY``) and it is immediately selectable.

Provider selection is intentionally string-keyed off ``Settings`` so the rest of
the app stays provider-agnostic.
"""
from typing import Callable, Dict, List, Optional

from app.ai.providers.base import BaseLLMProvider, ProviderType
from app.core.config import Settings


# --------------------------------------------------------------------------- #
# LLM provider registry
# --------------------------------------------------------------------------- #
def _make_openrouter(s: Settings, model: Optional[str]) -> BaseLLMProvider:
    return _require(
        "openrouter",
        s.OPENROUTER_API_KEY,
        lambda: __import__(
            "app.ai.providers.openrouter", fromlist=["OpenRouterProvider"]
        ).OpenRouterProvider(api_key=s.OPENROUTER_API_KEY, base_url=s.OPENROUTER_BASE_URL),
    )


def _make_openai(s: Settings, model: Optional[str]) -> BaseLLMProvider:
    return _require(
        "openai",
        s.OPENAI_API_KEY,
        lambda: __import__(
            "app.ai.providers.openai_compatible", fromlist=["OpenAIProvider"]
        ).OpenAIProvider(
            api_key=s.OPENAI_API_KEY,
            base_url=s.OPENAI_BASE_URL,
        ),
    )


def _make_anthropic(s: Settings, model: Optional[str]) -> BaseLLMProvider:
    return _require(
        "anthropic",
        s.ANTHROPIC_API_KEY,
        lambda: __import__(
            "app.ai.providers.anthropic_provider", fromlist=["AnthropicProvider"]
        ).AnthropicProvider(api_key=s.ANTHROPIC_API_KEY, base_url=s.ANTHROPIC_BASE_URL),
    )


def _make_gemini(s: Settings, model: Optional[str]) -> BaseLLMProvider:
    return _require(
        "gemini",
        s.GEMINI_API_KEY,
        lambda: __import__(
            "app.ai.providers.gemini_provider", fromlist=["GeminiProvider"]
        ).GeminiProvider(api_key=s.GEMINI_API_KEY, base_url=s.GEMINI_BASE_URL),
    )


def _make_azure(s: Settings, model: Optional[str]) -> BaseLLMProvider:
    def _build():
        az = __import__(
            "app.ai.providers.azure_openai", fromlist=["AzureOpenAIProvider"]
        ).AzureOpenAIProvider
        if not s.AZURE_OPENAI_ENDPOINT or not s.AZURE_OPENAI_DEPLOYMENT:
            from app.ai.providers.base import ProviderError

            raise ProviderError(
                "Azure OpenAI requires AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT",
                "azure",
            )
        return az(
            api_key=s.AZURE_OPENAI_API_KEY,
            endpoint=s.AZURE_OPENAI_ENDPOINT,
            deployment=s.AZURE_OPENAI_DEPLOYMENT,
            api_version=s.AZURE_OPENAI_API_VERSION,
        )

    return _require("azure", s.AZURE_OPENAI_API_KEY, _build)


def _make_ollama(s: Settings, model: Optional[str]) -> BaseLLMProvider:
    return __import__(
        "app.ai.providers.ollama", fromlist=["OllamaProvider"]
    ).OllamaProvider(base_url=f"{s.OLLAMA_BASE_URL.rstrip('/')}/v1", default_model=s.OLLAMA_LLM_MODEL)


def _require(name: str, key: Optional[str], build: Callable[[], BaseLLMProvider]) -> BaseLLMProvider:
    from app.ai.providers.base import AuthenticationError

    if not key:
        raise AuthenticationError(f"No API key configured for provider '{name}'", name)
    return build()


LLM_PROVIDER_REGISTRY: Dict[str, Callable[[Settings, Optional[str]], BaseLLMProvider]] = {
    "openrouter": _make_openrouter,
    "openai": _make_openai,
    "anthropic": _make_anthropic,
    "gemini": _make_gemini,
    "azure": _make_azure,
    "ollama": _make_ollama,
}

# Human-readable metadata used by docs, the providers status API, and config.
LLM_PROVIDER_META: Dict[str, dict] = {
    "openrouter": {"label": "OpenRouter", "requires_key": True, "description": "Aggregator for many models."},
    "openai": {"label": "OpenAI", "requires_key": True, "description": "OpenAI GPT models."},
    "anthropic": {"label": "Anthropic Claude", "requires_key": True, "description": "Claude family of models."},
    "gemini": {"label": "Google Gemini", "requires_key": True, "description": "Google Gemini models."},
    "azure": {"label": "Azure OpenAI", "requires_key": True, "description": "Azure-hosted OpenAI deployments."},
    "ollama": {"label": "Ollama (local)", "requires_key": False, "description": "Self-hosted local models, no API key."},
    "local": {"label": "Local (offline)", "requires_key": False, "description": "Deterministic offline composer."},
}


def create_llm_provider(
    name: str,
    settings: Settings,
    model: Optional[str] = None,
) -> Optional[BaseLLMProvider]:
    """Return an LLM provider instance for ``name``.

    ``"local"`` (or any unknown/offline value) returns ``None`` — callers fall
    back to the deterministic offline composer in that case.
    """
    if not name or name == "local":
        return None
    builder = LLM_PROVIDER_REGISTRY.get(name.lower())
    if not builder:
        from app.ai.providers.base import ProviderError

        raise ProviderError(f"Unknown LLM provider: {name}", name)
    return builder(settings, model)


def active_llm_provider_name(settings: Settings) -> str:
    return (getattr(settings, "RAG_LLM_PROVIDER", "local") or "local").lower()


def get_llm_provider(settings: Settings, model: Optional[str] = None) -> Optional[BaseLLMProvider]:
    """Convenience: the provider selected by ``RAG_LLM_PROVIDER``."""
    return create_llm_provider(active_llm_provider_name(settings), settings, model)


def llm_provider_base_url(name: str, settings: Settings) -> Optional[str]:
    """Best-effort base URL for a provider (used by health probes / UI)."""
    name = (name or "local").lower()
    mapping = {
        "openrouter": settings.OPENROUTER_BASE_URL,
        "openai": settings.OPENAI_BASE_URL,
        "anthropic": settings.ANTHROPIC_BASE_URL,
        "gemini": settings.GEMINI_BASE_URL,
        "ollama": f"{settings.OLLAMA_BASE_URL.rstrip('/')}/v1",
    }
    if name == "azure" and settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_DEPLOYMENT:
        return f"{settings.AZURE_OPENAI_ENDPOINT.rstrip('/')}/openai/deployments/{settings.AZURE_OPENAI_DEPLOYMENT}"
    return mapping.get(name)


def list_llm_provider_specs(settings: Settings) -> List[dict]:
    """Describe every supported LLM provider + whether it is configured."""
    active = active_llm_provider_name(settings)
    specs = []
    for name, meta in LLM_PROVIDER_META.items():
        if name == "local":
            configured = True
        elif name == "ollama":
            configured = True  # local service; reachability is checked at runtime
        else:
            configured = bool(_provider_key(name, settings))
        specs.append(
            {
                "name": name,
                "label": meta["label"],
                "description": meta["description"],
                "requires_key": meta["requires_key"],
                "configured": configured,
                "active": name == active,
            }
        )
    return specs


def _provider_key(name: str, settings: Settings) -> Optional[str]:
    return {
        "openrouter": settings.OPENROUTER_API_KEY,
        "openai": settings.OPENAI_API_KEY,
        "anthropic": settings.ANTHROPIC_API_KEY,
        "gemini": settings.GEMINI_API_KEY,
        "azure": settings.AZURE_OPENAI_API_KEY,
    }.get(name)
