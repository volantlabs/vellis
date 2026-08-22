from pathlib import Path

import pytest

from tools.package_smoke import _run_isolated_tool


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


def test_run_isolated_tool_rejects_missing_overrides(tmp_path: Path) -> None:
    temporary = tmp_path / "isolated"
    temporary.mkdir()

    with pytest.raises(KeyError):
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
