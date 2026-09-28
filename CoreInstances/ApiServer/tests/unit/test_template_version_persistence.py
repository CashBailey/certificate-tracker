"""Tests that template version writes preserve historical provenance."""

import json

import pytest

from src.routes.templates import _TemplateVersionConflict, _append_template_version


def _template(version: int, *, template_id: str = "safety") -> dict:
    return {
        "template_id": template_id,
        "version": version,
        "name": f"Safety v{version}",
    }


def test_next_version_is_appended_without_losing_history(tmp_path):
    path = tmp_path / "safety.json"
    path.write_text(json.dumps([_template(1), _template(2)]))

    prior_versions = _append_template_version(path, _template(3))

    stored = json.loads(path.read_text())
    assert prior_versions == [1, 2]
    assert [item["version"] for item in stored] == [1, 2, 3]
    assert stored[0]["name"] == "Safety v1"


@pytest.mark.parametrize("version", [1, 2, 4, 99])
def test_existing_or_skipped_version_is_rejected_without_writing(tmp_path, version):
    path = tmp_path / "safety.json"
    original = json.dumps([_template(1), _template(2)])
    path.write_text(original)

    with pytest.raises(_TemplateVersionConflict, match="must use version 3"):
        _append_template_version(path, _template(version))

    assert path.read_text() == original


def test_new_template_must_start_at_version_one(tmp_path):
    path = tmp_path / "new_template.json"

    with pytest.raises(_TemplateVersionConflict, match="must use version 1"):
        _append_template_version(path, _template(2, template_id="new_template"))

    assert not path.exists()


def test_invalid_existing_file_is_never_overwritten(tmp_path):
    path = tmp_path / "safety.json"
    path.write_text("not json")

    with pytest.raises(RuntimeError, match="invalid"):
        _append_template_version(path, _template(1))

    assert path.read_text() == "not json"
