"""
Unit tests for _safe_csv_cell — CSV formula-injection defense (MED-07).

Excel/LibreOffice/Sheets interpret cells beginning with =, +, -, @, \\t, or
\\r as formulas. The defense prepends a single quote to defang them; the
leading quote is hidden as a text-entry marker and the formula renders
inert. Pure function — no fixtures needed.
"""

import pytest

from src.routes.reports import _safe_csv_cell, _safe_xlsx_cell


def test_safe_csv_cell_defangs_equals() -> None:
    assert _safe_csv_cell("=CMD") == "'=CMD"


@pytest.mark.parametrize(
    "value",
    ["+CMD", "-CMD", "@CMD"],
)
def test_safe_csv_cell_defangs_plus_minus_at(value: str) -> None:
    assert _safe_csv_cell(value) == "'" + value


@pytest.mark.parametrize(
    "value",
    ["\tCMD", "\rCMD"],
)
def test_safe_csv_cell_defangs_tab_carriage_return(value: str) -> None:
    assert _safe_csv_cell(value) == "'" + value


@pytest.mark.parametrize(
    "value",
    ["OK", "abc", "John Doe", "Active", "2025-01-15"],
)
def test_safe_csv_cell_passes_through_safe_text(value: str) -> None:
    assert _safe_csv_cell(value) == value


def test_safe_csv_cell_handles_none() -> None:
    assert _safe_csv_cell(None) == ""


@pytest.mark.parametrize(
    "value,expected",
    [(42, "42"), (0, "0")],
)
def test_safe_csv_cell_handles_int(value: int, expected: str) -> None:
    assert _safe_csv_cell(value) == expected


def test_safe_csv_cell_negative_int_is_defanged() -> None:
    # Documents an emergent behavior: -5 stringifies to "-5" which begins
    # with '-' so it MUST be defanged. The defense applies after str()
    # conversion, not based on input type — keeping it consistent prevents
    # drift if a column type changes.
    assert _safe_csv_cell(-5) == "'-5"


def test_safe_csv_cell_empty_string() -> None:
    assert _safe_csv_cell("") == ""


@pytest.mark.parametrize("value", ["=1+1", "+CMD", "-2+3", "@SUM(A1:A2)"])
def test_safe_xlsx_cell_defangs_formula_prefixes(value: str) -> None:
    assert _safe_xlsx_cell(value) == "'" + value
