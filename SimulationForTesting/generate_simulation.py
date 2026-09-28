#!/usr/bin/env python3
"""
Certificate Simulation Generator

Generates realistic test certificates for the City of Laredo Public Health
Department certificate management system.

Usage:
    python generate_simulation.py [options]

Options:
    --output DIR        Output directory (default: ./output)
    --seed INT          Random seed for reproducibility
    --limit INT         Limit number of certificates to generate
    --reference-date    Reference date YYYY-MM-DD (default: today)
"""

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional


def _name_to_filename_part(full_name: str) -> str:
    """Convert 'First Last' to 'first_last' for use in filenames."""
    name = full_name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    return name.strip("_")

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from lib.data_loader import create_loader_from_defaults
from lib.employee_assigner import create_assigner_from_defaults, RoleAssignment
from lib.certificate_scheduler import create_scheduler_from_defaults, ScheduledCertificate
from generators.certificate_generator import CertificateGenerator


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate test certificates for simulation"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "output",
        help="Output directory",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of certificates to generate",
    )
    parser.add_argument(
        "--reference-date",
        type=str,
        default=None,
        help="Reference date YYYY-MM-DD",
    )
    parser.add_argument(
        "--start-employee",
        type=int,
        default=None,
        help="Start employee ID for parallel processing",
    )
    parser.add_argument(
        "--end-employee",
        type=int,
        default=None,
        help="End employee ID for parallel processing",
    )
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Only generate images, skip CSV/JSON output",
    )
    return parser.parse_args()


def write_manifest(
    scheduled: list[ScheduledCertificate],
    output_path: Path,
) -> None:
    """
    Write manifest CSV with certificate metadata.

    Args:
        scheduled: List of scheduled certificates
        output_path: Path to write manifest
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "filename",
            "employee_id",
            "employee_name",
            "employee_email",
            "certificate_id",
            "certificate_name",
            "completion_date",
            "expiration_date",
            "state",
            "days_until_expiry",
            "template_type",
        ])

        for cert in scheduled:
            if not cert.should_generate:
                continue

            filename = f"{_name_to_filename_part(cert.employee_name)}_{cert.certificate_id}.png"
            writer.writerow([
                filename,
                cert.employee_id,
                cert.employee_name,
                cert.employee_email,
                cert.certificate_id,
                cert.certificate_name,
                cert.completion_date.strftime("%m/%d/%Y") if cert.completion_date else "",
                cert.expiration_date.strftime("%m/%d/%Y") if cert.expiration_date else "",
                cert.state,
                cert.days_until_expiry if cert.days_until_expiry is not None else "",
                cert.template_type,
            ])


def write_employee_assignments(
    assignments: list[RoleAssignment],
    output_path: Path,
) -> None:
    """
    Write employee assignments CSV.

    Args:
        assignments: List of role assignments
        output_path: Path to write CSV
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "employee_id",
            "employee_name",
            "employee_email",
            "role_id",
            "role_name",
            "hire_date",
            "tenure_profile",
            "compliance_profile",
            "required_certificates",
        ])

        for a in assignments:
            writer.writerow([
                a.employee_id,
                a.employee_name,
                a.employee_email,
                a.role_id,
                a.role_name,
                a.hire_date.strftime("%Y-%m-%d"),
                a.tenure_profile,
                a.compliance_profile,
                ";".join(a.required_certificates),
            ])


def write_compliance_summary(
    assignments: list[RoleAssignment],
    scheduled: list[ScheduledCertificate],
    output_path: Path,
) -> None:
    """
    Write compliance summary CSV.

    Args:
        assignments: Role assignments
        scheduled: Scheduled certificates
        output_path: Path to write CSV
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build per-employee stats
    employee_stats = {}
    for a in assignments:
        employee_stats[a.employee_id] = {
            "employee_id": a.employee_id,
            "employee_name": a.employee_name,
            "total_required": len(a.required_certificates),
            "total_completed": 0,
            "valid_count": 0,
            "expiring_count": 0,
            "expired_count": 0,
            "missing_count": 0,
        }

    for cert in scheduled:
        stats = employee_stats.get(cert.employee_id)
        if not stats:
            continue

        if cert.state == "valid":
            stats["valid_count"] += 1
            stats["total_completed"] += 1
        elif cert.state == "expiring_soon":
            stats["expiring_count"] += 1
            stats["total_completed"] += 1
        elif cert.state in ("recently_expired", "significantly_overdue"):
            stats["expired_count"] += 1
            stats["total_completed"] += 1
        elif cert.state == "missing":
            stats["missing_count"] += 1

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "employee_id",
            "employee_name",
            "total_required",
            "total_completed",
            "valid_count",
            "expiring_count",
            "expired_count",
            "missing_count",
            "compliance_rate",
        ])

        for stats in employee_stats.values():
            compliance_rate = (
                stats["valid_count"] / stats["total_required"] * 100
                if stats["total_required"] > 0
                else 0
            )
            writer.writerow([
                stats["employee_id"],
                stats["employee_name"],
                stats["total_required"],
                stats["total_completed"],
                stats["valid_count"],
                stats["expiring_count"],
                stats["expired_count"],
                stats["missing_count"],
                f"{compliance_rate:.1f}%",
            ])


def write_simulation_report(
    assignments: list[RoleAssignment],
    scheduled: list[ScheduledCertificate],
    generated_count: int,
    output_path: Path,
    reference_date: date,
    seed: int,
) -> None:
    """
    Write simulation report JSON.

    Args:
        assignments: Role assignments
        scheduled: Scheduled certificates
        generated_count: Number of certificates generated
        output_path: Path to write report
        reference_date: Reference date used
        seed: Random seed used
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Calculate statistics
    role_counts = {}
    compliance_counts = {}
    state_counts = {}
    template_counts = {}

    for a in assignments:
        role_counts[a.role_name] = role_counts.get(a.role_name, 0) + 1
        compliance_counts[a.compliance_profile] = (
            compliance_counts.get(a.compliance_profile, 0) + 1
        )

    for cert in scheduled:
        state_counts[cert.state] = state_counts.get(cert.state, 0) + 1
        template_counts[cert.template_type] = (
            template_counts.get(cert.template_type, 0) + 1
        )

    report = {
        "generated_at": datetime.now().isoformat(),
        "reference_date": reference_date.isoformat(),
        "random_seed": seed,
        "summary": {
            "total_employees": len(assignments),
            "total_certificates_scheduled": len(scheduled),
            "certificates_generated": generated_count,
            "certificates_missing": sum(1 for c in scheduled if c.state == "missing"),
        },
        "role_distribution": role_counts,
        "compliance_distribution": compliance_counts,
        "state_distribution": state_counts,
        "template_distribution": template_counts,
    }

    with open(output_path, "w") as f:
        json.dump(report, f, indent=2)


def main() -> None:
    """Main entry point."""
    args = parse_args()

    # Parse reference date
    if args.reference_date:
        reference_date = datetime.strptime(args.reference_date, "%Y-%m-%d").date()
    else:
        reference_date = date(2026, 2, 4)  # Default to current project date

    print("=" * 60)
    print("Certificate Simulation Generator")
    print("=" * 60)
    print(f"Output directory: {args.output}")
    print(f"Random seed: {args.seed}")
    print(f"Reference date: {reference_date}")
    if args.limit:
        print(f"Limit: {args.limit} certificates")
    print()

    # Step 1: Load employee data
    print("Step 1: Loading employee data...")
    loader = create_loader_from_defaults()
    loader.load_all()
    print(f"  Loaded {len(loader.employees)} employees")
    print(f"  Loaded {len(loader.courses)} courses")

    # Step 2: Assign roles
    print("\nStep 2: Assigning roles to employees...")
    assigner = create_assigner_from_defaults(
        reference_date=reference_date,
        random_seed=args.seed,
    )
    assignments = assigner.assign_roles(loader.employees)
    summary = assigner.summary(assignments)
    print(f"  Total certificates needed: {summary['total_certificates_needed']}")
    print(f"  Avg per employee: {summary['avg_certs_per_employee']:.1f}")

    # Step 3: Schedule certificates
    print("\nStep 3: Scheduling certificates...")
    scheduler = create_scheduler_from_defaults(
        reference_date=reference_date,
        random_seed=args.seed,
    )
    scheduled = scheduler.schedule_certificates(assignments)
    sched_summary = scheduler.summary(scheduled)
    print(f"  Total scheduled: {sched_summary['total_scheduled']}")
    print(f"  To generate: {sched_summary['to_generate']}")
    print(f"  Missing: {sched_summary['missing']}")

    # Step 4: Generate certificate images
    print("\nStep 4: Generating certificate images...")
    generator = CertificateGenerator()
    output_dir = args.output / "certificates"
    output_dir.mkdir(parents=True, exist_ok=True)

    to_generate = [c for c in scheduled if c.should_generate]

    # Filter by employee ID range for parallel processing
    if args.start_employee is not None and args.end_employee is not None:
        to_generate = [c for c in to_generate
                       if args.start_employee <= c.employee_id <= args.end_employee]
        print(f"  Filtering employees {args.start_employee}-{args.end_employee}: {len(to_generate)} certificates")

    if args.limit:
        to_generate = to_generate[:args.limit]

    generated_count = 0
    for i, cert in enumerate(to_generate):
        if i % 500 == 0:
            print(f"  Generated {i}/{len(to_generate)} certificates...")

        filename = f"{_name_to_filename_part(cert.employee_name)}_{cert.certificate_id}.png"
        output_path = output_dir / filename

        try:
            generator.generate_and_save(
                name=cert.employee_name,
                course=cert.certificate_name,
                completion_date=cert.completion_date,
                output_path=output_path,
            )
            generated_count += 1
        except Exception as e:
            print(f"  Error generating {filename}: {e}")

    print(f"  Generated {generated_count} certificates")

    # Step 5: Write output files (skip if --images-only for parallel workers)
    if args.images_only:
        print("\nSkipping CSV/JSON output (--images-only mode)")
        print("\n" + "=" * 60)
        print(f"Worker complete! Generated {generated_count} certificates")
        print("=" * 60)
        return

    print("\nStep 5: Writing output files...")

    manifest_path = args.output / "manifest.csv"
    write_manifest(scheduled, manifest_path)
    print(f"  Wrote manifest: {manifest_path}")

    assignments_path = args.output / "employee_assignments.csv"
    write_employee_assignments(assignments, assignments_path)
    print(f"  Wrote assignments: {assignments_path}")

    compliance_path = args.output / "compliance_summary.csv"
    write_compliance_summary(assignments, scheduled, compliance_path)
    print(f"  Wrote compliance: {compliance_path}")

    report_path = args.output / "simulation_report.json"
    write_simulation_report(
        assignments, scheduled, generated_count, report_path, reference_date, args.seed
    )
    print(f"  Wrote report: {report_path}")

    # Done
    print("\n" + "=" * 60)
    print("Simulation complete!")
    print(f"  Generated {generated_count} certificate images")
    print(f"  Output directory: {args.output}")
    print("=" * 60)


if __name__ == "__main__":
    main()
