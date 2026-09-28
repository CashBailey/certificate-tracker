"""
Certificate scheduler.

Plans certificate completion dates and states for each employee based on their
role requirements and compliance profile.
"""

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .employee_assigner import RoleAssignment


@dataclass
class ScheduledCertificate:
    """A scheduled certificate for an employee."""

    employee_id: int
    employee_name: str
    employee_email: str
    certificate_id: str
    certificate_name: str
    completion_date: Optional[date]
    expiration_date: Optional[date]
    state: str  # 'valid', 'expiring_soon', 'recently_expired', 'significantly_overdue', 'missing'
    should_generate: bool  # Whether to generate a certificate image
    days_until_expiry: Optional[int]  # Positive = not expired, negative = expired
    template_type: str  # 'lms_certificate', 'aha_bls', etc.


class CertificateScheduler:
    """
    Plans certificate dates and states based on employee assignments.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        compliance_config_path: Optional[Path] = None,
        expiration_config_path: Optional[Path] = None,
        reference_date: Optional[date] = None,
        random_seed: Optional[int] = None,
    ):
        """
        Initialize the scheduler.

        Args:
            config_path: Path to roles.json
            compliance_config_path: Path to compliance_profiles.json
            expiration_config_path: Path to expiration_distribution.json
            reference_date: Reference date for calculations
            random_seed: Random seed for reproducibility
        """
        base_path = Path(__file__).parent.parent
        self.config_path = config_path or base_path / "config" / "roles.json"
        self.compliance_config_path = (
            compliance_config_path or base_path / "config" / "compliance_profiles.json"
        )
        self.expiration_config_path = (
            expiration_config_path or base_path / "config" / "expiration_distribution.json"
        )
        self.reference_date = reference_date or date.today()

        if random_seed is not None:
            random.seed(random_seed)

        self._load_config()

    def _load_config(self) -> None:
        """Load configurations."""
        with open(self.config_path) as f:
            config = json.load(f)
        self.certificates = config["certificates"]

        with open(self.compliance_config_path) as f:
            compliance_config = json.load(f)
        self.compliance_profiles = compliance_config["compliance_profiles"]
        self.state_definitions = compliance_config["certificate_state_definitions"]

        with open(self.expiration_config_path) as f:
            expiration_config = json.load(f)
        self.monthly_distribution = expiration_config["monthly_distribution"]

    def _weighted_choice(self, items: dict[str, float]) -> str:
        """Make a weighted random choice."""
        total = sum(items.values())
        if total == 0:
            return list(items.keys())[0]
        r = random.uniform(0, total)
        cumulative = 0
        for item_id, weight in items.items():
            cumulative += weight
            if r <= cumulative:
                return item_id
        return list(items.keys())[-1]

    def _pick_expiration_month(self) -> int:
        """Pick a month based on distribution."""
        month_weights = {
            1: self.monthly_distribution["january"]["percentage"],
            2: self.monthly_distribution["february"]["percentage"],
            3: self.monthly_distribution["march"]["percentage"],
            4: self.monthly_distribution["april"]["percentage"],
            5: self.monthly_distribution["may"]["percentage"],
            6: self.monthly_distribution["june"]["percentage"],
            7: self.monthly_distribution["july"]["percentage"],
            8: self.monthly_distribution["august"]["percentage"],
            9: self.monthly_distribution["september"]["percentage"],
            10: self.monthly_distribution["october"]["percentage"],
            11: self.monthly_distribution["november"]["percentage"],
            12: self.monthly_distribution["december"]["percentage"],
        }
        return int(self._weighted_choice({str(k): v for k, v in month_weights.items()}))

    def _generate_expiration_date(
        self,
        state: str,
        validity_days: Optional[int],
    ) -> Optional[date]:
        """
        Generate an expiration date based on state and validity period.

        Args:
            state: Certificate state ('valid', 'expiring_soon', etc.)
            validity_days: Validity period in days (None = never expires)

        Returns:
            Expiration date or None
        """
        if validity_days is None:
            return None  # Never expires

        # Pick a month for the expiration
        month = self._pick_expiration_month()

        # Pick a day (prefer 1st, 15th, end of month)
        day_choice = random.random()
        if day_choice < 0.15:
            day = 1
        elif day_choice < 0.25:
            day = 15
        elif day_choice < 0.45:
            day = random.choice([28, 29, 30])
        else:
            day = random.randint(1, 28)

        # Determine year based on state
        if state == "valid":
            # Expires 31+ days from now
            days_from_now = random.randint(31, 365)
            base_date = self.reference_date + timedelta(days=days_from_now)
        elif state == "expiring_soon":
            # Expires within 30 days
            days_from_now = random.randint(1, 30)
            base_date = self.reference_date + timedelta(days=days_from_now)
        elif state == "recently_expired":
            # Expired within last 90 days
            days_ago = random.randint(1, 90)
            base_date = self.reference_date - timedelta(days=days_ago)
        elif state == "significantly_overdue":
            # Expired 91+ days ago
            days_ago = random.randint(91, 365)
            base_date = self.reference_date - timedelta(days=days_ago)
        else:
            # Default to valid
            days_from_now = random.randint(31, 365)
            base_date = self.reference_date + timedelta(days=days_from_now)

        # Use the target month but keep a similar year
        try:
            expiration_date = date(base_date.year, month, min(day, 28))
        except ValueError:
            expiration_date = date(base_date.year, month, 28)

        return expiration_date

    def _calculate_completion_date(
        self,
        expiration_date: Optional[date],
        validity_days: Optional[int],
    ) -> Optional[date]:
        """
        Calculate completion date from expiration date.

        Args:
            expiration_date: When the certificate expires
            validity_days: Validity period in days

        Returns:
            Completion date
        """
        if expiration_date is None:
            # Never expires - pick a random past date
            days_ago = random.randint(30, 1825)  # 30 days to 5 years ago
            return self.reference_date - timedelta(days=days_ago)

        if validity_days is None:
            # One-time completion
            days_ago = random.randint(30, 1825)
            return self.reference_date - timedelta(days=days_ago)

        # Completion date = expiration - validity period
        return expiration_date - timedelta(days=validity_days)

    def schedule_certificates(
        self,
        assignments: list[RoleAssignment],
    ) -> list[ScheduledCertificate]:
        """
        Schedule certificates for all employee assignments.

        Args:
            assignments: List of role assignments

        Returns:
            List of scheduled certificates
        """
        scheduled = []

        for assignment in assignments:
            # Get compliance profile state distribution
            profile = self.compliance_profiles[assignment.compliance_profile]
            state_weights = profile["certificate_states"]

            for cert_id in assignment.required_certificates:
                cert_config = self.certificates.get(cert_id, {})
                cert_name = cert_config.get("name", cert_id)
                validity_days = cert_config.get("validity_days")
                template_type = cert_config.get("template", "lms_certificate")

                # Determine certificate state based on compliance profile
                state = self._weighted_choice(state_weights)

                # Handle missing certificates
                if state == "missing":
                    scheduled.append(
                        ScheduledCertificate(
                            employee_id=assignment.employee_id,
                            employee_name=assignment.employee_name,
                            employee_email=assignment.employee_email,
                            certificate_id=cert_id,
                            certificate_name=cert_name,
                            completion_date=None,
                            expiration_date=None,
                            state="missing",
                            should_generate=False,
                            days_until_expiry=None,
                            template_type=template_type,
                        )
                    )
                    continue

                # Generate dates
                expiration_date = self._generate_expiration_date(state, validity_days)
                completion_date = self._calculate_completion_date(
                    expiration_date, validity_days
                )

                # Calculate days until expiry
                if expiration_date:
                    days_until_expiry = (expiration_date - self.reference_date).days
                else:
                    days_until_expiry = None

                scheduled.append(
                    ScheduledCertificate(
                        employee_id=assignment.employee_id,
                        employee_name=assignment.employee_name,
                        employee_email=assignment.employee_email,
                        certificate_id=cert_id,
                        certificate_name=cert_name,
                        completion_date=completion_date,
                        expiration_date=expiration_date,
                        state=state,
                        should_generate=True,
                        days_until_expiry=days_until_expiry,
                        template_type=template_type,
                    )
                )

        return scheduled

    def summary(self, scheduled: list[ScheduledCertificate]) -> dict:
        """
        Generate summary statistics.

        Args:
            scheduled: List of scheduled certificates

        Returns:
            Summary dict
        """
        state_counts = {}
        template_counts = {}
        to_generate = 0
        missing = 0

        for cert in scheduled:
            state_counts[cert.state] = state_counts.get(cert.state, 0) + 1
            template_counts[cert.template_type] = (
                template_counts.get(cert.template_type, 0) + 1
            )
            if cert.should_generate:
                to_generate += 1
            if cert.state == "missing":
                missing += 1

        return {
            "total_scheduled": len(scheduled),
            "to_generate": to_generate,
            "missing": missing,
            "state_distribution": state_counts,
            "template_distribution": template_counts,
        }


def create_scheduler_from_defaults(
    reference_date: Optional[date] = None,
    random_seed: Optional[int] = None,
) -> CertificateScheduler:
    """Create a scheduler with default config paths."""
    return CertificateScheduler(
        reference_date=reference_date,
        random_seed=random_seed,
    )


if __name__ == "__main__":
    from .data_loader import create_loader_from_defaults
    from .employee_assigner import create_assigner_from_defaults

    print("=== Certificate Scheduler Test ===")

    # Load employees
    loader = create_loader_from_defaults()
    loader.load_employees()

    # Assign roles
    assigner = create_assigner_from_defaults(
        reference_date=date(2026, 2, 4),
        random_seed=42,
    )
    assignments = assigner.assign_roles(loader.employees)

    # Schedule certificates
    scheduler = create_scheduler_from_defaults(
        reference_date=date(2026, 2, 4),
        random_seed=42,
    )
    scheduled = scheduler.schedule_certificates(assignments)

    # Print summary
    summary = scheduler.summary(scheduled)
    print(f"\nSummary:")
    print(f"  Total scheduled: {summary['total_scheduled']}")
    print(f"  To generate: {summary['to_generate']}")
    print(f"  Missing: {summary['missing']}")

    print(f"\nState distribution:")
    for state, count in sorted(summary['state_distribution'].items()):
        pct = count / summary['total_scheduled'] * 100
        print(f"  {state}: {count} ({pct:.1f}%)")

    print(f"\nTemplate distribution:")
    for template, count in sorted(summary['template_distribution'].items()):
        pct = count / summary['total_scheduled'] * 100
        print(f"  {template}: {count} ({pct:.1f}%)")

    # Show first 10 certificates
    print(f"\nFirst 10 certificates:")
    for cert in scheduled[:10]:
        exp_str = cert.expiration_date.strftime("%Y-%m-%d") if cert.expiration_date else "Never"
        comp_str = cert.completion_date.strftime("%Y-%m-%d") if cert.completion_date else "N/A"
        days_str = f"{cert.days_until_expiry:+d}" if cert.days_until_expiry is not None else "N/A"
        print(f"  {cert.employee_name[:20]:20s} | {cert.certificate_name[:30]:30s}")
        print(f"    State: {cert.state:20s} | Completed: {comp_str} | Expires: {exp_str} ({days_str} days)")
