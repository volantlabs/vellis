"""Run the selected MCP boundary over local standard input and output.

``python -m vellis`` is what a client launches. Setup is its own entry point because
establishing a memory is the owner's decision and starting a server is not; a boundary
that quietly created one would be making it for them.

``python -m vellis restore`` is the owner's, for the same reason inverted. Restoring a
past state is a modeled capability the ten agent tools deliberately leave out, because
that surface decides no authorization and an agent that damaged a memory should not also
hold the means of rewriting it. Leaving it off every surface, though, is not a decision —
it is a capability nobody can reach, and an owner watching their history is owed a way to
act on it.

``VellisVerification::simpleOperation`` names a connection failure alongside a failed
setup attempt and holds both to the same minimum: the stage that failed, whether
established memory changed, and an available corrective action. A generic failure lacking
any of the three does not pass, so nothing here may reach the owner as a bare traceback
or a one-line message. Every failure below happens before a single tool is served, so the
state effect is always the same one and is always stated rather than left to be inferred.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TextIO

from vellis.canonical import Provenance
from vellis.history import HistoricalSelection, RevisionSelection, TimeSelection
from vellis.mcp import ServeError, serve
from vellis.paths import DestinationError, resolve_data_directory, store_path
from vellis.store import StoreError
from vellis.system import RTGSystem

EXIT_SUCCESS = 0
EXIT_FAILED = 1


class ConnectionStage:
    """The stages a client-launched run can fail at, by name."""

    RESOLVE_DESTINATION = "resolve-destination"
    OPEN_MEMORY = "open-memory"
    RESTORE_STATE = "restore-state"
    CLOSE_MEMORY = "close-memory"


def _report(
    stage: str,
    summary: str,
    corrective_action: str,
    stream: TextIO,
    *,
    memory_changed: bool = False,
) -> None:
    """Say what failed, what it did to established memory, and what to do about it.

    The state effect is stated rather than omitted when nothing happened. "Unchanged" is
    the answer an owner needs before deciding whether to retry, and an absent line is not
    that answer.
    """
    print(f"Vellis could not serve this memory. Stage: {stage}", file=stream)
    print(f"  what happened: {summary}", file=stream)
    changed = "changed" if memory_changed else "unchanged"
    print(f"  established memory: {changed}", file=stream)
    print(f"  what to do next: {corrective_action}", file=stream)


def _restore(
    argv: list[str], *, error: TextIO, output: TextIO, confirm: Callable[[str], str]
) -> int:
    """Make a past state current again, on the owner's own say-so.

    Restoration commits the selected state as the next revision rather than erasing what
    followed, so this asks before acting and then says exactly what it did. The prompt is
    the point: the owner is the only party the model lets decide this.
    """
    parser = argparse.ArgumentParser(
        prog="python -m vellis restore",
        description="Make one past state of this memory current again, as a new revision.",
    )
    parser.add_argument("--data-dir", default=None, help="Where the memory lives.")
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--revision", type=int, help="The committed revision to restore.")
    selector.add_argument(
        "--time",
        help=("Restore the greatest revision committed at or before this ISO-8601 instant."),
    )
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    arguments = parser.parse_args(argv)
    restored = False
    result = EXIT_FAILED
    try:
        directory: Path = resolve_data_directory(arguments.data_dir)
    except DestinationError as unusable:
        _report(
            ConnectionStage.RESOLVE_DESTINATION,
            f"no usable destination: {unusable}",
            "pass --data-dir with the directory holding your Vellis system",
            error,
        )
        return EXIT_FAILED

    selection: HistoricalSelection
    if arguments.revision is not None:
        selection = RevisionSelection(revision=arguments.revision)
        named = f"revision {arguments.revision}"
    else:
        try:
            selection = TimeSelection(time=datetime.fromisoformat(arguments.time))
        except ValueError:
            _report(
                ConnectionStage.RESTORE_STATE,
                f"--time is not an ISO-8601 instant: {arguments.time!r}",
                "pass an instant such as 2026-08-14T18:59:30+00:00",
                error,
            )
            return EXIT_FAILED
        named = f"the state at {arguments.time}"

    path = store_path(directory)
    if not path.exists():
        _report(
            ConnectionStage.OPEN_MEMORY,
            f"no Vellis memory is established at {path}",
            f"run `python -m vellis.setup --data-dir {directory}` to begin one here",
            error,
        )
        return EXIT_FAILED
    try:
        system = RTGSystem.open(path)
    except StoreError as unopenable:
        _report(
            ConnectionStage.OPEN_MEMORY,
            f"the memory at {path} could not be opened: {unopenable}",
            "check that this account can read and write that file",
            error,
        )
        return EXIT_FAILED
    try:
        print(f"Vellis will restore {named} in {path}.", file=output)
        print(
            "  Everything already recorded stays where it is: the restored state is "
            "committed as the next revision, so this is itself undoable.",
            file=output,
        )
        if not arguments.yes and confirm("  Restore it? [y/N] ").strip().lower() not in {
            "y",
            "yes",
        }:
            print("  nothing was restored; established memory is unchanged", file=output)
            result = EXIT_SUCCESS
        else:
            outcome = system.restore_historical_state(selection, provenance=Provenance("owner"))
            if not outcome.accepted:
                _report(
                    ConnectionStage.RESTORE_STATE,
                    outcome.summary,
                    "resolve what the finding names, then run this again",
                    error,
                )
                for finding in outcome.findings:
                    print(f"  finding: {finding.summary}", file=error)
            else:
                restored = True
                result = EXIT_SUCCESS
                print(f"  restored: {outcome.summary}", file=output)
    except StoreError as operation_error:
        _report(
            ConnectionStage.RESTORE_STATE,
            f"the restoration could not complete: {operation_error}",
            "resolve the reported store problem, then inspect history before retrying",
            error,
        )
    try:
        system.close()
    except StoreError as close_error:
        _report(
            ConnectionStage.CLOSE_MEMORY,
            f"the restore operation finished, but cleanup could not: {close_error}",
            "close the other database reader, then open and close Vellis again before "
            "copying the memory file; inspect history before retrying a restore",
            error,
            memory_changed=restored,
        )
        return EXIT_FAILED
    return result


def main(
    argv: list[str] | None = None,
    *,
    stderr: TextIO | None = None,
    stdout: TextIO | None = None,
    confirm: Callable[[str], str] = input,
) -> int:
    error: TextIO = sys.stderr if stderr is None else stderr
    arguments_given = sys.argv[1:] if argv is None else argv
    if arguments_given and arguments_given[0] == "restore":
        return _restore(
            list(arguments_given[1:]),
            error=error,
            output=sys.stdout if stdout is None else stdout,
            confirm=confirm,
        )
    parser = argparse.ArgumentParser(
        prog="python -m vellis",
        description="Serve one established Vellis memory over local standard input and output.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Where the memory lives. Defaults to VELLIS_DATA_DIR when it is set, and "
            "otherwise to the platform's user-data location."
        ),
    )
    arguments = parser.parse_args(argv)
    try:
        directory: Path = resolve_data_directory(arguments.data_dir)
    except DestinationError as unusable:
        _report(
            ConnectionStage.RESOLVE_DESTINATION,
            f"no usable destination: {unusable}",
            "pass --data-dir with the directory holding your Vellis system, or unset "
            "VELLIS_DATA_DIR to use the platform's user-data location",
            error,
        )
        return EXIT_FAILED
    try:
        serve(store_path(directory))
    except ServeError as unavailable:
        _report(
            ConnectionStage.OPEN_MEMORY,
            unavailable.summary,
            unavailable.corrective_action,
            error,
        )
        return EXIT_FAILED
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
