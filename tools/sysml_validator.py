from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from jupyter_client.blocking.client import BlockingKernelClient
from jupyter_client.connect import write_connection_file

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "model"
LOCK_PATH = MODEL_ROOT / "validator.lock.json"
CACHE_ROOT = MODEL_ROOT / ".cache" / "validator"

MODEL_ORDER = (
    "foundation/SoftwareComponentModeling.sysml",
    "foundation/SoftwareComponentPattern.sysml",
    "bibliotek/shared-values/SoftwareValues.sysml",
    "bibliotek/shared-values/RtgDiagnostics.sysml",
    "bibliotek/components/component.storage.json_file.sysml",
    "bibliotek/components/component.storage.sql.sysml",
    "bibliotek/components/component.rtg.graph.sysml",
    "bibliotek/components/component.rtg.schema.sysml",
    "bibliotek/components/component.rtg.migration.sysml",
    "bibliotek/components/component.rtg.query.sysml",
    "bibliotek/components/component.rtg.constraints.sysml",
    "bibliotek/components/component.rtg.change_validation.sysml",
    "bibliotek/components/component.rtg.discovery.sysml",
    "bibliotek/components/component.rtg.controller.sysml",
    "bibliotek/Bibliotek.sysml",
    "bibliotek/views/BibliotekViews.sysml",
    "vellis/VellisOperations.sysml",
    "vellis/Vellis.sysml",
    "vellis/use-cases/VellisUseCases.sysml",
    "vellis/realizations/VellisLocalPython.sysml",
    "vellis/realizations/VellisMcpPython.sysml",
    "vellis/views/VellisViews.sysml",
    "realizations/PythonImplementationDrift.sysml",
)

DIAGNOSTIC = re.compile(
    r"(?P<level>ERROR|WARNING):(?P<message>.*?)"
    r"\((?P<cell>\d+)\.sysml line : (?P<line>\d+) column : (?P<column>\d+)\)"
)


def _lock() -> dict[str, Any]:
    value = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("validator lock must be a JSON object")
    return value


def _platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine == "aarch64":
        machine = "arm64"
    return f"{system}-{machine}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, expected: str, destination: Path) -> None:
    if destination.exists() and _sha256(destination) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "vellis-sysml-validator"})
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            shutil.copyfileobj(response, temporary)
    if _sha256(temporary_path) != expected:
        temporary_path.unlink(missing_ok=True)
        raise RuntimeError(f"checksum mismatch for {url}")
    temporary_path.replace(destination)


def _java_path(runtime: Path) -> Path:
    mac = runtime / "Contents" / "Home" / "bin" / "java"
    return mac if mac.exists() else runtime / "bin" / "java"


def setup() -> tuple[Path, Path, Path]:
    lock = _lock()
    version = str(lock["implementation_version"])
    destination = CACHE_ROOT / version
    kernel = lock["kernel"]
    assert isinstance(kernel, dict)
    kernel_archive = destination / "downloads" / "kernel.zip"
    _download(str(kernel["url"]), str(kernel["sha256"]), kernel_archive)
    kernel_root = destination / "kernel"
    jar = kernel_root / str(kernel["jar"])
    library = kernel_root / str(kernel["library"])
    if not jar.exists() or not library.is_dir():
        shutil.rmtree(kernel_root, ignore_errors=True)
        kernel_root.mkdir(parents=True)
        with zipfile.ZipFile(kernel_archive) as archive:
            archive.extractall(kernel_root)

    java_lock = lock["java"]
    assert isinstance(java_lock, dict)
    platforms = java_lock["platforms"]
    assert isinstance(platforms, dict)
    key = _platform_key()
    artifact = platforms.get(key)
    if not isinstance(artifact, dict):
        raise RuntimeError(f"no pinned Java runtime for {key}")
    java_archive = destination / "downloads" / f"java-{key}.tar.gz"
    _download(str(artifact["url"]), str(artifact["sha256"]), java_archive)
    runtime = destination / f"java-{key}"
    java = _java_path(runtime)
    if not java.exists():
        shutil.rmtree(runtime, ignore_errors=True)
        runtime.mkdir(parents=True)
        with tarfile.open(java_archive) as archive:
            archive.extractall(runtime, filter="data")
        children = [path for path in runtime.iterdir() if path.is_dir()]
        if len(children) == 1 and not _java_path(runtime).exists():
            extracted = children[0]
            temporary = destination / f"java-{key}.moving"
            extracted.replace(temporary)
            runtime.rmdir()
            temporary.replace(runtime)
        java = _java_path(runtime)
    if not java.exists():
        raise RuntimeError("pinned Java runtime did not contain a java executable")
    return java, jar, library


def _model_files(scope: str) -> list[Path]:
    allowed = {
        "foundation": ("foundation/",),
        "bibliotek": ("foundation/", "bibliotek/"),
        "vellis": ("foundation/", "bibliotek/", "vellis/"),
        "all": ("foundation/", "bibliotek/", "vellis/", "realizations/"),
    }[scope]
    return [MODEL_ROOT / relative for relative in MODEL_ORDER if relative.startswith(allowed)]


def validate(scope: str, self_test: bool = False) -> int:
    java, jar, library = setup()
    files = _model_files(scope)
    with tempfile.TemporaryDirectory(prefix="vellis-sysml-") as temporary:
        connection_file = Path(temporary) / "kernel.json"
        write_connection_file(str(connection_file))
        environment = os.environ.copy()
        environment["ISYSML_LIBRARY_PATH"] = str(library)
        log_path = Path(temporary) / "kernel.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(  # noqa: S603
                [
                    str(java),
                    "-cp",
                    str(jar),
                    "org.omg.sysml.jupyter.kernel.ISysML",
                    str(connection_file),
                ],
                cwd=jar.parent,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        client = BlockingKernelClient(connection_file=str(connection_file))
        client.load_connection_file()
        client.start_channels()
        diagnostics: list[str] = []
        negative_diagnostics: list[str] = []
        try:
            time.sleep(3)
            client.kernel_info()
            client.get_shell_msg(timeout=90)

            def execute_source(source: str) -> list[str]:
                captured: list[str] = []
                message_id = client.execute(source)
                while True:
                    message = client.get_iopub_msg(timeout=120)
                    if message["parent_header"].get("msg_id") != message_id:
                        continue
                    message_type = message["msg_type"]
                    content = message["content"]
                    if message_type == "stream" and content.get("name") == "stderr":
                        captured.extend(str(content.get("text", "")).splitlines())
                    elif message_type == "error":
                        captured.extend(str(line) for line in content.get("traceback", []))
                    elif message_type == "status" and content.get("execution_state") == "idle":
                        break
                return captured

            if self_test:
                negative_diagnostics = execute_source(
                    "package ValidatorNegative { part def Broken :> MissingType; }"
                )
            for path in files:
                diagnostics.extend(execute_source(path.read_text(encoding="utf-8")))
        finally:
            client.stop_channels()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

    failed = False
    cell_offset = 1 if self_test else 0
    if self_test and not any(
        match and match.group("level") == "ERROR"
        for diagnostic in negative_diagnostics
        if (match := DIAGNOSTIC.search(diagnostic))
    ):
        print("ERROR formal validator negative self-test accepted an unresolved type")
        failed = True
    for diagnostic in diagnostics:
        match = DIAGNOSTIC.search(diagnostic)
        if match:
            cell = int(match.group("cell")) - cell_offset
            path = files[cell - 1] if 0 < cell <= len(files) else MODEL_ROOT
            relative = path.relative_to(ROOT)
            level = match.group("level")
            print(
                f"{level} {relative}:{match.group('line')}:{match.group('column')}:"
                f"{match.group('message').strip()}"
            )
            failed = failed or level == "ERROR"
        elif diagnostic.strip():
            print(f"ERROR {diagnostic.strip()}")
            failed = True
    if failed:
        print("Formal SysML validation failed.")
        return 1
    print(
        f"Formal SysML validation passed for {len(files)} files "
        f"with official Java pilot { _lock()['implementation_version'] }."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pinned official SysML v2 Java validator adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument(
        "--scope", choices=("foundation", "bibliotek", "vellis", "all"), default="all"
    )
    validate_parser.add_argument(
        "--self-test",
        action="store_true",
        help="require the official validator to reject an unresolved-type probe before validation",
    )
    arguments = parser.parse_args()
    if arguments.command == "setup":
        java, jar, library = setup()
        print(f"Pinned Java: {java}")
        print(f"Pinned validator: {jar}")
        print(f"Pinned library: {library}")
        return 0
    return validate(arguments.scope, arguments.self_test)


if __name__ == "__main__":
    raise SystemExit(main())
