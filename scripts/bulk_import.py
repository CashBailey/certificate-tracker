#!/usr/bin/env python3
"""
Day-One Bulk Import: Load employees, certificates, and requirements
into the system as pre-verified records, bypassing extraction and review.

This is a DATA MIGRATION tool for historical certificates that Dr. Morgan
has already verified via her spreadsheets. INV-02 (human approval hard gate)
governs new certificates going forward; historical data enters pre-verified.

Usage (inside api container):
    python3 scripts/bulk_import.py \
        --employees /data/SimulationForTesting/laredo_test_employees_2000_full.xlsx \
        --manifest /data/SimulationForTesting/output/manifest.csv \
        --certificates /data/SimulationForTesting/output/certificates/ \
        --roles-config /data/SimulationForTesting/config/roles.json \
        --assignments /data/SimulationForTesting/output/employee_assignments.csv

Or via Makefile:
    make bulk-import
"""

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Optional

import openpyxl
from minio import Minio
from minio.error import S3Error
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker


# ---------------------------------------------------------------------------
# Add project src to path so we can import ORM models.
# Inside the API container: /app/src/shared/orm_models.py
# Outside container: CoreInstances/ApiServer/src/shared/orm_models.py
# ---------------------------------------------------------------------------
_api_dir = Path("/app")
if not _api_dir.exists():
    _api_dir = Path(__file__).parent.parent / "CoreInstances" / "ApiServer"
sys.path.insert(0, str(_api_dir))
sys.path.insert(0, str(_api_dir / "src"))

from shared.orm_models import (  # noqa: E402 - shared package is resolved above
    AuditLogORM,
    CertificateDocumentORM,
    CertificateTypeORM,
    EmployeeORM,
    ExtractionRunORM,
    RequirementAssignmentORM,
    VerifiedCertificateRecordORM,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BATCH_SIZE = 100  # Commit every N records
COORDINATOR_ROLE = "Coordinator"
EMPLOYEE_ROLE = "Employee"
NOW = datetime.now(timezone.utc)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk import employees and pre-verified certificates"
    )
    parser.add_argument(
        "--employees",
        type=Path,
        default=None,
        help="Path to employee Excel file (.xlsx)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Path to certificate manifest CSV",
    )
    parser.add_argument(
        "--certificates",
        type=Path,
        default=None,
        help="Path to directory of certificate image/PDF files",
    )
    parser.add_argument(
        "--roles-config",
        type=Path,
        default=None,
        help="Path to roles.json (for certificate type definitions and validity periods)",
    )
    parser.add_argument(
        "--assignments",
        type=Path,
        default=None,
        help="Path to employee_assignments.csv (for requirement creation)",
    )
    parser.add_argument(
        "--coordinator-email",
        type=str,
        default=None,
        help="Email of Coordinator for audit trail (auto-detected if omitted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without writing to DB or MinIO",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------------
def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    # Build from individual vars (inside Docker container)
    user = os.getenv("POSTGRES_USER", "laredo")
    password = os.getenv("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError("POSTGRES_PASSWORD environment variable is required")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "laredo_certificates")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


def get_minio_client() -> tuple[Minio, str]:
    endpoint = os.getenv("MINIO_ENDPOINT", "minio:9000")
    access_key = os.getenv("MINIO_ACCESS_KEY") or os.getenv("MINIO_ROOT_USER", "minioadmin")
    secret_key = os.getenv("MINIO_SECRET_KEY") or os.getenv("MINIO_ROOT_PASSWORD")
    if not secret_key:
        raise RuntimeError("MINIO_SECRET_KEY environment variable is required")
    secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
    bucket = os.getenv("MINIO_BUCKET", "documents")
    client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
    # Ensure bucket exists
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
    return client, bucket


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def sha256_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_manifest_date(date_str: str) -> Optional[date]:
    """Parse MM/DD/YYYY date from manifest CSV."""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), "%m/%d/%Y").date()
    except ValueError:
        # Try ISO format as fallback
        try:
            return datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None


def build_extracted_fields(
    holder_name: str,
    cert_name: str,
    issue_date: Optional[date],
    expiration_date: Optional[date],
    issuing_authority: str,
) -> dict:
    """Build extracted_fields JSONB matching pipeline output structure."""
    def field(value, source="bulk_import"):
        return {
            "value": str(value) if value is not None else "",
            "confidence": {"zone": 1.0, "ocr": 1.0, "parse": 1.0, "validate": 1.0, "overall": 1.0},
            "extraction_source": source,
            "needs_review": False,
        }

    fields = {
        "certificate_holder_name": field(holder_name),
        "certificate_type": field(cert_name),
    }
    if issue_date:
        fields["issue_date"] = field(issue_date.isoformat())
    if expiration_date:
        fields["expiration_date"] = field(expiration_date.isoformat())
    if issuing_authority:
        fields["issuing_authority"] = field(issuing_authority)
    return fields


# ---------------------------------------------------------------------------
# Issuing authority mapping (cert_id -> authority name)
# ---------------------------------------------------------------------------
ISSUING_AUTHORITIES = {
    "sexual_harassment_training": "City of Laredo LMS",
    "workplace_violence_prevention": "City of Laredo LMS",
    "hipaa_privacy_security": "City of Laredo LMS",
    "bloodborne_pathogens": "OSHA / City of Laredo",
    "cpr_bls": "American Heart Association",
    "rn_license_texas": "Texas Board of Nursing",
    "lvn_license_texas": "Texas Board of Nursing",
    "chw_certification": "Texas DSHS",
    "registered_sanitarian_license": "Texas DSHS",
    "pesticide_applicator_license": "Texas Dept. of Agriculture",
    "fema_ics_nims": "FEMA / DHS",
    "hazcom_training": "OSHA / City of Laredo",
    "respiratory_protection_n95": "City of Laredo LMS",
    "wic_civil_rights_training": "USDA / City of Laredo",
    "vfc_program_training": "CDC / City of Laredo",
}


# ---------------------------------------------------------------------------
# Phase A: Import employees from Excel
# ---------------------------------------------------------------------------
async def import_employees(
    session: AsyncSession,
    excel_path: Path,
    dry_run: bool,
) -> dict[str, int]:
    """Import employees from Excel. Returns email -> employee_id mapping."""
    print(f"\n{'='*60}")
    print("PHASE A: Importing Employees")
    print(f"{'='*60}")

    wb = openpyxl.load_workbook(excel_path, read_only=True)
    ws = wb.active
    headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
    print(f"  Excel columns: {headers}")

    # Build existing employee cache
    result = await session.execute(select(EmployeeORM.id, EmployeeORM.email))
    existing = {row.email.lower(): row.id for row in result}
    print(f"  Existing employees in DB: {len(existing)}")

    email_to_id: dict[str, int] = dict(existing)
    created = 0
    skipped = 0
    emp_number_counter = 10001  # Start employee numbers above any existing

    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        first_name = row[0] or ""
        last_name = row[2] or ""
        # row[3] = suffix, row[4] = gender
        email = (row[5] or "").strip().lower()

        if not email:
            continue

        if email in email_to_id:
            skipped += 1
            continue

        if dry_run:
            email_to_id[email] = row_num  # placeholder
            created += 1
            continue

        emp = EmployeeORM(
            employee_number=str(emp_number_counter),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            email=email,
            role=EMPLOYEE_ROLE,
            is_active=True,
        )
        session.add(emp)
        emp_number_counter += 1
        created += 1

        if created % BATCH_SIZE == 0:
            await session.flush()
            print(f"    ... flushed {created} employees")

    if not dry_run and created > 0:
        await session.flush()

        # Rebuild cache with actual IDs
        result = await session.execute(select(EmployeeORM.id, EmployeeORM.email))
        email_to_id = {row.email.lower(): row.id for row in result}

    wb.close()
    print(f"  Created: {created}, Skipped (existing): {skipped}")
    print(f"  Total employees in cache: {len(email_to_id)}")
    return email_to_id


# ---------------------------------------------------------------------------
# Phase B: Ensure certificate types exist
# ---------------------------------------------------------------------------
async def ensure_certificate_types(
    session: AsyncSession,
    manifest_path: Path,
    roles_config_path: Optional[Path],
    dry_run: bool,
) -> dict[str, int]:
    """Ensure all certificate types from manifest exist in DB. Returns name -> id."""
    print(f"\n{'='*60}")
    print("PHASE B: Ensuring Certificate Types")
    print(f"{'='*60}")

    # Load validity periods from roles.json if available
    validity_map: dict[str, Optional[int]] = {}
    if roles_config_path and roles_config_path.exists():
        with open(roles_config_path) as f:
            config = json.load(f)
        for cert_id, cert_info in config.get("certificates", {}).items():
            validity_map[cert_info["name"]] = cert_info.get("validity_days")
        print(f"  Loaded {len(validity_map)} cert type definitions from roles.json")

    # Collect unique cert names from manifest
    cert_names: set[str] = set()
    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("certificate_name", "").strip()
            if name:
                cert_names.add(name)
    print(f"  Unique certificate types in manifest: {len(cert_names)}")

    # Check existing types
    result = await session.execute(select(CertificateTypeORM.id, CertificateTypeORM.name))
    existing = {row.name: row.id for row in result}

    name_to_id: dict[str, int] = dict(existing)
    created = 0

    for name in sorted(cert_names):
        if name in name_to_id:
            continue

        if dry_run:
            name_to_id[name] = 9000 + created  # placeholder
            created += 1
            continue

        ct = CertificateTypeORM(
            name=name,
            description="Auto-created during bulk import",
            validity_period_days=validity_map.get(name),
        )
        session.add(ct)
        await session.flush()
        name_to_id[name] = ct.id
        created += 1

    print(f"  Created: {created}, Already existed: {len(cert_names) - created}")
    return name_to_id


# ---------------------------------------------------------------------------
# Phase C: Import certificates
# ---------------------------------------------------------------------------
async def import_certificates(
    session: AsyncSession,
    minio_client: Minio,
    bucket: str,
    manifest_path: Path,
    certs_dir: Path,
    email_to_id: dict[str, int],
    coordinator_id: int,
    dry_run: bool,
) -> dict[tuple[int, str], int]:
    """
    Import certificates from manifest + files.
    Returns (employee_id, cert_name) -> verified_record_id mapping.
    """
    print(f"\n{'='*60}")
    print("PHASE C: Importing Certificates")
    print(f"{'='*60}")

    # Build existing file_hash set for dedup
    result = await session.execute(
        select(CertificateDocumentORM.file_hash).where(
            CertificateDocumentORM.file_hash.is_not(None)
        )
    )
    existing_hashes: set[str] = {row.file_hash for row in result}
    print(f"  Existing file hashes in DB: {len(existing_hashes)}")

    verified_map: dict[tuple[int, str], int] = {}
    imported = 0
    skipped_missing_file = 0
    skipped_missing_employee = 0
    skipped_dedup = 0
    skipped_no_date = 0
    errors = 0

    with open(manifest_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    print(f"  Manifest rows: {total}")

    for i, row in enumerate(rows):
        filename = row.get("filename", "").strip()
        emp_email = row.get("employee_email", "").strip().lower()
        emp_name = row.get("employee_name", "").strip()
        cert_id = row.get("certificate_id", "").strip()
        cert_name = row.get("certificate_name", "").strip()
        completion_str = row.get("completion_date", "").strip()
        expiration_str = row.get("expiration_date", "").strip()
        state = row.get("state", "").strip()

        # Skip missing certificates (no file to import)
        if state == "missing":
            skipped_missing_file += 1
            continue

        # Resolve employee
        emp_id = email_to_id.get(emp_email)
        if not emp_id:
            skipped_missing_employee += 1
            continue

        # Check file exists
        file_path = certs_dir / filename
        if not file_path.exists():
            skipped_missing_file += 1
            continue

        # Parse dates
        issue_date = parse_manifest_date(completion_str)
        expiration_date = parse_manifest_date(expiration_str)

        if not issue_date:
            skipped_no_date += 1
            continue

        # Read file and compute hash
        try:
            file_bytes = file_path.read_bytes()
        except Exception as e:
            print(f"    ERROR reading {filename}: {e}")
            errors += 1
            continue

        file_hash = sha256_hash(file_bytes)

        # Dedup check
        if file_hash in existing_hashes:
            skipped_dedup += 1
            continue

        if dry_run:
            existing_hashes.add(file_hash)
            imported += 1
            if imported % 500 == 0:
                print(f"    ... validated {imported}/{total}")
            continue

        # Determine original file type from extension
        ext = file_path.suffix.lower()
        mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".pdf": "application/pdf", ".tiff": "image/tiff", ".tif": "image/tiff"}
        original_type = mime_map.get(ext, "image/png")

        # The stored object is the immutable source document. Browser previews
        # are derived on demand by the API and never replace these bytes.
        upload_bytes = file_bytes
        file_type = original_type

        # Upload to MinIO
        storage_key = f"{emp_id}/{uuid.uuid4().hex[:12]}/{filename}"
        try:
            minio_client.put_object(
                bucket, storage_key, BytesIO(upload_bytes),
                length=len(upload_bytes), content_type=file_type,
            )
        except S3Error as e:
            print(f"    ERROR uploading {filename} to MinIO: {e}")
            errors += 1
            continue

        # Issuing authority
        authority = ISSUING_AUTHORITIES.get(cert_id, "")

        # 1. Create CertificateDocument
        doc = CertificateDocumentORM(
            employee_id=emp_id,
            storage_key=storage_key,
            file_name=filename,
            file_type=file_type,
            file_size_bytes=len(upload_bytes),
            uploaded_by_id=coordinator_id,
            acting_as="Coordinator",
            intake_channel="BULK_IMPORT",
            file_hash=file_hash,
        )
        session.add(doc)
        await session.flush()

        # 2. Create ExtractionRun (pre-approved)
        extracted_fields = build_extracted_fields(
            holder_name=emp_name,
            cert_name=cert_name,
            issue_date=issue_date,
            expiration_date=expiration_date,
            issuing_authority=authority,
        )
        extraction = ExtractionRunORM(
            document_id=doc.id,
            review_state="Approved",
            extracted_fields=extracted_fields,
            needs_review=False,
            needs_review_reasons=[],
            template_id=None,
            template_version=None,
            reviewed_by_id=coordinator_id,
            reviewed_at=NOW,
            review_state_version=2,
        )
        session.add(extraction)
        await session.flush()

        # 3. Create VerifiedCertificateRecord
        verified = VerifiedCertificateRecordORM(
            extraction_id=extraction.id,
            document_id=doc.id,
            employee_id=emp_id,
            certificate_holder_name=emp_name,
            certificate_type=cert_name,
            issuing_authority=authority,
            issue_date=issue_date,
            expiration_date=expiration_date,
            reviewed_by_id=coordinator_id,
            reviewed_at=NOW,
            field_provenance={"import_source": "bulk_import"},
        )
        session.add(verified)
        await session.flush()

        verified_map[(emp_id, cert_name)] = verified.id

        # 4. Audit log
        audit = AuditLogORM(
            actor_type="System",
            employee_id=None,
            action="bulk_import",
            target_type="certificate",
            target_id=str(verified.id),
            details={
                "document_id": doc.id,
                "extraction_id": extraction.id,
                "employee_email": emp_email,
                "certificate_type": cert_name,
                "filename": filename,
            },
            initiated_by_id=coordinator_id,
        )
        session.add(audit)

        existing_hashes.add(file_hash)
        imported += 1

        # Batch commit
        if imported % BATCH_SIZE == 0:
            await session.commit()
            print(f"    ... imported {imported} certificates")

    # Final commit
    if not dry_run and imported % BATCH_SIZE != 0:
        await session.commit()

    print(f"\n  Imported: {imported}")
    print(f"  Skipped (missing file): {skipped_missing_file}")
    print(f"  Skipped (missing employee): {skipped_missing_employee}")
    print(f"  Skipped (duplicate hash): {skipped_dedup}")
    print(f"  Skipped (no completion date): {skipped_no_date}")
    print(f"  Errors: {errors}")

    return verified_map


# ---------------------------------------------------------------------------
# Phase D: Create requirement assignments
# ---------------------------------------------------------------------------
async def create_requirements(
    session: AsyncSession,
    assignments_path: Path,
    roles_config_path: Path,
    email_to_id: dict[str, int],
    cert_name_to_id: dict[str, int],
    verified_map: dict[tuple[int, str], int],
    coordinator_id: int,
    dry_run: bool,
) -> None:
    """Create requirement assignments from employee_assignments.csv."""
    print(f"\n{'='*60}")
    print("PHASE D: Creating Requirement Assignments")
    print(f"{'='*60}")

    # Load certificate definitions for validity + due date calculation
    with open(roles_config_path) as f:
        config = json.load(f)
    cert_defs = config.get("certificates", {})
    # Build cert_id -> full name mapping
    cert_id_to_name: dict[str, str] = {
        cid: cdef["name"] for cid, cdef in cert_defs.items()
    }
    cert_id_to_validity: dict[str, Optional[int]] = {
        cid: cdef.get("validity_days") for cid, cdef in cert_defs.items()
    }

    # Check for existing requirements to avoid duplicates
    result = await session.execute(
        select(
            RequirementAssignmentORM.employee_id,
            RequirementAssignmentORM.certificate_type_id,
        )
    )
    existing_reqs: set[tuple[int, int]] = {
        (row.employee_id, row.certificate_type_id) for row in result
    }
    print(f"  Existing requirements: {len(existing_reqs)}")

    created = 0
    skipped = 0

    with open(assignments_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            emp_email = row.get("employee_email", "").strip().lower()
            hire_date_str = row.get("hire_date", "").strip()
            required_certs_str = row.get("required_certificates", "").strip()

            emp_id = email_to_id.get(emp_email)
            if not emp_id:
                continue

            hire_date = None
            if hire_date_str:
                try:
                    hire_date = datetime.strptime(hire_date_str, "%Y-%m-%d").date()
                except ValueError:
                    pass

            required_cert_ids = [c.strip() for c in required_certs_str.split(";") if c.strip()]

            for cert_id in required_cert_ids:
                cert_name = cert_id_to_name.get(cert_id)
                if not cert_name:
                    continue

                cert_type_db_id = cert_name_to_id.get(cert_name)
                if not cert_type_db_id:
                    continue

                # Skip if requirement already exists
                if (emp_id, cert_type_db_id) in existing_reqs:
                    skipped += 1
                    continue

                # Calculate due date: hire_date + validity, or 1 year from today
                validity_days = cert_id_to_validity.get(cert_id)
                if hire_date and validity_days:
                    due = hire_date + timedelta(days=validity_days)
                    # If the initial due date has passed, calculate next cycle
                    today = date.today()
                    while due < today - timedelta(days=90):
                        due += timedelta(days=validity_days)
                elif validity_days:
                    due = date.today() + timedelta(days=validity_days)
                else:
                    due = date.today() + timedelta(days=365)

                # Check if a verified record satisfies this requirement
                verified_id = verified_map.get((emp_id, cert_name))
                req_status = "Satisfied" if verified_id else "NotStarted"

                if dry_run:
                    created += 1
                    existing_reqs.add((emp_id, cert_type_db_id))
                    continue

                req = RequirementAssignmentORM(
                    employee_id=emp_id,
                    certificate_type_id=cert_type_db_id,
                    due_date=due,
                    status=req_status,
                    satisfied_by_id=verified_id,
                    created_by_id=coordinator_id,
                )
                session.add(req)
                existing_reqs.add((emp_id, cert_type_db_id))
                created += 1

                if created % BATCH_SIZE == 0:
                    await session.flush()
                    print(f"    ... created {created} requirements")

    if not dry_run and created > 0:
        await session.commit()

    print(f"  Created: {created}, Skipped (existing): {skipped}")


# ---------------------------------------------------------------------------
# Phase E: Reset sequences
# ---------------------------------------------------------------------------
async def reset_sequences(session: AsyncSession) -> None:
    """Reset PostgreSQL sequences to max(id) for all affected tables."""
    print(f"\n{'='*60}")
    print("PHASE E: Resetting Sequences")
    print(f"{'='*60}")

    tables = [
        ("certificates.employees", "certificates.employees_id_seq"),
        ("certificates.certificate_documents", "certificates.certificate_documents_id_seq"),
        ("certificates.extraction_runs", "certificates.extraction_runs_id_seq"),
        ("certificates.verified_certificate_records", "certificates.verified_certificate_records_id_seq"),
        ("certificates.certificate_types", "certificates.certificate_types_id_seq"),
        ("certificates.requirement_assignments", "certificates.requirement_assignments_id_seq"),
    ]

    for table, seq in tables:
        result = await session.execute(text(f"SELECT COALESCE(MAX(id), 0) FROM {table}"))
        max_id = result.scalar()
        if max_id and max_id > 0:
            await session.execute(text(f"SELECT setval('{seq}', {max_id})"))
            print(f"  {seq} -> {max_id}")

    await session.commit()
    print("  Sequences reset.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> None:
    args = parse_args()

    print("=" * 60)
    print("City of Laredo — Day-One Bulk Import")
    print("=" * 60)

    # Connect to database
    db_url = get_database_url()
    print(f"  Database: {db_url.split('@')[-1]}")  # Hide credentials
    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Normal import mode: validate required paths
    print(f"  Employees:    {args.employees}")
    print(f"  Manifest:     {args.manifest}")
    print(f"  Certificates: {args.certificates}")
    print(f"  Roles config: {args.roles_config}")
    print(f"  Assignments:  {args.assignments}")
    print(f"  Dry run:      {args.dry_run}")

    for label, path in [("Employees", args.employees), ("Manifest", args.manifest),
                         ("Certificates", args.certificates)]:
        if not path or not path.exists():
            print(f"\nERROR: {label} path is required and must exist: {path}")
            sys.exit(1)

    minio_client = None
    bucket = "documents"
    if not args.dry_run:
        minio_client, bucket = get_minio_client()
        print(f"  MinIO bucket: {bucket}")

    async with SessionLocal() as session:
        # Find Coordinator for audit trail
        if args.coordinator_email:
            result = await session.execute(
                select(EmployeeORM).where(EmployeeORM.email == args.coordinator_email)
            )
        else:
            result = await session.execute(
                select(EmployeeORM).where(EmployeeORM.role == COORDINATOR_ROLE)
            )
        coordinator = result.scalar_one_or_none()
        if not coordinator:
            # Fall back to any admin
            result = await session.execute(
                select(EmployeeORM).where(EmployeeORM.role == "Admin")
            )
            coordinator = result.scalar_one_or_none()

        if not coordinator:
            print("\nERROR: No Coordinator or Admin found in DB. Run migrations and seed first.")
            sys.exit(1)
        print(f"  Coordinator: {coordinator.first_name} {coordinator.last_name} (id={coordinator.id})")

        # Phase A: Employees
        email_to_id = await import_employees(session, args.employees, args.dry_run)

        # Phase B: Certificate types
        cert_name_to_id = await ensure_certificate_types(
            session, args.manifest, args.roles_config, args.dry_run
        )

        # Phase C: Certificates
        verified_map = await import_certificates(
            session, minio_client, bucket,
            args.manifest, args.certificates, email_to_id,
            coordinator.id, args.dry_run,
        )

        # Phase D: Requirements (optional)
        if args.assignments and args.assignments.exists() and args.roles_config and args.roles_config.exists():
            await create_requirements(
                session, args.assignments, args.roles_config,
                email_to_id, cert_name_to_id, verified_map,
                coordinator.id, args.dry_run,
            )
        else:
            print("\n  Skipping Phase D (requirements) — no assignments/roles-config provided")

        # Phase E: Reset sequences
        if not args.dry_run:
            await reset_sequences(session)

    await engine.dispose()

    # Summary
    print(f"\n{'='*60}")
    if args.dry_run:
        print("DRY RUN COMPLETE — no changes were made")
    else:
        print("BULK IMPORT COMPLETE")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
