from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader, PdfWriter

from tools import model_layout, sysml_reference


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_outline_flattening_preserves_hierarchy_and_page_ranges(tmp_path: Path) -> None:
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
    assert entries[0]["section_number"] == "1"
    assert entries[1]["parent_id"] == entries[0]["id"]
    assert entries[1]["physical_page_start"] == 2
    assert entries[1]["physical_page_end"] == 2
    assert entries[0]["subtree_physical_page_end"] == 2


def test_printed_page_mapping_and_text_normalization() -> None:
    sysml, kerml = sysml_reference._load_specifications()

    assert sysml_reference._printed_page(sysml, 8) == "pdf-8"
    assert sysml_reference._printed_page(sysml, 11) == "i"
    assert sysml_reference._printed_page(sysml, 32) == "xxii"
    assert sysml_reference._printed_page(sysml, 33) == "1"
    assert sysml_reference._printed_page(kerml, 11) == "i"
    assert sysml_reference._printed_page(kerml, 26) == "xvi"
    assert sysml_reference._printed_page(kerml, 27) == "1"
    assert (
        sysml_reference._normalize_text(
            "\nMeaningful text\n\n\n\nSystems Modeling Language v2.0, Part 1       63\n",
            sysml,
        )
        == "Meaningful text"
    )


def test_source_verification_rejects_checksum_drift(tmp_path: Path) -> None:
    specification = sysml_reference._load_specifications()[0]
    wrong = tmp_path / "wrong.pdf"
    wrong.write_bytes(b"not the pinned specification")
    changed = sysml_reference.Specification(
        **{**specification.__dict__, "source_pdf": wrong}
    )

    with pytest.raises(RuntimeError, match="checksum mismatch"):
        sysml_reference._verify_source(changed)


def test_source_verification_rejects_missing_pdf(tmp_path: Path) -> None:
    specification = replace(
        sysml_reference._load_specifications()[0],
        source_pdf=tmp_path / "missing.pdf",
    )

    with pytest.raises(RuntimeError, match="run `just model-setup`"):
        sysml_reference._verify_source(specification)


def test_pdf_identity_and_citation_anchors_are_verified() -> None:
    specifications = sysml_reference._load_specifications()
    for actual in specifications:
        actual_reader = PdfReader(actual.source_pdf)
        sysml_reference._verify_pdf_identity(
            actual, actual_reader, sysml_reference._flatten_outline(actual_reader)
        )

    specification = specifications[0]
    reader = PdfReader(specification.source_pdf)
    entries = sysml_reference._flatten_outline(reader)

    sysml_reference._verify_pdf_identity(specification, reader, entries)
    with pytest.raises(RuntimeError, match="expected PDF title"):
        sysml_reference._verify_pdf_identity(
            replace(specification, pdf_title="Wrong title"), reader, entries
        )
    with pytest.raises(RuntimeError, match="cover does not contain"):
        sysml_reference._verify_pdf_identity(
            replace(specification, document_number="formal/invalid"), reader, entries
        )
    with pytest.raises(RuntimeError, match="expected outline entry '1 Scope'"):
        sysml_reference._verify_pdf_identity(
            replace(specification, body_start=34), reader, entries
        )


def test_clean_ci_provisions_reference_sources_before_full_check() -> None:
    workflow = (model_layout.ROOT / ".github" / "workflows" / "check.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.index("run: just model-setup") < workflow.index("run: just check")


@pytest.mark.parametrize(
    ("specification_id", "page_count", "outline_count"),
    (("sysml-2.0", 691, 991), ("kerml-1.0", 454, 661)),
)
def test_committed_reference_corpus_is_complete_and_internally_verified(
    specification_id: str,
    page_count: int,
    outline_count: int,
) -> None:
    root = model_layout.SPECIFICATION_REFERENCE_ROOT / specification_id
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    outline = json.loads((root / "outline.json").read_text(encoding="utf-8"))
    pages = sorted((root / "pages").glob("page-*.md"))

    assert manifest["page_count"] == page_count
    assert manifest["outline_entry_count"] == outline_count
    assert outline["outline_entry_count"] == outline_count
    assert len(outline["entries"]) == outline_count
    assert len(pages) == page_count
    assert [path.name for path in pages] == [
        f"page-{physical_page:04d}.md" for physical_page in range(1, page_count + 1)
    ]
    assert all(
        1 <= entry["physical_page_start"] <= entry["physical_page_end"] <= page_count
        for entry in outline["entries"]
    )
    assert all(
        manifest["files"][relative_path] == _digest(root / relative_path)
        for relative_path in manifest["files"]
    )


def test_reference_extraction_preserves_representative_language_and_examples() -> None:
    sysml_port = (
        model_layout.SPECIFICATION_REFERENCE_ROOT
        / "sysml-2.0"
        / "pages"
        / "page-0095.md"
    ).read_text(encoding="utf-8")
    kerml_root = (
        model_layout.SPECIFICATION_REFERENCE_ROOT
        / "kerml-1.0"
        / "pages"
        / "page-0041.md"
    ).read_text(encoding="utf-8")
    kerml_binding = (
        model_layout.SPECIFICATION_REFERENCE_ROOT
        / "kerml-1.0"
        / "pages"
        / "page-0076.md"
    ).read_text(encoding="utf-8")

    assert "7.12.2    Port Definitions and Usages" in sysml_port
    assert "port def       FuelingPort" in sysml_port
    assert "7.2.2.1  Elements and Relationships Overview" in kerml_root
    assert "A binding connector is declared as a feature" in kerml_binding


def test_page_metadata_reports_boundary_context_and_every_starting_section() -> None:
    page = (
        model_layout.SPECIFICATION_REFERENCE_ROOT
        / "sysml-2.0"
        / "pages"
        / "page-0095.md"
    ).read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(page.split("---", 2)[1])

    assert "section_context" not in frontmatter
    assert frontmatter["section_context_before_page"][-1] == "7.12.1 Ports Overview"
    assert [
        "7 Language Description",
        "7.12 Ports",
        "7.12.2 Port Definitions and Usages",
    ] in frontmatter["section_paths_starting_here"]
    assert [
        "7 Language Description",
        "7.13 Connections",
        "7.13.1 Connections Overview",
    ] in frontmatter["section_paths_starting_here"]


@pytest.mark.parametrize(
    ("query", "specification_id", "expected_pages"),
    (
        ("default multiplicity of a part usage", "sysml-2.0", {92}),
        ("features of an interface definition", "sysml-2.0", {109, 447}),
        ("derived feature", "kerml-1.0", {60, 185}),
    ),
)
def test_ranked_discovery_routes_natural_questions_to_relevant_pages(
    query: str,
    specification_id: str,
    expected_pages: set[int],
) -> None:
    results = sysml_reference.find_references(query, limit=5)

    assert any(
        result.specification_id == specification_id
        and result.physical_page in expected_pages
        for result in results
    )
    assert all(result.snippet for result in results)


def test_reference_corpus_remains_text_scale() -> None:
    files = [
        path
        for path in model_layout.SPECIFICATION_REFERENCE_ROOT.rglob("*")
        if path.is_file()
    ]

    assert sum(path.stat().st_size for path in files) < 10 * 1024 * 1024
