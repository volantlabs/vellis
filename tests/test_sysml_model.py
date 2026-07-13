from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from tools import model_layout, model_tool, sysml_validator

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
    model_descriptions = model_tool._model_tool_descriptions()
    manifest = json.loads(model_layout.GENERATED_MANIFEST.read_text(encoding="utf-8"))
    assert model_descriptions == {tool["name"]: tool["description"] for tool in manifest["tools"]}
    assert len(set(model_tool._model_operation_ids())) == 27


def test_formal_validator_is_pinned_and_covers_every_authored_model() -> None:
    lock = json.loads(model_layout.VALIDATOR_LOCK_PATH.read_text(encoding="utf-8"))

    assert lock["provider"] == "Systems-Modeling/SysML-v2-Pilot-Implementation"
    assert lock["release"] == "2025-06"
    assert lock["language_baseline"] == {"sysml": "2.0", "kerml": "1.0"}
    assert len(lock["kernel"]["sha256"]) == 64
    assert (
        "--self-test"
        in json.loads(model_layout.LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))["validator"][
            "command"
        ]
    )
    assert (
        json.loads(model_layout.LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))["validator"][
            "external_validation"
        ]
        == "required"
    )
    assert len(sysml_validator._model_files("all")) == 22
    assert all(path.exists() for path in sysml_validator._model_files("all"))
    assert model_layout.SOFTWARE_COMPONENT_PATTERN_PATH not in sysml_validator._model_files("all")


def test_formal_validator_diagnostic_parser_captures_cell_location() -> None:
    diagnostic = "ERROR:Couldn't resolve reference to Type 'Missing'(7.sysml line : 12 column : 9)"

    match = sysml_validator.DIAGNOSTIC.search(diagnostic)

    assert match is not None
    assert match.groupdict() == {
        "level": "ERROR",
        "message": "Couldn't resolve reference to Type 'Missing'",
        "cell": "7",
        "line": "12",
        "column": "9",
    }


def test_formal_validator_inventory_and_import_order_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "A.sysml").write_text("package A { private import B::*; }", encoding="utf-8")
    (tmp_path / "B.sysml").write_text("package B {}", encoding="utf-8")
    monkeypatch.setattr(sysml_validator, "MODEL_ROOT", tmp_path)
    monkeypatch.setattr(sysml_validator, "MODEL_ORDER", ("A.sysml", "B.sysml"))

    with pytest.raises(RuntimeError, match="before imported package"):
        sysml_validator._check_inventory_and_order()

    monkeypatch.setattr(sysml_validator, "MODEL_ORDER", ("B.sysml", "A.sysml"))
    sysml_validator._check_inventory_and_order()
    (tmp_path / "Unlisted.sysml").write_text("package Unlisted {}", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unlisted"):
        sysml_validator._check_inventory_and_order()


def test_packaged_validation_rejects_stale_model_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_root = tmp_path / "model"
    package_root = tmp_path / "packages"
    model_source = model_root / "foundation" / "Foundation.sysml"
    model_source.parent.mkdir(parents=True)
    package_root.mkdir()
    model_source.write_text("library package Foundation {}", encoding="utf-8")
    archive = package_root / "foundation.kpar"
    with zipfile.ZipFile(archive, "w") as packaged:
        packaged.writestr(
            "Foundation/Foundation.sysml",
            "library package Foundation { doc /* stale */ }",
        )

    monkeypatch.setattr(sysml_validator, "MODEL_ROOT", model_root)
    monkeypatch.setattr(sysml_validator, "MODEL_PACKAGE_ROOT", package_root)
    monkeypatch.setattr(
        sysml_validator,
        "MODEL_ORDER",
        ("foundation/Foundation.sysml",),
    )
    monkeypatch.setattr(
        sysml_validator,
        "PACKAGE_ARCHIVES",
        {"foundation": archive.name},
    )

    with pytest.raises(RuntimeError, match="stale for current model sources"):
        sysml_validator._packaged_model_files("foundation", tmp_path / "extract")


def test_generated_conformance_objectives_resolve_model_requirements_and_evidence() -> None:
    data = model_tool._conformance_objectives_data()
    objectives = data["objectives"]

    assert isinstance(objectives, list)
    assert len(objectives) == sum(
        path.read_text(encoding="utf-8").count("verification def ")
        for path in model_tool._sysml_files("all")
    )
    assert all(objective["requirements"] for objective in objectives)
    assert all(objective["evidence_id"] for objective in objectives)
    assert all(
        requirement.startswith(("contract.", "invariant."))
        for objective in objectives
        for requirement in objective["requirements"]
    )


def test_official_parser_index_covers_authored_packages_and_public_definitions() -> None:
    index = json.loads(model_layout.GENERATED_FORMAL_INDEX.read_text(encoding="utf-8"))

    assert len(index["authored_packages"]) == 22
    assert "SoftwareComponentPattern" not in index["authored_packages"]
    assert set(index["packages"]) == set(index["authored_packages"])
    assert model_tool._check_formal_model_index() == []
    graph_parts = {
        element["name"]
        for element in index["packages"]["BibliotekRtgGraph"]["named_elements"]
        if element["kind"] == "PartDefinition"
    }
    assert "RtgGraph" in graph_parts


def test_profile_checker_rejects_unbalanced_and_nonbaseline_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = tmp_path / "Invalid.sysml"
    invalid.write_text("package Invalid { #component thing;", encoding="utf-8")
    profile = tmp_path / "allowed-constructs.json"
    profile.write_text(json.dumps({"forbidden_patterns": ["#component\\b"]}), encoding="utf-8")
    monkeypatch.setattr(model_tool, "MODEL_ROOT", tmp_path)
    monkeypatch.setattr(model_tool, "ALLOWED_CONSTRUCTS_PATH", profile)

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
            @StateAccess { kind = StateAccessKind::read; }
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


def test_profile_rejects_concrete_doc_only_public_values(tmp_path: Path) -> None:
    model = tmp_path / "Opaque.sysml"
    model.write_text(
        "attribute def OpaqueChoice { doc /* prose is not a value algebra */ }",
        encoding="utf-8",
    )

    findings = model_tool._check_empty_public_definitions([model])

    assert any("only documentation" in finding.message for finding in findings)


def test_connected_semantics_rejects_orphaned_calculation(tmp_path: Path) -> None:
    model = tmp_path / "Orphan.sysml"
    model.write_text(
        "calc def Orphan { in value : Integer; return result : Integer = value; }",
        encoding="utf-8",
    )

    findings = model_tool._check_connected_formal_semantics([model])

    assert any("is not connected to a contract" in finding.message for finding in findings)


def test_evidence_groups_resolve_to_concrete_test_nodes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "test_evidence.py"
    evidence.write_text(
        "MODEL_EVIDENCE = {\n"
        "    'ContractVerification': ('test_contract_behavior', 'test_contract_edge'),\n"
        "    'OtherVerification': ('test_other_behavior',),\n"
        "}\n"
        "def test_contract_behavior() -> None:\n    pass\n"
        "def test_contract_edge() -> None:\n    pass\n"
        "def test_other_behavior() -> None:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "ROOT", tmp_path)

    assert model_tool._evidence_test_nodes(
        "test_evidence.py::test_contract_behavior#ContractVerification"
    ) == ["test_evidence.py::test_contract_behavior"]
    assert model_tool._evidence_test_nodes("test_evidence.py#ContractVerification") == [
        "test_evidence.py::test_contract_behavior",
        "test_evidence.py::test_contract_edge",
    ]
    assert model_tool._evidence_test_nodes("test_evidence.py#OtherVerification") == [
        "test_evidence.py::test_other_behavior"
    ]
    assert model_tool._evidence_test_nodes("test_evidence.py#MissingVerification") == []
    assert (
        model_tool._evidence_test_nodes("test_evidence.py::missing_test#ContractVerification") == []
    )


def test_evidence_groups_reject_duplicate_missing_and_non_test_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "test_evidence.py"
    evidence.write_text(
        "MODEL_EVIDENCE = {\n"
        "    'DuplicateVerification': ('test_one', 'test_one'),\n"
        "}\n"
        "def test_one() -> None:\n    pass\n"
        "def helper() -> None:\n    pass\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "ROOT", tmp_path)

    assert model_tool._evidence_group_map(evidence) == {}
    assert model_tool._evidence_test_nodes("test_evidence.py#DuplicateVerification") == []
    assert model_tool._evidence_test_nodes("test_evidence.py::helper#ExplicitVerification") == []


def test_generated_evidence_status_reports_resolution_not_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = tmp_path / "test_evidence.py"
    evidence.write_text(
        "MODEL_EVIDENCE = {'KnownVerification': ('test_known',)}\n"
        "def test_known() -> None:\n    pass\n",
        encoding="utf-8",
    )
    model = tmp_path / "Evidence.sysml"
    model.write_text(
        '@EvidenceBinding { evidenceId = "test_evidence.py#KnownVerification"; }\n'
        '@EvidenceBinding { evidenceId = "test_evidence.py#MissingVerification"; }\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "ROOT", tmp_path)
    monkeypatch.setattr(model_tool, "_sysml_files", lambda _scope: [model])

    groups = model_tool._verification_evidence_data()["groups"]

    assert groups["test_evidence.py#KnownVerification"]["status"] == "resolved"
    assert groups["test_evidence.py#MissingVerification"]["status"] == "unresolved"
    assert all(group["status"] != "passed" for group in groups.values())


def test_model_defaults_distinguish_overridable_values_from_fixed_identities() -> None:
    query = (model_tool.COMPONENT_MODEL_ROOT / "component.rtg.query.sysml").read_text()
    ontology = (model_tool.MODEL_ROOT / "vellis" / "EverydayLifeOntology.sysml").read_text()
    mcp = (model_tool.MODEL_ROOT / "vellis" / "realizations" / "VellisMcpPython.sysml").read_text()

    assert "attribute required : Boolean default = true;" in query
    assert "attribute liveFilter : RtgQueryLiveFilter default =" in query
    assert 'attribute ontologyId : String = "ontology.vellis.everyday_life";' in ontology
    assert "attribute ok : Boolean = false;" in mcp


def test_model_audit_writes_advisory_bundle(tmp_path: Path) -> None:
    json_path, markdown_path = model_tool.model_audit("component.rtg.query", tmp_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["components"][0]["component_id"] == "component.rtg.query"
    assert payload["components"][0]["implementation_codecs"]
    assert payload["components"][0]["boundary_comparisons"]
    assert "Advisory only" in markdown_path.read_text(encoding="utf-8")


def test_model_audit_flattens_inherited_sysml_boundary_fields(tmp_path: Path) -> None:
    model = tmp_path / "component.example.sysml"
    model.write_text(
        """package Example {
        item def Base { attribute identity : String; }
        item def Child :> Base { attribute detail[0..1] : String; }
        }
        """,
        encoding="utf-8",
    )

    boundary = model_tool._audit_model_boundary(model)

    assert set(boundary["records"]["Child"]) == {"identity", "detail"}


def test_requirement_checker_rejects_documentation_only_and_incompatible_verification(
    tmp_path: Path,
) -> None:
    model = tmp_path / "Requirements.sysml"
    model.write_text(
        """part def Component;
        action def Operation;
        requirement obligation { subject operation : Operation; doc /* shall do work */ }
        verification def WrongCase {
            subject component : Component;
            objective { verify obligation; }
            @EvidenceBinding { evidenceId = "evidence#WrongCase"; implementationScope = "test"; }
        }
        """,
        encoding="utf-8",
    )

    findings = model_tool._check_requirement_and_verification_semantics([model])

    assert any("no required constraint" in finding.message for finding in findings)
    assert any("no satisfier" in finding.message for finding in findings)
    assert any("is incompatible" in finding.message for finding in findings)


def test_state_access_checker_rejects_untyped_owned_state_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component_root = tmp_path / "bibliotek" / "components"
    component_root.mkdir(parents=True)
    model = component_root / "component.example.sysml"
    model.write_text(
        """part def <'component.example'> Example {
            item records : Record;
            perform action read[0..*] : Read;
            dependency readRecords from read to records { doc /* read */ }
        }
        item def Record { attribute value : String; }
        action def Read { out value : String; }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "COMPONENT_MODEL_ROOT", component_root)

    findings = model_tool._check_state_access_semantics()

    assert any("lacks typed StateAccess" in finding.message for finding in findings)
    assert any("action read lacks typed state access" in finding.message for finding in findings)


def test_state_access_checker_rejects_missing_action_declaration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    component_root = tmp_path / "bibliotek" / "components"
    component_root.mkdir(parents=True)
    model = component_root / "component.example.sysml"
    model.write_text(
        """part def <'component.example'> Example {
            item records : Record;
            perform action read[0..*] : Read;
        }
        item def Record { attribute value : String; }
        action def Read { out value : String; }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(model_tool, "COMPONENT_MODEL_ROOT", component_root)

    findings = model_tool._check_state_access_semantics()

    assert any("action read lacks typed state access" in finding.message for finding in findings)


def test_foundation_native_semantics() -> None:
    fixture = model_layout.SOFTWARE_COMPONENT_PATTERN_PATH.read_text(encoding="utf-8")

    assert "assume constraint" in fixture
    assert "require constraint matchingResponse : MatchingResponse" in fixture
    assert "satisfy processRequestRequirement by provider.processRequest" in fixture
    assert "verification def ProcessRequestVerification" in fixture
    assert "calc def RequestIsValid" in fixture
    assert "assign successfulRequestCount" in fixture
    assert "in request redefines ProcessRequest::request" in fixture


def test_native_behavior_checker_rejects_unbound_facade_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_root = tmp_path / "model"
    component_root = model_root / "bibliotek" / "components"
    component_root.mkdir(parents=True)
    (model_root / "vellis" / "realizations").mkdir(parents=True)
    operations = model_root / "vellis" / "VellisOperations.sysml"
    operations.write_text(
        """action def Outer { in request : String; out result : String; }
        action def Inner { in request : String; out result : String; }
        part def VellisApplicationFacade {
            ref part controller : RtgController { perform rtgCall.invokeController; }
            perform action rtgCall[0..*] : Outer {
                action invokeController : Inner {
                    out result redefines Inner::result = rtgCall::result;
                }
            }
        }
        """,
        encoding="utf-8",
    )
    (component_root / "component.rtg.controller.sysml").write_text(
        "part def RtgController;", encoding="utf-8"
    )
    (model_root / "vellis" / "realizations" / "VellisMcpPython.sysml").write_text(
        "part def VellisMcpAdapter;", encoding="utf-8"
    )
    (model_root / "vellis" / "realizations" / "VellisLocalPython.sysml").write_text(
        "part :>> facade : PythonVellisFacade;", encoding="utf-8"
    )
    monkeypatch.setattr(model_tool, "MODEL_ROOT", model_root)
    monkeypatch.setattr(model_tool, "COMPONENT_MODEL_ROOT", component_root)

    findings = model_tool._check_native_behavior_realizations()

    assert any("leaves input request unbound" in finding.message for finding in findings)


def test_native_view_packages_cover_library_and_application_concerns() -> None:
    bibliotek_views = (ROOT / "model" / "bibliotek" / "views" / "BibliotekViews.sysml").read_text(
        encoding="utf-8"
    )
    vellis_views = (ROOT / "model" / "vellis" / "views" / "VellisViews.sysml").read_text(
        encoding="utf-8"
    )

    assert "viewpoint def" not in bibliotek_views
    assert "view bibliotekComponentStructure" in bibliotek_views
    assert "filter @SysML::SatisfyRequirementUsage" in bibliotek_views
    assert "viewpoint def" not in vellis_views
    assert "view vellisUseCases" in vellis_views
    assert "filter @SysML::BindingConnectorAsUsage" in vellis_views
    assert "expose VellisLocalPythonRealization::**;" in vellis_views
    assert "expose VellisMcpPythonRealization::**;" in vellis_views


def test_generated_artifact_checker_detects_staleness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stale = tmp_path / "bibliotek-index.md"
    stale.write_text("stale", encoding="utf-8")
    monkeypatch.setattr(model_tool, "BIBLIOTEK_REFERENCE_ROOT", tmp_path / "bibliotek")
    monkeypatch.setattr(model_tool, "VELLIS_REFERENCE_ROOT", tmp_path / "vellis")
    monkeypatch.setattr(model_tool, "GENERATED_COMPONENT_DOC_ROOT", tmp_path / "components")
    monkeypatch.setattr(model_tool, "GENERATED_MANIFEST", tmp_path / "manifest.json")
    monkeypatch.setattr(model_tool, "GENERATED_EVIDENCE_INDEX", tmp_path / "evidence.json")
    monkeypatch.setattr(
        model_tool, "GENERATED_CONFORMANCE_OBJECTIVES", tmp_path / "conformance.json"
    )
    monkeypatch.setattr(model_tool, "_check_formal_model_index", lambda: [])

    findings = model_tool.check_generated()

    assert findings
    assert all("missing or stale" in finding.message for finding in findings)


def test_all_python_protocol_operations_map_to_model_actions() -> None:
    assert model_tool._check_protocol_action_coverage() == []
    assert model_tool._check_protocol_action_signatures() == []


def test_public_definitions_and_component_contracts_are_complete() -> None:
    assert model_tool._check_empty_public_definitions(model_tool._sysml_files("all")) == []
    assert model_tool._check_component_contract_completeness() == []


def test_generated_component_views_cover_actions_state_and_invariants() -> None:
    pages = model_tool._component_pages()

    assert len(pages) == 10
    for content in pages.values():
        assert "## Provided actions" in content
        assert "## Construction actions" in content
        assert "## Owned state" in content
        assert "## Action and state effects" in content
        assert "## Native action behavior" in content
        assert "## Invariants and behavioral obligations" in content
        assert "## Public enumerations" in content
        assert "## Verification" in content

    json_page = next(
        content for path, content in pages.items() if path.name == "component.storage.json_file.md"
    )
    assert "`OpenJsonFileStorage`" in json_page
    assert '`relativeDirectoryPath: JsonRelativePath` = `"."`' in json_page
    assert "| `write` | `storageRoot` | `write` |" in json_page
    assert (
        "| `contract.storage.json_file.write_effect` | `WriteJsonDocument` | `storage.write` |"
        in json_page
    )

    schema_page = next(
        content for path, content in pages.items() if path.name == "component.rtg.schema.md"
    )
    assert "`valueKinds[1..*]: RtgSchemaValueKind`" in schema_page
    assert "`anchorTypeKeys: String[1..*] ordered`" in schema_page
    assert "`properties[0..*]: RtgSchemaProperty`" in schema_page
    assert "`direction: RtgSchemaParticipationQueryDirection`" in schema_page
    assert "`direction: RtgSchemaParticipationDirection`" in schema_page

    query_page = next(
        content for path, content in pages.items() if path.name == "component.rtg.query.md"
    )
    assert "`anchors[1..*]: RtgQueryNamedObjectBinding`" in query_page
    assert "`liveStatusOverlay[0..*]: RtgQueryLiveStatusOverride`" in query_page

    graph_page = next(
        content for path, content in pages.items() if path.name == "component.rtg.graph.md"
    )
    assert "| `getObject` | `GetGraphObject` |" in graph_page
    assert "`uuid[0..1]: Uuid`" in graph_page
    assert "`type: String`" in graph_page
    assert "`system: RtgSystem`" in graph_page

    vellis_page = (ROOT / "generated" / "reference" / "vellis" / "index.md").read_text(
        encoding="utf-8"
    )
    assert "## Requirements and satisfaction" in vellis_page
    assert "## Verification closure" in vellis_page
    assert "## Python realization" in vellis_page
    assert "`documentStorage` | `JsonFileStorage` | `LocalJsonFileStorage`" in vellis_page
    assert "`state: RtgGetSystemState`, `guide: RtgGetUsageGuide`" in vellis_page
    assert "`rtgGetSystemState` → `GetSystemState` → `getSystemState`" in vellis_page


def test_generated_bibliotek_index_covers_library_topology() -> None:
    index = (ROOT / "generated" / "reference" / "bibliotek" / "index.md").read_text(
        encoding="utf-8"
    )

    assert "## Shared public packages" in index
    assert "`BibliotekSoftwareValues`" in index
    assert "## Shared public values" in index
    assert "`JsonValue`" in index
    assert "`RtgDiagnostic`" in index
    assert "`safeToRetry: Boolean`" in index
    assert "## Retained component dependency topology" in index
    assert "`component.rtg.controller`" in index
    assert "`component.rtg.graph`" in index


def test_model_handoff_names_complete_products_and_application_sources(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert model_tool.handoff("component.rtg.query") == 0
    component_output = capsys.readouterr().out
    assert "bibliotek-0.1.0.kpar" in component_output
    assert "generated/reference/bibliotek/components/component.rtg.query.md" in component_output

    assert model_tool.handoff("application.vellis") == 0
    application_output = capsys.readouterr().out
    assert "vellis-0.1.0.kpar" in application_output
    for source in (
        "model/vellis/EverydayLifeOntology.sysml",
        "model/vellis/Vellis.sysml",
        "model/vellis/VellisOperations.sysml",
        "model/vellis/use-cases/VellisUseCases.sysml",
        "model/vellis/realizations/VellisLocalPython.sysml",
        "model/vellis/realizations/VellisMcpPython.sysml",
    ):
        assert source in application_output
    assert "apps/rtg_knowledge_graph/resources/everyday_life_schema.json" in application_output
    assert "Verification: 32 structured objective(s)" in application_output


def test_model_packages_exclude_fixture_configuration_and_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "packages"
    monkeypatch.setattr(model_tool, "MODEL_PACKAGE_ROOT", package_root)

    model_tool.package_models()

    expected_sources = {
        "software-component-modeling-foundation-0.1.0.kpar": {"SoftwareComponentModeling.sysml"},
        "bibliotek-0.1.0.kpar": {
            path.name for path in model_layout.BIBLIOTEK_MODEL_ROOT.rglob("*.sysml")
        },
        "vellis-0.1.0.kpar": {
            path.name for path in model_layout.VELLIS_MODEL_ROOT.rglob("*.sysml")
        },
    }
    for archive_name, expected in expected_sources.items():
        with zipfile.ZipFile(package_root / archive_name) as archive:
            actual = {Path(name).name for name in archive.namelist() if name.endswith(".sysml")}
            project_path = next(
                name for name in archive.namelist() if name.endswith(".project.json")
            )
            metadata_path = next(name for name in archive.namelist() if name.endswith(".meta.json"))
            project = json.loads(archive.read(project_path))
            metadata = json.loads(archive.read(metadata_path))
        assert actual == expected
        assert "SoftwareComponentPattern.sysml" not in actual
        assert project["version"] == "0.1.0"
        assert metadata["status"] == "formally-validated"
