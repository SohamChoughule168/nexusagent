import json
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.all_models import Agent
from app.repositories.tenant_repository import RepositoryFactory
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentSettingsResponse,
    Both,
    StringMap,
)

router = APIRouter(prefix="/agents", tags=["agents"])


def _slugify(value: str) -> str:
    """Minimal slugify without external dependency."""
    value = (value or "").lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or str(uuid4())[:8]


@router.get("/", response_model=List[AgentResponse])
def list_agents(db: Session = Depends(get_db)):
    """List all agents for the current context."""
    # NOTE: Tenant scoping is enforced in later milestones.
    repository_factory = RepositoryFactory(db)
    agents_repo = repository_factory.agents()
    return agents_repo.get_all()


@router.get("/{public_id}", response_model=AgentResponse)
def get_agent(public_id: str, db: Session = Depends(get_db)):
    """Get an agent by public ID."""
    repo_factory = RepositoryFactory(db)
    agents_repo = repo_factory.agents()
    agent = agents_repo.get_by_public_id(public_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    return agent


@router.post("/", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(agent_data: AgentCreate, db: Session = Depends(get_db)):
    """Create a new agent."""
    repo_factory = RepositoryFactory(db)
    agents_repo = repo_factory.agents()

    public_id = agent_data.public_id or str(uuid4())[:8]
    name_slug = _slugify(agent_data.name)

    config = dict(agent_data.config or {})
    config.setdefault("model_name", "anthropic/claude-3.5-sonnet")
    config.setdefault("temperature", 0.7)

    agent = Agent(
        organization_id=agent_data.organization_id
        if getattr(agent_data, "organization_id", None)
        else uuid4(),
        name=agent_data.name,
        description=agent_data.description,
        system_prompt=agent_data.system_prompt,
        welcome_message=agent_data.welcome_message,
        model_provider=agent_data.model_provider or "openrouter",
        model_name=config["model_name"],
        temperature=config["temperature"],
        max_tokens=config.get("max_tokens"),
        top_p=config.get("top_p"),
        presence_penalty=config.get("presence_penalty"),
        frequency_penalty=config.get("frequency_penalty"),
        status="draft",
        public_id=public_id,
        config=json.dumps(config),
    )

    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.put("/{public_id}", response_model=AgentResponse)
def update_agent(
    public_id: str, agent_data: AgentUpdate, db: Session = Depends(get_db)
):
    """Update an agent."""
    repo_factory = RepositoryFactory(db)
    agents_repo = repo_factory.agents()
    existing_agent = agents_repo.get_by_public_id(public_id)

    if not existing_agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    update_fields = agent_data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(existing_agent, field, value)

    existing_agent.updated_at = datetime.utcnow()
    db.add(existing_agent)
    db.commit()
    db.refresh(existing_agent)
    return existing_agent


@router.delete("/{public_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(public_id: str, db: Session = Depends(get_db)):
    """Delete an agent."""
    repo_factory = RepositoryFactory(db)
    agents_repo = repo_factory.agents()

    agent = agents_repo.get_by_public_id(public_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found",
        )

    agents_repo.delete(agent)
