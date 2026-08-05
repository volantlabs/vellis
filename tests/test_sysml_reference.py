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


@pytest.mark.parametrize(
    "specification_id",
    ("sysml-2.0", "kerml-1.0"),
)
def test_committed_corpus_matches_the_pinned_language_baseline(specification_id: str) -> None:
    lock = json.loads(model_layout.LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))
    artifact = next(
        value
        for value in lock["specifications"].values()
        if value["specification_id"] == specification_id
    )
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
    assert manifest["document_number"] == artifact["document_number"]
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


@pytest.mark.parametrize(
    ("query", "specification_id", "expected_pages"),
    (
        ("default multiplicity of a part usage", "sysml-2.0", {92}),
        ("features of an interface definition", "sysml-2.0", {109, 447}),
        ("derived feature", "kerml-1.0", {60, 185}),
    ),
)
def test_representative_questions_route_to_language_sections(
    query: str, specification_id: str, expected_pages: set[int]
) -> None:
    results = sysml_reference.find_references(query, limit=6)

    assert any(
        result.specification_id == specification_id and result.physical_page in expected_pages
        for result in results
    )


def test_natural_use_case_questions_route_to_description_and_semantics() -> None:
    description = sysml_reference.find_references("How do I define and use a use case?", limit=6)
    semantics = sysml_reference.find_references(
        "How do I model a use case with a subject and actors?", limit=6
    )

    assert any(result.physical_page == 179 for result in description)
    assert any(result.physical_page == 488 for result in semantics)


def test_ownership_query_reformulation_reaches_kerml_feature_sections() -> None:
    initial = sysml_reference.find_references(
        "owned feature versus reference feature", specification_id="kerml-1.0", limit=6
    )
    reformulated = sysml_reference.find_references(
        "reference feature versus composite feature", specification_id="kerml-1.0", limit=8
    )

    assert initial
    assert any(result.physical_page == 185 for result in reformulated)


def test_specification_filter_and_cli_citation_fields(capsys: pytest.CaptureFixture[str]) -> None:
    results = sysml_reference.find_references(
        "derived feature", specification_id="kerml-1.0", limit=3
    )
    sysml_reference._print_search_results(results)
    output = capsys.readouterr().out

    assert results and all(result.specification_id == "kerml-1.0" for result in results)
    assert "reference/specifications/kerml-1.0/pages/" in output
    assert "physical " in output
    assert "printed " in output


def test_extraction_warning_is_exposed_in_page_metadata() -> None:
    page = (
        model_layout.SPECIFICATION_REFERENCE_ROOT / "sysml-2.0" / "pages" / "page-0091.md"
    ).read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(page.split("---", 2)[1])

    assert frontmatter["extraction_warnings"]


def test_reference_corpus_remains_text_scale() -> None:
    files = [
        path for path in model_layout.SPECIFICATION_REFERENCE_ROOT.rglob("*") if path.is_file()
    ]

    assert sum(path.stat().st_size for path in files) < 10 * 1024 * 1024


@pytest.mark.parametrize("limit", (0, -1, 51))
def test_reference_finder_rejects_unbounded_limits(limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 50"):
        sysml_reference.find_references("use case", limit=limit)


def test_reference_finder_rejects_unknown_programmatic_specification() -> None:
    with pytest.raises(ValueError, match="unknown specification"):
        sysml_reference.find_references("use case", specification_id="not-a-specification")
