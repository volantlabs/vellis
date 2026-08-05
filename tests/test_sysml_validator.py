from __future__ import annotations

import json
import re
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


def test_model_readme_maps_every_discovered_file() -> None:
    files = sysml_validator._model_files()
    readme = (model_layout.MODEL_ROOT / "README.md").read_text(encoding="utf-8")
    mapped_files = set(re.findall(r"`([^`/]+\.sysml)`", readme))

    assert mapped_files == {path.name for path in files}


def test_combined_source_retains_file_line_spans(tmp_path: Path) -> None:
    first = tmp_path / "10-first.sysml"
    second = tmp_path / "20-second.sysml"
    first.write_text("package First {\n}\n", encoding="utf-8")
    second.write_text("package Second {}", encoding="utf-8")

    source, spans = sysml_validator._combined_source([first, second])

    assert source == "package First {\n}\npackage Second {}\n"
    assert spans == [
        sysml_validator.SourceSpan(first, 1, 2),
        sysml_validator.SourceSpan(second, 3, 3),
    ]


def test_official_validator_accepts_later_import_and_multiple_packages() -> None:
    source = (
        "package First { private import Second::*; item example : Thing; } "
        "package Second { item def Thing; } "
        "package Third {}"
    )

    with sysml_validator._kernel_session() as client:
        diagnostics = sysml_validator._execute_source(client, source)

    assert diagnostics == []


def test_model_check_uses_official_validator_and_negative_probe() -> None:
    justfile = (model_layout.ROOT / "justfile").read_text(encoding="utf-8")
    lock = json.loads(
        (model_layout.MODEL_CONFIG_ROOT / "validator.lock.json").read_text(encoding="utf-8")
    )

    assert "tools/sysml_validator.py validate --self-test" in justfile
    assert lock["provider"] == "Systems-Modeling/SysML-v2-Pilot-Implementation"
    assert lock["kernel"]["jar"].endswith(
        f"jupyter-sysml-kernel-{lock['implementation_version']}-all.jar"
    )


def test_negative_probe_uses_a_separate_kernel_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "10-model.sysml"
    model.write_text("package Model {}\n", encoding="utf-8")
    sessions: list[str] = []
    executions: list[tuple[str, str]] = []

    class FakeSession:
        def __enter__(self) -> str:
            label = f"session-{len(sessions) + 1}"
            sessions.append(label)
            return label

        def __exit__(self, *_: object) -> None:
            return None

    def fake_execute(client: str, source: str) -> list[str]:
        executions.append((client, source))
        if "VellisValidatorNegative" in source:
            return ["ERROR:unresolved type(1.sysml line : 1 column : 1)"]
        return []

    monkeypatch.setattr(sysml_validator, "ROOT", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(sysml_validator, "_model_files", lambda: [model])
    monkeypatch.setattr(sysml_validator, "_kernel_session", FakeSession)
    monkeypatch.setattr(sysml_validator, "_execute_source", fake_execute)
    monkeypatch.setattr(
        sysml_validator,
        "_json_object",
        lambda _: {"implementation_version": "test"},
    )

    assert sysml_validator.validate(self_test=True) == 0
    assert sessions == ["session-1", "session-2"]
    assert executions[0][0] != executions[1][0]


def test_validator_warning_maps_to_its_file_and_fails_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    first = tmp_path / "10-first.sysml"
    second = tmp_path / "20-second.sysml"
    first.write_text("package First {\n}\n", encoding="utf-8")
    second.write_text("package Second {\n}\n", encoding="utf-8")

    class FakeSession:
        def __enter__(self) -> object:
            return object()

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(sysml_validator, "ROOT", tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setattr(sysml_validator, "_model_files", lambda: [first, second])
    monkeypatch.setattr(sysml_validator, "_kernel_session", FakeSession)
    monkeypatch.setattr(
        sysml_validator,
        "_execute_source",
        lambda *_: ["WARNING:ambiguous model(1.sysml line : 4 column : 9)"],
    )

    assert sysml_validator.validate() == 1
    assert "WARNING 20-second.sysml:2:9:ambiguous model" in capsys.readouterr().out


def test_kernel_execution_collects_only_related_diagnostics() -> None:
    messages = iter(
        (
            {
                "parent_header": {"msg_id": "unrelated"},
                "msg_type": "stream",
                "content": {"name": "stderr", "text": "unrelated error"},
            },
            {
                "parent_header": {"msg_id": "wanted"},
                "msg_type": "stream",
                "content": {"name": "stdout", "text": "ordinary output"},
            },
            {
                "parent_header": {"msg_id": "wanted"},
                "msg_type": "stream",
                "content": {
                    "name": "stdout",
                    "text": "WARNING:notice(1.sysml line : 2 column : 3)",
                },
            },
            {
                "parent_header": {"msg_id": "wanted"},
                "msg_type": "stream",
                "content": {
                    "name": "stderr",
                    "text": "ERROR:broken(1.sysml line : 4 column : 5)",
                },
            },
            {
                "parent_header": {"msg_id": "wanted"},
                "msg_type": "status",
                "content": {"execution_state": "idle"},
            },
        )
    )

    class FakeClient:
        def execute(self, _: str) -> str:
            return "wanted"

        def get_iopub_msg(self, *, timeout: int) -> dict[str, object]:
            assert timeout == 120
            return next(messages)

    diagnostics = sysml_validator._execute_source(FakeClient(), "package Model {}")  # type: ignore[arg-type]

    assert diagnostics == [
        "WARNING:notice(1.sysml line : 2 column : 3)",
        "ERROR:broken(1.sysml line : 4 column : 5)",
    ]


def test_language_source_is_pinned_to_an_immutable_commit() -> None:
    """A tag can move; a commit cannot. Setup verifies the resolved commit matches."""
    lock = json.loads(model_layout.LANGUAGE_LOCK_PATH.read_text(encoding="utf-8"))
    source = lock["source"]

    assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
    assert source["repository"].startswith("https://")
    assert source["sparse_paths"]
    for artifact in lock["specifications"].values():
        assert artifact["path"] in source["sparse_paths"] or any(
            artifact["path"].startswith(prefix.rstrip("*")) for prefix in source["sparse_paths"]
        )
