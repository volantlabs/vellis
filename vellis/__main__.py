"""Run the selected MCP boundary over local standard input and output.

``python -m vellis`` is what a client launches. Setup is its own entry point because
establishing a memory is the owner's decision and starting a server is not; a boundary
that quietly created one would be making it for them.

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
from pathlib import Path
from typing import TextIO

from vellis.mcp import ServeError, serve
from vellis.paths import DestinationError, resolve_data_directory, store_path

EXIT_SUCCESS = 0
EXIT_FAILED = 1


class ConnectionStage:
    """The stages a client-launched run can fail at, by name."""

    RESOLVE_DESTINATION = "resolve-destination"
    OPEN_MEMORY = "open-memory"


def _report(stage: str, summary: str, corrective_action: str, stream: TextIO) -> None:
    """Say what failed, what it did to established memory, and what to do about it.

    The state effect is stated rather than omitted when nothing happened. "Unchanged" is
    the answer an owner needs before deciding whether to retry, and an absent line is not
    that answer.
    """
    print(f"Vellis could not serve this memory. Stage: {stage}", file=stream)
    print(f"  what happened: {summary}", file=stream)
    print("  established memory: unchanged", file=stream)
    print(f"  what to do next: {corrective_action}", file=stream)


def main(argv: list[str] | None = None, *, stderr: TextIO | None = None) -> int:
    error: TextIO = sys.stderr if stderr is None else stderr
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
