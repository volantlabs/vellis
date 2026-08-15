"""Evidence for the setup portion of ``VellisVerification::simpleOperation``.

The verification case is explicit that a generic failure does not pass: every failure
must name the stage that failed, state whether established memory changed, and offer an
available corrective action. ``SetupReport.is_actionable_failure`` is asserted for each
failure below so that a future regression toward a bare error message fails the suite.

Every case uses a temporary destination; none touches the platform default.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from tests.vellis.oracle import materialize_replay, materialize_state
from tests.vellis.semantic_state import semantic_state_equal
from vellis.activity import HistoryKind, HistoryQuery
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
    FreshVocabularyChoice,
    SetupReport,
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


def test_the_three_outcomes_an_agent_reads_stay_distinct() -> None:
    """The exit status is the whole of what a non-interactive caller can see."""
    assert (EXIT_SUCCESS, EXIT_FAILED, EXIT_DECLINED) == (0, 1, 3)


@pytest.mark.parametrize("missing", ["nothing", "the stage", "what happened", "what to do next"])
def test_a_failure_missing_any_part_of_its_minimum_is_not_actionable(missing: str) -> None:
    """The model says a failure without that minimum does not pass, so absence must show."""
    report = SetupReport(
        stage="" if missing == "the stage" else SetupStage.INITIALIZE,
        succeeded=False,
        memory_changed=False,
        summary="" if missing == "what happened" else "something went wrong",
        choice=FreshVocabularyChoice.BLANK,
        corrective_action=None if missing == "what to do next" else "try this",
    )

    assert report.is_actionable_failure == (missing == "nothing")


def test_a_success_is_not_an_actionable_failure() -> None:
    """Excludes a predicate that answers the question it was not asked."""
    report = SetupReport(
        stage=SetupStage.INITIALIZE,
        succeeded=True,
        memory_changed=True,
        summary="established revision 0",
        choice=FreshVocabularyChoice.BLANK,
        corrective_action="try this",
    )

    assert not report.is_actionable_failure


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
    # Stated rather than defaulted: this evidence is about the setup path, not about
    # which starting vocabulary the choice slice preselects.
    report = prepare_local_system(data_directory=destination, choice=FreshVocabularyChoice.BLANK)
    assert report.succeeded
    assert report.memory_changed
    assert report.revision == 0
    assert report.store == store_path(destination.resolve())
    assert report.store is not None and report.store.exists()

    system = RTGSystem.open(report.store)
    try:
        assert system.is_initialized
        assert materialize_state(system).revision == 0
        assert materialize_state(system).graph.is_empty
    finally:
        system.close()


def test_a_second_attempt_fails_actionably_and_leaves_memory_unchanged(tmp_path: Path) -> None:
    """Excludes a setup that re-seeds an established system or reports a bare error."""
    destination = tmp_path / "vellis"
    first = prepare_local_system(data_directory=destination, choice=FreshVocabularyChoice.BLANK)
    assert first.succeeded and first.store is not None

    system = RTGSystem.open(first.store)
    try:
        before = materialize_state(system)
    finally:
        system.close()

    second = prepare_local_system(data_directory=destination, choice=FreshVocabularyChoice.BLANK)
    assert not second.succeeded
    assert second.stage == SetupStage.INITIALIZE
    assert not second.memory_changed
    assert second.is_actionable_failure

    system = RTGSystem.open(first.store)
    try:
        assert semantic_state_equal(materialize_state(system), before)
        assert semantic_state_equal(materialize_replay(system), before)
        assert system.store.canonical_record_count() == 1
    finally:
        system.close()


def test_a_checkpoint_blocker_cannot_replace_a_second_start_report(tmp_path: Path) -> None:
    """Cleanup contention remains part of the staged, state-accurate setup outcome."""
    destination = tmp_path / "vellis"
    first = prepare_local_system(data_directory=destination, choice=FreshVocabularyChoice.BLANK)
    assert first.succeeded and first.store is not None

    reader = sqlite3.connect(first.store)
    writer = RTGSystem.open(first.store)
    try:
        reader.execute("BEGIN")
        assert reader.execute("SELECT revision FROM state_head WHERE id = 0").fetchone() == (0,)
        assert writer.history(HistoryQuery(kind=HistoryKind.CANONICAL, maximum_records=1)).accepted

        second = prepare_local_system(
            data_directory=destination, choice=FreshVocabularyChoice.BLANK
        )

        assert second.is_actionable_failure
        assert second.stage == SetupStage.INITIALIZE
        assert not second.memory_changed
        assert "already established" in second.summary
        assert "cleanup could not finish" in second.summary
        assert "use this system as it is" in (second.corrective_action or "")
        assert "close the other database reader" in (second.corrective_action or "")
    finally:
        reader.close()
        writer.close()

    RTGSystem.open(first.store).close()


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


def test_confirming_the_prompt_establishes_the_system(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    code, out, _ = _run(["--data-dir", str(destination), "--vocabulary", "blank"], answer="y\n")
    assert code == EXIT_SUCCESS
    assert "current revision: 0" in out
    assert store_path(destination.resolve()).exists()


def test_a_dry_run_stays_a_dry_run_when_the_confirmation_is_skipped(tmp_path: Path) -> None:
    """Excludes the one flag combination where a regression would establish silently."""
    destination = tmp_path / "vellis"
    code, out, _ = _run(["--data-dir", str(destination), "--dry-run", "--yes"])
    assert code == EXIT_SUCCESS
    assert "Dry run: nothing was created." in out
    assert not destination.exists()


@pytest.mark.parametrize("answer", ["y", "yes", "Y", "YES", " y \n"])
def test_every_way_of_saying_yes_proceeds(tmp_path: Path, answer: str) -> None:
    """The negatives are pinned below; what an owner may actually type is pinned here."""
    destination = tmp_path / "vellis"
    code, _, _ = _run(["--data-dir", str(destination)], answer=f"{answer}\n")
    assert code == EXIT_SUCCESS
    assert store_path(destination.resolve()).exists()


def test_a_destination_below_a_directory_that_does_not_exist_is_created(tmp_path: Path) -> None:
    destination = tmp_path / "one" / "two" / "vellis"
    code, _, _ = _run(["--data-dir", str(destination), "--yes", "--vocabulary", "blank"])
    assert code == EXIT_SUCCESS
    assert store_path(destination.resolve()).exists()


def test_a_failing_command_reports_stage_state_effect_and_next_step(tmp_path: Path) -> None:
    destination = tmp_path / "vellis"
    blank = ["--vocabulary", "blank"]
    assert _run(["--data-dir", str(destination), "--yes", *blank])[0] == EXIT_SUCCESS
    code, _, err = _run(["--data-dir", str(destination), "--yes", *blank])
    assert code == EXIT_FAILED
    # The command can tell before it prompts, so it says so at the stage that found out.
    assert f"stage: {SetupStage.PREVIEW}" in err
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


# --- Beginning from a canonical snapshot ----------------------------------------------


def _snapshot_document(tmp_path: Path, name: str = "snapshot.ndjson") -> Path:
    """Write one normalized streaming capture where an owner would bring it."""
    from tests.vellis.oracle import materialize_everyday_life
    from vellis.canonical import Provenance
    from vellis.changes import GraphChange
    from vellis.graph import Anchor
    from vellis.streaming import export_ndjson

    source_path = tmp_path / f"source-{name}.sqlite3"
    source = RTGSystem.open(source_path)
    try:
        owner = Provenance(initiator="owner")
        assert source.initialize_fresh(
            materialize_everyday_life(), provenance=owner, initialization_summary="a fresh start"
        ).accepted
        assert source.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "life.person", "Ada"),)), provenance=owner
        ).accepted
        document = tmp_path / name
        with document.open("w", encoding="utf-8") as output:
            export_ndjson(source_path, output)
        return document
    finally:
        source.close()


@pytest.mark.parametrize(
    "extra",
    [["--vocabulary", "blank"], ["--vocabulary", "everydayLifeStarter"]],
    ids=["blank", "starter"],
)
def test_a_starting_vocabulary_beside_a_snapshot_is_refused_not_ignored(
    tmp_path: Path, extra: list[str]
) -> None:
    """A snapshot answers the vocabulary question; accepting both would silently pick one."""
    document = _snapshot_document(tmp_path)
    with pytest.raises(SystemExit):
        _run(["--data-dir", str(tmp_path / "new"), "--from-snapshot", str(document), *extra])


def test_two_starting_inputs_are_refused(tmp_path: Path) -> None:
    """Excludes the option order deciding which memory an owner ends up with."""
    document = _snapshot_document(tmp_path)
    with pytest.raises(SystemExit):
        _run(
            [
                "--data-dir",
                str(tmp_path / "new"),
                "--from-snapshot",
                str(document),
                "--from-v1",
                str(document),
            ]
        )


def test_a_file_that_is_not_a_snapshot_stream_is_an_actionable_failure(tmp_path: Path) -> None:
    not_one = tmp_path / "notes.ndjson"
    not_one.write_text('{"hello": "world"}', encoding="utf-8")

    code, _, err = _run(
        ["--data-dir", str(tmp_path / "new"), "--from-snapshot", str(not_one), "--yes"]
    )

    assert code == EXIT_FAILED
    assert "what to do next:" in err
    assert "--from-snapshot" in err
    assert not (tmp_path / "new").exists()


def test_a_snapshot_that_changed_after_preview_is_not_the_one_confirmed(tmp_path: Path) -> None:
    """The owner agreed to one exact reconstructed state, not to whatever the file holds.

    Confirming re-reads the document, so a file rewritten between the preview and the
    answer is a different start that nobody has seen.
    """
    document = _snapshot_document(tmp_path)
    replacement = _snapshot_document(tmp_path, name="other.ndjson")
    destination = tmp_path / "new"

    stdout, stderr = io.StringIO(), io.StringIO()

    class _SwapOnRead(io.StringIO):
        """Answers yes, and rewrites the document while the owner is answering."""

        def readline(self, size: int = -1) -> str:
            document.write_text(replacement.read_text(encoding="utf-8"), encoding="utf-8")
            return "y\n"

    code = main(
        ["--data-dir", str(destination), "--from-snapshot", str(document)],
        stdout=stdout,
        stderr=stderr,
        stdin=_SwapOnRead(),
    )

    assert code == EXIT_FAILED
    assert "the snapshot changed after it was previewed" in stderr.getvalue()
    assert not store_path(destination.resolve()).exists()


def test_the_published_import_is_bound_to_the_confirmed_snapshot_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import vellis.setup as setup

    document = _snapshot_document(tmp_path)
    replacement = _snapshot_document(tmp_path, name="replacement.ndjson")
    destination = tmp_path / "new"
    original = setup.import_ndjson
    calls = 0

    def replace_before_publication(*args: object, **kwargs: object) -> object:
        nonlocal calls
        calls += 1
        if calls == 3:
            document.write_text(replacement.read_text(encoding="utf-8"), encoding="utf-8")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(setup, "import_ndjson", replace_before_publication)
    code, _out, error = _run(
        ["--data-dir", str(destination), "--from-snapshot", str(document), "--yes"]
    )
    assert code == EXIT_FAILED
    assert "confirmed input" in error
    assert not store_path(destination.resolve()).exists()


def test_a_normalized_snapshot_initializes_the_selected_destination(tmp_path: Path) -> None:
    document = _snapshot_document(tmp_path)
    destination = tmp_path / "new"

    code, out, err = _run(
        ["--data-dir", str(destination), "--from-snapshot", str(document), "--yes"]
    )

    assert code == EXIT_SUCCESS, err
    assert "normalized Vellis snapshot" in out
    system = RTGSystem.open(store_path(destination.resolve()))
    try:
        assert system.store.current_revision() == 1
    finally:
        system.close()


def test_a_normalized_snapshot_plus_contiguous_tail_initializes_the_later_state(
    tmp_path: Path,
) -> None:
    from vellis.canonical import Provenance
    from vellis.changes import GraphChange
    from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
    from vellis.graph import Anchor
    from vellis.streaming import export_ndjson, export_tail_ndjson

    source_path = tmp_path / "source.sqlite3"
    snapshot = tmp_path / "snapshot.ndjson"
    tail = tmp_path / "tail.ndjson"
    source = RTGSystem.open(source_path)
    try:
        owner = Provenance("owner")
        assert source.initialize_fresh(
            GraphDefinitionSet(anchor_types=(AnchorTypeDefinition("person", "A person."),)),
            provenance=owner,
            initialization_summary="fresh",
        ).accepted
        with snapshot.open("w", encoding="utf-8") as output:
            captured = export_ndjson(source_path, output)
        assert source.apply_graph_change(
            GraphChange(anchor_upserts=(Anchor("a-1", "person", "Ada"),)),
            provenance=owner,
        ).accepted
        with tail.open("w", encoding="utf-8") as output:
            export_tail_ndjson(
                source_path,
                output,
                after_revision=captured.revision,
                after_record_identity=captured.record_identity,
            )
    finally:
        source.close()

    destination = tmp_path / "new"
    code, _out, error = _run(
        [
            "--data-dir",
            str(destination),
            "--from-snapshot",
            str(snapshot),
            "--tail",
            str(tail),
            "--yes",
        ]
    )
    assert code == EXIT_SUCCESS, error
    imported = RTGSystem.open(store_path(destination.resolve()))
    try:
        assert imported.store.current_revision() == 1
        assert materialize_state(imported).graph.anchor("a-1") is not None
    finally:
        imported.close()
