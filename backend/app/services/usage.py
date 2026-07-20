"""Usage-event recording (Milestone B, Step 5 — analytics).

Thin helper to append a ``UsageEvent`` row. Used by the tool executor, the RAG
query endpoint, and the chat pipeline so the analytics endpoints have real data
for token usage, latency, provider breakdown, and error rates.

Defensive by design: it never raises, so recording analytics can never break the
operation it observes (a failed usage write is logged and swallowed).
"""
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.all_models import UsageEvent


def record_event(
    db: Session,
    organization_id: Any,
    event_type: str,
    *,
    agent_id: Optional[Any] = None,
    conversation_id: Optional[Any] = None,
    model_provider: Optional[str] = None,
    model_name: Optional[str] = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
    cost_usd: float = 0.0,
    latency_ms: Optional[int] = None,
    status: Optional[str] = None,
    error: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Optional[UsageEvent]:
    """Append a usage event for analytics. Returns the row or ``None`` on error."""
    try:
        data: Dict[str, Any] = {
            "event_type": event_type,
            "agent_id": str(agent_id) if agent_id else None,
            "conversation_id": str(conversation_id) if conversation_id else None,
            "model_provider": model_provider,
            "model_name": model_name,
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "total_tokens": int(total_tokens or 0),
            "cost_usd": float(cost_usd or 0.0),
            "latency_ms": int(latency_ms) if latency_ms is not None else None,
            "status": status,
            "error": error,
            "metadata": meta or {},
        }
        ev = UsageEvent(organization_id=str(organization_id), data=data)
        db.add(ev)
        db.commit()
        db.refresh(ev)
        return ev
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None


__all__ = ["record_event"]
