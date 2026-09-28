"""
Unit tests for compliance status computation utilities.

Tests the pure functions in src/shared/status_computation.py that determine
requirement and certificate lifecycle statuses.
"""

import pytest
from datetime import date, timedelta

from src.shared.status_computation import (
    compute_requirement_status,
    compute_certificate_lifecycle_status,
    compute_requirement_compliance_status,
    certificate_has_expiration,
    DEFAULT_SOON_DAYS,
)
from src.shared.models import (
    RequirementStatus,
    RequirementComplianceStatus,
    CertificateLifecycleStatus,
)


class TestComputeRequirementStatus:
    """Tests for compute_requirement_status function."""

    @pytest.fixture
    def today(self):
        """Fixed reference date for tests."""
        return date(2026, 2, 4)

    def test_not_started_when_nothing_submitted(self, today):
        """Requirement with no activity should be NOT_STARTED."""
        due_date = today + timedelta(days=30)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
            has_pending_document=False,
            has_extraction_in_progress=False,
        )
        assert status == RequirementStatus.NOT_STARTED

    def test_submitted_when_document_pending(self, today):
        """Requirement should be SUBMITTED when document uploaded but not processed."""
        due_date = today + timedelta(days=30)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
            has_pending_document=True,
            has_extraction_in_progress=False,
        )
        assert status == RequirementStatus.SUBMITTED

    def test_in_progress_when_extraction_running(self, today):
        """Requirement should be IN_PROGRESS when extraction is pending review."""
        due_date = today + timedelta(days=30)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
            has_pending_document=True,
            has_extraction_in_progress=True,
        )
        assert status == RequirementStatus.IN_PROGRESS

    def test_satisfied_when_approved(self, today):
        """Requirement should be SATISFIED when extraction approved."""
        due_date = today + timedelta(days=30)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=True,
            is_waived=False,
        )
        assert status == RequirementStatus.SATISFIED

    def test_satisfied_overrides_waived(self, today):
        """SATISFIED should take precedence over WAIVED."""
        due_date = today + timedelta(days=30)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=True,
            is_waived=True,  # Both set
        )
        assert status == RequirementStatus.SATISFIED

    def test_waived_when_not_satisfied(self, today):
        """Requirement should be WAIVED when waived and not satisfied."""
        due_date = today + timedelta(days=30)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=True,
        )
        assert status == RequirementStatus.WAIVED

    def test_overdue_when_past_due_date(self, today):
        """Requirement should be OVERDUE when current date > due date."""
        due_date = today - timedelta(days=1)  # Yesterday
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
        )
        assert status == RequirementStatus.OVERDUE

    def test_overdue_even_with_pending_document(self, today):
        """OVERDUE takes precedence over SUBMITTED state."""
        due_date = today - timedelta(days=1)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
            has_pending_document=True,
        )
        assert status == RequirementStatus.OVERDUE

    def test_overdue_even_with_extraction_in_progress(self, today):
        """OVERDUE takes precedence over IN_PROGRESS state."""
        due_date = today - timedelta(days=1)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
            has_extraction_in_progress=True,
        )
        assert status == RequirementStatus.OVERDUE

    def test_satisfied_not_overdue_even_past_due(self, today):
        """SATISFIED should not become OVERDUE even if past due date."""
        due_date = today - timedelta(days=30)  # Long past due
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=True,
            is_waived=False,
        )
        assert status == RequirementStatus.SATISFIED

    def test_due_date_boundary_same_day_not_overdue(self, today):
        """Requirement due today should NOT be overdue yet."""
        due_date = today  # Due today
        status = compute_requirement_status(
            due_date=due_date,
            current_date=today,
            is_satisfied=False,
            is_waived=False,
        )
        assert status == RequirementStatus.NOT_STARTED  # Not overdue

    def test_due_date_boundary_next_day_is_overdue(self, today):
        """Requirement becomes overdue the day after due date."""
        due_date = today
        tomorrow = today + timedelta(days=1)
        status = compute_requirement_status(
            due_date=due_date,
            current_date=tomorrow,
            is_satisfied=False,
            is_waived=False,
        )
        assert status == RequirementStatus.OVERDUE


class TestCertificateHasExpiration:
    """Tests for certificate_has_expiration helper."""

    def test_returns_true_for_date(self):
        """Should return True when expiration date is set."""
        assert certificate_has_expiration(date(2025, 12, 31)) is True

    def test_returns_false_for_none(self):
        """Should return False when expiration date is None."""
        assert certificate_has_expiration(None) is False


class TestComputeCertificateLifecycleStatus:
    """Tests for compute_certificate_lifecycle_status function."""

    @pytest.fixture
    def today(self):
        """Fixed reference date for tests."""
        return date(2026, 2, 4)

    def test_valid_when_not_expiring_soon(self, today):
        """Certificate should be VALID when expiration is far away."""
        expiration = today + timedelta(days=90)  # 90 days out
        result = compute_certificate_lifecycle_status(expiration, today)
        assert result.status == CertificateLifecycleStatus.VALID
        assert result.missing_expiration is False

    def test_expiring_soon_within_threshold(self, today):
        """Certificate should be EXPIRING_SOON within threshold days."""
        expiration = today + timedelta(days=25)  # 25 days < 30 default
        result = compute_certificate_lifecycle_status(expiration, today)
        assert result.status == CertificateLifecycleStatus.EXPIRING_SOON
        assert result.missing_expiration is False

    def test_expiring_soon_at_boundary(self, today):
        """Certificate should be EXPIRING_SOON at exactly threshold days."""
        expiration = today + timedelta(days=DEFAULT_SOON_DAYS)  # 30 days
        result = compute_certificate_lifecycle_status(expiration, today)
        assert result.status == CertificateLifecycleStatus.EXPIRING_SOON

    def test_valid_just_past_threshold(self, today):
        """Certificate should be VALID just past threshold days."""
        expiration = today + timedelta(days=DEFAULT_SOON_DAYS + 1)  # 31 days
        result = compute_certificate_lifecycle_status(expiration, today)
        assert result.status == CertificateLifecycleStatus.VALID

    def test_expired_when_past_expiration(self, today):
        """Certificate should be EXPIRED when current date > expiration."""
        expiration = today - timedelta(days=1)  # Yesterday
        result = compute_certificate_lifecycle_status(expiration, today)
        assert result.status == CertificateLifecycleStatus.EXPIRED
        assert result.missing_expiration is False

    def test_expired_at_boundary(self, today):
        """Certificate expires the day AFTER expiration date."""
        expiration = today  # Expires today
        result = compute_certificate_lifecycle_status(expiration, today)
        # Same day should still be EXPIRING_SOON, not expired
        assert result.status == CertificateLifecycleStatus.EXPIRING_SOON

        # Next day should be expired
        tomorrow = today + timedelta(days=1)
        result = compute_certificate_lifecycle_status(expiration, tomorrow)
        assert result.status == CertificateLifecycleStatus.EXPIRED

    def test_null_expiration_non_expiring_type(self, today):
        """Non-expiring certificate type with null expiration is VALID."""
        result = compute_certificate_lifecycle_status(
            expiration_date=None,
            current_date=today,
            is_non_expiring_cert_type=True,
        )
        assert result.status == CertificateLifecycleStatus.VALID
        assert result.missing_expiration is False  # Expected to be null

    def test_null_expiration_expiring_type_flags_missing(self, today):
        """Expiring certificate type with null expiration is VALID but flagged."""
        result = compute_certificate_lifecycle_status(
            expiration_date=None,
            current_date=today,
            is_non_expiring_cert_type=False,  # Type normally expires
        )
        assert result.status == CertificateLifecycleStatus.VALID
        assert result.missing_expiration is True  # Data quality issue

    def test_custom_threshold_days(self, today):
        """Should respect custom expiring_soon_days parameter."""
        expiration = today + timedelta(days=50)

        # With default 30 days, should be VALID
        result = compute_certificate_lifecycle_status(expiration, today)
        assert result.status == CertificateLifecycleStatus.VALID

        # With custom 60 days, should be EXPIRING_SOON
        result = compute_certificate_lifecycle_status(
            expiration, today, expiring_soon_days=60
        )
        assert result.status == CertificateLifecycleStatus.EXPIRING_SOON


class TestComputeRequirementComplianceStatus:
    """Tests for compute_requirement_compliance_status function (reporting)."""

    @pytest.fixture
    def today(self):
        """Fixed reference date for tests."""
        return date(2026, 2, 4)

    def test_compliant_when_satisfied(self, today):
        """SATISFIED requirement should be COMPLIANT."""
        due_date = today + timedelta(days=10)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.SATISFIED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.COMPLIANT

    def test_waived_when_waived(self, today):
        """WAIVED requirement should be WAIVED in compliance."""
        due_date = today + timedelta(days=10)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.WAIVED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.WAIVED

    def test_overdue_when_overdue(self, today):
        """OVERDUE requirement should be OVERDUE in compliance."""
        due_date = today - timedelta(days=10)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.OVERDUE,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.OVERDUE

    def test_due_soon_when_within_threshold(self, today):
        """NOT_STARTED requirement due soon should be DUE_SOON."""
        due_date = today + timedelta(days=20)  # Within 30-day threshold
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.DUE_SOON

    def test_due_soon_for_submitted_within_threshold(self, today):
        """SUBMITTED requirement due soon should be DUE_SOON."""
        due_date = today + timedelta(days=20)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.SUBMITTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.DUE_SOON

    def test_due_soon_for_in_progress_within_threshold(self, today):
        """IN_PROGRESS requirement due soon should be DUE_SOON."""
        due_date = today + timedelta(days=20)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.IN_PROGRESS,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.DUE_SOON

    def test_compliant_when_not_started_but_far_from_due(self, today):
        """NOT_STARTED requirement far from due should be COMPLIANT."""
        due_date = today + timedelta(days=60)  # Outside 30-day threshold
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.COMPLIANT

    def test_due_soon_at_boundary(self, today):
        """Requirement at exactly threshold days should be DUE_SOON."""
        due_date = today + timedelta(days=DEFAULT_SOON_DAYS)  # Exactly 30 days
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.DUE_SOON

    def test_compliant_just_past_boundary(self, today):
        """Requirement just past threshold should be COMPLIANT."""
        due_date = today + timedelta(days=DEFAULT_SOON_DAYS + 1)  # 31 days
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.COMPLIANT

    def test_overdue_when_not_started_past_due(self, today):
        """NOT_STARTED requirement past due date should be OVERDUE, not DUE_SOON."""
        due_date = today - timedelta(days=10)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.OVERDUE

    def test_overdue_when_submitted_past_due(self, today):
        """SUBMITTED requirement past due date should be OVERDUE, not DUE_SOON."""
        due_date = today - timedelta(days=5)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.SUBMITTED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.OVERDUE

    def test_overdue_when_in_progress_past_due(self, today):
        """IN_PROGRESS requirement past due date should be OVERDUE."""
        due_date = today - timedelta(days=1)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.IN_PROGRESS,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.OVERDUE

    def test_satisfied_not_overdue_even_past_due(self, today):
        """SATISFIED requirement should be COMPLIANT even past due date."""
        due_date = today - timedelta(days=30)
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.SATISFIED,
            due_date=due_date,
            current_date=today,
        )
        assert status == RequirementComplianceStatus.COMPLIANT

    def test_custom_threshold_days(self, today):
        """Should respect custom due_soon_days parameter."""
        due_date = today + timedelta(days=50)

        # With default 30 days, should be COMPLIANT
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
            due_soon_days=30,
        )
        assert status == RequirementComplianceStatus.COMPLIANT

        # With custom 60 days, should be DUE_SOON
        status = compute_requirement_compliance_status(
            requirement_status=RequirementStatus.NOT_STARTED,
            due_date=due_date,
            current_date=today,
            due_soon_days=60,
        )
        assert status == RequirementComplianceStatus.DUE_SOON


class TestStatusComputationDeterminism:
    """Tests that status computation is deterministic for the same inputs."""

    def test_requirement_status_deterministic(self):
        """Same inputs should always produce same requirement status."""
        kwargs = {
            "due_date": date(2026, 3, 15),
            "current_date": date(2026, 2, 4),
            "is_satisfied": False,
            "is_waived": False,
            "has_pending_document": True,
            "has_extraction_in_progress": False,
        }
        results = [compute_requirement_status(**kwargs) for _ in range(100)]
        assert all(r == results[0] for r in results)

    def test_certificate_lifecycle_deterministic(self):
        """Same inputs should always produce same certificate status."""
        results = [
            compute_certificate_lifecycle_status(
                expiration_date=date(2026, 3, 15),
                current_date=date(2026, 2, 4),
            )
            for _ in range(100)
        ]
        assert all(r.status == results[0].status for r in results)

    def test_compliance_status_deterministic(self):
        """Same inputs should always produce same compliance status."""
        results = [
            compute_requirement_compliance_status(
                requirement_status=RequirementStatus.SUBMITTED,
                due_date=date(2026, 3, 15),
                current_date=date(2026, 2, 4),
            )
            for _ in range(100)
        ]
        assert all(r == results[0] for r in results)


class TestStatusTransitionInvariants:
    """Tests for status transition invariants."""

    @pytest.fixture
    def today(self):
        return date(2026, 2, 4)

    def test_satisfied_is_terminal_success(self, today):
        """SATISFIED should be stable regardless of other inputs."""
        for days_offset in [-90, -30, 0, 30, 90]:
            due_date = today + timedelta(days=days_offset)
            for pending in [True, False]:
                for in_progress in [True, False]:
                    for waived in [True, False]:
                        status = compute_requirement_status(
                            due_date=due_date,
                            current_date=today,
                            is_satisfied=True,
                            is_waived=waived,
                            has_pending_document=pending,
                            has_extraction_in_progress=in_progress,
                        )
                        assert status == RequirementStatus.SATISFIED

    def test_waived_takes_precedence_when_not_satisfied(self, today):
        """WAIVED should take precedence over other non-satisfied states."""
        due_date = today + timedelta(days=30)
        for pending in [True, False]:
            for in_progress in [True, False]:
                status = compute_requirement_status(
                    due_date=due_date,
                    current_date=today,
                    is_satisfied=False,
                    is_waived=True,
                    has_pending_document=pending,
                    has_extraction_in_progress=in_progress,
                )
                assert status == RequirementStatus.WAIVED

    def test_overdue_when_past_due_and_not_terminal(self, today):
        """OVERDUE should apply when past due and not satisfied/waived."""
        due_date = today - timedelta(days=1)
        for pending in [True, False]:
            for in_progress in [True, False]:
                status = compute_requirement_status(
                    due_date=due_date,
                    current_date=today,
                    is_satisfied=False,
                    is_waived=False,
                    has_pending_document=pending,
                    has_extraction_in_progress=in_progress,
                )
                assert status == RequirementStatus.OVERDUE
