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
from app.ai.providers.factory import (
    active_llm_provider_name,
    create_llm_provider,
)
from app.ai.providers.base import ProviderError
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
    name = active_llm_provider_name(settings)
    if name == "local":
        return False
    try:
        return create_llm_provider(name, settings) is not None
    except ProviderError:
        # Configured provider but missing/invalid credentials -> degrade to
        # the offline composer rather than failing the request.
        return False


def rag_llm_enabled() -> bool:
    """Public accessor: is the LLM answer path configured?"""
    return _llm_enabled()


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

    provider = create_llm_provider(active_llm_provider_name(settings), settings, model_name)
    if provider is None:
        return compose_answer_offline(scored)

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


def build_sources(scored: List[Tuple[DocumentChunk, float]]) -> List[dict]:
    """Build serialisable source citations from scored chunks."""
    return [
        {
            "chunk_id": str(chunk.id),
            "document_id": str(chunk.document_id),
            "score": score,
            "snippet": (chunk.content or "")[:300],
        }
        for chunk, score in scored
    ]


def retrieve_chunks_for_query(
    org_id: uuid.UUID,
    db,
    query: str,
    top_k: int = 5,
    kb_ids: Optional[List[uuid.UUID]] = None,
) -> List[Tuple[DocumentChunk, float]]:
    """Retrieve the top-k chunks for ``query`` across one or more KBs.

    If ``kb_ids`` is provided, only those knowledge bases are searched;
    otherwise all of the organization's knowledge bases are searched. Tenant
    isolation is enforced by the tenant-scoped ``RepositoryFactory``.
    """
    repo_factory = RepositoryFactory(db, org_id)
    if kb_ids:
        kb_uuids = [uuid.UUID(str(k)) for k in kb_ids]
    else:
        kb_uuids = [kb.id for kb in repo_factory.knowledge_bases().get_all()]

    candidates = []
    for kb_id in kb_uuids:
        chunks = repo_factory.document_chunks().get_by_knowledge_base(
            uuid.UUID(str(kb_id))
        )
        candidates.extend(c for c in chunks if c.embedding)
    if not candidates:
        return []

    provider = get_embedding_provider(None, settings)
    (query_vec,) = provider.embed([query])
    scored = [
        (cosine_similarity(query_vec, c.embedding), c) for c in candidates
    ]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [(c, s) for s, c in scored[:top_k]]


async def stream_answer(
    query: str,
    scored: List[Tuple[DocumentChunk, float]],
    model_name: Optional[str] = None,
):
    """Stream a grounded answer token-by-token from the LLM provider."""
    context = _build_context(scored)
    system = (
        "You are a helpful assistant that answers questions using ONLY the "
        "provided knowledge base context. Cite the relevant [Source N] numbers. "
        "If the context does not contain the answer, say so clearly."
    )
    user = f"Context:\n{context}\n\nQuestion: {query}"

    provider = create_llm_provider(active_llm_provider_name(settings), settings, model_name)
    if provider is None:
        yield compose_answer_offline(scored)
        return
    request = GenerationRequest(
        messages=[
            Message(role=MessageRole.SYSTEM, content=system),
            Message(role=MessageRole.USER, content=user),
        ],
        model=model_name or settings.RAG_LLM_MODEL,
        temperature=0.2,
        max_tokens=512,
        stream=True,
    )
    try:
        async for chunk in provider.stream(request):
            if chunk.delta_content:
                yield chunk.delta_content
    except Exception:
        # On provider failure, fall back to the offline composer so the user
        # still receives the retrieved context as the answer.
        yield compose_answer_offline(scored)
    finally:
        await provider.close()


__all__ = [
    "retrieve_chunks",
    "compose_answer",
    "compose_answer_offline",
    "build_sources",
    "retrieve_chunks_for_query",
    "stream_answer",
    "rag_llm_enabled",
]
