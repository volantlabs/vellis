from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tools import model_views


def _graph() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "source_digest": "digest",
        "validator": {},
        "nodes": [
            {
                "id": "component.example.consumer",
                "kind": "PartDefinition",
                "label": "Consumer",
                "package": "ConsumerPackage",
                "product": "bibliotek",
                "qualified_name": "ConsumerPackage::Consumer",
                "source": "model/bibliotek/components/consumer.sysml",
            },
            {
                "id": "ConsumerPackage::Consumer::provider",
                "kind": "PartUsage",
                "label": "provider",
                "package": "ConsumerPackage",
                "product": "bibliotek",
                "qualified_name": "ConsumerPackage::Consumer::provider",
                "source": "model/bibliotek/components/consumer.sysml",
            },
            {
                "id": "component.example.provider",
                "kind": "PartDefinition",
                "label": "Provider",
                "package": "ProviderPackage",
                "product": "bibliotek",
                "qualified_name": "ProviderPackage::Provider",
                "source": "model/bibliotek/components/provider.sysml",
            },
            {
                "id": "contract.example.provider.available",
                "kind": "RequirementUsage",
                "label": "available",
                "package": "ProviderPackage",
                "product": "bibliotek",
                "qualified_name": "ProviderPackage::available",
                "source": "model/bibliotek/components/provider.sysml",
                "short_name": "contract.example.provider.available",
            },
            {
                "id": "ProviderPackage::Verification",
                "kind": "VerificationCaseDefinition",
                "label": "Verification",
                "package": "ProviderPackage",
                "product": "bibliotek",
                "qualified_name": "ProviderPackage::Verification",
                "source": "model/bibliotek/components/provider.sysml",
            },
        ],
        "edges": [
            {
                "kind": "contains",
                "source": "component.example.consumer",
                "target": "ConsumerPackage::Consumer::provider",
            },
            {
                "kind": "types",
                "source": "ConsumerPackage::Consumer::provider",
                "target": "component.example.provider",
            },
            {
                "kind": "verifies",
                "source": "ProviderPackage::Verification",
                "target": "contract.example.provider.available",
            },
        ],
    }


def test_preset_catalog_exposes_architect_questions_and_parameter_contracts() -> None:
    expected = {
        "contract",
        "context",
        "impact",
        "composition",
        "runtime-topology",
        "operation",
        "action-flow",
        "requirements",
        "verification-coverage",
        "package-layers",
    }

    assert set(model_views.PRESETS) == expected
    for preset in model_views.PRESETS.values():
        value = preset.as_dict()
        assert value["question"].endswith("?")
        assert value["parameters"]["max_nodes"]["default"] == 60
        assert value["parameters"]["depth"]["maximum"] == 3


def test_target_resolution_accepts_stable_qualified_and_unique_display_names() -> None:
    graph = _graph()

    assert (
        model_views.resolve_target(graph, "component.example.consumer")
        == "component.example.consumer"
    )
    assert (
        model_views.resolve_target(graph, "ProviderPackage::Provider")
        == "component.example.provider"
    )
    assert model_views.resolve_target(graph, "Provider") == "component.example.provider"

    with pytest.raises(ValueError, match="unknown model target"):
        model_views.resolve_target(graph, "missing")


def test_projection_traversal_honors_direction_depth_relations_and_completeness_limit() -> None:
    graph = _graph()
    context = model_views.PRESETS["context"]

    outbound = model_views.select_projection(
        graph,
        context,
        "component.example.consumer",
        depth=2,
        direction="outbound",
        relations=["contains", "types"],
        max_nodes=3,
    )
    assert {node["id"] for node in outbound["nodes"]} == {
        "component.example.consumer",
        "ConsumerPackage::Consumer::provider",
        "component.example.provider",
    }

    with pytest.raises(ValueError, match="exceeding max-nodes"):
        model_views.select_projection(
            graph,
            context,
            "component.example.consumer",
            depth=2,
            direction="outbound",
            relations=["contains", "types"],
            max_nodes=2,
        )


def test_projection_rendering_is_normalized_styled_and_uuid_free() -> None:
    projection = model_views.select_projection(
        _graph(),
        model_views.PRESETS["context"],
        "component.example.consumer",
        depth=2,
        direction="outbound",
        relations=["contains", "types"],
    )

    plantuml = model_views.projection_plantuml(
        projection, title="Consumer context", detail="normal", layout="horizontal"
    ).decode()

    assert plantuml.startswith("@startuml\n")
    assert "left to right direction" in plantuml
    assert "component.example.consumer" in plantuml
    assert "psysml:" not in plantuml
    assert "shadowing false" in plantuml
    assert plantuml.endswith("@enduml\n")


def test_coverage_matrix_and_promotion_candidate_preserve_model_identity() -> None:
    graph = _graph()
    coverage = model_views.select_projection(
        graph,
        model_views.PRESETS["verification-coverage"],
        None,
        max_nodes=10,
    )
    markdown = model_views.projection_markdown(coverage, title="Verification coverage").decode()
    candidate = model_views.promotion_candidate(
        graph, model_views.PRESETS["composition"], "component.example.consumer"
    )

    assert "ProviderPackage::Verification" in markdown
    assert "contract.example.provider.available" in markdown
    assert "Candidate only" in candidate
    assert "expose ConsumerPackage::Consumer;" in candidate
    assert "render asInterconnectionDiagram;" in candidate


def test_architecture_graph_validation_rejects_duplicate_and_unresolved_nodes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    formal = tmp_path / "formal.json"
    formal.write_text(json.dumps({"source_digest": "digest"}), encoding="utf-8")
    monkeypatch.setattr(model_views, "GENERATED_FORMAL_INDEX", formal)
    graph = _graph()
    graph["nodes"].append(dict(graph["nodes"][0]))
    graph["edges"].append(
        {"kind": "types", "source": "missing", "target": "component.example.provider"}
    )

    findings = model_views.validate_architecture_graph(graph)

    assert any("not unique" in finding for finding in findings)
    assert any("unresolved endpoint" in finding for finding in findings)


def test_changed_source_discovery_uses_git_model_diff(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        captured.extend(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "model/bibliotek/components/provider.sysml\ndocs/readme.md\n",
            "",
        )

    monkeypatch.setattr(model_views.subprocess, "run", fake_run)

    assert model_views.changed_model_sources("origin/main") == (
        "model/bibliotek/components/provider.sysml",
    )
    assert captured == ["git", "diff", "--name-only", "origin/main", "--", "model"]


def test_committed_graph_covers_stable_architecture_catalog() -> None:
    graph = json.loads(model_views.GENERATED_ARCHITECTURE_GRAPH.read_text(encoding="utf-8"))

    assert model_views.validate_architecture_graph(graph) == []
    assert len([node for node in graph["nodes"] if node["id"].startswith("component.")]) == 13
    assert (
        len([node for node in graph["nodes"] if node["id"].startswith("operation.vellis.")]) == 27
    )
    assert {
        "contains",
        "types",
        "depends",
        "imports",
        "binds",
        "satisfies",
        "verifies",
    } <= {edge["kind"] for edge in graph["edges"]}


@pytest.mark.integration
def test_parser_backed_architecture_graph_is_byte_stable() -> None:
    first = model_views.build_architecture_graph()
    second = model_views.build_architecture_graph()

    assert first == second
    assert first == json.loads(model_views.GENERATED_ARCHITECTURE_GRAPH.read_text(encoding="utf-8"))
