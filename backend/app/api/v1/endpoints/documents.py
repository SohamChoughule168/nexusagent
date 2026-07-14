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
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.config import settings
from app.core.database import get_db
from app.models.all_models import Document, DocumentChunk
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.document import DocumentChunkResponse, DocumentResponse
from app.services.embeddings import cosine_similarity, get_embedding_provider
from app.services.ingestion import ingest_document
from app.services.tenant_context import TenantContext
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


@kb_documents_router.post(
    "/knowledge-bases/{knowledge_base_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: str,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    tenant: TenantContext = Depends(require_roles(*_WRITE_ROLES)),
    db: Session = Depends(get_db),
):
    """Upload a document (PDF) into a knowledge base owned by the tenant."""
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
    try:
        created = doc_repo.create(doc)
    except Exception:
        # Roll back the on-disk write if the DB insert failed.
        _remove_file(storage_path)
        raise
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

    return ingest_document(db, tenant, doc, kb)


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

    provider = get_embedding_provider(kb, settings)
    contents = [c.content for c in chunks]
    vectors = provider.embed(contents)

    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
        chunk.embedding_id = str(uuid.uuid4())
        chunk_repo.update(chunk)

    doc.status = "indexed"
    doc.meta = {
        **(doc.meta or {}),
        "embedding": {
            "provider": type(provider).__name__,
            "dimensions": provider.dimensions,
            "chunk_count": len(chunks),
        },
    }
    return doc_repo.update(doc)


@kb_documents_router.get(
    "/knowledge-bases/{knowledge_base_id}/search",
    response_model=List[DocumentChunkResponse],
)
def search_knowledge_base(
    knowledge_base_id: str,
    q: Optional[str] = None,
    top_k: int = 5,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Retrieve the most relevant document chunks for a query (RAG retrieval).

    Embeds the query with the knowledge base's provider, then ranks the
    knowledge base's embedded chunks by cosine similarity and returns the top-k.
    Any authenticated tenant member may search (read access).

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
