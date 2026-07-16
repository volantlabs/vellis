from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools import sysml_diagrams, sysml_validator

ROOT = Path(__file__).resolve().parents[1]


def _index(source: str, elements: list[dict[str, str]]) -> dict[str, object]:
    return {
        "packages": {
            "ExampleViews": {
                "source": source,
                "named_elements": elements,
            }
        }
    }


def test_diagram_discovery_resolves_identity_qualified_name_and_paths(tmp_path: Path) -> None:
    source = tmp_path / "model" / "ExampleViews.sysml"
    source.parent.mkdir()
    source.write_text(
        """package ExampleViews {
            view <'diagram.bibliotek.component.example.contract'> exampleDiagram {
                expose Example::Root;
                render asTreeDiagram;
            }
        }""",
        encoding="utf-8",
    )
    index = _index(
        "model/ExampleViews.sysml",
        [
            {
                "kind": "ViewUsage",
                "name": "exampleDiagram",
                "short_name": "diagram.bibliotek.component.example.contract",
            }
        ],
    )

    assert sysml_diagrams.discover_diagrams(index, root=tmp_path) == (
        sysml_diagrams.DiagramSpec(
            diagram_id="diagram.bibliotek.component.example.contract",
            product="bibliotek",
            name="component.example.contract",
            package="ExampleViews",
            view_name="exampleDiagram",
            rendering="asTreeDiagram",
        ),
    )
    spec = sysml_diagrams.discover_diagrams(index, root=tmp_path)[0]
    assert spec.qualified_name == "ExampleViews::exampleDiagram"
    assert spec.artifact_path("svg") == Path("bibliotek/diagrams/component.example.contract.svg")


def test_diagram_discovery_rejects_duplicate_ids_and_unsupported_rendering(
    tmp_path: Path,
) -> None:
    source = tmp_path / "views.sysml"
    source.write_text(
        """package ExampleViews {
            view <'diagram.bibliotek.example'> first { render asElementTable; }
            view <'diagram.bibliotek.example'> second { render asTreeDiagram; }
        }""",
        encoding="utf-8",
    )
    unsupported = _index(
        "views.sysml",
        [
            {
                "kind": "ViewUsage",
                "name": "first",
                "short_name": "diagram.bibliotek.example",
            }
        ],
    )
    with pytest.raises(ValueError, match="must render exactly once"):
        sysml_diagrams.discover_diagrams(unsupported, root=tmp_path)

    source.write_text(source.read_text(encoding="utf-8").replace("asElementTable", "asTreeDiagram"))
    duplicate = _index(
        "views.sysml",
        [
            {"kind": "ViewUsage", "name": name, "short_name": "diagram.bibliotek.example"}
            for name in ("first", "second")
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        sysml_diagrams.discover_diagrams(duplicate, root=tmp_path)


def test_plantuml_normalization_removes_volatile_links_and_normalizes_newlines() -> None:
    source = (
        "@startuml\r\nskinparam wrapWidth 300\r\n"
        'comp def "A  " <<part  def>> [[psysml:1234]] {\r\n'
        "##//doc//##\r\nMeaning.\r\n}\r\n@enduml\r\n"
    )

    assert sysml_diagrams.normalize_plantuml(source) == (
        b'@startuml\nskinparam wrapWidth 380\ncomp def "A" <<part def>>  {\nMeaning.\n}\n@enduml\n'
    )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("", "empty"),
        ("@startuml\nERROR: failed\n@enduml", "incomplete"),
        ("@startuml\nEXCEEDS THE LIMIT\n@enduml", "incomplete"),
        ("not a supported rendering", "unsupported"),
    ],
)
def test_plantuml_normalization_rejects_every_incomplete_output_class(
    source: str, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        sysml_diagrams.normalize_plantuml(source)


@pytest.mark.parametrize("source", [b"", b"<svg>ERROR:</svg>", b"<svg>"])
def test_svg_normalization_rejects_invalid_renderer_output(source: bytes) -> None:
    with pytest.raises(ValueError):
        sysml_diagrams.normalize_svg(source)


def test_svg_normalization_removes_cross_renderer_text_metric_overrides() -> None:
    source = b'<svg><text lengthAdjust="spacing" textLength="63" x="1">part def</text></svg>'

    normalized = sysml_diagrams.normalize_svg(source)

    assert b"lengthAdjust" not in normalized
    assert b"textLength" not in normalized
    assert b">part def</text>" in normalized


def test_smetana_renderer_launches_java_headlessly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[str] = []

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        captured.extend(command)
        return subprocess.CompletedProcess(command, 0, b"<svg></svg>", b"")

    monkeypatch.setattr(
        sysml_diagrams,
        "setup",
        lambda: (tmp_path / "java", tmp_path / "kernel.jar", tmp_path / "library"),
    )
    monkeypatch.setattr(sysml_diagrams.subprocess, "run", fake_run)

    assert sysml_diagrams.render_svg(b"@startuml\n@enduml\n") == b"<svg></svg>\n"
    assert captured[:4] == [
        str(tmp_path / "java"),
        sysml_validator.JAVA_HEADLESS_OPTION,
        "-cp",
        str(tmp_path / "kernel.jar"),
    ]


def test_official_kernel_launches_java_headlessly() -> None:
    source = Path("tools/sysml_validator.py").read_text(encoding="utf-8")

    assert 'JAVA_HEADLESS_OPTION = "-Djava.awt.headless=true"' in source
    assert (
        'str(java),\n                    JAVA_HEADLESS_OPTION,\n                    "-cp",'
        in source
    )


def test_atomic_sync_removes_stale_artifacts_only_after_complete_generation(
    tmp_path: Path,
) -> None:
    stale = tmp_path / "bibliotek" / "diagrams" / "stale.svg"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")
    artifacts = {
        Path("bibliotek/diagrams/example.puml"): b"@startuml\n@enduml\n",
        Path("bibliotek/diagrams/example.svg"): b"<svg></svg>\n",
    }

    sysml_diagrams.synchronize_artifacts(artifacts, root=tmp_path)

    assert not stale.exists()
    assert sysml_diagrams.check_artifacts(artifacts, root=tmp_path) == []


def test_backend_selection_is_fail_closed() -> None:
    assert isinstance(sysml_diagrams.backend_named("pilot"), sysml_diagrams.PilotBackend)
    with pytest.raises(ValueError, match="unsupported"):
        sysml_diagrams.backend_named("syside")


def test_registered_catalog_has_six_supported_unique_diagrams() -> None:
    specs = sysml_diagrams.load_registered_diagrams()

    assert len(specs) == 6
    assert len({spec.diagram_id for spec in specs}) == 6
    assert {spec.rendering for spec in specs} <= sysml_diagrams.SUPPORTED_RENDERINGS
    assert {spec.name for spec in specs} == {
        "component.rtg.constraints.contract",
        "component.rtg.discovery.contract",
        "component.rtg.migration.contract",
        "component.rtg.schema.contract",
        "component.storage.json_file.contract",
        "component.storage.sql.contract",
    }
    for spec in specs:
        plantuml = (sysml_diagrams.REFERENCE_DOC_ROOT / spec.artifact_path("puml")).read_text()
        svg = (sysml_diagrams.REFERENCE_DOC_ROOT / spec.artifact_path("svg")).read_bytes()
        assert "skin sysmlc" in plantuml
        if spec.name in {
            "component.rtg.constraints.contract",
            "component.rtg.migration.contract",
            "component.rtg.schema.contract",
        }:
            assert "applyBatch:" in plantuml
            assert "comp usage" in plantuml
            assert "EXCEEDS THE LIMIT" not in plantuml
        else:
            assert "##//perform actions//##" in plantuml
            assert "comp usage" not in plantuml
        assert b"textLength" not in svg
        assert b"lengthAdjust" not in svg


@pytest.mark.integration
def test_minimal_view_renders_through_pinned_kernel_and_smetana() -> None:
    source = """package DiagramFixture {
        private import Views::*;
        part def Root { part child; }
        view <'diagram.fixture.minimal'> minimalDiagram {
            expose Root;
            render asTreeDiagram;
        }
    }"""
    with sysml_validator._kernel_session() as client:
        diagnostics, _ = sysml_validator._execute_source(client, source)
        assert diagnostics == []
        diagnostics, outputs = sysml_validator._execute_source(
            client,
            "%view --style PUMLCODE --style HIDEMETADATA DiagramFixture::minimalDiagram",
        )
    assert diagnostics == []
    plantuml = next(item["text/plain"] for item in outputs if "text/plain" in item)
    svg = sysml_diagrams.render_svg(sysml_diagrams.normalize_plantuml(plantuml))
    assert b"<svg" in svg


@pytest.mark.integration
def test_all_registered_views_are_byte_identical_across_kernel_sessions() -> None:
    specs = sysml_diagrams.load_registered_diagrams()

    first = sysml_diagrams.PilotBackend().generate(specs)
    second = sysml_diagrams.PilotBackend().generate(specs)

    assert first == second
    assert sysml_diagrams.check_artifacts(first) == []


@pytest.mark.integration
def test_broad_library_view_fails_on_traversal_limit_instead_of_becoming_an_artifact() -> None:
    with sysml_validator._kernel_session() as client:
        for path in sysml_validator._model_files("all"):
            diagnostics, _ = sysml_validator._execute_source(
                client, path.read_text(encoding="utf-8")
            )
            assert not any(sysml_validator.DIAGNOSTIC.search(line) for line in diagnostics)
        diagnostics, outputs = sysml_validator._execute_source(
            client,
            "%view --style PUMLCODE --style HIDEMETADATA "
            "BibliotekViews::bibliotekComponentStructure",
        )
    assert diagnostics == []
    plantuml = next(item["text/plain"] for item in outputs if "text/plain" in item)
    with pytest.raises(ValueError, match="EXCEEDS THE LIMIT"):
        sysml_diagrams.normalize_plantuml(plantuml)


def test_formal_index_fixture_is_json_serializable() -> None:
    # Keep the small inventory shape used by discovery tests aligned with the committed JSON form.
    assert json.loads(json.dumps(_index("views.sysml", [])))["packages"]
