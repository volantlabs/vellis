"""Evidence for the confirmed first-use vocabulary choice.

Carries the part of ``VellisVerification::everydayLifeStart`` this slice reaches: blank
and Everyday Life are the complete choice set, Everyday Life is recommended and
preselected, neither is established until the owner confirms, each establishes exactly its
own definition set, and neither creates graph objects.

Asking what a destination already holds means setup can now fail before it prompts, so the
cases below also show that failure conforming to obligations ``simpleIndividualOperation``
already carries: a destination setup cannot use is named, staged, and given a way out that
suits whose file it is. That is conformance to an obligation another slice covers, not new
coverage of it.

Where an assertion is about what the offer says, it reads the offer block rather than the
whole transcript, because a temporary directory's own path can contain the word being
looked for and would satisfy a naive substring check no matter what the offer said. Each
choice is checked against both vocabularies — the one it must establish and the one it
must not — so that a mapping which swapped them could not pass.
"""

from __future__ import annotations

import io
import sqlite3
from pathlib import Path

import pytest

from vellis.canonical import CanonicalState, Provenance
from vellis.definitions import GraphDefinitionSet, definition_set_equal
from vellis.everyday_life import everyday_life_starter
from vellis.paths import store_path
from vellis.setup import (
    EXIT_DECLINED,
    EXIT_FAILED,
    EXIT_SUCCESS,
    FreshVocabularyChoice,
    SetupStage,
    main,
    prepare_local_system,
)
from vellis.store import (
    APPLICATION_ID,
    CanonicalStore,
    ForeignDatabaseError,
    NotADatabaseError,
    StoreError,
    UnreadableStoreError,
    holds_established_memory,
)
from vellis.system import RTGSystem

BLANK = FreshVocabularyChoice.BLANK
STARTER = FreshVocabularyChoice.EVERYDAY_LIFE_STARTER
EXIT_USAGE = 2


def _confirmed_run(argv: list[str], answer: str = "y\n") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err, stdin=io.StringIO(answer))
    return code, out.getvalue(), err.getvalue()


def _offer(output: str) -> list[str]:
    """Return the offered lines, which are the only place the choice set is stated."""
    lines = output.splitlines()
    assert "  starting vocabulary:" in lines, output
    start = lines.index("  starting vocabulary:")
    return [line for line in lines[start + 1 :] if line.startswith("    [")]


def _selected(output: str) -> str:
    marked = [line for line in _offer(output) if "[x]" in line]
    assert len(marked) == 1, output
    return marked[0]


def _state_of(store: Path | None) -> CanonicalState:
    assert store is not None
    system = RTGSystem.open(store)
    try:
        return system.current_state()
    finally:
        system.close()


def _state(destination: Path) -> CanonicalState:
    return _state_of(store_path(destination.resolve()))


# --- The complete choice set --------------------------------------------------------


def test_the_choice_set_is_exactly_the_modeled_pair() -> None:
    """``Vellis::'Fresh Vocabulary Choice'`` declares two values and no others."""
    assert [each.value for each in FreshVocabularyChoice] == ["blank", "everydayLifeStarter"]


def test_an_unmodeled_vocabulary_is_refused(tmp_path: Path) -> None:
    destination = tmp_path / "v"

    with pytest.raises(SystemExit) as refusal:
        _confirmed_run(["--data-dir", str(destination), "--vocabulary", "somethingElse"])

    assert refusal.value.code == EXIT_USAGE
    assert not destination.exists()


def test_the_preview_says_what_it_will_do_and_where(tmp_path: Path) -> None:
    """An owner confirms what they were shown, so all of it has to be there."""
    destination = tmp_path / "v"

    _, out, _ = _confirmed_run(["--data-dir", str(destination), "--dry-run"])

    assert out.splitlines()[:3] == [
        "Vellis setup will prepare one local personal system.",
        f"  destination:  {destination.resolve()}",
        f"  memory store: {store_path(destination.resolve())}",
    ]
    assert "  nothing outside that directory is read or changed." in out.splitlines()


def test_the_offer_names_both_choices_and_preselects_the_recommendation(tmp_path: Path) -> None:
    """Excludes presenting the recommendation as the only vocabulary there is."""
    _, out, _ = _confirmed_run(["--data-dir", str(tmp_path / "v"), "--dry-run"])

    assert _offer(out) == [
        "    [ ] blank (an empty definition set) - to choose it, pass --vocabulary blank",
        "    [x] Everyday Life (a starter vocabulary of everyday things) - recommended",
    ]


def test_the_offer_marks_the_requested_alternative(tmp_path: Path) -> None:
    """Excludes a preview that reports the recommendation whatever was asked for, and
    excludes marking whatever was selected as the recommended one: the mark moves, the
    recommendation does not, and the way back to it is named."""
    _, out, _ = _confirmed_run(
        ["--data-dir", str(tmp_path / "v"), "--dry-run", "--vocabulary", "blank"]
    )

    assert _offer(out) == [
        "    [x] blank (an empty definition set)",
        "    [ ] Everyday Life (a starter vocabulary of everyday things) - recommended"
        " - to choose it, pass --vocabulary everydayLifeStarter",
    ]


def test_the_offer_is_shown_before_the_noninteractive_path_establishes(tmp_path: Path) -> None:
    """--yes confirms what was previewed; an owner who sees nothing confirms nothing."""
    _, out, _ = _confirmed_run(["--data-dir", str(tmp_path / "v"), "--yes"])

    assert len(_offer(out)) == 2
    assert out.index("  starting vocabulary:") < out.index("established revision 0")


class _RecordingStream(io.StringIO):
    """A stream that remembers what had been flushed by the time it was read from."""

    def __init__(self) -> None:
        super().__init__()
        self.flushed = ""

    def flush(self) -> None:
        self.flushed = self.getvalue()


def test_the_prompt_reaches_the_owner_before_the_answer_is_read(tmp_path: Path) -> None:
    """A prompt that ends without a newline sits in the buffer until something flushes it.

    Excludes a command that looks to its owner as though it has stopped, at the one moment
    the model requires them to say yes.
    """
    out = _RecordingStream()
    main(
        ["--data-dir", str(tmp_path / "v")],
        stdout=out,
        stderr=io.StringIO(),
        stdin=io.StringIO("n\n"),
    )

    assert out.flushed.endswith("Proceed? [y/N] ")


def test_the_offer_precedes_the_confirmation_on_the_path_that_establishes(tmp_path: Path) -> None:
    """Excludes an offer that only ever appears under --dry-run."""
    code, out, _ = _confirmed_run(["--data-dir", str(tmp_path / "v")], answer="n\n")

    assert code == EXIT_DECLINED
    assert len(_offer(out)) == 2
    assert out.index("  starting vocabulary:") < out.index("Proceed?")


# --- Confirmation ------------------------------------------------------------------


@pytest.mark.parametrize("choice", list(FreshVocabularyChoice))
def test_nothing_is_established_until_the_owner_confirms(
    tmp_path: Path, choice: FreshVocabularyChoice
) -> None:
    """Excludes acting on the recommendation instead of offering it."""
    destination = tmp_path / "v"

    code, out, _ = _confirmed_run(
        ["--data-dir", str(destination), "--vocabulary", choice.value], answer="n\n"
    )

    assert code == EXIT_DECLINED
    assert "Declined" in out
    assert not destination.exists()
    assert not store_path(destination.resolve()).exists()


def test_the_confirmed_recommendation_establishes_the_starter(tmp_path: Path) -> None:
    """The whole path: the argparse default, the prompt, and the state on disk."""
    destination = tmp_path / "v"

    code, out, err = _confirmed_run(["--data-dir", str(destination)])

    assert code == EXIT_SUCCESS, err
    assert definition_set_equal(_state(destination).active_definitions, everyday_life_starter())
    assert "current revision: 0" in out
    # An owner is told what they now have, not only that something happened.
    assert "12 anchor types" in out


def test_the_confirmed_alternative_establishes_nothing_but_an_empty_vocabulary(
    tmp_path: Path,
) -> None:
    """Excludes handing an owner who asked for blank a vocabulary to undo."""
    destination = tmp_path / "v"

    code, out, err = _confirmed_run(["--data-dir", str(destination), "--vocabulary", "blank"])

    assert code == EXIT_SUCCESS, err
    assert "0 anchor types" in out
    active = _state(destination).active_definitions
    assert definition_set_equal(active, GraphDefinitionSet())
    assert not definition_set_equal(active, everyday_life_starter())


def test_the_programmatic_default_is_the_recommendation(tmp_path: Path) -> None:
    """The preselection is the default wherever a caller does not state a choice."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"))

    assert report.succeeded, report.summary
    assert report.choice is STARTER
    assert definition_set_equal(_state_of(report.store).active_definitions, everyday_life_starter())


def test_a_successful_report_names_the_choice_it_established(tmp_path: Path) -> None:
    """Excludes a report that always says the recommendation, whatever it started."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)

    assert report.succeeded, report.summary
    assert report.choice is BLANK


@pytest.mark.parametrize("choice", list(FreshVocabularyChoice))
def test_the_record_says_which_vocabulary_was_started(
    tmp_path: Path, choice: FreshVocabularyChoice
) -> None:
    """The report is transient; the initial record is the durable statement."""
    expected = {
        BLANK: "blank first-use start with an empty definition set",
        STARTER: "first-use start with the Everyday Life starter vocabulary",
    }[choice]
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=choice)

    assert report.succeeded, report.summary
    assert report.store is not None
    system = RTGSystem.open(report.store)
    try:
        summary: str = system.initial_record().initialization_summary
    finally:
        system.close()
    assert summary == expected
    # The recommendation is a stance while offering, not a fact about what was started,
    # so the durable sentence is not the one the offer shows.
    assert "recommended" not in summary
    assert summary != choice.description


@pytest.mark.parametrize("choice", list(FreshVocabularyChoice))
def test_either_choice_leaves_one_fresh_canonical_base(
    tmp_path: Path, choice: FreshVocabularyChoice
) -> None:
    """A vocabulary is a way of saying things, not something already said.

    A starting vocabulary is active state, not a proposal and not a transition: a start
    that staged it would leave the owner a decision they never made.
    """
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=choice)

    assert report.succeeded, report.summary
    assert report.store is not None
    system = RTGSystem.open(report.store)
    try:
        state = system.current_state()
        assert state.graph.is_empty
        assert state.revision == 0
        assert state.definition_delta is None
        assert system.store.canonical_record_count() == 1
        assert system.store.activity_record_count() == 0
    finally:
        system.close()


# --- An established system is offered nothing ----------------------------------------


@pytest.mark.parametrize("interruption", ["before the schema was written", "after it was written"])
def test_an_interrupted_first_attempt_is_still_a_beginning(
    tmp_path: Path, interruption: str
) -> None:
    """A store file is not a memory: an owner who has nothing yet is still choosing.

    Excludes a check that asks whether a file is there rather than whether anything was
    ever established — which would tell this owner setup cannot start, and then start it
    with a vocabulary they were never offered. Setup creates the file before it writes
    the schema, so an interruption can leave either form behind.
    """
    destination = tmp_path / "v"
    destination.mkdir()
    if interruption == "before the schema was written":
        store_path(destination).touch()
    else:
        CanonicalStore(store_path(destination)).close()

    code, out, _ = _confirmed_run(["--data-dir", str(destination)], answer="n\n")

    assert code == EXIT_DECLINED
    assert len(_offer(out)) == 2
    assert "already holds memory" not in out
    assert "cannot be used" not in out


def test_a_destination_whose_path_reads_as_uri_punctuation_is_answered_for(
    tmp_path: Path,
) -> None:
    """Excludes probing some other path because this one contains a '?' or a '#'."""
    destination = tmp_path / "wh?at#now"
    assert (
        _confirmed_run(["--data-dir", str(destination), "--vocabulary", "blank"])[0] == EXIT_SUCCESS
    )

    assert holds_established_memory(store_path(destination.resolve()))
    code, out, _ = _confirmed_run(["--data-dir", str(destination)], answer="n\n")

    assert code == EXIT_FAILED
    assert "already holds memory" in out
    assert sorted(each.name for each in destination.iterdir()) == ["vellis.sqlite3"]


def test_a_destination_that_belongs_to_something_else_is_neither(tmp_path: Path) -> None:
    """Saying which it was is more use than either answer it is not."""
    destination = tmp_path / "v"
    destination.mkdir()
    connection = sqlite3.connect(store_path(destination))
    try:
        connection.execute("CREATE TABLE somebody_elses (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    code, out, err = _confirmed_run(["--data-dir", str(destination)], answer="n\n")

    assert code == EXIT_FAILED
    assert "cannot be used" in out
    assert "already holds memory" not in out
    assert "  starting vocabulary:" not in out
    # Setup knows the way out here, so it says so rather than asking to proceed and
    # ending in the general store-open failure, whose advice would not help.
    assert "Proceed?" not in out
    assert f"stage: {SetupStage.PREVIEW}" in err
    assert "what happened: this destination cannot be used" in err
    assert "established memory: unchanged" in err
    assert "--data-dir" in err


def test_a_store_damaged_below_its_header_is_an_actionable_failure(tmp_path: Path) -> None:
    """The last shape of damage that could still leave a bare traceback where a report was
    promised: a file that opens as a database and then cannot be read."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    damaged = bytearray(report.store.read_bytes())
    damaged[100:400] = b"\x00" * 300
    report.store.write_bytes(bytes(damaged))

    with pytest.raises(StoreError):
        holds_established_memory(report.store)

    code, _, err = _confirmed_run(["--data-dir", str(report.store.parent), "--yes"])

    assert code == EXIT_FAILED
    assert f"stage: {SetupStage.INITIALIZE}" in err
    assert "established memory: unchanged" in err
    assert "read and write" in err


@pytest.mark.parametrize(
    "kind", ["a file that is not a database", "a destination that cannot be prepared"]
)
def test_a_failed_report_names_the_destination_it_tried(tmp_path: Path, kind: str) -> None:
    """A caller telling its own user what went wrong needs to know which file that was."""
    if kind == "a file that is not a database":
        destination = tmp_path / "v"
        destination.mkdir()
        store_path(destination).write_text("not a database\n", encoding="utf-8")
    else:
        blocker = tmp_path / "file"
        blocker.write_text("not a directory\n", encoding="utf-8")
        destination = blocker / "v"

    report = prepare_local_system(data_directory=str(destination), choice=BLANK)

    assert not report.succeeded
    assert report.destination == destination.resolve()
    assert report.store == store_path(destination.resolve())
    if kind == "a file that is not a database":
        # The same reading the documented command gives, from the same classification.
        assert "move or rename it" in (report.corrective_action or "")


def test_a_file_that_is_not_a_database_is_an_actionable_failure(tmp_path: Path) -> None:
    """Told apart from a store this attempt could not open, which is a different answer."""
    destination = tmp_path / "v"
    destination.mkdir()
    store_path(destination).write_bytes(b"SQLite format 3 but not really" + b"\x00" * 64)

    code, out, err = _confirmed_run(["--data-dir", str(destination), "--dry-run"])

    assert code == EXIT_FAILED
    assert "is not a database" in out
    assert "  starting vocabulary:" not in out
    # Whose file it is was never established, so neither answer about ownership is given.
    assert "move or rename it" in err
    assert "empty or holds a Vellis system" not in err
    assert "leave this system where it is" not in err


def test_a_destination_this_cannot_read_is_left_to_the_operation(tmp_path: Path) -> None:
    """Not being able to read something is not a statement about what it is.

    The preview says nothing, the offer stands, and the operation — which opens the file
    properly — refuses with the advice that fits what it found.
    """
    destination = tmp_path / "v"
    destination.mkdir()
    store_path(destination).mkdir()

    code, out, err = _confirmed_run(["--data-dir", str(destination)], answer="n\n")

    assert code == EXIT_DECLINED
    assert len(_offer(out)) == 2

    report = prepare_local_system(data_directory=str(destination), choice=BLANK)

    assert report.stage == SetupStage.INITIALIZE
    assert report.is_actionable_failure
    assert not report.memory_changed
    assert report.choice is BLANK
    advice = report.corrective_action or ""
    assert f"read and write {destination} and everything in it" in advice
    assert "vellis.sqlite3" not in advice


def test_previewing_a_destination_that_holds_a_store_changes_nothing(tmp_path: Path) -> None:
    """Reading what is there to preview it may not leave anything behind."""
    destination = tmp_path / "v"
    assert (
        _confirmed_run(["--data-dir", str(destination), "--vocabulary", "blank"])[0] == EXIT_SUCCESS
    )
    before = sorted(each.name for each in destination.iterdir())

    code, out, err = _confirmed_run(["--data-dir", str(destination), "--dry-run"])

    assert code == EXIT_FAILED
    assert out.splitlines() == [
        "Vellis setup cannot prepare a system here.",
        f"  destination:  {destination.resolve()}",
        f"  memory store: {store_path(destination.resolve())}",
        "  this destination already holds memory; setup cannot start it again.",
        "  nothing outside that directory is read or changed.",
    ]
    assert "use this system as it is" in err
    assert sorted(each.name for each in destination.iterdir()) == before


def test_previewing_an_existing_but_empty_destination_creates_no_store(tmp_path: Path) -> None:
    destination = tmp_path / "v"
    destination.mkdir()

    code, _, _ = _confirmed_run(["--data-dir", str(destination), "--dry-run"])

    assert code == EXIT_SUCCESS
    assert list(destination.iterdir()) == []


# --- What the store says about a path ------------------------------------------------


def test_an_established_store_holds_memory_and_keeps_its_bytes(tmp_path: Path) -> None:
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    before = sorted(each.name for each in report.store.parent.iterdir())
    contents = report.store.read_bytes()

    assert holds_established_memory(report.store)
    assert sorted(each.name for each in report.store.parent.iterdir()) == before
    assert report.store.read_bytes() == contents


def test_a_start_left_in_the_log_is_refused_by_the_operation(tmp_path: Path) -> None:
    """What a preview cannot see without writing, the operation sees and refuses.

    An immutable read cannot follow a write-ahead log, so a system whose commits are still
    in one reads as empty and the offer is made. Nothing is established: the operation
    opens the file properly, finds the memory, and says so.
    """
    destination = tmp_path / "v"
    destination.mkdir()
    store = store_path(destination)
    # Held open, so the log is never checkpointed and the memory lives only in it.
    keeper = CanonicalStore(store)
    try:
        RTGSystem(keeper).initialize_fresh(
            GraphDefinitionSet(),
            provenance=Provenance(initiator="owner"),
            initialization_summary=BLANK.established_summary,
        )
        assert store.with_name(store.name + "-wal").stat().st_size > 0
        assert not holds_established_memory(store)

        code, out, err = _confirmed_run(["--data-dir", str(destination), "--yes"])
    finally:
        keeper.close()

    assert code == EXIT_FAILED
    assert len(_offer(out)) == 2
    assert f"stage: {SetupStage.INITIALIZE}" in err
    assert "already established" in err
    assert "use this system as it is" in err


def test_a_second_reader_does_not_change_the_answer(tmp_path: Path) -> None:
    """Another connection being open is not a different state of the memory."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    reader = CanonicalStore(report.store)
    try:
        assert holds_established_memory(report.store)
    finally:
        reader.close()
    assert definition_set_equal(_state_of(report.store).active_definitions, GraphDefinitionSet())


def test_a_store_that_vanishes_after_the_check_is_not_created_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The connection refuses to create, not only the guard in front of it.

    Nothing else stands between a preview and a stray empty database at a destination the
    owner was only looking at.
    """
    absent = tmp_path / "vellis.sqlite3"
    monkeypatch.setattr(Path, "exists", lambda self: True)

    with pytest.raises(StoreError):
        holds_established_memory(absent)

    assert list(tmp_path.iterdir()) == []


def test_a_store_missing_the_table_that_says_what_it_is_still_belongs_to_its_owner(
    tmp_path: Path,
) -> None:
    """Our own marker over our own tables is a store with a piece missing, not a stranger.

    Excludes the one reading that would enumerate an owner's ledger as evidence the file
    is somebody else's and then send them somewhere else to start again.
    """
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    connection = sqlite3.connect(report.store)
    try:
        connection.execute("DROP TABLE schema_meta")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(UnreadableStoreError):
        holds_established_memory(report.store)

    code, _, err = _confirmed_run(["--data-dir", str(report.store.parent), "--dry-run"])

    assert code == EXIT_FAILED
    assert "leave this system where it is" in err
    assert "choose a different" not in err


def test_a_store_that_does_not_say_which_schema_it_is_is_not_assumed_to_be_this_one(
    tmp_path: Path,
) -> None:
    """A version that was never written is not this version, and saying so is not a crash."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    connection = sqlite3.connect(report.store)
    try:
        connection.execute("DELETE FROM schema_meta WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(UnreadableStoreError, match="schema version none"):
        holds_established_memory(report.store)

    code, _, err = _confirmed_run(["--data-dir", str(report.store.parent), "--yes"])

    assert code == EXIT_FAILED
    assert f"stage: {SetupStage.PREVIEW}" in err
    assert "leave this system where it is" in err


def test_a_store_written_by_a_later_build_is_still_this_owner_s(tmp_path: Path) -> None:
    """The case the class exists for, said through the command an owner runs."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    connection = sqlite3.connect(report.store)
    try:
        connection.execute("UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(UnreadableStoreError, match="schema version 3"):
        holds_established_memory(report.store)

    code, out, err = _confirmed_run(["--data-dir", str(report.store.parent), "--dry-run"])

    assert code == EXIT_FAILED
    assert "schema version 3" in out
    assert "  starting vocabulary:" not in out
    assert "leave this system where it is" in err


def test_a_store_this_cannot_reach_answers_nothing_rather_than_no(tmp_path: Path) -> None:
    """A path with no file is not opened, and answers for itself."""
    assert not holds_established_memory(tmp_path / "absent.sqlite3")


@pytest.mark.parametrize(
    "table", ["canonical_record", "activity_record", "current_state", "ledger"]
)
def test_a_store_missing_one_of_its_tables_still_belongs_to_its_owner(
    tmp_path: Path, table: str
) -> None:
    """The other way a Vellis store can be unreadable, and the programmatic path.

    Each table is named separately because the screen is only as good as its narrowest
    omission: a store missing any one of them is unreadable, not somebody else's.
    """
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    connection = sqlite3.connect(report.store)
    try:
        connection.execute(f"DROP TABLE {table}")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(UnreadableStoreError):
        holds_established_memory(report.store)

    # The programmatic path answers the same way the documented command does.
    again = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert again.is_actionable_failure
    assert "leave this system where it is" in (again.corrective_action or "")


def test_a_store_in_a_directory_this_account_cannot_write_still_says_what_it_holds(
    tmp_path: Path,
) -> None:
    """Reading a system may not depend on being allowed to add to the directory it is in."""
    import os

    if os.geteuid() == 0:  # pragma: no cover - the root account may write it anyway
        pytest.skip("root can write a directory nobody else may write")
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)
    assert report.store is not None
    directory = report.store.parent
    directory.chmod(0o500)
    try:
        assert holds_established_memory(report.store)

        code, out, err = _confirmed_run(["--data-dir", str(directory), "--dry-run"])
    finally:
        directory.chmod(0o700)

    assert code == EXIT_FAILED
    assert "already holds memory" in out
    assert "use this system as it is" in err


def test_a_store_another_process_is_writing_does_not_block_a_beginning(tmp_path: Path) -> None:
    """A log left open by something else is not this owner's answer, and not their wall.

    Excludes a preview that refuses a start on evidence it could not read, which would
    leave an owner whose first attempt was interrupted with no way forward at all.
    """
    destination = tmp_path / "v"
    destination.mkdir()
    store = store_path(destination)
    CanonicalStore(store).close()
    writer = sqlite3.connect(store)
    try:
        writer.execute("PRAGMA journal_mode = WAL")
        writer.execute("INSERT INTO activity_record (recorded_at, payload) VALUES ('x', 'y')")
        writer.commit()

        code, out, err = _confirmed_run(["--data-dir", str(destination)])
    finally:
        writer.close()

    assert code == EXIT_SUCCESS, err
    assert len(_offer(out)) == 2
    assert definition_set_equal(_state(destination).active_definitions, everyday_life_starter())


def test_a_file_carrying_our_own_marker_and_nothing_else_is_a_beginning(tmp_path: Path) -> None:
    """A first attempt can set the marker and stop before the schema; that is still ours."""
    destination = tmp_path / "v"
    destination.mkdir()
    connection = sqlite3.connect(store_path(destination))
    try:
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.commit()
    finally:
        connection.close()

    assert not holds_established_memory(store_path(destination))

    code, out, _ = _confirmed_run(["--data-dir", str(destination)], answer="n\n")

    assert code == EXIT_DECLINED
    assert len(_offer(out)) == 2


def test_a_database_belonging_to_another_application_is_refused_before_the_offer(
    tmp_path: Path,
) -> None:
    """The marker another application wrote is the plainest statement that this is not ours.

    Excludes offering a starting vocabulary at a stranger's database, and excludes the
    advice that assumes a Vellis build somewhere could read it.
    """
    destination = tmp_path / "v"
    destination.mkdir()
    connection = sqlite3.connect(store_path(destination))
    try:
        connection.execute("PRAGMA application_id = 196078063")
        connection.execute("CREATE TABLE theirs (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ForeignDatabaseError, match="belongs to another application"):
        holds_established_memory(store_path(destination))

    code, out, err = _confirmed_run(["--data-dir", str(destination), "--yes"])

    assert code == EXIT_FAILED
    assert "  starting vocabulary:" not in out
    assert f"stage: {SetupStage.PREVIEW}" in err
    assert "empty or holds a Vellis system" in err


def test_a_file_that_stops_partway_through_the_header_is_not_a_database(
    tmp_path: Path,
) -> None:
    """A truncated copy begins like a database and is not one."""
    destination = tmp_path / "v"
    destination.mkdir()
    store_path(destination).write_bytes(b"SQLite format 3")

    code, out, err = _confirmed_run(["--data-dir", str(destination), "--dry-run"])

    assert code == EXIT_FAILED
    assert "is not a database" in out
    assert "  starting vocabulary:" not in out
    assert "move or rename it" in err


def test_a_database_that_only_looks_like_ours_is_still_not_ours(tmp_path: Path) -> None:
    """A stranger's ``schema_meta`` is not a Vellis system, and its owner is not ours.

    Excludes sending someone whose file was never Vellis off to find a Vellis build that
    would read it, which is no way out at all.
    """
    destination = tmp_path / "v"
    destination.mkdir()
    connection = sqlite3.connect(store_path(destination))
    try:
        connection.execute("CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ForeignDatabaseError):
        holds_established_memory(store_path(destination))

    code, _, err = _confirmed_run(["--data-dir", str(destination), "--dry-run"])

    assert code == EXIT_FAILED
    assert "empty or holds a Vellis system" in err
    assert "leave this system where it is" not in err


def test_an_established_system_keeps_the_vocabulary_it_has(tmp_path: Path) -> None:
    """No separate starter-install path arrives with the choice."""
    destination = tmp_path / "v"
    assert (
        _confirmed_run(["--data-dir", str(destination), "--vocabulary", "blank"])[0] == EXIT_SUCCESS
    )
    before = _state(destination)

    code, out, err = _confirmed_run(["--data-dir", str(destination), "--yes"])

    assert code == EXIT_FAILED
    assert "already holds memory" in err
    # --yes is the agent path, so it is the one where a false offer would be acted on.
    assert "  starting vocabulary:" not in out
    assert "Everyday Life" not in out
    after = _state(destination)
    assert after.revision == before.revision
    assert definition_set_equal(after.active_definitions, GraphDefinitionSet())


# --- What the report says ----------------------------------------------------------


def test_a_second_start_is_told_to_keep_the_system_it_has(tmp_path: Path) -> None:
    """Excludes advice that would have an owner clear the way for a fresh start."""
    destination = str(tmp_path / "v")
    assert prepare_local_system(data_directory=destination, choice=BLANK).succeeded

    report = prepare_local_system(data_directory=destination, choice=BLANK)

    assert report.is_actionable_failure
    assert report.revision == 0
    assert report.corrective_action == (
        "use this system as it is, or pass a different --data-dir for a separate system"
    )


def test_a_refusal_survives_a_reading_that_does_not(tmp_path: Path) -> None:
    """One unreadable number may not turn 'you already have one' into 'you have none'."""
    destination = str(tmp_path / "v")
    first = prepare_local_system(data_directory=destination, choice=BLANK)
    assert first.succeeded and first.store is not None
    connection = sqlite3.connect(first.store)
    try:
        connection.execute("UPDATE current_state SET state = '{not json' WHERE id = 0")
        connection.commit()
    finally:
        connection.close()

    report = prepare_local_system(data_directory=destination, choice=BLANK)

    assert not report.succeeded
    assert report.stage == SetupStage.INITIALIZE
    assert report.revision is None
    assert "use this system as it is" in (report.corrective_action or "")


@pytest.mark.parametrize("refusal", ["the store refuses to write", "the record cannot be stored"])
def test_a_start_that_did_not_happen_is_not_reported_as_one_that_did(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: str
) -> None:
    """Nothing was established, so the way out may not be 'use the system you have'."""
    initiator = "owner"
    if refusal == "the store refuses to write":

        def fails(*arguments: object, **keywords: object) -> None:
            raise StoreError("the disk filled up")

        monkeypatch.setattr(CanonicalStore, "initialize", fails)
    else:
        # A lone surrogate cannot be encoded, so the record's own text cannot be stored.
        initiator = "owner\ud800"

    report = prepare_local_system(
        data_directory=str(tmp_path / "v"), choice=BLANK, initiator=initiator
    )

    assert not report.succeeded
    assert report.stage == SetupStage.INITIALIZE
    assert not report.memory_changed
    assert report.revision is None
    assert report.is_actionable_failure
    assert report.choice is BLANK
    action = report.corrective_action or ""
    assert "remove nothing" in action
    assert "use this system as it is" not in action


def test_the_two_refusals_are_not_each_other() -> None:
    """The whole triage rests on these being different answers, so they may not nest."""
    refusals = (ForeignDatabaseError, NotADatabaseError, UnreadableStoreError)
    for one in refusals:
        for other in refusals:
            assert (one is other) == issubclass(one, other)


def test_the_initial_record_says_where_it_came_from(tmp_path: Path) -> None:
    """A record outlives the run that made it, so it names the path that made it."""
    report = prepare_local_system(data_directory=str(tmp_path / "v"), choice=BLANK)

    assert report.store is not None
    system = RTGSystem.open(report.store)
    try:
        provenance = system.initial_record().provenance
    finally:
        system.close()
    assert provenance.initiator == "owner"
    assert provenance.source == "vellis setup"


@pytest.mark.parametrize("stage", [SetupStage.RESOLVE_DESTINATION, SetupStage.PREPARE_DESTINATION])
def test_a_failed_report_still_names_the_requested_choice(tmp_path: Path, stage: str) -> None:
    """Excludes a report that substitutes the recommendation for an absent value."""
    choice = BLANK
    if stage == SetupStage.RESOLVE_DESTINATION:
        destination = tmp_path / ".data"
    else:
        blocker = tmp_path / "file"
        blocker.write_text("not a directory\n", encoding="utf-8")
        destination = blocker / "v"

    report = prepare_local_system(data_directory=str(destination), choice=choice)

    assert not report.succeeded
    assert report.stage == stage
    assert report.choice is choice
