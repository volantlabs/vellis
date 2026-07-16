from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

try:
    from .model_layout import GENERATED_FORMAL_INDEX, REFERENCE_DOC_ROOT, ROOT
    from .sysml_validator import (
        DIAGNOSTIC,
        JAVA_HEADLESS_OPTION,
        _execute_source,
        _kernel_session,
        _model_files,
        _source_digest,
        setup,
    )
except ImportError:  # pragma: no cover - direct script execution
    from model_layout import (  # type: ignore[no-redef]
        GENERATED_FORMAL_INDEX,
        REFERENCE_DOC_ROOT,
        ROOT,
    )
    from sysml_validator import (  # type: ignore[no-redef]
        DIAGNOSTIC,
        JAVA_HEADLESS_OPTION,
        _execute_source,
        _kernel_session,
        _model_files,
        _source_digest,
        setup,
    )

DIAGRAM_ID = re.compile(r"diagram\.(?P<product>[a-z0-9_]+)\.(?P<name>[a-z0-9_.]+)\Z")
PSYSML_LINK = re.compile(r"\[\[psysml:[^\]]+\]\]")
SVG_TEXT_METRIC = re.compile(rb'\s+(?:lengthAdjust|textLength)="[^"]*"')
REJECTED_OUTPUT_MARKERS = ("ERROR:", "EXCEEDS THE LIMIT")
SUPPORTED_RENDERINGS = {"asTreeDiagram", "asInterconnectionDiagram"}


@dataclass(frozen=True, slots=True)
class DiagramSpec:
    diagram_id: str
    product: str
    name: str
    package: str
    view_name: str
    rendering: str

    @property
    def qualified_name(self) -> str:
        return f"{self.package}::{self.view_name}"

    def artifact_path(self, suffix: str) -> Path:
        return Path(self.product) / "diagrams" / f"{self.name}.{suffix}"


class DiagramBackend(Protocol):
    def generate(self, specs: tuple[DiagramSpec, ...]) -> dict[Path, bytes]: ...


def _view_block(source: str, view_name: str) -> str:
    match = re.search(
        rf"\bview\s+(?:<'[^']+'>\s+)?{re.escape(view_name)}(?:\s*:[^{{]+)?\s*\{{",
        source,
    )
    if match is None:
        raise ValueError(f"registered view {view_name} is not declared in its indexed source")
    depth = 0
    for index in range(source.index("{", match.start()), len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start() : index + 1]
    raise ValueError(f"registered view {view_name} has an unterminated body")


def _view_rendering(source: str, view_name: str) -> str:
    block = _view_block(source, view_name)
    renderings = re.findall(r"\brender\s+(as\w+)\s*;", block)
    if len(renderings) != 1 or renderings[0] not in SUPPORTED_RENDERINGS:
        raise ValueError(
            f"registered view {view_name} must render exactly once as one of "
            f"{sorted(SUPPORTED_RENDERINGS)}"
        )
    return renderings[0]


def discover_diagrams(index: dict[str, Any], *, root: Path = ROOT) -> tuple[DiagramSpec, ...]:
    packages = index.get("packages")
    if not isinstance(packages, dict):
        raise ValueError("formal model index has no package inventory")
    specs: list[DiagramSpec] = []
    seen: set[str] = set()
    for package, details in sorted(packages.items()):
        if not isinstance(details, dict):
            continue
        source_name = details.get("source")
        elements = details.get("named_elements")
        if not isinstance(source_name, str) or not isinstance(elements, list):
            continue
        source = (root / source_name).read_text(encoding="utf-8")
        for element in elements:
            if not isinstance(element, dict) or element.get("kind") != "ViewUsage":
                continue
            diagram_id = element.get("short_name")
            if not isinstance(diagram_id, str) or not diagram_id.startswith("diagram."):
                continue
            match = DIAGRAM_ID.fullmatch(diagram_id)
            if match is None:
                raise ValueError(f"invalid registered diagram ID: {diagram_id}")
            if diagram_id in seen:
                raise ValueError(f"duplicate registered diagram ID: {diagram_id}")
            view_name = element.get("name")
            if not isinstance(view_name, str) or not view_name:
                raise ValueError(f"registered diagram {diagram_id} has no view name")
            seen.add(diagram_id)
            specs.append(
                DiagramSpec(
                    diagram_id=diagram_id,
                    product=match.group("product"),
                    name=match.group("name"),
                    package=str(package),
                    view_name=view_name,
                    rendering=_view_rendering(source, view_name),
                )
            )
    return tuple(sorted(specs, key=lambda item: item.diagram_id))


def load_registered_diagrams(index_path: Path = GENERATED_FORMAL_INDEX) -> tuple[DiagramSpec, ...]:
    if not index_path.exists():
        raise RuntimeError(f"missing parser inventory {index_path.relative_to(ROOT)}")
    index = json.loads(index_path.read_text(encoding="utf-8"))
    files = _model_files("all")
    if index.get("source_digest") != _source_digest(files):
        raise RuntimeError("formal model index is stale; regenerate it before rendering diagrams")
    specs = discover_diagrams(index)
    if not specs:
        raise RuntimeError("official parser inventory contains no registered diagram views")
    return specs


def normalize_plantuml(value: str) -> bytes:
    normalized = PSYSML_LINK.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    normalized = normalized.replace("part  def", "part def")
    normalized = normalized.replace("skinparam wrapWidth 300", "skinparam wrapWidth 380")
    normalized = normalized.replace("##//doc//##\n", "")
    normalized = re.sub(r"\s{2,}(?=\")", "", normalized).strip()
    if not normalized:
        raise ValueError("diagram generator returned empty PlantUML")
    for marker in REJECTED_OUTPUT_MARKERS:
        if marker in normalized:
            raise ValueError(f"diagram generator returned incomplete output: {marker}")
    if "@startuml" not in normalized or "@enduml" not in normalized:
        raise ValueError("diagram generator returned unsupported non-PlantUML output")
    return (normalized + "\n").encode()


def normalize_svg(value: bytes) -> bytes:
    normalized = value.replace(b"\r\n", b"\n").replace(b"\r", b"\n").strip()
    if b"<svg" not in normalized or b"</svg>" not in normalized:
        raise ValueError("PlantUML did not return a complete SVG document")
    if b"ERROR:" in normalized:
        raise ValueError("PlantUML returned a renderer error")
    # PlantUML 1.2022.7 emits SVG textLength/lengthAdjust pairs that browsers handle but
    # macOS Quick Look stretches incorrectly. Natural font metrics are deterministic and
    # render consistently in both consumers.
    normalized = SVG_TEXT_METRIC.sub(b"", normalized)
    return normalized + b"\n"


def render_svg(plantuml: bytes) -> bytes:
    java, jar, _ = setup()
    result = subprocess.run(  # noqa: S603
        [
            str(java),
            JAVA_HEADLESS_OPTION,
            "-cp",
            str(jar),
            "net.sourceforge.plantuml.Run",
            "-pipe",
            "-tsvg",
            "-Playout=smetana",
        ],
        cwd=ROOT,
        input=plantuml,
        capture_output=True,
        check=False,
    )
    if result.returncode or result.stderr.strip():
        detail = result.stderr.decode(errors="replace").strip()
        raise RuntimeError(f"PlantUML Smetana rendering failed: {detail or result.returncode}")
    return normalize_svg(result.stdout)


class PilotBackend:
    def generate(self, specs: tuple[DiagramSpec, ...]) -> dict[Path, bytes]:
        artifacts: dict[Path, bytes] = {}
        with _kernel_session() as client:
            for path in _model_files("all"):
                diagnostics, _ = _execute_source(client, path.read_text(encoding="utf-8"))
                if any(DIAGNOSTIC.search(line) for line in diagnostics):
                    raise RuntimeError(
                        f"cannot render invalid model {path.relative_to(ROOT)}:\n"
                        + "\n".join(diagnostics)
                    )
            for spec in specs:
                diagnostics, outputs = _execute_source(
                    client,
                    "%view --style PUMLCODE --style COMPMOST --style STDCOLOR "
                    f"--style HIDEMETADATA {spec.qualified_name}",
                )
                if diagnostics:
                    raise RuntimeError(
                        f"official pilot failed to render {spec.diagram_id}:\n"
                        + "\n".join(diagnostics)
                    )
                output = next(
                    (
                        value
                        for item in outputs
                        if isinstance((value := item.get("text/plain")), str)
                    ),
                    None,
                )
                if output is None:
                    raise ValueError(f"official pilot returned no PlantUML for {spec.diagram_id}")
                try:
                    plantuml = normalize_plantuml(output)
                except ValueError as error:
                    raise ValueError(f"{spec.diagram_id}: {error}") from error
                artifacts[spec.artifact_path("puml")] = plantuml
                artifacts[spec.artifact_path("svg")] = render_svg(plantuml)
        return artifacts


def backend_named(name: str) -> DiagramBackend:
    if name == "pilot":
        return PilotBackend()
    raise ValueError(f"unsupported diagram backend: {name}")


def _existing_artifacts(root: Path) -> set[Path]:
    return {
        path.relative_to(root)
        for path in root.glob("*/diagrams/*")
        if path.is_file() and path.suffix in {".puml", ".svg"}
    }


def check_artifacts(artifacts: dict[Path, bytes], *, root: Path = REFERENCE_DOC_ROOT) -> list[str]:
    findings: list[str] = []
    expected = set(artifacts)
    existing = _existing_artifacts(root)
    for relative in sorted(expected):
        path = root / relative
        if not path.exists():
            findings.append(f"missing diagram artifact: {path.relative_to(ROOT)}")
        elif path.read_bytes() != artifacts[relative]:
            findings.append(f"stale diagram artifact: {path.relative_to(ROOT)}")
    for relative in sorted(existing - expected):
        findings.append(f"extra diagram artifact: {(root / relative).relative_to(ROOT)}")
    return findings


def synchronize_artifacts(artifacts: dict[Path, bytes], *, root: Path = REFERENCE_DOC_ROOT) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vellis-diagrams-", dir=root) as temporary:
        staging = Path(temporary)
        for relative, content in artifacts.items():
            staged = staging / relative
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(content)
        for relative in sorted(artifacts):
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, destination)
        for relative in sorted(_existing_artifacts(root) - set(artifacts)):
            (root / relative).unlink()


def generate(backend_name: str) -> dict[Path, bytes]:
    specs = load_registered_diagrams()
    artifacts = backend_named(backend_name).generate(specs)
    expected = {
        path for spec in specs for path in (spec.artifact_path("puml"), spec.artifact_path("svg"))
    }
    if set(artifacts) != expected:
        raise RuntimeError("diagram backend returned an incomplete artifact set")
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser(description="Render repository-native SysML v2 diagrams")
    parser.add_argument("command", choices=("render", "check"))
    parser.add_argument("--backend", choices=("pilot",), default="pilot")
    arguments = parser.parse_args()
    artifacts = generate(arguments.backend)
    if arguments.command == "check":
        repeated = generate(arguments.backend)
        if repeated != artifacts:
            print("ERROR diagram generation is nondeterministic across independent kernel sessions")
            return 1
        findings = check_artifacts(artifacts)
        for finding in findings:
            print(f"ERROR {finding}")
        if findings:
            return 1
        print(f"Diagram artifacts are current ({len(artifacts) // 2} views).")
        return 0
    synchronize_artifacts(artifacts)
    print(f"Rendered {len(artifacts) // 2} SysML diagrams with {arguments.backend} and Smetana.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
