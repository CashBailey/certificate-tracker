"""
Employee role assigner.

Assigns job roles to employees based on configured distribution percentages.
"""

import json
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from .data_loader import DataLoader, Employee


@dataclass
class RoleAssignment:
    """Assignment of a role to an employee."""

    employee_id: int
    employee_name: str
    employee_email: str
    role_id: str
    role_name: str
    required_certificates: list[str]
    hire_date: date
    tenure_profile: str  # 'new_hire', 'regular', 'long_tenured'
    compliance_profile: str  # 'fully_compliant', 'expiring_soon', etc.


@dataclass
class RoleConfig:
    """Configuration for a role."""

    id: str
    name: str
    description: str
    percentage: float
    required_certificates: list[str]


@dataclass
class ComplianceProfileConfig:
    """Configuration for a compliance profile."""

    id: str
    name: str
    percentage: float
    certificate_states: dict[str, float]


@dataclass
class TenureProfileConfig:
    """Configuration for a tenure profile."""

    id: str
    description: str
    percentage: float
    hire_date_range_days: tuple[int, int]


class EmployeeRoleAssigner:
    """
    Assigns roles to employees based on configured distributions.
    """

    def __init__(
        self,
        config_path: Optional[Path] = None,
        compliance_config_path: Optional[Path] = None,
        reference_date: Optional[date] = None,
        random_seed: Optional[int] = None,
    ):
        """
        Initialize the assigner.

        Args:
            config_path: Path to roles.json config
            compliance_config_path: Path to compliance_profiles.json
            reference_date: Reference date for calculations (default: today)
            random_seed: Random seed for reproducibility
        """
        base_path = Path(__file__).parent.parent
        self.config_path = config_path or base_path / "config" / "roles.json"
        self.compliance_config_path = (
            compliance_config_path or base_path / "config" / "compliance_profiles.json"
        )
        self.reference_date = reference_date or date.today()

        if random_seed is not None:
            random.seed(random_seed)

        # Load configurations
        self.roles: dict[str, RoleConfig] = {}
        self.certificates: dict[str, dict] = {}
        self.compliance_profiles: dict[str, ComplianceProfileConfig] = {}
        self.tenure_profiles: dict[str, TenureProfileConfig] = {}

        self._load_config()

    def _load_config(self) -> None:
        """Load role and compliance configurations."""
        # Load roles config
        with open(self.config_path) as f:
            config = json.load(f)

        for role_id, role_data in config["roles"].items():
            self.roles[role_id] = RoleConfig(
                id=role_id,
                name=role_data["name"],
                description=role_data["description"],
                percentage=role_data["percentage"],
                required_certificates=role_data["required_certificates"],
            )

        self.certificates = config["certificates"]

        # Load compliance profiles
        with open(self.compliance_config_path) as f:
            compliance_config = json.load(f)

        for profile_id, profile_data in compliance_config["compliance_profiles"].items():
            self.compliance_profiles[profile_id] = ComplianceProfileConfig(
                id=profile_id,
                name=profile_data["name"],
                percentage=profile_data["percentage"],
                certificate_states=profile_data["certificate_states"],
            )

        for tenure_id, tenure_data in compliance_config["tenure_profiles"].items():
            self.tenure_profiles[tenure_id] = TenureProfileConfig(
                id=tenure_id,
                description=tenure_data["description"],
                percentage=tenure_data["percentage"],
                hire_date_range_days=tuple(tenure_data["hire_date_range_days"]),
            )

    def _weighted_choice(self, items: dict[str, float]) -> str:
        """
        Make a weighted random choice.

        Args:
            items: Dict of item_id -> percentage/weight

        Returns:
            Selected item ID
        """
        total = sum(items.values())
        r = random.uniform(0, total)
        cumulative = 0
        for item_id, weight in items.items():
            cumulative += weight
            if r <= cumulative:
                return item_id
        return list(items.keys())[-1]  # Fallback to last item

    def _generate_hire_date(self, tenure_profile: str) -> date:
        """
        Generate a hire date based on tenure profile.

        Args:
            tenure_profile: Tenure profile ID

        Returns:
            Generated hire date
        """
        profile = self.tenure_profiles[tenure_profile]
        min_days, max_days = profile.hire_date_range_days

        days_ago = random.randint(min_days, max_days)
        return self.reference_date - timedelta(days=days_ago)

    def assign_roles(self, employees: list[Employee]) -> list[RoleAssignment]:
        """
        Assign roles to all employees.

        Args:
            employees: List of employees to assign roles to

        Returns:
            List of role assignments
        """
        assignments = []

        # Build weighted choice dicts
        role_weights = {r.id: r.percentage for r in self.roles.values()}
        compliance_weights = {
            p.id: p.percentage for p in self.compliance_profiles.values()
        }
        tenure_weights = {t.id: t.percentage for t in self.tenure_profiles.values()}

        for employee in employees:
            # Assign role
            role_id = self._weighted_choice(role_weights)
            role = self.roles[role_id]

            # Assign tenure profile
            tenure_profile = self._weighted_choice(tenure_weights)

            # Assign compliance profile
            compliance_profile = self._weighted_choice(compliance_weights)

            # Generate hire date
            hire_date = self._generate_hire_date(tenure_profile)

            assignment = RoleAssignment(
                employee_id=employee.id,
                employee_name=employee.full_name,
                employee_email=employee.email,
                role_id=role_id,
                role_name=role.name,
                required_certificates=role.required_certificates.copy(),
                hire_date=hire_date,
                tenure_profile=tenure_profile,
                compliance_profile=compliance_profile,
            )
            assignments.append(assignment)

        return assignments

    def get_certificate_info(self, cert_id: str) -> dict:
        """Get certificate configuration by ID."""
        return self.certificates.get(cert_id, {})

    def summary(self, assignments: list[RoleAssignment]) -> dict:
        """
        Generate summary statistics for assignments.

        Args:
            assignments: List of role assignments

        Returns:
            Summary dict
        """
        role_counts = {}
        compliance_counts = {}
        tenure_counts = {}
        total_certs = 0

        for assignment in assignments:
            role_counts[assignment.role_name] = (
                role_counts.get(assignment.role_name, 0) + 1
            )
            compliance_counts[assignment.compliance_profile] = (
                compliance_counts.get(assignment.compliance_profile, 0) + 1
            )
            tenure_counts[assignment.tenure_profile] = (
                tenure_counts.get(assignment.tenure_profile, 0) + 1
            )
            total_certs += len(assignment.required_certificates)

        return {
            "total_employees": len(assignments),
            "total_certificates_needed": total_certs,
            "avg_certs_per_employee": total_certs / len(assignments) if assignments else 0,
            "role_distribution": role_counts,
            "compliance_distribution": compliance_counts,
            "tenure_distribution": tenure_counts,
        }


def create_assigner_from_defaults(
    reference_date: Optional[date] = None,
    random_seed: Optional[int] = None,
) -> EmployeeRoleAssigner:
    """Create an assigner with default config paths."""
    return EmployeeRoleAssigner(
        reference_date=reference_date,
        random_seed=random_seed,
    )


if __name__ == "__main__":
    from .data_loader import create_loader_from_defaults

    print("=== Employee Role Assigner Test ===")

    # Load employees
    loader = create_loader_from_defaults()
    loader.load_employees()
    print(f"Loaded {len(loader.employees)} employees")

    # Create assigner with fixed seed for reproducibility
    assigner = create_assigner_from_defaults(
        reference_date=date(2026, 2, 4),
        random_seed=42,
    )

    # Assign roles
    assignments = assigner.assign_roles(loader.employees)
    print(f"Created {len(assignments)} role assignments")

    # Print summary
    summary = assigner.summary(assignments)
    print(f"\nSummary:")
    print(f"  Total employees: {summary['total_employees']}")
    print(f"  Total certs needed: {summary['total_certificates_needed']}")
    print(f"  Avg certs/employee: {summary['avg_certs_per_employee']:.1f}")

    print(f"\nRole distribution:")
    for role, count in sorted(summary['role_distribution'].items()):
        print(f"  {role}: {count} ({count/len(assignments)*100:.1f}%)")

    print(f"\nCompliance distribution:")
    for profile, count in sorted(summary['compliance_distribution'].items()):
        print(f"  {profile}: {count} ({count/len(assignments)*100:.1f}%)")

    print(f"\nTenure distribution:")
    for tenure, count in sorted(summary['tenure_distribution'].items()):
        print(f"  {tenure}: {count} ({count/len(assignments)*100:.1f}%)")

    # Show first 5 assignments
    print(f"\nFirst 5 assignments:")
    for a in assignments[:5]:
        print(f"  {a.employee_name}: {a.role_name} ({len(a.required_certificates)} certs)")
        print(f"    Hired: {a.hire_date}, Compliance: {a.compliance_profile}")
