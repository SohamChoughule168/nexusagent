"""Document Upload API tests (Milestone 3).

Exercises the document endpoints reusing the same tenant-isolation boundary as
the Knowledge Base API: ``organization_id`` is derived from the authenticated
principal, never from request data. Write operations are additionally gated by
RBAC (owner/admin/member); reads are open to any tenant member.

Style mirrors ``test_knowledge_base_api.py``: register a real user (yields a
JWT + organization), then exercise the document endpoints with a ``Bearer``
token. Each test registers a fresh organization so seeded data never collides.
"""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.security import create_access_token, get_password_hash
from app.core.database import get_sessionmaker as SessionLocal
from app.models.all_models import Document, KnowledgeBase
from app.models.user import User
from app.models.all_models import OrganizationMember

KB_PREFIX = "/api/v1/knowledge-bases"
DOC_PREFIX = "/api/v1/documents"
AUTH_PREFIX = "/api/v1/auth"


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
    email = f"doc-owner-{uuid.uuid4()}@example.com"
    resp = client.post(
        f"{AUTH_PREFIX}/register",
        json={
            "email": email,
            "password": "TestPass#123",
            "full_name": "Doc Owner",
            "organization_name": f"Doc Org {uuid.uuid4()}",
            "organization_slug": f"doc-org-{uuid.uuid4()}",
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
    email = f"doc-viewer-{uuid.uuid4()}@example.com"
    user = User(
        email=email,
        password_hash=get_password_hash("TestPass#123"),
        full_name="Doc Viewer",
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


@pytest.fixture
def auth_org(client, db_session):
    """Register an owner; yield (token, org_id, tracker); clean up on exit."""
    token, org_id = _register(client)
    tracker = {"viewer_user_ids": []}
    yield token, org_id, tracker

    # Cleanup: documents cascade via FK when KBs are removed. Also drop any
    # viewer users this test created.
    db_session.query(Document).filter(Document.organization_id == org_id).delete(
        synchronize_session=False
    )
    db_session.query(KnowledgeBase).filter(
        KnowledgeBase.organization_id == org_id
    ).delete(synchronize_session=False)
    for uid in tracker["viewer_user_ids"]:
        db_session.query(OrganizationMember).filter(
            OrganizationMember.user_id == uid
        ).delete(synchronize_session=False)
        db_session.query(User).filter(User.id == uid).delete(
            synchronize_session=False
        )
    db_session.commit()


def _pdf_bytes(extra: bytes = b"") -> bytes:
    return b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF" + extra


# ---------------------------------------------------------------------------
# POST /knowledge-bases/{kb_id}/documents  (upload)
# ---------------------------------------------------------------------------


def test_upload_pdf_returns_201(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Upload KB {uuid.uuid4()}")
    pdf = _pdf_bytes()

    response = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("report.pdf", pdf, "application/pdf")},
        data={"title": "My Report"},
        headers=_auth_headers(token),
    )
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["knowledge_base_id"] == kb_id
    assert body["organization_id"] == org_id
    assert body["original_filename"] == "report.pdf"
    assert body["filename"] == "report.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["file_size"] == len(pdf)
    assert body["status"] == "uploaded"
    assert body["title"] == "My Report"
    assert body["upload_member_id"]
    assert body["storage_path"]
    assert isinstance(body["metadata"], dict)


def test_upload_requires_authentication(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Auth KB {uuid.uuid4()}")
    response = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("report.pdf", _pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 401


def test_upload_invalid_knowledge_base_404(client, auth_org):
    token, org_id, _ = auth_org
    response = client.post(
        f"{KB_PREFIX}/{uuid.uuid4()}/documents",
        files={"file": ("report.pdf", _pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token),
    )
    assert response.status_code == 404


def test_upload_invalid_file_type_400(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Type KB {uuid.uuid4()}")
    response = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


def test_upload_oversized_file_413(client, auth_org, monkeypatch):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Big KB {uuid.uuid4()}")
    # Shrink the limit so we can trigger 413 with a 2 MB payload.
    monkeypatch.setattr(
        __import__("app.core.config", fromlist=["settings"]).settings,
        "MAX_UPLOAD_SIZE_MB",
        1,
    )
    big = _pdf_bytes(b"x" * (2 * 1024 * 1024))
    response = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("big.pdf", big, "application/pdf")},
        headers=_auth_headers(token),
    )
    assert response.status_code == 413


def test_upload_invalid_kb_id_400(client, auth_org):
    token, org_id, _ = auth_org
    response = client.post(
        f"{KB_PREFIX}/not-a-uuid/documents",
        files={"file": ("report.pdf", _pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token),
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# GET /knowledge-bases/{kb_id}/documents  (list)
# ---------------------------------------------------------------------------


def test_list_documents_includes_uploaded(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"List KB {uuid.uuid4()}")
    for i in range(2):
        resp = client.post(
            f"{KB_PREFIX}/{kb_id}/documents",
            files={"file": (f"doc{i}.pdf", _pdf_bytes(), "application/pdf")},
            headers=_auth_headers(token),
        )
        assert resp.status_code == 201, resp.text

    response = client.get(
        f"{KB_PREFIX}/{kb_id}/documents", headers=_auth_headers(token)
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    filenames = {d["original_filename"] for d in body}
    assert "doc0.pdf" in filenames and "doc1.pdf" in filenames


def test_list_documents_invalid_kb_404(client, auth_org):
    token, org_id, _ = auth_org
    response = client.get(
        f"{KB_PREFIX}/{uuid.uuid4()}/documents", headers=_auth_headers(token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /documents/{document_id}
# ---------------------------------------------------------------------------


def _upload(client, token, kb_id, name="doc.pdf"):
    resp = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": (name, _pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def test_get_document_returns_200(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Get KB {uuid.uuid4()}")
    doc_id = _upload(client, token, kb_id)

    response = client.get(f"{DOC_PREFIX}/{doc_id}", headers=_auth_headers(token))
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == doc_id
    assert body["knowledge_base_id"] == kb_id


def test_get_document_invalid_id_400(client, auth_org):
    token, org_id, _ = auth_org
    response = client.get(f"{DOC_PREFIX}/not-a-uuid", headers=_auth_headers(token))
    assert response.status_code == 400


def test_get_document_unknown_404(client, auth_org):
    token, org_id, _ = auth_org
    response = client.get(f"{DOC_PREFIX}/{uuid.uuid4()}", headers=_auth_headers(token))
    assert response.status_code == 404


def test_get_document_requires_authentication(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Auth Get KB {uuid.uuid4()}")
    doc_id = _upload(client, token, kb_id)
    response = client.get(f"{DOC_PREFIX}/{doc_id}")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /documents/{document_id}
# ---------------------------------------------------------------------------


def test_delete_document_returns_204(client, auth_org):
    token, org_id, _ = auth_org
    kb_id = _create_kb(client, token, f"Del KB {uuid.uuid4()}")
    doc_id = _upload(client, token, kb_id)

    response = client.delete(
        f"{DOC_PREFIX}/{doc_id}", headers=_auth_headers(token)
    )
    assert response.status_code == 204

    follow_up = client.get(f"{DOC_PREFIX}/{doc_id}", headers=_auth_headers(token))
    assert follow_up.status_code == 404


def test_delete_document_unknown_404(client, auth_org):
    token, org_id, _ = auth_org
    response = client.delete(
        f"{DOC_PREFIX}/{uuid.uuid4()}", headers=_auth_headers(token)
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------


def test_tenant_isolation_blocks_cross_tenant_read(client, db_session):
    # Two distinct organizations (function-scoped fixtures are cached, so we
    # register the second org explicitly to guarantee a different tenant).
    token_a, org_a = _register(client)
    kb_a = _create_kb(client, token_a, f"Tenant A KB {uuid.uuid4()}")
    doc_a = _upload(client, token_a, kb_a)

    token_b, org_b = _register(client)

    # B cannot read A's document by id.
    resp = client.get(f"{DOC_PREFIX}/{doc_a}", headers=_auth_headers(token_b))
    assert resp.status_code == 404

    # B cannot list documents in A's knowledge base.
    resp = client.get(
        f"{KB_PREFIX}/{kb_a}/documents", headers=_auth_headers(token_b)
    )
    assert resp.status_code == 404

    # B cannot upload into A's knowledge base.
    resp = client.post(
        f"{KB_PREFIX}/{kb_a}/documents",
        files={"file": ("x.pdf", _pdf_bytes(), "application/pdf")},
        headers=_auth_headers(token_b),
    )
    assert resp.status_code == 404

    # Cleanup both tenants' data.
    for org in (org_a, org_b):
        db_session.query(Document).filter(Document.organization_id == org).delete(
            synchronize_session=False
        )
        db_session.query(KnowledgeBase).filter(
            KnowledgeBase.organization_id == org
        ).delete(synchronize_session=False)
    db_session.commit()


# ---------------------------------------------------------------------------
# Authorization (RBAC) — viewers may read but not write
# ---------------------------------------------------------------------------


def test_authorization_viewer_cannot_upload(client, auth_org, db_session):
    token, org_id, tracker = auth_org
    kb_id = _create_kb(client, token, f"RBAC KB {uuid.uuid4()}")
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)
    tracker["viewer_user_ids"].append(viewer_uid)

    response = client.post(
        f"{KB_PREFIX}/{kb_id}/documents",
        files={"file": ("report.pdf", _pdf_bytes(), "application/pdf")},
        headers=_auth_headers(viewer_token),
    )
    assert response.status_code == 403


def test_authorization_viewer_cannot_delete(client, auth_org, db_session):
    token, org_id, tracker = auth_org
    kb_id = _create_kb(client, token, f"RBAC Del KB {uuid.uuid4()}")
    doc_id = _upload(client, token, kb_id)
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)
    tracker["viewer_user_ids"].append(viewer_uid)

    response = client.delete(
        f"{DOC_PREFIX}/{doc_id}", headers=_auth_headers(viewer_token)
    )
    assert response.status_code == 403

    # Document must still exist (delete was refused).
    follow = client.get(f"{DOC_PREFIX}/{doc_id}", headers=_auth_headers(token))
    assert follow.status_code == 200


def test_authorization_viewer_can_read(client, auth_org, db_session):
    token, org_id, tracker = auth_org
    kb_id = _create_kb(client, token, f"RBAC Read KB {uuid.uuid4()}")
    _upload(client, token, kb_id)
    viewer_token, viewer_uid = _make_viewer(db_session, org_id)
    tracker["viewer_user_ids"].append(viewer_uid)

    response = client.get(
        f"{KB_PREFIX}/{kb_id}/documents", headers=_auth_headers(viewer_token)
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1
