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

This milestone stores document metadata + raw bytes only. No PDF parsing,
text extraction, chunking, embeddings, or vector storage happens here.
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
from app.models.all_models import Document
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.document import DocumentResponse
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
