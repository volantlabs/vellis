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
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from jupyter_client.blocking.client import BlockingKernelClient
from jupyter_client.connect import write_connection_file

try:
    from .model_layout import (
        MODEL_PACKAGE_ROOT,
        MODEL_ROOT,
        ROOT,
        SOFTWARE_COMPONENT_PATTERN_PATH,
        VALIDATOR_CACHE_ROOT,
        VALIDATOR_LOCK_PATH,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        MODEL_PACKAGE_ROOT,
        MODEL_ROOT,
        ROOT,
        SOFTWARE_COMPONENT_PATTERN_PATH,
        VALIDATOR_CACHE_ROOT,
        VALIDATOR_LOCK_PATH,
    )

LOCK_PATH = VALIDATOR_LOCK_PATH
CACHE_ROOT = VALIDATOR_CACHE_ROOT
JAVA_HEADLESS_OPTION = "-Djava.awt.headless=true"

MODEL_ORDER = (
    "foundation/SoftwareComponentModeling.sysml",
    "bibliotek/shared-values/SoftwareValues.sysml",
    "bibliotek/shared-values/RtgDiagnostics.sysml",
    "bibliotek/shared-values/RtgChangeValues.sysml",
    "bibliotek/shared-values/RuntimeMessaging.sysml",
    "bibliotek/components/component.runtime.message_runtime.sysml",
    "bibliotek/components/component.runtime.component_adapter.sysml",
    "bibliotek/components/component.interface.mcp_gateway.sysml",
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
    "bibliotek/realizations/BibliotekRuntimePython.sysml",
    "bibliotek/Bibliotek.sysml",
    "bibliotek/views/BibliotekViews.sysml",
    "vellis/EverydayLifeOntology.sysml",
    "vellis/VellisOperations.sysml",
    "vellis/Vellis.sysml",
    "vellis/use-cases/VellisUseCases.sysml",
    "vellis/realizations/VellisLocalPython.sysml",
    "vellis/realizations/VellisRuntimePython.sysml",
    "vellis/realizations/VellisMcpPython.sysml",
    "vellis/views/VellisViews.sysml",
)

PACKAGE_ARCHIVES = {
    "foundation": "software-component-modeling-foundation-0.1.0.kpar",
    "bibliotek": "bibliotek-0.1.0.kpar",
    "vellis": "vellis-0.1.0.kpar",
}

DIAGNOSTIC = re.compile(
    r"(?P<level>ERROR|WARNING):(?P<message>.*?)"
    r"\((?P<cell>\d+)\.sysml line : (?P<line>\d+) column : (?P<column>\d+)\)"
)
LISTING_LINE = re.compile(
    r"^(?P<kind>[A-Za-z_]\w*)(?:\s+(?P<name>.*?))?\s+"
    r"\([0-9a-fA-F-]{36}\)$"
)
INDEXED_ELEMENT_KINDS = {
    "AllocationUsage",
    "RequirementUsage",
    "SatisfyRequirementUsage",
    "UseCaseUsage",
    "ViewUsage",
}


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


def _authored_model_files() -> set[str]:
    return {
        path.relative_to(MODEL_ROOT).as_posix()
        for path in MODEL_ROOT.rglob("*.sysml")
        if not {".cache", "dist"}.intersection(path.relative_to(MODEL_ROOT).parts)
    }


def _check_inventory_and_order() -> None:
    authored = _authored_model_files()
    ordered = set(MODEL_ORDER)
    missing = sorted(authored - ordered)
    stale = sorted(ordered - authored)
    if missing or stale:
        raise RuntimeError(
            f"validator model inventory differs: unlisted={missing}, missing={stale}"
        )

    package_files: dict[str, str] = {}
    imports_by_file: dict[str, set[str]] = {}
    for relative in MODEL_ORDER:
        text = (MODEL_ROOT / relative).read_text(encoding="utf-8")
        package_match = re.search(r"\b(?:library\s+)?package\s+([A-Za-z_]\w*)\s*\{", text)
        if not package_match:
            raise RuntimeError(f"{relative} does not declare a package")
        package = package_match.group(1)
        if package in package_files:
            raise RuntimeError(
                f"package {package} is declared by both {package_files[package]} and {relative}"
            )
        package_files[package] = relative
        imports_by_file[relative] = set(
            re.findall(
                r"\b(?:private|public)?\s*import\s+([A-Za-z_]\w*)::",
                text,
            )
        )

    position = {relative: index for index, relative in enumerate(MODEL_ORDER)}
    for relative, imports in imports_by_file.items():
        for imported_package in imports:
            dependency = package_files.get(imported_package)
            if dependency is not None and position[dependency] >= position[relative]:
                raise RuntimeError(
                    f"validator load order places {relative} before imported package "
                    f"{imported_package} in {dependency}"
                )


def _model_files(scope: str) -> list[Path]:
    _check_inventory_and_order()
    allowed = {
        "foundation": ("foundation/",),
        "bibliotek": ("foundation/", "bibliotek/"),
        "vellis": ("foundation/", "bibliotek/", "vellis/"),
        "all": ("foundation/", "bibliotek/", "vellis/", "realizations/"),
    }[scope]
    return [MODEL_ROOT / relative for relative in MODEL_ORDER if relative.startswith(allowed)]


def _packaged_model_files(scope: str, destination: Path) -> tuple[list[Path], list[str]]:
    _check_inventory_and_order()
    products = {
        "foundation": ("foundation",),
        "bibliotek": ("foundation", "bibliotek"),
        "vellis": ("foundation", "bibliotek", "vellis"),
    }[scope]
    extracted_by_name: dict[str, Path] = {}
    labels_by_name: dict[str, str] = {}
    for product in products:
        archive_path = MODEL_PACKAGE_ROOT / PACKAGE_ARCHIVES[product]
        if not archive_path.exists():
            raise RuntimeError(f"missing packaged model artifact: {archive_path}")
        product_root = destination / product
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(product_root)
        for path in product_root.rglob("*.sysml"):
            if path.name in extracted_by_name:
                raise RuntimeError(f"duplicate packaged model filename: {path.name}")
            extracted_by_name[path.name] = path
            labels_by_name[path.name] = f"{archive_path.name}!/{path.name}"

    allowed = {
        "foundation": ("foundation/",),
        "bibliotek": ("foundation/", "bibliotek/"),
        "vellis": ("foundation/", "bibliotek/", "vellis/"),
    }[scope]
    relatives = [relative for relative in MODEL_ORDER if relative.startswith(allowed)]
    files: list[Path] = []
    labels: list[str] = []
    for relative in relatives:
        name = Path(relative).name
        path = extracted_by_name.get(name)
        if path is None:
            raise RuntimeError(f"packaged {scope} product omits {relative}")
        files.append(path)
        labels.append(labels_by_name[name])
    unexpected = sorted(set(extracted_by_name) - {path.name for path in files})
    if unexpected:
        raise RuntimeError(f"packaged {scope} product has unexpected SysML files: {unexpected}")
    source_by_name = {Path(relative).name: MODEL_ROOT / relative for relative in relatives}
    stale = [
        name
        for name, packaged_path in extracted_by_name.items()
        if name in source_by_name
        and packaged_path.read_bytes() != source_by_name[name].read_bytes()
    ]
    if stale:
        raise RuntimeError(
            f"packaged {scope} product is stale for current model sources: {sorted(stale)}; "
            "run `just model-package`"
        )
    return files, labels


@contextmanager
def _kernel_session() -> Iterator[BlockingKernelClient]:
    java, jar, library = setup()
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
                    JAVA_HEADLESS_OPTION,
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


def _execute_source(
    client: BlockingKernelClient, source: str
) -> tuple[list[str], list[dict[str, Any]]]:
    diagnostics: list[str] = []
    outputs: list[dict[str, Any]] = []
    message_id = client.execute(source)
    while True:
        message = client.get_iopub_msg(timeout=120)
        if message["parent_header"].get("msg_id") != message_id:
            continue
        message_type = message["msg_type"]
        content = message["content"]
        if message_type == "stream" and content.get("name") == "stderr":
            diagnostics.extend(str(content.get("text", "")).splitlines())
        elif message_type == "error":
            diagnostics.extend(str(line) for line in content.get("traceback", []))
        elif message_type in {"display_data", "execute_result"}:
            data = content.get("data", {})
            if isinstance(data, dict):
                outputs.append(data)
        elif message_type == "status" and content.get("execution_state") == "idle":
            break
    return diagnostics, outputs


def _validate_files(
    files: list[Path], labels: list[str], self_test: bool, product_label: str
) -> int:
    diagnostics: list[str] = []
    negative_diagnostics: list[str] = []
    with _kernel_session() as client:
        if self_test:
            negative_diagnostics, _ = _execute_source(
                client, "package ValidatorNegative { part def Broken :> MissingType; }"
            )
        for path in files:
            captured, _ = _execute_source(client, path.read_text(encoding="utf-8"))
            diagnostics.extend(captured)

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
            label = labels[cell - 1] if 0 < cell <= len(labels) else "model"
            level = match.group("level")
            print(
                f"{level} {label}:{match.group('line')}:{match.group('column')}:"
                f"{match.group('message').strip()}"
            )
            failed = failed or level == "ERROR"
        elif diagnostic.strip():
            print(f"ERROR {diagnostic.strip()}")
            failed = True
    if failed:
        print(f"Formal SysML validation failed for {product_label}.")
        return 1
    print(
        f"Formal SysML validation passed for {product_label} ({len(files)} files) "
        f"with official Java pilot {_lock()['implementation_version']}."
    )
    return 0


def validate(scope: str, self_test: bool = False, packaged: bool = False) -> int:
    if packaged:
        if scope == "all":
            raise RuntimeError("packaged validation requires a concrete product scope")
        with tempfile.TemporaryDirectory(prefix=f"vellis-{scope}-kpar-") as temporary:
            files, labels = _packaged_model_files(scope, Path(temporary))
            return _validate_files(files, labels, self_test, f"packaged {scope}")
    files = _model_files(scope)
    labels = [path.relative_to(ROOT).as_posix() for path in files]
    return _validate_files(files, labels, self_test, f"source {scope}")


def validate_products(self_test: bool = False) -> int:
    for scope in ("foundation", "bibliotek", "vellis"):
        if validate(scope, self_test=self_test, packaged=True):
            return 1
    return validate_fixture(self_test=self_test)


def validate_fixture(self_test: bool = False) -> int:
    with tempfile.TemporaryDirectory(prefix="vellis-foundation-fixture-") as temporary:
        files, labels = _packaged_model_files("foundation", Path(temporary))
        files.append(SOFTWARE_COMPONENT_PATTERN_PATH)
        labels.append(SOFTWARE_COMPONENT_PATTERN_PATH.relative_to(ROOT).as_posix())
        return _validate_files(files, labels, self_test, "foundation modeling fixture")


def _source_digest(files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(MODEL_ROOT).as_posix()):
        relative = path.relative_to(MODEL_ROOT).as_posix()
        digest.update(relative.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def export_index(output: Path) -> None:
    files = _model_files("all")
    package_sources: dict[str, str] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        match = re.search(r"\b(?:library\s+)?package\s+([A-Za-z_]\w*)\s*\{", text)
        if not match:
            raise RuntimeError(f"{path} does not declare a package")
        package_sources[match.group(1)] = path.relative_to(ROOT).as_posix()

    package_indexes: dict[str, dict[str, Any]] = {}
    with _kernel_session() as client:
        for path in files:
            diagnostics, _ = _execute_source(client, path.read_text(encoding="utf-8"))
            if any(DIAGNOSTIC.search(line) for line in diagnostics):
                raise RuntimeError(
                    f"cannot export invalid model {path.relative_to(ROOT)}:\n"
                    + "\n".join(diagnostics)
                )
        for package, source in sorted(package_sources.items()):
            diagnostics, outputs = _execute_source(client, f"%list {package}::**")
            if diagnostics:
                raise RuntimeError(f"listing of {package} failed:\n" + "\n".join(diagnostics))
            listing = next(
                (
                    value
                    for result in outputs
                    if isinstance((value := result.get("text/plain")), str)
                ),
                None,
            )
            if listing is None:
                raise RuntimeError(f"official Java pilot did not list package {package}")
            named_elements: list[dict[str, str]] = []
            for line in listing.splitlines():
                match = LISTING_LINE.match(line.strip())
                if not match:
                    if line.strip():
                        raise RuntimeError(
                            f"unrecognized official listing line for {package}: {line}"
                        )
                    continue
                listed_name = match.group("name") or ""
                identification = re.match(r"<([^>]+)>\s+(.*)", listed_name)
                element = {
                    "kind": match.group("kind"),
                    "name": identification.group(2) if identification else listed_name,
                }
                if identification:
                    element["short_name"] = identification.group(1)
                named_elements.append(element)
            counts = Counter(element["kind"] for element in named_elements)
            contract_elements = [
                element
                for element in named_elements
                if element["name"]
                and (
                    element["kind"].endswith("Definition")
                    or element["kind"] in INDEXED_ELEMENT_KINDS
                )
            ]
            package_indexes[package] = {
                "source": source,
                "element_counts": dict(sorted(counts.items())),
                "named_elements": sorted(
                    contract_elements, key=lambda item: (item["kind"], item["name"])
                ),
            }

    value = {
        "schema_version": 1,
        "source_digest": _source_digest(files),
        "validator": {
            "provider": _lock()["provider"],
            "release": _lock()["release"],
            "implementation_version": _lock()["implementation_version"],
        },
        "authored_packages": dict(sorted(package_sources.items())),
        "packages": package_indexes,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Exported official parser-backed model index to {output.resolve().relative_to(ROOT)}.")


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
    validate_parser.add_argument(
        "--packaged",
        action="store_true",
        help="validate sources extracted from the packaged product artifact",
    )
    products_parser = subparsers.add_parser("validate-products")
    products_parser.add_argument("--self-test", action="store_true")
    fixture_parser = subparsers.add_parser("validate-fixture")
    fixture_parser.add_argument("--self-test", action="store_true")
    export_parser = subparsers.add_parser("export-index")
    export_parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "setup":
        java, jar, library = setup()
        print(f"Pinned Java: {java}")
        print(f"Pinned validator: {jar}")
        print(f"Pinned library: {library}")
        return 0
    if arguments.command == "validate-products":
        return validate_products(arguments.self_test)
    if arguments.command == "validate-fixture":
        return validate_fixture(arguments.self_test)
    if arguments.command == "export-index":
        export_index(arguments.output)
        return 0
    return validate(arguments.scope, arguments.self_test, arguments.packaged)


if __name__ == "__main__":
    raise SystemExit(main())
