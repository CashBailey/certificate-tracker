"""
Integration test fixtures for the City of Laredo API tests.

These fixtures require Docker services (postgres, redis, minio) to be running.
"""

import os
import pytest
import json
from datetime import date, datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# Ensure test environment is set
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://laredo:laredo123@localhost:5432/laredo_certificates")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "minioadmin")
os.environ.setdefault("MINIO_SECRET_KEY", "minioadmin123")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("ALLOWED_EMAIL_DOMAIN", "ci.laredo.tx.us")


# ==================== Database Fixtures ====================

@pytest.fixture
async def db_session():
    """
    Create an async database session for integration tests.

    Uses the actual test database with rollback after each test.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url, echo=False)
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_factory() as session:
        yield session
        # Rollback any uncommitted changes after test
        await session.rollback()

    await engine.dispose()


@pytest.fixture
def repository(db_session):
    """Create a real SqlRepository with test database session."""
    from src.shared.repository import SqlRepository
    return SqlRepository(db_session)


# ==================== Redis Fixtures ====================

@pytest.fixture
def redis_client():
    """Create a Redis client for queue testing."""
    import redis
    client = redis.from_url(os.environ["REDIS_URL"])
    yield client
    # Clean up test keys after test
    client.flushdb()


@pytest.fixture
def mock_redis():
    """Create a mock Redis client for unit-style integration tests."""
    client = MagicMock()
    client.rpush = MagicMock(return_value=1)
    client.blpop = MagicMock(return_value=None)
    client.get = MagicMock(return_value=None)
    client.set = MagicMock(return_value=True)
    client.setex = MagicMock(return_value=True)
    client.delete = MagicMock(return_value=1)
    return client


# ==================== MinIO/Storage Fixtures ====================

@pytest.fixture
def mock_minio():
    """Create a mock MinIO client for storage tests."""
    client = MagicMock()
    client.put_object = MagicMock()
    client.get_object = MagicMock()
    client.bucket_exists = MagicMock(return_value=True)
    client.make_bucket = MagicMock()
    return client


# ==================== Domain Model Fixtures ====================

@pytest.fixture
def sample_employee_orm():
    """Create a sample employee ORM model."""
    from src.shared.orm_models import EmployeeORM

    return EmployeeORM(
        id=1,
        employee_number="E12345",
        first_name="John",
        last_name="Doe",
        email="john.doe@ci.laredo.tx.us",
        role="Employee",
        is_active=True,
    )


@pytest.fixture
def sample_reviewer():
    """Create a sample reviewer (Admin role) for approval tests."""
    from src.shared.models import Employee, Role

    return Employee(
        id=2,
        employee_number="R00001",
        first_name="Review",
        last_name="Admin",
        email="reviewer@ci.laredo.tx.us",
        role=Role.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_coordinator():
    """Create a sample Coordinator for SOD bypass tests."""
    from src.shared.models import Employee, Role

    return Employee(
        id=3,
        employee_number="C00001",
        first_name="Coord",
        last_name="User",
        email="coordinator@ci.laredo.tx.us",
        role=Role.COORDINATOR,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_document():
    """Create a sample certificate document."""
    from src.shared.models import CertificateDocument, IntakeChannel

    return CertificateDocument(
        id=1,
        employee_id=1,
        file_name="certificate.pdf",
        file_type="application/pdf",
        file_size_bytes=1024,
        storage_key="documents/1/abc123/certificate.pdf",
        uploaded_by_id=1,
        intake_channel=IntakeChannel.MANUAL_UPLOAD,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_extraction():
    """Create a sample extraction in PENDING_REVIEW state."""
    from src.shared.models import ExtractionRun, ReviewState

    return ExtractionRun(
        id=1,
        document_id=1,
        review_state=ReviewState.PENDING_REVIEW,
        extracted_fields={
            "certificate_holder_name": {
                "value": "John Doe",
                "confidence": {"overall": 0.95},
                "needs_review": False,
            },
            "certificate_type": {
                "value": "CPR/BLS",
                "confidence": {"overall": 0.90},
                "needs_review": False,
            },
            "expiration_date": {
                "value": "2027-01-15",
                "confidence": {"overall": 0.85},
                "needs_review": True,
            },
        },
        needs_review=True,
        needs_review_reasons=["Low confidence on expiration_date"],
        review_state_version=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_extraction_approved():
    """Create a sample extraction that has been approved."""
    from src.shared.models import ExtractionRun, ReviewState

    return ExtractionRun(
        id=2,
        document_id=2,
        review_state=ReviewState.APPROVED,
        extracted_fields={
            "certificate_holder_name": {"value": "Jane Smith"},
        },
        needs_review=False,
        needs_review_reasons=[],
        review_state_version=1,
        reviewed_by_id=2,
        reviewed_at=datetime.now(timezone.utc),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ==================== Email Intake Fixtures ====================

@pytest.fixture
def sample_email_attachment():
    """Create a sample email attachment."""
    return {
        "filename": "certificate.pdf",
        "content_type": "application/pdf",
        "payload": b"%PDF-1.4\n%test pdf content",
        "size": 24,
    }


@pytest.fixture
def sample_incoming_email(sample_email_attachment):
    """Create a sample incoming email with attachment."""
    return {
        "message_id": "<test-message-123@mail.ci.laredo.tx.us>",
        "from_address": "john.doe@ci.laredo.tx.us",
        "subject": "Certificate Upload",
        "received_date": datetime.now(timezone.utc),
        "attachments": [sample_email_attachment],
        "uid": "1",
    }


# ==================== OCR Pipeline Fixtures ====================

@pytest.fixture
def sample_ocr_request():
    """Create a sample OCR request message."""
    import base64

    # Minimal 1x1 PNG for testing
    image_bytes = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89,
    ])

    return {
        "request_id": "test-request-001",
        "page_num": 1,
        "image_b64": base64.b64encode(image_bytes).decode("ascii"),
        "width_px": 1,
        "height_px": 1,
        "dpi": 72,
        "bbox_norm": [0.0, 0.0, 1.0, 1.0],
    }


@pytest.fixture
def sample_ocr_response():
    """Create a sample OCR response message."""
    return {
        "request_id": "test-request-001",
        "spans": [
            {
                "text": "John Doe",
                "bbox_norm": [0.1, 0.1, 0.5, 0.2],
                "confidence": 0.95,
            },
            {
                "text": "CPR Certified",
                "bbox_norm": [0.1, 0.3, 0.6, 0.4],
                "confidence": 0.88,
            },
        ],
    }


@pytest.fixture
def sample_extraction_task():
    """Create a sample extraction task message."""
    return {
        "document_id": 1,
        "queued_at": datetime.now(timezone.utc).isoformat(),
        "source": "email_intake",
    }


# ==================== Test Data Fixtures ====================

@pytest.fixture
def valid_pdf_bytes():
    """Return minimal valid PDF bytes for upload testing."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"


@pytest.fixture
def valid_png_bytes():
    """Return minimal valid PNG bytes for upload testing."""
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
        0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
        0x42, 0x60, 0x82,
    ])


# ==================== Review Service Fixtures ====================

@pytest.fixture
def review_service(repository):
    """Create a ReviewService with real repository."""
    from src.review import ReviewService
    return ReviewService(repository)


@pytest.fixture
def mock_review_repository():
    """Create a mock repository for review service tests."""
    repo = AsyncMock()
    repo.get_extraction_by_id = AsyncMock(return_value=None)
    repo.get_document_by_id = AsyncMock(return_value=None)
    repo.get_verified_record_by_extraction_id = AsyncMock(return_value=None)
    repo.try_transition_extraction_review_state = AsyncMock(return_value=True)
    repo.insert_verified_record_idempotent = AsyncMock()
    repo.link_requirement_if_unset = AsyncMock()
    repo.create_audit_log = AsyncMock()
    return repo
