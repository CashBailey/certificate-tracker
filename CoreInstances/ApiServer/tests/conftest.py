"""
Pytest configuration and shared fixtures for the City of Laredo API tests.
"""

import os
import pytest
from datetime import date, datetime, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

# ==================== Pytest Configuration ====================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line(
        "markers",
        "performance: marks tests as performance tests (may be slow or flaky under load)",
    )
    config.addinivalue_line(
        "markers",
        "resilience: marks tests as resilience/failure handling tests",
    )
    config.addinivalue_line(
        "markers",
        "security: marks tests as security tests",
    )
    config.addinivalue_line(
        "markers",
        "asyncio: marks tests as async tests requiring asyncio event loop",
    )


# Set test environment before importing application modules
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test_db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-testing-only")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ACCESS_KEY", "testaccess")
os.environ.setdefault("MINIO_SECRET_KEY", "testsecret")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")


# ==================== Domain Model Fixtures ====================

@pytest.fixture
def sample_employee():
    """Create a sample employee for testing."""
    from src.shared.models import Employee, Role
    return Employee(
        id=1,
        employee_number="E12345",
        first_name="John",
        last_name="Doe",
        email="john.doe@ci.laredo.tx.us",
        role=Role.EMPLOYEE.value,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_admin():
    """Create a sample admin user for testing."""
    from src.shared.models import Employee, Role
    return Employee(
        id=2,
        employee_number="ADMIN001",
        first_name="Admin",
        last_name="User",
        email="admin@ci.laredo.tx.us",
        role=Role.ADMIN.value,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_document():
    """Create a sample document for testing."""
    from src.shared.models import CertificateDocument
    return CertificateDocument(
        id=1,
        employee_id=1,
        file_name="certificate.pdf",
        file_type="application/pdf",
        file_size_bytes=1024,
        storage_key="documents/1/abc123/certificate.pdf",
        uploaded_by_id=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ==================== Mock Fixtures ====================

@pytest.fixture
def mock_repository():
    """Create a mock repository for testing."""
    repo = AsyncMock()
    repo.get_employee_by_id = AsyncMock(return_value=None)
    repo.get_employee_by_email = AsyncMock(return_value=None)
    repo.list_employees = AsyncMock(return_value=[])
    repo.create_employee = AsyncMock()
    repo.update_employee = AsyncMock()
    return repo


@pytest.fixture
def mock_storage():
    """Create a mock storage client for testing."""
    storage = AsyncMock()
    storage.put = AsyncMock()
    storage.get = AsyncMock(return_value=b"test content")
    storage.delete = AsyncMock()
    storage.exists = AsyncMock(return_value=True)
    return storage


@pytest.fixture
def mock_clock():
    """Create a mock clock for deterministic time testing."""
    from src.shared.protocols import Clock

    class MockClock(Clock):
        def __init__(self, fixed_time: datetime | None = None):
            self._now = fixed_time or datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

        def now(self) -> datetime:
            return self._now

        def today(self) -> date:
            return self._now.date()

        def set_time(self, dt: datetime) -> None:
            self._now = dt

    return MockClock()


@pytest.fixture
def mock_uuid_generator():
    """Create a mock UUID generator for deterministic IDs."""
    from src.shared.protocols import UuidGenerator

    class MockUuidGenerator(UuidGenerator):
        def __init__(self):
            self._counter = 0

        def generate(self) -> str:
            self._counter += 1
            return f"test-uuid-{self._counter:08d}"

    return MockUuidGenerator()


# ==================== Test Data Fixtures ====================

@pytest.fixture
def valid_pdf_bytes():
    """Return minimal valid PDF bytes for upload testing."""
    return b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n>>\nendobj\ntrailer\n<<\n/Root 1 0 R\n>>\n%%EOF"


@pytest.fixture
def valid_png_bytes():
    """Return minimal valid PNG bytes for upload testing."""
    # Minimal 1x1 transparent PNG
    return bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
        0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
        0x42, 0x60, 0x82,
    ])


@pytest.fixture
def invalid_file_bytes():
    """Return bytes that don't match any allowed file type."""
    return b"This is not a valid PDF or image file content"
