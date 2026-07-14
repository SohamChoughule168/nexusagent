"""Pydantic schemas for the Tool Registry API (Milestone 4, Phase 1)."""
from typing import Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator
from datetime import datetime

from app.services.tool_registry import validate_tool_definition


class ToolBase(BaseModel):
    """Shared fields for tool schemas."""

    name: str = Field(..., min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    tool_type: str = Field(..., min_length=1, max_length=50)
    config: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class ToolCreate(ToolBase):
    """Payload for registering (creating) a tool.

    Structural rules (supported ``tool_type``, JSON-Schema shape of
    ``input_schema``) are enforced here so invalid input yields a 422 before any
    database write.
    """

    @model_validator(mode="after")
    def _validate_definition(self) -> "ToolCreate":
        errors = validate_tool_definition(self.model_dump(), partial=False)
        if errors:
            raise ValueError("; ".join(errors))
        return self


class ToolUpdate(ToolBase):
    """Payload for updating a tool (all fields optional).

    Inherits every field from ``ToolBase`` (so ``is_active`` is included) but
    makes them optional so a PATCH-style partial update is valid.
    """

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    display_name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    tool_type: Optional[str] = Field(None, min_length=1, max_length=50)
    config: Optional[Dict[str, Any]] = None
    input_schema: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def _validate_definition(self) -> "ToolUpdate":
        # Partial validation: only the fields that are actually supplied are
        # checked; missing fields are left untouched on the stored tool.
        errors = validate_tool_definition(self.model_dump(), partial=True)
        if errors:
            raise ValueError("; ".join(errors))
        return self


class ToolResponse(ToolBase):
    """A registered tool as returned by the API."""

    id: UUID
    organization_id: UUID
    is_active: Optional[bool] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ToolExecuteRequest(BaseModel):
    """Payload to invoke a registered tool.

    ``arguments`` are the runtime parameters passed to the tool; they are
    validated against the tool's ``input_schema`` by the execution engine.
    """

    arguments: Optional[Dict[str, Any]] = None


class ToolExecutionResponse(BaseModel):
    """Normalized outcome of executing a tool (Milestone 4, Phase 2).

    Mirrors ``ToolResult.to_dict()``. ``success`` is False on any failure; the
    failure reason lives in ``error`` / ``error_type``.
    """

    execution_id: str
    success: bool
    tool_id: Optional[UUID] = None
    tool_name: str
    tool_type: str
    arguments: Dict[str, Any]
    output: Optional[Any] = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    started_at: datetime
    duration_ms: float
    meta: Dict[str, Any] = {}

    class Config:
        from_attributes = True
