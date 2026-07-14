"""Document Embeddings & RAG Retrieval tests (Milestone 3).

Exercises ``POST /documents/{id}/embed`` (vector storage) and
``GET /knowledge-bases/{id}/search`` (retrieval), reusing the same tenant
isolation + RBAC boundary as the upload/ingest endpoints.

Embeddings use the pluggable provider: offline this is the deterministic
local embedder (no API key), so the pipeline runs end-to-end in tests.
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
from app.services.embeddings import LocalDeterministicEmbedder, cosine_similarity

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
    email = f"emb-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Emb Owner",
            "organization_name": f"Emb Org {uuid.uuid4()}",
            "organization_slug": f"emb-org-{uuid.uuid4()}",
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
    email = f"emb-viewer-{uuid.uuid4()}@example.com"
    user = User(
        email=email,
        password_hash=get_password_hash("TestPass#123"),
        full_name="Emb Viewer",
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


def _ingest_and_embed(client, db_session, token, org_id, doc):
    ing = client.post(f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token))
    assert ing.status_code == 200, ing.text
    emb = client.post(f"{DOC_PREFIX}/{doc.id}/embed", headers=_auth_headers(token))
    assert emb.status_code == 200, emb.text
    return emb


# ---------------------------------------------------------------------------
# Pure-function unit tests
# ---------------------------------------------------------------------------


def test_local_embedder_is_deterministic_and_normalized():
    e = LocalDeterministicEmbedder()
    v1 = e.embed(["the quick brown fox"])[0]
    v2 = e.embed(["the quick brown fox"])[0]
    assert v1 == v2
    assert len(v1) == e.dimensions
    import math

    assert math.isclose(math.sqrt(sum(x * x for x in v1)), 1.0, rel_tol=1e-6)


def test_cosine_similarity_self_is_one():
    e = LocalDeterministicEmbedder()
    v = e.embed(["hello world"])[0]
    assert cosine_similarity(v, v) == 1.0
    assert cosine_similarity(v, []) == 0.0
    assert cosine_similarity(v, [0.0] * len(v)) == 0.0


# ---------------------------------------------------------------------------
# API: embed
# ---------------------------------------------------------------------------


def test_embed_document_fills_chunk_embeddings(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Emb KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())

    emb = _ingest_and_embed(client, db_session, token, org_id, doc)
    body = emb.json()
    assert body["status"] == "indexed"
    assert body["chunk_count"] and body["chunk_count"] > 0
    assert body["embedding_id"] is None  # doc itself has no vector, only chunks
    assert body["metadata"]["embedding"]["provider"] == "LocalDeterministicEmbedder"

    chunks = (
        RepositoryFactory(db_session, org_id)
        .document_chunks()
        .get_by_document(uuid.UUID(str(doc.id)))
    )
    assert len(chunks) == body["chunk_count"]
    for c in chunks:
        assert c.embedding is not None and len(c.embedding) == 256
        assert c.embedding_id

    _cleanup(db_session, org_id, kb_id, [doc.id])


def test_embed_requires_ingest_first_409(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Empty KB {uuid.uuid4()}")
    # Upload a (fake) PDF and ingest -> zero chunks.
    fake = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    up = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("r.pdf", fake, "application/pdf")},
        headers=_auth_headers(token),
    )
    doc_id = up.json()["id"]
    client.post(f"{DOC_PREFIX}/{doc_id}/ingest", headers=_auth_headers(token))

    emb = client.post(f"{DOC_PREFIX}/{doc_id}/embed", headers=_auth_headers(token))
    assert emb.status_code == 409

    _cleanup(db_session, org_id, kb_id, [uuid.UUID(doc_id)])


def test_embed_is_idempotent(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Idem KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())

    _ingest_and_embed(client, db_session, token, org_id, doc)
    second = client.post(
        f"{DOC_PREFIX}/{doc.id}/embed", headers=_auth_headers(token)
    )
    assert second.status_code == 200

    chunks = (
        RepositoryFactory(db_session, org_id)
        .document_chunks()
        .get_by_document(uuid.UUID(str(doc.id)))
    )
    # Re-embedding replaces vectors, not duplicates chunks.
    assert len(chunks) == second.json()["chunk_count"]
    assert all(c.embedding is not None for c in chunks)

    _cleanup(db_session, org_id, kb_id, [doc.id])


def test_embed_invalid_id_400(client, db_session):
    token, org_id = _register(client)
    resp = client.post(
        f"{DOC_PREFIX}/not-a-uuid/embed", headers=_auth_headers(token)
    )
    assert resp.status_code == 400


def test_embed_unknown_document_404(client, db_session):
    token, org_id = _register(client)
    resp = client.post(
        f"{DOC_PREFIX}/{uuid.uuid4()}/embed", headers=_auth_headers(token)
    )
    assert resp.status_code == 404


def test_embed_requires_auth(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Auth KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())
    resp = client.post(f"{DOC_PREFIX}/{doc.id}/embed")
    assert resp.status_code == 401
    _cleanup(db_session, org_id, kb_id, [doc.id])


def test_embed_viewer_cannot_embed(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"RBAC KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())
    # Ingest so the document has chunks; embedding is the operation under test.
    client.post(f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token))
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)

    resp = client.post(
        f"{DOC_PREFIX}/{doc.id}/embed", headers=_auth_headers(viewer_token)
    )
    assert resp.status_code == 403
    # Confirm the document was not embedded by the viewer (owner still can).
    follow = client.post(
        f"{DOC_PREFIX}/{doc.id}/embed", headers=_auth_headers(token)
    )
    assert follow.status_code == 200

    _cleanup(db_session, org_id, kb_id, [doc.id])
    db_session.query(OrganizationMember).filter(
        OrganizationMember.user_id == str(viewer_uid)
    ).delete(synchronize_session=False)
    db_session.query(User).filter(User.id == str(viewer_uid)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_embed_tenant_isolation_blocks_cross_tenant(client, db_session):
    token_a, org_a = _register(client)
    kb_a = _create_kb(client, token_a, f"Tenant A KB {uuid.uuid4()}")
    doc_a = _write_doc_direct(db_session, org_a, kb_a, _TEXT_ONE.encode())
    client.post(f"{DOC_PREFIX}/{doc_a.id}/ingest", headers=_auth_headers(token_a))

    token_b, org_b = _register(client)
    resp = client.post(
        f"{DOC_PREFIX}/{doc_a.id}/embed", headers=_auth_headers(token_b)
    )
    assert resp.status_code == 404

    _cleanup(db_session, org_a, kb_a, [doc_a.id])
    for org in (org_a, org_b):
        db_session.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == str(org)
        ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# API: search / retrieval
# ---------------------------------------------------------------------------


def test_search_returns_relevant_chunks(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Search KB {uuid.uuid4()}")
    doc1 = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())
    doc2 = _write_doc_direct(db_session, org_id, kb_id, _TEXT_TWO.encode())
    _ingest_and_embed(client, db_session, token, org_id, doc1)
    _ingest_and_embed(client, db_session, token, org_id, doc2)

    resp = client.get(
        f"{KB_PREFIX}/{kb_id}/search",
        params={"q": "quantum entanglement qubits", "top_k": 3},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    results = resp.json()
    assert len(results) > 0
    # The top chunk should come from the QUANTUM document.
    assert results[0]["document_id"] == str(doc1.id)
    assert results[0]["score"] > 0
    # Relevance ordering: the quantum doc chunk outscores the bakery one.
    bakery_ids = {str(doc2.id)}
    top_is_quantum = results[0]["document_id"] not in bakery_ids
    assert top_is_quantum

    _cleanup(db_session, org_id, kb_id, [doc1.id, doc2.id])


def test_search_requires_query_400(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Q KB {uuid.uuid4()}")
    resp = client.get(f"{KB_PREFIX}/{kb_id}/search", headers=_auth_headers(token))
    assert resp.status_code == 400
    _cleanup(db_session, org_id, kb_id, [])


def test_search_unknown_kb_404(client, db_session):
    token, org_id = _register(client)
    resp = client.get(
        f"{KB_PREFIX}/{uuid.uuid4()}/search",
        params={"q": "anything"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


def test_search_viewer_can_search(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Read KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _TEXT_ONE.encode())
    _ingest_and_embed(client, db_session, token, org_id, doc)
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)

    resp = client.get(
        f"{KB_PREFIX}/{kb_id}/search",
        params={"q": "quantum"},
        headers=_auth_headers(viewer_token),
    )
    assert resp.status_code == 200

    _cleanup(db_session, org_id, kb_id, [doc.id])
    db_session.query(OrganizationMember).filter(
        OrganizationMember.user_id == str(viewer_uid)
    ).delete(synchronize_session=False)
    db_session.query(User).filter(User.id == str(viewer_uid)).delete(
        synchronize_session=False
    )
    db_session.commit()


def test_search_tenant_isolation_blocks_cross_tenant(client, db_session):
    token_a, org_a = _register(client)
    kb_a = _create_kb(client, token_a, f"Tenant A KB {uuid.uuid4()}")
    doc_a = _write_doc_direct(db_session, org_a, kb_a, _TEXT_ONE.encode())
    _ingest_and_embed(client, db_session, token_a, org_a, doc_a)

    token_b, org_b = _register(client)
    resp = client.get(
        f"{KB_PREFIX}/{kb_a}/search",
        params={"q": "quantum"},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404

    _cleanup(db_session, org_a, kb_a, [doc_a.id])
    for org in (org_a, org_b):
        db_session.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == str(org)
        ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
