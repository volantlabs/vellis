"""Dispatch the installed owner command and local MCP boundary.

``vellis`` and the legacy ``vellis-rtg-knowledge-graph`` executable both expose setup,
preserve, restore, and serving. The existing ``python -m`` forms stay available. A bare
command still serves over standard input/output so existing MCP client launch commands do
not change.

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
or a one-line message. A failure before serving leaves memory unchanged; a close-stage
failure carries the revision effect observed across the completed server session.
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
    memory_changed: bool | None = False,
    operation: str = "serve",
) -> None:
    """Say what failed, what it did to established memory, and what to do about it.

    The state effect is stated rather than omitted when nothing happened. "Unchanged" is
    the answer an owner needs before deciding whether to retry, and an absent line is not
    that answer.
    """
    print(f"Vellis could not {operation} this memory. Stage: {stage}", file=stream)
    print(f"  what happened: {summary}", file=stream)
    changed = (
        "could not be determined"
        if memory_changed is None
        else "changed"
        if memory_changed
        else "unchanged"
    )
    print(f"  established memory: {changed}", file=stream)
    print(f"  what to do next: {corrective_action}", file=stream)


def _memory_position(system: RTGSystem) -> tuple[int, int] | None:
    """Return canonical and observational positions, or preserve honest uncertainty."""
    try:
        return system.store.current_revision(), system.store.activity_record_count()
    except StoreError:
        return None


def _position_changed(before: tuple[int, int] | None, after: tuple[int, int] | None) -> bool | None:
    if before is None or after is None:
        return None
    return before != after


def _restore(
    argv: list[str],
    *,
    error: TextIO,
    output: TextIO,
    confirm: Callable[[str], str],
    prog: str = "python -m vellis restore",
) -> int:
    """Make a past state current again, on the owner's own say-so.

    Restoration commits the selected state as the next revision rather than erasing what
    followed, so this asks before acting and then says exactly what it did. The prompt is
    the point: the owner is the only party the model lets decide this.
    """
    parser = argparse.ArgumentParser(
        prog=prog,
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
    result = EXIT_FAILED
    try:
        directory: Path = resolve_data_directory(arguments.data_dir)
    except DestinationError as unusable:
        _report(
            ConnectionStage.RESOLVE_DESTINATION,
            f"no usable destination: {unusable}",
            "pass --data-dir with the directory holding your Vellis system",
            error,
            operation="restore",
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
                operation="restore",
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
            operation="restore",
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
            operation="restore",
        )
        return EXIT_FAILED
    starting_position = _memory_position(system)
    ending_position = starting_position
    control_failure: BaseException | None = None
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
            ending_position = _memory_position(system)
            if not outcome.accepted:
                _report(
                    ConnectionStage.RESTORE_STATE,
                    outcome.summary,
                    "resolve what the finding names, then run this again",
                    error,
                    memory_changed=_position_changed(starting_position, ending_position),
                    operation="restore",
                )
                for finding in outcome.findings:
                    print(f"  finding: {finding.summary}", file=error)
            else:
                result = EXIT_SUCCESS
                print(f"  restored: {outcome.summary}", file=output)
    except Exception as operation_error:
        ending_position = _memory_position(system)
        _report(
            ConnectionStage.RESTORE_STATE,
            f"the restoration could not complete: {operation_error}",
            "resolve the reported store problem, then inspect history before retrying",
            error,
            memory_changed=_position_changed(starting_position, ending_position),
            operation="restore",
        )
    except BaseException as interrupted:
        # KeyboardInterrupt, SystemExit, and cancellation retain their process-control
        # meaning, but not at the cost of bypassing the same checkpoint cleanup every
        # ordinary restore path receives.
        control_failure = interrupted
    try:
        system.close()
    except StoreError as close_error:
        if control_failure is not None:
            control_failure.add_note(
                "Vellis cleanup also failed: "
                f"{close_error}. Close the other database reader, then open and close "
                "Vellis again before copying the memory file."
            )
            raise control_failure from close_error
        _report(
            ConnectionStage.CLOSE_MEMORY,
            f"the restore operation finished, but cleanup could not: {close_error}",
            "close the other database reader, then open and close Vellis again before "
            "copying the memory file; inspect history before retrying a restore",
            error,
            memory_changed=_position_changed(starting_position, ending_position),
            operation="restore",
        )
        return EXIT_FAILED
    if control_failure is not None:
        raise control_failure
    return result


def _serve(argv: list[str], *, error: TextIO, prog: str) -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
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
            unavailable.stage,
            unavailable.summary,
            unavailable.corrective_action,
            error,
            memory_changed=unavailable.memory_changed,
        )
        return EXIT_FAILED
    return EXIT_SUCCESS


def _print_root_help(prog: str, output: TextIO) -> None:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Set up, preserve, restore, or serve one local Vellis personal-memory system. "
            "With no command, Vellis serves over local standard input and output."
        ),
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("setup", "preserve", "restore", "serve", "serve-mcp"),
        help="owner operation; serve-mcp is the legacy spelling of serve",
    )
    parser.add_argument(
        "--data-dir",
        help="serve the memory in this directory when no explicit command is given",
    )
    parser.print_help(file=output)


def _invoked_program() -> str:
    name = Path(sys.argv[0]).name
    return "python -m vellis" if name == "__main__.py" else name


def main(
    argv: list[str] | None = None,
    *,
    stderr: TextIO | None = None,
    stdout: TextIO | None = None,
    confirm: Callable[[str], str] = input,
    prog: str | None = None,
) -> int:
    error: TextIO = sys.stderr if stderr is None else stderr
    output: TextIO = sys.stdout if stdout is None else stdout
    arguments_given = list(sys.argv[1:] if argv is None else argv)
    program = prog or (_invoked_program() if argv is None else "vellis")
    if arguments_given and arguments_given[0] in {"-h", "--help"}:
        _print_root_help(program, output)
        return EXIT_SUCCESS
    if arguments_given and arguments_given[0] == "setup":
        from vellis.setup import main as setup

        return setup(
            arguments_given[1:],
            stdout=output,
            stderr=error,
            prog=f"{program} setup",
        )
    if arguments_given and arguments_given[0] == "preserve":
        from vellis.preserve import main as preserve

        return preserve(
            arguments_given[1:],
            stdout=output,
            stderr=error,
            prog=f"{program} preserve",
        )
    if arguments_given and arguments_given[0] == "restore":
        return _restore(
            list(arguments_given[1:]),
            error=error,
            output=output,
            confirm=confirm,
            prog=f"{program} restore",
        )
    if arguments_given and arguments_given[0] in {"serve", "serve-mcp"}:
        command = arguments_given.pop(0)
        return _serve(arguments_given, error=error, prog=f"{program} {command}")
    return _serve(arguments_given, error=error, prog=program)


if __name__ == "__main__":
    raise SystemExit(main())
