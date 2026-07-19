#!/usr/bin/env python3
"""
Seed the NexusAgent *Brightpath* demo workspace.

Creates a self-contained demo organization so prospects can explore a real,
grounded agent without affecting production data:

    - Organization "Brightpath (Demo)"  (slug: brightpath-demo)
    - Owner user  (demo@nexusagent.dev / see DEMO_USER_PASSWORD below)
    - Knowledge base "Brightpath Help Center"
    - 4 demo PDFs ingested + embedded (local deterministic embedder offline)
    - Agent "Aria - Brightpath Support" grounded in the help center
    - 3 sample conversations with cited answers
    - A demo API key (printed once)

Idempotent: re-running is a no-op if the demo user already exists.

Usage:
    # local dev (creates tables from models):
    python backend/scripts/seed_demo.py --init-db
    # against a migrated database (docker-compose / AWS):
    python backend/scripts/seed_demo.py

Requires the backend package on the path (pip install -e .) and a reachable
PostgreSQL instance configured via DATABASE_URL / .env.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# Make the backend package importable regardless of CWD.
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.database import get_sessionmaker, init_db  # noqa: E402
from app.core.security import (  # noqa: E402
    get_password_hash,
    generate_api_key,
    hash_api_key,
)
from app.models.organization import Organization  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.all_models import (  # noqa: E402
    Agent,
    APIKey,
    Conversation,
    Document,
    DocumentChunk,
    KnowledgeBase,
    Message,
    OrganizationMember,
)
from app.services.embeddings import get_embedding_provider  # noqa: E402
from app.services.ingestion import ingest_document  # noqa: E402
from app.services.tenant_context import TenantContext  # noqa: E402

# ---------------------------------------------------------------------------
# Demo configuration (override via environment)
# ---------------------------------------------------------------------------
DEMO_ORG_NAME = os.getenv("DEMO_ORG_NAME", "Brightpath (Demo)")
DEMO_ORG_SLUG = os.getenv("DEMO_ORG_SLUG", "brightpath-demo")
DEMO_USER_EMAIL = os.getenv("DEMO_USER_EMAIL", "demo@nexusagent.dev")
DEMO_USER_PASSWORD = os.getenv("DEMO_USER_PASSWORD", "nexusagent-demo")
DEMO_USER_NAME = os.getenv("DEMO_USER_NAME", "Demo Admin")
DEMO_KB_NAME = os.getenv("DEMO_KB_NAME", "Brightpath Help Center")
DEMO_AGENT_NAME = os.getenv("DEMO_AGENT_NAME", "Aria - Brightpath Support")

PDF_DIR = Path(__file__).resolve().parents[2] / "demo" / "assets" / "pdfs"

SYSTEM_PROMPT = (
    "You are Aria, the friendly and knowledgeable support agent for Brightpath, "
    "a project management workspace where teams plan, track, and ship work.\n\n"
    "Answer using ONLY the Brightpath Help Center knowledge base. Cite the "
    "specific help article or section you used. If the answer is not in the "
    "knowledge base, say so honestly and offer to connect the user with the "
    "Brightpath team - do not invent features, prices, or policies.\n\n"
    "Be concise and concrete. Use short steps or bullets when explaining how to "
    "do something. Keep a warm, professional tone."
)

WELCOME_MESSAGE = (
    "Hi! I'm Aria, the Brightpath support assistant. Ask me anything about "
    "setting up your workspace, inviting your team, pricing, or security - I'll "
    "answer from the Brightpath Help Center."
)

SAMPLE_CONVERSATIONS = [
    {
        "title": "Inviting the team",
        "user": "How do I invite my team to our Brightpath workspace?",
        "assistant": (
            "You can invite teammates from Settings -> Members. Click Invite "
            "people, enter their email addresses, pick a role for each (Admin, "
            "Member, or Viewer), and send the invites. Invited people get an "
            "email with a link and show up in the member list once they accept.\n\n"
            "A few notes:\n"
            "- Viewers can read boards and docs but can't edit them.\n"
            "- If your plan includes SSO, members can also join through your "
            "identity provider.\n"
            "- Owners can set a default role so everyone from your domain starts "
            "with the right permissions."
        ),
        "pdf": "brightpath-getting-started.pdf",
    },
    {
        "title": "Pricing questions",
        "user": "What does Brightpath cost?",
        "assistant": (
            "Brightpath is priced per seat, per month. Free covers up to 3 members "
            "and 2 boards. Team is $8/seat and adds unlimited boards, automations, "
            "and integrations. Business is $15/seat and adds Insights dashboards, "
            "advanced permissions, and audit-log export. Enterprise is custom and "
            "includes SSO/SAML, SCIM provisioning, and a support SLA.\n\n"
            "You can change plans anytime (changes prorate), and you can export all "
            "workspace data whenever you like - there's no lock-in."
        ),
        "pdf": "brightpath-pricing.pdf",
    },
    {
        "title": "Security & SSO",
        "user": "Do you support single sign-on?",
        "assistant": (
            "Yes. SSO with SAML and SCIM user provisioning is available on "
            "Enterprise plans. Once enabled, members sign in through your identity "
            "provider instead of email invites, and their access is revoked "
            "automatically when they leave your directory.\n\n"
            "On the data side, every workspace is isolated from every other "
            "workspace, backups run daily, and Enterprise customers can request "
            "region pinning."
        ),
        "pdf": "brightpath-faq.pdf",
    },
]


def log(msg: str) -> None:
    print(f"[seed-demo] {msg}")


def write_pdf_to_storage(org_id: uuid.UUID, kb_id: uuid.UUID, filename: str, content: bytes) -> str:
    root = Path(settings.UPLOAD_STORAGE_DIR)
    token = uuid.uuid4()
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    storage_path = root / str(org_id) / str(kb_id) / f"{token}__{safe}"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)
    return str(storage_path)


def embed_document(db, doc, kb):
    """Embed a document's chunks using the KB's embedding provider."""
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == doc.id)
        .order_by(DocumentChunk.chunk_index)
        .all()
    )
    if not chunks:
        return
    provider = get_embedding_provider(kb, settings)
    vectors = provider.embed([c.content for c in chunks])
    for chunk, vector in zip(chunks, vectors):
        chunk.embedding = vector
        chunk.embedding_id = str(uuid.uuid4())
        db.add(chunk)
    doc.status = "indexed"
    db.add(doc)
    db.commit()
    log(f"  embedded {len(chunks)} chunks ({type(provider).__name__})")


def seed(db) -> None:
    # Idempotency: bail if the demo user already exists.
    existing = db.query(User).filter(User.email == DEMO_USER_EMAIL).first()
    if existing:
        log(f"Demo user {DEMO_USER_EMAIL} already exists - skipping (delete it to reseed).")
        return

    # Organization + owner user + membership.
    org = Organization(name=DEMO_ORG_NAME, slug=DEMO_ORG_SLUG, plan="enterprise")
    db.add(org)
    db.flush()

    user = User(
        email=DEMO_USER_EMAIL,
        password_hash=get_password_hash(DEMO_USER_PASSWORD),
        full_name=DEMO_USER_NAME,
        email_verified=True,
    )
    db.add(user)
    db.flush()

    db.add(
        OrganizationMember(
            organization_id=str(org.id),
            user_id=str(user.id),
            role="owner",
        )
    )
    db.flush()
    log(f"Created organization '{org.name}' (slug={org.slug}) and owner {user.email}")

    tenant = TenantContext(organization_id=org.id, user_id=user.id, role="owner")

    # Knowledge base. The model takes its fields via the JSON ``data`` dict
    # (the same shape the REST API uses), so pass them that way.
    kb = KnowledgeBase(
        organization_id=str(org.id),
        data={
            "name": DEMO_KB_NAME,
            "description": "Public help center for the Brightpath demo workspace.",
            "chunk_size": 1000,
            "chunk_overlap": 200,
            "chunk_strategy": "recursive",
        },
    )
    db.add(kb)
    db.flush()
    log(f"Created knowledge base '{kb.name}'")

    # Upload + ingest + embed each demo PDF.
    docs_by_file: dict[str, Document] = {}
    for pdf_path in sorted(PDF_DIR.glob("*.pdf")):
        content = pdf_path.read_bytes()
        storage_path = write_pdf_to_storage(org.id, kb.id, pdf_path.name, content)
        doc = Document(
            organization_id=org.id,
            data={
                "knowledge_base_id": str(kb.id),
                "filename": pdf_path.name,
                "original_filename": pdf_path.name,
                "title": pdf_path.name.replace(".pdf", "").replace("-", " ").title(),
                "mime_type": "application/pdf",
                "file_size": len(content),
                "storage_path": storage_path,
                "status": "uploaded",
                "upload_member_id": str(user.id),
                "metadata": {"storage_token": str(uuid.uuid4())},
            },
        )
        db.add(doc)
        db.flush()
        ingest_document(db, tenant, doc, kb)
        db.commit()
        embed_document(db, doc, kb)
        docs_by_file[pdf_path.name] = doc
        log(f"  ingested + embedded {pdf_path.name}")

    # Agent grounded in the help center.
    agent = Agent(
        organization_id=str(org.id),
        data={
            "name": DEMO_AGENT_NAME,
            "description": "Support agent for the Brightpath demo workspace, grounded in the Brightpath Help Center.",
            "system_prompt": SYSTEM_PROMPT,
            "welcome_message": WELCOME_MESSAGE,
            "model_provider": "openrouter",
            "model_name": "anthropic/claude-3.5-sonnet",
            "temperature": 0.4,
            "status": "active",
            "public_id": "aria",
            "knowledge_base_ids": [str(kb.id)],
            "config": {"model_name": "anthropic/claude-3.5-sonnet", "temperature": 0.4},
        },
    )
    agent.id = uuid.uuid4()
    db.add(agent)
    db.flush()
    log(f"Created agent '{DEMO_AGENT_NAME}' (public_id=aria)")

    # Sample conversations with cited answers.
    for sample in SAMPLE_CONVERSATIONS:
        doc = docs_by_file.get(sample["pdf"])
        snippet = ""
        chunk_id = None
        if doc:
            chunk = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc.id)
                .order_by(DocumentChunk.chunk_index)
                .first()
            )
            if chunk:
                chunk_id = str(chunk.id)
                snippet = (chunk.content or "")[:300]

        conv = Conversation(
            organization_id=org.id,
            agent_id=agent.id,
            session_id=str(uuid.uuid4()),
            user_identifier="demo-visitor@brightpath.example",
            status="active",
        )
        conv.id = uuid.uuid4()
        db.add(conv)
        db.flush()

        # Set ``id`` explicitly (as the REST API does). A Python-side
        # ``default=uuid.uuid4()`` is evaluated once per flush batch, so two
        # messages committed together would otherwise collide on the PK.
        user_msg = Message(
            conversation_id=str(conv.id),
            organization_id=str(org.id),
            role="user",
            content=sample["user"],
            token_count=len(sample["user"].split()),
        )
        user_msg.id = uuid.uuid4()
        db.add(user_msg)

        assistant_msg = Message(
            conversation_id=str(conv.id),
            organization_id=str(org.id),
            role="assistant",
            content=sample["assistant"],
            token_count=len(sample["assistant"].split()),
            citations={"sources": [{"chunk_id": chunk_id, "document_id": str(doc.id) if doc else None, "score": 0.92, "snippet": snippet}]},
            model_provider="openrouter",
            model_name="anthropic/claude-3.5-sonnet",
        )
        assistant_msg.id = uuid.uuid4()
        db.add(assistant_msg)
        db.commit()
        log(f"  created sample conversation: {sample['title']}")

    # Demo API key (printed once). The ``APIKey`` model has no ``user_id``
    # column (matching the REST API and the migration); scope by organization.
    plain_key = generate_api_key()
    api_key = APIKey(
        organization_id=org.id,
        name="Demo workspace key",
        key_hash=hash_api_key(plain_key),
        key_prefix=plain_key[:8],
        scopes={"chat": True, "read": True},
    )
    db.add(api_key)
    db.commit()

    log("Seed complete.")
    print("\n" + "=" * 60)
    print("DEMO WORKSPACE CREDENTIALS")
    print("=" * 60)
    print(f"  Email:    {DEMO_USER_EMAIL}")
    print(f"  Password: {DEMO_USER_PASSWORD}")
    print(f"  Agent:    {DEMO_AGENT_NAME} (public_id=aria)")
    print(f"  API key:  {plain_key}")
    print("=" * 60 + "\n")


def main() -> None:
    if "--init-db" in sys.argv:
        log("Creating tables from models (--init-db)...")
        init_db()

    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        seed(db)
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
