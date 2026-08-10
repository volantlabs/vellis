"""The documented setup path for one local Vellis system.

Supports ``Vellis::'Begin using one personal Vellis system'`` and
``VellisRequirements::simpleIndividualOperation``: one owner previews what setup will
do, confirms it, and gets either an established local system or a failure that names
the stage that failed, states whether established memory changed, and offers an
available corrective action. A generic failure without that minimum is not actionable
and is therefore not produced.

This slice establishes the blank start. The recommended Everyday Life start, snapshot
initialization, and confirmed v1 recovery are separate owner-visible choices that
arrive with their own slices; setup does not offer a choice it cannot honor.
"""

from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from vellis.canonical import Provenance
from vellis.definitions import GraphDefinitionSet
from vellis.outcomes import OperationStatus
from vellis.paths import DestinationError, resolve_data_directory, store_path
from vellis.store import CanonicalStore, StoreError
from vellis.system import RTGSystem

__all__ = ["SetupReport", "SetupStage", "main", "prepare_local_system"]

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_DECLINED = 3


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
    environ: dict[str, str] | None = None,
) -> SetupReport:
    """Prepare one local Vellis system with a blank starting vocabulary.

    With ``dry_run`` the destination is resolved and previewed and nothing is created.
    """
    try:
        destination = resolve_data_directory(data_directory, environ=environ)
    except DestinationError as error:
        return SetupReport(
            stage=SetupStage.RESOLVE_DESTINATION,
            succeeded=False,
            memory_changed=False,
            summary=f"no usable destination: {error}",
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
        )
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return SetupReport(
            stage=SetupStage.PREPARE_DESTINATION,
            succeeded=False,
            memory_changed=False,
            summary=f"could not prepare {destination}: {error}",
            corrective_action=(
                "check that the parent directory exists and is writable, then run setup again"
            ),
            destination=destination,
        )
    return _initialize(destination, store_file, initiator)


def _initialize(destination: Path, store_file: Path, initiator: str) -> SetupReport:
    try:
        store = CanonicalStore(store_file)
    except (StoreError, sqlite3.Error) as error:
        return SetupReport(
            stage=SetupStage.INITIALIZE,
            succeeded=False,
            memory_changed=False,
            summary=f"could not open the canonical store at {store_file}: {error}",
            corrective_action=(
                "check that the file is readable and writable by this account, then run setup "
                "again; any established memory is unchanged"
            ),
            destination=destination,
            store=store_file,
        )
    system = RTGSystem(store)
    try:
        outcome = system.initialize_fresh(
            GraphDefinitionSet(),
            provenance=Provenance(initiator=initiator, source="vellis setup"),
            initialization_summary="blank first-use start with an empty definition set",
        )
        if outcome.status is not OperationStatus.ACCEPTED:
            return SetupReport(
                stage=SetupStage.INITIALIZE,
                succeeded=False,
                memory_changed=False,
                summary=outcome.summary,
                corrective_action=(
                    "this system already holds memory; use it as it is, or choose a different "
                    "--data-dir for a separate system"
                ),
                destination=destination,
                store=store_file,
                revision=system.current_state().revision if system.is_initialized else None,
            )
        return SetupReport(
            stage=SetupStage.INITIALIZE,
            succeeded=True,
            memory_changed=True,
            summary=outcome.summary,
            destination=destination,
            store=store_file,
            revision=outcome.resulting_revision,
        )
    except StoreError as error:
        return SetupReport(
            stage=SetupStage.INITIALIZE,
            succeeded=False,
            memory_changed=False,
            summary=f"initialization did not complete: {error}",
            corrective_action=(
                "remove nothing; run setup again, and if it still fails choose a different "
                "--data-dir"
            ),
            destination=destination,
            store=store_file,
        )
    finally:
        system.close()


def _write_preview(report: SetupReport, stream: TextIO) -> None:
    print("Vellis setup will prepare one local personal system.", file=stream)
    print(f"  destination:  {report.destination}", file=stream)
    print(f"  memory store: {report.store}", file=stream)
    print("  starting vocabulary: blank (an empty definition set)", file=stream)
    print("  nothing outside that directory is read or changed.", file=stream)


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
        help="skip the confirmation prompt; required when running without a terminal",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what setup would do and change nothing",
    )
    arguments = parser.parse_args(argv)

    preview = prepare_local_system(data_directory=arguments.data_dir, dry_run=True)
    if not preview.succeeded:
        _write_report(preview, error)
        return EXIT_FAILED
    _write_preview(preview, out)
    if arguments.dry_run:
        print("Dry run: nothing was created.", file=out)
        return EXIT_SUCCESS
    if not arguments.yes:
        print("Proceed? [y/N] ", end="", file=out)
        out.flush()
        answer = source.readline().strip().lower()
        if answer not in {"y", "yes"}:
            print("Declined; nothing was created.", file=out)
            return EXIT_DECLINED

    report = prepare_local_system(data_directory=arguments.data_dir)
    _write_report(report, out if report.succeeded else error)
    return EXIT_SUCCESS if report.succeeded else EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
