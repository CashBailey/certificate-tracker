"""
Digest email builder for the notification system.

Takes a batch of NotificationEvent objects for a single recipient and produces
a formatted plain-text digest email (subject + body).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.models import NotificationEvent

# Notification types in display priority order (most urgent first)
_SECTION_ORDER = [
    "RequirementOverdue",
    "RequirementDueTomorrow",
    "CertificateExpired",
    "RequirementDueSoon",
    "CertificateExpiringSoon",
    "RequirementEscalation",
]

_SECTION_TITLES = {
    "RequirementOverdue": "OVERDUE REQUIREMENTS",
    "RequirementDueTomorrow": "DUE TOMORROW",
    "CertificateExpired": "EXPIRED CERTIFICATES",
    "RequirementDueSoon": "REQUIREMENTS DUE SOON",
    "CertificateExpiringSoon": "CERTIFICATES EXPIRING SOON",
    "RequirementEscalation": "ESCALATIONS",
}

_SECTION_ACTION = {
    "RequirementOverdue": "Please contact your manager and submit immediately.",
    "RequirementDueTomorrow": "Please upload your certificate document today.",
    "CertificateExpired": "Begin renewal process immediately.",
    "RequirementDueSoon": None,  # handled inline with date
    "CertificateExpiringSoon": None,
    "RequirementEscalation": "Immediate action required.",
}

# Prefixes to strip from subject lines to get the item name.
#
# Order matters: entries are checked top-to-bottom and the first match wins, so
# MORE-SPECIFIC prefixes must come before LESS-SPECIFIC ones. In particular, every
# specific "[Coordinator] <marker> " entry must appear before the generic
# "[Coordinator] " fallback, otherwise the fallback swallows the subject early
# and leaves the urgency marker (e.g. "OVERDUE ") sitting in front of the item
# name inside a section that already says "OVERDUE REQUIREMENTS" — a duplicated,
# ugly output.
#
# Previous versions of this list contained 11 entries that looked plausible
# (e.g. "DUE TOMORROW: ", "[Coordinator] OVERDUE: ") but did NOT match any
# subject actually emitted by notifications.py. As a result, every coordinator
# subject fell through to the generic "[Coordinator] " fallback and the
# urgency marker was not stripped — a real digest-formatting bug. The list
# below only contains prefixes that match subjects actually produced by
# notifications._build_requirement_message{,_for_coordinator} and
# notifications._build_certificate_message{,_for_coordinator}.
_SUBJECT_PREFIXES = [
    # Coordinator-specific markers (most specific first, no colons — matches
    # the exact emission format used by notifications.py).
    "[Coordinator] OVERDUE ",          # "[Coordinator] OVERDUE {cert} - {emp}"
    "[Coordinator] EXPIRED Certificate - ",  # "[Coordinator] EXPIRED Certificate - {emp}"
    "[Coordinator] Upcoming ",         # "[Coordinator] Upcoming {cert} - {emp}{days}"
    "[Coordinator] Certificate Expiring - ",  # "[Coordinator] Certificate Expiring - {emp}{days}"
    "[Coordinator] Certificate Update - ",    # "[Coordinator] Certificate Update - {emp}"
    # Employee-side live prefixes.
    "OVERDUE: ",                       # "OVERDUE: {cert} Requirement Past Due"
    "EXPIRED: ",                       # "EXPIRED: {cert} Has Expired"
    # Generic coordinator fallback — MUST stay last. Catches the variants
    # where the cert_type_name comes first after "[Coordinator] "
    # (e.g. "[Coordinator] {cert} Due Tomorrow - {emp}",
    #       "[Coordinator] {cert} Update - {emp}").
    "[Coordinator] ",
]


def _strip_subject_prefix(subject: str) -> str:
    """Strip known prefixes from notification subject to get item name."""
    for prefix in _SUBJECT_PREFIXES:
        if subject.startswith(prefix):
            return subject[len(prefix):]
    return subject


def _days_until(target: date | None, today: date) -> int | None:
    """Return days from today to target date, or None if no date."""
    if target is None:
        return None
    return (target - today).days


def _urgency_bucket(days: int | None) -> str:
    """Categorize days remaining into urgency buckets."""
    if days is None:
        return "Unknown timeline"
    if days <= 30:
        return "Within 30 days"
    if days <= 60:
        return "Within 60 days"
    return "Within 90 days"


def build_digest_email(
    notifications: list[NotificationEvent],
    employee_name: str,
    is_coordinator: bool = False,
) -> tuple[str, str]:
    """
    Build a digest email from a batch of notifications for one recipient.

    Returns (subject, body) tuple. Plain text only.
    """
    if not notifications:
        return ("", "")

    today = date.today()
    today_str = today.strftime("%B %d, %Y").replace(" 0", " ")
    total = len(notifications)

    # Group by notification type
    by_type: dict[str, list[NotificationEvent]] = defaultdict(list)
    for n in notifications:
        by_type[n.notification_type.value if hasattr(n.notification_type, 'value') else str(n.notification_type)].append(n)

    # Build subject line
    if is_coordinator:
        subject = f"[Coordinator] Compliance Digest - {today_str} ({total} items)"
    else:
        subject = f"[Action Required] Your Certificate Compliance Digest - {today_str}"

    # Build body
    lines: list[str] = []
    lines.append("=" * 50)
    lines.append("Certificate Compliance Digest")
    lines.append(today_str)
    lines.append("=" * 50)
    lines.append("")

    # Summary counts
    lines.append(f"You have {total} item{'s' if total != 1 else ''} requiring attention:")
    for ntype in _SECTION_ORDER:
        if ntype in by_type:
            count = len(by_type[ntype])
            title = _SECTION_TITLES[ntype].lower()
            lines.append(f"  - {count} {title}")
    # Any types not in the order list
    for ntype in by_type:
        if ntype not in _SECTION_ORDER:
            count = len(by_type[ntype])
            lines.append(f"  - {count} {ntype}")
    lines.append("")

    # Detail sections
    for ntype in _SECTION_ORDER:
        if ntype not in by_type:
            continue

        batch = by_type[ntype]
        title = _SECTION_TITLES[ntype]
        action = _SECTION_ACTION.get(ntype)

        lines.append("-" * 50)
        lines.append(f"{title} ({len(batch)})")
        lines.append("-" * 50)
        lines.append("")

        if ntype in ("RequirementDueSoon", "CertificateExpiringSoon"):
            # Group by urgency bucket
            by_bucket: dict[str, list[NotificationEvent]] = defaultdict(list)
            for n in batch:
                bucket = _urgency_bucket(_days_until(n.effective_date, today))
                by_bucket[bucket].append(n)

            for bucket in ["Within 30 days", "Within 60 days", "Within 90 days", "Unknown timeline"]:
                if bucket not in by_bucket:
                    continue
                lines.append(f"  {bucket}:")
                for n in by_bucket[bucket]:
                    # For coordinators, the subject already contains the
                    # employee name after prefix stripping (e.g.,
                    # "[Coordinator] DUE SOON Hazmat - John Smith"
                    # becomes "Hazmat - John Smith").
                    item_name = _strip_subject_prefix(n.subject)
                    date_label = "due" if "DueSoon" in ntype else "expires"
                    date_str = n.effective_date.isoformat() if n.effective_date else "unknown"
                    lines.append(f"    * {item_name} - {date_label} {date_str}")
                lines.append("")
        else:
            # Standard list. For coordinators, the employee name is
            # already embedded in the subject after prefix stripping.
            for n in batch:
                item_name = _strip_subject_prefix(n.subject)
                lines.append(f"  * {item_name}")

                # Date line
                if ntype == "RequirementOverdue":
                    date_str = n.effective_date.isoformat() if n.effective_date else "unknown"
                    lines.append(f"    Was due: {date_str}")
                elif ntype == "RequirementDueTomorrow":
                    date_str = n.effective_date.isoformat() if n.effective_date else "unknown"
                    lines.append(f"    Due: {date_str}")
                elif ntype == "CertificateExpired":
                    date_str = n.effective_date.isoformat() if n.effective_date else "unknown"
                    lines.append(f"    Expired: {date_str}")

                if action:
                    lines.append(f"    {action}")
                lines.append("")

    # Any types not in the standard order
    for ntype in by_type:
        if ntype in _SECTION_ORDER:
            continue
        batch = by_type[ntype]
        lines.append("-" * 50)
        lines.append(f"{ntype.upper()} ({len(batch)})")
        lines.append("-" * 50)
        lines.append("")
        for n in batch:
            item_name = _strip_subject_prefix(n.subject)
            lines.append(f"  * {item_name}")
            lines.append("")

    # Footer
    lines.append("=" * 50)
    lines.append("This is an automated message from the City of Laredo")
    lines.append("Certificate Management System. Do not reply.")
    lines.append("All dates shown in Central Time (America/Chicago).")
    lines.append("=" * 50)

    body = "\n".join(lines)
    return subject, body
