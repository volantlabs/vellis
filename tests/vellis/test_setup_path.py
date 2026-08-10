"""Evidence for the setup portion of ``VellisVerification::simpleOperation``.

The verification case is explicit that a generic failure does not pass: every failure
must name the stage that failed, state whether established memory changed, and offer an
available corrective action. ``SetupReport.is_actionable_failure`` is asserted for each
failure below so that a future regression toward a bare error message fails the suite.

Every case uses a temporary destination; none touches the platform default.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from vellis.canonical import canonical_state_equal
from vellis.paths import (
    DATA_DIRECTORY_VARIABLE,
    DestinationError,
    default_data_directory,
    resolve_data_directory,
    store_path,
)
from vellis.setup import (
    EXIT_DECLINED,
    EXIT_FAILED,
    EXIT_SUCCESS,
    SetupStage,
    main,
    prepare_local_system,
)
from vellis.system import RTGSystem

# --- Destination resolution ---------------------------------------------------------


def test_the_default_follows_each_platform_convention() -> None:
    home = Path("/home/owner")
    assert default_data_directory(platform="darwin", home=home, environ={}) == (
        home / "Library" / "Application Support" / "Vellis"
    )
    assert default_data_directory(
        platform="win32", home=home, environ={"LOCALAPPDATA": "/c/Users/owner/AppData/Local"}
    ) == Path("/c/Users/owner/AppData/Local/Vellis")
    assert default_data_directory(platform="linux", home=home, environ={}) == (
        home / ".local" / "share" / "vellis"
    )
    assert default_data_directory(
        platform="linux", home=home, environ={"XDG_DATA_HOME": "/home/owner/data"}
    ) == Path("/home/owner/data/vellis")


def test_an_explicit_destination_wins_over_the_environment(tmp_path: Path) -> None:
    chosen = tmp_path / "chosen"
    resolved = resolve_data_directory(
        chosen, environ={DATA_DIRECTORY_VARIABLE: str(tmp_path / "other")}
    )
    assert resolved == chosen.resolve()


def test_a_destination_named_dot_data_is_refused(tmp_path: Path) -> None:
    """The repository reserves ``.data/`` for owner-owned working data."""
    with pytest.raises(DestinationError):
        resolve_data_directory(tmp_path / ".data")


def test_an_empty_configured_destination_is_refused() -> None:
    with pytest.raises(DestinationError):
        resolve_data_directory(environ={DATA_DIRECTORY_VARIABLE: "   "})


def test_an_empty_explicit_destination_is_refused_not_read_as_the_working_directory() -> None:
    """Excludes ``--data-dir ""`` quietly establishing a system wherever setup was run."""
    for empty in ("", "   "):
        with pytest.raises(DestinationError):
            resolve_data_directory(empty)


def test_a_filesystem_root_is_refused() -> None:
    with pytest.raises(DestinationError):
        resolve_data_directory("/")


# --- Preparing a system -------------------------------------------------------------


def test_a_dry_run_creates_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    report = prepare_local_system(data_directory=destination, dry_run=True)
    assert report.succeeded
    assert not report.memory_changed
    assert report.stage == SetupStage.PREVIEW
    assert report.destination == destination.resolve()
    assert not destination.exists()


def test_setup_establishes_one_local_system(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    report = prepare_local_system(data_directory=destination)
    assert report.succeeded
    assert report.memory_changed
    assert report.revision == 0
    assert report.store == store_path(destination.resolve())
    assert report.store is not None and report.store.exists()

    system = RTGSystem.open(report.store)
    try:
        assert system.is_initialized
        assert system.current_state().revision == 0
        assert system.current_state().graph.is_empty
    finally:
        system.close()


def test_a_second_attempt_fails_actionably_and_leaves_memory_unchanged(tmp_path: Path) -> None:
    """Excludes a setup that re-seeds an established system or reports a bare error."""
    destination = tmp_path / "vellis"
    first = prepare_local_system(data_directory=destination)
    assert first.succeeded and first.store is not None

    system = RTGSystem.open(first.store)
    try:
        before = system.current_state()
    finally:
        system.close()

    second = prepare_local_system(data_directory=destination)
    assert not second.succeeded
    assert second.stage == SetupStage.INITIALIZE
    assert not second.memory_changed
    assert second.is_actionable_failure

    system = RTGSystem.open(first.store)
    try:
        assert canonical_state_equal(system.current_state(), before)
        assert canonical_state_equal(system.replay(), before)
        assert system.store.canonical_record_count() == 1
    finally:
        system.close()


def test_an_unresolvable_destination_fails_before_any_state_exists(tmp_path: Path) -> None:
    report = prepare_local_system(data_directory=tmp_path / ".data")
    assert not report.succeeded
    assert report.stage == SetupStage.RESOLVE_DESTINATION
    assert not report.memory_changed
    assert report.is_actionable_failure
    assert not (tmp_path / ".data").exists()


def test_an_unusable_destination_fails_at_the_prepare_stage(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory\n", encoding="utf-8")
    report = prepare_local_system(data_directory=blocker / "vellis")
    assert not report.succeeded
    assert report.stage == SetupStage.PREPARE_DESTINATION
    assert not report.memory_changed
    assert report.is_actionable_failure


# --- The documented command ---------------------------------------------------------


def _run(argv: list[str], answer: str = "") -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    code = main(argv, stdout=stdout, stderr=stderr, stdin=io.StringIO(answer))
    return code, stdout.getvalue(), stderr.getvalue()


def test_the_command_previews_before_it_changes_anything(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    code, out, _ = _run(["--data-dir", str(destination), "--dry-run"])
    assert code == EXIT_SUCCESS
    assert str(destination.resolve()) in out
    assert "blank" in out
    assert not destination.exists()


def test_declining_the_prompt_creates_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    code, out, _ = _run(["--data-dir", str(destination)], answer="n\n")
    assert code == EXIT_DECLINED
    assert "Declined" in out
    assert not store_path(destination.resolve()).exists()


def test_confirming_the_prompt_establishes_the_system(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    code, out, _ = _run(["--data-dir", str(destination)], answer="y\n")
    assert code == EXIT_SUCCESS
    assert "current revision: 0" in out
    assert store_path(destination.resolve()).exists()


def test_the_noninteractive_path_needs_no_terminal(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    code, _, _ = _run(["--data-dir", str(destination), "--yes"])
    assert code == EXIT_SUCCESS
    assert store_path(destination.resolve()).exists()


def test_a_failing_command_reports_stage_state_effect_and_next_step(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    assert _run(["--data-dir", str(destination), "--yes"])[0] == EXIT_SUCCESS
    code, _, err = _run(["--data-dir", str(destination), "--yes"])
    assert code == EXIT_FAILED
    assert f"stage: {SetupStage.INITIALIZE}" in err
    assert "established memory: unchanged" in err
    assert "what to do next:" in err


@pytest.mark.parametrize("relative", [".data", ".data/graphs", ".Data", "nested/.data/deep"])
def test_no_destination_inside_a_reserved_directory_is_accepted(
    tmp_path: Path, relative: str
) -> None:
    """The guard must hold at any depth and in any case, not only on the final component."""
    with pytest.raises(DestinationError):
        resolve_data_directory(tmp_path / relative)


def test_setup_refuses_a_reserved_destination_without_creating_it(tmp_path: Path) -> None:
    destination = tmp_path / ".data" / "graphs"
    report = prepare_local_system(data_directory=destination)
    assert not report.succeeded
    assert report.stage == SetupStage.RESOLVE_DESTINATION
    assert report.is_actionable_failure
    assert not destination.exists()


@pytest.mark.parametrize(
    "destination",
    ["~nosuchuser1234/vellis", "vellis\x00dir"],
    ids=["unknown-home", "embedded-nul"],
)
def test_an_unresolvable_path_is_an_actionable_failure_not_a_traceback(
    destination: str,
) -> None:
    """Excludes a bare exception where the model requires a stage and a next step.

    A mistyped ``~user`` and a NUL byte both raise from the standard library rather than
    from this project's own guard, so both have to be converted here.
    """
    with pytest.raises(DestinationError):
        resolve_data_directory(destination)

    report = prepare_local_system(data_directory=destination)
    assert not report.succeeded
    assert report.stage == SetupStage.RESOLVE_DESTINATION
    assert report.is_actionable_failure

    code, _, err = _run(["--data-dir", destination, "--dry-run"])
    assert code == EXIT_FAILED
    assert "what to do next:" in err


@pytest.mark.parametrize(
    "answer", ["", "\n", "maybe\n", "Y E S\n"], ids=["eof", "empty", "unrecognized", "spaced"]
)
def test_only_an_explicit_yes_proceeds(tmp_path: Path, answer: str) -> None:
    """Excludes a prompt that proceeds unless refused; --yes is the non-interactive path."""
    destination = tmp_path / "vellis"
    code, out, _ = _run(["--data-dir", str(destination)], answer=answer)
    assert code == EXIT_DECLINED
    assert "Declined" in out
    assert not store_path(destination.resolve()).exists()
