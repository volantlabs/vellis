import ast
import sys
from pathlib import Path

import pytest

import tools.package_smoke as package_smoke
from tools.package_smoke import (
    ROOT,
    _assert_installed_import,
    _assert_installed_matches_source,
    _build_distribution,
    _purge_build_tree,
    _run_isolated_tool,
)


def test_run_isolated_tool_rejects_environment_outside_temp_root(tmp_path: Path) -> None:
    temporary = tmp_path / "isolated"
    temporary.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    environment = {"UV_TOOL_DIR": str(outside), "UV_TOOL_BIN_DIR": str(temporary / "bin")}

    with pytest.raises(AssertionError, match="outside its isolated temp root"):
        _run_isolated_tool(
            "/usr/bin/true", cwd=temporary, environment=environment, temporary=temporary
        )


def test_run_isolated_tool_refuses_an_environment_without_overrides(tmp_path: Path) -> None:
    temporary = tmp_path / "isolated"
    temporary.mkdir()

    with pytest.raises((KeyError, AssertionError)):
        _run_isolated_tool("/usr/bin/true", cwd=temporary, environment={}, temporary=temporary)


def test_run_isolated_tool_runs_when_environment_is_inside_temp_root(tmp_path: Path) -> None:
    temporary = tmp_path / "isolated"
    temporary.mkdir()
    environment = {
        "UV_TOOL_DIR": str(temporary / "tools"),
        "UV_TOOL_BIN_DIR": str(temporary / "bin"),
        "PATH": "/usr/bin:/bin",
    }

    result = _run_isolated_tool(
        "/usr/bin/true", cwd=temporary, environment=environment, temporary=temporary
    )

    assert result.returncode == 0


def test_only_the_isolated_helper_can_run_a_tool_install() -> None:
    """The chokepoint invariant _run_isolated_tool's docstring claims, asserted.

    Without this, adding a bare _run("uv", "tool", "install", ...) elsewhere in the
    module would reintroduce exactly the defect the helper exists to prevent, and
    every other test here would stay green.
    """
    source = (ROOT / "tools" / "package_smoke.py").read_text(encoding="utf-8")
    module = ast.parse(source)

    offenders: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"_run", "run"}:
            continue
        literals = [
            argument.value
            for argument in node.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        ]
        if literals[:2] == ["uv", "tool"] or (literals and literals[0] == "uvx"):
            offenders.append(f"line {node.lineno}")

    assert offenders == [], (
        f"uv tool/uvx invoked outside _run_isolated_tool at {offenders}; "
        "route it through the isolated helper instead"
    )


def _mirror_source(destination: Path) -> Path:
    package = destination / "vellis"
    package.mkdir(parents=True)
    for path in (ROOT / "vellis").rglob("*.py"):
        target = package / path.relative_to(ROOT / "vellis")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    return package


def test_installed_match_accepts_a_faithful_copy_of_the_source_tree(tmp_path: Path) -> None:
    _assert_installed_matches_source(_mirror_source(tmp_path), "wheel")


def test_installed_match_rejects_a_module_deleted_from_source(tmp_path: Path) -> None:
    """A rebuilt distribution keeps its name and version, so only content differs."""
    package = _mirror_source(tmp_path)
    (package / "graph.py").write_text("# a module deleted from source but left in build/lib\n")

    with pytest.raises(AssertionError, match="unexpected=..graph.py"):
        _assert_installed_matches_source(package, "wheel")


def test_installed_match_rejects_a_module_that_drifted_from_source(tmp_path: Path) -> None:
    package = _mirror_source(tmp_path)
    (package / "mcp.py").write_text("# stale copy\n")

    with pytest.raises(AssertionError, match="altered=..mcp.py"):
        _assert_installed_matches_source(package, "wheel")


def test_installed_match_rejects_a_missing_module(tmp_path: Path) -> None:
    package = _mirror_source(tmp_path)
    (package / "mcp.py").unlink()

    with pytest.raises(AssertionError, match="missing=..mcp.py"):
        _assert_installed_matches_source(package, "wheel")


def test_purge_build_tree_removes_the_intermediate_build_directory(tmp_path: Path) -> None:
    stale = tmp_path / "build" / "lib" / "vellis"
    stale.mkdir(parents=True)
    (stale / "ghost.py").write_text("# deleted from source, still in build/\n")

    _purge_build_tree(tmp_path)

    assert not (tmp_path / "build").exists()


def test_purge_build_tree_accepts_a_tree_that_was_never_built(tmp_path: Path) -> None:
    _purge_build_tree(tmp_path)

    assert not (tmp_path / "build").exists()


def test_installed_import_check_compares_content_not_only_the_version(tmp_path: Path) -> None:
    """The comparison has to be wired into the import check, not merely defined.

    A perfect comparator that no caller invokes leaves the original defect in
    place while every check stays green.
    """
    environment = tmp_path / "env"
    package = _mirror_source(environment)
    (package / "mcp.py").write_text("# stale copy left by an uncleaned build tree\n")

    with pytest.raises(AssertionError, match="does not match the source tree"):
        _assert_installed_import(Path(sys.executable), environment, environment, "wheel")


def test_build_distribution_purges_the_intermediate_tree_before_building(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The purge must be part of the build, not merely defined next to it.

    A purge helper that no build path invokes leaves a stale tree shipping
    modules that no longer exist in source.
    """
    stale = tmp_path / "build" / "lib" / "vellis"
    stale.mkdir(parents=True)
    (stale / "ghost.py").write_text("# deleted from source, still in build/\n")
    observed: list[bool] = []

    def recording_run(*arguments: str, cwd: Path, env: dict[str, str] | None = None):
        observed.append((tmp_path / "build").exists())
        return None

    monkeypatch.setattr(package_smoke, "_run", recording_run)
    _build_distribution(tmp_path, tmp_path / "dist", {})

    assert observed == [False], "the build ran against a tree that was not purged"


def test_only_build_distribution_can_run_a_uv_build() -> None:
    """The purge must be unavoidable, not merely available.

    Restoring a bare _run("uv", "build", ...) in main would rebuild through the
    uncleaned tree again, and every other test here would stay green.
    """
    source = (ROOT / "tools" / "package_smoke.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    permitted = {
        node
        for definition in ast.walk(module)
        if isinstance(definition, ast.FunctionDef) and definition.name == "_build_distribution"
        for node in ast.walk(definition)
    }

    offenders: list[str] = []
    for node in ast.walk(module):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"_run", "run"} or node in permitted:
            continue
        literals = [
            argument.value
            for argument in node.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        ]
        if literals[:2] == ["uv", "build"]:
            offenders.append(f"line {node.lineno}")

    assert offenders == [], (
        f"uv build invoked outside _build_distribution at {offenders}; "
        "such a build skips the purge of the stale intermediate tree"
    )


def test_module_digests_ignore_a_directory_setuptools_does_not_package(tmp_path: Path) -> None:
    """A scratch directory without __init__.py is not a missing module."""
    package = _mirror_source(tmp_path)
    scratch = package / "scratchdir"
    scratch.mkdir()
    (scratch / "note.py").write_text("# developer scratch, not packaged\n")

    _assert_installed_matches_source(package, "wheel")
