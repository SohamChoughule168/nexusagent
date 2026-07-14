"""Conversational RAG Chat tests (Milestone 3).

Exercises ``POST /conversations/{id}/chat`` (retrieve -> grounded, streamed
answer -> persist user + assistant messages with citations). Reuses the same
tenant isolation boundary as the conversation endpoints. Offline this uses the
deterministic local answer composer.
"""
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.database import get_sessionmaker as SessionLocal
from app.models.all_models import Agent, Conversation, Document, DocumentChunk, KnowledgeBase, Message
from app.models.user import User
from app.models.all_models import OrganizationMember
from app.repositories.tenant_repository import RepositoryFactory

CONV_PREFIX = "/api/v1/conversations"
KB_PREFIX = "/api/v1/knowledge-bases"
DOC_PREFIX = "/api/v1/documents"
AUTH_PREFIX = "/api/v1/auth"

_TEXT_QUANTUM = (
    "QUANTUM computing exploits superposition and entanglement. "
    "Quantum algorithms can solve certain problems exponentially faster "
    "than classical computers. A quantum processor manipulates qubits."
)
_TEXT_BAKERY = (
    "BAKERY produces fresh bread and pastries every morning. "
    "A baker kneads dough and bakes loaves in a hot stone oven."
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db_session():
    db = SessionLocal()()
    try:
        yield db
    finally:
        db.close()


def _register(client: TestClient):
    email = f"chat-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Chat Owner",
            "organization_name": f"Chat Org {uuid.uuid4()}",
            "organization_slug": f"chat-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_agent(db_session, org_id):
    """Create a real agent in the org (mirrors test_conversation_api fixture)."""
    agent = Agent(
        organization_id=org_id,
        data={
            "name": "Chat Agent",
            "system_prompt": "You are a helpful assistant.",
            "public_id": f"chat-agent-{uuid.uuid4()}",
        },
    )
    agent.id = uuid.uuid4()
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


def _create_kb(client, token, name):
    response = client.post(
        f"{KB_PREFIX}/", json={"name": name}, headers=_auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _write_doc_direct(db_session, org_id, kb_id, content: bytes, filename="n.txt"):
    storage_path = (
        Path(settings.UPLOAD_STORAGE_DIR)
        / str(org_id)
        / str(kb_id)
        / f"{uuid.uuid4()}__{filename}"
    )
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(content)
    doc = Document(
        organization_id=str(org_id),
        data={
            "knowledge_base_id": str(kb_id),
            "filename": filename,
            "original_filename": filename,
            "title": filename,
            "mime_type": "text/plain",
            "file_size": len(content),
            "storage_path": str(storage_path),
            "status": "uploaded",
            "upload_member_id": str(uuid.uuid4()),
        },
    )
    return RepositoryFactory(db_session, org_id).documents().create(doc)


def _ingest_embed(client, token, doc_id):
    ing = client.post(f"{DOC_PREFIX}/{doc_id}/ingest", headers=_auth_headers(token))
    assert ing.status_code == 200, ing.text
    emb = client.post(f"{DOC_PREFIX}/{doc_id}/embed", headers=_auth_headers(token))
    assert emb.status_code == 200, emb.text


def _create_conversation(client, token, agent_id):
    resp = client.post(
        f"{CONV_PREFIX}/",
        json={"agent_id": str(agent_id), "session_id": f"session-{uuid.uuid4()}"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _cleanup(db_session, org_id, agent_id=None, kb_ids=None, doc_ids=None, conv_ids=None):
    for did in doc_ids or []:
        db_session.query(DocumentChunk).filter(
            DocumentChunk.document_id == str(did)
        ).delete(synchronize_session=False)
        db_session.query(Document).filter(Document.id == str(did)).delete(
            synchronize_session=False
        )
    for cid in conv_ids or []:
        db_session.query(Message).filter(Message.conversation_id == str(cid)).delete(
            synchronize_session=False
        )
        db_session.query(Conversation).filter(Conversation.id == str(cid)).delete(
            synchronize_session=False
        )
    for kid in kb_ids or []:
        db_session.query(KnowledgeBase).filter(KnowledgeBase.id == str(kid)).delete(
            synchronize_session=False
        )
    if agent_id:
        db_session.query(Agent).filter(Agent.id == str(agent_id)).delete(
            synchronize_session=False
        )
    db_session.commit()


# ---------------------------------------------------------------------------
# API: chat
# ---------------------------------------------------------------------------


def test_chat_streams_answer_and_persists(client, db_session):
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    kb_id = _create_kb(client, token, f"Chat KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_QUANTUM.encode())
    _ingest_embed(client, token, doc.id)
    conv_id = _create_conversation(client, token, agent.id)

    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/chat",
        json={"message": "what is quantum entanglement?", "top_k": 3},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    answer = resp.text
    assert answer and "quantum" in answer.lower()

    # Both messages persisted: user + assistant with citations.
    msgs = client.get(
        f"{CONV_PREFIX}/{conv_id}/messages", headers=_auth_headers(token)
    ).json()
    assert len(msgs) == 2
    roles = {m["role"] for m in msgs}
    assert roles == {"user", "assistant"}
    assistant = next(m for m in msgs if m["role"] == "assistant")
    assert assistant["citations"]
    assert assistant["citations"]["sources"]
    assert assistant["citations"]["sources"][0]["document_id"] == str(doc.id)

    _cleanup(db_session, org_id, agent.id, [kb_id], [doc.id], [conv_id])


def test_chat_scoped_to_knowledge_base(client, db_session):
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    kb_q = _create_kb(client, token, f"Q KB {uuid.uuid4()}")
    kb_b = _create_kb(client, token, f"B KB {uuid.uuid4()}")
    doc_q = _write_doc_direct(db_session, org_id, kb_q, _TEXT_QUANTUM.encode())
    doc_b = _write_doc_direct(db_session, org_id, kb_b, _TEXT_BAKERY.encode())
    _ingest_embed(client, token, doc_q.id)
    _ingest_embed(client, token, doc_b.id)
    conv_id = _create_conversation(client, token, agent.id)

    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/chat",
        json={
            "message": "quantum entanglement",
            "top_k": 3,
            "knowledge_base_ids": [kb_q],
        },
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text

    msgs = client.get(
        f"{CONV_PREFIX}/{conv_id}/messages", headers=_auth_headers(token)
    ).json()
    assistant = next(m for m in msgs if m["role"] == "assistant")
    source_doc_ids = {s["document_id"] for s in assistant["citations"]["sources"]}
    # Only the quantum KB was searched, so sources come from doc_q.
    assert str(doc_q.id) in source_doc_ids
    assert str(doc_b.id) not in source_doc_ids

    _cleanup(
        db_session, org_id, agent.id, [kb_q, kb_b], [doc_q.id, doc_b.id], [conv_id]
    )


def test_chat_requires_auth(client, db_session):
    token, org_id = _register(client)
    agent = _create_agent(db_session, org_id)
    conv_id = _create_conversation(client, token, agent.id)
    resp = client.post(
        f"{CONV_PREFIX}/{conv_id}/chat", json={"message": "hi"}
    )
    assert resp.status_code == 401
    _cleanup(db_session, org_id, agent.id, conv_ids=[conv_id])


def test_chat_unknown_conversation_404(client, db_session):
    token, org_id = _register(client)
    resp = client.post(
        f"{CONV_PREFIX}/{uuid.uuid4()}/chat",
        json={"message": "hi"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


def test_chat_tenant_isolation_blocks_cross_tenant(client, db_session):
    token_a, org_a = _register(client)
    agent_a = _create_agent(db_session, org_a)
    kb_a = _create_kb(client, token_a, f"Tenant A KB {uuid.uuid4()}")
    doc_a = _write_doc_direct(db_session, org_a, kb_a, _TEXT_QUANTUM.encode())
    _ingest_embed(client, token_a, doc_a.id)
    conv_a = _create_conversation(client, token_a, agent_a.id)

    token_b, org_b = _register(client)
    resp = client.post(
        f"{CONV_PREFIX}/{conv_a}/chat",
        json={"message": "quantum"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404

    _cleanup(db_session, org_a, agent_a.id, [kb_a], [doc_a.id], [conv_a])
    for org in (org_a, org_b):
        db_session.query(OrganizationMember).filter(
            OrganizationMember.organization_id == str(org)
        ).delete(synchronize_session=False)
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.organization_id == str(org_b)
    ).delete(synchronize_session=False)
    db_session.commit()
