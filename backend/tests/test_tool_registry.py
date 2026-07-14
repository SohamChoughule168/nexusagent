"""Unit tests for the Tool Registry validation logic (Milestone 4, Phase 1).

These tests exercise ``app.services.tool_registry`` directly and need no
database -- they pin down the structural rules the API schemas rely on to
produce 422 responses.
"""
import pytest

from app.services.tool_registry import (
    SUPPORTED_TOOL_TYPES,
    validate_tool_definition,
)


VALID_DEFINITION = {
    "name": "weather_lookup",
    "display_name": "Weather Lookup",
    "description": "Fetches current weather for a city.",
    "tool_type": "function",
    "config": {"endpoint": "https://api.example.com/weather"},
    "input_schema": {
        "type": "object",
        "properties": {"city": {"type": "string"}},
    },
    "is_active": True,
}


def test_supported_tool_types_are_expected():
    assert SUPPORTED_TOOL_TYPES == (
        "webhook",
        "function",
        "lead_capture",
        "human_escalation",
        "custom",
    )


def test_valid_definition_passes():
    assert validate_tool_definition(VALID_DEFINITION) == []


def test_minimal_valid_definition_passes():
    # description / input_schema / config may be omitted; the API fills them.
    definition = {"name": "ping", "tool_type": "function"}
    assert validate_tool_definition(definition) == []


def test_missing_name_fails():
    errors = validate_tool_definition({"tool_type": "function"})
    assert any("name is required" in e for e in errors)


def test_empty_name_fails():
    errors = validate_tool_definition({"name": "   ", "tool_type": "function"})
    assert any("name must be a non-empty string" in e for e in errors)


def test_invalid_tool_type_fails():
    errors = validate_tool_definition({"name": "x", "tool_type": "rocket"})
    assert any("tool_type must be one of" in e for e in errors)


def test_input_schema_not_a_dict_fails():
    errors = validate_tool_definition(
        {"name": "x", "tool_type": "function", "input_schema": "nope"}
    )
    assert any("input_schema must be a JSON object" in e for e in errors)


def test_input_schema_wrong_type_fails():
    errors = validate_tool_definition(
        {
            "name": "x",
            "tool_type": "function",
            "input_schema": {"type": "string", "properties": {}},
        }
    )
    assert any("input_schema must have type 'object'" in e for e in errors)


def test_input_schema_missing_properties_fails():
    errors = validate_tool_definition(
        {
            "name": "x",
            "tool_type": "function",
            "input_schema": {"type": "object"},
        }
    )
    assert any("input_schema must include a 'properties' object" in e for e in errors)


def test_config_not_a_dict_fails():
    errors = validate_tool_definition(
        {"name": "x", "tool_type": "function", "config": "nope"}
    )
    assert any("config must be a JSON object" in e for e in errors)


def test_empty_input_schema_is_allowed():
    # An empty object means "no parameters" and is valid.
    errors = validate_tool_definition(
        {"name": "x", "tool_type": "function", "input_schema": {}}
    )
    assert errors == []


# --- Partial (update) validation ----------------------------------------------


def test_partial_update_allows_missing_required_fields():
    assert validate_tool_definition({}, partial=True) == []


def test_partial_update_still_validates_supplied_tool_type():
    errors = validate_tool_definition({"tool_type": "rocket"}, partial=True)
    assert any("tool_type must be one of" in e for e in errors)


def test_partial_update_still_validates_supplied_input_schema():
    errors = validate_tool_definition(
        {"input_schema": {"type": "string"}}, partial=True
    )
    assert any("input_schema must have type 'object'" in e for e in errors)
