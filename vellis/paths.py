"""Where one owner's local Vellis system lives.

Supports ``VellisRequirements::simpleIndividualOperation``: one owner on a clean
supported local environment needs a destination that follows the platform's own
user-data convention rather than a location this project invents.

The resolved destination is confirmed nonempty, and any destination inside a directory
named ``.data`` is refused, at any depth and regardless of case. That name is this
repository's ignored working directory for owner-owned graphs, and the contributor
workflow forbids writing there implicitly. Matching only the final component would let
``--data-dir .data/graphs`` through on the same filesystem the guard exists to protect,
and matching case-sensitively would let ``.Data`` through on a case-insensitive one.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

__all__ = [
    "DATA_DIRECTORY_VARIABLE",
    "STORE_FILENAME",
    "DestinationError",
    "default_data_directory",
    "resolve_data_directory",
    "store_path",
]

DATA_DIRECTORY_VARIABLE = "VELLIS_DATA_DIR"
STORE_FILENAME = "vellis.sqlite3"
_REFUSED_DIRECTORY_NAME = ".data"


class DestinationError(ValueError):
    """Raised when no usable local destination can be resolved."""


def default_data_directory(
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Return the platform's conventional user-data directory for Vellis."""
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    if home is None:
        try:
            home = Path.home()
        except RuntimeError as error:
            raise DestinationError(
                f"no home directory could be determined for the default destination: {error}"
            ) from error
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Vellis"
    if platform.startswith("win"):
        local = environ.get("LOCALAPPDATA")
        base = Path(local) if local else home / "AppData" / "Local"
        return base / "Vellis"
    xdg = environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else home / ".local" / "share"
    return base / "vellis"


def resolve_data_directory(
    explicit: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    platform: str | None = None,
    home: Path | None = None,
) -> Path:
    """Resolve the destination from an explicit choice, the environment, or the platform.

    The result is absolute and confirmed usable as a destination name.
    """
    environ = os.environ if environ is None else environ
    chosen: Path
    if explicit is not None:
        if not str(explicit).strip():
            raise DestinationError(
                "an empty destination was given; pass a directory path or omit the option"
            )
        chosen = Path(explicit)
    else:
        configured = environ.get(DATA_DIRECTORY_VARIABLE)
        if configured is not None and configured.strip():
            chosen = Path(configured)
        elif configured is not None:
            raise DestinationError(
                f"{DATA_DIRECTORY_VARIABLE} is set to an empty value; unset it or give a path"
            )
        else:
            chosen = default_data_directory(environ=environ, platform=platform, home=home)
    try:
        resolved = chosen.expanduser().resolve()
    except (OSError, RuntimeError, ValueError) as error:
        # An unknown ~user, an undeterminable home, or a NUL byte in the path all land
        # here. The setup path promises a named stage and a corrective action, so none
        # of them may escape as a bare traceback.
        raise DestinationError(f"{chosen} cannot be resolved to a destination: {error}") from error
    if not resolved.name:
        raise DestinationError(
            f"{resolved} is a filesystem root, which cannot hold one owner's Vellis system"
        )
    for part in resolved.parts:
        if part.casefold() == _REFUSED_DIRECTORY_NAME:
            raise DestinationError(
                f"{resolved} lies in a directory named {_REFUSED_DIRECTORY_NAME!r}, which this "
                "project reserves for owner-owned working data that setup must never write "
                "implicitly"
            )
    return resolved


def store_path(data_directory: Path) -> Path:
    """Return the canonical store file inside a resolved destination."""
    return data_directory / STORE_FILENAME
