"""
Unit tests for ``digest_builder._strip_subject_prefix`` and ``_SUBJECT_PREFIXES``.

These tests pin the behaviour of ``_SUBJECT_PREFIXES``. The list contains only
prefixes that match real subjects emitted by ``notifications.py``, with
specific coordinator markers ordered before the generic ``"[Coordinator] "``
fallback so urgency markers (OVERDUE, EXPIRED, etc.) are stripped from
coordinator digest entries instead of falling through to the bracketed
fallback.

Canonical subject emissions (from ``notifications.py`` lines ~440-560):

    Employee:
        "Requirement Due Tomorrow: {cert}"
        "Upcoming Requirement: {cert} Due {date}{days}"
        "OVERDUE: {cert} Requirement Past Due"
        "Certificate Expiring Soon: {cert}{days}"
        "EXPIRED: {cert} Has Expired"
        "Certificate Update: {cert}"

    Coordinator:
        "[Coordinator] {cert} Due Tomorrow - {emp}"
        "[Coordinator] Upcoming {cert} - {emp}{days}"
        "[Coordinator] OVERDUE {cert} - {emp}"
        "[Coordinator] {cert} Update - {emp}"
        "[Coordinator] Certificate Expiring - {emp}{days}"
        "[Coordinator] EXPIRED Certificate - {emp}"
        "[Coordinator] Certificate Update - {emp}"
"""

from __future__ import annotations

import pytest

from digest_builder import _strip_subject_prefix, _SUBJECT_PREFIXES


# ---------------------------------------------------------------------------
# Coordinator-variant stripping
# ---------------------------------------------------------------------------


def test_coordinator_overdue_strips_urgency_marker() -> None:
    """'[Coordinator] OVERDUE Hazmat - John Smith' must strip the OVERDUE
    marker, not just the bracketed '[Coordinator] ' prefix. Otherwise the
    output 'OVERDUE Hazmat - John Smith' duplicates the urgency tag under a
    section header that already reads 'OVERDUE REQUIREMENTS'."""
    assert (
        _strip_subject_prefix("[Coordinator] OVERDUE Hazmat - John Smith")
        == "Hazmat - John Smith"
    )


def test_coordinator_expired_certificate_strips_to_employee_name() -> None:
    """Coordinator CERTIFICATE_EXPIRED subjects use the literal 'EXPIRED
    Certificate - ' prefix (cert_name is not interpolated in this variant).
    Must strip to just the employee name."""
    assert (
        _strip_subject_prefix("[Coordinator] EXPIRED Certificate - John Smith")
        == "John Smith"
    )


def test_coordinator_upcoming_strips_urgency_marker() -> None:
    """Coordinator DUE SOON subject is '[Coordinator] Upcoming {cert} - {emp}
    ({days} days)'. After stripping, only the cert-and-employee segment remains."""
    assert (
        _strip_subject_prefix("[Coordinator] Upcoming Hazmat - John Smith (30 days)")
        == "Hazmat - John Smith (30 days)"
    )


def test_coordinator_certificate_expiring_strips_to_employee_name() -> None:
    """Coordinator CERTIFICATE_EXPIRING_SOON uses literal 'Certificate
    Expiring - '; cert_name does NOT appear in the subject."""
    assert (
        _strip_subject_prefix("[Coordinator] Certificate Expiring - John Smith (14 days)")
        == "John Smith (14 days)"
    )


def test_coordinator_certificate_update_strips_to_employee_name() -> None:
    """The else-branch coordinator Certificate Update variant."""
    assert (
        _strip_subject_prefix("[Coordinator] Certificate Update - John Smith")
        == "John Smith"
    )


def test_coordinator_generic_fallback_for_due_tomorrow() -> None:
    """'[Coordinator] {cert} Due Tomorrow - {emp}' starts with a variable
    cert_type_name, so no specific prefix matches. The generic '[Coordinator] '
    fallback must still apply."""
    assert (
        _strip_subject_prefix("[Coordinator] Hazmat Due Tomorrow - John Smith")
        == "Hazmat Due Tomorrow - John Smith"
    )


def test_coordinator_generic_fallback_for_requirement_update() -> None:
    """'[Coordinator] {cert} Update - {emp}' (else-branch of requirement-
    for-coordinator) also relies on the generic fallback."""
    assert (
        _strip_subject_prefix("[Coordinator] Hazmat Update - John Smith")
        == "Hazmat Update - John Smith"
    )


# ---------------------------------------------------------------------------
# Employee-side live prefixes — regression guard.
# ---------------------------------------------------------------------------


def test_employee_overdue_strips_colon_prefix() -> None:
    assert (
        _strip_subject_prefix("OVERDUE: Hazmat Requirement Past Due")
        == "Hazmat Requirement Past Due"
    )


def test_employee_expired_strips_colon_prefix() -> None:
    assert (
        _strip_subject_prefix("EXPIRED: Hazmat Has Expired")
        == "Hazmat Has Expired"
    )


# ---------------------------------------------------------------------------
# Ordering invariant — this is the tripwire that catches future edits that
# alphabetise or reorder the list and accidentally move "[Coordinator] "
# before the more-specific coordinator entries.
# ---------------------------------------------------------------------------


def test_generic_coordinator_fallback_is_last() -> None:
    """If the generic '[Coordinator] ' entry is not last, a coordinator
    subject with a specific marker (e.g. OVERDUE) would be stripped by the
    generic prefix first and the urgency marker would remain, reintroducing
    the Wave-2 bug."""
    assert _SUBJECT_PREFIXES[-1] == "[Coordinator] "
    # And the entry must appear exactly once.
    assert _SUBJECT_PREFIXES.count("[Coordinator] ") == 1


def test_no_dead_prefixes_with_colons_for_coordinator_markers() -> None:
    """The old list had '[Coordinator] OVERDUE: ' etc. with colons that no
    emitter ever produces. Guard against re-introduction."""
    dead = {
        "[Coordinator] OVERDUE: ",
        "[Coordinator] DUE TOMORROW: ",
        "[Coordinator] EXPIRED: ",
        "[Coordinator] EXPIRING SOON: ",
        "[Coordinator] DUE SOON: ",
        "[Coordinator] ESCALATION: ",
        "DUE TOMORROW: ",
        "EXPIRING SOON: ",
        "DUE SOON: ",
        "ESCALATION: ",
    }
    assert not (dead & set(_SUBJECT_PREFIXES)), (
        "re-introduced a prefix that never matches any subject emitted by "
        "notifications.py"
    )


# ---------------------------------------------------------------------------
# Unknown prefix — should pass through unchanged.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "Some unrelated subject",
        "Requirement Due Tomorrow: Hazmat",  # employee DUE_TOMORROW — no prefix defined, pass-through
        "Upcoming Requirement: Hazmat Due 2026-05-01 (30 days)",  # employee DUE_SOON — pass-through
        "Certificate Expiring Soon: Hazmat (14 days)",  # employee EXPIRING_SOON — pass-through
        "Certificate Update: Hazmat",  # employee else-branch — pass-through
    ],
)
def test_non_matching_subjects_pass_through_unchanged(subject: str) -> None:
    """Subjects we don't explicitly strip must be returned as-is (never
    mangled by a near-miss prefix)."""
    assert _strip_subject_prefix(subject) == subject
