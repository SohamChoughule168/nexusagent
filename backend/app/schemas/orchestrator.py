"""Schemas for the Agent Orchestrator endpoints (Milestone 4, Phase 4)."""
import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class OrchestrateRequest(BaseModel):
    """Request body for ``POST /conversations/{id}/orchestrate``.

    Kicks off a multi-agent orchestrated task for the conversation's tenant.
    """

    goal: str = Field(..., min_length=1, description="The high-level goal to accomplish")
    halt_on_failure: bool = Field(
        default=False,
        description="If True, stop the plan and skip remaining steps after the first failure.",
    )
    max_retries: int = Field(
        default=1,
        ge=0,
        le=5,
        description="Number of retry attempts per step (beyond the first try).",
    )


class PlanStepSchema(BaseModel):
    step_id: str
    agent_ref: str
    instruction: str
    depends_on: List[str] = []
    parallel_group: Optional[str] = None
    max_retries: Optional[int] = None
    notes: Optional[str] = None


class TaskPlanSchema(BaseModel):
    goal: str
    steps: List[PlanStepSchema] = []


class PlanStepResultSchema(BaseModel):
    step_id: str
    agent_ref: str
    agent_id: Optional[str] = None
    status: str
    output: str
    error: Optional[str] = None
    error_type: Optional[str] = None
    attempts: int = 0
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    depends_on: List[str] = []
    duration_ms: float = 0.0


class OrchestrationResultSchema(BaseModel):
    goal: str
    plan: TaskPlanSchema
    step_results: List[PlanStepResultSchema] = []
    final_answer: str
    status: str
    duration_ms: float = 0.0


# Streaming event shapes (NDJSON lines emitted by the orchestrate endpoint).

class OrchestrateEvent(BaseModel):
    type: str  # "plan" | "step_start" | "step_result" | "token" | "done" | "error"
    data: Dict[str, Any] = {}


__all__ = [
    "OrchestrateRequest",
    "PlanStepSchema",
    "TaskPlanSchema",
    "PlanStepResultSchema",
    "OrchestrationResultSchema",
    "OrchestrateEvent",
]
