"""Document Upload API (Milestone 3).

Endpoints for uploading and managing documents inside a Knowledge Base.

Tenant isolation is enforced exactly like the Knowledge Base API: every
endpoint derives ``organization_id`` from the authenticated principal via
``app.core.auth_dependencies`` (``get_tenant_context`` / ``require_roles``),
never from request data. Write operations (upload, delete) are additionally
gated by RBAC using the existing ``require_roles`` hook; reads are open to any
authenticated member of the tenant.

Reused, never duplicated:
* ``RepositoryFactory`` -> ``knowledge_bases()`` / ``documents()``
* ``DocumentRepository`` / ``KnowledgeBaseRepository`` (tenant-filtered)
* ``Document`` model (aligned to the live ``documents`` schema)
* auth + tenant context + RBAC hooks
* ``settings`` for size / type limits

This milestone stores document metadata + raw bytes, adds a processing step
(``POST /documents/{id}/ingest``) that extracts text and splits it into
``DocumentChunk`` rows, and adds vector storage + retrieval:
``POST /documents/{id}/embed`` generates embeddings per chunk (stored on
``DocumentChunk.embedding``) and ``GET /knowledge-bases/{id}/search`` ranks
embedded chunks by cosine similarity. Embeddings use a pluggable provider
(local deterministic offline, OpenAI-compatible when a key is configured);
pgvector is the documented production upgrade (ADR-003).
"""
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, status, UploadFile
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.all_models import Document, DocumentChunk
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.document import DocumentChunkResponse, DocumentResponse
from app.schemas.rag import RAGQueryRequest, RAGQueryResponse
from app.services.audit import record_audit
from app.services.background_tasks import create_task, finish_task, start_task, update_progress
from app.services.embeddings import cosine_similarity, get_embedding_provider
from app.services.ingestion import ingest_document
from app.services.rag import compose_answer, retrieve_chunks
from app.services.tenant_context import TenantContext
from app.services.usage import record_event
from app.ai.providers.factory import active_llm_provider_name
# Reuse the existing UUID-path validation helper rather than duplicating it.
from app.api.v1.endpoints.knowledge_bases import _uuid_or_400

# Roles permitted to upload/delete documents. Any authenticated tenant member
# (including viewers) may list and read documents.
_WRITE_ROLES = ("owner", "admin", "member")

# Nested under a knowledge base.
kb_documents_router = APIRouter()
# Top-level document operations.
documents_router = APIRouter()


def _sanitize_filename(name: str) -> str:
    """Return a filesystem-safe basename, collapsing unsafe characters."""
    base = os.path.basename(name or "upload")
    safe = []
    for ch in base:
        safe.append(ch if (ch.isalnum() or ch in "._-") else "_")
    safe = "".join(safe).strip("_.")
    return safe or "upload"


def _build_storage_path(org_id: uuid.UUID, kb_id: uuid.UUID, token: uuid.UUID, safe_name: str) -> str:
    root = Path(settings.UPLOAD_STORAGE_DIR)
    return str(root / str(org_id) / str(kb_id) / f"{token}__{safe_name}")


def _save_file(storage_path: str, content: bytes) -> None:
    path = Path(storage_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _remove_file(storage_path: str) -> None:
    try:
        Path(storage_path).unlink(missing_ok=True)
    except OSError:
        pass


def _validate_file_type(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower().lstrip(".")
    content_type = (file.content_type or "").lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '.{ext}'. Allowed: {settings.ALLOWED_EXTENSIONS}",
        )
    if content_type not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported MIME type '{content_type}'. Allowed: {settings.ALLOWED_MIME_TYPES}",
        )


def _parse_tags(raw: Optional[str]) -> List[str]:
    """Parse a comma-separated tag string into a clean, de-duplicated list."""
    if not raw:
        return []
    out: List[str] = []
    for part in raw.split(","):
        tag = part.strip()
        if tag and tag not in out:
            out.append(tag)
    return out


def _document_ids_with_any_tag(
    repo_factory: RepositoryFactory,
    kb_uuid: uuid.UUID,
    tags: List[str],
) -> set:
    """Return the set of document ids in ``kb`` whose tags intersect ``tags``."""
    docs = repo_factory.documents().get_by_knowledge_base(kb_uuid)
    wanted = set(tags)
    return {
        str(d.id)
        for d in docs
        if wanted.intersection(set(d.tags or []))
    }


@kb_documents_router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    tenant: TenantContext = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """Upload a document (PDF) into a knowledge base owned by the tenant.

    ``tags`` is an optional comma-separated list of metadata tags stored on the
    document and later used to filter retrieval (see the search/query endpoints).
    """
    kb_uuid = _uuid_or_400(knowledge_base_id, "knowledge_base_id")
    org_id = tenant.organization_id

    repo_factory = RepositoryFactory(db, org_id)
    kb = repo_factory.knowledge_bases().get(kb_uuid)
    if kb is None:
        # Tenant isolation: a KB in another org is invisible -> 404.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    content = await file.read()

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File too large: {len(content)} bytes exceeds limit of {max_bytes} bytes",
        )

    _validate_file_type(file)

    original_filename = file.filename or "upload.bin"
    safe_name = _sanitize_filename(original_filename)
    storage_token = uuid.uuid4()
    storage_path = _build_storage_path(org_id, kb_uuid, storage_token, safe_name)

    try:
        _save_file(storage_path, content)
    except OSError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store uploaded file",
        )

    doc_data = {
        "knowledge_base_id": str(kb_uuid),
        "filename": original_filename,
        "original_filename": original_filename,
        "title": title or original_filename,
        "mime_type": file.content_type or "application/pdf",
        "file_size": len(content),
        "storage_path": storage_path,
        "status": "uploaded",
        "upload_member_id": str(tenant.user_id),
        "metadata": {"storage_token": str(storage_token)},
    }

    doc_repo = repo_factory.documents()
    doc = Document(organization_id=str(org_id), data=doc_data)
    # ``Document.__init__`` does not consume ``tags``, so assign it directly.
    parsed_tags = _parse_tags(tags)
    if parsed_tags:
        doc.tags = parsed_tags
    try:
        created = doc_repo.create(doc)
    except Exception:
        # Roll back the on-disk write if the DB insert failed.
        _remove_file(storage_path)
        raise
    record_audit(
        db, org_id, "document.upload",
        user_id=str(tenant.user_id), resource_type="document",
        resource_id=str(created.id), meta={"kb_id": str(kb_uuid), "tags": parsed_tags},
    )
    return created


@kb_documents_router.get(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=List[DocumentResponse],
)
def list_documents(
    knowledge_base_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List documents for a knowledge base within the tenant."""
    kb_uuid = _uuid_or_400(knowledge_base_id, "knowledge_base_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kb = repo_factory.knowledge_bases().get(kb_uuid)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return repo_factory.documents().get_by_knowledge_base(kb_uuid)


@documents_router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
)
def get_document(
    document_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get document metadata by id within the tenant."""
    doc_uuid = _uuid_or_400(document_id, "document_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    doc = repo_factory.documents().get(doc_uuid)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


@documents_router.get(
    "/documents",
    response_model=List[DocumentResponse],
    tags=["documents"],
)
def list_documents_org(
    knowledge_base_id: Optional[str] = Query(None, description="Filter by knowledge base"),
    status: Optional[str] = Query(None, description="Filter by lifecycle status"),
    tag: Optional[str] = Query(None, description="Filter by a metadata tag"),
    search: Optional[str] = Query(None, description="Substring match on title/filename"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List documents across the tenant's knowledge bases with optional filters.

    Supports scoping to a knowledge base (``knowledge_base_id``), a lifecycle
    ``status`` (uploaded/processed/indexed/failed), a metadata ``tag`` (ARRAY
    containment), and a free-text ``search`` over title/filename. Pagination is
    via ``limit`` / ``offset``. This is the org-wide document-management view
    that complements the per-KB listing.
    """
    kb_uuid = _uuid_or_400(knowledge_base_id, "knowledge_base_id") if knowledge_base_id else None
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    docs = repo_factory.documents().find(
        kb_id=kb_uuid,
        status=status,
        tag=tag,
        search=search,
        limit=limit,
        offset=offset,
    )
    return docs


@documents_router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_document(
    document_id: str,
    tenant: TenantContext = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """Delete a document within the tenant (hard delete; no soft-delete column)."""
    doc_uuid = _uuid_or_400(document_id, "document_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    doc_repo = repo_factory.documents()
    doc = doc_repo.get(doc_uuid)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    storage_path = doc.storage_path
    doc_repo.delete(doc)
    record_audit(
        db, tenant.organization_id, "document.delete",
        user_id=str(tenant.user_id), resource_type="document",
        resource_id=str(doc_uuid),
    )
    # Best-effort cleanup of the persisted raw bytes.
    _remove_file(storage_path)


@documents_router.post(
    "/documents/{document_id}/ingest",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
def ingest_document_endpoint(
    document_id: str,
    tenant: TenantContext = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """Extract, chunk and index a previously uploaded document (ingestion).

    This is the processing step that follows upload: it reads the document's
    raw bytes from storage, extracts text, splits it into chunks using the
    owning knowledge base's ``chunk_size`` / ``chunk_overlap`` / ``chunk_strategy``
    config, persists ``DocumentChunk`` rows, and marks the document ``processed``
    with its ``chunk_count``. No embeddings/vectors are produced here.

    Tenant isolation is enforced by deriving ``organization_id`` from the
    authenticated principal; a document in another org is invisible -> 404.
    Write operations require owner/admin/member roles (viewers get 403).
    """
    doc_uuid = _uuid_or_400(document_id, "document_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    doc_repo = repo_factory.documents()

    doc = doc_repo.get(doc_uuid)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    kb = repo_factory.knowledge_bases().get(uuid.UUID(str(doc.knowledge_base_id)))
    if kb is None:
        # Tenant isolation: a KB in another org (or a deleted KB) is invisible.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    result = ingest_document(db, tenant, doc, kb)
    record_audit(
        db, tenant.organization_id, "document.ingest",
        user_id=str(tenant.user_id), resource_type="document",
        resource_id=str(doc_uuid), meta={"chunk_count": result.chunk_count},
    )
    return result


@documents_router.post(
    "/documents/{document_id}/embed",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
)
def embed_document_endpoint(
    document_id: str,
    tenant: TenantContext = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """Generate and store embeddings for a document's chunks (vector storage).

    This is the step that follows ingestion: it loads the document's
    ``DocumentChunk`` rows, computes a dense embedding vector for each via the
    knowledge base's embedding provider (local deterministic embedder offline,
    OpenAI-compatible API when a key is configured), persists the vectors on
    ``DocumentChunk.embedding`` with an ``embedding_id``, and marks the document
    ``indexed``. Retrieval (``GET /knowledge-bases/{id}/search``) then ranks
    these chunks by cosine similarity.

    Tenant isolation + RBAC mirror the upload/ingest endpoints: ``organization_id``
    is derived from the principal and write roles (owner/admin/member) are
    required; viewers receive 403.
    """
    doc_uuid = _uuid_or_400(document_id, "document_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    doc_repo = repo_factory.documents()

    doc = doc_repo.get(doc_uuid)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    kb = repo_factory.knowledge_bases().get(uuid.UUID(str(doc.knowledge_base_id)))
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    chunk_repo = repo_factory.document_chunks()
    chunks = chunk_repo.get_by_document(doc_uuid)
    if not chunks:
        # Nothing to embed: the document must be ingested first.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document has no chunks; ingest it before embedding",
        )

    # Track the embedding job so clients can poll real status/progress.
    task = create_task(db, tenant.organization_id, "document_embed", {"document_id": str(doc_uuid)})
    start_task(db, task)

    provider = get_embedding_provider(kb, settings)
    contents = [c.content for c in chunks]
    vectors = provider.embed(contents)

    total = len(chunks)
    for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
        chunk.embedding = vector
        chunk.embedding_id = str(uuid.uuid4())
        chunk_repo.update(chunk)
        # Report incremental progress (chunking was the first 50%).
        update_progress(db, task, 50 + int((i + 1) / total * 50))

    doc.status = "indexed"
    doc.indexing_progress = 100
    doc.total_chunks = total
    doc.indexed_chunks = total
    from datetime import datetime, timezone

    doc.last_indexed_at = datetime.now(timezone.utc)
    doc.meta = {
        **(doc.meta or {}),
        "embedding": {
            "provider": type(provider).__name__,
            "dimensions": provider.dimensions,
            "chunk_count": total,
        },
    }
    finish_task(db, task, result={"document_id": str(doc_uuid), "chunks": total})
    record_audit(
        db, tenant.organization_id, "document.embed",
        user_id=str(tenant.user_id), resource_type="document",
        resource_id=str(doc_uuid), meta={"chunks": total},
    )
    return doc_repo.update(doc)


@kb_documents_router.get(
    "/knowledge-bases/{knowledge_base_id}/search",
    response_model=List[DocumentChunkResponse],
)
def search_knowledge_base(
    knowledge_base_id: str,
    q: Optional[str] = None,
    top_k: int = 5,
    tags: Optional[List[str]] = Query(None, description="Restrict to documents carrying any of these tags"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieve the most relevant document chunks for a query (RAG retrieval).

    Embeds the query with the knowledge base's provider, then ranks the
    knowledge base's embedded chunks by cosine similarity and returns the top-k.
    Any authenticated tenant member may search (read access).

    ``tags`` (optional, repeatable) restricts retrieval to chunks whose document
    carries at least one of the supplied metadata tags -- the Milestone B
    metadata-filtering capability.

    Tenant isolation is enforced: a knowledge base in another org is invisible
    -> 404, and only this tenant's chunks are ranked.
    """
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter 'q' is required",
        )
    top_k = max(1, min(int(top_k), 20))

    kb_uuid = _uuid_or_400(knowledge_base_id, "knowledge_base_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kb = repo_factory.knowledge_bases().get(kb_uuid)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    chunk_repo = repo_factory.document_chunks()
    chunks = chunk_repo.get_by_knowledge_base(kb_uuid)
    # Only chunks that have been embedded can be ranked.
    embedded = [c for c in chunks if c.embedding]

    # Milestone B: metadata filtering. Restrict to chunks whose document has at
    # least one of the requested tags (no tag filter -> search everything).
    if tags:
        allowed = _document_ids_with_any_tag(repo_factory, kb_uuid, tags)
        embedded = [c for c in embedded if str(c.document_id) in allowed]

    provider = get_embedding_provider(kb, settings)
    (query_vec,) = provider.embed([q])

    scored = []
    for chunk in embedded:
        score = cosine_similarity(query_vec, chunk.embedding)
        scored.append((score, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    results = []
    for score, chunk in top:
        item = DocumentChunkResponse.model_validate(chunk)
        item.score = score
        results.append(item)
    return results


@kb_documents_router.post(
    "/knowledge-bases/{knowledge_base_id}/query",
    response_model=RAGQueryResponse,
)
async def query_knowledge_base(
    knowledge_base_id: str,
    payload: RAGQueryRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Answer a question using the knowledge base (RAG query).

    Retrieves the most relevant embedded chunks for the question, then composes
    a grounded answer (locally offline, or via the configured LLM when
    ``RAG_LLM_PROVIDER`` + a key are set). Returns the answer plus its sources.
    Any authenticated tenant member may query (read access).

    ``tags`` (optional, repeatable on the request body) restricts retrieval to
    chunks whose document carries at least one of the supplied metadata tags.

    Tenant isolation: a knowledge base in another org is invisible -> 404, and
    only this tenant's chunks are retrieved/ranked.
    """
    q = payload.question
    if not q or not q.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question is required",
        )
    top_k = max(1, min(int(payload.top_k), 20))

    kb_uuid = _uuid_or_400(knowledge_base_id, "knowledge_base_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kb = repo_factory.knowledge_bases().get(kb_uuid)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    scored = retrieve_chunks(kb, q, db, tenant.organization_id, top_k)

    # Milestone B: metadata filtering on the retrieved set.
    tags = payload.tags
    if tags:
        allowed = _document_ids_with_any_tag(repo_factory, kb_uuid, tags)
        scored = [(c, s) for c, s in scored if str(c.document_id) in allowed]

    started_at = datetime.now(timezone.utc)
    answer = await compose_answer(q, scored)
    latency_ms = int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)

    # Milestone B, Step 5: record a RAG-query usage event so analytics has
    # real latency / provider / success data (defensive: never breaks the query).
    record_event(
        db, tenant.organization_id, "rag_query",
        model_provider=active_llm_provider_name(settings),
        model_name=settings.RAG_LLM_MODEL,
        latency_ms=latency_ms,
        status="success" if answer else "error",
        meta={"kb_id": str(kb_uuid), "chunks": len(scored)},
    )

    sources = [
        {
            "chunk_id": chunk.id,
            "document_id": chunk.document_id,
            "score": score,
            "snippet": (chunk.content or "")[:300],
        }
        for chunk, score in scored
    ]
    return RAGQueryResponse(answer=answer, sources=sources)
