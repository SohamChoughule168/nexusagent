import uuid
from datetime import datetime, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.database import get_db
from app.models.all_models import Tool
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.tool import (
    ToolCreate,
    ToolExecutionResponse,
    ToolExecuteRequest,
    ToolResponse,
    ToolUpdate,
)
from app.services.audit import record_audit
from app.services.tool_executor import ToolExecutionEngine
from app.services.tool_registry import SUPPORTED_TOOL_TYPES
from app.services.usage import record_event
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/tools", tags=["tools"])

# Single engine instance shared across requests (stateless, tenant-scoped per
# call). Reuses the existing RepositoryFactory/ToolRepository for tenant
# isolation rather than opening its own data path.
_executor = ToolExecutionEngine()

# Roles permitted to manage (register / update / delete) tools. Reads are
# allowed for any authenticated member of the organization, mirroring the agent
# management boundary.
_TOOL_MANAGER_ROLES = ("owner", "admin", "member")


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
    response_model=ToolResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_tool(
    tool_data: ToolCreate,
    tenant: TenantContext = Depends(require_roles(*_TOOL_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Register a new tool in the authenticated principal's tenant.

    Tenant isolation is enforced by deriving ``organization_id`` from the
    authenticated principal (see ``app.core.auth_dependencies``), never from the
    request body. Structural validation of ``tool_type`` / ``input_schema`` is
    performed by the ``ToolCreate`` schema before this handler runs.
    """
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    tools_repo = repo_factory.tools()

    tool = Tool(
        organization_id=str(tenant.organization_id),
        data=tool_data.model_dump(exclude_none=True),
    )
    created = tools_repo.create(tool)
    record_audit(
        db, tenant.organization_id, "tool.register",
        user_id=str(tenant.user_id), resource_type="tool",
        resource_id=str(created.id), meta={"tool_type": created.tool_type},
    )
    return created


@router.get("/", response_model=List[ToolResponse])
def list_tools(
    tool_type: Optional[str] = Query(None, description="Filter by tool type"),
    is_active: Optional[bool] = Query(None, description="Filter by enabled state"),
    search: Optional[str] = Query(None, description="Substring match on name/display/description"),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Discover tools within the authenticated principal's tenant.

    Supports filtering by ``tool_type``, ``is_active``, and a free-text
    ``search`` across name / display name / description.
    """
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    tools_repo = repo_factory.tools()
    return tools_repo.find(tool_type=tool_type, is_active=is_active, search=search)


@router.get("/types", response_model=List[str])
def list_tool_types(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List the tool types the platform supports (registry discovery helper)."""
    return sorted(SUPPORTED_TOOL_TYPES)


@router.get("/{tool_id}", response_model=ToolResponse)
def get_tool(
    tool_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get a single tool by id within the authenticated principal's tenant."""
    tool_uuid = _uuid_or_400(tool_id, "tool_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    tools_repo = repo_factory.tools()

    tool = tools_repo.get(tool_uuid)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found",
        )
    return tool


@router.put("/{tool_id}", response_model=ToolResponse)
def update_tool(
    tool_id: str,
    tool_data: ToolUpdate,
    tenant: TenantContext = Depends(require_roles(*_TOOL_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Update a tool within the authenticated principal's tenant.

    Only the fields present in the request are mutated; the tool is resolved
    within the tenant first, so updates stay tenant-scoped. ``None`` values are
    ignored so NOT NULL columns are never set to NULL.
    """
    tool_uuid = _uuid_or_400(tool_id, "tool_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    tools_repo = repo_factory.tools()

    tool = tools_repo.get(tool_uuid)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found",
        )

    update_fields = {
        k: v for k, v in tool_data.model_dump(exclude_unset=True).items() if v is not None
    }
    for field, value in update_fields.items():
        setattr(tool, field, value)

    updated = tools_repo.update(tool)
    record_audit(
        db, tenant.organization_id, "tool.update",
        user_id=str(tenant.user_id), resource_type="tool",
        resource_id=str(updated.id), meta={"fields": list(update_fields.keys())},
    )
    return updated


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tool(
    tool_id: str,
    tenant: TenantContext = Depends(require_roles(*_TOOL_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Delete a tool within the authenticated principal's tenant."""
    tool_uuid = _uuid_or_400(tool_id, "tool_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    tools_repo = repo_factory.tools()

    tool = tools_repo.get(tool_uuid)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found",
        )

    tools_repo.delete(tool)
    record_audit(
        db, tenant.organization_id, "tool.delete",
        user_id=str(tenant.user_id), resource_type="tool", resource_id=str(tool_id),
    )


@router.post(
    "/{tool_id}/execute",
    response_model=ToolExecutionResponse,
)
def execute_tool(
    tool_id: str,
    payload: ToolExecuteRequest,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Execute a registered tool within the authenticated principal's tenant.

    The tool is resolved *inside* ``organization_id`` (derived from the
    principal), so a tool owned by another tenant cannot be executed -- tenant
    isolation is preserved by the engine's repository lookup. Any tenant member
    may invoke a tool; the fine-grained Tool-Permissions matrix is a later Phase
    2 component.

    A successful HTTP 200 does not imply the tool *ran* successfully: tool
    failures are reported via ``success=False`` in the body (mirroring agent
    tool-call semantics). A 404 means the tool does not exist in this tenant.
    """
    tool_uuid = _uuid_or_400(tool_id, "tool_id")
    result = _executor.execute_by_id(
        tool_id=tool_uuid,
        organization_id=tenant.organization_id,
        arguments=payload.arguments,
        db=db,
        caller_role=tenant.role,
    )
    if result.error_type == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found",
        )
    # Milestone B: tool-permission denial surfaces as 403, not a 200 error body.
    if result.error_type == "permission_denied":
        record_audit(
            db, tenant.organization_id, "tool.execute_denied",
            user_id=str(tenant.user_id), resource_type="tool",
            resource_id=str(tool_uuid), meta={"role": tenant.role},
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=result.error or "Tool execution not permitted for your role",
        )

    record_event(
        db, tenant.organization_id, "tool_execution",
        model_provider=result.tool_type, model_name=result.tool_name,
        latency_ms=int(result.duration_ms),
        status="success" if result.success else "error",
        error=result.error if not result.success else None,
        meta={"tool_id": str(result.tool_id), "error_type": result.error_type},
    )
    record_audit(
        db, tenant.organization_id, "tool.execute",
        user_id=str(tenant.user_id), resource_type="tool",
        resource_id=str(tool_uuid),
        meta={"success": result.success, "error_type": result.error_type},
    )
    return ToolExecutionResponse(**result.to_dict())


@router.post(
    "/{tool_id}/health",
    response_model=ToolResponse,
)
def check_tool_health(
    tool_id: str,
    tenant: TenantContext = Depends(require_roles(*_TOOL_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Probe a tool's health and persist the result (Milestone B, Step 3).

    Webhook tools are probed with a lightweight ``HEAD`` request to their
    configured endpoint (no payload, short timeout) so the check is safe and
    cheap. Connection failures / timeouts mark the tool ``down``; any response
    (including 4xx, which still proves the endpoint is reachable) marks it
    ``ok``. Non-network tool types (function / lead_capture / human_escalation)
    are marked ``ok``; ``custom`` tools (operator-defined) are ``unknown``.

    The result is written to ``tool.health_status`` / ``last_checked_at`` and
    returned on every tool read. Requires a manager role (same as updates).
    """
    tool_uuid = _uuid_or_400(tool_id, "tool_id")
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    tools_repo = repo_factory.tools()

    tool = tools_repo.get(tool_uuid)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found",
        )

    health = _probe_tool_health(tool)
    tool.health_status = health
    tool.last_checked_at = datetime.now(timezone.utc)
    updated = tools_repo.update(tool)
    record_audit(
        db, tenant.organization_id, "tool.health_check",
        user_id=str(tenant.user_id), resource_type="tool",
        resource_id=str(tool.id), meta={"health_status": health},
    )
    return updated


def _probe_tool_health(tool: Tool) -> str:
    """Return a coarse health status for a tool without raising."""
    if tool.tool_type == "webhook":
        endpoint = (tool.config or {}).get("endpoint") or (tool.config or {}).get("url")
        if not endpoint:
            return "unknown"
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.head(endpoint, follow_redirects=True)
            # Any response (even 4xx/5xx) proves the endpoint is reachable.
            return "ok" if resp.status_code < 500 else "degraded"
        except (httpx.ConnectError, httpx.TimeoutException, httpx.TransportError):
            return "down"
        except Exception:
            return "unknown"
    if tool.tool_type == "custom":
        return "unknown"
    # function / lead_capture / human_escalation are built-in and always healthy.
    return "ok"
