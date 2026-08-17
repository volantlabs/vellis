"""Repository evidence for the installable Vellis 2.0 release boundary."""

from __future__ import annotations

import io
import re
import subprocess
import tomllib

import yaml

import vellis
from tools import model_layout
from vellis import __main__ as owner_command

ROOT = model_layout.ROOT


def _just_recipes() -> set[str]:
    result = subprocess.run(
        ["just", "--summary"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.split())


def test_documented_commands_exist() -> None:
    documents = [
        *ROOT.glob("*.md"),
        ROOT / "model" / "README.md",
        *(ROOT / "docs").rglob("*.md"),
        *(ROOT / ".github").rglob("*.md"),
        *(ROOT / ".agents" / "skills").rglob("*.md"),
    ]
    documented = {
        command
        for path in documents
        for command in re.findall(r"\bjust\s+([a-z][a-z0-9-]*)", path.read_text(encoding="utf-8"))
    }

    assert documented
    assert documented <= _just_recipes()


def test_reference_finder_quotes_untrusted_questions() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-reference-find", "$(printf unsafe)"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "'$(printf unsafe)'" in result.stdout + result.stderr


def test_reference_finder_routes_positional_specification_and_limit() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-reference-find", "part or item", "sysml-2.1", "5"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    command = result.stdout + result.stderr
    assert "specification='sysml-2.1'" in command
    assert '--specification "$specification"' in command
    assert "--limit '5'" in command


def test_snippet_probe_quotes_untrusted_source() -> None:
    result = subprocess.run(
        ["just", "--dry-run", "model-probe", "$(printf unsafe)"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "'$(printf unsafe)'" in result.stdout + result.stderr


def test_ci_runs_locked_setup_before_full_check() -> None:
    workflow = yaml.safe_load(
        (ROOT / ".github" / "workflows" / "check.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["check"]["steps"]
    commands = [" ".join(str(step["run"]).split()) for step in steps if "run" in step]
    checkout = next(
        step for step in steps if str(step.get("uses", "")).startswith("actions/checkout@")
    )

    assert checkout["with"]["fetch-depth"] == 0
    assert "uv sync --locked" in commands
    assert commands.index("just model-setup") < commands.index("just check")


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
