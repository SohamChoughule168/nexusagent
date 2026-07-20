"""Analytics dashboards (Milestone B, Step 5).

Aggregated, tenant-scoped analytics over the organization's users, agents,
conversations, messages, and recorded usage events. Every query is filtered by
``organization_id`` (derived from the authenticated principal), so one tenant
can never read another's metrics. Reads are available to any authenticated
member of the organization.

The underlying figures come from the ``usage_events`` table, which is populated
by :func:`app.services.usage.record_event` at tool-execution and RAG-query time,
plus the agent / conversation / message tables.
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth_dependencies import get_tenant_context
from app.core.database import get_db
from app.models.all_models import (
    Agent,
    Conversation,
    Message,
    OrganizationMember,
    UsageEvent,
)
from app.services.tenant_context import TenantContext

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _count(db: Session, org_id, model) -> int:
    stmt = select(func.count()).select_from(model).where(model.organization_id == org_id)
    return db.execute(stmt).scalar() or 0


def _provider_usage(db: Session, org_id) -> List[Dict[str, Any]]:
    """Token / cost / count per (model_provider, model_name)."""
    rows = db.execute(
        select(
            UsageEvent.model_provider,
            UsageEvent.model_name,
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
            func.count(),
        )
        .where(UsageEvent.organization_id == org_id)
        .group_by(UsageEvent.model_provider, UsageEvent.model_name)
    ).all()
    return [
        {
            "model_provider": p or "unknown",
            "model_name": n or "unknown",
            "total_tokens": int(t or 0),
            "cost_usd": round(float(c or 0.0), 6),
            "count": int(cnt or 0),
        }
        for p, n, t, c, cnt in rows
    ]


@router.get("/overview")
def analytics_overview(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """High-level organization analytics: counts, tokens, latency, errors, providers."""
    org_id = tenant.organization_id

    users = _count(db, org_id, OrganizationMember)
    agents = _count(db, org_id, Agent)
    conversations = _count(db, org_id, Conversation)
    messages = _count(db, org_id, Message)

    # Usage aggregates.
    agg = db.execute(
        select(
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
            func.coalesce(func.sum(UsageEvent.cost_usd), 0.0),
            func.coalesce(func.avg(UsageEvent.latency_ms), 0.0),
            func.count(),
        ).where(UsageEvent.organization_id == org_id)
    ).first()
    total_tokens = int(agg[0] or 0)
    total_cost = round(float(agg[1] or 0.0), 6)
    avg_latency = round(float(agg[2] or 0.0), 3)
    usage_total = int(agg[3] or 0)

    status_counts = db.execute(
        select(UsageEvent.status, func.count())
        .where(UsageEvent.organization_id == org_id)
        .group_by(UsageEvent.status)
    ).all()
    success_count = 0
    error_count = 0
    for st, cnt in status_counts:
        if st == "success":
            success_count = int(cnt)
        elif st in ("error", "timeout"):
            error_count += int(cnt)

    # Conversation status breakdown.
    conv_status_rows = db.execute(
        select(Conversation.status, func.count())
        .where(Conversation.organization_id == org_id)
        .group_by(Conversation.status)
    ).all()
    conversation_status = {st or "unknown": int(cnt) for st, cnt in conv_status_rows}

    # Tokens per day over the last 30 days.
    since = datetime.now(timezone.utc) - timedelta(days=30)
    day_rows = db.execute(
        select(
            func.date_trunc("day", UsageEvent.created_at).label("day"),
            func.coalesce(func.sum(UsageEvent.total_tokens), 0),
        )
        .where(
            UsageEvent.organization_id == org_id,
            UsageEvent.created_at >= since,
        )
        .group_by(func.date_trunc("day", UsageEvent.created_at))
        .order_by(func.date_trunc("day", UsageEvent.created_at))
    ).all()
    tokens_by_day = [
        {"date": d.date().isoformat() if d else None, "total_tokens": int(t or 0)}
        for d, t in day_rows
    ]

    return {
        "organization_id": str(org_id),
        "users": users,
        "agents": agents,
        "conversations": conversations,
        "messages": messages,
        "total_tokens": total_tokens,
        "total_cost_usd": total_cost,
        "avg_latency_ms": avg_latency,
        "usage_events": usage_total,
        "success_count": success_count,
        "error_count": error_count,
        "provider_usage": _provider_usage(db, org_id),
        "conversation_status": conversation_status,
        "tokens_by_day": tokens_by_day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/usage")
def analytics_usage(
    days: int = Query(30, ge=1, le=365),
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Usage-event analytics: per event type, status breakdown, latency, providers."""
    org_id = tenant.organization_id
    since = datetime.now(timezone.utc) - timedelta(days=days)

    by_type_rows = db.execute(
        select(UsageEvent.event_type, func.count(), func.coalesce(func.sum(UsageEvent.total_tokens), 0))
        .where(UsageEvent.organization_id == org_id, UsageEvent.created_at >= since)
        .group_by(UsageEvent.event_type)
    ).all()
    by_event_type = [
        {"event_type": et or "unknown", "count": int(c), "total_tokens": int(t or 0)}
        for et, c, t in by_type_rows
    ]

    status_rows = db.execute(
        select(UsageEvent.status, func.count())
        .where(UsageEvent.organization_id == org_id, UsageEvent.created_at >= since)
        .group_by(UsageEvent.status)
    ).all()
    by_status = {st or "unknown": int(c) for st, c in status_rows}

    lat = db.execute(
        select(
            func.coalesce(func.avg(UsageEvent.latency_ms), 0.0),
            func.coalesce(func.min(UsageEvent.latency_ms), 0.0),
            func.coalesce(func.max(UsageEvent.latency_ms), 0.0),
        ).where(UsageEvent.organization_id == org_id, UsageEvent.created_at >= since)
    ).first()
    latency = {
        "avg_ms": round(float(lat[0] or 0.0), 3),
        "min_ms": round(float(lat[1] or 0.0), 3),
        "max_ms": round(float(lat[2] or 0.0), 3),
    }

    return {
        "organization_id": str(org_id),
        "window_days": days,
        "by_event_type": by_event_type,
        "by_status": by_status,
        "latency": latency,
        "provider_usage": _provider_usage(db, org_id),
    }


@router.get("/conversations")
def analytics_conversations(
    tenant: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Conversation analytics: status breakdown, top agents by conversation count."""
    org_id = tenant.organization_id

    total = _count(db, org_id, Conversation)
    status_rows = db.execute(
        select(Conversation.status, func.count())
        .where(Conversation.organization_id == org_id)
        .group_by(Conversation.status)
    ).all()
    by_status = {st or "unknown": int(c) for st, c in status_rows}

    messages = _count(db, org_id, Message)

    # Top agents by conversation volume.
    top_rows = db.execute(
        select(
            Conversation.agent_id,
            func.count(),
        )
        .where(Conversation.organization_id == org_id, Conversation.agent_id.isnot(None))
        .group_by(Conversation.agent_id)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    top_agents = [
        {"agent_id": str(aid), "conversations": int(c)} for aid, c in top_rows if aid
    ]

    return {
        "organization_id": str(org_id),
        "total_conversations": total,
        "total_messages": messages,
        "by_status": by_status,
        "top_agents": top_agents,
    }
