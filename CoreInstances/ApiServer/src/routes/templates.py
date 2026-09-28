"""
Templates API endpoints.
"""

import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_repository, require_coordinator
from ..shared.audit import audit_employee_action
from ..shared.models import Employee, CANONICAL_FIELDS
from ..shared.template_registry import JsonTemplateRegistry
from ..shared.protocols import Repository
from ..shared.regex_safety import validate_template_regex
from .schemas import (
    TemplateCreateRequest,
    TemplateListResponse,
    TemplateResponse,
    TemplateZoneResponse,
)

router = APIRouter(prefix="/templates", tags=["templates"])

# Template registry singleton
_template_registry: Optional[JsonTemplateRegistry] = None


def _get_templates_dir() -> str:
    return os.getenv("TEMPLATES_DIR", "templates")


def get_template_registry() -> JsonTemplateRegistry:
    """Get or create template registry singleton."""
    global _template_registry
    if _template_registry is None:
        _template_registry = JsonTemplateRegistry(_get_templates_dir())
    return _template_registry


def _reload_registry() -> JsonTemplateRegistry:
    """Force reload of the template registry after changes."""
    global _template_registry
    _template_registry = JsonTemplateRegistry(_get_templates_dir())
    return _template_registry


class _TemplateVersionConflict(ValueError):
    """Raised when a template write would replace or skip a retained version."""


def _append_template_version(file_path: Path, template_data: dict) -> list[int]:
    """Atomically append exactly the next version while retaining prior bytes."""
    lock_path = file_path.parent / f".{file_path.stem}.lock"
    with open(lock_path, "a", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        existing: list[dict] = []
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as existing_file:
                    loaded = json.load(existing_file)
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("Existing template file is invalid") from exc
            if not isinstance(loaded, list) or not all(
                isinstance(item, dict) for item in loaded
            ):
                raise RuntimeError("Existing template file is invalid")
            existing = loaded

        template_id = template_data["template_id"]
        if any(item.get("template_id") != template_id for item in existing):
            raise RuntimeError("Existing template file contains a different ID")

        try:
            existing_versions = sorted(int(item["version"]) for item in existing)
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError("Existing template versions are invalid") from exc

        expected_version = existing_versions[-1] + 1 if existing_versions else 1
        if template_data["version"] != expected_version:
            raise _TemplateVersionConflict(
                f"Template {template_id} must use version {expected_version}; "
                "existing versions are retained and cannot be replaced"
            )

        versions = [*existing, template_data]
        versions.sort(key=lambda item: int(item["version"]))
        serialized = json.dumps(versions, indent=2).encode("utf-8")

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{file_path.stem}.",
            suffix=".tmp",
            dir=file_path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as temp_file:
                temp_file.write(serialized)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_name, file_path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        return existing_versions


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    current_user: Employee = Depends(require_coordinator),
):
    """
    List all available templates.

    Returns latest version of each template.
    """
    registry = get_template_registry()
    templates = registry.list_templates()

    return TemplateListResponse(
        templates=[
            TemplateResponse(
                template_id=t.template_id,
                version=t.version,
                name=t.name,
                description=t.description,
                issuing_authority=t.issuing_authority,
                certificate_type_ref=t.certificate_type_ref,
                zones=[
                    TemplateZoneResponse(
                        field_name=z.field_name,
                        bbox_norm=list(z.bbox_norm),
                        required=z.required,
                    )
                    for z in t.zones
                ],
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in templates
        ],
        registry_hash=registry.get_registry_hash(),
    )


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    body: TemplateCreateRequest,
    current_user: Employee = Depends(require_coordinator),
    repository: Repository = Depends(get_repository),
):
    """
    Create the first or next immutable version of a template definition.

    Existing versions are retained for extraction provenance.
    """
    # Validate all zone field names are canonical
    try:
        if body.anchor_regex:
            validate_template_regex(body.anchor_regex)
        for zone in body.zones:
            if zone.regex_pattern:
                validate_template_regex(zone.regex_pattern)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    for zone in body.zones:
        if zone.field_name not in CANONICAL_FIELDS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid field name '{zone.field_name}'. "
                f"Must be one of: {', '.join(CANONICAL_FIELDS)}",
            )
        # Validate bbox coordinates are in [0, 1] and x0 < x1, y0 < y1
        x0, y0, x1, y1 = zone.bbox_norm
        if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Zone '{zone.field_name}' has invalid bbox_norm. "
                f"Coordinates must be in [0,1] with x0<x1 and y0<y1.",
            )

    templates_dir = Path(_get_templates_dir()).resolve()
    templates_dir.mkdir(parents=True, exist_ok=True)
    file_path = (templates_dir / f"{body.template_id}.json").resolve()

    # Containment check: prevent path traversal via crafted template_id
    if not file_path.is_relative_to(templates_dir):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid template ID",
        )

    # Build the template JSON in registry format
    template_data = {
        "template_id": body.template_id,
        "version": body.version,
        "name": body.name,
        "description": body.description or "",
        "issuing_authority": body.issuing_authority,
        "certificate_type_ref": body.certificate_type_ref,
        "detection": {
            "anchor_keywords": body.anchor_keywords or [],
            "min_keyword_matches": body.min_keyword_matches,
            "min_confidence_score": 0.70,
        },
        "alignment": {
            "reference_anchors": [],
            "tolerance_bbox": 0.04,
            "min_anchors_matched": 2,
        },
        "zones": [
            {
                "field_name": z.field_name,
                "bbox_norm": z.bbox_norm,
                "parsing": {
                    "strip_whitespace": True,
                    **({"regex_pattern": z.regex_pattern} if z.regex_pattern else {}),
                    **({"date_format": z.date_format} if z.date_format else {}),
                    **({"allow_multiline": True} if z.allow_multiline else {}),
                },
                "validators": {
                    **({"min_length": z.min_length} if z.min_length else {}),
                    **({"max_length": z.max_length} if z.max_length else {}),
                },
                "required": z.required,
                **({"hardcoded_value": z.hardcoded_value} if z.hardcoded_value else {}),
            }
            for z in body.zones
        ],
        "review_rules": {
            "always_review_fields": body.always_review_fields or [],
            "skip_generic_if_zone_confident": True,
        },
        "created_at": body.created_at,
        "updated_at": body.updated_at,
    }

    if body.anchor_regex:
        template_data["detection"]["anchor_regex"] = body.anchor_regex

    try:
        prior_versions = _append_template_version(file_path, template_data)
    except _TemplateVersionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Existing template data is invalid; no changes were written",
        ) from exc

    # Reload the registry to pick up the new template
    registry = _reload_registry()
    template = registry.get_template(body.template_id, body.version)

    # Audit log for template creation
    await audit_employee_action(
        repository=repository,
        actor=current_user,
        action="template_created",
        target_type="template",
        target_id=body.template_id,
        details={
            "version": body.version,
            "prior_versions": prior_versions,
            "zone_count": len(body.zones),
            "definition_sha256": hashlib.sha256(
                json.dumps(template_data, sort_keys=True).encode("utf-8")
            ).hexdigest(),
        },
    )

    return TemplateResponse(
        template_id=template.template_id,
        version=template.version,
        name=template.name,
        description=template.description,
        issuing_authority=template.issuing_authority,
        certificate_type_ref=template.certificate_type_ref,
        zones=[
            TemplateZoneResponse(
                field_name=z.field_name,
                bbox_norm=list(z.bbox_norm),
                required=z.required,
            )
            for z in template.zones
        ],
        created_at=template.created_at,
        updated_at=template.updated_at,
    )
