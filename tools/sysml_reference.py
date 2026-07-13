from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pypdf import PdfReader

try:
    from .model_layout import (
        FORMAL_CACHE_ROOT,
        LANGUAGE_LOCK_PATH,
        ROOT,
        SPECIFICATION_REFERENCE_ROOT,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        FORMAL_CACHE_ROOT,
        LANGUAGE_LOCK_PATH,
        ROOT,
        SPECIFICATION_REFERENCE_ROOT,
    )

GENERATOR_VERSION = 2
SECTION_NUMBER = re.compile(r"^(?P<number>(?:\d+|[A-Z])(?:\.\d+)*)\s+")
SEARCH_WORD = re.compile(r"[a-z0-9]+")
SEARCH_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "be",
    "can",
    "does",
    "for",
    "how",
    "in",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "what",
    "when",
    "with",
}


@dataclass(frozen=True)
class Specification:
    artifact_id: str
    specification_id: str
    title: str
    pdf_title: str
    document_number: str
    source_url: str
    source_sha256: str
    source_pdf: Path
    front_matter_start: int
    body_start: int
    expected_page_count: int
    expected_outline_count: int


@dataclass(frozen=True)
class SearchResult:
    specification_id: str
    physical_page: int
    printed_page: str
    page_path: Path
    section_titles: tuple[str, ...]
    snippet: str
    score: float


class _WarningCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if message not in self.messages:
            self.messages.append(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_specifications() -> list[Specification]:
    lock = json.loads(LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))
    grammar = lock.get("grammar")
    if not isinstance(grammar, dict):
        raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing grammar artifacts")
    specifications: list[Specification] = []
    for artifact_id in ("sysml_language_pdf", "kerml_language_pdf"):
        artifact = grammar.get(artifact_id)
        if not isinstance(artifact, dict):
            raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing {artifact_id}")
        try:
            specifications.append(
                Specification(
                    artifact_id=artifact_id,
                    specification_id=str(artifact["specification_id"]),
                    title=str(artifact["title"]),
                    pdf_title=str(artifact["pdf_title"]),
                    document_number=str(artifact["document_number"]),
                    source_url=str(artifact["url"]),
                    source_sha256=str(artifact["sha256"]),
                    source_pdf=FORMAL_CACHE_ROOT / f"{artifact_id}.pdf",
                    front_matter_start=int(artifact["front_matter_start_physical_page"]),
                    body_start=int(artifact["body_start_physical_page"]),
                    expected_page_count=int(artifact["expected_page_count"]),
                    expected_outline_count=int(artifact["expected_outline_count"]),
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: invalid {artifact_id}: {error}") from error
    return specifications


def _verify_source(specification: Specification) -> None:
    if not specification.source_pdf.exists():
        raise RuntimeError(
            f"missing pinned {specification.specification_id} PDF at "
            f"{specification.source_pdf}; run `just model-setup`"
        )
    actual = _sha256(specification.source_pdf)
    if actual != specification.source_sha256:
        raise RuntimeError(
            f"checksum mismatch for {specification.source_pdf}: expected "
            f"{specification.source_sha256}, found {actual}; run `just model-setup`"
        )


def _roman(number: int) -> str:
    values = (
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    )
    result: list[str] = []
    remaining = number
    for value, numeral in values:
        while remaining >= value:
            result.append(numeral)
            remaining -= value
    return "".join(result)


def _printed_page(specification: Specification, physical_page: int) -> str:
    if physical_page < specification.front_matter_start:
        return f"pdf-{physical_page}"
    if physical_page < specification.body_start:
        return _roman(physical_page - specification.front_matter_start + 1)
    return str(physical_page - specification.body_start + 1)


def _section_number(title: str) -> str | None:
    match = SECTION_NUMBER.match(title)
    return match.group("number") if match else None


def _flatten_outline(reader: PdfReader) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    def visit(items: Iterable[Any], level: int, parent_id: int | None) -> None:
        last_entry_id: int | None = None
        for item in items:
            if isinstance(item, list):
                visit(item, level + 1, last_entry_id if last_entry_id is not None else parent_id)
                continue
            destination_page = reader.get_destination_page_number(item)
            if destination_page is None:
                raise RuntimeError(f"outline destination has no page: {item}")
            physical_page = destination_page + 1
            title = str(getattr(item, "title", item)).strip()
            entry_id = len(entries)
            entries.append(
                {
                    "id": entry_id,
                    "parent_id": parent_id,
                    "level": level,
                    "section_number": _section_number(title),
                    "title": title,
                    "physical_page_start": physical_page,
                }
            )
            last_entry_id = entry_id

    visit(reader.outline, 0, None)
    page_count = len(reader.pages)
    for index, entry in enumerate(entries):
        next_page = (
            entries[index + 1]["physical_page_start"]
            if index + 1 < len(entries)
            else page_count + 1
        )
        entry["physical_page_end"] = max(entry["physical_page_start"], next_page - 1)
        next_peer = next(
            (
                later
                for later in entries[index + 1 :]
                if later["level"] <= entry["level"]
            ),
            None,
        )
        entry["subtree_physical_page_end"] = (
            max(entry["physical_page_start"], next_peer["physical_page_start"] - 1)
            if next_peer is not None
            else page_count
        )
    return entries


def _verify_pdf_identity(
    specification: Specification,
    reader: PdfReader,
    entries: list[dict[str, Any]],
) -> None:
    actual_title = str(reader.metadata.title if reader.metadata is not None else "")
    if actual_title != specification.pdf_title:
        raise RuntimeError(
            f"{specification.specification_id}: expected PDF title "
            f"{specification.pdf_title!r}, found {actual_title!r}"
        )
    cover_text = reader.pages[0].extract_text() or ""
    if specification.document_number not in cover_text:
        raise RuntimeError(
            f"{specification.specification_id}: cover does not contain configured document "
            f"number {specification.document_number!r}"
        )
    anchors = {str(entry["title"]): int(entry["physical_page_start"]) for entry in entries}
    expected_anchors = {
        "Table of Contents": specification.front_matter_start,
        "1 Scope": specification.body_start,
    }
    for title, expected_page in expected_anchors.items():
        actual_page = anchors.get(title)
        if actual_page != expected_page:
            raise RuntimeError(
                f"{specification.specification_id}: expected outline entry {title!r} on "
                f"physical page {expected_page}, found {actual_page}"
            )


def _entry_path(entries: list[dict[str, Any]], entry: dict[str, Any]) -> list[str]:
    by_id = {int(candidate["id"]): candidate for candidate in entries}
    path = [str(entry["title"])]
    parent_id = entry["parent_id"]
    while parent_id is not None:
        parent = by_id[int(parent_id)]
        path.append(str(parent["title"]))
        parent_id = parent["parent_id"]
    return list(reversed(path))


def _page_context_before(entries: list[dict[str, Any]], physical_page: int) -> list[str]:
    prior = [entry for entry in entries if entry["physical_page_start"] < physical_page]
    return _entry_path(entries, prior[-1]) if prior else []


def _section_paths_starting(
    entries: list[dict[str, Any]], physical_page: int
) -> list[list[str]]:
    return [
        _entry_path(entries, entry)
        for entry in entries
        if entry["physical_page_start"] == physical_page
    ]


def _normalize_text(text: str, specification: Specification) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "")
    lines = [line.rstrip() for line in normalized.splitlines()]
    if specification.specification_id == "sysml-2.0":
        footer = re.compile(r"^Systems Modeling Language v2\.0, Part 1\s+\d+$")
    else:
        footer = re.compile(r"^Kernel Modeling Language v1\.0\s+\d+$")
    lines = [line for line in lines if not footer.fullmatch(line.strip())]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    compact: list[str] = []
    blank_count = 0
    for line in lines:
        if line:
            blank_count = 0
            compact.append(line)
        else:
            blank_count += 1
            if blank_count <= 2:
                compact.append("")
    return "\n".join(compact)


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _page_markdown(
    specification: Specification,
    physical_page: int,
    context_before: list[str],
    starting_paths: list[list[str]],
    starts: list[str],
    text: str,
    extraction_warnings: list[str],
) -> str:
    printed_page = _printed_page(specification, physical_page)
    lines = [
        "---",
        f"specification_id: {_json_string(specification.specification_id)}",
        f"specification: {_json_string(specification.title)}",
        f"document_number: {_json_string(specification.document_number)}",
        f"source_url: {_json_string(specification.source_url)}",
        f"source_sha256: {_json_string(specification.source_sha256)}",
        f"physical_page: {physical_page}",
        f"printed_page: {_json_string(printed_page)}",
        "generated: true",
        "section_context_before_page:",
    ]
    if context_before:
        lines.extend(f"  - {_json_string(title)}" for title in context_before)
    else:
        lines[-1] = "section_context_before_page: []"
    if starting_paths:
        lines.append("section_paths_starting_here:")
        lines.extend(
            f"  - {json.dumps(path, ensure_ascii=False)}" for path in starting_paths
        )
    else:
        lines.append("section_paths_starting_here: []")
    if starts:
        lines.append("sections_starting_here:")
        lines.extend(f"  - {_json_string(title)}" for title in starts)
    else:
        lines.append("sections_starting_here: []")
    if extraction_warnings:
        lines.append("extraction_warnings:")
        lines.extend(f"  - {_json_string(message)}" for message in extraction_warnings)
    else:
        lines.append("extraction_warnings: []")
    lines.extend(
        [
            "---",
            "",
            f"# {specification.specification_id} physical page {physical_page} "
            f"(printed {printed_page})",
            "",
            "## Extracted specification text",
            "",
            text or "_[No extractable text on this source page.]_",
            "",
            "---",
            "",
            f"Source: [{specification.title}]({specification.source_url}), "
            f"{specification.document_number}, physical page {physical_page}. "
            "The official PDF is authoritative.",
            "",
        ]
    )
    return "\n".join(lines)


def _outline_data(
    specification: Specification,
    page_count: int,
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    projected: list[dict[str, Any]] = []
    for entry in entries:
        value = dict(entry)
        value["printed_page_start"] = _printed_page(
            specification, int(entry["physical_page_start"])
        )
        value["printed_page_end"] = _printed_page(
            specification, int(entry["physical_page_end"])
        )
        projected.append(value)
    return {
        "schema_version": 1,
        "specification_id": specification.specification_id,
        "source_sha256": specification.source_sha256,
        "page_count": page_count,
        "outline_entry_count": len(entries),
        "entries": projected,
    }


def _index_markdown(
    specification: Specification,
    page_count: int,
    entries: list[dict[str, Any]],
) -> str:
    lines = [
        f"# {specification.title}",
        "",
        "This is a generated, searchable projection of the checksum-pinned official PDF. The PDF",
        "is authoritative; do not edit these pages manually or treat them as a replacement",
        "specification.",
        "",
        f"- OMG document: `{specification.document_number}`",
        f"- Official source: [{specification.source_url}]({specification.source_url})",
        f"- Source SHA-256: `{specification.source_sha256}`",
        f"- Physical pages: {page_count}",
        f"- Outline entries: {len(entries)}",
        "- Copyright and permission notices: see physical pages 1-8 in this corpus and the",
        "  official PDF.",
        "",
        "## Outline",
        "",
    ]
    for entry in entries:
        page = int(entry["physical_page_start"])
        indent = "  " * int(entry["level"])
        printed = _printed_page(specification, page)
        lines.append(
            f"{indent}- [{entry['title']}](pages/page-{page:04d}.md) "
            f"(physical {page}, printed {printed})"
        )
    lines.append("")
    return "\n".join(lines)


def _write_specification(specification: Specification, output_root: Path) -> dict[str, Any]:
    _verify_source(specification)
    reader = PdfReader(specification.source_pdf)
    page_count = len(reader.pages)
    entries = _flatten_outline(reader)
    if page_count != specification.expected_page_count:
        raise RuntimeError(
            f"{specification.specification_id}: expected "
            f"{specification.expected_page_count} pages, "
            f"found {page_count}"
        )
    if len(entries) != specification.expected_outline_count:
        raise RuntimeError(
            f"{specification.specification_id}: expected {specification.expected_outline_count} "
            f"outline entries, found {len(entries)}"
        )
    _verify_pdf_identity(specification, reader, entries)

    target = output_root / specification.specification_id
    pages = target / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    extraction_warning_pages: dict[str, list[str]] = {}
    warning_logger = logging.getLogger("pypdf._text_extraction._layout_mode._fixed_width_page")
    warning_collector = _WarningCollector()
    previous_propagate = warning_logger.propagate
    warning_logger.addHandler(warning_collector)
    warning_logger.propagate = False
    try:
        for physical_page, page in enumerate(reader.pages, start=1):
            warning_collector.messages.clear()
            starts = [
                str(entry["title"])
                for entry in entries
                if entry["physical_page_start"] == physical_page
            ]
            text = _normalize_text(
                page.extract_text(extraction_mode="layout") or "", specification
            )
            warnings = list(warning_collector.messages)
            if warnings:
                extraction_warning_pages[str(physical_page)] = warnings
            (pages / f"page-{physical_page:04d}.md").write_text(
                _page_markdown(
                    specification,
                    physical_page,
                    _page_context_before(entries, physical_page),
                    _section_paths_starting(entries, physical_page),
                    starts,
                    text,
                    warnings,
                ),
                encoding="utf-8",
            )
    finally:
        warning_logger.removeHandler(warning_collector)
        warning_logger.propagate = previous_propagate

    (target / "outline.json").write_text(
        json.dumps(_outline_data(specification, page_count, entries), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (target / "index.md").write_text(
        _index_markdown(specification, page_count, entries), encoding="utf-8"
    )
    files = {
        path.relative_to(target).as_posix(): _sha256(path)
        for path in sorted(target.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    manifest = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "specification_id": specification.specification_id,
        "title": specification.title,
        "pdf_title": specification.pdf_title,
        "document_number": specification.document_number,
        "source_url": specification.source_url,
        "source_sha256": specification.source_sha256,
        "page_count": page_count,
        "outline_entry_count": len(entries),
        "extraction_warning_pages": extraction_warning_pages,
        "files": files,
    }
    (target / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _render_into(output_root: Path) -> list[dict[str, Any]]:
    output_root.mkdir(parents=True)
    manifests = [
        _write_specification(specification, output_root)
        for specification in _load_specifications()
    ]
    (output_root / "index.md").write_text(
        "# SysML and KerML specification references\n\n"
        "Generated searchable projections of the checksum-pinned official specifications. "
        "The official PDFs are authoritative.\n\n"
        "- [SysML 2.0](sysml-2.0/index.md)\n"
        "- [KerML 1.0](kerml-1.0/index.md)\n",
        encoding="utf-8",
    )
    return manifests


def render(output_root: Path = SPECIFICATION_REFERENCE_ROOT) -> list[dict[str, Any]]:
    specifications = _load_specifications()
    for specification in specifications:
        _verify_source(specification)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="vellis-sysml-reference-render-", dir=output_root.parent
    ) as temporary:
        staged = Path(temporary) / "specifications"
        manifests = _render_into(staged)
        if output_root.exists():
            shutil.rmtree(output_root)
        staged.replace(output_root)
    return manifests


def _directory_files(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def check(reference_root: Path = SPECIFICATION_REFERENCE_ROOT) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="vellis-sysml-reference-") as temporary:
        generated = Path(temporary) / "specifications"
        render(generated)
        expected = _directory_files(generated)
        actual = _directory_files(reference_root)
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    changed = sorted(path for path in set(expected) & set(actual) if expected[path] != actual[path])
    findings: list[str] = []
    findings.extend(f"missing generated reference: {path}" for path in missing)
    findings.extend(f"unexpected generated reference: {path}" for path in extra)
    findings.extend(f"stale generated reference: {path}" for path in changed)
    return findings


def _search_terms(value: str) -> tuple[str, ...]:
    terms: list[str] = []
    for word in SEARCH_WORD.findall(value.lower()):
        if word in SEARCH_STOP_WORDS:
            continue
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        if word not in terms:
            terms.append(word)
    return tuple(terms)


def _search_snippet(text: str, terms: tuple[str, ...]) -> str:
    marker = "## Extracted specification text"
    body = text.split(marker, 1)[1] if marker in text else text
    lines = [line.strip() for line in body.splitlines() if line.strip() and line != "---"]
    best = ""
    best_score = -1
    for index in range(len(lines)):
        candidate = " ".join(lines[index : index + 3])
        candidate_terms = set(_search_terms(candidate))
        score = sum(term in candidate_terms for term in terms)
        if score > best_score:
            best = candidate
            best_score = score
    compact = re.sub(r"\s+", " ", best).strip()
    return compact[:320] + ("…" if len(compact) > 320 else "")


def find_references(
    query: str,
    *,
    limit: int = 8,
    specification_id: str | None = None,
    reference_root: Path = SPECIFICATION_REFERENCE_ROOT,
) -> list[SearchResult]:
    terms = _search_terms(query)
    if not terms:
        raise ValueError("reference query must contain at least one searchable term")
    normalized_query = " ".join(terms)
    specifications = {
        specification.specification_id: specification
        for specification in _load_specifications()
    }
    selected = (
        [specifications[specification_id]]
        if specification_id is not None
        else list(specifications.values())
    )
    results: list[SearchResult] = []
    for specification in selected:
        root = reference_root / specification.specification_id
        outline_path = root / "outline.json"
        if not outline_path.exists():
            raise RuntimeError(f"missing reference outline: {outline_path}")
        outline = json.loads(outline_path.read_text(encoding="utf-8"))
        entries = outline.get("entries")
        if not isinstance(entries, list):
            raise RuntimeError(f"invalid reference outline: {outline_path}")
        entries_by_page: dict[int, list[dict[str, Any]]] = {}
        for entry in entries:
            if isinstance(entry, dict):
                entries_by_page.setdefault(int(entry["physical_page_start"]), []).append(entry)
        for page_path in sorted((root / "pages").glob("page-*.md")):
            physical_page = int(page_path.stem.removeprefix("page-"))
            text = page_path.read_text(encoding="utf-8")
            text_terms = _search_terms(text)
            text_term_set = set(text_terms)
            matched = sum(term in text_term_set for term in terms)
            if matched == 0:
                continue
            coverage = matched / len(terms)
            normalized_text = " ".join(text_terms)
            frequency = sum(min(normalized_text.count(term), 8) for term in terms)
            page_entries = entries_by_page.get(physical_page, [])
            section_titles = (
                tuple(str(entry["title"]) for entry in page_entries)
                if page_entries
                else tuple(_page_context_before(entries, physical_page))
            )
            section_term_set = set(_search_terms(" ".join(section_titles)))
            section_matched = sum(term in section_term_set for term in terms)
            section_coverage = section_matched / len(terms)
            score = coverage * 50 + section_coverage * 45 + min(frequency, 20)
            if coverage == 1:
                score += 35
            if section_coverage == 1:
                score += 55
            if normalized_query in normalized_text:
                score += 70
            results.append(
                SearchResult(
                    specification_id=specification.specification_id,
                    physical_page=physical_page,
                    printed_page=_printed_page(specification, physical_page),
                    page_path=page_path,
                    section_titles=section_titles,
                    snippet=_search_snippet(text, terms),
                    score=score,
                )
            )
    return sorted(
        results,
        key=lambda result: (-result.score, result.specification_id, result.physical_page),
    )[:limit]


def _print_search_results(results: list[SearchResult]) -> None:
    for index, result in enumerate(results, start=1):
        sections = "; ".join(result.section_titles) or "continuation page"
        try:
            page_path = result.page_path.relative_to(ROOT)
        except ValueError:
            page_path = result.page_path
        print(
            f"{index}. {result.specification_id}: {sections} — physical "
            f"{result.physical_page}, printed {result.printed_page}"
        )
        print(f"   {page_path}")
        print(f"   {result.snippet}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate searchable Markdown from pinned SysML and KerML specification PDFs"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("render")
    subparsers.add_parser("check")
    find_parser = subparsers.add_parser("find")
    find_parser.add_argument("query")
    find_parser.add_argument("--limit", type=int, default=8)
    find_parser.add_argument(
        "--specification", choices=("sysml-2.0", "kerml-1.0"), default=None
    )
    args = parser.parse_args()
    try:
        if args.command == "render":
            manifests = render()
            for manifest in manifests:
                print(
                    f"Rendered {manifest['specification_id']}: {manifest['page_count']} pages, "
                    f"{manifest['outline_entry_count']} outline entries."
                )
            return 0
        if args.command == "find":
            results = find_references(
                args.query,
                limit=args.limit,
                specification_id=args.specification,
            )
            if not results:
                print("No reference pages matched the query.")
                return 1
            _print_search_results(results)
            return 0
        findings = check()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"ERROR {error}")
        return 1
    if findings:
        for finding in findings:
            print(f"ERROR {finding}")
        print(f"Reference check failed with {len(findings)} finding(s).")
        return 1
    print("SysML and KerML reference corpus is current.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
