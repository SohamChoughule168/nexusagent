"""RAG Query tests (Milestone 3).

Exercises ``POST /knowledge-bases/{id}/query`` (retrieve -> grounded answer),
reusing the same tenant isolation + RBAC boundary as the other document
endpoints. Offline this uses the deterministic local answer composer.
"""
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.config import settings
from app.core.database import get_sessionmaker as SessionLocal
from app.core.security import create_access_token, get_password_hash
from app.models.all_models import Document, DocumentChunk, KnowledgeBase
from app.models.user import User
from app.models.all_models import OrganizationMember
from app.repositories.tenant_repository import RepositoryFactory

DOC_PREFIX = "/api/v1/documents"
KB_PREFIX = "/api/v1/knowledge-bases"
AUTH_PREFIX = "/api/v1/auth"

_TEXT_ONE = (
    "QUANTUM computing exploits superposition and entanglement. "
    "Quantum algorithms can solve certain problems exponentially faster "
    "than classical computers. A quantum processor manipulates qubits."
)
_TEXT_TWO = (
    "BAKERY produces fresh bread and pastries every morning. "
    "A baker kneads dough and bakes loaves in a hot stone oven. "
    "Pastries are made with butter, flour, sugar and eggs."
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
    email = f"rag-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Rag Owner",
            "organization_name": f"Rag Org {uuid.uuid4()}",
            "organization_slug": f"rag-org-{uuid.uuid4()}",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return body["access_token"], body["user"]["organization_id"]


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _create_kb(client, token, name):
    response = client.post(
        f"{KB_PREFIX}/", json={"name": name}, headers=_auth_headers(token)
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _make_viewer(db_session, org_id):
    email = f"rag-viewer-{uuid.uuid4()}@example.com"
    user = User(
        email=email,
        password_hash=get_password_hash("TestPass#123"),
        full_name="Rag Viewer",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    member = OrganizationMember(
        organization_id=str(org_id), user_id=str(user.id), role="viewer"
    )
    db_session.add(member)
    db_session.commit()
    token = create_access_token(user.id, org_id)
    return token, user.id


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


def _ingest_embed(client, db_session, token, org_id, doc):
    ing = client.post(f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token))
    assert ing.status_code == 200, ing.text
    emb = client.post(f"{DOC_PREFIX}/{doc.id}/embed", headers=_auth_headers(token))
    assert emb.status_code == 200, emb.text


def _cleanup(db_session, org_id, kb_id, doc_ids):
    for did in doc_ids:
        db_session.query(DocumentChunk).filter(
            DocumentChunk.document_id == str(did)
        ).delete(synchronize_session=False)
        db_session.query(Document).filter(Document.id == str(did)).delete(
            synchronize_session=False
        )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# API: query
# ---------------------------------------------------------------------------


def test_query_returns_grounded_answer_and_sources(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Q KB {uuid.uuid4()}")
    doc1 = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())
    doc2 = _write_doc_direct(db_session, org_id, kb_id, _TEXT_TWO.encode())
    _ingest_embed(client, db_session, token, org_id, doc1)
    _ingest_embed(client, db_session, token, org_id, doc2)

    resp = client.post(
        f"{KB_PREFIX}/{kb_id}/query",
        json={"question": "quantum entanglement qubits", "top_k": 3},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["answer"]
    assert len(body["sources"]) > 0
    # Top source should be the QUANTUM document.
    assert body["sources"][0]["document_id"] == str(doc1.id)
    assert body["sources"][0]["score"] > 0
    assert "quantum" in body["answer"].lower() or body["sources"]

    _cleanup(db_session, org_id, kb_id, [doc1.id, doc2.id])


def test_query_blank_question_400(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Blank KB {uuid.uuid4()}")
    resp = client.post(
        f"{KB_PREFIX}/{kb_id}/query",
        json={"question": "   "},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 400
    _cleanup(db_session, org_id, kb_id, [])


def test_query_unknown_kb_404(client, db_session):
    token, org_id = _register(client)
    resp = client.post(
        f"{KB_PREFIX}/{uuid.uuid4()}/query",
        json={"question": "anything"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


def test_query_viewer_can_query(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Read KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())
    _ingest_embed(client, db_session, token, org_id, doc)
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)

    resp = client.post(
        f"{KB_PREFIX}/{kb_id}/query",
        json={"question": "quantum"},
        headers=_auth_headers(viewer_token),
    )
    assert resp.status_code == 200
    assert resp.json()["sources"]

    _cleanup(db_session, org_id, kb_id, [doc.id])
    db_session.query(OrganizationMember).filter(
        OrganizationMember.user_id == str(viewer_uid)
    ).delete(synchronize_session=False)
    db_session.query(User).filter(User.id == str(viewer_uid)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_query_tenant_isolation_blocks_cross_tenant(client, db_session):
    token_a, org_a = _register(client)
    kb_a = _create_kb(client, token_a, f"Tenant A KB {uuid.uuid4()}")
    doc_a = _write_doc_direct(db_session, org_a, kb_a, _TEXT_ONE.encode())
    _ingest_embed(client, db_session, token_a, org_a, doc_a)

    token_b, org_b = _register(client)
    resp = client.post(
        f"{KB_PREFIX}/{kb_a}/query",
        json={"question": "quantum"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404

    _cleanup(db_session, org_a, kb_a, [doc_a.id])
    for org in (org_a, org_b):
        db_session.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == str(org)
        ).delete(synchronize_session=False)
    db_session.commit()
