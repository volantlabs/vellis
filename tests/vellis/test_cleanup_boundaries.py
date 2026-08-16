"""Evidence that a fallible checkpoint never erases an owner-facing outcome."""

from __future__ import annotations

import io
import os
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
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        raise StoreError("another database reader prevented the write-ahead log checkpoint")


class _CleanCloseSystem(_BlockedCloseSystem):
    def close(self) -> None:
        self.close_calls += 1


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


@pytest.mark.parametrize("change", ("none", "activity", "revision"))
def test_unexpected_mcp_runtime_failure_reports_its_stage_and_observed_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _CleanCloseSystem()

    class _Server:
        def run(self, *, transport: str) -> None:
            assert transport == "stdio"
            if change == "activity":
                system.store.activity_count = 1
            elif change == "revision":
                system.store.revision = 1
            raise RuntimeError("transport failed")

    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(mcp_boundary.ServeError) as raised:
        mcp_boundary.serve(memory)

    assert raised.value.stage == mcp_boundary.ServeStage.SERVE_MEMORY
    assert raised.value.memory_changed is (change != "none")
    assert "transport failed" in raised.value.summary
    assert "inspect activity and canonical history" in raised.value.corrective_action
    assert system.close_calls == 1


def test_unexpected_mcp_runtime_and_close_failures_are_both_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _BlockedCloseSystem()

    class _Server:
        def run(self, *, transport: str) -> None:
            raise RuntimeError("transport failed")

    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(mcp_boundary.ServeError) as raised:
        mcp_boundary.serve(memory)

    assert "transport failed" in raised.value.summary
    assert "memory cleanup also failed" in raised.value.summary
    assert "before copying the memory file" in raised.value.corrective_action


def test_mcp_process_control_failure_keeps_its_meaning_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _CleanCloseSystem()

    class _Server:
        def run(self, *, transport: str) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(KeyboardInterrupt):
        mcp_boundary.serve(memory)
    assert system.close_calls == 1


def test_mcp_shutdown_reports_an_indeterminate_effect_when_final_position_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    memory = tmp_path / "vellis.sqlite3"
    memory.touch()
    system = _BlockedCloseSystem()
    revision_reads = 0

    def current_revision() -> int:
        nonlocal revision_reads
        revision_reads += 1
        if revision_reads == 2:
            raise StoreError("final position unavailable")
        return 0

    class _Server:
        def run(self, *, transport: str) -> None:
            assert transport == "stdio"

    monkeypatch.setattr(system.store, "current_revision", current_revision)
    monkeypatch.setattr(mcp_boundary.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(mcp_boundary, "build_server", lambda value, name: _Server())

    with pytest.raises(mcp_boundary.ServeError) as raised:
        mcp_boundary.serve(memory)

    assert raised.value.stage == mcp_boundary.ServeStage.CLOSE_MEMORY
    assert raised.value.memory_changed is None
    assert system.close_calls == 1

    error = io.StringIO()

    def failed_close(path: Path) -> None:
        raise raised.value

    monkeypatch.setattr(owner_command, "serve", failed_close)
    code = owner_command.main(["--data-dir", str(tmp_path / "memory")], stderr=error)

    assert code == owner_command.EXIT_FAILED
    assert "Stage: close-memory" in error.getvalue()
    assert "established memory: could not be determined" in error.getvalue()


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
            self.store.revision = 1
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


def test_rejected_restore_reports_restore_and_its_activity_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    owner_command.store_path(directory).touch()

    class _RestoreSystem(_CleanCloseSystem):
        def restore_historical_state(self, selection: object, *, provenance: object):
            self.store.activity_count += 1
            return RevisionedOutcome(
                status=OperationStatus.REJECTED,
                summary="revision 99 does not exist",
            )

    monkeypatch.setattr(owner_command.RTGSystem, "open", lambda path: _RestoreSystem())
    output, error = io.StringIO(), io.StringIO()

    code = owner_command._restore(
        ["--data-dir", str(directory), "--revision", "99", "--yes"],
        output=output,
        error=error,
        confirm=lambda prompt: "yes",
    )

    assert code == owner_command.EXIT_FAILED
    assert "Vellis could not restore this memory" in error.getvalue()
    assert "established memory: changed" in error.getvalue()


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
            self.store.activity_count += 1
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


def test_preserve_never_replaces_a_concurrently_created_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()
    document = tmp_path / "memory.snapshot"

    class _PreserveSystem(_CleanCloseSystem):
        def export_snapshot(self, stream: TextIO, *, provenance: object) -> SnapshotMetadata:
            stream.write("snapshot\n")
            self.store.activity_count += 1
            return SnapshotMetadata(0, "record", 1, "digest", 1)

    real_link = os.link

    def establish_then_link(source: str, destination: Path) -> None:
        Path(destination).write_text("somebody else's document", encoding="utf-8")
        real_link(source, destination)

    monkeypatch.setattr(preserve_command.RTGSystem, "open", lambda path: _PreserveSystem())
    monkeypatch.setattr(preserve_command.os, "link", establish_then_link)
    error = io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(document)], stderr=error
    )

    assert code == preserve_command.EXIT_FAILED
    assert document.read_text(encoding="utf-8") == "somebody else's document"
    assert "Stage: write" in error.getvalue()


def test_preserve_refuses_a_dangling_symlink_before_observing_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()
    document = tmp_path / "memory.snapshot"
    document.symlink_to(tmp_path / "missing-target")

    def should_not_open(path: Path) -> object:
        raise AssertionError("memory should not be opened")

    monkeypatch.setattr(preserve_command.RTGSystem, "open", should_not_open)
    error = io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(document)], stderr=error
    )

    assert code == preserve_command.EXIT_FAILED
    assert document.is_symlink()
    assert "already exists" in error.getvalue()


def test_preserve_reports_capture_and_close_failures_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()

    class _PreserveSystem(_BlockedCloseSystem):
        def export_snapshot(self, stream: TextIO, *, provenance: object) -> SnapshotMetadata:
            self.store.activity_count += 1
            raise StoreError("capture unavailable")

    monkeypatch.setattr(preserve_command.RTGSystem, "open", lambda path: _PreserveSystem())
    error = io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(tmp_path / "out.snapshot")],
        stderr=error,
    )

    assert code == preserve_command.EXIT_FAILED
    assert "Stage: capture" in error.getvalue()
    assert "close-memory" in error.getvalue()
    assert "before copying the memory file" in error.getvalue()
    assert "attempt is recorded" in error.getvalue()


def test_preserve_reports_write_and_close_failures_together(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()

    class _PreserveSystem(_BlockedCloseSystem):
        def export_snapshot(self, stream: TextIO, *, provenance: object) -> SnapshotMetadata:
            stream.write("snapshot\n")
            self.store.activity_count += 1
            return SnapshotMetadata(0, "record", 1, "digest", 1)

    def fail_link(source: str, destination: Path) -> None:
        raise OSError("read only")

    monkeypatch.setattr(preserve_command.RTGSystem, "open", lambda path: _PreserveSystem())
    monkeypatch.setattr(preserve_command.os, "link", fail_link)
    error = io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(tmp_path / "out.snapshot")],
        stderr=error,
    )

    assert code == preserve_command.EXIT_FAILED
    assert "Stage: write" in error.getvalue()
    assert "close-memory" in error.getvalue()
    assert "before copying the memory file" in error.getvalue()


def test_preserve_failure_before_capture_does_not_claim_an_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()
    system = _CleanCloseSystem()
    monkeypatch.setattr(preserve_command.RTGSystem, "open", lambda path: system)
    monkeypatch.setattr(
        preserve_command.tempfile,
        "mkstemp",
        lambda **values: (_ for _ in ()).throw(OSError("no temporary file")),
    )
    error = io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(tmp_path / "out.snapshot")],
        stderr=error,
    )

    assert code == preserve_command.EXIT_FAILED
    assert "Stage: capture" in error.getvalue()
    assert "attempt is recorded" not in error.getvalue()


def test_preserve_reports_an_indeterminate_activity_effect_when_position_is_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "memory"
    directory.mkdir()
    preserve_command.store_path(directory).touch()

    class _UnreadablePositionSystem(_CleanCloseSystem):
        def __init__(self) -> None:
            super().__init__()
            self.activity_reads = 0

        def export_snapshot(self, stream: TextIO, *, provenance: object) -> SnapshotMetadata:
            raise StoreError("capture unavailable")

    system = _UnreadablePositionSystem()

    def activity_record_count() -> int:
        system.activity_reads += 1
        if system.activity_reads == 2:
            raise StoreError("activity position unavailable")
        return 0

    monkeypatch.setattr(system.store, "activity_record_count", activity_record_count)
    monkeypatch.setattr(preserve_command.RTGSystem, "open", lambda path: system)
    error = io.StringIO()

    code = preserve_command.main(
        ["--data-dir", str(directory), "--out", str(tmp_path / "out.snapshot")],
        stderr=error,
    )

    assert code == preserve_command.EXIT_FAILED
    assert "could not be determined" in error.getvalue()
