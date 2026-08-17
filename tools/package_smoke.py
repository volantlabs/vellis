"""Build and exercise the installable Vellis release artifacts."""

from __future__ import annotations

import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "2.0.0"


def _run(*arguments: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        env=environment,
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
