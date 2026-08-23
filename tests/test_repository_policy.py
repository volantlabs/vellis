"""Repository evidence for the installable Vellis 2.0 release boundary."""

from __future__ import annotations

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


def test_release_metadata_exposes_only_the_selected_owner_command() -> None:
    metadata = _metadata()

    assert metadata["build-system"] == {  # type: ignore[index]
        "requires": ["setuptools>=83.0.0", "wheel"],
        "build-backend": "setuptools.build_meta",
    }
    project = metadata["project"]  # type: ignore[assignment]
    assert project["name"] == "vellis"  # type: ignore[index]
    assert project["scripts"] == {  # type: ignore[index]
        "vellis": "vellis.__main__:main",
    }
    assert metadata.get("tool", {}).get("uv", {}).get("package") is not False  # type: ignore[union-attr]


def test_unreleased_predecessor_modules_are_absent() -> None:
    removed = {
        "activity",
        "canonical",
        "changes",
        "client_setup",
        "definitions",
        "discovery",
        "everyday_life",
        "governance",
        "graph",
        "history",
        "json_value",
        "mutation_impact",
        "normalized",
        "outcomes",
        "patterns",
        "preserve",
        "query",
        "setup",
        "sqlite_query",
        "store",
        "streaming",
        "system",
        "v1",
        "v1_streaming",
        "validation",
    }

    assert not {name for name in removed if (ROOT / "vellis" / f"{name}.py").exists()}


def test_unified_owner_command_advertises_only_selected_dispatch_paths() -> None:
    help_text = owner_command._parser().format_help()
    for command in ("setup", "connect", "serve", "backup", "restore", "audit", "configure"):
        assert command in help_text
    for removed in ("preserve", "serve-mcp"):
        assert removed not in help_text


def test_version_is_consistent_across_metadata_runtime_and_lock() -> None:
    project = _metadata()["project"]  # type: ignore[index]
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert project["version"] == vellis.__version__ == "2.0.0"  # type: ignore[index]
    assert 'name = "vellis"\nversion = "2.0.0"\nsource = { editable = "." }' in lock


def test_documented_subcommands_match_the_owner_command() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"```text\n(.*?)```", readme, re.DOTALL)
    assert block is not None, "README.md has no fenced subcommand block to verify"

    documented = {
        line.removeprefix("vellis ").strip() for line in block.group(1).splitlines() if line
    }
    subparsers = next(
        action
        for action in owner_command._parser()._subparsers._group_actions  # type: ignore[union-attr]
        if hasattr(action, "choices")
    )
    assert documented == set(subparsers.choices)  # type: ignore[arg-type]
