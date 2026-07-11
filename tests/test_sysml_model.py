from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools import model_tool

ROOT = Path(__file__).resolve().parents[1]


def test_repository_model_profile_and_generated_artifacts_are_current() -> None:
    assert model_tool.check("all") == []
    assert model_tool.check_generated() == []


def test_bibliotek_model_has_all_ten_component_identities() -> None:
    assert len(model_tool._component_model_statuses()) == 10
    assert model_tool._component_model_statuses()["component.rtg.discovery"] == "draft"


def test_vellis_has_nine_bibliotek_roles_and_exact_mcp_surface() -> None:
    assert model_tool._vellis_roles() == model_tool.EXPECTED_VELLIS_ROLES
    assert len(model_tool._model_tool_names()) == 27
    assert set(model_tool._model_tool_names()) == set(model_tool._python_tool_names())
    assert model_tool._model_tool_parameters() == model_tool._python_tool_parameters()
    assert model_tool._python_tool_description_names() == set(model_tool._python_tool_names())
    assert len(set(model_tool._model_operation_ids())) == 27


def test_model_remains_shadow_until_formal_and_human_gates_pass() -> None:
    status = json.loads((ROOT / "model" / "model-status.json").read_text(encoding="utf-8"))

    assert status["phase"] == "shadow"
    assert status["authored_design"] == "model/**/*.sysml"
    assert status["frozen_migration_baseline"] == "docs/components/*.md"
    assert status["gates"]["markdown_retirement"] == "blocked"
    assert status["gates"]["external_sysml_validator"] == "pending"
    assert status["gates"]["representative_pilots"] == "implemented-pending-human-review"
    assert status["gates"]["accepted_contract_preservation"] == "implemented-pending-human-review"


def test_profile_checker_rejects_unbalanced_and_nonbaseline_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "Invalid.sysml"
    invalid.write_text("package Invalid { #component thing;", encoding="utf-8")
    profile = tmp_path / "allowed-constructs.json"
    profile.write_text(json.dumps({"forbidden_patterns": ["#component\\b"]}), encoding="utf-8")
    monkeypatch.setattr(model_tool, "MODEL_ROOT", tmp_path)

    delimiter_findings = model_tool._balanced_delimiters(invalid, invalid.read_text())
    profile_findings = model_tool._check_allowed_profile([invalid])

    assert any("unclosed" in finding.message for finding in delimiter_findings)
    assert any("outside the baseline profile" in finding.message for finding in profile_findings)


def test_native_style_rejects_realization_leaks_and_semantic_profile_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component_root = tmp_path / "bibliotek" / "components"
    component_root.mkdir(parents=True)
    model = component_root / "component.example.sysml"
    model.write_text(
        """part def Example {
        @ImplementationBinding { codeRoot = "components/example"; symbol = "Example"; }
        ref action requiredRead[0..*] : Read {
            @RequiredCapability { providerLowerBound = 1; providerUpperBound = 1; }
        }
        perform action useRead[0..*] : UseRead;
        dependency misuse from useRead to requiredRead {
            @StateAccess { kind = StateAccessKind::read; effect = "delegate"; }
        }
    }
    """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "MODEL_ROOT", tmp_path)
    monkeypatch.setattr(model_tool, "COMPONENT_MODEL_ROOT", component_root)

    findings = model_tool._check_native_modeling_style([model])

    assert any("realization bindings" in finding.message for finding in findings)
    assert any("duplicates native SysML" in finding.message for finding in findings)


def test_contract_checker_rejects_part_role_type_and_cardinality_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component_root = tmp_path / "bibliotek" / "components"
    vellis_root = tmp_path / "vellis"
    component_root.mkdir(parents=True)
    vellis_root.mkdir()
    (component_root / "consumer.sysml").write_text(
        "part def ExpectedProvider;\n"
        "part def Consumer { ref part provider[1] : ExpectedProvider; }\n",
        encoding="utf-8",
    )
    (component_root / "provider.sysml").write_text(
        "part def WrongProvider;\n",
        encoding="utf-8",
    )
    (vellis_root / "Vellis.sysml").write_text(
        """part def App {
        part consumer : Consumer;
        part provider : WrongProvider;
        part provider2 : WrongProvider;
        bind consumer.provider = provider;
        bind consumer.provider = provider2;
    }
    """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "MODEL_ROOT", tmp_path)
    monkeypatch.setattr(model_tool, "COMPONENT_MODEL_ROOT", component_root)

    findings = model_tool._check_contract_satisfaction()

    assert any("binding type mismatch" in finding.message for finding in findings)
    assert any("requires exactly one bound" in finding.message for finding in findings)


def test_native_style_rejects_hollow_calculations(tmp_path: Path) -> None:
    model = tmp_path / "Hollow.sysml"
    model.write_text(
        "calc def Hollow { in value : Integer; out result : Integer; doc /* prose only */ }",
        encoding="utf-8",
    )

    findings = model_tool._check_native_modeling_style([model])

    assert any("has no evaluable result" in finding.message for finding in findings)


def test_native_view_packages_cover_library_and_application_concerns() -> None:
    bibliotek_views = (
        ROOT / "model" / "bibliotek" / "views" / "BibliotekViews.sysml"
    ).read_text(encoding="utf-8")
    vellis_views = (ROOT / "model" / "vellis" / "views" / "VellisViews.sysml").read_text(
        encoding="utf-8"
    )

    assert "viewpoint def BibliotekComponentStructureViewpoint" in bibliotek_views
    assert "view bibliotekComponentStructure" in bibliotek_views
    assert "viewpoint def VellisCompositionViewpoint" in vellis_views
    assert "view vellisUseCases" in vellis_views


def test_generated_artifact_checker_detects_staleness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "bibliotek-components.md"
    stale.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(model_tool, "GENERATED_DOC_ROOT", tmp_path)
    monkeypatch.setattr(model_tool, "GENERATED_COMPONENT_DOC_ROOT", tmp_path / "components")
    monkeypatch.setattr(model_tool, "GENERATED_MANIFEST", tmp_path / "manifest.json")

    findings = model_tool.check_generated()

    assert findings
    assert all("missing or stale" in finding.message for finding in findings)


def test_all_python_protocol_operations_map_to_model_actions() -> None:
    assert model_tool._check_protocol_action_coverage() == []
    assert model_tool._check_protocol_action_signatures() == []


def test_public_definitions_are_not_empty_and_drift_is_explicit() -> None:
    assert model_tool._check_empty_public_definitions(model_tool._sysml_files("all")) == []
    assert model_tool._check_component_contract_completeness() == []
    assert model_tool._check_shadow_contract_parity() == []
    assert model_tool._check_implementation_drift_file() == []


def test_generated_component_views_cover_actions_state_and_invariants() -> None:
    pages = model_tool._component_pages()

    assert len(pages) == 10
    for content in pages.values():
        assert "## Provided actions" in content
        assert "## Construction actions" in content
        assert "## Owned state" in content
        assert "## Action and state effects" in content
        assert "## Invariants and behavioral obligations" in content
        assert "## Public enumerations" in content
        assert "## Verification" in content

    json_page = next(
        content for path, content in pages.items() if path.name == "component.storage.json_file.md"
    )
    assert "`OpenJsonFileStorage`" in json_page
    assert '`relativeDirectoryPath: JsonRelativePath` = `"."`' in json_page

    graph_page = next(
        content for path, content in pages.items() if path.name == "component.rtg.graph.md"
    )
    assert "| `getObject` | `GetGraphObject` |" in graph_page
    assert "`uuid[0..1]: Uuid`" in graph_page
    assert "`type: String`" in graph_page
    assert "`system: RtgSystem`" in graph_page
