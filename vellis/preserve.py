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
import os
import sys
import tempfile
from pathlib import Path
from typing import TextIO

from vellis.canonical import Provenance
from vellis.paths import DestinationError, resolve_data_directory, store_path
from vellis.store import StoreError
from vellis.streaming import SnapshotMetadata
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
    CLOSE_MEMORY = "close-memory"


def _failed(
    stage: str,
    summary: str,
    corrective_action: str,
    stream: TextIO,
    *,
    observed: bool | None = False,
    close_error: Exception | None = None,
    cleanup_error: OSError | None = None,
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
    if observed is True:
        print("  the attempt is recorded in this system's activity history.", file=stream)
    elif observed is None:
        print(
            "  whether the attempt was recorded in activity history could not be determined.",
            file=stream,
        )
    print(f"  what to do next: {corrective_action}", file=stream)
    if cleanup_error is not None:
        print(f"  temporary-file cleanup also failed: {cleanup_error}", file=stream)
        print("  remove the named temporary snapshot after checking its contents", file=stream)
    if close_error is not None:
        print(
            f"  memory cleanup also failed at {PreserveStage.CLOSE_MEMORY}: {close_error}",
            file=stream,
        )
        print(
            "  before copying the memory file: close the other database reader, then open "
            "and close Vellis again so its write-ahead log can be checkpointed",
            file=stream,
        )
    return EXIT_FAILED


def _activity_count(system: RTGSystem) -> int | None:
    """Read the observable ledger position without turning uncertainty into a claim."""
    try:
        return system.store.activity_record_count()
    except StoreError:
        return None


def _changed(before: int | None, after: int | None) -> bool | None:
    if before is None or after is None:
        return None
    return before != after


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    prog: str = "python -m vellis.preserve",
) -> int:
    """Write one snapshot document, or say why it could not be written."""
    out: TextIO = sys.stdout if stdout is None else stdout
    error: TextIO = sys.stderr if stderr is None else stderr

    parser = argparse.ArgumentParser(
        prog=prog,
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
    if os.path.lexists(document):
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
    activity_before = _activity_count(system)
    activity_after: int | None = None
    temporary_name: str | None = None
    metadata: SnapshotMetadata | None = None
    failure: tuple[str, str, str] | None = None
    published = False
    close_error: Exception | None = None
    cleanup_error: OSError | None = None
    try:
        try:
            # Prefer the destination filesystem for an atomic publication.  If the named
            # parent is absent, capture to the platform temporary area first so the owner
            # still gets a complete capture followed by a precise write-stage refusal.
            temporary_directory = document.parent if document.parent.is_dir() else None
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{document.name}.", suffix=".snapshot", dir=temporary_directory
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                metadata = system.export_snapshot(stream, provenance=Provenance(initiator="owner"))
                stream.flush()
                os.fsync(stream.fileno())
        except Exception as unavailable_snapshot:
            failure = (
                PreserveStage.CAPTURE,
                f"the snapshot could not be streamed: {unavailable_snapshot}",
                unavailable,
            )
        if failure is None:
            assert temporary_name is not None
            try:
                # A hard-link publication is atomic and refuses every established name,
                # including a concurrent file and a dangling symbolic link. The temporary
                # lives beside the destination whenever its parent exists, so both names
                # are on the same filesystem.
                os.link(temporary_name, document)
                published = True
            except OSError as unwritable:
                failure = (
                    PreserveStage.WRITE,
                    f"the document could not be written to {document}: {unwritable}",
                    "pass --out a path in a directory that exists and this account can write to",
                )
    finally:
        activity_after = _activity_count(system)
        try:
            system.close()
        except Exception as unavailable_checkpoint:
            close_error = unavailable_checkpoint
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError as unavailable_cleanup:
                cleanup_error = unavailable_cleanup
    observed = _changed(activity_before, activity_after)
    if failure is not None:
        return _failed(
            *failure,
            error,
            observed=observed,
            close_error=close_error,
            cleanup_error=cleanup_error,
        )
    assert metadata is not None and published
    print(f"Preserved revision {metadata.revision} to {document}", file=out)
    print(f"  normalized rows carried: {metadata.row_count}", file=out)
    # Both halves, because the second one is visible to the owner: the next activity
    # history they read will have this capture in it, and a line saying nothing changed
    # would have told them otherwise.
    print("  canonical memory and its revision are unchanged.", file=out)
    if observed is True:
        print("  the capture is recorded in this system's activity history.", file=out)
    elif observed is False:
        print("  the capture was not recorded in this system's activity history.", file=out)
    else:
        print("  whether activity history recorded the capture could not be determined.", file=out)
    if cleanup_error is not None:
        print(
            f"Vellis preserved the snapshot but could not remove its temporary name: "
            f"{cleanup_error}",
            file=error,
        )
        print("  snapshot document: written", file=error)
        print(
            "  what to do next: remove the named temporary snapshot after checking its contents",
            file=error,
        )
    if close_error is not None:
        print(
            f"Vellis preserved the snapshot but could not finish closing. "
            f"Stage: {PreserveStage.CLOSE_MEMORY}",
            file=error,
        )
        print(f"  what happened: the memory could not finish closing: {close_error}", file=error)
        print("  established memory: unchanged", file=error)
        print("  snapshot document: written", file=error)
        print(
            "  what to do next: close the other database reader, then open and close "
            "Vellis again before copying the memory file; the snapshot already written "
            "does not need repeating",
            file=error,
        )
    return EXIT_FAILED if cleanup_error is not None or close_error is not None else EXIT_SUCCESS


if __name__ == "__main__":
    raise SystemExit(main())
