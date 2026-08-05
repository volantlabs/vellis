from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader, PdfWriter

from tools import model_layout, sysml_reference


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_outline_hierarchy_and_ranges_are_preserved(tmp_path: Path) -> None:
    pdf = tmp_path / "fixture.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=612, height=792)
    first = writer.add_outline_item("1 First", 0)
    writer.add_outline_item("1.1 Child", 1, parent=first)
    writer.add_outline_item("2 Second", 2)
    with pdf.open("wb") as stream:
        writer.write(stream)

    entries = sysml_reference._flatten_outline(PdfReader(pdf))

    assert [(entry["title"], entry["level"]) for entry in entries] == [
        ("1 First", 0),
        ("1.1 Child", 1),
        ("2 Second", 0),
    ]
    assert entries[1]["parent_id"] == entries[0]["id"]
    assert entries[0]["subtree_physical_page_end"] == 2


def _lock_artifacts() -> list[dict[str, object]]:
    lock = json.loads(model_layout.LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))
    return list(lock["specifications"].values())


def _artifact_ids() -> list[str]:
    return [str(artifact["specification_id"]) for artifact in _lock_artifacts()]


@pytest.mark.parametrize("specification_id", _artifact_ids())
def test_generated_corpus_matches_the_pinned_language_baseline(specification_id: str) -> None:
    artifact = next(
        value for value in _lock_artifacts() if value["specification_id"] == specification_id
    )
    root_check = model_layout.SPECIFICATION_REFERENCE_ROOT / specification_id
    if not root_check.exists():
        pytest.skip("generated corpus absent; run `just model-setup`")
    page_count = artifact["expected_page_count"]
    outline_count = artifact["expected_outline_count"]
    root = model_layout.SPECIFICATION_REFERENCE_ROOT / specification_id
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    outline = json.loads((root / "outline.json").read_text(encoding="utf-8"))
    pages = sorted((root / "pages").glob("page-*.md"))
    projected_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }

    assert manifest["source_sha256"] == artifact["sha256"]
    assert manifest["version_identity"] == artifact["version_identity"]
    assert manifest["page_count"] == page_count
    assert manifest["outline_entry_count"] == outline_count
    assert len(outline["entries"]) == outline_count
    assert len(pages) == page_count
    assert set(manifest["files"]) == projected_files
    assert all(
        1 <= entry["physical_page_start"] <= entry["physical_page_end"] <= page_count
        for entry in outline["entries"]
    )
    assert all(
        manifest["files"][relative] == _digest(root / relative) for relative in manifest["files"]
    )


def test_specification_filter_and_cli_citation_fields(capsys: pytest.CaptureFixture[str]) -> None:
    kerml = next(identifier for identifier in _artifact_ids() if identifier.startswith("kerml-"))
    if not (model_layout.SPECIFICATION_REFERENCE_ROOT / kerml).exists():
        pytest.skip("generated corpus absent; run `just model-setup`")
    results = sysml_reference.find_references("derived feature", specification_id=kerml, limit=3)
    sysml_reference._print_search_results(results)
    output = capsys.readouterr().out

    assert results and all(result.specification_id == kerml for result in results)
    assert f"{kerml}/pages/" in output
    assert "physical " in output
    assert "printed " in output


def test_page_frontmatter_exposes_extraction_warnings_field() -> None:
    """Every page declares the field, so the skill can tell an agent to check it."""
    identifier = _artifact_ids()[0]
    pages_root = model_layout.SPECIFICATION_REFERENCE_ROOT / identifier / "pages"
    if not pages_root.exists():
        pytest.skip("generated corpus absent; run `just model-setup`")
    pages = sorted(pages_root.glob("page-*.md"))
    sampled = [pages[0], pages[len(pages) // 2], pages[-1]]

    for page_path in sampled:
        frontmatter = yaml.safe_load(page_path.read_text(encoding="utf-8").split("---", 2)[1])
        assert "extraction_warnings" in frontmatter


@pytest.mark.parametrize("limit", (0, -1, 51))
def test_reference_finder_rejects_unbounded_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 50"):
        sysml_reference.find_references("use case", limit=limit)


def test_reference_finder_rejects_unknown_programmatic_specification() -> None:
    with pytest.raises(ValueError, match="unknown specification"):
        sysml_reference.find_references("use case", specification_id="not-a-specification")
