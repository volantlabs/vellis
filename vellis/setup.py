"""The documented setup path for one local Vellis system.

Supports ``Vellis::'Begin using one personal Vellis system'`` and
``VellisRequirements::simpleIndividualOperation``: one owner previews what setup will
do, confirms it, and gets either an established local system or a failure that names
the stage that failed, states whether established memory changed, and offers an
available corrective action. A generic failure without that minimum is not actionable
and is therefore not produced.

Also realizes ``Vellis::'Fresh Vocabulary Choice'`` and the part of
``VellisRequirements::recommendedEverydayLifeStart`` a first use reaches: where there is
no prior canonical state, the preview names the complete choice set, marks Everyday Life
as recommended and preselected, and establishes neither one until the owner confirms.
Where setup reaches a definite answer about a destination — prior state, a stranger's
database, a store this build cannot read, a file that is not a database — no starting
vocabulary is offered at all. Where it cannot tell, the offer stands and the operation,
which opens the file properly, is the one that decides.

``--from-v1`` realizes the owner-facing half of ``Vellis::'Begin from Vellis v1 snapshot'``:
a snapshot brings its own vocabulary, so no starting vocabulary is offered, and what the
recovery would establish and what it costs are shown in full before it is confirmed.
Beginning from a v2 snapshot is a separate owner-visible choice that arrives with its own
slice; setup does not offer a choice it cannot honor.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import TextIO

from vellis.canonical import Provenance
from vellis.definitions import GraphDefinitionSet
from vellis.everyday_life import everyday_life_starter
from vellis.json_value import JsonValueError, loads
from vellis.outcomes import OperationStatus
from vellis.paths import DestinationError, resolve_data_directory, store_path
from vellis.store import (
    CanonicalStore,
    ForeignDatabaseError,
    NotADatabaseError,
    StoreError,
    UnreadableStoreError,
    holds_established_memory,
)
from vellis.system import RTGSystem
from vellis.v1 import (
    ImportPreview,
    SnapshotError,
    analyze_v1_snapshot,
    recovery_summary,
)

__all__ = [
    "RECOMMENDED_VOCABULARY",
    "FreshVocabularyChoice",
    "SetupReport",
    "SetupStage",
    "main",
    "prepare_local_system",
]

# What an owner can do about a destination that is already a system. Said once, because
# the preview and the operation are describing the same situation to the same person.
ALREADY_ESTABLISHED = (
    "use this system as it is, or pass a different --data-dir for a separate system"
)

# What an owner can do when a start did not happen. Nothing was established, so nothing
# has to be undone first, and the destination is still the one they asked for.
NOTHING_STARTED = (
    "remove nothing; run setup again, and if it still fails choose a different --data-dir"
)

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_DECLINED = 3


class FreshVocabularyChoice(Enum):
    """The two starting vocabularies an owner may confirm.

    Only meaningful when there is no prior memory. Everyday Life is recommended and
    preselected because a blank system cannot record anything until its owner has built a
    vocabulary, and most people did not come here to design one first. Blank stays fully
    supported: someone who knows what they want should not have to undo a gift.
    """

    BLANK = "blank"
    EVERYDAY_LIFE_STARTER = "everydayLifeStarter"

    @property
    def definitions(self) -> GraphDefinitionSet:
        """The definition set this choice establishes.

        Written as exhaustive dispatch rather than a two-way test so that a third choice
        would be a type error here instead of silently becoming one of these two.
        """
        match self:
            case FreshVocabularyChoice.BLANK:
                return GraphDefinitionSet()
            case FreshVocabularyChoice.EVERYDAY_LIFE_STARTER:
                return everyday_life_starter()

    @property
    def description(self) -> str:
        """How this choice is named to an owner who is choosing between the two."""
        match self:
            case FreshVocabularyChoice.BLANK:
                return "blank (an empty definition set)"
            case FreshVocabularyChoice.EVERYDAY_LIFE_STARTER:
                return "Everyday Life (a starter vocabulary of everyday things)"

    @property
    def established_summary(self) -> str:
        """How a confirmed start is recorded permanently.

        Kept apart from :attr:`description` because the recommendation is a stance taken
        while offering, not a fact about the state that was established. The canonical
        record outlives the moment of choosing and should say only what was started.
        """
        match self:
            case FreshVocabularyChoice.BLANK:
                return "blank first-use start with an empty definition set"
            case FreshVocabularyChoice.EVERYDAY_LIFE_STARTER:
                return "first-use start with the Everyday Life starter vocabulary"


RECOMMENDED_VOCABULARY = FreshVocabularyChoice.EVERYDAY_LIFE_STARTER


class SetupStage:
    """The stages an owner can be told about by name."""

    RESOLVE_DESTINATION = "resolve-destination"
    PREVIEW = "preview"
    PREPARE_DESTINATION = "prepare-destination"
    INITIALIZE = "initialize"


@dataclass(frozen=True, slots=True)
class SetupReport:
    """What setup did, or the stage at which it stopped and what to do about it."""

    stage: str
    succeeded: bool
    memory_changed: bool
    summary: str
    # The starting vocabulary this run asked for. Carried without a default so no report
    # can silently substitute the recommendation for the choice its owner actually made.
    # A recovery brings its own vocabulary and establishes none of this one.
    choice: FreshVocabularyChoice
    corrective_action: str | None = None
    destination: Path | None = None
    store: Path | None = None
    revision: int | None = None

    @property
    def is_actionable_failure(self) -> bool:
        """A failure is actionable only with a stage, a state effect, and a next step."""
        return (
            not self.succeeded
            and bool(self.stage)
            and bool(self.summary)
            and bool(self.corrective_action)
        )


def prepare_local_system(
    *,
    data_directory: str | Path | None = None,
    dry_run: bool = False,
    initiator: str = "owner",
    choice: FreshVocabularyChoice = RECOMMENDED_VOCABULARY,
    recovery: ImportPreview | None = None,
    environ: dict[str, str] | None = None,
) -> SetupReport:
    """Prepare one local Vellis system with the start it is given.

    The confirmation the model requires is the documented command's; this establishes what
    a caller asks for. ``choice`` defaults to the recommendation because that is what an
    owner who says nothing is offered, not because anything here has been agreed to.

    A ``recovery`` preview begins from a Vellis v1 system instead. It carries its own
    vocabulary, so no starting vocabulary is chosen or overlaid; ``choice`` then says only
    what the report names, and establishes nothing.

    With ``dry_run`` the destination is resolved and reported and nothing is created. What
    is already at that destination is the command's question, not this one's: a dry run
    here says where a system would go, and the command says whether one can.
    """
    try:
        destination = resolve_data_directory(data_directory, environ=environ)
    except DestinationError as error:
        return SetupReport(
            stage=SetupStage.RESOLVE_DESTINATION,
            succeeded=False,
            memory_changed=False,
            summary=f"no usable destination: {error}",
            choice=choice,
            corrective_action=(
                "pass --data-dir with a writable directory path, or unset VELLIS_DATA_DIR "
                "to use the platform's user-data location"
            ),
        )
    store_file = store_path(destination)
    if dry_run:
        return SetupReport(
            stage=SetupStage.PREVIEW,
            succeeded=True,
            memory_changed=False,
            summary=f"dry run only; nothing was created at {destination}",
            destination=destination,
            store=store_file,
            choice=choice,
        )
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return SetupReport(
            stage=SetupStage.PREPARE_DESTINATION,
            succeeded=False,
            memory_changed=False,
            summary=f"could not prepare {destination}: {error}",
            choice=choice,
            corrective_action=(
                "check that the parent directory exists and is writable, then run setup again"
            ),
            destination=destination,
            store=store_file,
        )
    return _initialize(destination, store_file, initiator, choice, recovery)


def _revision_if_readable(system: RTGSystem) -> int | None:
    """Say where an established system stands, or nothing when that cannot be read.

    The refusal has already been diagnosed by the time this is asked. Letting a failure to
    read one more number replace that diagnosis would answer a different question, and
    would tell an owner with a system that they have none.
    """
    try:
        return system.current_state().revision
    except StoreError:
        return None


def _initialize(
    destination: Path,
    store_file: Path,
    initiator: str,
    choice: FreshVocabularyChoice,
    recovery: ImportPreview | None = None,
) -> SetupReport:
    try:
        store = CanonicalStore(store_file)
    except StoreError as error:
        return SetupReport(
            stage=SetupStage.INITIALIZE,
            succeeded=False,
            memory_changed=False,
            summary=f"could not open the canonical store at {store_file}: {error}",
            # The same triage the preview uses, so a caller reaching this function
            # directly gets the same reading of the same failure.
            corrective_action=_corrective_action(error, store_file),
            destination=destination,
            store=store_file,
            choice=choice,
        )
    system = RTGSystem(store)
    try:
        if recovery is None:
            outcome = system.initialize_fresh(
                choice.definitions,
                provenance=Provenance(initiator=initiator, source="vellis setup"),
                initialization_summary=choice.established_summary,
            )
        else:
            outcome = system.initialize_from_recovery(
                recovery.candidate.graph,
                recovery.candidate.active_definitions,
                provenance=Provenance(initiator=initiator, source="vellis setup: v1 recovery"),
                initialization_summary=recovery_summary(recovery),
            )
        if outcome.status is not OperationStatus.ACCEPTED:
            # Refused because this is already a system, or refused for some other reason
            # with nothing established. Telling the second owner to use the system they
            # have would be telling them to use one that does not exist.
            established = system.is_initialized
            return SetupReport(
                stage=SetupStage.INITIALIZE,
                succeeded=False,
                memory_changed=False,
                summary=outcome.summary,
                corrective_action=ALREADY_ESTABLISHED if established else NOTHING_STARTED,
                destination=destination,
                store=store_file,
                choice=choice,
                revision=_revision_if_readable(system) if established else None,
            )
        return SetupReport(
            stage=SetupStage.INITIALIZE,
            succeeded=True,
            memory_changed=True,
            summary=outcome.summary,
            destination=destination,
            store=store_file,
            choice=choice,
            revision=outcome.resulting_revision,
        )
    except StoreError as error:
        return SetupReport(
            stage=SetupStage.INITIALIZE,
            succeeded=False,
            memory_changed=False,
            summary=f"initialization did not complete: {error}",
            corrective_action=NOTHING_STARTED,
            destination=destination,
            store=store_file,
            choice=choice,
        )
    finally:
        system.close()


def _corrective_action(error: StoreError, store_file: Path) -> str:
    """What an owner can do about a store this build could not use.

    Whose file it is decides the answer. Sending the owner of a Vellis system off to
    another directory would leave their memory behind and start a second system beside
    it, so only a database that is demonstrably somebody else's gets that advice, and a
    file whose owner could not be established gets neither.
    """
    if isinstance(error, UnreadableStoreError):
        return (
            "leave this system where it is: use a Vellis build that reads it, or restore "
            "it from a copy that this one can"
        )
    if isinstance(error, ForeignDatabaseError):
        return "run setup again with a --data-dir that is empty or holds a Vellis system"
    if isinstance(error, NotADatabaseError):
        return (
            "keep that file: move or rename it, or run setup again with a different "
            "--data-dir; whatever it is, this cannot open it as a system"
        )
    # Whose file this is was never established, so the way out may not assume either. In
    # particular it may not suggest going elsewhere: this could be the owner's own store.
    return (
        f"check that this account can read and write {store_file.parent} and everything in "
        "it, then run setup again; if it still fails, keep what is there and run setup "
        "again with a different --data-dir"
    )


@dataclass(frozen=True, slots=True)
class _Existing:
    """What a destination already holds, and what its owner can do about it.

    Every one of these means setup already knows this destination will not do, and knows
    why. Nothing means the opposite: either an owner is beginning, or setup could not tell,
    and the operation answers for both.
    """

    summary: str
    corrective_action: str


def _write_preview(
    report: SetupReport,
    stream: TextIO,
    *,
    existing: _Existing | None,
    recovered: ImportPreview | None = None,
    snapshot: str | None = None,
) -> None:
    stopped = existing is not None or snapshot is not None or _refused(recovered)
    if not stopped:
        print("Vellis setup will prepare one local personal system.", file=stream)
    else:
        # Said before the destination rather than after it: an owner reading down the
        # transcript should not be told a system will be prepared and then untold it.
        print("Vellis setup cannot prepare a system here.", file=stream)
    print(f"  destination:  {report.destination}", file=stream)
    print(f"  memory store: {report.store}", file=stream)
    if snapshot is not None:
        print(f"  this snapshot cannot be read: {snapshot}", file=stream)
    elif recovered is not None:
        _write_recovery(recovered, stream)
    elif existing is None:
        _write_offer(report.choice, stream)
    else:
        # A starting vocabulary is chosen only where there is nothing yet. Offering one
        # here would be offering something setup will refuse a moment later, and taking a
        # confirmation for it would be taking it under a false description.
        print(f"  {existing.summary}", file=stream)
    print("  nothing outside that directory is read or changed.", file=stream)


def _existing_memory(store_file: Path) -> _Existing | None:
    """Say what is already at the store path, or ``None`` where setup cannot tell.

    Cannot tell covers both an owner who is beginning and a destination this could not
    read at all: in either case the operation opens the file and answers for itself.

    Prior canonical state is the condition the model puts the choice under, not a file at
    the path: an interrupted first attempt leaves a store behind that holds nothing, and
    that owner is still beginning. A file this build cannot read is neither — saying which
    it was is more use than either of the two answers it is not.
    """
    try:
        if not holds_established_memory(store_file):
            return None
    except (ForeignDatabaseError, NotADatabaseError, UnreadableStoreError) as error:
        return _Existing(
            summary=f"this destination cannot be used: {error}",
            corrective_action=_corrective_action(error, store_file),
        )
    except StoreError:
        # Something is there and this could not read it — a store another process is
        # writing, or one this account cannot open. Neither is an answer about what the
        # destination holds, so the preview says nothing and the operation, which opens
        # the file properly, decides. Guessing here would either refuse an owner who is
        # entitled to begin or take a confirmation under a description nobody checked.
        return None
    return _Existing(
        summary="this destination already holds memory; setup cannot start it again.",
        corrective_action=ALREADY_ESTABLISHED,
    )


def _refused(recovered: ImportPreview | None) -> bool:
    """Say whether a recovery has already been decided against."""
    return recovered is not None and not recovered.is_acceptable


def _write_recovery(preview: ImportPreview, stream: TextIO) -> None:
    """Show the exact candidate and report an owner is being asked to confirm.

    Every finding is printed, not a count and not a sample. An owner confirming an import
    is agreeing to what it costs as much as to what it keeps, and a cost they were not
    shown is one they did not agree to.
    """
    print("  starting from a Vellis v1 snapshot:", file=stream)
    for finding in preview.report.findings:
        print(f"    {finding.disposition.value}: {finding.summary}", file=stream)


def _write_offer(selected: FreshVocabularyChoice, stream: TextIO) -> None:
    """Name the complete choice set, marking the one that is selected.

    Both are shown every time. A choice that appears only in ``--help`` has not been
    offered, and the model offers two starting vocabularies with one preselected — not a
    setting with a hidden override.
    """
    print("  starting vocabulary:", file=stream)
    for each in FreshVocabularyChoice:
        recommendation = " - recommended" if each is RECOMMENDED_VOCABULARY else ""
        if each is selected:
            print(f"    [x] {each.description}{recommendation}", file=stream)
        else:
            print(
                f"    [ ] {each.description}{recommendation}"
                f" - to choose it, pass --vocabulary {each.value}",
                file=stream,
            )


def _write_report(report: SetupReport, stream: TextIO) -> None:
    if report.succeeded:
        print(report.summary, file=stream)
        if report.revision is not None:
            print(f"  current revision: {report.revision}", file=stream)
        return
    print(f"Setup failed at stage: {report.stage}", file=stream)
    print(f"  what happened: {report.summary}", file=stream)
    changed = "changed" if report.memory_changed else "unchanged"
    print(f"  established memory: {changed}", file=stream)
    print(f"  what to do next: {report.corrective_action}", file=stream)


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdin: TextIO | None = None,
) -> int:
    """Run the documented setup path."""
    import sys

    out: TextIO = sys.stdout if stdout is None else stdout
    error: TextIO = sys.stderr if stderr is None else stderr
    source: TextIO = sys.stdin if stdin is None else stdin

    parser = argparse.ArgumentParser(
        prog="python -m vellis.setup",
        description="Prepare one local Vellis personal-memory system.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="where this system lives; defaults to the platform's user-data location",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt; use it when running without a terminal",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what setup would do and change nothing; it reports a\n"
        "destination that will not do rather than pretending otherwise",
    )
    parser.add_argument(
        "--from-v1",
        default=None,
        help=(
            "begin from a Vellis v1 JSON system snapshot instead of a starting vocabulary; "
            "setup shows exactly what it would recover and what that costs before it is "
            "confirmed"
        ),
    )
    parser.add_argument(
        "--vocabulary",
        choices=[each.value for each in FreshVocabularyChoice],
        default=None,
        help=(
            "the starting vocabulary; defaults to the recommended Everyday Life starter, "
            "with blank fully supported"
        ),
    )
    arguments = parser.parse_args(argv)
    if arguments.from_v1 is not None and arguments.vocabulary is not None:
        parser.error("a v1 snapshot carries its own vocabulary, so --vocabulary says nothing")
    choice = FreshVocabularyChoice(arguments.vocabulary or RECOMMENDED_VOCABULARY.value)

    preview = prepare_local_system(data_directory=arguments.data_dir, dry_run=True, choice=choice)
    if not preview.succeeded:
        _write_report(preview, error)
        return EXIT_FAILED
    # A preview that succeeded resolved a destination, so it knows where the store goes.
    assert preview.store is not None
    existing = _existing_memory(preview.store)
    recovered: ImportPreview | None = None
    unreadable_snapshot: str | None = None
    if arguments.from_v1 is not None and existing is None:
        try:
            recovered = _read_v1_snapshot(str(arguments.from_v1))
        except SnapshotError as unreadable:
            unreadable_snapshot = str(unreadable)
    _write_preview(
        preview, out, existing=existing, recovered=recovered, snapshot=unreadable_snapshot
    )
    if unreadable_snapshot is not None:
        _write_report(
            replace(
                preview,
                succeeded=False,
                summary=f"this snapshot cannot be read: {unreadable_snapshot}",
                corrective_action=(
                    "check that --from-v1 names a complete Vellis v1 system snapshot; the "
                    "destination is untouched either way"
                ),
            ),
            error,
        )
        return EXIT_FAILED
    if existing is not None:
        # Setup already knows this destination will not do, and knows the way out. Going
        # on would ask an owner to confirm an operation that has already been decided
        # against, which is not a confirmation of anything.
        _write_report(
            replace(
                preview,
                succeeded=False,
                summary=existing.summary,
                corrective_action=existing.corrective_action,
            ),
            error,
        )
        return EXIT_FAILED
    if _refused(recovered):
        # Every reason this import would be refused is already in the report above, so
        # there is nothing to confirm and nothing an answer could change.
        _write_report(
            replace(
                preview,
                succeeded=False,
                summary="this snapshot cannot be recovered as it stands",
                corrective_action=(
                    "the conditions above have to be resolved in the v1 system and a new "
                    "snapshot taken; nothing here was changed"
                ),
            ),
            error,
        )
        return EXIT_FAILED
    if arguments.dry_run:
        print("Dry run: nothing was created.", file=out)
        return EXIT_SUCCESS
    if not arguments.yes:
        # The recommendation is stated, not applied: nothing is established until the
        # owner says so, whichever vocabulary is preselected.
        print("Proceed? [y/N] ", end="", file=out)
        out.flush()
        answer = source.readline().strip().lower()
        if answer not in {"y", "yes"}:
            print("Declined; nothing was created.", file=out)
            return EXIT_DECLINED

    if recovered is not None:
        # Read again rather than trusting what was shown. The owner confirmed one exact
        # candidate and report; a snapshot that changed since is a different import that
        # nobody has seen, let alone agreed to.
        try:
            confirmed = _read_v1_snapshot(str(arguments.from_v1))
        except SnapshotError:
            confirmed = None
        if confirmed is None or confirmed.source_identity != recovered.source_identity:
            _write_report(
                replace(
                    preview,
                    succeeded=False,
                    summary="the snapshot changed after it was previewed",
                    corrective_action=(
                        "run setup again to preview and confirm the snapshot as it now "
                        "stands; nothing here was changed"
                    ),
                ),
                error,
            )
            return EXIT_FAILED

    report = prepare_local_system(
        data_directory=arguments.data_dir, choice=choice, recovery=recovered
    )
    _write_report(report, out if report.succeeded else error)
    return EXIT_SUCCESS if report.succeeded else EXIT_FAILED


def _read_v1_snapshot(path: str) -> ImportPreview:
    """Read and analyze one v1 snapshot document, or say why it cannot be read."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SnapshotError(f"could not read {path}: {error}") from error
    try:
        return analyze_v1_snapshot(loads(text))
    except JsonValueError as error:
        raise SnapshotError(f"{path} does not hold JSON this can read: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
