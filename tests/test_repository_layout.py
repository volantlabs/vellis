from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

from tools import model_layout, sysml_validator

ROOT = Path(__file__).resolve().parents[1]

STALE_PATHS = (
    "docs" + "/components/",
    "docs" + "/reference/",
    "docs" + "/model/generated/",
    "docs" + "/evals/",
    "docs" + "/sysml-modeling.md",
    "docs" + "/agentic-mbse-engineering-system.md",
    "docs" + "/model/open-design-questions.md",
    "model" + "/model-status.json",
    "model" + "/model.lock.json",
    "model" + "/validator.lock.json",
    "model" + "/allowed-constructs.json",
    "model" + "/invariant-id-migration.json",
    "model" + "/.cache/",
    "model" + "/dist/",
    "model" + "/foundation/SoftwareComponentPattern.sysml",
    "bibliotek" + "-components.md",
    "vellis" + "-operations.md",
)

TEXT_SUFFIXES = {
    ".json",
    ".md",
    ".py",
    ".sysml",
    ".toml",
    ".yaml",
    ".yml",
}


def _repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [ROOT / value.decode() for value in result.stdout.split(b"\0") if value]


def test_repository_text_has_no_stale_organization_paths() -> None:
    violations: list[str] = []
    for path in _repository_files():
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for stale in STALE_PATHS:
            if stale in text:
                violations.append(f"{path.relative_to(ROOT)}: {stale}")

    assert violations == []


def test_local_markdown_links_resolve() -> None:
    missing: list[str] = []
    link_pattern = re.compile(r"!?\[[^]]*\]\(([^)]+)\)")
    for path in _repository_files():
        if not path.is_file() or path.suffix != ".md":
            continue
        for raw_target in link_pattern.findall(path.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:", "app://")):
                continue
            target = unquote(target.split("#", 1)[0])
            resolved = ROOT / target.lstrip("/") if target.startswith("/") else path.parent / target
            if not resolved.exists():
                missing.append(f"{path.relative_to(ROOT)} -> {raw_target}")

    assert missing == []


def test_authored_products_generated_outputs_and_fixture_are_separated() -> None:
    authored = {path.resolve() for path in sysml_validator._model_files("all")}
    under_model = {path.resolve() for path in model_layout.MODEL_ROOT.rglob("*.sysml")}

    assert authored == under_model
    assert model_layout.SOFTWARE_COMPONENT_PATTERN_PATH.exists()
    assert model_layout.SOFTWARE_COMPONENT_PATTERN_PATH.resolve() not in authored
    assert not list(model_layout.REFERENCE_DOC_ROOT.rglob("*.json"))
    assert {path.name for path in model_layout.GENERATED_MODEL_ROOT.glob("*.json")} == {
        "conformance-objectives.json",
        "formal-model-index.json",
        "verification-evidence.json",
    }
    for path in model_layout.REFERENCE_DOC_ROOT.rglob("*.md"):
        notice = path.read_text(encoding="utf-8").splitlines()[2]
        assert "Generated" in notice
        assert "non-normative reading projection" in notice


def test_model_cache_and_packages_are_ignored() -> None:
    for path in (model_layout.SYSML_CACHE_ROOT, model_layout.MODEL_PACKAGE_ROOT):
        result = subprocess.run(["git", "check-ignore", "-q", str(path)], cwd=ROOT, check=False)
        assert result.returncode == 0, path


def test_local_vellis_data_readme_is_tracked_and_runtime_state_is_ignored() -> None:
    readme = ROOT / ".data" / "README.md"
    assert readme.is_file()
    trackable = subprocess.run(
        ["git", "check-ignore", "-q", ".data/README.md"],
        cwd=ROOT,
        check=False,
    )
    assert trackable.returncode == 1
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".data/rtg_knowledge_graph/runtime.sqlite"],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 0
