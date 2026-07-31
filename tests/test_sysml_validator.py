from __future__ import annotations

from pathlib import Path

import pytest

from tools import model_layout, sysml_validator


def test_model_discovery_is_dynamic_and_filename_ordered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "20-second.sysml").write_text("package Second {}\n", encoding="utf-8")
    (tmp_path / "10-first.sysml").write_text("package First {}\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("ignored\n", encoding="utf-8")
    monkeypatch.setattr(sysml_validator, "MODEL_ROOT", tmp_path)  # type: ignore[attr-defined]

    assert [path.name for path in sysml_validator._model_files()] == [
        "10-first.sysml",
        "20-second.sysml",
    ]


def test_current_model_packages_are_unique_and_imports_are_ordered() -> None:
    files = sysml_validator._model_files()

    assert files == sorted(model_layout.MODEL_ROOT.glob("*.sysml"), key=lambda path: path.name)
    sysml_validator._check_packages_and_import_order(files)


def test_import_from_later_file_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "10-first.sysml"
    second = tmp_path / "20-second.sysml"
    first.write_text("package First { private import Second::*; }\n", encoding="utf-8")
    second.write_text("package Second {}\n", encoding="utf-8")
    monkeypatch.setattr(sysml_validator, "ROOT", tmp_path)  # type: ignore[attr-defined]

    with pytest.raises(RuntimeError, match="not earlier in filename order"):
        sysml_validator._check_packages_and_import_order([first, second])


def test_model_check_uses_official_validator_and_negative_probe() -> None:
    justfile = (model_layout.ROOT / "justfile").read_text(encoding="utf-8")
    lock = (model_layout.MODEL_CONFIG_ROOT / "validator.lock.json").read_text(encoding="utf-8")

    assert "tools/sysml_validator.py validate --self-test" in justfile
    assert "Systems-Modeling/SysML-v2-Pilot-Implementation" in lock
    assert "jupyter-sysml-kernel" in lock
