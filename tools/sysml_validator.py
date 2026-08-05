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
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from jupyter_client.blocking.client import BlockingKernelClient
from jupyter_client.connect import write_connection_file

try:
    from .model_layout import (
        LANGUAGE_LOCK_PATH,
        MODEL_ROOT,
        RELEASE_CACHE_ROOT,
        ROOT,
        VALIDATOR_CACHE_ROOT,
        VALIDATOR_LOCK_PATH,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        LANGUAGE_LOCK_PATH,
        MODEL_ROOT,
        RELEASE_CACHE_ROOT,
        ROOT,
        VALIDATOR_CACHE_ROOT,
        VALIDATOR_LOCK_PATH,
    )

DIAGNOSTIC = re.compile(
    r"(?P<level>ERROR|WARNING):(?P<message>.*?)"
    r"\((?P<cell>\d+)\.sysml line : (?P<line>\d+) column : (?P<column>\d+)\)"
)
PACKAGE = re.compile(r"\bpackage\s+([A-Za-z_]\w*)\s*\{")
IMPORT = re.compile(r"\b(?:private|public)?\s*import\s+([A-Za-z_]\w*)::")


def _mask_non_code(text: str) -> str:
    """Mask comments and string literals while preserving offsets and newlines."""
    masked = list(text)
    index = 0
    state = "code"
    while index < len(text):
        current = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if state == "code":
            if current == "/" and following == "/":
                masked[index] = masked[index + 1] = " "
                index += 2
                state = "line-comment"
                continue
            if current == "/" and following == "*":
                masked[index] = masked[index + 1] = " "
                index += 2
                state = "block-comment"
                continue
            if current == '"':
                masked[index] = " "
                index += 1
                state = "string"
                continue
        elif state == "line-comment":
            if current == "\n":
                state = "code"
            else:
                masked[index] = " "
        elif state == "block-comment":
            if current == "*" and following == "/":
                masked[index] = masked[index + 1] = " "
                index += 2
                state = "code"
                continue
            if current != "\n":
                masked[index] = " "
        elif state == "string":
            if current == "\\" and following:
                if current != "\n":
                    masked[index] = " "
                if following != "\n":
                    masked[index + 1] = " "
                index += 2
                continue
            if current == '"':
                masked[index] = " "
                state = "code"
            elif current != "\n":
                masked[index] = " "
        index += 1
    return "".join(masked)


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


DOWNLOAD_READ_TIMEOUT_SECONDS = 300


def _download(url: str, expected: str, destination: Path) -> None:
    if destination.exists() and _sha256(destination) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "vellis-model-setup"})
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with (
            urllib.request.urlopen(  # noqa: S310
                request, timeout=DOWNLOAD_READ_TIMEOUT_SECONDS
            ) as response,
            temporary_path.open("wb") as stream,
        ):
            shutil.copyfileobj(response, stream)
        actual = _sha256(temporary_path)
        if actual != expected:
            raise RuntimeError(f"checksum mismatch for {url}: expected {expected}, found {actual}")
    except BaseException:
        # A partial or corrupt download must never be left behind: the next run
        # would either resume from it or report a confusing checksum failure.
        temporary_path.unlink(missing_ok=True)
        raise
    temporary_path.replace(destination)


def _git(*arguments: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(  # noqa: S603
        ["git", *arguments],
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(arguments)} failed:\n{completed.stderr.strip()}")
    return completed.stdout.strip()


def _setup_release_checkout() -> Path:
    """Materialise the pinned upstream release into the cache.

    A blobless sparse clone fetches only the paths the reference layer needs
    (12MB rather than 364MB), and Git's content addressing verifies every object,
    so pinning the commit is a stronger guarantee than per-file checksums.
    """
    lock = _json_object(LANGUAGE_LOCK_PATH)
    source = lock.get("source")
    if not isinstance(source, dict):
        raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing source")
    repository = str(source["repository"])
    tag = str(source["tag"])
    commit = str(source["commit"])
    paths = [str(entry) for entry in source["sparse_paths"]]
    checkout = RELEASE_CACHE_ROOT / tag

    if (checkout / ".git").is_dir():
        if _git("rev-parse", "HEAD", cwd=checkout) == commit:
            return checkout
        shutil.rmtree(checkout)

    checkout.parent.mkdir(parents=True, exist_ok=True)
    staged = checkout.with_name(f"{checkout.name}.partial")
    if staged.exists():
        shutil.rmtree(staged)
    try:
        _git(
            "clone",
            "--depth",
            "1",
            "--branch",
            tag,
            "--filter=blob:none",
            "--sparse",
            "--quiet",
            repository,
            str(staged),
        )
        _git("sparse-checkout", "set", "--no-cone", *paths, cwd=staged)
        actual = _git("rev-parse", "HEAD", cwd=staged)
        if actual != commit:
            raise RuntimeError(
                f"{repository} tag {tag} resolved to commit {actual}, expected {commit}"
            )
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    staged.replace(checkout)
    return checkout


def _setup_language_pdfs() -> list[Path]:
    checkout = _setup_release_checkout()
    lock = _json_object(LANGUAGE_LOCK_PATH)
    artifacts = lock.get("specifications")
    if not isinstance(artifacts, dict):
        raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing specification artifacts")
    pdfs: list[Path] = []
    for artifact_id in ("sysml_language_pdf", "kerml_language_pdf"):
        artifact = artifacts.get(artifact_id)
        if not isinstance(artifact, dict):
            raise RuntimeError(f"{LANGUAGE_LOCK_PATH}: missing {artifact_id}")
        source_pdf = checkout / str(artifact["path"])
        if not source_pdf.is_file():
            raise RuntimeError(f"{artifact_id}: {source_pdf} is absent from the pinned checkout")
        actual = _sha256(source_pdf)
        if actual != str(artifact["sha256"]):
            raise RuntimeError(
                f"{artifact_id}: checksum mismatch in the pinned checkout: "
                f"expected {artifact['sha256']}, found {actual}"
            )
        pdfs.append(source_pdf)
    return pdfs


def _platform_key() -> str:
    machine = platform.machine().lower()
    if machine == "aarch64":
        machine = "arm64"
    return f"{platform.system().lower()}-{machine}"


def _java_path(runtime: Path) -> Path:
    mac = runtime / "Contents" / "Home" / "bin" / "java"
    return mac if mac.exists() else runtime / "bin" / "java"


def _setup_validator() -> tuple[Path, Path, Path]:
    lock = _json_object(VALIDATOR_LOCK_PATH)
    version = str(lock["implementation_version"])
    destination = VALIDATOR_CACHE_ROOT / version
    kernel = lock["kernel"]
    if not isinstance(kernel, dict):
        raise RuntimeError(f"{VALIDATOR_LOCK_PATH}: invalid kernel metadata")
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
    if not isinstance(java_lock, dict) or not isinstance(java_lock.get("platforms"), dict):
        raise RuntimeError(f"{VALIDATOR_LOCK_PATH}: invalid Java metadata")
    key = _platform_key()
    artifact = java_lock["platforms"].get(key)
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
            temporary = destination / f"java-{key}.moving"
            children[0].replace(temporary)
            runtime.rmdir()
            temporary.replace(runtime)
        java = _java_path(runtime)
    if not java.exists():
        raise RuntimeError("pinned Java runtime did not contain a java executable")
    return java, jar, library


def setup() -> tuple[list[Path], Path, Path, Path]:
    pdfs = _setup_language_pdfs()
    java, jar, library = _setup_validator()
    return pdfs, java, jar, library


def _model_files() -> list[Path]:
    files = sorted(MODEL_ROOT.glob("*.sysml"), key=lambda path: path.name)
    if not files:
        raise RuntimeError(f"no SysML model files found in {MODEL_ROOT}")
    return files


def _check_packages_and_import_order(files: list[Path]) -> None:
    package_files: dict[str, Path] = {}
    imports_by_file: dict[Path, set[str]] = {}
    for path in files:
        text = _mask_non_code(path.read_text(encoding="utf-8"))
        packages = PACKAGE.findall(text)
        if not packages:
            raise RuntimeError(f"{path.relative_to(ROOT)} does not declare a package")
        if len(packages) != 1:
            raise RuntimeError(
                f"{path.relative_to(ROOT)} must declare exactly one package, found {packages}"
            )
        package = packages[0]
        previous = package_files.get(package)
        if previous is not None:
            raise RuntimeError(
                f"package {package} is declared by both {previous.relative_to(ROOT)} "
                f"and {path.relative_to(ROOT)}"
            )
        package_files[package] = path
        imports_by_file[path] = set(IMPORT.findall(text))
    position = {path: index for index, path in enumerate(files)}
    for path, imports in imports_by_file.items():
        for imported_package in imports:
            dependency = package_files.get(imported_package)
            if dependency is not None and position[dependency] >= position[path]:
                raise RuntimeError(
                    f"{path.relative_to(ROOT)} imports {imported_package} from "
                    f"{dependency.relative_to(ROOT)}, which is not earlier in filename order"
                )


@contextmanager
def _kernel_session() -> Iterator[BlockingKernelClient]:
    _, java, jar, library = setup()
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
        try:
            client.load_connection_file()
            client.start_channels()
            time.sleep(3)
            if process.poll() is not None:
                raise RuntimeError(
                    "official Java kernel exited during startup:\n"
                    + log_path.read_text(encoding="utf-8")
                )
            client.kernel_info()
            client.get_shell_msg(timeout=90)
            yield client
        finally:
            client.stop_channels()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _execute_source(client: BlockingKernelClient, source: str) -> list[str]:
    diagnostics: list[str] = []
    message_id = client.execute(source)
    while True:
        message = client.get_iopub_msg(timeout=120)
        if message["parent_header"].get("msg_id") != message_id:
            continue
        content = message["content"]
        if message["msg_type"] == "stream":
            lines = str(content.get("text", "")).splitlines()
            if content.get("name") == "stderr":
                diagnostics.extend(lines)
            else:
                diagnostics.extend(line for line in lines if DIAGNOSTIC.search(line))
        elif message["msg_type"] == "error":
            diagnostics.extend(str(line) for line in content.get("traceback", []))
        elif message["msg_type"] == "status" and content.get("execution_state") == "idle":
            break
    return diagnostics


def validate(*, self_test: bool = False) -> int:
    files = _model_files()
    _check_packages_and_import_order(files)
    diagnostics: list[str] = []
    negative: list[str] = []
    with _kernel_session() as client:
        for path in files:
            diagnostics.extend(_execute_source(client, path.read_text(encoding="utf-8")))
    if self_test:
        with _kernel_session() as client:
            negative = _execute_source(
                client,
                "package VellisValidatorNegative_7F3A { "
                "part def Broken :> VellisMissingType_7F3A; }",
            )

    failed = False
    if self_test and not any(
        match and match.group("level") == "ERROR"
        for line in negative
        if (match := DIAGNOSTIC.search(line))
    ):
        print("ERROR formal validator negative self-test accepted an unresolved type")
        failed = True
    labels = [path.relative_to(ROOT).as_posix() for path in files]
    for diagnostic in diagnostics:
        match = DIAGNOSTIC.search(diagnostic)
        if match:
            cell = int(match.group("cell"))
            label = labels[cell - 1] if 0 < cell <= len(labels) else "model"
            level = match.group("level")
            print(
                f"{level} {label}:{match.group('line')}:{match.group('column')}:"
                f"{match.group('message').strip()}"
            )
            failed = failed or level in {"ERROR", "WARNING"}
        elif diagnostic.strip():
            print(f"ERROR {diagnostic.strip()}")
            failed = True
    if failed:
        print("Formal SysML validation failed.")
        return 1
    version = _json_object(VALIDATOR_LOCK_PATH)["implementation_version"]
    print(
        f"Formal SysML validation passed for {len(files)} files with official Java pilot {version}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Pinned official SysML v2 validator adapter")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("setup")
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--self-test", action="store_true")
    arguments = parser.parse_args()
    if arguments.command == "setup":
        pdfs, java, jar, library = setup()
        for pdf in pdfs:
            print(f"Pinned specification: {pdf}")
        print(f"Pinned Java: {java}")
        print(f"Pinned validator: {jar}")
        print(f"Pinned library: {library}")
        return 0
    return validate(self_test=arguments.self_test)


if __name__ == "__main__":
    raise SystemExit(main())
