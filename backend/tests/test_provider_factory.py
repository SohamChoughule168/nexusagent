"""Provider factory + provider request/response shaping tests (Milestone B, Step 1).

Uses ``httpx.MockTransport`` so no network, API keys, or database are required.
"""
import json
from typing import Any

import httpx
import pytest

from app.ai.providers.base import ProviderType, ProviderError, AuthenticationError
from app.ai.providers.factory import (
    create_llm_provider,
    active_llm_provider_name,
    list_llm_provider_specs,
)
from app.ai.providers.openrouter import OpenRouterProvider
from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.providers.anthropic_provider import AnthropicProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.azure_openai import AzureOpenAIProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.base import GenerationRequest, Message, MessageRole
from app.core.config import settings
from app.services.embeddings import (
    get_embedding_provider,
    OpenAICompatibleEmbedder,
    GeminiEmbedder,
    LocalDeterministicEmbedder,
)


def _mock_provider(provider, payload: dict, status: int = 200):
    """Swap the provider's async client for a mocked transport."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    provider.client = httpx.AsyncClient(
        base_url="http://test", transport=httpx.MockTransport(handler)
    )
    return provider


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #
def test_local_provider_is_none():
    assert create_llm_provider("local", settings) is None


def test_unknown_provider_raises():
    with pytest.raises(ProviderError):
        create_llm_provider("does-not-exist", settings)


def test_factory_requires_key(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    with pytest.raises(AuthenticationError):
        create_llm_provider("openrouter", settings)


def test_factory_builds_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "sk-test")
    p = create_llm_provider("openrouter", settings)
    assert isinstance(p, OpenRouterProvider)


def test_factory_builds_ollama_without_key():
    p = create_llm_provider("ollama", settings)
    assert isinstance(p, OllamaProvider)
    assert p.provider_type == ProviderType.OLLAMA


def test_active_provider_name():
    monkeypatch_active = "openai"

    class _S:
        RAG_LLM_PROVIDER = monkeypatch_active

    assert active_llm_provider_name(_S()) == "openai"


def test_list_provider_specs():
    specs = list_llm_provider_specs(settings)
    names = {s["name"] for s in specs}
    assert {"openrouter", "openai", "anthropic", "gemini", "azure", "ollama", "local"} <= names
    # local is always configured
    assert next(s for s in specs if s["name"] == "local")["configured"] is True


# --------------------------------------------------------------------------- #
# OpenAI-compatible (openai)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_openai_compatible_generate(monkeypatch):
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(settings, "OPENAI_BASE_URL", "https://api.openai.com/v1")
    p = create_llm_provider("openai", settings)
    _mock_provider(
        p,
        {
            "choices": [
                {
                    "message": {
                        "content": "Hi",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {"name": "f", "arguments": "{}"},
                            }
                        ],
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            "model": "gpt-4o-mini",
        },
    )
    resp = await p.generate(
        GenerationRequest(messages=[Message(role=MessageRole.USER, content="hi")], model="gpt-4o-mini")
    )
    assert resp.content == "Hi"
    assert resp.tool_calls[0]["function"]["name"] == "f"
    assert resp.token_usage.total_tokens == 8
    assert resp.cost_usd > 0  # gpt-4o-mini is a known, priced model
    await p.close()


# --------------------------------------------------------------------------- #
# Anthropic
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_anthropic_generate():
    p = _mock_provider(
        AnthropicProvider(api_key="sk-test"),
        {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Hello"},
                {"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"city": "SF"}},
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        },
    )
    resp = await p.generate(
        GenerationRequest(messages=[Message(role=MessageRole.USER, content="hi")], model="claude-3-5-sonnet")
    )
    assert resp.content == "Hello"
    assert resp.tool_calls[0]["function"]["name"] == "get_weather"
    assert json.loads(resp.tool_calls[0]["function"]["arguments"]) == {"city": "SF"}
    assert resp.token_usage.prompt_tokens == 10
    await p.close()


# --------------------------------------------------------------------------- #
# Gemini
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_gemini_generate():
    p = _mock_provider(
        GeminiProvider(api_key="key"),
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": "Hi"},
                            {"functionCall": {"name": "f", "args": {"x": 1}}},
                        ]
                    },
                    "finishReason": "STOP",
                }
            ],
            "usageMetadata": {"promptTokenCount": 3, "candidatesTokenCount": 2, "totalTokenCount": 5},
        },
    )
    resp = await p.generate(
        GenerationRequest(messages=[Message(role=MessageRole.USER, content="hi")], model="gemini-1.5-flash")
    )
    assert resp.content == "Hi"
    assert resp.tool_calls[0]["function"]["name"] == "f"
    assert resp.token_usage.total_tokens == 5
    await p.close()


# --------------------------------------------------------------------------- #
# Azure OpenAI
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_azure_generate_url_and_auth(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["api_key"] = request.headers.get("api-key")
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Azure hi"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    p = AzureOpenAIProvider(
        api_key="azure-key",
        endpoint="https://res.openai.azure.com",
        deployment="gpt-4o",
        api_version="2024-02-15-preview",
    )
    p.client = httpx.AsyncClient(
        base_url="http://test", headers=p.client.headers, transport=httpx.MockTransport(handler)
    )
    resp = await p.generate(
        GenerationRequest(messages=[Message(role=MessageRole.USER, content="hi")], model="gpt-4o")
    )
    assert resp.content == "Azure hi"
    assert "api-version=2024-02-15-preview" in captured["url"]
    assert captured["api_key"] == "azure-key"
    await p.close()


# --------------------------------------------------------------------------- #
# Embeddings
# --------------------------------------------------------------------------- #
def test_openai_embedder(monkeypatch):
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]}, request=httpx.Request("POST", "http://x")),
    )
    emb = OpenAICompatibleEmbedder(api_key="sk", model="text-embedding-3-small", base_url="https://api.openai.com/v1")
    vecs = emb.embed(["hello"])
    assert vecs == [[0.1, 0.2, 0.3]]


def test_gemini_embedder(monkeypatch):
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: httpx.Response(200, json={"embeddings": [{"values": [0.5, 0.6]}]}, request=httpx.Request("POST", "http://x")),
    )
    emb = GeminiEmbedder(api_key="key", model="text-embedding-004")
    vecs = emb.embed(["hello"])
    assert vecs == [[0.5, 0.6]]


def test_get_embedding_provider_local_default(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDINGS_PROVIDER", "local")
    assert isinstance(get_embedding_provider(None, settings), LocalDeterministicEmbedder)


def test_get_embedding_provider_ollama(monkeypatch):
    monkeypatch.setattr(settings, "EMBEDDINGS_PROVIDER", "ollama")
    monkeypatch.setattr(settings, "OLLAMA_BASE_URL", "http://localhost:11434")
    emb = get_embedding_provider(None, settings)
    assert isinstance(emb, OpenAICompatibleEmbedder)
    assert emb.base_url.endswith("/v1")
