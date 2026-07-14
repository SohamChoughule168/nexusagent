"""Retrieval-augmented generation (RAG) query service (Milestone 3).

Ties the vector-storage/retrieval pipeline to answer generation: given a
question and a knowledge base, it retrieves the most relevant embedded chunks
(via ``app.services.embeddings``) and composes a grounded answer.

Answer generation is pluggable, mirroring the embedding provider design:
* ``local`` (default, offline) -- a deterministic composer that returns the
  most relevant retrieved context with source attribution. Fully testable with
  no API key.
* ``openrouter`` / ``openai`` -- calls the existing ``OpenRouterProvider`` to
  generate a grounded answer from the retrieved context when a key is set.

Reuses, never duplicates: ``RepositoryFactory`` -> ``document_chunks()``,
the embedding provider + cosine similarity, and the existing LLM provider.
"""
import uuid
from typing import List, Optional, Tuple

from app.ai.providers.base import GenerationRequest, Message, MessageRole
from app.ai.providers.openrouter import OpenRouterProvider
from app.core.config import settings
from app.models.all_models import DocumentChunk, KnowledgeBase
from app.repositories.tenant_repository import RepositoryFactory
from app.services.embeddings import cosine_similarity, get_embedding_provider

# Cap on context characters passed to the LLM to stay within context windows.
_MAX_CONTEXT_CHARS = 6000


def retrieve_chunks(
    kb: KnowledgeBase,
    query: str,
    db,
    org_id: uuid.UUID,
    top_k: int = 5,
) -> List[Tuple[DocumentChunk, float]]:
    """Return the top-k embedded chunks for ``query`` ranked by cosine similarity.

    Tenant isolation is enforced by the tenant-scoped ``RepositoryFactory``:
    only this organization's chunks for the (already-tenant-checked) KB are
    ranked.
    """
    repo_factory = RepositoryFactory(db, org_id)
    chunks = repo_factory.document_chunks().get_by_knowledge_base(
        uuid.UUID(str(kb.id))
    )
    embedded = [c for c in chunks if c.embedding]

    provider = get_embedding_provider(kb, settings)
    (query_vec,) = provider.embed([query])

    scored = [
        (cosine_similarity(query_vec, c.embedding), c) for c in embedded
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(c, s) for s, c in scored[:top_k]]


def _llm_enabled() -> bool:
    name = (getattr(settings, "RAG_LLM_PROVIDER", "local") or "local").lower()
    if name in ("openrouter", "openai"):
        if settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY:
            return True
    return False


def _build_context(scored: List[Tuple[DocumentChunk, float]]) -> str:
    parts = []
    for i, (chunk, _score) in enumerate(scored):
        snippet = (chunk.content or "")[:_MAX_CONTEXT_CHARS]
        parts.append(f"[Source {i + 1}]\n{snippet}")
    return "\n\n".join(parts)


async def compose_answer(
    query: str,
    scored: List[Tuple[DocumentChunk, float]],
    model_name: Optional[str] = None,
) -> str:
    """Compose a grounded answer from retrieved chunks.

    Uses the LLM provider when configured (``RAG_LLM_PROVIDER`` + a key),
    otherwise a deterministic offline composer.
    """
    if _llm_enabled() and scored:
        return await _generate_with_llm(query, scored)

    if not scored:
        return (
            "I could not find relevant information in this knowledge base for "
            "your question."
        )
    top_content = scored[0][0].content
    return (
        "Based on the knowledge base, the most relevant information is:\n\n"
        f"{top_content}\n\n"
        f"(Retrieved {len(scored)} chunk(s) from the knowledge base.)"
    )


async def _generate_with_llm(
    query: str,
    scored: List[Tuple[DocumentChunk, float]],
    model_name: Optional[str] = None,
) -> str:
    context = _build_context(scored)
    system = (
        "You are a helpful assistant that answers questions using ONLY the "
        "provided knowledge base context. Cite the relevant [Source N] numbers. "
        "If the context does not contain the answer, say so clearly."
    )
    user = f"Context:\n{context}\n\nQuestion: {query}"

    api_key = settings.OPENROUTER_API_KEY or settings.OPENAI_API_KEY
    provider = OpenRouterProvider(
        api_key=api_key,
        base_url=settings.OPENROUTER_BASE_URL,
    )
    request = GenerationRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ],
        model=model_name or settings.RAG_LLM_MODEL,
        temperature=0.2,
        max_tokens=512,
    )
    try:
        response = await provider.generate(request)
        return response.content or compose_answer_offline(scored)
    except Exception:
        # Never let a provider failure break the endpoint; fall back to the
        # offline composer so the user still gets the retrieved context.
        return compose_answer_offline(scored)
    finally:
        await provider.close()


def compose_answer_offline(scored: List[Tuple[DocumentChunk, float]]) -> str:
    """Deterministic offline answer composer used when no LLM is configured."""
    if not scored:
        return (
            "I could not find relevant information in this knowledge base for "
            "your question."
        )
    top_content = scored[0][0].content
    return (
        "Based on the knowledge base, the most relevant information is:\n\n"
        f"{top_content}\n\n"
        f"(Retrieved {len(scored)} chunk(s) from the knowledge base.)"
    )


__all__ = [
    "retrieve_chunks",
    "compose_answer",
    "compose_answer_offline",
]
