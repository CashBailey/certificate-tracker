"""
Template identification for extraction pipeline.

Identifies which template matches a document using keyword/regex scoring.
"""

import re
from dataclasses import dataclass
from typing import Optional

from shared.models import NormalizedDocument, TemplateDefinition
from shared.template_registry import JsonTemplateRegistry

MAX_REGEX_EVIDENCE_CHARS = 256


@dataclass
class TemplateMatchResult:
    """Result of template matching."""
    template: Optional[TemplateDefinition]
    confidence: float
    evidence: dict


class TemplateIdentifier:
    """Identifies templates from document content."""

    def __init__(self, registry: JsonTemplateRegistry):
        """
        Initialize identifier with template registry.

        Args:
            registry: Template registry to match against
        """
        self.registry = registry

    def identify_template(
        self,
        document: NormalizedDocument,
    ) -> TemplateMatchResult:
        """
        Identify the best matching template for a document.

        Uses keyword matching and regex patterns from template detection config.

        Args:
            document: Normalized document to identify

        Returns:
            TemplateMatchResult with best match (or None if no match)
        """
        page_texts = [
            (page.page_num, page.page_text.upper())
            for page in document.pages
        ] or [(None, document.searchable_text.full_text.upper())]

        best_match: Optional[TemplateDefinition] = None
        best_score = 0.0
        best_evidence: dict = {}

        for template in self.registry.list_templates():
            score, evidence, page_num = max(
                (
                    (*self._score_template(template, page_text), candidate_page_num)
                    for candidate_page_num, page_text in page_texts
                ),
                key=lambda result: result[0],
            )

            if score > best_score and score >= template.detection.min_confidence_score:
                best_score = score
                best_match = template
                best_evidence = evidence
                best_evidence["page_num"] = page_num

        return TemplateMatchResult(
            template=best_match,
            confidence=best_score,
            evidence=best_evidence,
        )

    def _score_template(
        self,
        template: TemplateDefinition,
        text: str,
    ) -> tuple[float, dict]:
        """
        Score how well a template matches the text.

        Args:
            template: Template to score
            text: Document text (uppercase)

        Returns:
            Tuple of (score, evidence_dict)
        """
        detection = template.detection
        evidence: dict = {
            "template_id": template.template_id,
            "keyword_matches": [],
            "regex_match": None,
        }

        # Score keyword matches
        keyword_matches = 0
        for keyword in detection.anchor_keywords:
            if keyword.upper() in text:
                keyword_matches += 1
                evidence["keyword_matches"].append(keyword)

        # Check minimum keyword requirement
        if keyword_matches < detection.min_keyword_matches:
            return 0.0, evidence

        # Calculate keyword score (0 to 0.6)
        max_keywords = len(detection.anchor_keywords)
        keyword_score = (keyword_matches / max_keywords) * 0.6 if max_keywords > 0 else 0

        # Score regex match (0 to 0.4)
        regex_score = 0.0
        if detection.anchor_regex:
            try:
                match = re.search(detection.anchor_regex, text, re.IGNORECASE)
                if match:
                    regex_score = 0.4
                    matched_text = match.group(0)
                    evidence["regex_match"] = matched_text[:MAX_REGEX_EVIDENCE_CHARS]
                    evidence["regex_match_span"] = [match.start(), match.end()]
                    evidence["regex_match_truncated"] = (
                        len(matched_text) > MAX_REGEX_EVIDENCE_CHARS
                    )
            except re.error:
                pass

        total_score = keyword_score + regex_score
        evidence["score"] = total_score

        return total_score, evidence

    def identify_with_fallback(
        self,
        document: NormalizedDocument,
        fallback_threshold: float = 0.5,
    ) -> tuple[Optional[TemplateDefinition], bool, dict]:
        """
        Identify template with fallback to generic extraction.

        Args:
            document: Document to identify
            fallback_threshold: Minimum score to use template

        Returns:
            Tuple of (template_or_none, use_generic, evidence)
        """
        result = self.identify_template(document)

        if result.template and result.confidence >= fallback_threshold:
            return result.template, False, result.evidence

        # No confident match, use generic extraction
        return None, True, {
            "reason": "No template matched above threshold",
            "best_score": result.confidence,
            "threshold": fallback_threshold,
        }
