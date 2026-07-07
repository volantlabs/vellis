from __future__ import annotations

import tomllib
from pathlib import Path


def test_open_source_release_basics_are_present() -> None:
    for path in (
        "LICENSE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        ".github/workflows/check.yml",
    ):
        assert Path(path).is_file()


def test_project_metadata_declares_license_and_authors() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]

    assert project["license"] == "Apache-2.0"
    assert "LICENSE" in project["license-files"]
    assert project["authors"]
    assert "Development Status :: 4 - Beta" in project["classifiers"]
    assert "fastmcp>=3.4.3,<4" in project["dependencies"]
    assert "mcp>=1.28.1,<2" in data["dependency-groups"]["dev"]
    assert project["scripts"]["vellis-rtg-knowledge-graph"] == (
        "apps.rtg_knowledge_graph.main:main"
    )


def test_project_builds_declared_python_packages() -> None:
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    package_find = data["tool"]["setuptools"]["packages"]["find"]

    assert package_find["include"] == ["apps*", "components*", "vellis*"]
    assert package_find["namespaces"] is False
    assert "tests*" in package_find["exclude"]
    assert "apps.*.tests*" in package_find["exclude"]
    assert "components.*.tests*" in package_find["exclude"]
    assert data["tool"]["setuptools"]["package-data"]["apps.rtg_knowledge_graph"] == [
        "resources/*.json"
    ]


def test_project_has_vellis_import_identity() -> None:
    import vellis

    assert vellis.__version__ == "0.1.0"


def test_justfile_exposes_turnkey_rtg_launch_recipes() -> None:
    justfile = Path("justfile").read_text(encoding="utf-8")

    for recipe in (
        "skills-sync:",
        "rtg:",
        "rtg-mcp-info:",
        "rtg-mcp:",
        "rtg-mcp-http-info",
        "rtg-mcp-http",
        'host="127.0.0.1" port="8765" path="/mcp":',
        'rtg-eval-info storage_root="/tmp/vellis-beta-001":',
    ):
        assert recipe in justfile
