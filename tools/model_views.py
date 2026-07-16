from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

try:
    from .model_layout import (
        ARCHITECTURE_REFERENCE_ROOT,
        GENERATED_ARCHITECTURE_GRAPH,
        GENERATED_FORMAL_INDEX,
        ROOT,
    )
    from .sysml_diagrams import normalize_plantuml, render_svg
    from .sysml_validator import DIAGNOSTIC, _execute_source, _kernel_session, _model_files
except ImportError:  # pragma: no cover - direct execution
    from model_layout import (  # type: ignore[no-redef]
        ARCHITECTURE_REFERENCE_ROOT,
        GENERATED_ARCHITECTURE_GRAPH,
        GENERATED_FORMAL_INDEX,
        ROOT,
    )
    from sysml_diagrams import normalize_plantuml, render_svg  # type: ignore[no-redef]
    from sysml_validator import (  # type: ignore[no-redef]
        DIAGNOSTIC,
        _execute_source,
        _kernel_session,
        _model_files,
    )

Direction = Literal["inbound", "outbound", "both"]

GENERATED_READING_NOTICE = (
    "Generated non-normative reading projection from the parser-backed SysML "
    "architecture graph; do not edit by hand."
)

NODE_KINDS = {
    "ActionDefinition",
    "ActionUsage",
    "ConcernDefinition",
    "ConcernUsage",
    "InterfaceDefinition",
    "InterfaceUsage",
    "LibraryPackage",
    "Package",
    "PartDefinition",
    "PartUsage",
    "PerformActionUsage",
    "PortDefinition",
    "PortUsage",
    "RequirementDefinition",
    "RequirementUsage",
    "StateDefinition",
    "StateUsage",
    "UseCaseDefinition",
    "UseCaseUsage",
    "VerificationCaseDefinition",
    "VerificationCaseUsage",
    "ViewDefinition",
    "ViewUsage",
}

EDGE_FIELDS: dict[str, tuple[str, str, str]] = {
    "Dependency": ("client", "supplier", "depends"),
    "NamespaceImport": ("source", "target", "imports"),
    "MembershipImport": ("source", "target", "imports"),
    "Import": ("source", "target", "imports"),
    "BindingConnectorAsUsage": ("sourceFeature", "targetFeature", "binds"),
    "AllocationUsage": ("source", "target", "allocates"),
    "SuccessionAsUsage": ("sourceFeature", "targetFeature", "succeeds"),
    "FlowUsage": ("sourceFeature", "targetFeature", "flows"),
}

COLORS = {
    "Package": "#EAF2F8",
    "PartDefinition": "#D6EAF8",
    "PartUsage": "#E8F8F5",
    "ActionDefinition": "#FCF3CF",
    "ActionUsage": "#FEF9E7",
    "PerformActionUsage": "#FEF9E7",
    "RequirementDefinition": "#FDEDEC",
    "RequirementUsage": "#FDEDEC",
    "VerificationCaseDefinition": "#F4ECF7",
    "VerificationCaseUsage": "#F4ECF7",
}

EDGE_COLORS = {
    "imports": "#5D6D7E",
    "contains": "#85929E",
    "types": "#2471A3",
    "performs": "#B9770E",
    "depends": "#884EA0",
    "binds": "#117864",
    "allocates": "#A04000",
    "satisfies": "#B03A2E",
    "verifies": "#7D3C98",
    "succeeds": "#1F618D",
    "flows": "#148F77",
}


@dataclass(frozen=True, slots=True)
class ViewPreset:
    name: str
    question: str
    target_kinds: tuple[str, ...]
    relations: tuple[str, ...]
    depth: int
    direction: Direction
    output_kind: Literal["graph", "matrix"] = "graph"
    target_required: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "question": self.question,
            "target_kinds": list(self.target_kinds),
            "parameters": {
                "depth": {"default": self.depth, "minimum": 0, "maximum": 3},
                "direction": {
                    "default": self.direction,
                    "choices": ["inbound", "outbound", "both"],
                },
                "relations": {"default": list(self.relations)},
                "detail": {"default": "normal", "choices": ["summary", "normal", "full"]},
                "layout": {"default": "auto", "choices": ["auto", "vertical", "horizontal"]},
                "format": {
                    "default": "svg" if self.output_kind == "graph" else "markdown",
                    "choices": ["svg", "puml", "json", "markdown"],
                },
                "max_nodes": {"default": 60},
            },
            "target_required": self.target_required,
            "output_kind": self.output_kind,
        }


PRESETS: dict[str, ViewPreset] = {
    preset.name: preset
    for preset in (
        ViewPreset(
            "contract",
            "What public structure and behavior does this contract expose?",
            ("PartDefinition",),
            ("contains", "types", "performs"),
            2,
            "outbound",
        ),
        ViewPreset(
            "context",
            "What surrounds this element and what does it connect to?",
            ("Package", "PartDefinition", "PartUsage"),
            ("types", "depends", "binds", "allocates", "imports"),
            1,
            "both",
        ),
        ViewPreset(
            "impact",
            "What modeled elements may be affected by changing this element?",
            tuple(),
            ("types", "performs", "depends", "binds", "allocates", "satisfies", "verifies"),
            2,
            "inbound",
        ),
        ViewPreset(
            "composition",
            "How is this application or component assembled from roles and bindings?",
            ("PartDefinition", "PartUsage"),
            ("contains", "types", "binds", "allocates"),
            3,
            "outbound",
        ),
        ViewPreset(
            "runtime-topology",
            "Which runtime occurrences, ports, and bindings form this realization?",
            ("Package", "PartDefinition", "PartUsage"),
            ("contains", "types", "binds", "allocates", "flows"),
            3,
            "outbound",
        ),
        ViewPreset(
            "operation",
            "How does this operation map to performed actions and dependencies?",
            ("ActionDefinition", "ActionUsage", "PerformActionUsage"),
            ("contains", "types", "performs", "depends", "succeeds", "flows"),
            3,
            "both",
        ),
        ViewPreset(
            "action-flow",
            "What modeled actions, transfers, and successions implement this behavior?",
            ("ActionDefinition", "ActionUsage", "PerformActionUsage"),
            ("contains", "types", "performs", "succeeds", "flows"),
            3,
            "outbound",
        ),
        ViewPreset(
            "requirements",
            "Which requirements, satisfiers, and verification cases cover this subject?",
            ("PartDefinition", "PartUsage", "RequirementDefinition", "RequirementUsage"),
            ("contains", "satisfies", "verifies", "types"),
            3,
            "both",
        ),
        ViewPreset(
            "verification-coverage",
            "Where does modeled requirement satisfaction or verification coverage exist "
            "or remain absent?",
            tuple(),
            ("satisfies", "verifies"),
            1,
            "both",
            "matrix",
            False,
        ),
        ViewPreset(
            "package-layers",
            "Are authored package dependencies directed through the intended product layers?",
            tuple(),
            ("imports",),
            1,
            "both",
            "graph",
            False,
        ),
    )
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _refs(value: Any) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    return tuple(
        item["@id"]
        for item in values
        if isinstance(item, dict) and isinstance(item.get("@id"), str)
    )


def _payloads(outputs: list[dict[str, Any]], package: str) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for output in outputs:
        values = output.get("application/json")
        if not isinstance(values, list):
            continue
        for value in values:
            payload = value.get("payload") if isinstance(value, dict) else None
            if isinstance(payload, dict):
                result.append(payload)
    if not result:
        raise RuntimeError(f"official parser returned no JSON AST for {package}")
    return result


def _authored_package(qualified_name: str, packages: set[str]) -> str | None:
    root = qualified_name.split("::", 1)[0]
    return root if root in packages else None


def _stable_id(payload: dict[str, Any], packages: set[str]) -> str | None:
    qualified_name = payload.get("qualifiedName")
    if not isinstance(qualified_name, str) or not _authored_package(qualified_name, packages):
        return None
    short_name = payload.get("shortName")
    # Stable names are frequently reused by nested verification-objective copies of a
    # requirement. Preserve the short identity for the public package member and use the
    # qualified identity for nested occurrences so graph node IDs remain deterministic.
    if isinstance(short_name, str) and short_name and qualified_name.count("::") <= 1:
        return short_name
    return qualified_name


def _owning_authored_package(
    payload: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    packages: set[str],
) -> str | None:
    current = payload
    seen: set[str] = set()
    while current:
        qualified_name = current.get("qualifiedName")
        if isinstance(qualified_name, str):
            return _authored_package(qualified_name, packages)
        next_ids: tuple[str, ...] = ()
        for field in ("owner", "owningNamespace", "owningType", "owningRelationship"):
            if ids := _refs(current.get(field)):
                next_ids = ids
                break
        if not next_ids or next_ids[0] in seen:
            return None
        seen.add(next_ids[0])
        current = by_id.get(next_ids[0], {})
    return None


def _endpoint(
    value: Any,
    by_id: dict[str, dict[str, Any]],
    packages: set[str],
    *,
    chain_root: bool = True,
) -> str | None:
    ids = _refs(value)
    if not ids:
        return None
    current = by_id.get(ids[0], {})
    seen: set[str] = set()
    while current:
        current_id = current.get("@id")
        if isinstance(current_id, str):
            if current_id in seen:
                return None
            seen.add(current_id)
        chain = _refs(current.get("chainingFeature"))
        if chain:
            selected = chain[0] if chain_root else chain[-1]
            current = by_id.get(selected, {})
            continue
        if current.get("@type") in NODE_KINDS and (stable := _stable_id(current, packages)):
            return stable
        owner_ids: tuple[str, ...] = ()
        for field in ("owner", "owningNamespace", "owningType"):
            if values := _refs(current.get(field)):
                owner_ids = values
                break
        if not owner_ids:
            return None
        current = by_id.get(owner_ids[0], {})
    return None


def _chain_label(value: Any, by_id: dict[str, dict[str, Any]]) -> str | None:
    ids = _refs(value)
    if not ids:
        return None
    current = by_id.get(ids[0], {})
    chain = _refs(current.get("chainingFeature"))
    if chain:
        current = by_id.get(chain[-1], {})
    name = current.get("name")
    return name if isinstance(name, str) and name not in {"thisThing", "sameThing"} else None


def _product(source: str) -> str:
    parts = Path(source).parts
    if "foundation" in parts:
        return "foundation"
    if "bibliotek" in parts:
        return "bibliotek"
    if "vellis" in parts:
        return "vellis"
    return "model"


def build_architecture_graph(index: dict[str, Any] | None = None) -> dict[str, Any]:
    formal = index or _read_json(GENERATED_FORMAL_INDEX)
    package_sources = formal.get("authored_packages")
    if not isinstance(package_sources, dict) or not package_sources:
        raise RuntimeError("formal parser index has no authored package map")
    packages = {str(name) for name in package_sources}
    nodes: dict[str, dict[str, Any]] = {}
    edges: set[tuple[str, str, str, str]] = set()
    short_names: dict[str, str] = {}

    def add_edge(kind: str, source: str | None, target: str | None, label: str = "") -> None:
        if source and target and source != target:
            edges.add((kind, source, target, label))

    # Package identities and their source ownership are already official-parser-backed in the
    # formal inventory. Seed them here so package-level projections remain complete even when a
    # downstream AST does not expand an otherwise unreferenced package member.
    for package, source_value in sorted(package_sources.items()):
        source = str(source_value)
        nodes[package] = {
            "id": package,
            "kind": "Package",
            "label": package,
            "package": package,
            "product": _product(source),
            "qualified_name": package,
            "source": source,
        }

    with _kernel_session() as client:
        for path in _model_files("all"):
            diagnostics, _ = _execute_source(client, path.read_text(encoding="utf-8"))
            if any(DIAGNOSTIC.search(line) for line in diagnostics):
                raise RuntimeError(
                    f"cannot project invalid model {path.relative_to(ROOT)}:\n"
                    + "\n".join(diagnostics)
                )

        # This concrete downstream realization references the application composition, its façade
        # operations, every bound Bibliotek component, and their inherited contract semantics. A
        # single AST therefore avoids repeatedly materializing the pilot's very large inherited
        # semantic trees while retaining typed parser relationships for architectural queries.
        query_roots = (
            "Bibliotek",
            "Vellis",
            "VellisRuntimePythonRealization::VellisRuntimePython",
        )
        for query_package in query_roots:
            diagnostics, outputs = _execute_source(client, f"%show --style JSON {query_package}")
            if diagnostics:
                raise RuntimeError(
                    f"official parser AST export failed for {query_package}:\n"
                    + "\n".join(diagnostics)
                )
            payloads = _payloads(outputs, query_package)
            by_id = {
                payload["@id"]: payload
                for payload in payloads
                if isinstance(payload.get("@id"), str)
            }
            local = [
                payload
                for payload in payloads
                if _owning_authored_package(payload, by_id, packages) is not None
                or (
                    payload.get("@type") in EDGE_FIELDS
                    and (
                        _endpoint(payload.get("source"), by_id, packages) is not None
                        or _endpoint(payload.get("target"), by_id, packages) is not None
                    )
                )
            ]

            for payload in local:
                if payload.get("@type") not in NODE_KINDS:
                    continue
                stable_id = _stable_id(payload, packages)
                qualified_name = payload.get("qualifiedName")
                if stable_id is None or not isinstance(qualified_name, str):
                    continue
                package = _authored_package(qualified_name, packages)
                if package is None:
                    continue
                source = str(package_sources[package])
                previous = short_names.get(stable_id)
                if previous is not None and previous != qualified_name:
                    raise RuntimeError(
                        f"architecture graph stable ID {stable_id!r} is shared by "
                        f"{previous!r} and {qualified_name!r}"
                    )
                short_names[stable_id] = qualified_name
                name = payload.get("name")
                node_kind = (
                    "Package"
                    if payload["@type"] in {"Package", "LibraryPackage"}
                    else payload["@type"]
                )
                node = {
                    "id": stable_id,
                    "kind": node_kind,
                    "label": (
                        name
                        if isinstance(name, str) and name
                        else qualified_name.rsplit("::", 1)[-1]
                    ),
                    "package": package,
                    "product": _product(source),
                    "qualified_name": qualified_name,
                    "source": source,
                }
                declared_short_name = payload.get("shortName")
                if isinstance(declared_short_name, str) and declared_short_name:
                    node["short_name"] = declared_short_name
                nodes[stable_id] = node

            for payload in local:
                stable_id = _stable_id(payload, packages)
                if payload.get("@type") in NODE_KINDS and stable_id:
                    owner = _endpoint(payload.get("owner"), by_id, packages)
                    add_edge("contains", owner, stable_id)
                    relationship = (
                        "performs" if payload.get("@type") == "PerformActionUsage" else "types"
                    )
                    for type_id in _refs(payload.get("type")):
                        target = _endpoint({"@id": type_id}, by_id, packages)
                        add_edge(relationship, stable_id, target)
                    if payload.get("@type") in {
                        "VerificationCaseDefinition",
                        "VerificationCaseUsage",
                    }:
                        for requirement_id in _refs(payload.get("verifiedRequirement")):
                            target = _endpoint({"@id": requirement_id}, by_id, packages)
                            add_edge("verifies", stable_id, target)

                payload_type = payload.get("@type")
                if payload_type in EDGE_FIELDS:
                    source_field, target_field, relation = EDGE_FIELDS[payload_type]
                    source_id = _endpoint(payload.get(source_field), by_id, packages)
                    target_id = _endpoint(payload.get(target_field), by_id, packages)
                    if source_id is None and source_field == "sourceFeature":
                        source_id = _endpoint(payload.get("source"), by_id, packages)
                    if target_id is None and target_field == "targetFeature":
                        target_id = _endpoint(payload.get("target"), by_id, packages)
                    label = ""
                    if relation == "binds":
                        label = _chain_label(payload.get(source_field), by_id) or ""
                    elif isinstance(payload.get("name"), str):
                        label = payload["name"]
                    add_edge(relation, source_id, target_id, label)
                elif payload_type == "SatisfyRequirementUsage":
                    add_edge(
                        "satisfies",
                        _endpoint(payload.get("satisfyingFeature"), by_id, packages),
                        _endpoint(payload.get("satisfiedRequirement"), by_id, packages),
                    )

    filtered_edges = [
        {"kind": kind, "source": source, "target": target, **({"label": label} if label else {})}
        for kind, source, target, label in sorted(edges)
        if source in nodes and target in nodes
    ]
    endpoint_ids = {edge["source"] for edge in filtered_edges} | {
        edge["target"] for edge in filtered_edges
    }
    missing = endpoint_ids - set(nodes)
    if missing:
        raise RuntimeError(f"architecture graph has unresolved endpoints: {sorted(missing)}")
    return {
        "schema_version": 1,
        "source_digest": formal.get("source_digest"),
        "validator": formal.get("validator"),
        "nodes": [nodes[node_id] for node_id in sorted(nodes)],
        "edges": filtered_edges,
    }


def validate_architecture_graph(graph: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return ["architecture graph must contain node and edge arrays"]
    ids = [node.get("id") for node in nodes if isinstance(node, dict)]
    if len(ids) != len(set(ids)):
        findings.append("architecture graph node IDs are not unique")
    id_set = set(ids)
    for edge in edges:
        if not isinstance(edge, dict):
            findings.append("architecture graph contains a non-object edge")
            continue
        if edge.get("source") not in id_set or edge.get("target") not in id_set:
            findings.append(f"architecture graph edge has an unresolved endpoint: {edge}")
    if graph.get("source_digest") != _read_json(GENERATED_FORMAL_INDEX).get("source_digest"):
        findings.append("architecture graph source digest does not match the formal parser index")
    return findings


def _node_map(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in graph["nodes"]}


def resolve_target(graph: dict[str, Any], target: str) -> str:
    nodes = _node_map(graph)
    if target in nodes:
        return target
    exact = [node_id for node_id, node in nodes.items() if node["qualified_name"] == target]
    if len(exact) == 1:
        return exact[0]
    candidates = [
        node_id
        for node_id, node in nodes.items()
        if node["label"] == target
        or node.get("short_name") == target
        or node["qualified_name"].endswith(f"::{target}")
    ]
    public_candidates = [
        node_id for node_id in candidates if nodes[node_id]["qualified_name"].count("::") <= 1
    ]
    if len(public_candidates) == 1:
        return public_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise ValueError(f"ambiguous target {target!r}; choose one of {sorted(candidates)}")
    raise ValueError(f"unknown model target {target!r}; run `model-view-targets` to list choices")


def select_projection(
    graph: dict[str, Any],
    preset: ViewPreset,
    target: str | None,
    *,
    depth: int | None = None,
    direction: Direction | None = None,
    relations: Iterable[str] | None = None,
    max_nodes: int = 60,
) -> dict[str, Any]:
    nodes = _node_map(graph)
    selected_relations = set(relations or preset.relations)
    selected_direction = direction or preset.direction
    selected_depth = preset.depth if depth is None else depth
    if not 0 <= selected_depth <= 3:
        raise ValueError("depth must be between 0 and 3")
    if max_nodes < 1:
        raise ValueError("max-nodes must be positive")

    if preset.name == "package-layers":
        selected_nodes = {node_id for node_id, node in nodes.items() if node["kind"] == "Package"}
        selected_edges = [
            edge
            for edge in graph["edges"]
            if edge["kind"] == "imports"
            and edge["source"] in selected_nodes
            and edge["target"] in selected_nodes
        ]
    elif preset.name == "verification-coverage" and target is None:
        selected_edges = [edge for edge in graph["edges"] if edge["kind"] in selected_relations]
        selected_nodes = {
            endpoint for edge in selected_edges for endpoint in (edge["source"], edge["target"])
        }
    else:
        if target is None:
            raise ValueError(f"preset {preset.name!r} requires a target")
        root = resolve_target(graph, target)
        if preset.target_kinds and nodes[root]["kind"] not in preset.target_kinds:
            raise ValueError(
                f"preset {preset.name!r} does not support {nodes[root]['kind']} targets; "
                f"expected one of {list(preset.target_kinds)}"
            )
        selected_nodes = {root}
        selected_edges: list[dict[str, Any]] = []
        frontier = {root}
        for _ in range(selected_depth):
            next_frontier: set[str] = set()
            for edge in graph["edges"]:
                if edge["kind"] not in selected_relations:
                    continue
                use = False
                other: str | None = None
                if selected_direction in {"outbound", "both"} and edge["source"] in frontier:
                    use = True
                    other = edge["target"]
                if selected_direction in {"inbound", "both"} and edge["target"] in frontier:
                    use = True
                    other = edge["source"]
                if use:
                    selected_edges.append(edge)
                    if other is not None and other not in selected_nodes:
                        next_frontier.add(other)
            selected_nodes.update(next_frontier)
            if len(selected_nodes) > max_nodes:
                raise ValueError(
                    f"projection selected {len(selected_nodes)} nodes, exceeding max-nodes "
                    f"{max_nodes}; reduce depth or relations"
                )
            frontier = next_frontier
            if not frontier:
                break
        selected_edges = [
            edge
            for edge in selected_edges
            if edge["source"] in selected_nodes and edge["target"] in selected_nodes
        ]

    if len(selected_nodes) > max_nodes and preset.name != "verification-coverage":
        raise ValueError(
            f"projection selected {len(selected_nodes)} nodes, exceeding max-nodes {max_nodes}"
        )
    edge_keys: set[tuple[str, str, str, str]] = set()
    unique_edges: list[dict[str, Any]] = []
    for edge in selected_edges:
        key = (edge["kind"], edge["source"], edge["target"], edge.get("label", ""))
        if key not in edge_keys:
            edge_keys.add(key)
            unique_edges.append(edge)
    return {
        "preset": preset.name,
        "target": resolve_target(graph, target) if target is not None else None,
        "nodes": [nodes[node_id] for node_id in sorted(selected_nodes)],
        "edges": sorted(
            unique_edges,
            key=lambda edge: (
                edge["kind"],
                edge["source"],
                edge["target"],
                edge.get("label", ""),
            ),
        ),
        "parameters": {
            "depth": selected_depth,
            "direction": selected_direction,
            "relations": sorted(selected_relations),
            "max_nodes": max_nodes,
        },
    }


def _alias(node_id: str) -> str:
    return "n_" + hashlib.sha256(node_id.encode()).hexdigest()[:12]


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def projection_plantuml(
    projection: dict[str, Any],
    *,
    title: str,
    detail: str = "normal",
    layout: str = "auto",
) -> bytes:
    if detail not in {"summary", "normal", "full"}:
        raise ValueError("detail must be summary, normal, or full")
    if layout not in {"auto", "vertical", "horizontal"}:
        raise ValueError("layout must be auto, vertical, or horizontal")
    nodes = projection["nodes"]
    if not nodes:
        raise ValueError("projection contains no nodes")
    lines = [
        "@startuml",
        "skinparam backgroundColor #FFFFFF",
        "skinparam defaultFontName Helvetica",
        "skinparam defaultFontSize 13",
        "skinparam shadowing false",
        "skinparam roundCorner 12",
        "skinparam linetype ortho",
        "skinparam ArrowThickness 1.2",
        "skinparam ArrowFontSize 11",
        "skinparam rectangleBorderThickness 1",
        "skinparam nodesep 35",
        "skinparam ranksep 45",
        f"title {_escape(title)}",
    ]
    if layout == "horizontal" or (layout == "auto" and len(nodes) > 10):
        lines.append("left to right direction")
    else:
        lines.append("top to bottom direction")
    for node in nodes:
        label_parts = [node["label"]]
        if detail != "summary":
            label_parts.append(f"«{node['kind']}»")
        if detail == "full" or (detail == "normal" and node["id"] != node["qualified_name"]):
            label_parts.append(node["id"])
        label = "\\n".join(_escape(part) for part in label_parts)
        color = COLORS.get(node["kind"], "#F8F9F9")
        lines.append(f'rectangle "{label}" as {_alias(node["id"])} {color}')
    for edge in projection["edges"]:
        color = EDGE_COLORS.get(edge["kind"], "#566573")
        label = edge.get("label")
        if not label and projection.get("show_relation_labels", True):
            label = edge["kind"]
        line = f"{_alias(edge['source'])} -[#{color.removeprefix('#')}]-> {_alias(edge['target'])}"
        if label:
            line += f" : {_escape(label)}"
        lines.append(line)
    lines.append("@enduml")
    return normalize_plantuml("\n".join(lines))


def projection_markdown(projection: dict[str, Any], *, title: str) -> bytes:
    nodes = {node["id"]: node for node in projection["nodes"]}
    lines = [
        f"# {title}",
        "",
        GENERATED_READING_NOTICE,
        "",
        "| Source | Relationship | Target |",
        "|---|---|---|",
    ]
    for edge in projection["edges"]:
        source = nodes[edge["source"]]
        target = nodes[edge["target"]]
        relationship = edge["kind"]
        if edge.get("label"):
            relationship += f" ({edge['label']})"
        lines.append(f"| `{source['id']}` | `{relationship}` | `{target['id']}` |")
    if not projection["edges"]:
        lines.append("| — | — | No modeled relationships in this projection. |")
    return ("\n".join(lines) + "\n").encode()


def _projection_manifest(
    graph: dict[str, Any], projection: dict[str, Any], *, title: str, formats: list[str]
) -> bytes:
    value = {
        "schema_version": 1,
        "source_digest": graph["source_digest"],
        "title": title,
        "request": {
            "preset": projection["preset"],
            "target": projection["target"],
            "renderer": projection.get("renderer", "derived-plantuml"),
            **projection["parameters"],
        },
        "result": {
            "node_count": len(projection["nodes"]),
            "edge_count": len(projection["edges"]),
            "node_ids": [node["id"] for node in projection["nodes"]],
            "formats": formats,
            "omissions": [],
            "truncated": False,
        },
    }
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def render_projection_artifacts(
    graph: dict[str, Any],
    projection: dict[str, Any],
    *,
    title: str,
    output_format: str,
    detail: str = "normal",
    layout: str = "auto",
) -> dict[Path, bytes]:
    if output_format not in {"svg", "puml", "json", "markdown"}:
        raise ValueError("format must be svg, puml, json, or markdown")
    artifacts: dict[Path, bytes] = {}
    formats: list[str] = []
    if output_format in {"svg", "puml"}:
        plantuml = projection_plantuml(projection, title=title, detail=detail, layout=layout)
        artifacts[Path("view.puml")] = plantuml
        formats.append("puml")
        if output_format == "svg":
            artifacts[Path("view.svg")] = render_svg(plantuml)
            formats.append("svg")
    elif output_format == "json":
        artifacts[Path("view.json")] = (
            json.dumps(projection, indent=2, sort_keys=True) + "\n"
        ).encode()
        formats.append("json")
    else:
        artifacts[Path("view.md")] = projection_markdown(projection, title=title)
        formats.append("markdown")
    artifacts[Path("manifest.json")] = _projection_manifest(
        graph, projection, title=title, formats=formats
    )
    return artifacts


def render_native_projection(qualified_name: str, *, rendering: str, contract_style: bool) -> bytes:
    if rendering not in {"asTreeDiagram", "asInterconnectionDiagram"}:
        raise ValueError(f"unsupported transient SysML rendering: {rendering}")
    package = "TransientArchitectureProjection"
    source = "\n".join(
        [
            f"package {package} {{",
            "    private import Views::*;",
            "    view requestedView {",
            f"        expose {qualified_name};",
            f"        render {rendering};",
            "    }",
            "}",
        ]
    )
    with _kernel_session() as client:
        for path in _model_files("all"):
            diagnostics, _ = _execute_source(client, path.read_text(encoding="utf-8"))
            if any(DIAGNOSTIC.search(line) for line in diagnostics):
                raise RuntimeError(
                    f"cannot render an on-demand view from invalid model "
                    f"{path.relative_to(ROOT)}:\n" + "\n".join(diagnostics)
                )
        diagnostics, _ = _execute_source(client, source)
        if diagnostics:
            raise RuntimeError(
                "official pilot rejected the transient SysML view:\n" + "\n".join(diagnostics)
            )
        styles = "--style PUMLCODE --style HIDEMETADATA"
        if contract_style:
            styles += " --style COMPMOST --style STDCOLOR"
        diagnostics, outputs = _execute_source(client, f"%view {styles} {package}::requestedView")
        if diagnostics:
            raise RuntimeError(
                "official pilot failed to render the transient SysML view:\n"
                + "\n".join(diagnostics)
            )
        output = next(
            (value for item in outputs if isinstance((value := item.get("text/plain")), str)),
            None,
        )
        if output is None:
            raise RuntimeError("official pilot returned no PlantUML for the transient SysML view")
        return normalize_plantuml(output)


def _write_artifacts(root: Path, artifacts: dict[Path, bytes]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vellis-model-views-", dir=root.parent) as temporary:
        staging = Path(temporary)
        for relative, content in artifacts.items():
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
        expected = set(artifacts)
        for relative in sorted(expected):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, destination)
        for existing in sorted(path for path in root.rglob("*") if path.is_file()):
            if existing.relative_to(root) not in expected:
                existing.unlink()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", dir=path.parent, delete=False
    ) as temporary:
        temporary.write(content)
        staged = Path(temporary.name)
    os.replace(staged, path)


def _artifact_findings(root: Path, artifacts: dict[Path, bytes]) -> list[str]:
    findings: list[str] = []
    expected = set(artifacts)
    existing = (
        {path.relative_to(root) for path in root.rglob("*") if path.is_file()}
        if root.exists()
        else set()
    )
    for relative, content in artifacts.items():
        path = root / relative
        if not path.exists():
            findings.append(f"missing architecture artifact: {path.relative_to(ROOT)}")
        elif path.read_bytes() != content:
            findings.append(f"stale architecture artifact: {path.relative_to(ROOT)}")
    for relative in sorted(existing - expected):
        findings.append(f"extra architecture artifact: {(root / relative).relative_to(ROOT)}")
    return findings


def _component_projection(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = _node_map(graph)
    component_ids = {node_id for node_id in nodes if node_id.startswith("component.")}
    owner: dict[str, str] = {
        edge["target"]: edge["source"] for edge in graph["edges"] if edge["kind"] == "contains"
    }

    def component_ancestor(node_id: str) -> str | None:
        seen: set[str] = set()
        while node_id not in seen:
            seen.add(node_id)
            if node_id in component_ids:
                return node_id
            if node_id not in owner:
                return None
            node_id = owner[node_id]
        return None

    projected_edges: dict[tuple[str, str], set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        if edge["kind"] not in {"types", "depends", "binds", "allocates"}:
            continue
        source = component_ancestor(edge["source"])
        target = component_ancestor(edge["target"])
        if source and target and source != target:
            label = edge.get("label")
            if not label and edge["kind"] == "types":
                label = nodes[edge["source"]]["label"]
            projected_edges[(source, target)].add(label or edge["kind"])
    return {
        "preset": "context",
        "target": None,
        "nodes": [nodes[node_id] for node_id in sorted(component_ids)],
        "edges": [
            {
                "kind": "depends",
                "source": source,
                "target": target,
                "label": ", ".join(sorted(labels)),
            }
            for (source, target), labels in sorted(projected_edges.items())
        ],
        "parameters": {
            "depth": 1,
            "direction": "both",
            "relations": ["types", "depends", "binds", "allocates"],
            "max_nodes": 60,
        },
        "show_relation_labels": True,
    }


def _coverage_projection(graph: dict[str, Any]) -> dict[str, Any]:
    return select_projection(
        graph,
        PRESETS["verification-coverage"],
        None,
        max_nodes=max(1, len(graph["nodes"])),
    )


def _filter_projection_kinds(projection: dict[str, Any], allowed_kinds: set[str]) -> dict[str, Any]:
    kept = {node["id"] for node in projection["nodes"] if node["kind"] in allowed_kinds}
    result = dict(projection)
    result["nodes"] = [node for node in projection["nodes"] if node["id"] in kept]
    result["edges"] = [
        edge for edge in projection["edges"] if edge["source"] in kept and edge["target"] in kept
    ]
    return result


def _direct_composition_projection(
    graph: dict[str, Any], target: str, *, include_ports: bool = False
) -> dict[str, Any]:
    nodes = _node_map(graph)
    root = resolve_target(graph, target)
    allowed = {"PartUsage"}
    if include_ports:
        allowed.add("PortUsage")
    direct_edges = [
        edge
        for edge in graph["edges"]
        if edge["kind"] == "contains"
        and edge["source"] == root
        and nodes[edge["target"]]["kind"] in allowed
    ]
    occurrences = {edge["target"] for edge in direct_edges}
    typing_edges = [
        edge for edge in graph["edges"] if edge["kind"] == "types" and edge["source"] in occurrences
    ]
    type_nodes = {edge["target"] for edge in typing_edges}
    binding_edges = [
        edge
        for edge in graph["edges"]
        if edge["kind"] in {"binds", "allocates", "flows"}
        and edge["source"] in occurrences
        and edge["target"] in occurrences
    ]
    selected = {root} | occurrences | type_nodes
    return {
        "preset": "runtime-topology" if include_ports else "composition",
        "target": root,
        "nodes": [nodes[node_id] for node_id in sorted(selected)],
        "edges": sorted(
            direct_edges + typing_edges + binding_edges,
            key=lambda edge: (edge["kind"], edge["source"], edge["target"], edge.get("label", "")),
        ),
        "parameters": {
            "depth": 1,
            "direction": "outbound",
            "relations": ["contains", "types", "binds", "allocates", "flows"],
            "max_nodes": 60,
        },
    }


def _collapsed_composition_projection(
    graph: dict[str, Any],
    target: str,
    *,
    include_ports: bool = False,
    connected_only: bool = False,
) -> dict[str, Any]:
    direct = _direct_composition_projection(graph, target, include_ports=include_ports)
    nodes = {node["id"]: node for node in direct["nodes"]}
    occurrences = {
        node_id: node
        for node_id, node in nodes.items()
        if node["kind"] in {"PartUsage", "PortUsage"}
    }
    types = {
        edge["source"]: nodes[edge["target"]]
        for edge in direct["edges"]
        if edge["kind"] == "types" and edge["source"] in occurrences and edge["target"] in nodes
    }
    collapsed_nodes: list[dict[str, Any]] = []
    for node_id, occurrence in sorted(occurrences.items()):
        node = dict(occurrence)
        if target_type := types.get(node_id):
            node["label"] = f"{occurrence['label']}\n«{target_type['label']}»"
        collapsed_nodes.append(node)
    occurrence_ids = set(occurrences)
    collapsed_edges = [
        edge
        for edge in direct["edges"]
        if edge["kind"] in {"binds", "allocates", "flows"}
        and edge["source"] in occurrence_ids
        and edge["target"] in occurrence_ids
    ]
    if connected_only:
        connected = {
            endpoint for edge in collapsed_edges for endpoint in (edge["source"], edge["target"])
        }
        collapsed_nodes = [node for node in collapsed_nodes if node["id"] in connected]
    return {
        "preset": direct["preset"],
        "target": direct["target"],
        "nodes": collapsed_nodes,
        "edges": collapsed_edges,
        "parameters": direct["parameters"],
        "show_relation_labels": True,
    }


def _runtime_adapter_projection(graph: dict[str, Any], target: str) -> dict[str, Any]:
    detailed = _collapsed_composition_projection(
        graph, target, include_ports=True, connected_only=True
    )
    runtime = next(node for node in detailed["nodes"] if node["label"].startswith("runtime\n"))
    roles = {
        node["label"].split("\n", 1)[0]: node
        for node in detailed["nodes"]
        if node["id"] != runtime["id"]
    }
    groups = (
        ("interface", "Interface adapters", ("facadeAdapter", "gatewayAdapter")),
        (
            "rtg",
            "RTG component adapters",
            (
                "constraintsAdapter",
                "controllerAdapter",
                "graphAdapter",
                "migrationAdapter",
                "queryAdapter",
                "schemaAdapter",
                "validationAdapter",
            ),
        ),
        ("storage", "Storage adapters", ("jsonStorageAdapter",)),
        ("services", "Application service adapters", ("installerAdapter", "runnerAdapter")),
    )
    grouped_nodes: list[dict[str, Any]] = [runtime]
    grouped_edges: list[dict[str, Any]] = []
    for group_id, heading, members in groups:
        present = tuple(member for member in members if member in roles)
        if not present:
            continue
        node_id = f"runtime-adapter-group.{group_id}"
        grouped_nodes.append(
            {
                "id": node_id,
                "kind": "PartUsage",
                "label": f"{heading} ({len(present)})\n" + "\n".join(present),
                "package": roles[present[0]]["package"],
                "product": roles[present[0]]["product"],
                "qualified_name": node_id,
                "source": roles[present[0]]["source"],
            }
        )
        grouped_edges.append(
            {
                "kind": "binds",
                "source": node_id,
                "target": runtime["id"],
                "label": "runtime",
            }
        )
    return {
        "preset": "runtime-topology",
        "target": target,
        "nodes": grouped_nodes,
        "edges": grouped_edges,
        "parameters": detailed["parameters"],
        "show_relation_labels": True,
    }


def _product_layer_projection(graph: dict[str, Any]) -> dict[str, Any]:
    authored_products = ("foundation", "bibliotek", "vellis")
    package_counts = {
        product: sum(
            1 for node in graph["nodes"] if node["kind"] == "Package" and node["product"] == product
        )
        for product in authored_products
    }
    product_nodes = [
        {
            "id": f"product.{product}",
            "kind": "Package",
            "label": f"{product.title()}\n{package_counts[product]} authored packages",
            "package": product,
            "product": product,
            "qualified_name": f"product.{product}",
            "source": "model",
        }
        for product in authored_products
    ]
    nodes = _node_map(graph)
    directions = {
        (nodes[edge["source"]]["product"], nodes[edge["target"]]["product"])
        for edge in graph["edges"]
        if edge["kind"] == "imports"
        and nodes[edge["source"]]["product"] in authored_products
        and nodes[edge["target"]]["product"] in authored_products
        and nodes[edge["source"]]["product"] != nodes[edge["target"]]["product"]
    }
    return {
        "preset": "package-layers",
        "target": None,
        "nodes": product_nodes,
        "edges": [
            {
                "kind": "imports",
                "source": f"product.{source}",
                "target": f"product.{target}",
            }
            for source, target in sorted(directions)
        ],
        "parameters": {
            "depth": 1,
            "direction": "both",
            "relations": ["imports"],
            "max_nodes": 3,
        },
        "show_relation_labels": False,
    }


def _operation_ownership_markdown(graph: dict[str, Any]) -> bytes:
    nodes = _node_map(graph)
    operations = [node for node in graph["nodes"] if node["id"].startswith("operation.vellis.")]
    typed_by_target: dict[str, list[str]] = defaultdict(list)
    children: dict[str, list[str]] = defaultdict(list)
    typed_targets: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for edge in graph["edges"]:
        if edge["kind"] == "contains":
            children[edge["source"]].append(edge["target"])
        if edge["kind"] in {"types", "performs"}:
            typed_by_target[edge["target"]].append(edge["source"])
        if edge["kind"] in {"types", "performs"}:
            typed_targets[edge["source"]].append((edge["kind"], edge["target"]))
    lines = [
        "# Vellis operation ownership",
        "",
        GENERATED_READING_NOTICE,
        "",
        "| Operation | Modeled provider or performed action | Relationship |",
        "|---|---|---|",
    ]
    for operation in sorted(operations, key=lambda item: item["id"]):
        operation_usages = typed_by_target.get(operation["id"], [])
        frontier = list(operation_usages)
        descendants: set[str] = set()
        for _ in range(3):
            next_frontier: list[str] = []
            for source in frontier:
                for child in children.get(source, []):
                    if child not in descendants:
                        descendants.add(child)
                        next_frontier.append(child)
            frontier = next_frontier
        providers = sorted(
            {
                (relation, target)
                for descendant in descendants
                for relation, target in typed_targets.get(descendant, [])
                if target != operation["id"]
                and nodes[target]["kind"] in {"ActionDefinition", "ActionUsage"}
            }
        )
        if not providers:
            lines.append(f"| `{operation['id']}` | — | No direct provider projection |")
        for relation, target in providers:
            lines.append(f"| `{operation['id']}` | `{nodes[target]['id']}` | `{relation}` |")
    return ("\n".join(lines) + "\n").encode()


def _coverage_summary_markdown(graph: dict[str, Any]) -> bytes:
    requirement_nodes = {
        node["id"]: node
        for node in graph["nodes"]
        if node["kind"] in {"RequirementDefinition", "RequirementUsage"}
    }
    covered: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        if edge["kind"] in {"satisfies", "verifies"} and edge["target"] in requirement_nodes:
            covered[edge["target"]].add(edge["kind"])
    groups: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"requirements": set(), "satisfied": set(), "verified": set()}
    )
    for node_id, node in requirement_nodes.items():
        source = node["source"]
        identity = node.get("short_name") or node_id
        groups[source]["requirements"].add(identity)
        if "satisfies" in covered.get(node_id, set()):
            groups[source]["satisfied"].add(identity)
        if "verifies" in covered.get(node_id, set()):
            groups[source]["verified"].add(identity)
    lines = [
        "# Requirement and verification coverage",
        "",
        GENERATED_READING_NOTICE,
        "",
        "Counts are grouped by authored source and deduplicate nested copies by stable short name.",
        "",
        "| Model source | Requirements | Satisfied | Verified | Verification gaps |",
        "|---|---:|---:|---:|---:|",
    ]
    for source, values in sorted(groups.items()):
        total = len(values["requirements"])
        satisfied = len(values["satisfied"])
        verified = len(values["verified"])
        lines.append(
            f"| `{source}` | {total} | {satisfied} | {verified} | {max(0, total - verified)} |"
        )
    if not groups:
        lines.append("| — | 0 | 0 | 0 | 0 |")
    return ("\n".join(lines) + "\n").encode()


def _state_transfer_boundary_markdown(graph: dict[str, Any]) -> bytes:
    """Project modeled state-transfer permissions and their traceability."""
    coverage: dict[str, set[str]] = defaultdict(set)
    requirement_nodes = {
        node["id"]: node
        for node in graph["nodes"]
        if node["kind"] == "RequirementUsage"
        and any(
            token in f"{node.get('short_name', '')} {node.get('label', '')}".lower()
            for token in (
                "snapshot",
                "state_transfer",
                "complete_state",
                "routine_work",
                "projection",
            )
        )
    }
    for edge in graph["edges"]:
        target = edge.get("target")
        if target in requirement_nodes and edge["kind"] in {"satisfies", "verifies"}:
            coverage[requirement_nodes[target]["source"]].add(edge["kind"])

    rows: list[tuple[str, str, str, str, str, str]] = []
    for path in sorted((ROOT / "components").glob("**/resources/runtime_binding.json")):
        resource = _read_json(path)
        component_id = str(resource["component_contract_id"])
        model_source = f"model/bibliotek/components/{component_id}.sysml"
        component_coverage = coverage.get(model_source, set())
        for action in resource["actions"]:
            dispositions = {
                key.removesuffix("_payload_disposition"): action.get(key)
                for key in (
                    "request_payload_disposition",
                    "result_payload_disposition",
                    "effect_payload_disposition",
                )
                if action.get(key) == "state_transfer"
            }
            method = str(action["method_name"])
            if not dispositions and method not in {"apply_batch", "validate_batch"}:
                continue
            rows.append(
                (
                    component_id,
                    str(action["action_id"]),
                    ", ".join(sorted(dispositions)) or "none",
                    "yes" if dispositions else "no",
                    "yes" if "satisfies" in component_coverage else "missing",
                    "yes" if "verifies" in component_coverage else "missing",
                )
            )
    lines = [
        "# State-transfer boundary matrix",
        "",
        GENERATED_READING_NOTICE,
        "",
        "Only rows marked `yes` may carry complete component state. Batch and validation rows are",
        "included as explicit negative boundaries. Traceability columns summarize matching modeled",
        "state-transfer or delta-scaling requirements in the owning component source.",
        "",
        "| Component | Action | State-transfer positions | Complete state allowed | "
        "Satisfies | Verifies |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| `{component}` | `{action}` | {positions} | {allowed} | {satisfies} | {verifies} |"
        for component, action, positions, allowed, satisfies, verifies in rows
    )
    if not rows:
        lines.append("| — | — | — | no | missing | missing |")
    return ("\n".join(lines) + "\n").encode()


def dashboard_artifacts(graph: dict[str, Any]) -> dict[Path, bytes]:
    artifacts: dict[Path, bytes] = {}
    entries: list[tuple[str, str, str]] = []

    def add_graph(name: str, title: str, projection: dict[str, Any], layout: str = "auto") -> None:
        plantuml = projection_plantuml(projection, title=title, detail="summary", layout=layout)
        artifacts[Path(f"{name}.puml")] = plantuml
        artifacts[Path(f"{name}.svg")] = render_svg(plantuml)
        entries.append((title, f"{name}.svg", f"{name}.puml"))

    add_graph(
        "package-layers",
        "Model product and package layers",
        _product_layer_projection(graph),
        "vertical",
    )
    add_graph(
        "bibliotek-component-context",
        "Bibliotek component dependency context",
        _component_projection(graph),
        "horizontal",
    )
    add_graph(
        "vellis-logical-composition",
        "Vellis logical composition",
        _collapsed_composition_projection(graph, "application.vellis"),
        "vertical",
    )
    runtime_target = "VellisRuntimePythonRealization::VellisRuntimePython"
    add_graph(
        "vellis-runtime-topology",
        "Vellis runtime topology",
        _runtime_adapter_projection(graph, runtime_target),
        "vertical",
    )
    artifacts[Path("operation-ownership.md")] = _operation_ownership_markdown(graph)
    artifacts[Path("verification-coverage.md")] = _coverage_summary_markdown(graph)
    artifacts[Path("state-transfer-boundaries.md")] = _state_transfer_boundary_markdown(graph)
    artifacts[Path("manifest.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "source_digest": graph["source_digest"],
                "artifacts": sorted(str(path) for path in artifacts),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    index = [
        "# Architecture projections",
        "",
        GENERATED_READING_NOTICE,
        "",
        "These stable projections answer common architecture-review questions. On-demand views are",
        "generated under `build/model-views/` with `just model-view`.",
        "",
        "## Graphical views",
        "",
        "| View | SVG | PlantUML |",
        "|---|---|---|",
    ]
    index.extend(
        f"| {title} | [diagram]({svg}) | [source]({puml}) |" for title, svg, puml in entries
    )
    index.extend(
        [
            "",
            "## Dense relationship views",
            "",
            "- [Vellis operation ownership](operation-ownership.md)",
            "- [Requirement and verification coverage](verification-coverage.md)",
            "- [State-transfer boundary matrix](state-transfer-boundaries.md)",
            "",
            f"Model source digest: `{graph['source_digest']}`.",
            "",
        ]
    )
    artifacts[Path("index.md")] = "\n".join(index).encode()
    return artifacts


def render_architecture() -> tuple[dict[str, Any], dict[Path, bytes]]:
    graph = build_architecture_graph()
    findings = validate_architecture_graph(graph)
    if findings:
        raise RuntimeError("\n".join(findings))
    # Complete every parser query and SVG render before replacing committed output.
    artifacts = dashboard_artifacts(graph)
    _atomic_write(
        GENERATED_ARCHITECTURE_GRAPH,
        (json.dumps(graph, indent=2, sort_keys=True) + "\n").encode(),
    )
    _write_artifacts(ARCHITECTURE_REFERENCE_ROOT, artifacts)
    return graph, artifacts


def check_architecture() -> list[str]:
    expected = build_architecture_graph()
    findings = validate_architecture_graph(expected)
    if not GENERATED_ARCHITECTURE_GRAPH.exists():
        findings.append("missing architecture graph; run just model-render")
    elif _read_json(GENERATED_ARCHITECTURE_GRAPH) != expected:
        findings.append("stale architecture graph; run just model-render")
    artifacts = dashboard_artifacts(expected)
    if dashboard_artifacts(expected) != artifacts:
        findings.append("architecture dashboard rendering is nondeterministic")
    findings.extend(_artifact_findings(ARCHITECTURE_REFERENCE_ROOT, artifacts))
    return findings


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-") or "root"


def _default_view_root(graph: dict[str, Any], preset: str, target: str | None) -> Path:
    return (
        ROOT
        / "build"
        / "model-views"
        / str(graph["source_digest"])[:12]
        / preset
        / _slug(target or "all")
    )


def render_on_demand(
    graph: dict[str, Any],
    preset: ViewPreset,
    target: str | None,
    *,
    depth: int | None,
    direction: Direction | None,
    relations: list[str] | None,
    max_nodes: int,
    output_format: str | None,
    detail: str,
    layout: str,
    output: Path | None,
) -> Path:
    projection = select_projection(
        graph,
        preset,
        target,
        depth=depth,
        direction=direction,
        relations=relations,
        max_nodes=max_nodes,
    )
    resolved = projection["target"]
    title = f"{preset.name.replace('-', ' ').title()}: {resolved or 'model'}"
    selected_format = output_format or ("markdown" if preset.output_kind == "matrix" else "svg")
    native_rendering = {
        "contract": "asTreeDiagram",
        "action-flow": "asInterconnectionDiagram",
    }.get(preset.name)
    if native_rendering and selected_format in {"svg", "puml"}:
        qualified_name = _node_map(graph)[resolved]["qualified_name"]
        plantuml = render_native_projection(
            qualified_name,
            rendering=native_rendering,
            contract_style=preset.name == "contract",
        )
        projection["renderer"] = "transient-sysml-pilot"
        formats = ["puml"]
        artifacts = {Path("view.puml"): plantuml}
        if selected_format == "svg":
            artifacts[Path("view.svg")] = render_svg(plantuml)
            formats.append("svg")
        artifacts[Path("manifest.json")] = _projection_manifest(
            graph, projection, title=title, formats=formats
        )
    else:
        artifacts = render_projection_artifacts(
            graph,
            projection,
            title=title,
            output_format=selected_format,
            detail=detail,
            layout=layout,
        )
    destination = output or _default_view_root(graph, preset.name, resolved)
    if not destination.is_absolute():
        destination = ROOT / destination
    _write_artifacts(destination, artifacts)
    return destination


def changed_model_sources(base: str) -> tuple[str, ...]:
    result = subprocess.run(  # noqa: S603
        ["git", "diff", "--name-only", base, "--", "model"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"git diff against {base!r} failed")
    return tuple(sorted(line for line in result.stdout.splitlines() if line.endswith(".sysml")))


def render_changed_review(graph: dict[str, Any], base: str) -> Path:
    changed = set(changed_model_sources(base))
    nodes = _node_map(graph)
    targets = sorted(
        node_id
        for node_id, node in nodes.items()
        if node["source"] in changed
        and (node_id.startswith("component.") or node_id.startswith("application."))
    )
    destination = ROOT / "build" / "model-review" / f"{_slug(base)}..{graph['source_digest'][:12]}"
    artifacts: dict[Path, bytes] = {}
    rows = [
        "# Model change architecture review",
        "",
        f"Base: `{base}`. Model digest: `{graph['source_digest']}`.",
        "",
        "## Changed model sources",
        "",
    ]
    rows.extend(f"- `{source}`" for source in sorted(changed))
    rows.extend(["", "## Targeted projections", ""])
    for target in targets:
        presets = ["impact"]
        if nodes[target]["kind"] == "PartDefinition":
            presets = ["contract", "impact", "requirements"]
        for preset_name in presets:
            preset = PRESETS[preset_name]
            projection = select_projection(graph, preset, target, depth=1, max_nodes=80)
            name = f"{_slug(target)}.{preset_name}"
            plantuml = projection_plantuml(
                projection,
                title=f"{preset_name.title()}: {target}",
                detail="summary",
                layout="auto",
            )
            artifacts[Path(f"{name}.puml")] = plantuml
            artifacts[Path(f"{name}.svg")] = render_svg(plantuml)
            rows.append(f"- `{target}` {preset_name}: [{name}.svg]({name}.svg)")
    if not targets:
        rows.append(
            "- No component or application stable IDs were mapped from the changed sources."
        )
    artifacts[Path("index.md")] = ("\n".join(rows) + "\n").encode()
    artifacts[Path("manifest.json")] = (
        json.dumps(
            {
                "schema_version": 1,
                "base": base,
                "source_digest": graph["source_digest"],
                "changed_sources": sorted(changed),
                "targets": targets,
                "artifacts": sorted(str(path) for path in artifacts),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode()
    _write_artifacts(destination, artifacts)
    return destination


def promotion_candidate(graph: dict[str, Any], preset: ViewPreset, target: str) -> str:
    resolved = resolve_target(graph, target)
    node = _node_map(graph)[resolved]
    product = node["product"]
    candidate_name = _slug(f"{resolved}.{preset.name}").replace("-", "_")
    rendering = (
        "asInterconnectionDiagram"
        if preset.name in {"composition", "runtime-topology", "action-flow"}
        else "asTreeDiagram"
    )
    diagram_id = f"diagram.{product}.candidate.{_slug(resolved)}.{preset.name}"
    return "\n".join(
        [
            "// Candidate only: review with sysml-view-authoring before adding to model/.",
            f"view <'{diagram_id}'> {candidate_name} {{",
            f"    expose {node['qualified_name']};",
            f"    render {rendering};",
            "}",
        ]
    )


def _load_current_graph() -> dict[str, Any]:
    if not GENERATED_ARCHITECTURE_GRAPH.exists():
        raise RuntimeError("missing architecture graph; run just model-render")
    graph = _read_json(GENERATED_ARCHITECTURE_GRAPH)
    findings = validate_architecture_graph(graph)
    if findings:
        raise RuntimeError("; ".join(findings))
    return graph


def _print_presets(as_json: bool) -> None:
    values = [PRESETS[name].as_dict() for name in sorted(PRESETS)]
    if as_json:
        print(json.dumps({"schema_version": 1, "presets": values}, indent=2, sort_keys=True))
        return
    for value in values:
        target = "target required" if value["target_required"] else "model-wide"
        print(f"{value['name']:<24} {target:<16} {value['question']}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate stable and on-demand architecture projections from textual SysML"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    presets = subparsers.add_parser("presets")
    presets.add_argument("--json", action="store_true")
    explain = subparsers.add_parser("explain")
    explain.add_argument("preset", choices=sorted(PRESETS))
    targets = subparsers.add_parser("targets")
    targets.add_argument("--kind")
    targets.add_argument("--json", action="store_true")
    architecture = subparsers.add_parser("architecture")
    architecture.add_argument("action", choices=("render", "check"))
    render = subparsers.add_parser("render")
    render.add_argument("preset", choices=sorted(PRESETS))
    render.add_argument("target", nargs="?")
    render.add_argument("--depth", type=int)
    render.add_argument("--direction", choices=("inbound", "outbound", "both"))
    render.add_argument("--relations", nargs="+")
    render.add_argument("--max-nodes", type=int, default=60)
    render.add_argument("--format", choices=("svg", "puml", "json", "markdown"))
    render.add_argument("--detail", choices=("summary", "normal", "full"), default="normal")
    render.add_argument("--layout", choices=("auto", "vertical", "horizontal"), default="auto")
    render.add_argument("--output", type=Path)
    changed = subparsers.add_parser("changed")
    changed.add_argument("--base", default="main")
    promote = subparsers.add_parser("promote")
    promote.add_argument("preset", choices=sorted(PRESETS))
    promote.add_argument("target")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        if arguments.command == "presets":
            _print_presets(arguments.json)
            return 0
        if arguments.command == "explain":
            print(json.dumps(PRESETS[arguments.preset].as_dict(), indent=2, sort_keys=True))
            return 0
        if arguments.command == "architecture":
            if arguments.action == "render":
                graph, artifacts = render_architecture()
                print(
                    f"Rendered architecture graph ({len(graph['nodes'])} nodes, "
                    f"{len(graph['edges'])} edges) and {len(artifacts)} dashboard artifacts."
                )
                return 0
            findings = check_architecture()
            for finding in findings:
                print(f"ERROR {finding}")
            if findings:
                return 1
            print("Architecture graph and stable dashboard are current.")
            return 0
        graph = _load_current_graph()
        if arguments.command == "targets":
            nodes = [
                node
                for node in graph["nodes"]
                if not arguments.kind or node["kind"] == arguments.kind
            ]
            if arguments.json:
                print(json.dumps({"targets": nodes}, indent=2, sort_keys=True))
            else:
                for node in nodes:
                    print(f"{node['id']:<64} {node['kind']:<28} {node['qualified_name']}")
            return 0
        if arguments.command == "render":
            preset = PRESETS[arguments.preset]
            if preset.target_required and not arguments.target:
                raise ValueError(f"preset {preset.name!r} requires a target")
            destination = render_on_demand(
                graph,
                preset,
                arguments.target,
                depth=arguments.depth,
                direction=arguments.direction,
                relations=arguments.relations,
                max_nodes=arguments.max_nodes,
                output_format=arguments.format,
                detail=arguments.detail,
                layout=arguments.layout,
                output=arguments.output,
            )
            print(f"Rendered {preset.name} projection to {destination.relative_to(ROOT)}.")
            return 0
        if arguments.command == "changed":
            destination = render_changed_review(graph, arguments.base)
            print(f"Rendered changed-model review bundle to {destination.relative_to(ROOT)}.")
            return 0
        if arguments.command == "promote":
            print(promotion_candidate(graph, PRESETS[arguments.preset], arguments.target))
            return 0
    except (RuntimeError, ValueError) as error:
        print(f"ERROR {error}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
