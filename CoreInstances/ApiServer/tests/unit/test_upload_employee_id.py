"""
Unit tests for POST /documents — employee_id is required.

Defaulting employee_id to the uploader silently misattributes the resulting
verified record (especially harmful when a Coordinator uploads someone
else's cert without realising the form lacked the employee context).
The route now hard-fails with 400 if employee_id is omitted.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.deps import (
    get_current_user,
    get_db_session,
    get_redis,
    get_repository,
    get_storage,
    get_uuid_generator,
)
from src.routes.documents import router as documents_router
from src.shared.models import (
    CertificateDocument,
    Employee,
    ExtractionRun,
    ReviewState,
    Role,
)


# ==================== Helpers ====================


def _coordinator(employee_id: int = 10) -> Employee:
    return Employee(
        id=employee_id,
        employee_number=f"E{employee_id:05d}",
        first_name="Coord",
        last_name="User",
        email=f"coord{employee_id}@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_repo() -> AsyncMock:
    repo = AsyncMock()
    repo.create_document = AsyncMock(
        return_value=CertificateDocument(
            id=123,
            employee_id=1,
            storage_key="1/uuid/cert.pdf",
            file_name="cert.pdf",
            file_type="application/pdf",
            file_size_bytes=100,
            uploaded_by_id=10,
            acting_as="Coordinator",
            created_at=datetime.now(timezone.utc),
        )
    )
    repo.create_extraction = AsyncMock(
        return_value=ExtractionRun(
            id=456,
            document_id=123,
            review_state=ReviewState.PROCESSING,
            extracted_fields={},
            needs_review=True,
            needs_review_reasons=["Extraction in progress"],
        )
    )
    repo.create_audit_log = AsyncMock()
    return repo


def _make_storage() -> AsyncMock:
    storage = AsyncMock()
    storage.put = AsyncMock()
    return storage


def _make_uuid_generator() -> MagicMock:
    gen = MagicMock()
    gen.generate.return_value = "test-uuid-1"
    return gen


def _make_redis() -> MagicMock:
    # redis client uses sync rpush; MagicMock matches that.
    client = MagicMock()
    client.rpush = MagicMock(return_value=1)
    return client


def _create_app(
    user: Employee,
    repo: AsyncMock | None = None,
    storage: AsyncMock | None = None,
) -> tuple[FastAPI, TestClient, AsyncMock, AsyncMock]:
    app = FastAPI()
    app.include_router(documents_router, prefix="/api")

    repo = repo or _make_repo()
    storage = storage or _make_storage()
    session = AsyncMock()
    session.commit = AsyncMock()

    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: storage
    app.dependency_overrides[get_uuid_generator] = lambda: _make_uuid_generator()
    app.dependency_overrides[get_redis] = lambda: _make_redis()
    app.dependency_overrides[get_db_session] = lambda: session

    return app, TestClient(app), repo, storage


# ==================== Tests ====================


def test_upload_without_employee_id_returns_400(valid_pdf_bytes):
    """POST /documents without employee_id → 400 with helpful message;
    no storage or repo writes happen."""
    _, client, repo, storage = _create_app(_coordinator())

    resp = client.post(
        "/api/documents",
        files={"file": ("cert.pdf", valid_pdf_bytes, "application/pdf")},
    )

    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "employee_id is required" in detail
    # No side effects on the missing-id failure path.
    storage.put.assert_not_awaited()
    repo.create_document.assert_not_awaited()


def test_upload_with_employee_id_proceeds(valid_pdf_bytes):
    """POST /documents with valid employee_id → 201 and storage + repo are
    called with the supplied id (not the uploader's id)."""
    _, client, repo, storage = _create_app(_coordinator(employee_id=10))

    resp = client.post(
        "/api/documents",
        files={"file": ("cert.pdf", valid_pdf_bytes, "application/pdf")},
        data={"employee_id": "1"},
    )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["document_id"] == 123
    assert body["extraction_id"] == 456

    # Storage was written with a key under the target employee, not the uploader.
    storage.put.assert_awaited_once()
    storage_key = storage.put.await_args.args[0]
    assert storage_key.startswith("1/"), (
        f"storage key must use target employee_id (1), not uploader (10): {storage_key}"
    )

    # Document record created on behalf of employee_id=1
    repo.create_document.assert_awaited_once()
    created_doc = repo.create_document.await_args.args[0]
    assert created_doc.employee_id == 1
    assert created_doc.uploaded_by_id == 10
