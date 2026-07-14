"""Tool Registry: supported tool types and definition validation.

The registry is the single source of truth for *which* tool types the platform
understands and *what* a valid tool definition looks like. It is deliberately
free of database access so it can be unit-tested in isolation and reused by both
the API schemas (to produce 422 responses) and later milestones (the execution
engine will look up ``tool_type`` here to pick a strategy).

A "tool definition" is a plain ``dict`` produced from the API request body, e.g.::

    {
        "name": "weather_lookup",
        "display_name": "Weather Lookup",
        "description": "Fetches the current weather for a city.",
        "tool_type": "function",
        "config": {"endpoint": "https://api.example.com/weather"},
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string"}},
        },
        "is_active": True,
    }
"""
from typing import Dict, Any, List

# Tool types the platform can register and (in later milestones) execute.
# Mirrors the feature flags in app.core.config (ENABLE_WEBHOOK_TOOL,
# ENABLE_LEAD_CAPTURE_TOOL, ENABLE_HUMAN_ESCALATION_TOOL) plus the generic
# code-backed and custom types.
SUPPORTED_TOOL_TYPES = (
    "webhook",          # Calls an external HTTP endpoint.
    "function",         # A code-backed / registered function.
    "lead_capture",     # Captures lead information from a conversation.
    "human_escalation",  # Escalates the conversation to a human agent.
    "custom",           # Operator-defined behaviour.
)


def validate_tool_definition(
    data: Dict[str, Any],
    partial: bool = False,
) -> List[str]:
    """Validate a tool definition, returning a list of human-readable errors.

    An empty list means the definition is valid. When ``partial`` is True the
    check is relaxed for updates (PATCH-style): ``name`` and ``tool_type`` are
    only validated when present, and missing required fields are not reported.

    This function performs *structural* validation only (types, allowed values,
    basic JSON-Schema shape). Tenant-scoping and persistence are handled by the
    repository / API layers.
    """
    errors: List[str] = []

    name = data.get("name")
    if name is not None:
        if not isinstance(name, str) or not name.strip():
            errors.append("name must be a non-empty string")
    elif not partial:
        errors.append("name is required")

    tool_type = data.get("tool_type")
    if tool_type is not None:
        if tool_type not in SUPPORTED_TOOL_TYPES:
            allowed = ", ".join(sorted(SUPPORTED_TOOL_TYPES))
            errors.append(f"tool_type must be one of: {allowed}")
    elif not partial:
        errors.append("tool_type is required")

    schema = data.get("input_schema")
    if schema is not None:
        if not isinstance(schema, dict):
            errors.append("input_schema must be a JSON object")
        elif schema:
            # A non-empty schema must look like a JSON Schema object.
            if schema.get("type") != "object":
                errors.append("input_schema must have type 'object'")
            if not isinstance(schema.get("properties"), dict):
                errors.append("input_schema must include a 'properties' object")

    config = data.get("config")
    if config is not None and not isinstance(config, dict):
        errors.append("config must be a JSON object")

    return errors
