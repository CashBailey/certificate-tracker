"""
Data loader for simulation input files.

Loads employee and course data from Excel files.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd


@dataclass
class Employee:
    """Employee data from Excel."""

    id: int
    first_name: str
    middle_name: Optional[str]
    last_name: str
    suffix: Optional[str]
    gender: str
    email: str

    @property
    def full_name(self) -> str:
        """Build full name from components."""
        parts = [self.first_name]
        if self.middle_name:
            parts.append(self.middle_name)
        parts.append(self.last_name)
        if self.suffix:
            parts.append(self.suffix)
        return " ".join(parts)

    @property
    def formal_name(self) -> str:
        """Formal name: First Last (no middle, no suffix)."""
        return f"{self.first_name} {self.last_name}"

    @property
    def abbreviated_name(self) -> str:
        """Abbreviated: F. Last."""
        return f"{self.first_name[0]}. {self.last_name}"

    def name_variation(self, style: str = "full") -> str:
        """
        Get name in various styles for testing name matching.

        Args:
            style: One of 'full', 'formal', 'abbreviated', 'first_middle_last',
                   'last_first', 'initials'

        Returns:
            Name in requested style
        """
        if style == "full":
            return self.full_name
        elif style == "formal":
            return self.formal_name
        elif style == "abbreviated":
            return self.abbreviated_name
        elif style == "first_middle_last":
            if self.middle_name:
                return f"{self.first_name} {self.middle_name} {self.last_name}"
            return self.formal_name
        elif style == "last_first":
            return f"{self.last_name}, {self.first_name}"
        elif style == "initials":
            initials = self.first_name[0]
            if self.middle_name:
                initials += self.middle_name[0]
            return f"{initials}. {self.last_name}"
        else:
            return self.full_name


@dataclass
class Course:
    """Training course data from Excel."""

    id: int
    name: str
    renewal_periodicity: str
    validity_days: Optional[int] = None

    def __post_init__(self):
        """Parse validity days from renewal periodicity text."""
        if self.validity_days is None:
            self.validity_days = self._parse_validity()

    def _parse_validity(self) -> Optional[int]:
        """Parse validity period from renewal text."""
        text = self.renewal_periodicity.lower()

        # Check for no expiration
        if "no expiration" in text or "one-time" in text:
            return None

        # Look for "every X years" pattern
        year_match = re.search(r"every\s+(\d+)\s+years?", text)
        if year_match:
            years = int(year_match.group(1))
            return years * 365

        # Look for "X years" pattern
        year_match2 = re.search(r"(\d+)\s+years?", text)
        if year_match2:
            years = int(year_match2.group(1))
            return years * 365

        # Check for annual
        if "annual" in text:
            return 365

        # Default to 2 years if can't parse
        return 730


@dataclass
class DataLoader:
    """Loads simulation data from Excel files."""

    employees_path: Path
    courses_path: Path
    employees: list[Employee] = field(default_factory=list)
    courses: list[Course] = field(default_factory=list)

    def load_all(self) -> None:
        """Load all data files."""
        self.load_employees()
        self.load_courses()

    def load_employees(self) -> list[Employee]:
        """
        Load employees from Excel file.

        Expected columns: FirstName, MiddleName, LastName, Suffix, Gender, Email
        """
        df = pd.read_excel(self.employees_path)

        self.employees = []
        for idx, row in df.iterrows():
            employee = Employee(
                id=idx + 1,  # 1-based ID
                first_name=str(row.get("FirstName", "")).strip(),
                middle_name=self._clean_optional(row.get("MiddleName")),
                last_name=str(row.get("LastName", "")).strip(),
                suffix=self._clean_optional(row.get("Suffix")),
                gender=str(row.get("Gender", "")).strip(),
                email=str(row.get("Email", "")).strip(),
            )
            self.employees.append(employee)

        return self.employees

    def load_courses(self) -> list[Course]:
        """
        Load courses from Excel file.

        Expected columns: Course / Training Name, Renewal / Periodicity
        """
        df = pd.read_excel(self.courses_path)

        self.courses = []
        for idx, row in df.iterrows():
            course = Course(
                id=idx + 1,
                name=str(row.get("Course / Training Name", "")).strip(),
                renewal_periodicity=str(row.get("Renewal / Periodicity", "")).strip(),
            )
            self.courses.append(course)

        return self.courses

    def _clean_optional(self, value) -> Optional[str]:
        """Clean optional string value, returning None for empty/NaN."""
        if pd.isna(value):
            return None
        cleaned = str(value).strip()
        return cleaned if cleaned else None

    def get_employee_by_id(self, employee_id: int) -> Optional[Employee]:
        """Get employee by ID."""
        for emp in self.employees:
            if emp.id == employee_id:
                return emp
        return None

    def get_course_by_name(self, name: str) -> Optional[Course]:
        """Get course by name (case-insensitive partial match)."""
        name_lower = name.lower()
        for course in self.courses:
            if name_lower in course.name.lower():
                return course
        return None

    def summary(self) -> dict:
        """Get summary statistics."""
        return {
            "total_employees": len(self.employees),
            "total_courses": len(self.courses),
            "employees_with_middle_name": sum(
                1 for e in self.employees if e.middle_name
            ),
            "employees_with_suffix": sum(1 for e in self.employees if e.suffix),
            "courses_with_expiration": sum(
                1 for c in self.courses if c.validity_days is not None
            ),
            "courses_no_expiration": sum(
                1 for c in self.courses if c.validity_days is None
            ),
        }


def create_loader_from_defaults() -> DataLoader:
    """Create a data loader with default file paths."""
    base_path = Path(__file__).parent.parent
    return DataLoader(
        employees_path=base_path / "laredo_test_employees_2000_full.xlsx",
        courses_path=base_path / "City_of_Laredo_Public_Health_Training_Periodicity.xlsx",
    )


if __name__ == "__main__":
    # Test the loader
    loader = create_loader_from_defaults()
    loader.load_all()

    print("=== Data Loader Test ===")
    print(f"\nSummary: {loader.summary()}")

    print("\nFirst 5 employees:")
    for emp in loader.employees[:5]:
        print(f"  {emp.id}: {emp.full_name} ({emp.email})")

    print("\nAll courses:")
    for course in loader.courses:
        validity = f"{course.validity_days} days" if course.validity_days else "Never expires"
        print(f"  {course.id}: {course.name[:50]}... - {validity}")
