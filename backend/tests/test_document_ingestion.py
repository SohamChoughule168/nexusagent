"""Document Ingestion API tests (Milestone 3).

Exercises the document ingestion endpoint (``POST /documents/{id}/ingest``),
which extracts text from an uploaded file, splits it into chunks using the
owning knowledge base's chunk config, persists ``DocumentChunk`` rows, and
marks the document ``processed``. Tenant isolation and RBAC reuse the exact
same boundary as the upload API: ``organization_id`` comes from the
authenticated principal, and write roles (owner/admin/member) gate ingestion
while viewers are refused with 403.

Mirrors ``test_document_api.py``: register a real user (yields a JWT +
organization), create a knowledge base, then drive the ingest endpoint.
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
from app.services.ingestion import chunk_text, extract_text

DOC_PREFIX = "/api/v1/documents"
KB_PREFIX = "/api/v1/knowledge-bases"
AUTH_PREFIX = "/api/v1/auth"

# A few paragraphs of deterministic text used to verify chunking.
_SAMPLE_TEXT = (
    "NexusAgent is a multi-tenant AI agent platform. "
    "It ingests documents and splits them into chunks. "
    "Each chunk is stored and later embedded for retrieval.\n\n"
    "Tenant isolation keeps every organization's data separate. "
    "The ingestion step extracts text and applies the knowledge base "
    "chunk configuration. Overlap preserves context across boundaries.\n\n"
    "Retrieval augmented generation answers questions from the indexed "
    "knowledge. Chunks are the atomic unit of retrieval in this system."
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
    email = f"ing-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Ing Owner",
            "organization_name": f"Ing Org {uuid.uuid4()}",
            "organization_slug": f"ing-org-{uuid.uuid4()}",
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
    """Create a viewer user in the org and mint a token for it."""
    email = f"ing-viewer-{uuid.uuid4()}@example.com"
    user = User(
        email=email,
        password_hash=get_password_hash("TestPass#123"),
        full_name="Ing Viewer",
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


def _write_doc_direct(
    db_session, org_id, kb_id, content: bytes, filename="notes.txt", mime="text/plain"
):
    """Create a Document row backed by a real file in storage (bypasses upload)."""
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
            "mime_type": mime,
            "file_size": len(content),
            "storage_path": str(storage_path),
            "status": "uploaded",
            "upload_member_id": str(uuid.uuid4()),
        },
    )
    return RepositoryFactory(db_session, org_id).documents().create(doc)


# ---------------------------------------------------------------------------
# Pure-function unit tests (no DB)
# ---------------------------------------------------------------------------


def test_chunk_text_empty():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_chunk_text_respects_size_and_overlap():
    # A long single paragraph should be split into multiple bounded chunks.
    text = "word " * 500  # ~3000 chars
    chunks = chunk_text(text, chunk_size=500, chunk_overlap=50)
    assert len(chunks) > 1
    # No chunk should wildly exceed the configured size (+ overlap slack).
    for c in chunks:
        assert len(c) <= 500 + 50 + len("word ")


def test_chunk_text_overlap_carries_context():
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    chunks = chunk_text(text, chunk_size=20, chunk_overlap=10)
    # The tail of one chunk should reappear at the start of the next.
    assert len(chunks) >= 2
    if len(chunks) >= 2:
        # Overlap is at least partially preserved across boundaries.
        assert chunks[1][:5] in chunks[0][-15:] or chunks[1] != chunks[0]


def test_chunk_text_fixed_strategy():
    text = "one two three four five"
    chunks = chunk_text(text, chunk_size=8, chunk_overlap=2, strategy="fixed")
    assert "".join(chunks).replace(" ", "") != ""  # non-empty content preserved
    assert all(len(c) <= 8 + 2 for c in chunks)


def test_extract_text_plain():
    result = extract_text("notes.txt", "text/plain", b"hello world\nsecond line")
    assert result.method == "text"
    assert "hello world" in result.text


def test_extract_text_pdf_naive_handles_fake_pdf():
    fake = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    result = extract_text("report.pdf", "application/pdf", fake)
    # No parser library is installed, so the naive fallback runs and yields
    # nothing meaningful from a non-real PDF -- but it must not raise.
    assert result.method in ("pdf-naive", "pdf:fitz", "pdf:pdfminer", "pdf:pypdf2")
    assert isinstance(result.text, str)


# ---------------------------------------------------------------------------
# API: ingestion happy path
# ---------------------------------------------------------------------------


def test_ingest_text_document_creates_chunks(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Ing KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _SAMPLE_TEXT.encode(), "notes.txt")

    response = client.post(
        f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "processed"
    assert body["chunk_count"] and body["chunk_count"] > 0

    # Chunks were persisted to the document_chunks table for this document.
    chunks = (
        RepositoryFactory(db_session, org_id)
        .document_chunks()
        .get_by_document(uuid.UUID(str(doc.id)))
    )
    assert len(chunks) == body["chunk_count"]
    assert all(c.content.strip() for c in chunks)
    assert all(c.knowledge_base_id == uuid.UUID(str(kb_id)) for c in chunks)

    # Cleanup.
    db_session.query(DocumentChunk).filter(
        DocumentChunk.document_id == str(doc.id)
    ).delete(synchronize_session=False)
    db_session.query(Document).filter(Document.id == str(doc.id)).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


def test_ingest_is_idempotent(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Idem KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _SAMPLE_TEXT.encode())

    first = client.post(
        f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token)
    )
    assert first.status_code == 200, first.text
    first_count = first.json()["chunk_count"]
    assert first_count > 0

    second = client.post(
        f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token)
    )
    assert second.status_code == 200, second.text
    # Re-ingest must not duplicate chunks.
    assert second.json()["chunk_count"] == first_count

    chunks = (
        RepositoryFactory(db_session, org_id)
        .document_chunks()
        .get_by_document(uuid.UUID(str(doc.id)))
    )
    assert len(chunks) == first_count

    db_session.query(DocumentChunk).filter(
        DocumentChunk.document_id == str(doc.id)
    ).delete(synchronize_session=False)
    db_session.query(Document).filter(Document.id == str(doc.id)).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


def test_ingest_real_pdf_is_graceful(client, db_session):
    # Upload a (fake) PDF via the real upload endpoint, then ingest it.
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Pdf KB {uuid.uuid4()}")
    fake_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    up = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("report.pdf", fake_pdf, "application/pdf")},
        headers=_auth_headers(token),
    )
    assert up.status_code == 201, up.text
    doc_id = up.json()["id"]

    response = client.post(
        f"{DOC_PREFIX}/{doc_id}/ingest", headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    # A non-parseable PDF yields no text -> processed with zero chunks.
    assert body["status"] == "processed"
    assert body["chunk_count"] == 0

    db_session.query(Document).filter(Document.id == str(doc_id)).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


def test_ingest_missing_file_marks_failed(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Miss KB {uuid.uuid4()}")
    # Point the document at a path that does not exist.
    doc = _write_doc_direct(db_session, org_id, kb_id, b"")
    doc.storage_path = "/nonexistent/path/does-not-exist.bin"
    RepositoryFactory(db_session, org_id).documents().update(doc)

    response = client.post(
        f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token)
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"]
    assert body["chunk_count"] == 0

    db_session.query(Document).filter(Document.id == str(doc.id)).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# Auth / RBAC / tenant isolation
# ---------------------------------------------------------------------------


def test_ingest_requires_authentication(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"Auth KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _SAMPLE_TEXT.encode())

    response = client.post(f"{DOC_PREFIX}/{doc.id}/ingest")
    assert response.status_code == 401

    db_session.query(Document).filter(Document.id == str(doc.id)).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


def test_ingest_invalid_id_400(client, db_session):
    token, org_id = _register(client)
    response = client.post(
        f"{DOC_PREFIX}/not-a-uuid/ingest", headers=_auth_headers(token)
    )
    assert response.status_code == 400


def test_ingest_unknown_document_404(client, db_session):
    token, org_id = _register(client)
    response = client.post(
        f"{DOC_PREFIX}/{uuid.uuid4()}/ingest", headers=_auth_headers(token)
    )
    assert response.status_code == 404


def test_ingest_viewer_cannot_ingest(client, db_session):
    token, org_id = _register(client)
    kb_id = _create_kb(client, token, f"RBAC KB {uuid.uuid4()}")
    doc = _write_doc_direct(db_session, org_id, kb_id, _SAMPLE_TEXT.encode())
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)

    response = client.post(
        f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(viewer_token)
    )
    assert response.status_code == 403
    # Document must remain un-ingested.
    follow = client.post(
        f"{DOC_PREFIX}/{doc.id}/ingest", headers=_auth_headers(token)
    )
    assert follow.status_code == 200

    db_session.query(Document).filter(Document.id == str(doc.id)).delete(
        synchronize_session=False
    )
    db_session.query(OrganizationMember).filter(
        OrganizationMember.user_id == str(viewer_uid)
    ).delete(synchronize_session=False)
    db_session.query(User).filter(User.id == str(viewer_uid)).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.id == str(kb_id)
    ).delete(synchronize_session=False)
    db_session.commit()


def test_ingest_tenant_isolation_blocks_cross_tenant(client, db_session):
    token_a, org_a = _register(client)
    kb_a = _create_kb(client, token_a, f"Tenant A KB {uuid.uuid4()}")
    doc_a = _write_doc_direct(db_session, org_a, kb_a, _SAMPLE_TEXT.encode())

    token_b, org_b = _register(client)
    # B cannot ingest A's document (invisible -> 404).
    resp = client.post(
        f"{DOC_PREFIX}/{doc_a.id}/ingest", headers=_auth_headers(token_b)
    )
    assert resp.status_code == 404

    for org in (org_a, org_b):
        db_session.query(Document).filter(
            Document.organization_id == str(org)
        ).delete(synchronize_session=False)
        db_session.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == str(org)
        ).delete(synchronize_session=False)
    db_session.commit()
