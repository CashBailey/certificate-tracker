"""Administrator-defined extraction regexes must have bounded complexity."""

import pytest

from src.shared.regex_safety import validate_template_regex
from src.shared.template_registry import JsonTemplateRegistry


@pytest.mark.parametrize(
    "pattern",
    [
        r"(a+)+$",
        r"(a|aa)+$",
        r"(a+){1,}$",
        r"(?=(a+))a+",
        r"(secret)\1",
    ],
)
def test_high_risk_regexes_are_rejected(pattern: str):
    with pytest.raises(ValueError):
        validate_template_regex(pattern)


def test_bounded_nested_quantifier_used_by_templates_is_allowed():
    validate_template_regex(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5}")


def test_shipped_template_registry_passes_regex_validation():
    registry = JsonTemplateRegistry("templates")

    assert registry.list_templates()
