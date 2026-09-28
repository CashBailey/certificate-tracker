"""
JSON-based template registry implementation.

Loads template definitions from JSON files at startup and provides access to them.
"""

import hashlib
import json
from pathlib import Path
from typing import Optional

from .models import (
    CANONICAL_FIELDS,
    FieldZone,
    TemplateAlignment,
    TemplateDefinition,
    TemplateDetection,
    TemplateReviewRules,
    ZoneParsing,
    ZoneValidators,
)
from .protocols import TemplateNotFoundError, TemplateVersionNotFoundError
from .regex_safety import validate_template_regex


class JsonTemplateRegistry:
    """
    JSON-based template registry.

    Loads all *.json files from templates directory at startup.
    Each file contains an array of template versions.
    """

    def __init__(self, templates_dir: str | Path):
        """
        Initialize template registry.

        Args:
            templates_dir: Path to directory containing template JSON files

        Raises:
            ValueError: If templates_dir doesn't exist or templates are invalid
        """
        self.templates_dir = Path(templates_dir)
        if not self.templates_dir.exists():
            raise ValueError(f"Templates directory does not exist: {templates_dir}")

        # Storage: template_id -> list of versions (sorted by version number)
        self.templates: dict[str, list[TemplateDefinition]] = {}

        # Load all templates
        self._load_templates()

        # Compute registry hash for cache invalidation
        self._registry_hash = self._compute_registry_hash()

    def _load_templates(self) -> None:
        """Load all template JSON files from templates directory."""
        json_files = list(self.templates_dir.glob("*.json"))

        if not json_files:
            raise ValueError(f"No template JSON files found in {self.templates_dir}")

        for json_file in json_files:
            self._load_template_file(json_file)

    def _load_template_file(self, file_path: Path) -> None:
        """
        Load a single template JSON file.

        Args:
            file_path: Path to template JSON file

        Raises:
            ValueError: If template file is invalid
        """
        try:
            with open(file_path, "r") as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise ValueError(f"Template file must contain an array: {file_path}")

            for template_data in data:
                template = self._parse_template(template_data)
                self._validate_template(template)

                # Add to registry
                if template.template_id not in self.templates:
                    self.templates[template.template_id] = []
                self.templates[template.template_id].append(template)

            # Sort versions for each template
            for template_id in self.templates:
                self.templates[template_id].sort(key=lambda t: t.version)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            # JSONDecodeError: Invalid JSON syntax
            # KeyError: Missing required template fields
            # TypeError: Invalid data types in template structure
            raise ValueError(f"Failed to load template file {file_path}: {e}")

    def _parse_template(self, data: dict) -> TemplateDefinition:
        """
        Parse template from JSON data.

        Args:
            data: Template JSON data

        Returns:
            TemplateDefinition object
        """
        # Parse detection
        detection = TemplateDetection(
            anchor_keywords=data["detection"]["anchor_keywords"],
            anchor_regex=data["detection"].get("anchor_regex"),
            min_keyword_matches=data["detection"].get("min_keyword_matches", 2),
            min_confidence_score=data["detection"].get("min_confidence_score", 0.7),
        )

        # Parse alignment
        alignment = TemplateAlignment(
            reference_anchors=[
                (anchor["text"], tuple(anchor["position"]))
                for anchor in data["alignment"]["reference_anchors"]
            ],
            tolerance_bbox=data["alignment"].get("tolerance_bbox", 0.02),
            min_anchors_matched=data["alignment"].get("min_anchors_matched", 2),
        )

        # Parse zones
        zones = []
        for zone_data in data["zones"]:
            parsing = ZoneParsing(
                regex_pattern=zone_data["parsing"].get("regex_pattern"),
                date_format=zone_data["parsing"].get("date_format"),
                allow_multiline=zone_data["parsing"].get("allow_multiline", False),
                strip_whitespace=zone_data["parsing"].get("strip_whitespace", True),
            )

            validators = ZoneValidators(
                min_length=zone_data["validators"].get("min_length"),
                max_length=zone_data["validators"].get("max_length"),
                regex_match=zone_data["validators"].get("regex_match"),
                date_range=tuple(zone_data["validators"]["date_range"])
                if zone_data["validators"].get("date_range")
                else None,
            )

            zone = FieldZone(
                field_name=zone_data["field_name"],
                bbox_norm=tuple(zone_data["bbox_norm"]),
                parsing=parsing,
                validators=validators,
                required=zone_data.get("required", False),
                hardcoded_value=zone_data.get("hardcoded_value"),
            )
            zones.append(zone)

        # Parse review rules
        review_rules = TemplateReviewRules(
            always_review_fields=data["review_rules"].get("always_review_fields", []),
            skip_generic_if_zone_confident=data["review_rules"].get(
                "skip_generic_if_zone_confident", True
            ),
        )

        return TemplateDefinition(
            template_id=data["template_id"],
            version=data["version"],
            name=data["name"],
            description=data["description"],
            detection=detection,
            alignment=alignment,
            zones=zones,
            review_rules=review_rules,
            issuing_authority=data.get("issuing_authority"),
            certificate_type_ref=data.get("certificate_type_ref"),
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def _validate_template(self, template: TemplateDefinition) -> None:
        """
        Validate template definition.

        Args:
            template: Template to validate

        Raises:
            ValueError: If template is invalid
        """
        if template.detection.anchor_regex:
            validate_template_regex(template.detection.anchor_regex)

        # Check that all zone field names are canonical
        for zone in template.zones:
            if zone.field_name not in CANONICAL_FIELDS:
                raise ValueError(
                    f"Template {template.template_id} v{template.version}: "
                    f"Invalid field name '{zone.field_name}'. Must be one of {CANONICAL_FIELDS}"
                )

            # Check bbox coordinates are in [0, 1]
            x0, y0, x1, y1 = zone.bbox_norm
            if not (0 <= x0 <= 1 and 0 <= y0 <= 1 and 0 <= x1 <= 1 and 0 <= y1 <= 1):
                raise ValueError(
                    f"Template {template.template_id} v{template.version}: "
                    f"Zone {zone.field_name} has invalid bbox coordinates (must be 0..1): {zone.bbox_norm}"
                )

            # Check bbox is valid (x0 < x1, y0 < y1)
            if x0 >= x1 or y0 >= y1:
                raise ValueError(
                    f"Template {template.template_id} v{template.version}: "
                    f"Zone {zone.field_name} has invalid bbox (x0 must be < x1, y0 < y1): {zone.bbox_norm}"
                )

            if zone.parsing.regex_pattern:
                validate_template_regex(zone.parsing.regex_pattern)
            if zone.validators.regex_match:
                validate_template_regex(zone.validators.regex_match)

        # Check that always_review_fields are canonical
        for field_name in template.review_rules.always_review_fields:
            if field_name not in CANONICAL_FIELDS:
                raise ValueError(
                    f"Template {template.template_id} v{template.version}: "
                    f"Invalid always_review field '{field_name}'. Must be one of {CANONICAL_FIELDS}"
                )

    def _compute_registry_hash(self) -> str:
        """
        Compute SHA-256 hash of entire registry for cache invalidation.

        Returns:
            Hexadecimal hash string
        """
        # Serialize all templates in sorted order
        all_data = []
        for template_id in sorted(self.templates.keys()):
            for template in self.templates[template_id]:
                all_data.append(
                    {
                        "template_id": template.template_id,
                        "version": template.version,
                        "updated_at": template.updated_at,
                    }
                )

        json_str = json.dumps(all_data, sort_keys=True)
        return hashlib.sha256(json_str.encode()).hexdigest()

    def get_template(
        self, template_id: str, version: Optional[int] = None
    ) -> TemplateDefinition:
        """
        Get template by ID and optional version.

        Args:
            template_id: Template identifier
            version: Template version (if None, returns latest)

        Returns:
            TemplateDefinition

        Raises:
            TemplateNotFoundError: If template ID not found
            TemplateVersionNotFoundError: If specific version not found
        """
        if template_id not in self.templates:
            raise TemplateNotFoundError(f"Template not found: {template_id}")

        versions = self.templates[template_id]

        if version is None:
            # Return latest version
            return versions[-1]

        # Find specific version
        for template in versions:
            if template.version == version:
                return template

        raise TemplateVersionNotFoundError(
            f"Template {template_id} version {version} not found"
        )

    def list_templates(self) -> list[TemplateDefinition]:
        """
        List all templates (latest versions only).

        Returns:
            List of TemplateDefinition objects
        """
        return [versions[-1] for versions in self.templates.values()]

    def get_all_versions(self, template_id: str) -> list[TemplateDefinition]:
        """
        Get all versions of a template.

        Args:
            template_id: Template identifier

        Returns:
            List of TemplateDefinition objects sorted by version

        Raises:
            TemplateNotFoundError: If template ID not found
        """
        if template_id not in self.templates:
            raise TemplateNotFoundError(f"Template not found: {template_id}")

        return self.templates[template_id].copy()

    def get_registry_hash(self) -> str:
        """
        Get hash of entire registry for cache invalidation.

        Returns:
            Hexadecimal hash string
        """
        return self._registry_hash
