"""Evidence that a fallible checkpoint never erases an owner-facing outcome."""

from __future__ import annotations

import io
from pathlib import Path
from typing import TextIO

import pytest

import vellis.__main__ as owner_command
import vellis.mcp as mcp_boundary
import vellis.preserve as preserve_command
from vellis.outcomes import OperationStatus, RevisionedOutcome
from vellis.store import StoreError
from vellis.streaming import SnapshotMetadata


class _BlockedCloseSystem:
    is_initialized = True

    class _Store:
        revision = 0
        activity_count = 0

        def current_revision(self) -> int:
            return self.revision

        def activity_record_count(self) -> int:
            return self.activity_count

    def __init__(self) -> None:
        self.store = self._Store()

    def close(self) -> None:
        raise StoreError("another database reader prevented the write-ahead log checkpoint")


def test_mcp_shutdown_reports_checkpoint_contention_without_recasting_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _BlockedCloseSystem()

    class _Server:
        def run(self, *, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(mcp_boundary.ServeError) as raised:
        mcp_boundary.serve(memory)

    assert "changes already reported as committed remain committed" in raised.value.summary
    assert "close the other database reader" in raised.value.corrective_action
    assert raised.value.stage == mcp_boundary.ServeStage.CLOSE_MEMORY
    assert not raised.value.memory_changed


def test_mcp_shutdown_reports_whether_the_completed_session_changed_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _BlockedCloseSystem()

    class _Server:
        def run(self, *, transport: str) -> None:
            assert transport == "stdio"
            system.store.revision = 1

    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(mcp_boundary.ServeError) as raised:
        mcp_boundary.serve(memory)

    assert raised.value.stage == mcp_boundary.ServeStage.CLOSE_MEMORY
    assert raised.value.memory_changed


def test_mcp_shutdown_counts_read_activity_as_a_changed_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _BlockedCloseSystem()

    class _Server:
        def run(self, *, transport: str) -> None:
            assert transport == "stdio"
            system.store.activity_count = 1

    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(mcp_boundary.ServeError) as raised:
        mcp_boundary.serve(memory)

    assert raised.value.stage == mcp_boundary.ServeStage.CLOSE_MEMORY
    assert raised.value.memory_changed


def test_public_server_command_keeps_the_close_stage_and_state_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    error = io.StringIO()

    def failed_close(path: Path) -> None:
        raise mcp_boundary.ServeError(
            "the server stopped after committed changes",
            "close the other database reader",
            stage=mcp_boundary.ServeStage.CLOSE_MEMORY,
            memory_changed=True,
        )

    monkeypatch.setattr(owner_command, "serve", failed_close)

    code = owner_command.main(["--data-dir", str(directory)], stderr=error)

    assert code == owner_command.EXIT_FAILED
    assert "Stage: close-memory" in error.getvalue()
    assert "established memory: changed" in error.getvalue()


def test_restore_close_failure_names_the_committed_state_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    owner_command.store_path(directory).touch()

    class _RestoreSystem(_BlockedCloseSystem):
        def restore_historical_state(self, selection: object, *, provenance: object):
            return RevisionedOutcome(
                status=OperationStatus.ACCEPTED,
                summary="restored revision 0 as revision 1",
                resulting_revision=1,
            )

    monkeypatch.setattr(owner_command.RTGSystem, "open", lambda path: _RestoreSystem())
    output, error = io.StringIO(), io.StringIO()

    code = owner_command._restore(
        ["--data-dir", str(directory), "--revision", "0", "--yes"],
        output=output,
        error=error,
        confirm=lambda prompt: "yes",
    )

    assert code == owner_command.EXIT_FAILED
    assert "restored revision 0 as revision 1" in output.getvalue()
    assert "Stage: close-memory" in error.getvalue()
    assert "established memory: changed" in error.getvalue()
    assert "inspect history before retrying" in error.getvalue()


def test_preserve_close_failure_keeps_the_published_snapshot_truthful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()
    document = tmp_path / "memory.snapshot"

    class _PreserveSystem(_BlockedCloseSystem):
        def export_snapshot(self, stream: TextIO, *, provenance: object) -> SnapshotMetadata:
            stream.write("snapshot\n")
            return SnapshotMetadata(0, "record", 1, "digest", 1)

    monkeypatch.setattr(preserve_command.RTGSystem, "open", lambda path: _PreserveSystem())
    output, error = io.StringIO(), io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(document)],
        stdout=output,
        stderr=error,
    )

    assert code == preserve_command.EXIT_FAILED
    assert document.read_text(encoding="utf-8") == "snapshot\n"
    assert "Preserved revision 0" in output.getvalue()
    assert "Stage: close-memory" in error.getvalue()
    assert "snapshot document: written" in error.getvalue()
    assert "does not need repeating" in error.getvalue()
