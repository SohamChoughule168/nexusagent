"""Unit tests for the Tool Execution Engine (Milestone 4, Phase 2).

These exercise ``app.services.tool_executor`` directly and need no database.
The engine's core is DB-free by design (mirroring the registry), so the only
outbound dependency -- the webhook HTTP call -- is mocked with ``unittest.mock``.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.models.all_models import Tool
from app.services.tool_executor import (
    ToolExecutionEngine,
    ToolExecutionError,
    ToolResult,
    validate_arguments,
)


# --- Fixtures ---------------------------------------------------------------


def _make_tool(tool_type: str, config=None, input_schema=None, name="t"):
    """Build an in-memory Tool model (no DB session needed).

    ``Tool.__init__`` only accepts ``organization_id`` + ``data``; the primary
    key is normally assigned at flush. For unit tests we set ``id`` directly so
    the engine can echo it back in the result.
    """
    tool = Tool(
        organization_id=uuid.uuid4(),
        data={
            "name": name,
            "tool_type": tool_type,
            "config": config or {},
            "input_schema": input_schema or {},
        },
    )
    tool.id = uuid.uuid4()
    return tool


# --- ToolResult -------------------------------------------------------------


def test_tool_result_to_dict_shape():
    started = datetime.now(timezone.utc)
    result = ToolResult(
        execution_id="e1",
        success=True,
        tool_id="11111111-1111-1111-1111-111111111111",
        tool_name="t",
        tool_type="function",
        arguments={"a": 1},
        output={"ok": True},
        started_at=started,
        duration_ms=3.5,
        meta={"x": 1},
    )
    d = result.to_dict()
    assert d["execution_id"] == "e1"
    assert d["success"] is True
    assert d["tool_id"] == "11111111-1111-1111-1111-111111111111"
    assert d["arguments"] == {"a": 1}
    assert d["output"] == {"ok": True}
    assert d["error"] is None
    assert d["error_type"] is None
    assert d["started_at"] == started.isoformat()
    assert d["duration_ms"] == 3.5
    assert d["meta"] == {"x": 1}


def test_tool_result_render_success_and_failure():
    ok = ToolResult(
        execution_id="e", success=True, tool_id=None, tool_name="echo",
        tool_type="function", arguments={}, output="hi",
    )
    assert ok.render() == "[tool:echo] hi"
    bad = ToolResult(
        execution_id="e", success=False, tool_id=None, tool_name="echo",
        tool_type="function", arguments={}, error="boom", error_type="tool_error",
    )
    assert bad.render() == "[tool:echo ERROR] boom"


# --- validate_arguments -----------------------------------------------------


def test_validate_arguments_none_is_empty_object():
    assert validate_arguments(None, None) == []


def test_validate_arguments_non_object_fails():
    assert any("must be a JSON object" in e for e in validate_arguments({}, "nope"))


def test_validate_arguments_missing_required():
    schema = {"type": "object", "properties": {"city": {"type": "string"}},
              "required": ["city"]}
    errors = validate_arguments(schema, {})
    assert any("missing required argument: city" in e for e in errors)


def test_validate_arguments_wrong_type():
    schema = {"type": "object", "properties": {"city": {"type": "string"}}}
    errors = validate_arguments(schema, {"city": 123})
    assert any("must be string" in e for e in errors)


def test_validate_arguments_bool_not_integer():
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}}
    errors = validate_arguments(schema, {"n": True})
    assert any("not a boolean" in e for e in errors)


def test_validate_arguments_unknown_keys_tolerated():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}
    assert validate_arguments(schema, {"a": "x", "b": "y"}) == []


def test_validate_arguments_valid_passes():
    schema = {"type": "object", "properties": {"a": {"type": "string"}},
              "required": ["a"]}
    assert validate_arguments(schema, {"a": "x"}) == []


# --- function strategy (built-in allow-list) --------------------------------


def test_execute_function_echo():
    tool = _make_tool("function", config={"function_name": "echo"})
    result = ToolExecutionEngine().execute(tool, {"value": "hi"})
    assert result.success is True
    assert result.output == "hi"
    assert result.error_type is None
    assert result.meta["function_name"] == "echo"


def test_execute_function_uppercase():
    tool = _make_tool("function", config={"function_name": "uppercase"})
    result = ToolExecutionEngine().execute(tool, {"value": "abc"})
    assert result.success is True
    assert result.output == "ABC"


def test_execute_function_lowercase():
    tool = _make_tool("function", config={"function_name": "lowercase"})
    result = ToolExecutionEngine().execute(tool, {"value": "ABC"})
    assert result.success is True
    assert result.output == "abc"


def test_execute_function_add_numeric():
    tool = _make_tool("function", config={"function_name": "add"})
    result = ToolExecutionEngine().execute(tool, {"a": 2, "b": 3})
    assert result.success is True
    assert result.output == 5.0


def test_execute_function_add_non_numeric_is_controlled_error():
    tool = _make_tool("function", config={"function_name": "add"})
    result = ToolExecutionEngine().execute(tool, {"a": "x", "b": 3})
    assert result.success is False
    assert result.error_type == "tool_error"


def test_execute_function_unknown_name_is_error():
    tool = _make_tool("function", config={"function_name": "explode"})
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert result.error_type == "tool_error"
    assert "explode" in result.error


def test_execute_function_never_evals_arbitrary_code():
    # Even if config/name look like code, the engine only dispatches to the
    # fixed built-in allow-list; there is no eval/exec path.
    tool = _make_tool("function", config={"function_name": "__import__('os').system"})
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False


# --- webhook strategy -------------------------------------------------------


def _mock_client(json_payload=None, text="", status=200):
    resp = MagicMock()
    resp.json.return_value = json_payload if json_payload is not None else {}
    resp.text = text
    resp.status_code = status
    client = MagicMock()
    client.__enter__.return_value.request.return_value = resp
    return client


def test_execute_webhook_success():
    tool = _make_tool("webhook", config={"endpoint": "https://api.example.com/hook"})
    with patch(
        "app.services.tool_executor.httpx.Client",
        return_value=_mock_client(json_payload={"ok": True}, status=200),
    ):
        result = ToolExecutionEngine().execute(tool, {"q": "weather"})
    assert result.success is True
    assert result.output == {"ok": True}
    assert result.meta["http_status"] == 200
    assert result.meta["http_method"] == "POST"
    assert result.meta["endpoint"] == "https://api.example.com/hook"


def test_execute_webhook_missing_endpoint_is_error():
    tool = _make_tool("webhook", config={})
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert result.error_type == "tool_error"
    assert "endpoint" in result.error


def test_execute_webhook_rejects_unsafe_scheme():
    tool = _make_tool("webhook", config={"endpoint": "file:///etc/passwd"})
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert result.error_type == "tool_error"
    assert "http(s)" in result.error


def test_execute_webhook_rejects_non_http():
    tool = _make_tool("webhook", config={"endpoint": "ftp://example.com/x"})
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert "http(s)" in result.error


# --- lead_capture / human_escalation ----------------------------------------


def test_execute_lead_capture_structures_payload():
    tool = _make_tool("lead_capture")
    result = ToolExecutionEngine().execute(
        tool, {"name": "Jane", "email": "j@x.com", "phone": "123"}
    )
    assert result.success is True
    assert result.output["name"] == "Jane"
    assert result.output["email"] == "j@x.com"
    assert result.meta["captured"] is True
    assert result.output["tool_id"] == str(tool.id)


def test_execute_human_escalation_structures_payload():
    tool = _make_tool("human_escalation")
    result = ToolExecutionEngine().execute(
        tool, {"reason": "urgent", "priority": "high"}
    )
    assert result.success is True
    assert result.output["escalated"] is True
    assert result.output["reason"] == "urgent"
    assert result.output["priority"] == "high"
    assert result.meta["escalated"] is True


# --- error isolation / unknown / custom -------------------------------------


def test_execute_unknown_tool_type_is_error():
    tool = _make_tool("rocket", name="r")
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert result.error_type == "tool_error"
    assert "rocket" in result.error


def test_execute_custom_is_not_runnable():
    tool = _make_tool("custom")
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert result.error_type == "tool_error"
    assert "custom" in result.error


def test_execute_argument_validation_failure():
    tool = _make_tool(
        "function",
        config={"function_name": "echo"},
        input_schema={"type": "object", "properties": {"q": {"type": "string"}},
                      "required": ["q"]},
    )
    result = ToolExecutionEngine().execute(tool, {})
    assert result.success is False
    assert result.error_type == "argument_validation"
    assert "missing required argument: q" in result.error


def test_execute_isolates_unexpected_exceptions():
    tool = _make_tool("function", config={"function_name": "echo"})
    with patch(
        "app.services.tool_executor._BUILTIN_FUNCTIONS",
        {"echo": lambda args, config: 1 / 0},
    ):
        result = ToolExecutionEngine().execute(tool, {"value": "x"})
    assert result.success is False
    assert result.error_type == "unexpected_error"
    assert "ZeroDivisionError" in result.error


def test_execute_never_raises():
    tool = _make_tool("function", config={"function_name": "echo"})
    with patch(
        "app.services.tool_executor._BUILTIN_FUNCTIONS",
        {"echo": lambda args, config: (_ for _ in ()).throw(RuntimeError("boom"))},
    ):
        # A regular exception is captured and reported as a result, never
        # propagated to the caller. (Control-flow exceptions such as
        # KeyboardInterrupt/SystemExit are intentionally NOT swallowed.)
        result = ToolExecutionEngine().execute(tool, {"value": "x"})
    assert result.success is False
    assert result.error_type == "unexpected_error"


# --- output truncation (safe execution cap) ---------------------------------


def test_execute_truncates_oversized_output():
    engine = ToolExecutionEngine()
    engine._max_output_chars = 5
    tool = _make_tool("function", config={"function_name": "echo"})
    result = engine.execute(tool, {"value": "abcdefghij"})
    assert result.success is True
    assert result.output == "abcde"
    assert result.meta["truncated"] is True


def test_execute_does_not_truncate_small_output():
    engine = ToolExecutionEngine()
    tool = _make_tool("function", config={"function_name": "echo"})
    result = engine.execute(tool, {"value": "abc"})
    assert result.output == "abc"
    assert result.meta.get("truncated") is False


# --- tenant-scoped execute_by_id (uses repository; requires DB) -------------


def test_execute_by_id_requires_db():
    engine = ToolExecutionEngine()
    with pytest.raises(ValueError):
        engine.execute_by_id(uuid.uuid4(), uuid.uuid4(), {})
