from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from io import StringIO
from pathlib import Path

import pytest

from apps.rtg_knowledge_graph import onboarding
from apps.rtg_knowledge_graph.main import main
from apps.rtg_knowledge_graph.onboarding import (
    config_for_data_dir,
    register_client,
    select_client,
    setup_vellis,
)


class TtyStringIO(StringIO):
    def isatty(self) -> bool:
        return True


def test_setup_json_is_single_document_and_repeated_setup_is_noop(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data with spaces"
    assert (
        main(
            [
                "setup",
                "--client",
                "generic-json",
                "--data-dir",
                str(data_dir),
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    assert first["starter_schema"]["status"] == "installed"
    assert first["registration"].startswith("written:")
    assert Path(first["registration"].removeprefix("written:")).is_file()

    assert (
        main(
            [
                "setup",
                "--client",
                "generic-json",
                "--data-dir",
                str(data_dir),
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    second = json.loads(capsys.readouterr().out)
    assert second["registration"] == "already_configured"
    assert second["starter_schema"]["recovery"] == "ledger_replayed"


def test_setup_json_requires_yes_without_prompting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "setup",
                "--client",
                "generic-json",
                "--data-dir",
                str(tmp_path / "data"),
                "--json",
            ]
        )
        == 1
    )
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result == {
        "error": "non-interactive setup requires --yes",
        "ok": False,
    }
    assert captured.err == ""
    assert not (tmp_path / "data").exists()


@pytest.mark.parametrize("command", ["setup", "doctor"])
def test_json_commands_require_explicit_ambiguous_client_without_prompting(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
) -> None:
    monkeypatch.setattr(onboarding, "detected_clients", lambda **_kwargs: ("codex", "claude-code"))
    arguments = [command, "--data-dir", str(tmp_path / command), "--json"]
    if command == "setup":
        arguments.append("--yes")

    assert main(arguments) == 1
    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["ok"] is False
    assert "rerun with --client CLIENT" in result["error"]
    assert "Multiple MCP clients" not in captured.out
    assert captured.err == ""


def test_client_selection_uses_injected_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(onboarding, "detected_clients", lambda **_kwargs: ("codex", "claude-code"))
    input_stream = TtyStringIO("2\n")
    output_stream = StringIO()

    assert (
        select_client(
            "auto",
            input_stream=input_stream,
            output_stream=output_stream,
        )
        == "claude-code"
    )
    assert output_stream.getvalue() == (
        "Multiple MCP clients were detected:\n"
        "  1. codex\n"
        "  2. claude-code\n"
        "Choose a client number: "
    )


def test_client_selection_reports_eof_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(onboarding, "detected_clients", lambda **_kwargs: ("codex", "claude-code"))

    with pytest.raises(onboarding.VellisStartupFailed, match="interactive input ended"):
        select_client(
            "auto",
            input_stream=TtyStringIO(),
            output_stream=StringIO(),
        )


def test_setup_remains_interactive_with_injected_streams(tmp_path: Path) -> None:
    data_dir = tmp_path / "interactive"
    output_stream = StringIO()

    result = setup_vellis(
        config_for_data_dir(data_dir),
        client="generic-json",
        yes=False,
        input_stream=TtyStringIO("yes\n"),
        output_stream=output_stream,
    )

    assert result.client == "generic-json"
    assert result.registration.startswith("written:")
    assert output_stream.getvalue().endswith("Continue? [y/N] ")


def test_auto_client_selection_uses_supplied_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths: list[str | None] = []

    def fake_which(executable: str, *, path: str | None = None) -> str | None:
        paths.append(path)
        return f"/fake/{executable}" if path == "/fake-bin" else None

    monkeypatch.setattr(onboarding.shutil, "which", fake_which)
    env = {"HOME": str(tmp_path), "PATH": "/fake-bin"}

    assert onboarding.detected_clients(env=env) == ("codex", "claude-code")
    assert paths == ["/fake-bin", "/fake-bin"]


def test_generic_setup_prints_a_plain_configuration_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "data"

    assert (
        main(
            [
                "setup",
                "--client",
                "generic-json",
                "--data-dir",
                str(data_dir),
                "--yes",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    expected = data_dir / "setup" / "mcp-config.json"
    assert f"configuration at {expected}" in output
    assert "configuration at written:" not in output


def test_setup_preserves_legacy_flat_storage_root_as_the_data_location(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    legacy_root = tmp_path / "vellis-beta-001"
    assert (
        main(
            [
                "setup",
                "--client",
                "generic-json",
                "--storage-root",
                str(legacy_root),
                "--sql-database-path",
                str(legacy_root / "controller.sqlite"),
                "--yes",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["data_dir"] == str(legacy_root)
    assert (legacy_root / "setup" / "mcp-config.json").is_file()


def test_claude_desktop_merge_preserves_other_entries_and_is_idempotent(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "APPDATA": str(tmp_path / "AppData" / "Roaming"),
    }
    path = Path(env["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"mcpServers": {"other": {"command": "other"}}, "theme": "dark"}),
        encoding="utf-8",
    )
    server = {"command": "C:\\Program Files\\uv.exe", "args": ["run", "vellis"]}
    result = register_client("claude-desktop", server, data_dir=tmp_path / "data", env=env)
    assert result == "configured"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["theme"] == "dark"
    assert value["mcpServers"]["other"] == {"command": "other"}
    assert value["mcpServers"]["rtg_knowledge_graph"] == server
    assert list(path.parent.glob("claude_desktop_config.json.vellis-backup-*"))

    assert (
        register_client("claude-desktop", server, data_dir=tmp_path / "data", env=env)
        == "already_configured"
    )


@pytest.mark.parametrize(
    ("client", "executable", "config_relative", "add_fragment"),
    [
        ("codex", "codex", ".codex/config.toml", ("mcp", "add")),
        ("claude-code", "claude", ".claude.json", ("mcp", "add-json")),
    ],
)
def test_cli_registration_replaces_only_vellis_and_uses_user_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    client: str,
    executable: str,
    config_relative: str,
    add_fragment: tuple[str, str],
) -> None:
    env = {"HOME": str(tmp_path), "PATH": ""}
    config_path = tmp_path / config_relative
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("existing client configuration\n", encoding="utf-8")
    commands: list[list[str]] = []
    monkeypatch.setattr(
        onboarding,
        "_cli_registration",
        lambda *_args, **_kwargs: {"command": "old", "args": []},
    )

    def record(command: Sequence[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(onboarding, "_run", record)
    server = {"command": "/absolute path/uv", "args": ["run", "vellis"]}
    assert register_client(client, server, data_dir=tmp_path / "data", env=env) == "replaced"
    assert any(command[:3] == [executable, *add_fragment] for command in commands)
    if client == "claude-code":
        assert any("--scope" in command and "user" in command for command in commands)
    assert list(config_path.parent.glob(f"{config_path.name}.vellis-backup-*"))


def test_cli_registration_failure_restores_previous_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = {"HOME": str(tmp_path), "PATH": ""}
    path = tmp_path / ".codex" / "config.toml"
    path.parent.mkdir(parents=True)
    original = b"[mcp_servers.other]\ncommand='other'\n"
    path.write_bytes(original)
    monkeypatch.setattr(
        onboarding,
        "_cli_registration",
        lambda *_args, **_kwargs: {"command": "old", "args": []},
    )

    def fail_after_mutation(*_args: object, **_kwargs: object) -> object:
        path.write_text("partially changed", encoding="utf-8")
        raise RuntimeError("simulated client failure")

    monkeypatch.setattr(onboarding, "_run", fail_after_mutation)
    with pytest.raises(RuntimeError, match="simulated"):
        register_client(
            "codex",
            {"command": "/absolute/uv", "args": ["run", "vellis"]},
            data_dir=tmp_path / "data",
            env=env,
        )
    assert path.read_bytes() == original


def test_doctor_is_non_destructive_for_fresh_data_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "new-data"
    assert main(["doctor", "--client", "generic-json", "--data-dir", str(data_dir), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["ok"] is False
    assert not config_for_data_dir(data_dir).sql_database_path.exists()


def test_setup_fails_closed_for_corrupt_ledger_without_configuring_client(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    data_dir = tmp_path / "corrupt"
    data_dir.mkdir()
    (data_dir / "controller.sqlite").write_bytes(b"not a sqlite database")

    assert (
        main(
            [
                "setup",
                "--client",
                "generic-json",
                "--data-dir",
                str(data_dir),
                "--yes",
                "--json",
            ]
        )
        == 1
    )
    result = json.loads(capsys.readouterr().out)
    assert "no replacement empty graph" in result["error"]
    assert not (data_dir / "setup" / "mcp-config.json").exists()
