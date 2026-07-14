from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

from components.rtg.change_validation import (
    RtgChangeReference,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
)
from components.rtg.graph.protocol import JsonObject
from tools.repo_twin.check import evaluate_findings
from tools.repo_twin.commands import main as repo_twin_main
from tools.repo_twin.evidence import run_and_record
from tools.repo_twin.model import SNAPSHOT_PATH, DataRecord, managed_system, twin_uuid
from tools.repo_twin.scanner import component_subject_hashes, scan_repo
from tools.repo_twin.store import current_snapshot, open_controller, snapshot_loaded, sync_scan


def test_scanner_extracts_sysml_authority_and_repo_concepts(tmp_path: Path) -> None:
    scan = scan_repo(_fixture_repo(tmp_path))

    assert scan.parse_issues == ()
    assert scan.components["component.demo.core"].spec_path == (
        "model/bibliotek/components/component.demo.core.sysml"
    )
    assert scan.components["component.demo.core"].declared_code_roots == ("components/demo/core",)
    assert "components/demo/core" in scan.implementation_roots
    assert {anchor.type_key for anchor in scan.anchors} >= {
        "twin.Component",
        "twin.SpecDocument",
        "twin.ImplementationRoot",
        "twin.TestSuite",
        "twin.App",
    }
    assert any(link.type_key == "twin.Verifies" for link in scan.links)
    component_fact = next(
        item
        for item in scan.data_objects
        if item.natural_key == "component:component.demo.core:fact"
    )
    assert component_fact.properties["authority"] == "model"


def test_sync_is_idempotent_and_check_is_warnings_only_for_missing_evidence(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path / "repo")
    storage = tmp_path / "twin"

    first = sync_scan(scan_repo(repo), storage)
    second = sync_scan(scan_repo(repo), storage)
    findings = evaluate_findings(scan_repo(repo), storage)

    assert first.created > 0
    assert not second.changed
    assert not any(finding.severity == "error" for finding in findings)
    assert {finding.finding_id for finding in findings} == {"missing_evidence"}


def test_evidence_cli_parses_options_before_separator_regardless_of_order(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path / "repo")
    command = [sys.executable, "-c", "print('ok')"]

    for label, evidence_args in (
        (
            "before-kind",
            [
                "--repo-root",
                str(repo),
                "--storage-root",
                str(tmp_path / "twin-before-kind"),
                "test_run",
            ],
        ),
        (
            "after-kind",
            [
                "test_run",
                "--repo-root",
                str(repo),
                "--storage-root",
                str(tmp_path / "twin-after-kind"),
            ],
        ),
    ):
        storage = tmp_path / f"twin-{label}"
        result = repo_twin_main(["evidence", *evidence_args, "--", *command])

        assert result == 0
        assert snapshot_loaded(storage)
        assert "missing_evidence" not in _finding_ids(repo, storage)


def test_test_run_evidence_expires_when_modeled_contract_changes(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path / "repo")
    storage = tmp_path / "twin"
    sync_scan(scan_repo(repo), storage)

    assert run_and_record(repo, storage, "test_run", _passing_command()) == 0
    assert not _finding_ids(repo, storage)

    model = repo / "model" / "bibliotek" / "components" / "component.demo.core.sysml"
    model.write_text(
        model.read_text(encoding="utf-8").replace(
            "Return ok without mutation.",
            "Return ok and record the call without mutation.",
        ),
        encoding="utf-8",
    )
    _write_formal_index(repo)

    unsynced_findings = _finding_ids(repo, storage)
    assert "stale_graph" in unsynced_findings
    assert "changed_contract" in unsynced_findings

    sync_scan(scan_repo(repo), storage)
    assert "changed_contract" in _finding_ids(repo, storage)

    assert run_and_record(repo, storage, "test_run", _passing_command()) == 0
    assert "changed_contract" not in _finding_ids(repo, storage)


def test_deleted_model_after_regeneration_yields_orphan_code_root(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path / "repo")
    storage = tmp_path / "twin"
    sync_scan(scan_repo(repo), storage)

    (repo / "model" / "bibliotek" / "components" / "component.demo.core.sysml").unlink()
    _write_formal_index(repo)
    summary = sync_scan(scan_repo(repo), storage)
    findings = evaluate_findings(scan_repo(repo), storage)

    assert summary.pruned > 0
    assert any(
        finding.finding_id == "orphan_code_root"
        and finding.subject == "components/demo/core"
        and finding.severity == "error"
        for finding in findings
    )
    assert "stale_graph" not in {finding.finding_id for finding in findings}


def test_sync_fails_closed_on_stale_formal_index_and_preserves_snapshot(
    tmp_path: Path,
) -> None:
    repo = _fixture_repo(tmp_path / "repo")
    storage = tmp_path / "twin"
    assert repo_twin_main(["sync", "--repo-root", str(repo), "--storage-root", str(storage)]) == 0
    before = current_snapshot(storage)

    model = repo / "model" / "bibliotek" / "components" / "component.demo.core.sysml"
    original = model.read_text(encoding="utf-8")
    model.write_text(original.replace("Return ok", "Return changed ok"), encoding="utf-8")

    assert repo_twin_main(["sync", "--repo-root", str(repo), "--storage-root", str(storage)]) == 1
    assert current_snapshot(storage) == before
    with pytest.raises(ValueError, match="parse issues"):
        sync_scan(scan_repo(repo), storage)

    _write_formal_index(repo)
    assert repo_twin_main(["sync", "--repo-root", str(repo), "--storage-root", str(storage)]) == 0


def test_same_second_evidence_resolves_deterministically(tmp_path: Path) -> None:
    repo = _fixture_repo(tmp_path / "repo")
    scan = scan_repo(repo)
    component = scan.components["component.demo.core"]
    impl = scan.implementation_roots["components/demo/core"]
    current_hashes = component_subject_hashes(component, impl)
    stale_hashes: JsonObject = {key: "sha256:stale" for key in current_hashes}

    older = "2026-07-07T00:00:00Z"
    newer = "2026-07-07T00:00:00.250000Z"
    for index, order in enumerate((("stale", "current"), ("current", "stale"))):
        storage = tmp_path / f"twin-newest-{index}"
        sync_scan(scan, storage)
        for name in order:
            _write_test_run_evidence(
                storage,
                f"evidence:test_run:{name}",
                older if name == "stale" else newer,
                stale_hashes if name == "stale" else current_hashes,
            )
        assert "changed_contract" not in _finding_ids(repo, storage)

    tie = "2026-07-07T00:00:01Z"
    stale_wins = str(twin_uuid("evidence:test_run:stale")) > str(
        twin_uuid("evidence:test_run:current")
    )
    for index, order in enumerate((("stale", "current"), ("current", "stale"))):
        storage = tmp_path / f"twin-tie-{index}"
        sync_scan(scan, storage)
        for name in order:
            _write_test_run_evidence(
                storage,
                f"evidence:test_run:{name}",
                tie,
                stale_hashes if name == "stale" else current_hashes,
            )
        assert ("changed_contract" in _finding_ids(repo, storage)) == stale_wins


def _write_test_run_evidence(
    storage: Path,
    natural_key: str,
    produced_at: str,
    subject_hashes: JsonObject,
) -> None:
    record = DataRecord(
        natural_key,
        "twin.EvidenceRecord",
        {
            "source_path": ".",
            "source_hash": "",
            "repo_commit": "test",
            "last_indexed_at": produced_at,
            "authority": "evidence",
            "lifecycle_status": "active",
            "kind": "test_run",
            "command": "pytest",
            "passed": True,
            "summary": "exit 0",
            "produced_at": produced_at,
            "subject_hashes": json.dumps(subject_hashes, sort_keys=True),
            "artifact_path": None,
        },
        ("component:component.demo.core",),
    )
    controller = open_controller(storage)
    controller.apply_live_graph_changes(
        RtgGraphChangeSet(
            data_object_writes=(
                RtgGraphDataObjectWrite(
                    ref=RtgChangeReference(resource_id=record.uuid),
                    type=record.type_key,
                    properties=record.properties,
                    system=managed_system(record.natural_key, authority="evidence"),
                    anchor_refs=tuple(
                        RtgChangeReference(resource_id=twin_uuid(key)) for key in record.anchor_keys
                    ),
                ),
            )
        )
    )
    controller.persist_system_snapshot(SNAPSHOT_PATH)


def _finding_ids(repo: Path, storage: Path) -> set[str]:
    return {finding.finding_id for finding in evaluate_findings(scan_repo(repo), storage)}


def _passing_command() -> tuple[str, ...]:
    return (sys.executable, "-c", "print('ok')")


def _fixture_repo(root: Path) -> Path:
    _write(
        root / "model" / "bibliotek" / "components" / "component.demo.core.sysml",
        """library package DemoCoreModel {
    action def RunDemoCore {
        out result : String;
        doc /* Return ok without mutation. */
    }
    part def <'component.demo.core'> DemoCore {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        perform action run[0..*] : RunDemoCore;
    }
    requirement <'invariant.demo.core.always_ok'> alwaysOk {
        subject component : DemoCore;
        require constraint { doc /* Always return ok. */ }
    }
}
""",
    )
    _write(
        root / "model" / "bibliotek" / "realizations" / "DemoPython.sysml",
        """package DemoPythonRealization {
    part def LocalDemoCore :> DemoCore {
        @ImplementationBinding {
            implementationLanguage = ImplementationLanguage::python;
            codeRoot = "components/demo/core";
            symbol = "components.demo.core.DemoCore";
            realization = "DemoPython";
        }
    }
}
""",
    )
    _write(root / "components" / "demo" / "core" / "__init__.py", "")
    _write(root / "components" / "demo" / "core" / "protocol.py", "class DemoCore: ...\n")
    _write(
        root / "components" / "demo" / "core" / "implementation.py",
        "class DemoCore:\n    def run(self) -> str:\n        return 'ok'\n",
    )
    _write(
        root / "components" / "demo" / "core" / "reference.py",
        "from .implementation import DemoCore\n",
    )
    _write(
        root / "components" / "demo" / "core" / "tests" / "test_demo_core.py",
        "def test_demo_core() -> None:\n    assert True\n",
    )
    _write(root / "apps" / "demo_app" / "__main__.py", "print('demo')\n")
    _write_formal_index(root)
    return root


def _write_formal_index(root: Path) -> None:
    packages: dict[str, object] = {}
    authored: dict[str, str] = {}
    for path in sorted((root / "model").rglob("*.sysml")):
        text = path.read_text(encoding="utf-8")
        package_match = re.search(r"\b(?:library )?package\s+(\w+)", text)
        assert package_match is not None
        package_name = package_match.group(1)
        source = path.relative_to(root).as_posix()
        elements: list[JsonObject] = []
        for component_id, name in re.findall(r"\bpart def\s+<'(component\.[^']+)'>\s+(\w+)", text):
            elements.append({"kind": "PartDefinition", "name": name, "short_name": component_id})
        for name in re.findall(r"\baction def\s+(\w+)", text):
            elements.append({"kind": "ActionDefinition", "name": name})
        for stable_id, name in re.findall(r"\brequirement\s+<'([^']+)'>\s+(\w+)", text):
            elements.append({"kind": "RequirementUsage", "name": name, "short_name": stable_id})
        packages[package_name] = {
            "source": source,
            "element_counts": {},
            "named_elements": elements,
        }
        authored[package_name] = source
    digest = hashlib.sha256()
    model_root = root / "model"
    for source in sorted(
        authored.values(), key=lambda item: (root / item).relative_to(model_root).as_posix()
    ):
        path = root / source
        digest.update(path.relative_to(model_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    payload = {
        "schema_version": "1",
        "source_digest": digest.hexdigest(),
        "authored_packages": authored,
        "packages": packages,
        "validator": {},
    }
    _write(
        root / "generated" / "model" / "formal-model-index.json",
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
    )


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
