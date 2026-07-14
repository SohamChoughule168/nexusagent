import json
from typing import List
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context, require_roles
from app.core.database import get_db
from app.models.all_models import Agent
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.agent import (
    AgentCreate,
    AgentResponse,
    AgentUpdate,
)
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/agents", tags=["agents"])

# Roles permitted to perform agent management (create/update/delete).
# Mirrors ``TenantContext.can_manage_agents`` (owner, admin, member). Reads are
# allowed for any authenticated member of the organization.
_AGENT_MANAGER_ROLES = ("owner", "admin", "member")


@router.get("/", response_model=List[AgentResponse])
def list_agents(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List agents for the authenticated principal's tenant."""
    # Tenant isolation is enforced by deriving organization_id from the
    # authenticated principal (see app.core.auth_dependencies), never from
    # request data.
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    agents_repo = repo_factory.agents()
    return agents_repo.get_all()


@router.get("/{public_id}", response_model=AgentResponse)
def get_agent(
    public_id: str,
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get an agent by public ID within the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    agents_repo = repo_factory.agents()
    agent = agents_repo.get_by_public_id(public_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    agent_data: AgentCreate,
    tenant: TenantContext = Depends(require_roles(*_AGENT_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Create a new agent for the authenticated principal's tenant."""
    # organization_id is derived exclusively from the authenticated principal;
    # it is never read from the request body and never randomly generated.
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    agents_repo = repo_factory.agents()

    public_id = agent_data.public_id or str(uuid4())[:8]

    config = dict(agent_data.config or {})
    config.setdefault("model_name", agent_data.model_name or "anthropic/claude-3.5-sonnet")
    config.setdefault(
        "temperature",
        agent_data.temperature if agent_data.temperature is not None else 0.7,
    )

    agent = Agent(
        organization_id=str(tenant.organization_id),
        data={
            "name": agent_data.name,
            "description": agent_data.description,
            "system_prompt": agent_data.system_prompt,
            "welcome_message": agent_data.welcome_message,
            "model_provider": agent_data.model_provider or "openrouter",
            "model_name": config["model_name"],
            "temperature": config["temperature"],
            "max_tokens": agent_data.max_tokens,
            "top_p": agent_data.top_p,
            "presence_penalty": agent_data.presence_penalty,
            "frequency_penalty": agent_data.frequency_penalty,
            "status": "draft",
            "public_id": public_id,
            "config": config,
        },
    )
    # The Agent model overrides the base ``id`` without a server_default, so an
    # explicit primary key is required for an ORM insert.
    agent.id = uuid4()

    return agents_repo.create(agent)


@router.put("/{public_id}", response_model=AgentResponse)
def update_agent(
    public_id: str,
    agent_data: AgentUpdate,
    tenant: TenantContext = Depends(require_roles(*_AGENT_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Update an agent within the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    agents_repo = repo_factory.agents()
    existing_agent = agents_repo.get_by_public_id(public_id)

    if not existing_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    # Only fields present in the request are mutated; the agent was already
    # resolved within the tenant, so updates stay tenant-scoped.
    update_fields = agent_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(existing_agent, field, value)

    return agents_repo.update(existing_agent)


@router.delete("/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    public_id: str,
    tenant: TenantContext = Depends(require_roles(*_AGENT_MANAGER_ROLES)),
    db: Session = Depends(get_db),
):
    """Delete an agent within the authenticated principal's tenant."""
    repo_factory = RepositoryFactory(db, tenant.organization_id)
    agents_repo = repo_factory.agents()

    agent = agents_repo.get_by_public_id(public_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    agents_repo.delete(agent)
