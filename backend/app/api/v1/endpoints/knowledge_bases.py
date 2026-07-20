import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context
from app.core.database import get_db
from app.models.all_models import KnowledgeBase
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.knowledge_base import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
)
from app.services.audit import record_audit
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge-bases"])


def _uuid_or_400(value: str, field: str) -> uuid.UUID:
    """Parse a UUID supplied in a request path, returning 400 on failure."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}: expected a valid UUID",
        )


@router.post(
    "/",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    kb_data: KnowledgeBaseCreate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new knowledge base for the authenticated principal's tenant."""
    # Tenant isolation is enforced by deriving organization_id from the
    # authenticated principal (see app.core.auth_dependencies), never from
    # request data.
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kbs_repo = repo_factory.knowledge_bases()

    kb = KnowledgeBase(
        organization_id=str(tenant.organization_id),
        data=kb_data.model_dump(exclude_none=True),
    )

    try:
        created = kbs_repo.create(kb)
    except IntegrityError:
        # The live schema enforces a UNIQUE (organization_id, name) constraint.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A knowledge base with this name already exists",
        )
    record_audit(
        db, tenant.organization_id, "kb.create",
        user_id=str(tenant.user_id), resource_type="knowledge_base",
        resource_id=str(created.id), meta={"name": created.name},
    )
    return created


@router.get("/", response_model=List[KnowledgeBaseResponse])
def list_knowledge_bases(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List knowledge bases for the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kbs_repo = repo_factory.knowledge_bases()
    return kbs_repo.get_all()


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
def get_knowledge_base(
    kb_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get a knowledge base by id within the authenticated principal's tenant."""
    kb_uuid = _uuid_or_400(kb_id, "kb_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kbs_repo = repo_factory.knowledge_bases()

    kb = kbs_repo.get(kb_uuid)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )
    return kb


@router.put("/{kb_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base(
    kb_id: str,
    kb_data: KnowledgeBaseUpdate,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Update a knowledge base within the authenticated principal's tenant."""
    kb_uuid = _uuid_or_400(kb_id, "kb_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kbs_repo = repo_factory.knowledge_bases()

    kb = kbs_repo.get(kb_uuid)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    update_fields = kb_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(kb, field, value)

    try:
        updated = kbs_repo.update(kb)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A knowledge base with this name already exists",
        )
    record_audit(
        db, tenant.organization_id, "kb.update",
        user_id=str(tenant.user_id), resource_type="knowledge_base",
        resource_id=str(updated.id), meta={"fields": list(update_fields.keys())},
    )
    return updated


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    kb_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Delete a knowledge base within the authenticated principal's tenant."""
    kb_uuid = _uuid_or_400(kb_id, "kb_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    kbs_repo = repo_factory.knowledge_bases()

    kb = kbs_repo.get(kb_uuid)
    if kb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    kbs_repo.delete(kb)
    record_audit(
        db, tenant.organization_id, "kb.delete",
        user_id=str(tenant.user_id), resource_type="knowledge_base",
        resource_id=str(kb_uuid),
    )
