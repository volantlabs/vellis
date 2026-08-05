from __future__ import annotations

import argparse
import collections
import hashlib
import json
import logging
import math
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
        LANGUAGE_LOCK_PATH,
        RELEASE_CACHE_ROOT,
        ROOT,
        SPECIFICATION_REFERENCE_ROOT,
        VALIDATOR_CACHE_ROOT,
        VALIDATOR_LOCK_PATH,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        LANGUAGE_LOCK_PATH,
        RELEASE_CACHE_ROOT,
        ROOT,
        SPECIFICATION_REFERENCE_ROOT,
        VALIDATOR_CACHE_ROOT,
        VALIDATOR_LOCK_PATH,
    )

GENERATOR_VERSION = 3
# Okapi BM25 defaults. Deliberately not fitted to the eval set: a sweep showed
# retrieval is stable across b in 0.5-0.9, and every hand-tuned alternative lost.
BM25_K1 = 1.2
BM25_B = 0.75
# Clause titles carry the concept name ("Reference Usages", "States"), so a hit
# there is strong evidence. Swept on the register question sets: 0.0 scores 5/12
# on the jargon register, 1.8 scores 9/12, and everything above 1.8 is flat. The
# lowest weight that reaches the plateau is chosen rather than the largest.
BM25_TITLE_WEIGHT = 1.8
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
    # Interrogative and comparative filler. These used to survive as scored
    # terms, so "when should I use an item def instead of a part def" carried
    # four junk terms that diluted every real one.
    "also",
    "any",
    "as",
    "between",
    "but",
    "by",
    "difference",
    "differences",
    "differ",
    "do",
    "from",
    "i",
    "if",
    "instead",
    "it",
    "just",
    "mean",
    "means",
    "my",
    "need",
    "not",
    "only",
    "other",
    "rather",
    "should",
    "that",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "use",
    "used",
    "using",
    "versus",
    "vs",
    "want",
    "which",
    "while",
    "who",
    "why",
    "would",
    "write",
    "you",
    "your",
}


def _section_sort_key(number: str) -> tuple[object, ...]:
    """Stable tie-break: 7.9 sorts before 7.10, and letters sort after digits."""
    return tuple((0, int(part)) if part.isdigit() else (1, part) for part in number.split("."))


@dataclass(frozen=True)
class Specification:
    artifact_id: str
    specification_id: str
    title: str
    pdf_title: str
    version_identity: str
    page_footer_prefix: str
    short_label: str
    source_url: str
    source_sha256: str
    source_pdf: Path
    front_matter_start: int
    body_start: int
    expected_page_count: int
    expected_outline_count: int


@dataclass(frozen=True)
class Document:
    """One retrievable unit, whatever corpus it came from.

    The three corpora answer disjoint questions -- the specification says what a
    construct means, the library says what exists and what it specialises, and
    the examples say what it looks like -- so a hit is labelled with its source
    rather than blended into one undifferentiated ranking.

    Specification units are numbered clauses, not physical PDF pages: pages are
    an artefact of typesetting, and a clause straddling a page break used to
    split into two mediocre halves so that neither won.
    """

    source: str
    corpus_id: str
    identifier: str
    title_path: tuple[str, ...]
    citation: str
    location: Path | None
    body: str
    sort_key: tuple[object, ...]


@dataclass(frozen=True)
class SearchResult:
    source: str
    corpus_id: str
    identifier: str
    title_path: tuple[str, ...]
    citation: str
    location: Path | None
    snippet: str
    score: float

    @property
    def specification_id(self) -> str:
        return self.corpus_id

    @property
    def section_number(self) -> str:
        return self.identifier


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
    artifacts = lock.get("specifications")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing specification artifacts")
    source = lock.get("source")
    if not isinstance(source, dict):
        raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing source")
    checkout = RELEASE_CACHE_ROOT / str(source["tag"])
    specifications: list[Specification] = []
    for artifact_id in ("sysml_language_pdf", "kerml_language_pdf"):
        artifact = artifacts.get(artifact_id)
        if not isinstance(artifact, dict):
            raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing {artifact_id}")
        try:
            specifications.append(
                Specification(
                    artifact_id=artifact_id,
                    specification_id=str(artifact["specification_id"]),
                    title=str(artifact["title"]),
                    pdf_title=str(artifact["pdf_title"]),
                    version_identity=str(artifact["version_identity"]),
                    page_footer_prefix=str(artifact["page_footer_prefix"]),
                    short_label=str(artifact["short_label"]),
                    source_url=(f"{source['web_root']}/{source['tag']}/{artifact['path']}"),
                    source_sha256=str(artifact["sha256"]),
                    source_pdf=checkout / str(artifact["path"]),
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


def _page_span(start: str, end: str) -> str:
    return start if start == end else f"{start}-{end}"


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
            (later for later in entries[index + 1 :] if later["level"] <= entry["level"]),
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
    if specification.version_identity not in cover_text:
        raise RuntimeError(
            f"{specification.specification_id}: cover does not contain configured version "
            f"identity {specification.version_identity!r}"
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


def _section_paths_starting(entries: list[dict[str, Any]], physical_page: int) -> list[list[str]]:
    return [
        _entry_path(entries, entry)
        for entry in entries
        if entry["physical_page_start"] == physical_page
    ]


def _normalize_text(text: str, specification: Specification) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "")
    lines = [line.rstrip() for line in normalized.splitlines()]
    footer = re.compile(rf"^{re.escape(specification.page_footer_prefix)}\s+\d+$")
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
        f"version_identity: {_json_string(specification.version_identity)}",
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
        lines.extend(f"  - {json.dumps(path, ensure_ascii=False)}" for path in starting_paths)
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
            f"{specification.version_identity}, physical page {physical_page}. "
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
        value["printed_page_end"] = _printed_page(specification, int(entry["physical_page_end"]))
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
        f"- Specification version: `{specification.version_identity}`",
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
            text = _normalize_text(page.extract_text(extraction_mode="layout") or "", specification)
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
        "lock_sha256": _sha256(LANGUAGE_LOCK_PATH),
        "specification_id": specification.specification_id,
        "title": specification.title,
        "pdf_title": specification.pdf_title,
        "version_identity": specification.version_identity,
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
    specifications = _load_specifications()
    manifests = [
        _write_specification(specification, output_root) for specification in specifications
    ]
    links = "".join(
        f"- [{specification.short_label}]({specification.specification_id}/index.md)\n"
        for specification in specifications
    )
    (output_root / "index.md").write_text(
        "# SysML and KerML specification references\n\n"
        "Generated searchable projections of the checksum-pinned official specifications. "
        f"The official PDFs are authoritative.\n\n{links}",
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


def check(reference_root: Path = SPECIFICATION_REFERENCE_ROOT) -> list[str]:
    """Verify the generated corpus against the pin that produced it.

    The corpus is generated into the ignored cache rather than committed, so there
    is no repository copy to diff. What can go wrong instead is a lock bumped
    without regenerating, or a hand-edited page. Both are caught by comparing the
    recorded lock digest and the recorded per-file digests.
    """
    findings: list[str] = []
    lock_digest = _sha256(LANGUAGE_LOCK_PATH)
    for specification in _load_specifications():
        target = reference_root / specification.specification_id
        manifest_path = target / "manifest.json"
        if not manifest_path.exists():
            findings.append(
                f"missing generated corpus for {specification.specification_id}; "
                f"run `just model-setup`"
            )
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("lock_sha256") != lock_digest:
            findings.append(
                f"{specification.specification_id}: generated from a different language lock; "
                f"run `just model-reference-render`"
            )
            continue
        if int(manifest.get("generator_version", 0)) != GENERATOR_VERSION:
            findings.append(
                f"{specification.specification_id}: generated by generator version "
                f"{manifest.get('generator_version')}, expected {GENERATOR_VERSION}; "
                f"run `just model-reference-render`"
            )
            continue
        recorded = manifest.get("files")
        if not isinstance(recorded, dict):
            findings.append(f"{specification.specification_id}: manifest has no file digests")
            continue
        present = {
            path.relative_to(target).as_posix()
            for path in target.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        }
        for relative in sorted(set(recorded) - present):
            findings.append(f"missing generated reference: {relative}")
        for relative in sorted(present - set(recorded)):
            findings.append(f"unexpected generated reference: {relative}")
        for relative in sorted(set(recorded) & present):
            if _sha256(target / relative) != recorded[relative]:
                findings.append(f"hand-edited generated reference: {relative}")
    return findings


def _stem(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _term_counts(value: str) -> collections.Counter[str]:
    """Term frequencies for a document. Unlike a query, repetition is signal."""
    return collections.Counter(
        _stem(word) for word in SEARCH_WORD.findall(value.lower()) if word not in SEARCH_STOP_WORDS
    )


def _search_terms(value: str) -> tuple[str, ...]:
    """Distinct query terms. Deduplicated: asking twice is not asking harder."""
    terms: list[str] = []
    for word in SEARCH_WORD.findall(value.lower()):
        if word in SEARCH_STOP_WORDS:
            continue
        stemmed = _stem(word)
        if stemmed not in terms:
            terms.append(stemmed)
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


def _release_checkout() -> Path:
    lock = json.loads(LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))
    source = lock.get("source")
    if not isinstance(source, dict):
        raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing source")
    return RELEASE_CACHE_ROOT / str(source["tag"])


def _validator_library_root() -> Path:
    lock = json.loads(VALIDATOR_LOCK_PATH.read_text(encoding="utf-8"))
    version = str(lock["implementation_version"])
    return VALIDATOR_CACHE_ROOT / version / "kernel" / str(lock["kernel"]["library"])


LIBRARY_DECLARATION = re.compile(
    r"^[ \t]*(?:(?:private|protected|public)\s+)?(?:abstract\s+)?"
    r"(?P<kind>[a-z]+(?:\s+def)?)\s+(?P<name>'[^']+'|[A-Za-z_]\w*)"
    r"(?P<tail>[^{;]*)",
    re.MULTILINE,
)
LIBRARY_KINDS = frozenset(
    {
        "part def",
        "item def",
        "attribute def",
        "action def",
        "port def",
        "interface def",
        "connection def",
        "state def",
        "constraint def",
        "requirement def",
        "calc def",
        "enum def",
        "metadata def",
        "view def",
        "viewpoint def",
        "rendering def",
        "verification def",
        "case def",
        "analysis def",
        "concern def",
        "allocation def",
        "flow def",
        "occurrence def",
        "datatype",
        "class",
        "struct",
        "classifier",
        "assoc",
        "behavior",
        "function",
        "predicate",
        "interaction",
        "metaclass",
        "type",
    }
)


def _library_documents(library_root: Path | None = None) -> list[Document]:
    """Library elements: what actually exists, and what it specialises.

    The specification never lists library declarations, so questions like "what
    do I import for a String attribute" are unanswerable from prose alone. Only
    the Systems and Kernel libraries are indexed; the ISQ quantity files are
    thousands of unit types that would swamp every query.
    """
    root = library_root if library_root is not None else _validator_library_root()
    if not root.is_dir():
        return []
    documents: list[Document] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in {".sysml", ".kerml"}:
            continue
        area = path.relative_to(root).parts[0]
        if area not in {"Systems Library", "Kernel Libraries"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        package = next(
            (
                match.group(1)
                for line in lines[:5]
                if (match := re.search(r"package\s+([A-Za-z_]\w*)", line))
            ),
            path.stem,
        )
        for match in LIBRARY_DECLARATION.finditer(text):
            kind = " ".join(match.group("kind").split())
            if kind not in LIBRARY_KINDS:
                continue
            name = match.group("name").strip("'")
            line_number = text.count("\n", 0, match.start()) + 1
            declaration = " ".join(f"{kind} {name}{match.group('tail')}".split())[:200]
            documents.append(
                Document(
                    source="library",
                    corpus_id=area,
                    identifier=f"{package}::{name}",
                    title_path=(package, name),
                    citation=f"{path.relative_to(root).as_posix()}:{line_number}",
                    location=path,
                    body=f"{name} {kind} {declaration} {_declaration_doc(lines, line_number)}",
                    sort_key=(package, name),
                )
            )
    return documents


def _declaration_doc(lines: list[str], line_number: int) -> str:
    """First doc comment following a declaration, which is its definition."""
    collected: list[str] = []
    inside = False
    for line in lines[line_number : line_number + 12]:
        stripped = line.strip()
        if not inside and stripped.startswith("doc"):
            inside = True
            stripped = stripped[3:].strip()
        if inside:
            if "*/" in stripped:
                collected.append(stripped.split("*/")[0])
                break
            collected.append(stripped)
    text = " ".join(collected).replace("/*", " ").replace("*", " ")
    return " ".join(text.split())[:400]


def _example_documents(checkout: Path | None = None) -> list[Document]:
    """Training, example, and validation models: what a construct looks like.

    The 42 training modules are named for the decisions agents get wrong, and
    each is a short validated model rather than prose about one.
    """
    root = checkout if checkout is not None else _release_checkout()
    documents: list[Document] = []
    for area, base in (
        ("training", root / "sysml" / "src" / "training"),
        ("example", root / "sysml" / "src" / "examples"),
        ("validation", root / "sysml" / "src" / "validation"),
        ("kerml", root / "kerml" / "src"),
    ):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.suffix not in {".sysml", ".kerml"}:
                continue
            relative = path.relative_to(base)
            module = relative.parts[0] if len(relative.parts) > 1 else path.stem
            documents.append(
                Document(
                    source="example",
                    corpus_id=area,
                    identifier=relative.as_posix(),
                    title_path=(module, path.stem),
                    citation=f"{area}/{relative.as_posix()}",
                    location=path,
                    body=f"{module} {path.stem} "
                    + path.read_text(encoding="utf-8", errors="replace"),
                    sort_key=(area, relative.as_posix()),
                )
            )
    return documents


def _clause_documents(specification: Specification, reference_root: Path) -> list[Document]:
    root = reference_root / specification.specification_id
    outline_path = root / "outline.json"
    if not outline_path.exists():
        raise RuntimeError(
            f"missing generated corpus for {specification.specification_id} at {root}; "
            f"run `just model-setup`"
        )
    outline = json.loads(outline_path.read_text(encoding="utf-8"))
    entries = outline.get("entries")
    if not isinstance(entries, list):
        raise RuntimeError(f"invalid reference outline: {outline_path}")

    page_text: dict[int, str] = {}
    page_paths: dict[int, Path] = {}
    marker = "## Extracted specification text"
    for page_path in sorted((root / "pages").glob("page-*.md")):
        physical_page = int(page_path.stem.removeprefix("page-"))
        raw = page_path.read_text(encoding="utf-8")
        page_text[physical_page] = raw.split(marker, 1)[1] if marker in raw else raw
        page_paths[physical_page] = page_path

    clauses: list[Document] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        number = entry.get("section_number")
        if not number or int(entry.get("level", 0)) < 1:
            continue
        start = int(entry["physical_page_start"])
        end = int(entry["physical_page_end"])
        pages = [page for page in range(start, end + 1) if page in page_text]
        printed = _page_span(_printed_page(specification, start), _printed_page(specification, end))
        physical = _page_span(str(start), str(end))
        clauses.append(
            Document(
                source="specification",
                corpus_id=specification.specification_id,
                identifier=str(number),
                title_path=tuple(_entry_path(entries, entry)),
                citation=(
                    f"{specification.short_label} {number}, printed {printed}, physical {physical}"
                ),
                location=page_paths[pages[0]] if pages else None,
                body="\n".join(page_text[page] for page in pages),
                sort_key=_section_sort_key(str(number)),
            )
        )
    return clauses


def _bm25_scores(
    clauses: list[Document], terms: tuple[str, ...], *, k1: float = BM25_K1, b: float = BM25_B
) -> dict[int, float]:
    """Okapi BM25 over clause bodies, with a light title-path channel.

    Textbook parameters, deliberately not fitted. A parameter sweep showed
    retrieval degrading monotonically as title weight rises, so the title channel
    is a nudge rather than the dominant signal it used to be.
    """
    body_counts = [_term_counts(clause.body) for clause in clauses]
    title_counts = [_term_counts(" ".join(clause.title_path)) for clause in clauses]
    lengths = [sum(counts.values()) for counts in body_counts]
    total = len(clauses)
    average_length = (sum(lengths) / total) if total else 0.0
    document_frequency = collections.Counter(term for counts in body_counts for term in set(counts))
    scores: dict[int, float] = collections.defaultdict(float)
    for term in terms:
        frequency = document_frequency.get(term, 0)
        if not frequency:
            continue
        idf = math.log((total - frequency + 0.5) / (frequency + 0.5) + 1)
        for index, counts in enumerate(body_counts):
            occurrences = counts.get(term, 0)
            if occurrences:
                normalization = 1 - b + b * (lengths[index] / average_length or 1)
                scores[index] += idf * (occurrences * (k1 + 1)) / (occurrences + k1 * normalization)
            if title_counts[index].get(term, 0):
                scores[index] += BM25_TITLE_WEIGHT * idf
    return scores


SOURCES = ("specification", "library", "example")
# Below this, a hit is weak enough that the concept inventory is more useful than
# the results themselves.
WEAK_SCORE = 6.0


@dataclass(frozen=True)
class Concept:
    name: str
    pointer: str
    origin: str


def concepts(reference_root: Path = SPECIFICATION_REFERENCE_ROOT) -> list[Concept]:
    """The vocabulary an agent needs in order to ask a good question.

    Retrieval reaches the right clause ~93% of the time once the concept name is
    right, so the bottleneck is naming, not search. The inventory is small enough
    (~60 entries, well under a thousand tokens) to put in front of the agent and
    let it map the question itself.

    Two sources, because neither alone is sufficient. Clause titles are
    authoritative but use specification vocabulary; the training modules are
    finer-grained and use practitioner vocabulary. The specification calls clause
    7.6 "Definition and Usage"; the curriculum calls the same idea "Variability",
    which is the word someone actually searches for.
    """
    found: dict[str, Concept] = {}
    for specification in _load_specifications():
        outline_path = reference_root / specification.specification_id / "outline.json"
        if not outline_path.exists():
            continue
        entries = json.loads(outline_path.read_text(encoding="utf-8")).get("entries", [])
        for entry in entries:
            number = entry.get("section_number") or ""
            if not number.startswith("7."):
                continue
            depth = number.count(".")
            wanted = 1 if specification.specification_id.startswith("sysml") else 2
            if depth != wanted:
                continue
            title = re.sub(r"^[\d.]+\s*", "", str(entry["title"])).strip()
            if not title or title.endswith("Overview"):
                continue
            found.setdefault(
                title.casefold(),
                Concept(title, f"{specification.specification_id} {number}", "specification"),
            )
    training = _release_checkout() / "sysml" / "src" / "training"
    if training.is_dir():
        for module in sorted(path for path in training.iterdir() if path.is_dir()):
            title = re.sub(r"^\d+\.\s*", "", module.name).strip()
            found.setdefault(
                title.casefold(),
                Concept(title, f"training/{module.name}", "training"),
            )
    return sorted(found.values(), key=lambda concept: concept.name)


def _print_concept_hint() -> None:
    """Nothing scored well, so hand over the vocabulary instead of a bad guess."""
    print()
    print(
        "Nothing scored strongly. SysML v2 names concepts differently from common "
        "systems-engineering usage, so try naming the construct directly. Run "
        "`just model-reference-concepts` for the full inventory, then search again "
        "using the concept name."
    )


def _print_concepts(inventory: list[Concept]) -> None:
    width = max((len(concept.name) for concept in inventory), default=0)
    for concept in inventory:
        print(f"  {concept.name.ljust(width)}  {concept.pointer}")


def _rank_documents(documents: list[Document], terms: tuple[str, ...]) -> list[SearchResult]:
    scores = _bm25_scores(documents, terms)
    ranked = [
        SearchResult(
            source=documents[index].source,
            corpus_id=documents[index].corpus_id,
            identifier=documents[index].identifier,
            title_path=documents[index].title_path,
            citation=documents[index].citation,
            location=documents[index].location,
            snippet=_search_snippet(documents[index].body, terms),
            score=score,
        )
        for index, score in scores.items()
        if score > 0
    ]
    return sorted(
        ranked,
        key=lambda result: (
            -round(result.score, 6),
            result.corpus_id,
            documents_sort_key(documents, result),
        ),
    )


def documents_sort_key(documents: list[Document], result: SearchResult) -> tuple[object, ...]:
    for document in documents:
        if document.identifier == result.identifier and document.corpus_id == result.corpus_id:
            return document.sort_key
    return (result.identifier,)


def find_references(
    query: str,
    *,
    limit: int = 8,
    specification_id: str | None = None,
    sources: tuple[str, ...] = SOURCES,
    reference_root: Path = SPECIFICATION_REFERENCE_ROOT,
) -> list[SearchResult]:
    if not 1 <= limit <= 50:
        raise ValueError("reference result limit must be between 1 and 50")
    terms = _search_terms(query)
    if not terms:
        raise ValueError("reference query must contain at least one searchable term")
    unknown = set(sources) - set(SOURCES)
    if unknown:
        raise ValueError(f"unknown source: {sorted(unknown)[0]}")
    specifications = {
        specification.specification_id: specification for specification in _load_specifications()
    }
    if specification_id is not None and specification_id not in specifications:
        raise ValueError(f"unknown specification: {specification_id}")

    per_source: dict[str, list[SearchResult]] = {}
    if "specification" in sources:
        selected = (
            [specifications[specification_id]]
            if specification_id is not None
            else list(specifications.values())
        )
        clauses = [
            clause
            for specification in selected
            for clause in _clause_documents(specification, reference_root)
        ]
        per_source["specification"] = _rank_documents(clauses, terms)
    if specification_id is None:
        # A specification filter is a request for normative prose specifically.
        if "library" in sources:
            per_source["library"] = _rank_documents(_library_documents(), terms)
        if "example" in sources:
            per_source["example"] = _rank_documents(_example_documents(), terms)

    # Interleave by rank rather than merging scores. BM25 scores computed over
    # 1,550 clauses, ~400 library elements, and ~310 example models are not on a
    # common scale, and normalising them would be inventing a calibration.
    merged: list[SearchResult] = []
    position = 0
    while len(merged) < limit:
        added = False
        for name in SOURCES:
            candidates = per_source.get(name, [])
            if position < len(candidates):
                merged.append(candidates[position])
                added = True
                if len(merged) == limit:
                    break
        if not added:
            break
        position += 1
    return merged


def _print_search_results(results: list[SearchResult]) -> None:
    for index, result in enumerate(results, start=1):
        title = result.title_path[-1] if result.title_path else result.identifier
        # Every hit is labelled with the corpus it came from, so an agent never
        # has to guess whether it is reading normative prose, a library
        # declaration, or a worked example.
        print(f"{index}. [{result.source}] {title} — {result.citation}  ({result.score:.1f})")
        if len(result.title_path) > 1:
            print(f"   {' > '.join(result.title_path[:-1])}")
        if result.location is not None:
            location = result.location
            try:
                location = location.relative_to(ROOT)
            except ValueError:
                pass
            print(f"   {location}")
        print(f"   {result.snippet}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate searchable Markdown from pinned SysML and KerML specification PDFs"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("render")
    subparsers.add_parser("check")
    subparsers.add_parser("concepts")
    find_parser = subparsers.add_parser("find")
    find_parser.add_argument("query")
    find_parser.add_argument("--limit", type=int, default=8)
    find_parser.add_argument(
        "--specification",
        choices=tuple(specification.specification_id for specification in _load_specifications()),
        default=None,
    )
    args = parser.parse_args()
    try:
        if args.command == "concepts":
            _print_concepts(concepts())
            return 0
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
                print("No reference material matched the query.")
                _print_concept_hint()
                return 1
            _print_search_results(results)
            if max(result.score for result in results) < WEAK_SCORE:
                _print_concept_hint()
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
