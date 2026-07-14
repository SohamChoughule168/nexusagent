"""Tool Execution Engine (Milestone 4, Phase 2 -- first component).

The execution engine is the *runtime* counterpart to the Phase 1 Tool Registry:

* The **registry** (``app.services.tool_registry``) decides *which* tool types
  are valid and what a well-formed tool *definition* looks like.
* The **execution engine** (this module) decides *how* each registered tool type
  *runs* and produces a single normalized ``ToolResult``.

Design goals / reuse of existing architecture
---------------------------------------------
* **DB-free core.** Like the registry, the engine performs no database I/O of
  its own, so it is unit-testable in isolation. Tenant-scoped loading of a tool
  by id is delegated to ``ToolRepository`` (via ``RepositoryFactory``), which
  already enforces tenant isolation at the SQL ``WHERE`` level.
* **Safe-by-default.** Every strategy runs inside a guarded wrapper that:
  - validates ``arguments`` against the tool's ``input_schema``;
  - isolates exceptions (a failing tool returns an *error result*, never raises);
  - enforces an HTTP timeout and an output-size cap for the webhook strategy;
  - only ever issues ``http``/``https`` requests and **never** evaluates or
    executes arbitrary caller-supplied code (the ``function`` type dispatches
    only to a fixed allow-list of built-in functions).

The remaining Phase 2 components -- a dedicated Safe-Execution hardening layer,
a Tool-Permissions matrix, Context Injection, a Result-Formatting subsystem, and
persistent Execution Logging -- build on this engine in later work.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.models.all_models import Tool
from app.repositories.tenant_repository import RepositoryFactory

logger = get_logger(__name__)


class ToolExecutionError(Exception):
    """Raised by a strategy to signal a *controlled* execution failure.

    Controlled failures become an error ``ToolResult`` (``success=False``,
    ``error_type="tool_error"``) rather than propagating to the caller.
    """


@dataclass
class ToolResult:
    """Normalized outcome of executing a single tool.

    ``success`` is True only when the tool ran and produced an ``output``. On
    failure, ``error`` / ``error_type`` describe what went wrong and ``meta``
    carries engine/strategy diagnostics (HTTP status, truncation flag, timing).
    The result is intentionally JSON-serializable via :meth:`to_dict`.
    """

    execution_id: str
    success: bool
    tool_id: Optional[str]
    tool_name: str
    tool_type: str
    arguments: Dict[str, Any]
    output: Any = None
    error: Optional[str] = None
    error_type: Optional[str] = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable representation of this result."""
        return {
            "execution_id": self.execution_id,
            "success": self.success,
            "tool_id": self.tool_id,
            "tool_name": self.tool_name,
            "tool_type": self.tool_type,
            "arguments": self.arguments,
            "output": self.output,
            "error": self.error,
            "error_type": self.error_type,
            "started_at": self.started_at.isoformat(),
            "duration_ms": self.duration_ms,
            "meta": self.meta,
        }

    def render(self) -> str:
        """Best-effort textual rendering for downstream context injection.

        Intentionally minimal -- the dedicated Result-Formatting subsystem is a
        later Phase 2 component.
        """
        if self.success:
            return f"[tool:{self.tool_name}] {self.output}"
        return f"[tool:{self.tool_name} ERROR] {self.error or 'execution failed'}"


# ---------------------------------------------------------------------------
# Argument validation (runtime)
# ---------------------------------------------------------------------------


def validate_arguments(
    schema: Optional[Dict[str, Any]],
    args: Any,
) -> List[str]:
    """Validate runtime ``arguments`` against a tool ``input_schema``.

    Mirrors the JSON-Schema-flavoured shape produced by the registry
    (``type: object``, ``properties``, ``required``). Returns a list of
    human-readable errors (empty == valid). Unknown / extra keys are tolerated.

    This runs the actual call arguments against the schema the tool was
    registered with, complementing ``validate_tool_definition`` (which validates
    the *shape* of the schema itself).
    """
    errors: List[str] = []
    if args is None:
        args = {}
    if not isinstance(args, dict):
        return ["arguments must be a JSON object"]

    schema = schema or {}
    properties = schema.get("properties") or {}
    required = schema.get("required") or []

    for field_name in required:
        if field_name not in args or args.get(field_name) is None:
            errors.append(f"missing required argument: {field_name}")

    type_map: Dict[str, Tuple[type, ...]] = {
        "string": (str,),
        "integer": (int,),
        "number": (int, float),
        "boolean": (bool,),
        "object": (dict,),
        "array": (list,),
    }
    for field_name, value in args.items():
        if field_name not in properties:
            continue
        prop = properties[field_name] or {}
        expected = prop.get("type")
        if expected is None or value is None:
            continue
        # bool is a subclass of int/float; reject it for numeric fields.
        if expected in ("integer", "number") and isinstance(value, bool):
            errors.append(f"argument '{field_name}' must be {expected} (not a boolean)")
            continue
        py_types = type_map.get(expected)
        if py_types is None:
            continue
        if not isinstance(value, py_types):
            errors.append(f"argument '{field_name}' must be {expected}")
    return errors


# ---------------------------------------------------------------------------
# Built-in (safe) functions for the "function" tool type
# ---------------------------------------------------------------------------
# The generic engine never evaluates arbitrary code. A ``function`` tool runs
# *only* when its ``config.function_name`` maps to one of these allow-listed
# callables, keeping execution safe by construction.


def _bf_echo(args: Dict[str, Any], config: Dict[str, Any]) -> Any:
    return args.get("value", args)


def _bf_uppercase(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    return str(args.get("value", "")).upper()


def _bf_lowercase(args: Dict[str, Any], config: Dict[str, Any]) -> str:
    return str(args.get("value", "")).lower()


def _bf_add(args: Dict[str, Any], config: Dict[str, Any]) -> float:
    a, b = args.get("a"), args.get("b")
    try:
        return float(a) + float(b)
    except (TypeError, ValueError):
        raise ToolExecutionError("add requires numeric 'a' and 'b' arguments")


_BUILTIN_FUNCTIONS: Dict[str, Callable[[Dict[str, Any], Dict[str, Any]], Any]] = {
    "echo": _bf_echo,
    "uppercase": _bf_uppercase,
    "lowercase": _bf_lowercase,
    "add": _bf_add,
}


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def _is_safe_url(url: str) -> bool:
    """Allow only ``http``/``https`` absolute URLs for outbound tool calls."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
    except (ValueError, TypeError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _elapsed_ms(started: datetime) -> float:
    return round((datetime.now(timezone.utc) - started).total_seconds() * 1000, 3)


class ToolExecutionEngine:
    """Executes registered tools and returns a normalized ``ToolResult``.

    The engine is stateless with respect to tenants. Callers pass either a
    concrete ``Tool`` (when already loaded) or a ``tool_id`` +
    ``organization_id`` -- the latter routes through ``ToolRepository`` for
    tenant-scoped resolution.
    """

    def __init__(self, default_timeout: Optional[float] = None):
        self._default_timeout = float(
            default_timeout
            if default_timeout is not None
            else getattr(settings, "TOOL_EXECUTION_TIMEOUT_SECONDS", 15.0)
        )
        self._max_output_chars = int(
            getattr(settings, "TOOL_EXECUTION_MAX_OUTPUT_CHARS", 10000)
        )

    # --- Public API ---------------------------------------------------------

    def execute(
        self,
        tool: Tool,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """Execute a concrete ``Tool`` model with ``arguments``.

        Never raises: every failure path yields a ``ToolResult`` with
        ``success=False``. The strategy is resolved up-front so an unknown
        ``tool_type`` surfaces as a controlled error result.
        """
        started = datetime.now(timezone.utc)
        execution_id = str(uuid.uuid4())
        args = arguments or {}

        # Argument validation (execution correctness) before any side effects.
        validation_errors = validate_arguments(tool.input_schema, args)
        if validation_errors:
            logger.warning(
                "tool_execution_argument_error",
                tool_id=str(tool.id) if getattr(tool, "id", None) else None,
                tool_name=tool.name,
                errors=validation_errors,
            )
            return self._error_result(
                tool, execution_id, started, args,
                error="; ".join(validation_errors),
                error_type="argument_validation",
            )

        handler = self._strategy_for(tool.tool_type)
        try:
            output, extra_meta = handler(tool, args, execution_id)
            meta = dict(extra_meta or {})
            truncated = False
            if isinstance(output, str) and len(output) > self._max_output_chars:
                output = output[: self._max_output_chars]
                truncated = True
            meta["truncated"] = truncated
            result = ToolResult(
                execution_id=execution_id,
                success=True,
                tool_id=str(tool.id) if getattr(tool, "id", None) else None,
                tool_name=tool.name,
                tool_type=tool.tool_type,
                arguments=args,
                output=output,
                started_at=started,
                duration_ms=_elapsed_ms(started),
                meta=meta,
            )
            logger.info(
                "tool_execution_completed",
                execution_id=execution_id,
                tool_id=result.tool_id,
                tool_name=tool.name,
                tool_type=tool.tool_type,
                duration_ms=result.duration_ms,
                truncated=truncated,
            )
            return result
        except ToolExecutionError as exc:
            return self._error_result(
                tool, execution_id, started, args,
                error=str(exc), error_type="tool_error",
            )
        except Exception as exc:  # isolation: never propagate to the caller
            logger.error(
                "tool_execution_unexpected_error",
                execution_id=execution_id,
                tool_name=tool.name,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            return self._error_result(
                tool, execution_id, started, args,
                error=f"{type(exc).__name__}: {exc}",
                error_type="unexpected_error",
            )

    def execute_by_id(
        self,
        tool_id: uuid.UUID,
        organization_id: uuid.UUID,
        arguments: Optional[Dict[str, Any]] = None,
        db: Optional[Any] = None,
    ) -> ToolResult:
        """Tenant-scoped execution: resolve the tool *within* ``organization_id``.

        Reuses ``ToolRepository`` (via ``RepositoryFactory``), so tenant isolation
        is enforced by the query filter -- a tool owned by another tenant resolves
        to ``None`` and yields a not-found error result.
        """
        if db is None:
            raise ValueError("execute_by_id requires a database session")
        repo = RepositoryFactory(db, organization_id).tools()
        tool = repo.get(tool_id)
        if tool is None:
            return ToolResult(
                execution_id=str(uuid.uuid4()),
                success=False,
                tool_id=str(tool_id),
                tool_name="",
                tool_type="",
                arguments=arguments or {},
                error="Tool not found in this tenant",
                error_type="not_found",
                started_at=datetime.now(timezone.utc),
                meta={"organization_id": str(organization_id)},
            )
        return self.execute(tool, arguments)

    # --- Strategies ---------------------------------------------------------

    def _strategy_for(self, tool_type: str) -> Callable:
        return {
            "webhook": self._execute_webhook,
            "function": self._execute_function,
            "lead_capture": self._execute_lead_capture,
            "human_escalation": self._execute_human_escalation,
            "custom": self._execute_custom,
        }.get(tool_type, self._execute_unknown)

    def _execute_webhook(
        self, tool: Tool, args: Dict[str, Any], execution_id: str
    ) -> Tuple[Any, Dict[str, Any]]:
        config = tool.config or {}
        endpoint = config.get("endpoint") or config.get("url")
        if not endpoint:
            raise ToolExecutionError(
                "webhook tool is missing an 'endpoint' in its config"
            )
        if not _is_safe_url(endpoint):
            raise ToolExecutionError("webhook endpoint must be an http(s) URL")
        method = str(config.get("method") or "POST").upper()
        headers = dict(config.get("headers") or {})
        timeout = float(config.get("timeout") or self._default_timeout)
        # Send the supplied arguments (or a configured static body) as JSON.
        body = config.get("body") or args
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(method, endpoint, json=body, headers=headers)
        try:
            payload: Any = resp.json()
        except Exception:
            payload = resp.text
        return payload, {
            "http_status": resp.status_code,
            "http_method": method,
            "endpoint": endpoint,
        }

    def _execute_function(
        self, tool: Tool, args: Dict[str, Any], execution_id: str
    ) -> Tuple[Any, Dict[str, Any]]:
        config = tool.config or {}
        fn_name = config.get("function_name") or tool.name
        fn = _BUILTIN_FUNCTIONS.get(fn_name)
        if fn is None:
            raise ToolExecutionError(
                f"no executable implementation registered for function '{fn_name}'"
            )
        return fn(args, config), {"function_name": fn_name}

    def _execute_lead_capture(
        self, tool: Tool, args: Dict[str, Any], execution_id: str
    ) -> Tuple[Any, Dict[str, Any]]:
        lead = {
            "name": args.get("name"),
            "email": args.get("email"),
            "phone": args.get("phone"),
            "message": args.get("message"),
            "source": args.get("source") or tool.name,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "tool_id": str(tool.id) if getattr(tool, "id", None) else None,
        }
        return lead, {"captured": True}

    def _execute_human_escalation(
        self, tool: Tool, args: Dict[str, Any], execution_id: str
    ) -> Tuple[Any, Dict[str, Any]]:
        escalation = {
            "escalated": True,
            "reason": args.get("reason", "User requested human assistance"),
            "priority": args.get("priority", "normal"),
            "conversation_ref": args.get("conversation_ref"),
            "assigned_to": args.get("assigned_to"),
            "escalated_at": datetime.now(timezone.utc).isoformat(),
            "tool_id": str(tool.id) if getattr(tool, "id", None) else None,
        }
        return escalation, {"escalated": True}

    def _execute_custom(
        self, tool: Tool, args: Dict[str, Any], execution_id: str
    ) -> Tuple[Any, Dict[str, Any]]:
        raise ToolExecutionError(
            "custom tools require operator-defined behaviour and cannot be "
            "executed by the generic engine"
        )

    def _execute_unknown(
        self, tool: Tool, args: Dict[str, Any], execution_id: str
    ) -> Tuple[Any, Dict[str, Any]]:
        raise ToolExecutionError(f"unsupported tool_type: {tool.tool_type!r}")

    # --- Helpers ------------------------------------------------------------

    def _error_result(
        self,
        tool: Tool,
        execution_id: str,
        started: datetime,
        args: Dict[str, Any],
        error: str,
        error_type: str,
    ) -> ToolResult:
        return ToolResult(
            execution_id=execution_id,
            success=False,
            tool_id=str(tool.id) if getattr(tool, "id", None) else None,
            tool_name=tool.name,
            tool_type=tool.tool_type,
            arguments=args,
            error=error,
            error_type=error_type,
            started_at=started,
            duration_ms=_elapsed_ms(started),
            meta={},
        )


__all__ = [
    "ToolExecutionEngine",
    "ToolExecutionError",
    "ToolResult",
    "validate_arguments",
]
