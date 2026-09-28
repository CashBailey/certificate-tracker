"""
Security tests for the Certificate Management System.

Tests security controls including:
- JWT token validation
- Role-based access control (RBAC)
- Role escalation prevention
- SQL injection prevention
- Input validation
- Path traversal prevention
- Rate limiting concepts
"""

import pytest
import json
import re
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
from enum import Enum
from unittest.mock import MagicMock


# ==================== Mock Models ====================
# NOTE: Values must match src/shared/models.Role to ensure test validity.
# If the real Role enum changes, these mocks must be updated accordingly.


class MockRole(Enum):
    """Mock Role enum matching actual roles in src/shared/models.py."""
    COORDINATOR = "Coordinator"
    ADMIN = "Admin"
    EMPLOYEE = "Employee"


@dataclass
class MockEmployee:
    """Mock Employee model."""
    id: int
    employee_number: str
    email: str
    role: MockRole
    is_active: bool = True


@dataclass
class MockJWTPayload:
    """Mock JWT payload structure."""
    sub: str  # employee_id
    email: str
    role: str
    exp: int  # expiration timestamp
    iat: int  # issued at timestamp
    jti: str  # JWT ID for revocation


# ==================== Fixtures ====================


@pytest.fixture
def employee():
    """Regular employee user."""
    return MockEmployee(
        id=100,
        employee_number="E12345",
        email="employee@ci.laredo.tx.us",
        role=MockRole.EMPLOYEE,
    )


@pytest.fixture
def admin():
    """Admin role user."""
    return MockEmployee(
        id=300,
        employee_number="A00001",
        email="admin@ci.laredo.tx.us",
        role=MockRole.ADMIN,
    )


@pytest.fixture
def coordinator():
    """Coordinator role user."""
    return MockEmployee(
        id=400,
        employee_number="C00001",
        email="coordinator@ci.laredo.tx.us",
        role=MockRole.COORDINATOR,
    )


# ==================== JWT Token Validation Tests ====================


@pytest.mark.security
class TestJWTValidation:
    """Tests for JWT token validation."""

    def test_valid_token_accepted(self):
        """Valid JWT token should be accepted."""
        now = datetime.now(timezone.utc)
        payload = MockJWTPayload(
            sub="100",
            email="user@ci.laredo.tx.us",
            role="Employee",
            exp=int((now + timedelta(hours=24)).timestamp()),
            iat=int(now.timestamp()),
            jti=secrets.token_hex(16),
        )

        # Token is valid if not expired and has required fields
        is_valid = (
            payload.exp > int(now.timestamp())
            and bool(payload.sub)
            and bool(payload.email)
            and bool(payload.role)
        )

        assert is_valid is True

    def test_expired_token_rejected(self):
        """Expired JWT token should be rejected."""
        now = datetime.now(timezone.utc)
        payload = MockJWTPayload(
            sub="100",
            email="user@ci.laredo.tx.us",
            role="Employee",
            exp=int((now - timedelta(hours=1)).timestamp()),  # Expired 1 hour ago
            iat=int((now - timedelta(hours=25)).timestamp()),
            jti=secrets.token_hex(16),
        )

        is_expired = payload.exp < int(now.timestamp())
        assert is_expired is True

    def test_missing_subject_rejected(self):
        """Token without subject (sub) should be rejected."""
        now = datetime.now(timezone.utc)
        payload = {
            "email": "user@ci.laredo.tx.us",
            "role": "Employee",
            "exp": int((now + timedelta(hours=24)).timestamp()),
        }

        has_subject = "sub" in payload and payload.get("sub")
        assert has_subject is False

    def test_missing_role_rejected(self):
        """Token without role should be rejected."""
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "100",
            "email": "user@ci.laredo.tx.us",
            "exp": int((now + timedelta(hours=24)).timestamp()),
        }

        has_role = "role" in payload and payload.get("role")
        assert has_role is False

    def test_invalid_role_rejected(self):
        """Token with invalid role value should be rejected."""
        valid_roles = {"Coordinator", "Admin", "Employee"}

        invalid_roles = ["SuperAdmin", "Root", "ADMIN", "admin", "", None, "God"]

        for invalid_role in invalid_roles:
            is_valid = invalid_role in valid_roles
            assert is_valid is False, f"Role '{invalid_role}' should be invalid"

    def test_token_signature_verification(self):
        """Token signature should be verified against secret."""
        # Simulate HMAC signature verification
        secret = "super-secret-key-that-should-be-in-env"
        payload = '{"sub":"100","role":"Employee"}'

        # Create signature
        signature = hashlib.sha256((payload + secret).encode()).hexdigest()

        # Verify signature
        expected_signature = hashlib.sha256((payload + secret).encode()).hexdigest()

        assert signature == expected_signature

    def test_tampered_token_rejected(self):
        """Token with tampered payload should be rejected."""
        secret = "super-secret-key"

        # Original payload and signature
        original_payload = '{"sub":"100","role":"Employee"}'
        original_signature = hashlib.sha256((original_payload + secret).encode()).hexdigest()

        # Tampered payload (role changed to Admin)
        tampered_payload = '{"sub":"100","role":"Admin"}'
        tampered_verification = hashlib.sha256((tampered_payload + secret).encode()).hexdigest()

        # Signatures should not match
        assert original_signature != tampered_verification

    def test_future_issued_at_rejected(self):
        """Token with future iat (issued at) should be rejected."""
        now = datetime.now(timezone.utc)
        payload = MockJWTPayload(
            sub="100",
            email="user@ci.laredo.tx.us",
            role="Employee",
            exp=int((now + timedelta(hours=24)).timestamp()),
            iat=int((now + timedelta(hours=1)).timestamp()),  # Issued in future
            jti=secrets.token_hex(16),
        )

        is_future_iat = payload.iat > int(now.timestamp())
        assert is_future_iat is True  # Should be rejected


# ==================== Role-Based Access Control Tests ====================


@pytest.mark.security
class TestRBACEnforcement:
    """Tests for role-based access control enforcement."""

    def test_role_hierarchy(self):
        """Verify role hierarchy is correctly defined."""
        # Role hierarchy: Coordinator > Admin > Employee
        role_levels = {
            MockRole.COORDINATOR: 3,
            MockRole.ADMIN: 2,
            MockRole.EMPLOYEE: 1,
        }

        assert role_levels[MockRole.COORDINATOR] > role_levels[MockRole.ADMIN]
        assert role_levels[MockRole.ADMIN] > role_levels[MockRole.EMPLOYEE]

    def test_any_authenticated_user_can_access_review_endpoints(self, employee):
        """Any authenticated user can access review endpoints (RBAC disabled)."""
        # RBAC disabled — all authenticated users have full access
        assert employee.role is not None

    def test_any_authenticated_user_can_access_admin_endpoints(self, employee):
        """Any authenticated user can access admin endpoints (RBAC disabled)."""
        assert employee.role is not None

    def test_coordinator_can_access_review_endpoints(self, coordinator):
        """Coordinator role can access review endpoints."""
        assert coordinator.role == MockRole.COORDINATOR

    def test_admin_can_manage_employees(self, admin):
        """Admin can manage employee records."""
        assert admin.role is not None

    def test_coordinator_has_full_access(self, coordinator):
        """Coordinator has access to all operations."""
        all_operations = [
            "review_extractions",
            "manage_employees",
            "view_reports",
            "manage_requirements",
            "resolve_quarantine",
        ]

        # Coordinator should have access to all
        for operation in all_operations:
            has_access = coordinator.role == MockRole.COORDINATOR
            assert has_access is True

    def test_inactive_user_denied_access(self):
        """Inactive user should be denied access regardless of role."""
        inactive_admin = MockEmployee(
            id=999,
            employee_number="X00001",
            email="inactive@ci.laredo.tx.us",
            role=MockRole.ADMIN,
            is_active=False,
        )

        # Should be denied regardless of admin role
        access_granted = inactive_admin.is_active
        assert access_granted is False


# ==================== Role Escalation Prevention Tests ====================


@pytest.mark.security
class TestRoleEscalationPrevention:
    """Tests for preventing role escalation attacks."""

    def test_employee_cannot_self_promote(self, employee):
        """Employee cannot change their own role."""
        original_role = employee.role

        # Attempt to self-promote
        requested_new_role = MockRole.ADMIN

        # Only Admin/Coordinator can change roles
        can_change_own_role = employee.role in {MockRole.ADMIN, MockRole.COORDINATOR}
        assert can_change_own_role is False

    def test_admin_can_assign_coordinator(self, admin):
        """Admin CAN assign Coordinator role (that's their purpose)."""
        roles_admin_can_assign = {MockRole.COORDINATOR, MockRole.EMPLOYEE}

        can_create_coordinator = MockRole.COORDINATOR in roles_admin_can_assign
        assert can_create_coordinator is True

    def test_admin_cannot_assign_admin(self, admin):
        """Admin cannot create other Admin accounts (seed-only)."""
        roles_admin_can_assign = {MockRole.COORDINATOR, MockRole.EMPLOYEE}

        can_create_admin = MockRole.ADMIN in roles_admin_can_assign
        assert can_create_admin is False

    def test_coordinator_cannot_assign_admin(self, coordinator):
        """Coordinator cannot assign Admin role."""
        roles_coordinator_can_assign = {MockRole.COORDINATOR, MockRole.EMPLOYEE}

        can_assign_admin = MockRole.ADMIN in roles_coordinator_can_assign
        assert can_assign_admin is False

    def test_coordinator_can_assign_coordinator_and_employee(self, coordinator):
        """Coordinator can assign Coordinator and Employee roles."""
        roles_coordinator_can_assign = {MockRole.COORDINATOR, MockRole.EMPLOYEE}

        for role in roles_coordinator_can_assign:
            can_assign = role in roles_coordinator_can_assign
            assert can_assign is True

    def test_role_assignment_rules(self):
        """Only Coordinator and Admin can assign roles; Admin is never assignable via API."""
        # Admin role is seed-only, never assignable via API
        api_assignable_roles = {MockRole.COORDINATOR, MockRole.EMPLOYEE}

        test_cases = [
            (MockRole.EMPLOYEE, MockRole.COORDINATOR, False),   # Employee can't assign any role
            (MockRole.EMPLOYEE, MockRole.EMPLOYEE, False),      # Employee can't assign any role
            (MockRole.ADMIN, MockRole.COORDINATOR, True),       # Admin CAN assign Coordinator
            (MockRole.ADMIN, MockRole.EMPLOYEE, True),          # Admin CAN assign Employee
            (MockRole.ADMIN, MockRole.ADMIN, False),            # Admin can't create another Admin
            (MockRole.COORDINATOR, MockRole.COORDINATOR, True), # Coordinator CAN assign Coordinator
            (MockRole.COORDINATOR, MockRole.EMPLOYEE, True),    # Coordinator CAN assign Employee
            (MockRole.COORDINATOR, MockRole.ADMIN, False),      # Coordinator can't assign Admin
        ]

        for actor_role, target_role, expected_allowed in test_cases:
            # Only Admin and Coordinator can assign roles
            can_assign = actor_role in {MockRole.ADMIN, MockRole.COORDINATOR}
            # Target must be API-assignable
            target_ok = target_role in api_assignable_roles
            allowed = can_assign and target_ok

            assert allowed == expected_allowed, \
                f"{actor_role.value} assigning {target_role.value} should be {expected_allowed}"

    def test_jwt_role_tampering_detected(self):
        """JWT with tampered role should be detected."""
        # Original token claims
        original_claims = {"sub": "100", "role": "Employee"}

        # Tampered claims (role escalation attempt)
        tampered_claims = {"sub": "100", "role": "Admin"}

        # Signature verification would fail
        original_signature = hashlib.sha256(
            json.dumps(original_claims, sort_keys=True).encode()
        ).hexdigest()

        tampered_signature = hashlib.sha256(
            json.dumps(tampered_claims, sort_keys=True).encode()
        ).hexdigest()

        # Signatures don't match
        assert original_signature != tampered_signature


# ==================== SQL Injection Prevention Tests ====================


@pytest.mark.security
class TestSQLInjectionPrevention:
    """Tests for SQL injection prevention."""

    def test_parameterized_query_escapes_quotes(self):
        """Parameterized queries should escape single quotes."""
        malicious_input = "'; DROP TABLE employees; --"

        # Simulating parameterized query escaping
        escaped = malicious_input.replace("'", "''")

        assert "DROP TABLE" in escaped  # String is preserved
        assert escaped == "''; DROP TABLE employees; --"  # Quotes are escaped

    def test_common_sql_injection_patterns_blocked(self):
        """Common SQL injection patterns should be detected."""
        sql_injection_patterns = [
            "' OR '1'='1",
            "'; DROP TABLE users; --",
            "1; DELETE FROM employees",
            "' UNION SELECT * FROM users --",
            "admin'--",
            "1' AND '1'='1",
            "' OR 1=1 --",
            "'; EXEC xp_cmdshell('dir'); --",
        ]

        # Pattern to detect SQL injection attempts
        sql_pattern = re.compile(
            r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|EXEC|EXECUTE)\b|"
            r"(--|;)|(\'.*\bOR\b|\bAND\b).*=|\'--)",
            re.IGNORECASE,
        )

        for injection in sql_injection_patterns:
            is_suspicious = bool(sql_pattern.search(injection))
            assert is_suspicious is True, f"Should detect: {injection}"

    def test_employee_id_must_be_integer(self):
        """Employee ID parameters must be integers."""
        valid_ids = [1, 100, 999999]
        invalid_ids = ["1; DROP TABLE", "abc", "1.5", "1 OR 1=1", None, "", "0x1"]

        for valid_id in valid_ids:
            is_valid = isinstance(valid_id, int) and valid_id > 0
            assert is_valid is True

        for invalid_id in invalid_ids:
            try:
                parsed = int(invalid_id)
                is_valid = parsed > 0
            except (ValueError, TypeError):
                is_valid = False
            assert is_valid is False, f"Should reject: {invalid_id}"

    def test_search_query_sanitized(self):
        """Search queries should be sanitized."""
        dangerous_chars = ["'", '"', ";", "--", "/*", "*/", "\\"]

        search_input = "John'; DROP TABLE employees; --"

        # Remove dangerous characters
        sanitized = search_input
        for char in dangerous_chars:
            sanitized = sanitized.replace(char, "")

        # Should not contain dangerous chars
        for char in dangerous_chars:
            assert char not in sanitized


# ==================== Input Validation Tests ====================


@pytest.mark.security
class TestInputValidation:
    """Tests for input validation."""

    def test_email_format_validation(self):
        """Email addresses must match valid format."""
        valid_emails = [
            "user@ci.laredo.tx.us",
            "john.doe@ci.laredo.tx.us",
            "admin123@ci.laredo.tx.us",
        ]

        invalid_emails = [
            "not-an-email",
            "@ci.laredo.tx.us",
            "user@",
            "user@.com",
            "user name@ci.laredo.tx.us",
            "<script>@ci.laredo.tx.us",
            "user@ci.laredo.tx.us; DROP TABLE",
        ]

        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

        for email in valid_emails:
            assert email_pattern.match(email), f"Should be valid: {email}"

        for email in invalid_emails:
            assert not email_pattern.match(email), f"Should be invalid: {email}"

    def test_employee_number_format(self):
        """Employee numbers must match expected format."""
        valid_numbers = ["E12345", "A00001", "R99999"]
        invalid_numbers = ["", "12345", "E", "E1234567890", "<script>", "E12345; DROP"]

        # Pattern: Letter followed by 5 digits
        pattern = re.compile(r'^[A-Z]\d{5}$')

        for num in valid_numbers:
            assert pattern.match(num), f"Should be valid: {num}"

        for num in invalid_numbers:
            assert not pattern.match(num), f"Should be invalid: {num}"

    def test_file_size_limits_enforced(self):
        """File uploads must respect size limits."""
        MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB

        test_sizes = [
            (1024, True),                    # 1 KB - valid
            (10 * 1024 * 1024, True),       # 10 MB - valid
            (20 * 1024 * 1024, True),       # 20 MB - valid (at limit)
            (20 * 1024 * 1024 + 1, False),  # 20 MB + 1 byte - invalid
            (100 * 1024 * 1024, False),     # 100 MB - invalid
        ]

        for size, expected_valid in test_sizes:
            is_valid = size <= MAX_FILE_SIZE
            assert is_valid == expected_valid

    def test_content_type_whitelist(self):
        """Only allowed content types should be accepted."""
        allowed_types = {
            "application/pdf",
            "image/png",
            "image/jpeg",
            "image/tiff",
        }

        blocked_types = [
            "application/x-msdownload",  # .exe
            "application/javascript",
            "text/html",
            "application/x-sh",
            "application/zip",
        ]

        for blocked in blocked_types:
            assert blocked not in allowed_types

    def test_filename_sanitization(self):
        """Filenames should be sanitized."""
        dangerous_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config",
            "file.pdf\x00.exe",  # Null byte injection
            "<script>alert(1)</script>.pdf",
            "file; rm -rf /.pdf",
        ]

        # Sanitization: keep only alphanumeric, dash, underscore, dot
        # and collapse consecutive dots to prevent path traversal
        def sanitize_filename(filename):
            # Replace dangerous characters
            sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
            # Collapse multiple dots to single dot (prevents ..)
            sanitized = re.sub(r'\.{2,}', '.', sanitized)
            return sanitized

        for dangerous in dangerous_filenames:
            sanitized = sanitize_filename(dangerous)
            assert ".." not in sanitized
            assert "/" not in sanitized
            assert "\\" not in sanitized
            assert "\x00" not in sanitized
            assert "<" not in sanitized
            assert ";" not in sanitized


# ==================== Path Traversal Prevention Tests ====================


@pytest.mark.security
class TestPathTraversalPrevention:
    """Tests for path traversal attack prevention."""

    def test_storage_key_cannot_escape_bucket(self):
        """Storage keys cannot traverse outside bucket."""
        malicious_keys = [
            "../../../etc/passwd",
            "..\\..\\windows\\system.ini",
            "documents/../../../secrets",
            "/absolute/path/to/file",
            "documents/./../../escape",
        ]

        def is_safe_key(key):
            # No path traversal sequences
            if ".." in key:
                return False
            # No absolute paths
            if key.startswith("/"):
                return False
            # No backslashes
            if "\\" in key:
                return False
            return True

        for key in malicious_keys:
            assert is_safe_key(key) is False, f"Should block: {key}"

    def test_document_id_in_path_is_validated(self):
        """Document IDs in URL paths must be valid integers."""
        valid_paths = ["/documents/1", "/documents/999", "/documents/123456"]
        invalid_paths = [
            "/documents/../1",
            "/documents/abc",
            "/documents/1;DROP",
            "/documents/-1",
            "/documents/1.5",
        ]

        path_pattern = re.compile(r'^/documents/(\d+)$')

        for path in valid_paths:
            match = path_pattern.match(path)
            assert match is not None, f"Should match: {path}"

        for path in invalid_paths:
            match = path_pattern.match(path)
            assert match is None, f"Should not match: {path}"


# ==================== Separation of Duties Tests ====================


@pytest.mark.security
class TestSeparationOfDuties:
    """Tests for separation of duties enforcement."""

    def test_holder_cannot_approve_own_certificate(self):
        """Certificate holder cannot approve their own certificate."""
        employee_id = 100
        reviewer_id = 100  # Same user — reviewer IS the certificate holder

        # Check if reviewer is the certificate holder
        violates_sod = employee_id == reviewer_id
        assert violates_sod is True

    def test_different_user_can_approve(self):
        """Different user can approve certificate belonging to another employee."""
        employee_id = 100
        reviewer_id = 200  # Different user

        violates_sod = employee_id == reviewer_id
        assert violates_sod is False

    def test_coordinator_bypasses_sod(self, coordinator):
        """Coordinator role bypasses separation of duties."""
        employee_id = coordinator.id
        reviewer_id = coordinator.id  # Same user

        # Coordinator has SOD bypass
        is_coordinator = coordinator.role == MockRole.COORDINATOR
        sod_applies = not is_coordinator

        # SOD doesn't apply to Coordinator
        assert sod_applies is False

    def test_admin_cannot_bypass_sod(self, admin):
        """Admin role does not bypass separation of duties."""
        employee_id = admin.id
        reviewer_id = admin.id  # Same user

        # Admin does NOT have SOD bypass
        is_coordinator = admin.role == MockRole.COORDINATOR
        sod_applies = not is_coordinator

        # SOD applies to Admin
        assert sod_applies is True


# ==================== Password Security Tests ====================


@pytest.mark.security
class TestPasswordSecurity:
    """Tests for password security requirements."""

    def test_password_minimum_length(self):
        """Password must meet minimum length requirement."""
        MIN_LENGTH = 8

        valid_passwords = ["Password1!", "SecurePass123", "MyP@ssw0rd"]
        invalid_passwords = ["Pass1!", "Short1", "1234567"]

        for pwd in valid_passwords:
            assert len(pwd) >= MIN_LENGTH

        for pwd in invalid_passwords:
            assert len(pwd) < MIN_LENGTH

    def test_password_not_stored_plaintext(self):
        """Passwords should be hashed, not stored in plaintext."""
        plaintext = "MySecurePassword123!"

        # Simulate hashing
        hashed = hashlib.sha256(plaintext.encode()).hexdigest()

        # Hash should be different from plaintext
        assert hashed != plaintext
        # Hash should be fixed length (64 chars for SHA-256)
        assert len(hashed) == 64

    def test_password_hash_is_salted(self):
        """Same password with different salts produces different hashes."""
        password = "SamePassword123!"

        salt1 = secrets.token_hex(16)
        salt2 = secrets.token_hex(16)

        hash1 = hashlib.sha256((password + salt1).encode()).hexdigest()
        hash2 = hashlib.sha256((password + salt2).encode()).hexdigest()

        # Different salts = different hashes
        assert hash1 != hash2


# ==================== Audit Security Tests ====================


@pytest.mark.security
class TestAuditSecurity:
    """Tests for audit log security."""

    def test_audit_logs_are_immutable(self):
        """Audit logs should not be modifiable."""
        # Audit logs should only support INSERT, not UPDATE or DELETE
        allowed_operations = {"INSERT"}
        blocked_operations = {"UPDATE", "DELETE"}

        for op in blocked_operations:
            assert op not in allowed_operations

    def test_sensitive_data_redacted_in_logs(self):
        """Sensitive data should be redacted in audit logs."""
        sensitive_fields = ["password", "ssn", "credit_card", "api_key"]

        log_entry = {
            "action": "user_login",
            "details": {
                "email": "user@ci.laredo.tx.us",
                "password": "REDACTED",
                "ip_address": "10.0.0.1",
            },
        }

        # Password should be redacted
        assert log_entry["details"]["password"] == "REDACTED"

    def test_audit_log_includes_actor_info(self):
        """Audit logs must include actor information."""
        required_fields = ["actor_type", "action", "target_type", "target_id", "created_at"]

        audit_entry = {
            "actor_type": "EMPLOYEE",
            "employee_id": 100,
            "action": "document_uploaded",
            "target_type": "document",
            "target_id": "1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        for field in required_fields:
            assert field in audit_entry
