import ast
from pathlib import Path

import pytest

from tools.package_smoke import ROOT, _run_isolated_tool


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
