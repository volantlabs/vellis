"""Build and exercise the installable Vellis release artifacts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "2.0.0"


def _run(
    *arguments: str,
    cwd: Path = ROOT,
    env_updates: Mapping[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    if env_updates is not None:
        environment.update(env_updates)
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        env=environment,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def _assert_wheel(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        required = {
            "vellis/__init__.py",
            "vellis/__main__.py",
            "vellis/setup.py",
            "vellis/preserve.py",
            f"vellis-{VERSION}.dist-info/METADATA",
            f"vellis-{VERSION}.dist-info/entry_points.txt",
        }
        missing = required - names
        if missing:
            raise AssertionError(f"wheel omits required files: {sorted(missing)}")
        forbidden = [name for name in names if name.startswith(("tests/", ".data/"))]
        if forbidden:
            raise AssertionError(f"wheel contains non-product files: {forbidden[:5]}")
        metadata = archive.read(f"vellis-{VERSION}.dist-info/METADATA").decode()
        if f"Version: {VERSION}\n" not in metadata:
            raise AssertionError("wheel metadata version does not match the release version")
        entries = archive.read(f"vellis-{VERSION}.dist-info/entry_points.txt").decode()
        for command in ("vellis", "vellis-rtg-knowledge-graph"):
            if f"{command} = vellis.__main__:main" not in entries:
                raise AssertionError(f"wheel omits console entry point {command}")


def _assert_sdist(sdist: Path) -> None:
    prefix = f"vellis-{VERSION}/"
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
    required = {
        f"{prefix}LICENSE",
        f"{prefix}README.md",
        f"{prefix}pyproject.toml",
        f"{prefix}vellis/__init__.py",
        f"{prefix}vellis/__main__.py",
    }
    missing = required - names
    if missing:
        raise AssertionError(f"sdist omits required files: {sorted(missing)}")
    if any(name.startswith(f"{prefix}.data/") for name in names):
        raise AssertionError("sdist contains ignored owner data")


def _installed_smoke(wheel: Path, directory: Path) -> None:
    requirements = directory / "runtime-requirements.txt"
    environment = directory / "installed"
    invocation_directory = directory / "invocation"
    invocation_directory.mkdir()
    _run(
        "uv",
        "export",
        "--locked",
        "--no-dev",
        "--no-emit-project",
        "--output-file",
        str(requirements),
    )
    _run("uv", "venv", "--python", sys.executable, str(environment))
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    binary = environment / ("Scripts/vellis.exe" if os.name == "nt" else "bin/vellis")
    legacy = environment / (
        "Scripts/vellis-rtg-knowledge-graph.exe"
        if os.name == "nt"
        else "bin/vellis-rtg-knowledge-graph"
    )
    _run("uv", "pip", "install", "--python", str(python), "-r", str(requirements))
    _run("uv", "pip", "install", "--python", str(python), "--no-deps", str(wheel))

    for command, expected in (
        ((str(binary), "--help"), "usage: vellis "),
        ((str(binary), "setup", "--help"), "usage: vellis setup "),
        ((str(binary), "preserve", "--help"), "usage: vellis preserve "),
        ((str(binary), "restore", "--help"), "usage: vellis restore "),
        ((str(binary), "serve", "--help"), "usage: vellis serve "),
        ((str(binary), "serve-mcp", "--help"), "usage: vellis serve-mcp "),
        ((str(legacy), "--help"), "usage: vellis-rtg-knowledge-graph "),
        ((str(python), "-m", "vellis", "--help"), "usage: python -m vellis "),
        ((str(python), "-m", "vellis.setup", "--help"), "usage: python -m vellis.setup "),
        (
            (str(python), "-m", "vellis.preserve", "--help"),
            "usage: python -m vellis.preserve ",
        ),
        (
            (str(python), "-m", "vellis", "restore", "--help"),
            "usage: python -m vellis restore ",
        ),
    ):
        result = _run(*command, cwd=invocation_directory)
        if expected not in result.stdout:
            raise AssertionError(f"installed command {command!r} did not emit {expected!r}")
    imported = _run(
        str(python),
        "-c",
        "import vellis; print(vellis.__version__); print(vellis.__file__)",
        cwd=invocation_directory,
    )
    version, source = imported.stdout.splitlines()
    if version != VERSION:
        raise AssertionError(f"installed package reports {version!r}, not {VERSION}")
    if not Path(source).resolve().is_relative_to(environment.resolve()):
        raise AssertionError(f"smoke imported Vellis outside the isolated environment: {source}")

    fake_bin = directory / "fake-bin"
    fake_bin.mkdir()
    registration = directory / "codex-registration.json"
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        f"""#!{python}
import json
import os
import sys
from pathlib import Path

registration = Path(os.environ["VELLIS_SMOKE_REGISTRATION"])
arguments = sys.argv[1:]
if arguments == ["mcp", "get", "vellis", "--json"]:
    if not registration.exists():
        print("Error: No MCP server named 'vellis' found.", file=sys.stderr)
        raise SystemExit(1)
    target = json.loads(registration.read_text(encoding="utf-8"))
    print(json.dumps({{
        "name": "vellis",
        "enabled": True,
        "transport": {{"type": "stdio", "command": target[0], "args": target[1:]}},
    }}))
    raise SystemExit(0)
if arguments[:4] == ["mcp", "add", "vellis", "--"]:
    registration.write_text(json.dumps(arguments[4:]), encoding="utf-8")
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    client_environment = {
        "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
        "VELLIS_SMOKE_REGISTRATION": str(registration),
    }

    memory = directory / "memory"
    snapshot = directory / "snapshot.json"
    setup = _run(
        str(binary),
        "setup",
        "--data-dir",
        str(memory),
        "--vocabulary",
        "blank",
        "--client",
        "codex",
        "--yes",
        cwd=invocation_directory,
        env_updates=client_environment,
    )
    if (
        "established revision 0" not in setup.stdout
        or "MCP client codex: configured" not in setup.stdout
    ):
        raise AssertionError(
            "installed setup did not establish memory and configure the fake client"
        )
    target = tuple(json.loads(registration.read_text(encoding="utf-8")))
    expected_target = (
        str(python.absolute()),
        "-m",
        "vellis",
        "--data-dir",
        str(memory.resolve()),
    )
    if target != expected_target:
        raise AssertionError(f"installed setup registered {target!r}, not {expected_target!r}")
    preserve = _run(
        str(legacy),
        "preserve",
        "--data-dir",
        str(memory),
        "--out",
        str(snapshot),
        cwd=invocation_directory,
    )
    if "Preserved revision 0" not in preserve.stdout or not snapshot.is_file():
        raise AssertionError("installed legacy command did not publish a revision-zero snapshot")
    restore = _run(
        str(binary),
        "restore",
        "--data-dir",
        str(memory),
        "--revision",
        "0",
        "--yes",
        cwd=invocation_directory,
    )
    if "revision 0 is already current" not in restore.stdout:
        raise AssertionError("installed restore did not inspect the established revision")
    server = _run(
        str(binary),
        "serve",
        "--data-dir",
        str(memory),
        cwd=invocation_directory,
        input_text="",
    )
    if "Starting MCP server 'vellis'" not in server.stdout:
        raise AssertionError("installed serve did not start the pinned STDIO MCP boundary")
    registered_server = _run(
        *target,
        cwd=invocation_directory,
        input_text="",
    )
    if "Starting MCP server 'vellis'" not in registered_server.stdout:
        raise AssertionError("the installed client's exact persisted argv did not start Vellis")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="vellis-package-") as temporary:
        directory = Path(temporary)
        artifacts = directory / "dist"
        _run("uv", "build", "--out-dir", str(artifacts), "--no-build-logs")
        wheels = tuple(artifacts.glob("*.whl"))
        sdists = tuple(artifacts.glob("*.tar.gz"))
        if len(wheels) != 1 or len(sdists) != 1:
            raise AssertionError("package build did not produce exactly one wheel and one sdist")
        _assert_wheel(wheels[0])
        _assert_sdist(sdists[0])
        _installed_smoke(wheels[0], directory)
    print("Built, inspected, installed, and exercised Vellis 2.0.0 artifacts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
