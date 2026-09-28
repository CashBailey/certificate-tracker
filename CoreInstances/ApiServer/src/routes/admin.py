"""
Admin API endpoints for system administration tasks.
"""

import csv
import io
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..deps import get_db_session, get_repository, require_admin
from ..shared.audit import audit_employee_action
from ..shared.models import Employee
from ..shared.orm_models import GALDirectoryORM
from ..shared.protocols import Repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/gal/import")
async def import_gal_csv(
    file: UploadFile = File(...),
    current_user: Employee = Depends(require_admin),
    session: AsyncSession = Depends(get_db_session),
    repository: Repository = Depends(get_repository),
):
    """
    Import GAL (Global Address List) entries from CSV.

    CSV format: email,first_name,last_name,is_person
    The is_person column is optional and defaults to true.
    Upserts on email (updates existing entries).
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV",
        )

    MAX_GAL_BYTES = 10 * 1024 * 1024  # 10 MB

    # Check Content-Length header before reading to avoid loading oversized files
    content_length = file.size
    if content_length is not None and content_length > MAX_GAL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10 MB)",
        )

    content = await file.read()
    if len(content) > MAX_GAL_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large (max 10 MB)",
        )
    try:
        text = content.decode("utf-8-sig")  # Handle BOM
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be UTF-8 encoded",
        )

    reader = csv.DictReader(io.StringIO(text))

    # Validate headers
    if not reader.fieldnames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty or has no headers",
        )

    required_fields = {"email", "first_name", "last_name"}
    actual_fields = {f.strip().lower() for f in reader.fieldnames}
    missing = required_fields - actual_fields
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Missing required CSV columns: {', '.join(sorted(missing))}",
        )

    created = 0
    updated = 0
    errors = []
    results = []

    for row_num, row in enumerate(reader, start=2):  # row 1 is header
        # Normalize keys to lowercase
        row = {k.strip().lower(): v.strip() if v else "" for k, v in row.items()}

        email = row.get("email", "").lower()
        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")

        if not email or not first_name or not last_name:
            errors.append(f"Row {row_num}: missing required field(s)")
            continue

        # Parse is_person (defaults to true)
        is_person_raw = row.get("is_person", "true").lower()
        is_person = is_person_raw not in ("false", "0", "no")

        display_name = row.get("display_name", "").strip() or None

        # Upsert using PostgreSQL INSERT ... ON CONFLICT
        stmt = pg_insert(GALDirectoryORM).values(
            email=email,
            first_name=first_name,
            last_name=last_name,
            display_name=display_name,
            is_person=is_person,
            synced_at=datetime.now(timezone.utc),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_gal_directory_email",
            set_={
                "first_name": stmt.excluded.first_name,
                "last_name": stmt.excluded.last_name,
                "display_name": stmt.excluded.display_name,
                "is_person": stmt.excluded.is_person,
                "synced_at": stmt.excluded.synced_at,
            },
        )

        # Check if row exists to determine created vs updated
        existing = await session.execute(
            select(GALDirectoryORM.id).where(GALDirectoryORM.email == email)
        )
        is_update = existing.scalar_one_or_none() is not None

        await session.execute(stmt)

        if is_update:
            updated += 1
            results.append({"email": email, "action": "updated"})
        else:
            created += 1
            results.append({"email": email, "action": "created"})

    total_rows = created + updated + len(errors)

    # Audit log
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="gal_import",
        target_type="gal_directory",
        target_id="bulk",
        details={
            "total_rows": total_rows,
            "created": created,
            "updated": updated,
            "errors": len(errors),
        },
    )

    return {
        "total_rows": total_rows,
        "created": created,
        "updated": updated,
        "errors": errors,
        "results": results,
    }
