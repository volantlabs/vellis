from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_launch import (
    MCP_SERVER_NAME,
    mcp_launch_metadata,
    repository_root,
)
from apps.rtg_knowledge_graph.starter_schema import (
    StarterSchemaStatus,
    VellisStartupFailed,
    load_starter_schema_bundle,
)

JsonObject = dict[str, Any]
CLIENTS = ("codex", "claude-code", "claude-desktop", "generic-json")
FIRST_PROMPT = (
    "Help me start using Vellis to remember and organize things across my personal life, "
    "household or family responsibilities, and work. Use the schema already installed. "
    "Ask before assuming missing details and show me what you propose before making a large "
    "initial write."
)


@dataclass(frozen=True, slots=True)
class SetupResult:
    client: str
    registration: str
    data_dir: Path
    starter_schema: StarterSchemaStatus
    launch: JsonObject
    first_prompt: str = FIRST_PROMPT

    def to_json_value(self) -> JsonObject:
        return {
            "ok": True,
            "client": self.client,
            "registration": self.registration,
            "data_dir": str(self.data_dir),
            "starter_schema": self.starter_schema.to_json_value(),
            "launch": self.launch,
            "restart_required": True,
            "first_prompt": self.first_prompt,
        }


def config_for_data_dir(
    data_dir: Path,
    *,
    install_starter_schema: bool = True,
    automatic_recovery: bool = True,
) -> RtgKnowledgeGraphConfig:
    root = data_dir.expanduser().resolve(strict=False)
    return RtgKnowledgeGraphConfig(
        storage_root=root / "json_file",
        sql_database_path=root / "controller.sqlite",
        install_starter_schema=install_starter_schema,
        automatic_recovery=automatic_recovery,
    )


def detected_clients(
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    path = None if env is None else env.get("PATH", "")
    detected: list[str] = []
    if shutil.which("codex", path=path):
        detected.append("codex")
    if shutil.which("claude", path=path):
        detected.append("claude-code")
    if _claude_desktop_config_path(home=home, env=env).parent.exists():
        detected.append("claude-desktop")
    return tuple(detected)


def select_client(
    requested: str,
    *,
    interactive: bool = True,
    input_stream: Any = None,
    output_stream: Any = None,
    env: Mapping[str, str] | None = None,
) -> str:
    if requested != "auto":
        return requested
    choices = detected_clients(home=_home(env), env=env)
    if len(choices) == 1:
        return choices[0]
    if not choices:
        return "generic-json"
    input_handle = input_stream or sys.stdin
    if not interactive or not input_handle.isatty():
        joined = ", ".join(choices)
        raise VellisStartupFailed(
            f"multiple MCP clients were detected ({joined}); rerun with --client CLIENT"
        )
    output_handle = output_stream or sys.stdout
    print("Multiple MCP clients were detected:", file=output_handle)
    for number, client in enumerate(choices, start=1):
        print(f"  {number}. {client}", file=output_handle)
    while True:
        answer = _prompt(
            "Choose a client number: ",
            input_stream=input_handle,
            output_stream=output_handle,
        ).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]


def setup_vellis(
    config: RtgKnowledgeGraphConfig,
    *,
    client: str,
    yes: bool,
    interactive: bool = True,
    input_stream: Any = None,
    output_stream: Any = None,
    env: Mapping[str, str] | None = None,
) -> SetupResult:
    selected = select_client(
        client,
        interactive=interactive,
        input_stream=input_stream,
        output_stream=output_stream,
        env=env,
    )
    if not yes and not interactive:
        raise VellisStartupFailed("non-interactive setup requires --yes")
    metadata = mcp_launch_metadata(config)
    server = _single_server(metadata["client_config"])
    data_dir = _data_dir_for_config(config)
    output = output_stream or sys.stdout
    print(f"Client: {selected}", file=output)
    print(f"Data: {data_dir}", file=output)
    print(f"Launch: {_launch_text(server)}", file=output)
    print("Configuration: user-wide rtg_knowledge_graph MCP registration", file=output)
    preview = _registration_check(selected, server, data_dir=data_dir, env=env)
    if preview["ok"]:
        print("Client entry: already identical; setup will leave it unchanged", file=output)
    else:
        print(
            "Client entry: add or replace only rtg_knowledge_graph; preserve other entries",
            file=output,
        )
    if not yes:
        stream = input_stream or sys.stdin
        if not stream.isatty():
            raise VellisStartupFailed("setup confirmation requires a terminal or --yes")
        answer = (
            _prompt(
                "Continue? [y/N] ",
                input_stream=stream,
                output_stream=output,
            )
            .strip()
            .lower()
        )
        if answer not in {"y", "yes"}:
            raise VellisStartupFailed("setup cancelled")

    try:
        composition = build_app(config)
        starter = composition.prepare()
        validation = composition.controller.validate_graph()
        if not validation.accepted:
            raise VellisStartupFailed("the prepared Vellis graph did not pass validation")
    except VellisStartupFailed:
        raise
    except Exception as error:  # noqa: BLE001 - setup must fail closed with useful context
        raise VellisStartupFailed(
            "Vellis could not open or validate durable local state; no replacement empty graph "
            f"was configured. Run `uv run vellis doctor`. Cause: {error}"
        ) from error

    registration = register_client(
        selected,
        server,
        data_dir=data_dir,
        env=env,
    )
    return SetupResult(
        client=selected,
        registration=registration,
        data_dir=data_dir,
        starter_schema=starter,
        launch=server,
    )


def register_client(
    client: str,
    server: JsonObject,
    *,
    data_dir: Path,
    env: Mapping[str, str] | None = None,
) -> str:
    if client == "codex":
        return _register_cli_client(
            client="codex",
            executable="codex",
            server=server,
            config_path=_home(env) / ".codex" / "config.toml",
            env=env,
        )
    if client == "claude-code":
        return _register_cli_client(
            client="claude-code",
            executable="claude",
            server=server,
            config_path=_home(env) / ".claude.json",
            env=env,
        )
    if client == "claude-desktop":
        return _merge_desktop_config(server, env=env)
    if client == "generic-json":
        target = data_dir / "setup" / "mcp-config.json"
        desired = {"mcpServers": {MCP_SERVER_NAME: server}}
        if _read_json(target) == desired:
            return "already_configured"
        _atomic_json_write(target, desired)
        return f"written:{target}"
    raise VellisStartupFailed(f"unsupported MCP client: {client}")


def doctor_report(
    config: RtgKnowledgeGraphConfig,
    *,
    client: str,
    interactive: bool = True,
    input_stream: Any = None,
    output_stream: Any = None,
    env: Mapping[str, str] | None = None,
) -> JsonObject:
    checks: list[JsonObject] = []
    repo_root = repository_root()
    checks.append(
        {
            "id": "repository_checkout",
            "ok": repo_root is not None,
            "detail": str(repo_root) if repo_root is not None else "installed package mode",
        }
    )
    try:
        bundle = load_starter_schema_bundle()
        checks.append(
            {
                "id": "starter_schema_bundle",
                "ok": bool(bundle.get("knowledge_changes")) and bundle.get("graph_objects") == [],
                "detail": str(bundle.get("ontology_id")),
            }
        )
    except Exception as error:  # noqa: BLE001 - doctor reports rather than raises
        checks.append({"id": "starter_schema_bundle", "ok": False, "detail": str(error)})

    data_dir = _data_dir_for_config(config)
    checks.append(
        {
            "id": "data_directory",
            "ok": _writable_or_creatable(data_dir),
            "detail": str(data_dir),
        }
    )
    checks.append(_ledger_check(config.sql_database_path))
    checks.append(_replay_check(config))
    checks.append(_ignored_data_check(data_dir))
    selected = select_client(
        client,
        interactive=interactive,
        input_stream=input_stream,
        output_stream=output_stream,
        env=env,
    )
    metadata = mcp_launch_metadata(config)
    server = _single_server(metadata["client_config"])
    checks.append(_registration_check(selected, server, data_dir=data_dir, env=env))
    checks.append(
        {
            "id": "launch_command",
            "ok": _launch_executable_exists(server),
            "detail": _launch_text(server),
        }
    )
    return {
        "ok": all(bool(check["ok"]) for check in checks),
        "client": selected,
        "data_dir": str(data_dir),
        "checks": checks,
    }


def _prompt(message: str, *, input_stream: Any, output_stream: Any) -> str:
    print(message, end="", file=output_stream, flush=True)
    answer = input_stream.readline()
    if answer == "":
        raise VellisStartupFailed("interactive input ended before a response was provided")
    return cast(str, answer)


def _register_cli_client(
    *,
    client: str,
    executable: str,
    server: JsonObject,
    config_path: Path,
    env: Mapping[str, str] | None,
) -> str:
    before = config_path.read_bytes() if config_path.is_file() else None
    desired = dict(server)
    if client == "codex":
        # Codex has no cwd field; the generated uv --directory arguments already make it
        # independent of the client's working directory.
        desired.pop("cwd", None)
    current = _cli_registration(client, executable, env=env)
    if current == desired:
        return "already_configured"
    backup = _backup(config_path)
    try:
        if current is not None:
            remove = [executable, "mcp", "remove", MCP_SERVER_NAME]
            if client == "claude-code":
                remove.extend(["--scope", "user"])
            _run(remove, env=env)
        if client == "codex":
            command = str(desired["command"])
            args = cast(list[str], desired.get("args", []))
            _run([executable, "mcp", "add", MCP_SERVER_NAME, "--", command, *args], env=env)
        else:
            _run(
                [
                    executable,
                    "mcp",
                    "add-json",
                    "--scope",
                    "user",
                    MCP_SERVER_NAME,
                    json.dumps(desired, separators=(",", ":")),
                ],
                env=env,
            )
    except Exception:
        _restore_file(config_path, before)
        raise
    return "replaced" if backup is not None else "configured"


def _cli_registration(
    client: str,
    executable: str,
    *,
    env: Mapping[str, str] | None,
) -> JsonObject | None:
    if client == "codex":
        result = _run(
            [executable, "mcp", "get", MCP_SERVER_NAME, "--json"],
            env=env,
            check=False,
        )
        if result.returncode != 0:
            return None
        raw = json.loads(result.stdout)
        if isinstance(raw, dict) and isinstance(raw.get("transport"), dict):
            transport = raw["transport"]
            if transport.get("type") == "stdio":
                return {
                    "command": transport.get("command"),
                    "args": transport.get("args", []),
                    **({"cwd": raw["cwd"]} if isinstance(raw.get("cwd"), str) else {}),
                }
        return cast(JsonObject, raw) if isinstance(raw, dict) else None
    config_path = _home(env) / ".claude.json"
    value = _read_json(config_path)
    servers = value.get("mcpServers", {})
    current = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
    return cast(JsonObject, current) if isinstance(current, dict) else None


def _merge_desktop_config(server: JsonObject, *, env: Mapping[str, str] | None) -> str:
    path = _claude_desktop_config_path(home=_home(env), env=env)
    value = _read_json(path)
    servers = value.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise VellisStartupFailed(f"{path} contains a non-object mcpServers value")
    if servers.get(MCP_SERVER_NAME) == server:
        return "already_configured"
    replaced = MCP_SERVER_NAME in servers
    _backup(path)
    servers[MCP_SERVER_NAME] = server
    _atomic_json_write(path, value)
    return "replaced" if replaced else "configured"


def _registration_check(
    client: str,
    server: JsonObject,
    *,
    data_dir: Path,
    env: Mapping[str, str] | None,
) -> JsonObject:
    try:
        expected = dict(server)
        if client == "codex":
            expected.pop("cwd", None)
        if client in {"codex", "claude-code"}:
            executable = "codex" if client == "codex" else "claude"
            current = _cli_registration(client, executable, env=env)
        elif client == "claude-desktop":
            value = _read_json(_claude_desktop_config_path(home=_home(env), env=env))
            servers = value.get("mcpServers", {})
            current = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
        else:
            path = data_dir / "setup" / "mcp-config.json"
            value = _read_json(path)
            servers = value.get("mcpServers", {})
            current = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
        return {
            "id": "client_registration",
            "ok": current == expected,
            "detail": "configured" if current == expected else "missing or different",
        }
    except Exception as error:  # noqa: BLE001 - doctor reports rather than raises
        return {"id": "client_registration", "ok": False, "detail": str(error)}


def _ledger_check(path: Path) -> JsonObject:
    absolute = path.expanduser().resolve(strict=False)
    if not absolute.exists():
        return {"id": "ledger", "ok": True, "detail": "not created yet"}
    try:
        uri = f"file:{absolute.as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
        return {
            "id": "ledger",
            "ok": result == ("ok",),
            "detail": str(absolute),
        }
    except Exception as error:  # noqa: BLE001 - doctor reports rather than raises
        return {"id": "ledger", "ok": False, "detail": str(error)}


def _replay_check(config: RtgKnowledgeGraphConfig) -> JsonObject:
    source = config.sql_database_path.expanduser().resolve(strict=False)
    if not source.exists():
        return {"id": "replay_feasibility", "ok": True, "detail": "no ledger yet"}
    try:
        with tempfile.TemporaryDirectory(prefix="vellis-doctor-") as temporary:
            root = Path(temporary)
            copied_ledger = root / "controller.sqlite"
            shutil.copy2(source, copied_ledger)
            probe = build_app(
                RtgKnowledgeGraphConfig(
                    storage_root=root / "json_file",
                    sql_database_path=copied_ledger,
                    install_starter_schema=False,
                    automatic_recovery=True,
                )
            )
            status = probe.prepare()
        return {
            "id": "replay_feasibility",
            "ok": True,
            "detail": {"status": status.status, "recovery": status.recovery},
        }
    except Exception as error:  # noqa: BLE001 - doctor reports rather than raises
        return {"id": "replay_feasibility", "ok": False, "detail": str(error)}


def _ignored_data_check(data_dir: Path) -> JsonObject:
    repo_root = repository_root()
    resolved = data_dir.expanduser().resolve(strict=False)
    if repo_root is None or not resolved.is_relative_to(repo_root):
        return {
            "id": "git_ignore",
            "ok": True,
            "detail": "outside repository",
        }
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(data_dir)],
        check=False,
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    return {
        "id": "git_ignore",
        "ok": result.returncode == 0,
        "detail": "ignored" if result.returncode == 0 else "path is not ignored by Git",
    }


def _single_server(raw: object) -> JsonObject:
    if not isinstance(raw, dict):
        raise VellisStartupFailed("generated MCP client configuration is invalid")
    servers = raw.get("mcpServers")
    if not isinstance(servers, dict) or set(servers) != {MCP_SERVER_NAME}:
        raise VellisStartupFailed("generated MCP configuration must contain one Vellis server")
    server = servers[MCP_SERVER_NAME]
    if not isinstance(server, dict):
        raise VellisStartupFailed("generated Vellis MCP server entry is invalid")
    return cast(JsonObject, server)


def _data_dir_for_config(config: RtgKnowledgeGraphConfig) -> Path:
    storage_root = config.storage_root.expanduser().resolve(strict=False)
    sql_path = config.sql_database_path.expanduser().resolve(strict=False)
    if storage_root.name == "json_file" and sql_path.parent == storage_root.parent:
        return storage_root.parent
    return storage_root


def _launch_text(server: JsonObject) -> str:
    if isinstance(server.get("url"), str):
        return str(server["url"])
    command = str(server.get("command", ""))
    args = server.get("args", [])
    return " ".join([command, *(str(value) for value in args)])


def _launch_executable_exists(server: JsonObject) -> bool:
    command = server.get("command")
    if not isinstance(command, str):
        return isinstance(server.get("url"), str)
    return Path(command).is_file() or shutil.which(command) is not None


def _claude_desktop_config_path(
    *,
    home: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    user_home = home or _home(env)
    values = os.environ if env is None else env
    if os.name == "nt" or "APPDATA" in values:
        appdata = Path(values.get("APPDATA", user_home / "AppData" / "Roaming"))
        return appdata / "Claude" / "claude_desktop_config.json"
    return user_home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"


def _home(env: Mapping[str, str] | None) -> Path:
    values = os.environ if env is None else env
    return Path(values.get("HOME") or values.get("USERPROFILE") or Path.home())


def _read_json(path: Path) -> JsonObject:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VellisStartupFailed(f"{path} must contain a JSON object")
    return cast(JsonObject, value)


def _backup(path: Path) -> Path | None:
    if not path.is_file():
        return None
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = path.with_name(f"{path.name}.vellis-backup-{stamp}")
    shutil.copy2(path, target)
    return target


def _restore_file(path: Path, content: bytes | None) -> None:
    if content is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _atomic_json_write(path: Path, value: JsonObject) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(raw_temp)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _run(
    command: Sequence[str],
    *,
    env: Mapping[str, str] | None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            list(command),
            check=False,
            capture_output=True,
            text=True,
            env=None if env is None else dict(env),
        )
    except OSError as error:
        raise VellisStartupFailed(f"could not run {command[0]}: {error}") from error
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise VellisStartupFailed(f"{' '.join(command[:3])} failed: {detail}")
    return result


def _writable_or_creatable(path: Path) -> bool:
    existing = path
    while not existing.exists() and existing != existing.parent:
        existing = existing.parent
    return existing.is_dir() and os.access(existing, os.W_OK)
