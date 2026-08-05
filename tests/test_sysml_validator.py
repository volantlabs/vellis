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


def test_validator_downloads_are_checksum_pinned() -> None:
    lock = json.loads(
        (model_layout.MODEL_CONFIG_ROOT / "validator.lock.json").read_text(encoding="utf-8")
    )
    downloads = [lock["kernel"], *lock["java"]["platforms"].values()]

    assert downloads
    assert all(download["url"].startswith("https://") for download in downloads)
    assert all(re.fullmatch(r"[0-9a-f]{64}", download["sha256"]) for download in downloads)


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


@pytest.mark.parametrize(("level", "expected_status"), (("WARNING", 0), ("ERROR", 1)))
def test_validator_diagnostic_maps_to_its_file_without_promoting_warnings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    level: str,
    expected_status: int,
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
        lambda *_: [f"{level}:ambiguous model(1.sysml line : 4 column : 9)"],
    )

    assert sysml_validator.validate() == expected_status
    assert f"{level} 20-second.sysml:2:9:ambiguous model" in capsys.readouterr().out


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


@pytest.mark.parametrize(
    ("line", "expected"),
    (
        ("part def A { block def B; }", "part def"),
        ("attribute x = «stereotyped»;", "metadata def"),
        ("value def Temperature;", "attribute def"),
        ("assoc Ownership { }", "connection def"),
        ("part property wheel : Wheel;", "declares features directly"),
        ("flow port p : P;", "port def"),
        ("package P { struct A; }", "KerML root notation"),
    ),
)
def test_rejected_v1_notation_gets_a_hint_naming_its_replacement(line: str, expected: str) -> None:
    hint = sysml_validator._v1_notation_hint(line)

    assert hint is not None
    assert expected in hint


@pytest.mark.parametrize(
    "line",
    (
        "attribute def 'Block Diagram';",
        "part def BlockCache;",
        "doc /* the v1 block was replaced by part def */",
        "part def A { ref part b : B; }",
    ),
)
def test_valid_v2_declarations_are_never_hinted(line: str) -> None:
    assert sysml_validator._v1_notation_hint(line) is None
