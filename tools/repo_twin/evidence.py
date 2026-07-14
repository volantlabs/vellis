from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from components.rtg.change_validation import (
    RtgChangeReference,
    RtgGraphChangeSet,
    RtgGraphDataObjectWrite,
)
from components.rtg.graph.protocol import JsonObject
from tools.repo_twin.model import DataRecord, managed_system, twin_uuid
from tools.repo_twin.scanner import component_subject_hashes, repo_metadata, scan_repo
from tools.repo_twin.store import open_controller, sync_scan


def run_and_record(repo_root: Path, storage_root: Path, kind: str, command: tuple[str, ...]) -> int:
    if not command:
        raise ValueError("evidence command is required after --")
    completed = subprocess.run(command, cwd=repo_root, capture_output=True, text=True)
    sys.stdout.write(completed.stdout)
    sys.stderr.write(completed.stderr)
    scan = scan_repo(repo_root)
    sync_scan(scan, storage_root)
    metadata = repo_metadata(repo_root)
    produced_at = datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    summary = _summary(completed.stdout, completed.stderr, completed.returncode)
    command_text = " ".join(command)
    repo_hash = next(
        (
            data.properties["source_hash"]
            for data in scan.data_objects
            if data.natural_key == "repo:fact"
            and isinstance(data.properties.get("source_hash"), str)
        ),
        "",
    )
    anchor_keys = {"repo"}
    subject_hashes: JsonObject = {}
    if kind == "test_run":
        for component in scan.components.values():
            impl = next(
                (
                    scan.implementation_roots[root]
                    for root in component.declared_code_roots
                    if root in scan.implementation_roots
                    and scan.implementation_roots[root].has_tests
                ),
                None,
            )
            if impl is None:
                continue
            anchor_keys.add(f"component:{component.component_id}")
            anchor_keys.add(f"tests:{impl.path}/tests")
            subject_hashes.update(component_subject_hashes(component, impl))
    evidence_key = _evidence_key(kind, command_text, produced_at, subject_hashes)
    record = DataRecord(
        evidence_key,
        "twin.EvidenceRecord",
        {
            "source_path": ".",
            "source_hash": str(repo_hash),
            "repo_commit": metadata.repo_commit,
            "last_indexed_at": produced_at,
            "authority": "evidence",
            "lifecycle_status": "active",
            "kind": kind,
            "command": command_text,
            "passed": completed.returncode == 0,
            "summary": summary,
            "produced_at": produced_at,
            "subject_hashes": json.dumps(subject_hashes, sort_keys=True),
            "artifact_path": None,
        },
        tuple(sorted(anchor_keys)),
    )
    controller = open_controller(storage_root)
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
    controller.persist_system_snapshot("snapshots/current.json")
    return completed.returncode


def _evidence_key(
    kind: str,
    command_text: str,
    produced_at: str,
    subject_hashes: JsonObject,
) -> str:
    digest = hashlib.sha256(
        repr((kind, command_text, produced_at, sorted(subject_hashes.items()))).encode("utf-8")
    ).hexdigest()
    return f"evidence:{kind}:{digest}"


def _summary(stdout: str, stderr: str, returncode: int) -> str:
    for stream in (stdout, stderr):
        lines = [line.strip() for line in stream.splitlines() if line.strip()]
        if lines:
            return f"exit {returncode}: {lines[-1]}"
    return f"exit {returncode}"
