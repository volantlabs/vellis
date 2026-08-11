"""Run the selected MCP boundary over local standard input and output.

``python -m vellis`` is what a client launches. Setup is its own entry point because
establishing a memory is the owner's decision and starting a server is not; a boundary
that quietly created one would be making it for them.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from vellis.mcp import serve
from vellis.paths import default_data_directory, store_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m vellis",
        description="Serve one established Vellis memory over local standard input and output.",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Where the memory lives. Defaults to the platform's user-data location.",
    )
    arguments = parser.parse_args(argv)
    directory = default_data_directory() if arguments.data_dir is None else Path(arguments.data_dir)
    serve(store_path(directory))


if __name__ == "__main__":
    main()
