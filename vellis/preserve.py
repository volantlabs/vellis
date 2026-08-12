"""Write one established memory out as a canonical snapshot document.

Realizes the owner-facing half of ``Vellis::'Preserve personal memory snapshot'`` in the
form ``Vellis::'Begin using one personal Vellis system'`` takes back: a complete canonical
snapshot with an optional later ledger tail. Setup can begin from such a document; without
a command that produces one, that starting input would be reachable only by writing Python
against the library, and the owner-facing path would be half a loop.

Preserving leaves canonical memory and its revision exactly where they were, and the
attempt is recorded observationally the way every other read is — that is the state effect
``Vellis::'Preserve personal memory snapshot'`` names, and both halves of it are said
rather than only the reassuring one. The capture is bound to the record that established
the revision it captured, so the document a later system begins from is the state this one
was in, provably from this ledger rather than any other with the same numbers.

Failures say what setup's do, in the same three parts: the stage that failed, what it did
to established memory — always nothing, because no path here commits a canonical record —
and an available corrective action that is not one the owner has already satisfied.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TextIO

from vellis.canonical import Provenance
from vellis.paths import DestinationError, resolve_data_directory, store_path
from vellis.snapshot_document import write_snapshot_document
from vellis.store import StoreError
from vellis.system import RTGSystem

__all__ = ["EXIT_FAILED", "EXIT_SUCCESS", "PreserveStage", "main"]

EXIT_SUCCESS = 0
EXIT_FAILED = 1


class PreserveStage:
    """The stages an owner can be told about by name."""

    RESOLVE_DESTINATION = "resolve-destination"
    OPEN_MEMORY = "open-memory"
    CAPTURE = "capture"
    WRITE = "write"


def _failed(
    stage: str,
    summary: str,
    corrective_action: str,
    stream: TextIO,
    *,
    observed: bool = False,
) -> int:
    """Say what failed, what it did to established memory, and what to do about it.

    "Unchanged" is about canonical memory, which no path here commits a record to. The
    observational half is said whenever it happened, because it did happen and the owner
    will find it in their own activity history; a report that mentioned only the first
    half would be the reason they stopped believing the second.
    """
    print(f"Vellis could not preserve this memory. Stage: {stage}", file=stream)
    print(f"  what happened: {summary}", file=stream)
    print("  established memory: unchanged", file=stream)
    if observed:
        print("  the attempt is recorded in this system's activity history.", file=stream)
    print(f"  what to do next: {corrective_action}", file=stream)
    return EXIT_FAILED


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Write one snapshot document, or say why it could not be written."""
    out: TextIO = sys.stdout if stdout is None else stdout
    error: TextIO = sys.stderr if stderr is None else stderr

    parser = argparse.ArgumentParser(
        prog="python -m vellis.preserve",
        description=(
            "Write one established Vellis memory out as a canonical snapshot document, "
            "which setup can begin a new system from."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "where this system lives; defaults to VELLIS_DATA_DIR when it is set, and "
            "otherwise to the platform's user-data location"
        ),
    )
    parser.add_argument("--out", required=True, help="where to write the snapshot document")
    arguments = parser.parse_args(argv)

    try:
        directory = resolve_data_directory(arguments.data_dir)
    except DestinationError as unusable:
        return _failed(
            PreserveStage.RESOLVE_DESTINATION,
            f"no usable destination: {unusable}",
            "pass --data-dir with the directory holding your Vellis system, or unset "
            "VELLIS_DATA_DIR to use the platform's user-data location",
            error,
        )
    document = Path(arguments.out)
    if document.exists():
        # Never over something that is already there, and asked before anything is read.
        # Writing the document is the one effect this command has, and the path an owner
        # is most likely to mistype is the store itself — which this would replace, and
        # then report success for. Refusing first also means a run that cannot finish has
        # not observed the memory on its way to finding that out.
        return _failed(
            PreserveStage.WRITE,
            f"{document} already exists",
            "pass --out a path that does not exist yet, or move what is there first",
            error,
        )
    memory = store_path(directory)
    if not memory.exists():
        # Opening would create an empty store beside a path the owner probably mistyped.
        return _failed(
            PreserveStage.OPEN_MEMORY,
            f"no Vellis memory is established at {memory}",
            # Named, so the advice is about this destination rather than the default one
            # an owner would otherwise establish a second system at.
            "point --data-dir at the directory that holds your Vellis system, or run "
            f"`python -m vellis.setup --data-dir {directory}` to begin one there",
            error,
        )
    try:
        system = RTGSystem.open(memory)
    except StoreError as unreadable:
        return _failed(
            PreserveStage.OPEN_MEMORY,
            f"the memory at {memory} could not be opened: {unreadable}",
            # The directory as well as the file: opening a store writes, and a directory
            # this account cannot write is the ordinary way that fails. Advice to check
            # read access alone would already be satisfied and leave nothing to do.
            "check that this account can read and write that file and the directory "
            "holding it, and that --data-dir names your Vellis system's directory",
            error,
        )
    unavailable = "try again once nothing else is writing to this system"
    try:
        captured = system.create_snapshot(provenance=Provenance(initiator="owner"))
        if captured.snapshot is None:
            return _failed(
                PreserveStage.CAPTURE,
                captured.summary,
                f"run `python -m vellis.setup --data-dir {directory}` if this system "
                f"has not been established yet; otherwise {unavailable}",
                error,
                observed=True,
            )
        # Everything committed since the capture, which for a system nobody is writing to
        # is nothing at all. An empty run is written as no tail rather than as a tail with
        # nothing in it, which is a document no reconstruction would accept.
        try:
            tail = system.ledger_tail(after=captured.snapshot.revision)
        except StoreError as unreadable_tail:
            # The capture succeeded and this read did not. Reporting it as the stage it
            # failed at keeps the promise the capture path already keeps; letting it out
            # would be the one generic failure this command is not allowed to produce.
            return _failed(
                PreserveStage.CAPTURE,
                f"the records after revision {captured.snapshot.revision} could not be "
                f"read: {unreadable_tail}",
                unavailable,
                error,
                observed=True,
            )
    finally:
        system.close()

    try:
        write_snapshot_document(document, captured.snapshot, tail)
    except OSError as unwritable:
        return _failed(
            PreserveStage.WRITE,
            f"the document could not be written to {document}: {unwritable}",
            "pass --out a path in a directory that exists and this account can write to; "
            "if a partly written file was left behind, remove it before trying again",
            error,
            # The capture happened, whatever became of the document.
            observed=True,
        )
    print(f"Preserved revision {captured.snapshot.revision} to {document}", file=out)
    print(f"  later transitions carried: {len(tail.transitions)}", file=out)
    # Both halves, because the second one is visible to the owner: the next activity
    # history they read will have this capture in it, and a line saying nothing changed
    # would have told them otherwise.
    print("  canonical memory and its revision are unchanged.", file=out)
    print("  the capture is recorded in this system's activity history.", file=out)
    return EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
