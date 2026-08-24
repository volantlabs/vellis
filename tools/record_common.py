"""Record helpers shared by the durable engineering records.

Extracted from the retired implementation-campaign engine. `_evidence_reference_findings`
drops that engine's committed-revision lookup: the evolution record is the only caller and
always resolves against the working tree.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath

import yaml

try:
    from .model_layout import ROOT
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import ROOT  # type: ignore[no-redef]


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def authored_model_files(root: Path = ROOT) -> list[Path]:
    files = sorted((root / "model").glob("*.sysml"), key=lambda path: path.name)
    if not files:
        raise ValueError(f"no authored SysML files found under {root / 'model'}")
    return files


def authority_digest(root: Path = ROOT) -> str:
    entries = [
        {
            "path": path.relative_to(root).as_posix(),
            "sha256": _sha256(path),
        }
        for path in authored_model_files(root)
    ]
    canonical = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _markdown_anchors(source: str) -> set[str]:
    anchors: set[str] = set()
    counts: Counter[str] = Counter()
    for line in source.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", line)
        if match is None:
            continue
        heading = match.group(1).strip().lower()
        base = "".join(
            character for character in heading if character.isalnum() or character in " -_"
        )
        base = re.sub(r"\s+", "-", base)
        suffix = counts[base]
        counts[base] += 1
        anchors.add(base if suffix == 0 else f"{base}-{suffix}")
    return anchors


def _python_test_nodes(source: str) -> set[str]:
    try:
        module = ast.parse(source)
    except SyntaxError:
        return set()
    nodes: set[str] = set()
    for item in module.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name.startswith(
            "test_"
        ):
            nodes.add(item.name)
        elif isinstance(item, ast.ClassDef):
            for child in item.body:
                if isinstance(
                    child, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) and child.name.startswith("test_"):
                    nodes.add(f"{item.name}::{child.name}")
    return nodes


def _evidence_fragment_exists(path: str, source: str, fragment: str) -> bool:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix == ".md":
        return fragment in _markdown_anchors(source)
    if suffix == ".py":
        return fragment in _python_test_nodes(source)
    return False


def _evidence_reference_findings(reference: str, *, label: str, root: Path) -> list[str]:
    if reference.startswith("command:"):
        command = reference.removeprefix("command:")
        if (
            not command.strip()
            or command != command.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in command)
        ):
            return [f"{label} command evidence must contain one exact nonempty command"]
        return []
    if reference.startswith("path:"):
        value = reference.removeprefix("path:")
        path_text, separator, fragment = value.partition("#")
        path = PurePosixPath(path_text)
        if (
            separator != "#"
            or not fragment.strip()
            or not path_text
            or "\\" in path_text
            or path.is_absolute()
            or ".." in path.parts
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            return [f"{label} path evidence must be path:<repo-relative-path>#<test-or-section>"]
        candidate = root / Path(*path.parts)
        try:
            resolved_root = root.resolve(strict=True)
            resolved = candidate.resolve(strict=True)
        except OSError:
            return [f"{label} path evidence does not exist: {path_text}"]
        if not resolved.is_relative_to(resolved_root):
            return [f"{label} path evidence escapes the repository through a symlink: {path_text}"]
        if not resolved.is_file() or candidate.is_symlink():
            return [f"{label} path evidence does not exist: {path_text}"]
        try:
            source = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return [f"{label} path evidence must be UTF-8 Markdown or Python: {path_text}"]
        if not _evidence_fragment_exists(path_text, source, fragment):
            return [f"{label} evidence fragment does not resolve: {path_text}#{fragment}"]
        return []
    return [f"{label} evidence must use path: or command:"]
