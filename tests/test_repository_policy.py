"""Repository evidence for the installable Vellis 2.0 release boundary."""

from __future__ import annotations

import io
import tomllib
from pathlib import Path

import vellis
from vellis import __main__ as owner_command

ROOT = Path(__file__).resolve().parent.parent


def _metadata() -> dict[str, object]:
    with (ROOT / "pyproject.toml").open("rb") as source:
        return tomllib.load(source)


def test_release_metadata_restores_installable_package_and_legacy_commands() -> None:
    metadata = _metadata()

    assert metadata["build-system"] == {  # type: ignore[index]
        "requires": ["setuptools>=83.0.0", "wheel"],
        "build-backend": "setuptools.build_meta",
    }
    project = metadata["project"]  # type: ignore[assignment]
    assert project["name"] == "vellis"  # type: ignore[index]
    assert project["scripts"] == {  # type: ignore[index]
        "vellis": "vellis.__main__:main",
        "vellis-rtg-knowledge-graph": "vellis.__main__:main",
    }
    assert metadata.get("tool", {}).get("uv", {}).get("package") is not False  # type: ignore[union-attr]


def test_unified_owner_command_advertises_all_dispatch_paths() -> None:
    output = io.StringIO()

    assert owner_command.main(["--help"], stdout=output) == owner_command.EXIT_SUCCESS

    help_text = output.getvalue()
    for command in ("setup", "preserve", "restore", "serve", "serve-mcp"):
        assert command in help_text


def test_version_is_consistent_across_metadata_runtime_and_lock() -> None:
    project = _metadata()["project"]  # type: ignore[index]
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert project["version"] == vellis.__version__ == "2.0.0"  # type: ignore[index]
    assert 'name = "vellis"\nversion = "2.0.0"\nsource = { editable = "." }' in lock
