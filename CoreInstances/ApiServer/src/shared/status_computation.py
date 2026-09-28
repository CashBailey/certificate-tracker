"""
Status computation utilities for the City of Laredo Certificate Management System.

Functions for computing requirement and certificate lifecycle statuses.
"""

from datetime import date
from typing import Optional

from .models import (
    CertificateLifecycleResult,
    CertificateLifecycleStatus,
    RequirementComplianceStatus,
    RequirementStatus,
)


# Default threshold for "expiring soon" and "due soon" notifications
DEFAULT_SOON_DAYS = 30


def compute_requirement_status(
    due_date: date,
    current_date: date,
    is_satisfied: bool,
    is_waived: bool,
    has_pending_document: bool = False,
    has_extraction_in_progress: bool = False,
) -> RequirementStatus:
    """
    Compute requirement status based on dates and satisfaction state.

    Args:
        due_date: Requirement due date
        current_date: Current date
        is_satisfied: Whether requirement is satisfied (approved extraction)
        is_waived: Whether requirement is waived
        has_pending_document: Whether a document has been uploaded but not yet processed
        has_extraction_in_progress: Whether extraction is in progress (pending review)

    Returns:
        RequirementStatus enum value

    Status flow:
        NOT_STARTED -> SUBMITTED (document uploaded)
        SUBMITTED -> IN_PROGRESS (extraction started)
        IN_PROGRESS -> SATISFIED (extraction approved)
        Any state can become OVERDUE if due_date passes
        Any state can become WAIVED if coordinator waives
    """
    # Waived takes precedence over everything except satisfied
    if is_waived and not is_satisfied:
        return RequirementStatus.WAIVED

    # Satisfied is the terminal success state
    if is_satisfied:
        return RequirementStatus.SATISFIED

    # Check overdue - applies to all non-terminal states
    if current_date > due_date:
        return RequirementStatus.OVERDUE

    # Check in-progress states
    if has_extraction_in_progress:
        return RequirementStatus.IN_PROGRESS

    if has_pending_document:
        return RequirementStatus.SUBMITTED

    return RequirementStatus.NOT_STARTED


def certificate_has_expiration(expiration_date: Optional[date]) -> bool:
    """
    Check if a certificate has an expiration date.

    Some certificates (e.g., certain training completions) may not expire.
    This helper makes null-expiration handling explicit.

    Args:
        expiration_date: Certificate expiration date or None

    Returns:
        True if certificate has an expiration date, False if it doesn't expire
    """
    return expiration_date is not None


def compute_certificate_lifecycle_status(
    expiration_date: Optional[date],
    current_date: date,
    expiring_soon_days: int = DEFAULT_SOON_DAYS,
    is_non_expiring_cert_type: bool = False,
) -> CertificateLifecycleResult:
    """
    Compute certificate lifecycle status based on expiration date.

    Per SM-03 from the spec: when expiration_date is null, returns VALID status
    with missing_expiration flag set to True (unless the certificate type is
    known to be non-expiring).

    Handles these cases:
    - No expiration date + non-expiring type: VALID, missing_expiration=False
    - No expiration date + expiring type: VALID, missing_expiration=True
    - Expired: current_date > expiration_date
    - Expiring soon: within expiring_soon_days of expiration
    - Valid: not expired and not expiring soon

    Args:
        expiration_date: Certificate expiration date or None
        current_date: Current date for comparison
        expiring_soon_days: Days before expiration to consider "expiring soon"
        is_non_expiring_cert_type: True if this certificate type never expires

    Returns:
        CertificateLifecycleResult with status and missing_expiration flag
    """
    # Null expiration handling per SM-03
    if not certificate_has_expiration(expiration_date):
        if is_non_expiring_cert_type:
            # Known non-expiring certificate type - this is expected
            return CertificateLifecycleResult(
                status=CertificateLifecycleStatus.VALID,
                missing_expiration=False,
            )
        else:
            # Expiration date is missing but cert type may require it
            # Return VALID with flag to indicate data quality issue
            return CertificateLifecycleResult(
                status=CertificateLifecycleStatus.VALID,
                missing_expiration=True,
            )

    # At this point expiration_date is guaranteed non-None
    if current_date > expiration_date:
        return CertificateLifecycleResult(
            status=CertificateLifecycleStatus.EXPIRED,
            missing_expiration=False,
        )

    days_until_expiration = (expiration_date - current_date).days
    if days_until_expiration <= expiring_soon_days:
        return CertificateLifecycleResult(
            status=CertificateLifecycleStatus.EXPIRING_SOON,
            missing_expiration=False,
        )

    return CertificateLifecycleResult(
        status=CertificateLifecycleStatus.VALID,
        missing_expiration=False,
    )


def compute_requirement_compliance_status(
    requirement_status: RequirementStatus,
    due_date: date,
    current_date: date,
    due_soon_days: int = DEFAULT_SOON_DAYS,
) -> RequirementComplianceStatus:
    """
    Compute requirement compliance status for reporting.

    Args:
        requirement_status: Current requirement status
        due_date: Requirement due date
        current_date: Current date
        due_soon_days: Days before due date to consider "due soon"

    Returns:
        RequirementComplianceStatus enum value
    """
    if requirement_status == RequirementStatus.WAIVED:
        return RequirementComplianceStatus.WAIVED

    if requirement_status == RequirementStatus.SATISFIED:
        return RequirementComplianceStatus.COMPLIANT

    # Check date directly — don't rely on stored OVERDUE status
    if current_date > due_date:
        return RequirementComplianceStatus.OVERDUE

    days_until_due = (due_date - current_date).days
    if days_until_due <= due_soon_days:
        return RequirementComplianceStatus.DUE_SOON

    # Per HLSD Decision 19: unsatisfied requirements not within 30 days count as compliant
    return RequirementComplianceStatus.COMPLIANT


def get_certificate_lifecycle_status_enum(
    expiration_date: Optional[date],
    current_date: date,
    expiring_soon_days: int = DEFAULT_SOON_DAYS,
) -> CertificateLifecycleStatus:
    """
    Legacy helper that returns just the status enum for backward compatibility.

    Prefer using compute_certificate_lifecycle_status() which returns the full
    CertificateLifecycleResult with the missing_expiration flag.

    Args:
        expiration_date: Certificate expiration date or None
        current_date: Current date for comparison
        expiring_soon_days: Days before expiration to consider "expiring soon"

    Returns:
        CertificateLifecycleStatus enum value
    """
    result = compute_certificate_lifecycle_status(
        expiration_date, current_date, expiring_soon_days
    )
    return result.status
