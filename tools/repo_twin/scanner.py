from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from components.rtg.graph.protocol import JsonObject
from tools.repo_twin.model import (
    IMPORTER_VERSION,
    SCHEMA_VERSION,
    AnchorRecord,
    ComponentScan,
    DataRecord,
    ImplementationScan,
    LinkRecord,
    ParseIssue,
    RepoMetadata,
    ScanResult,
)

_COMPONENT_ID_RE = re.compile(r"^component\.[A-Za-z0-9_.-]+$")
_COMPONENT_IDENTITY_RE = re.compile(r"\bpart def\s+<'(component\.[^']+)'>\s+(\w+)")
_STATUS_RE = re.compile(
    r"@SpecificationStatus\s*\{[^}]*lifecycleStatus\s*=\s*SpecLifecycle::(\w+);",
    re.DOTALL,
)
_OWNER_RE = re.compile(r'@SpecificationStatus\s*\{[^}]*owner\s*=\s*"([^"]*)";', re.DOTALL)
_REALIZATION_RE = re.compile(r"\bpart def\s+\w+\s*:>\s*(\w+)\s*\{")
_CODE_ROOT_RE = re.compile(r'codeRoot\s*=\s*"([^"]+)"')
_REF_PART_RE = re.compile(r"\bref part\s+\w+\s*\[[^]]+\]\s*:\s*(\w+)\s*;")


def scan_repo(repo_root: Path) -> ScanResult:
    root = repo_root.resolve()
    metadata = repo_metadata(root)
    anchors: dict[str, AnchorRecord] = {}
    data_objects: dict[str, DataRecord] = {}
    links: dict[str, LinkRecord] = {}
    components: dict[str, ComponentScan] = {}
    implementation_roots: dict[str, ImplementationScan] = {}
    parse_issues: list[ParseIssue] = []
    component_paths: dict[str, list[str]] = {}
    now = metadata.indexed_at

    repo_key = "repo"
    anchors[repo_key] = AnchorRecord(repo_key, "twin.Repo", "Vellis repository")

    parsed_models, model_issues = _parse_component_models(root, metadata, now)
    parse_issues.extend(model_issues)
    for parsed in parsed_models:
        component = parsed.component
        component_paths.setdefault(component.component_id, []).append(component.spec_path)
        if component.component_id in components:
            continue
        components[component.component_id] = component
        anchors.update(parsed.anchors)
        data_objects.update(parsed.data_objects)
        links.update(parsed.links)

    duplicate_component_ids = {
        component_id: tuple(paths)
        for component_id, paths in sorted(component_paths.items())
        if len(paths) > 1
    }

    declared_roots: dict[str, list[str]] = {}
    for component in components.values():
        for code_root in component.declared_code_roots:
            declared_roots.setdefault(code_root, []).append(component.component_id)

    for impl_path in _implementation_root_paths(root):
        impl = _scan_implementation_root(root, impl_path)
        implementation_roots[impl.path] = impl
        impl_key = f"impl:{impl.path}"
        anchors[impl_key] = AnchorRecord(impl_key, "twin.ImplementationRoot", impl.path)
        data_objects[f"{impl_key}:fact"] = DataRecord(
            f"{impl_key}:fact",
            "twin.ImplementationRootFact",
            {
                **_grounding(
                    source_path=impl.path,
                    source_hash=impl.source_hash,
                    metadata=metadata,
                    indexed_at=now,
                    authority="derived",
                    lifecycle_status="active",
                ),
                "language": "python",
                "has_protocol": impl.has_protocol,
                "has_implementation": impl.has_implementation,
                "has_reference": impl.has_reference,
                "has_tests": impl.has_tests,
                "protocol_hash": impl.protocol_hash,
                "file_count": impl.file_count,
            },
            (impl_key,),
        )
        if impl.has_tests:
            tests_path = f"{impl.path}/tests"
            tests_key = f"tests:{tests_path}"
            anchors[tests_key] = AnchorRecord(tests_key, "twin.TestSuite", tests_path)
            data_objects[f"{tests_key}:fact"] = DataRecord(
                f"{tests_key}:fact",
                "twin.TestSuiteFact",
                {
                    **_grounding(
                        source_path=tests_path,
                        source_hash=_directory_hash(root, root / tests_path, suffixes=(".py",)),
                        metadata=metadata,
                        indexed_at=now,
                        authority="derived",
                        lifecycle_status="active",
                    ),
                    "test_file_names": list(impl.test_file_names),
                    "test_file_count": len(impl.test_file_names),
                },
                (tests_key,),
            )
            _add_link(links, "twin.HasTestSuite", impl_key, tests_key)

        for component_id in declared_roots.get(impl.path, ()):
            component_key = f"component:{component_id}"
            _add_link(links, "twin.HasImplementationRoot", component_key, impl_key)
            if impl.has_tests:
                _add_link(links, "twin.Verifies", f"tests:{impl.path}/tests", component_key)

    for app_path in sorted((root / "apps").glob("*")):
        if not app_path.is_dir() or app_path.name == "__pycache__":
            continue
        app_relative = _relative_path(root, app_path)
        app_key = f"app:{app_relative}"
        modules = tuple(
            sorted(
                _relative_path(app_path, path.with_suffix(""))
                for path in app_path.rglob("*.py")
                if "__pycache__" not in path.parts
            )
        )
        anchors[app_key] = AnchorRecord(app_key, "twin.App", app_relative)
        data_objects[f"{app_key}:fact"] = DataRecord(
            f"{app_key}:fact",
            "twin.AppFact",
            {
                **_grounding(
                    source_path=app_relative,
                    source_hash=_directory_hash(root, app_path, suffixes=(".py",)),
                    metadata=metadata,
                    indexed_at=now,
                    authority="derived",
                    lifecycle_status="active",
                ),
                "entry_point": (
                    f"{app_relative}/__main__.py" if (app_path / "__main__.py").is_file() else None
                ),
                "module_names": list(modules),
            },
            (app_key,),
        )

    repo_hash = _hash_text(
        "\n".join(
            sorted(
                [
                    *(
                        str(item.properties.get("source_hash", ""))
                        for item in data_objects.values()
                    ),
                    *(component.component_id for component in components.values()),
                ]
            )
        )
    )
    data_objects["repo:fact"] = DataRecord(
        "repo:fact",
        "twin.RepoFact",
        {
            **_grounding(
                source_path=".",
                source_hash=repo_hash,
                metadata=metadata,
                indexed_at=now,
                authority="derived",
                lifecycle_status="active",
            ),
            "branch": metadata.branch,
            "dirty": metadata.dirty,
            "importer_version": IMPORTER_VERSION,
            "schema_version": SCHEMA_VERSION,
        },
        (repo_key,),
    )

    resolvable_links = {
        natural_key: link
        for natural_key, link in links.items()
        if link.source_key in anchors and link.target_key in anchors
    }
    return ScanResult(
        anchors=tuple(sorted(anchors.values(), key=lambda item: item.natural_key)),
        data_objects=tuple(sorted(data_objects.values(), key=lambda item: item.natural_key)),
        links=tuple(sorted(resolvable_links.values(), key=lambda item: item.natural_key)),
        components=components,
        implementation_roots=implementation_roots,
        parse_issues=tuple(parse_issues),
        duplicate_component_ids=duplicate_component_ids,
    )


@dataclass(frozen=True, slots=True)
class _ParsedModel:
    component: ComponentScan
    anchors: dict[str, AnchorRecord]
    data_objects: dict[str, DataRecord]
    links: dict[str, LinkRecord]


def _parse_component_models(
    root: Path,
    metadata: RepoMetadata,
    indexed_at: str,
) -> tuple[tuple[_ParsedModel, ...], tuple[ParseIssue, ...]]:
    index_path = root / "generated" / "model" / "formal-model-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return (), (
            ParseIssue(_relative_or_path(root, index_path), f"invalid formal model index: {error}"),
        )
    if not isinstance(index, dict):
        return (), (
            ParseIssue(_relative_or_path(root, index_path), "formal model index must be an object"),
        )
    packages = index.get("packages")
    authored = index.get("authored_packages")
    if not isinstance(packages, dict) or not isinstance(authored, dict):
        return (), (
            ParseIssue(
                _relative_path(root, index_path), "formal model index lacks package inventories"
            ),
        )

    source_paths = {str(value) for value in authored.values() if isinstance(value, str)}
    actual_paths = {
        _relative_path(root, path) for path in (root / "model").rglob("*.sysml") if path.is_file()
    }
    issues: list[ParseIssue] = []
    if source_paths != actual_paths:
        issues.append(
            ParseIssue(
                _relative_path(root, index_path),
                "formal model index inventory is stale; run `just model-render`",
            )
        )
    elif index.get("source_digest") != _model_source_digest(root, source_paths):
        issues.append(
            ParseIssue(
                _relative_path(root, index_path),
                "formal model index source digest is stale; run `just model-render`",
            )
        )
    if issues:
        return (), tuple(issues)

    component_entries: list[tuple[str, str, str, dict[str, object]]] = []
    definition_owners: dict[str, str] = {}
    for _package_name, raw_package in packages.items():
        if not isinstance(raw_package, dict):
            continue
        source = raw_package.get("source")
        elements = raw_package.get("named_elements")
        if not isinstance(source, str) or not source.startswith("model/bibliotek/components/"):
            continue
        if not isinstance(elements, list):
            continue
        for raw_element in elements:
            if not isinstance(raw_element, dict) or raw_element.get("kind") != "PartDefinition":
                continue
            component_id = raw_element.get("short_name")
            definition_name = raw_element.get("name")
            if (
                isinstance(component_id, str)
                and _COMPONENT_ID_RE.fullmatch(component_id)
                and isinstance(definition_name, str)
            ):
                component_entries.append(
                    (component_id, definition_name, source, cast(dict[str, object], raw_package))
                )
                definition_owners[definition_name] = component_id

    code_roots = _realization_code_roots(root)
    parsed: list[_ParsedModel] = []
    for component_id, definition_name, source, package in component_entries:
        path = root / source
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            issues.append(ParseIssue(source, str(error)))
            continue
        identity = _COMPONENT_IDENTITY_RE.search(text)
        status = _STATUS_RE.search(text)
        if (
            identity is None
            or identity.group(1) != component_id
            or identity.group(2) != definition_name
        ):
            issues.append(
                ParseIssue(source, f"component identity {component_id!r} is absent or ambiguous")
            )
            continue
        if status is None:
            issues.append(
                ParseIssue(source, "component lacks @SpecificationStatus lifecycleStatus")
            )
            continue
        owner_match = _OWNER_RE.search(text)
        owner = owner_match.group(1) if owner_match else ""
        component_block = _extract_braced_block(text, identity.start())
        related_ids = tuple(
            sorted(
                {
                    definition_owners[required_type]
                    for required_type in _REF_PART_RE.findall(component_block)
                    if required_type in definition_owners
                    and definition_owners[required_type] != component_id
                }
            )
        )
        elements = package.get("named_elements")
        named_elements = (
            [item for item in elements if isinstance(item, dict)]
            if isinstance(elements, list)
            else []
        )
        stable_requirements = {
            str(item["short_name"]): str(item.get("name", item["short_name"]))
            for item in named_elements
            if item.get("kind") == "RequirementUsage"
            and isinstance(item.get("short_name"), str)
            and str(item["short_name"]).startswith(("contract.", "invariant."))
        }
        contract_blocks = [component_block]
        for match in re.finditer(r"(?m)^\s*action def\s+\w+\s*\{", text):
            contract_blocks.append(_extract_braced_block(text, match.start()))
        for stable_id in sorted(stable_requirements):
            marker = re.search(rf"\brequirement\s+<'{re.escape(stable_id)}'>\s+\w+\s*\{{", text)
            if marker is not None:
                contract_blocks.append(_extract_braced_block(text, marker.start()))
        contract_hash = _hash_text("\n".join(contract_blocks))
        component = ComponentScan(
            component_id=component_id,
            status=status.group(1),
            spec_path=source,
            declared_code_roots=tuple(sorted(code_roots.get(definition_name, ()))),
            section_hashes={"Provided contracts": contract_hash},
            related_component_ids=related_ids,
        )
        component_key = f"component:{component_id}"
        authority_key = f"spec:{source}"
        source_hash = _file_hash(path)
        anchors = {
            component_key: AnchorRecord(component_key, "twin.Component", component_id),
            authority_key: AnchorRecord(authority_key, "twin.SpecDocument", path.name),
        }
        element_kinds = sorted(
            {str(item.get("kind")) for item in named_elements if item.get("kind")}
        )
        data_objects: dict[str, DataRecord] = {
            f"{component_key}:fact": DataRecord(
                f"{component_key}:fact",
                "twin.ComponentFact",
                cast(
                    JsonObject,
                    {
                        **_grounding(
                            source_path=source,
                            source_hash=source_hash,
                            metadata=metadata,
                            indexed_at=indexed_at,
                            authority="model",
                            lifecycle_status=status.group(1),
                        ),
                        "component_id": component_id,
                        "owner": owner,
                        "declared_code_roots": list(component.declared_code_roots),
                        "spec_section_hashes": json.dumps(component.section_hashes, sort_keys=True),
                        "related_component_ids": list(related_ids),
                        "spec_path": source,
                    },
                ),
                (component_key,),
            ),
            f"{authority_key}:fact": DataRecord(
                f"{authority_key}:fact",
                "twin.SpecDocumentFact",
                cast(
                    JsonObject,
                    {
                        **_grounding(
                            source_path=source,
                            source_hash=source_hash,
                            metadata=metadata,
                            indexed_at=indexed_at,
                            authority="model",
                            lifecycle_status=status.group(1),
                        ),
                        "title": str(package.get("source", path.name)),
                        "frontmatter_id": component_id,
                        "frontmatter_status": status.group(1),
                        "section_titles": list(element_kinds),
                    },
                ),
                (authority_key,),
            ),
        }
        links: dict[str, LinkRecord] = {}
        _add_link(links, "twin.HasSpec", component_key, authority_key)
        for related_id in related_ids:
            _add_link(links, "twin.DependsOn", component_key, f"component:{related_id}")
        for stable_id, _requirement_name in sorted(stable_requirements.items()):
            if not stable_id.startswith("invariant."):
                continue
            invariant_key = f"{component_key}:invariant:{stable_id}"
            data_objects[invariant_key] = DataRecord(
                invariant_key,
                "twin.Invariant",
                {
                    **_grounding(
                        source_path=source,
                        source_hash=_hash_text(stable_id),
                        metadata=metadata,
                        indexed_at=indexed_at,
                        authority="model",
                        lifecycle_status=status.group(1),
                    ),
                    "invariant_name": stable_id,
                    "component_id": component_id,
                },
                (component_key,),
            )
        parsed.append(_ParsedModel(component, anchors, data_objects, links))
    return tuple(parsed), tuple(issues)


def _realization_code_roots(root: Path) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for path in sorted((root / "model").rglob("*.sysml")):
        text = path.read_text(encoding="utf-8")
        for match in _REALIZATION_RE.finditer(text):
            block = _extract_braced_block(text, match.start())
            for code_root in _CODE_ROOT_RE.findall(block):
                result.setdefault(match.group(1), set()).add(code_root)
    return result


def _model_source_digest(root: Path, sources: set[str]) -> str:
    model_root = root / "model"
    digest = hashlib.sha256()
    for source in sorted(
        sources, key=lambda item: (root / item).relative_to(model_root).as_posix()
    ):
        path = root / source
        relative = path.relative_to(model_root).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def component_subject_hashes(
    component: ComponentScan, impl: ImplementationScan | None
) -> JsonObject:
    hashes: JsonObject = {}
    provided = component.section_hashes.get("Provided contracts")
    if provided is not None:
        hashes[f"model:{component.spec_path}#public-contract"] = provided
    if impl is not None:
        hashes[f"impl:{impl.path}"] = impl.source_hash
        if impl.protocol_hash is not None:
            hashes[f"impl:{impl.path}#protocol"] = impl.protocol_hash
    return hashes


def repo_metadata(root: Path) -> RepoMetadata:
    commit = _git_output(root, "rev-parse", "--short", "HEAD") or "unknown"
    branch = _git_output(root, "branch", "--show-current") or "unknown"
    status = _git_output(root, "status", "--short")
    dirty = bool(status)
    if dirty and commit != "unknown":
        commit = f"{commit}-dirty"
    return RepoMetadata(
        repo_commit=commit,
        branch=branch,
        dirty=dirty,
        indexed_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )


def _scan_implementation_root(root: Path, path: Path) -> ImplementationScan:
    relative = _relative_path(root, path)
    test_dir = path / "tests"
    test_file_names = tuple(
        sorted(
            item.name
            for item in test_dir.glob("test_*.py")
            if item.is_file() and "__pycache__" not in item.parts
        )
    )
    protocol = path / "protocol.py"
    py_files = _tracked_files_under(root, path, suffixes=(".py",))
    return ImplementationScan(
        path=relative,
        source_hash=_hash_pairs(root, py_files),
        has_protocol=protocol.is_file(),
        has_implementation=(path / "implementation.py").is_file(),
        has_reference=(path / "reference.py").is_file(),
        has_tests=test_dir.is_dir(),
        protocol_hash=_file_hash(protocol) if protocol.is_file() else None,
        file_count=len(py_files),
        test_file_names=test_file_names,
    )


def _implementation_root_paths(root: Path) -> tuple[Path, ...]:
    components_dir = root / "components"
    if not components_dir.is_dir():
        return ()
    roots: list[Path] = []
    for domain in sorted(components_dir.iterdir()):
        if not domain.is_dir() or domain.name.startswith(".") or domain.name == "__pycache__":
            continue
        for candidate in sorted(domain.iterdir()):
            if (
                candidate.is_dir()
                and candidate.name != "__pycache__"
                and any(candidate.glob("*.py"))
            ):
                roots.append(candidate)
    return tuple(roots)


def _extract_braced_block(text: str, start: int) -> str:
    brace = text.find("{", start)
    if brace < 0:
        return ""
    depth = 0
    in_comment = False
    in_string = False
    escaped = False
    index = brace
    while index < len(text):
        if in_comment:
            if text.startswith("*/", index):
                in_comment = False
                index += 2
                continue
            index += 1
            continue
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif text.startswith("/*", index):
            in_comment = True
            index += 2
            continue
        elif char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
        index += 1
    return text[start:]


def _grounding(
    *,
    source_path: str,
    source_hash: str,
    metadata: RepoMetadata,
    indexed_at: str,
    authority: str,
    lifecycle_status: str,
) -> JsonObject:
    return {
        "source_path": source_path,
        "source_hash": source_hash,
        "repo_commit": metadata.repo_commit,
        "last_indexed_at": indexed_at,
        "authority": authority,
        "lifecycle_status": lifecycle_status,
    }


def _add_link(
    links: dict[str, LinkRecord], type_key: str, source_key: str, target_key: str
) -> None:
    link = LinkRecord(type_key, source_key, target_key)
    links[link.natural_key] = link


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _directory_hash(root: Path, path: Path, *, suffixes: tuple[str, ...]) -> str:
    return _hash_pairs(root, _tracked_files_under(root, path, suffixes=suffixes))


def _tracked_files_under(root: Path, path: Path, *, suffixes: tuple[str, ...]) -> tuple[Path, ...]:
    tracked = _git_tracked_files(root)
    if tracked is None:
        files = [
            item
            for item in path.rglob("*")
            if item.is_file()
            and item.suffix in suffixes
            and "__pycache__" not in item.parts
            and ".data" not in item.parts
        ]
    else:
        files = [
            root / relative
            for relative in tracked
            if (root / relative).is_relative_to(path)
            and (root / relative).suffix in suffixes
            and "__pycache__" not in (root / relative).parts
        ]
    return tuple(sorted(files, key=lambda item: _relative_path(root, item)))


def _hash_pairs(root: Path, paths: tuple[Path, ...]) -> str:
    pairs = "\n".join(f"{_relative_path(root, path)} {_file_hash(path)}" for path in paths)
    return _hash_text(pairs)


def _hash_text(text: object) -> str:
    normalized = "\n".join(line.rstrip() for line in str(text).strip().splitlines())
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"


def _git_tracked_files(root: Path) -> tuple[Path, ...] | None:
    output = _git_output(root, "ls-files")
    if output is None:
        return None
    return tuple(Path(line) for line in output.splitlines() if line)


def _git_output(root: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ("git", *args), cwd=root, check=True, capture_output=True, text=True
        )
    except OSError, subprocess.CalledProcessError:
        return None
    return result.stdout.strip()


def _relative_path(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _relative_or_path(root: Path, path: Path) -> str:
    try:
        return _relative_path(root, path)
    except ValueError:
        return str(path)
