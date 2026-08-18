"""Evidence for S018's public-CLI-only MCP client setup decisions."""

from __future__ import annotations

import io
import json
import os
import stat
import sys
from pathlib import Path

import pytest

from tests.vellis.oracle import materialize_state
from vellis import setup as setup_implementation
from vellis.client_setup import (
    ClientAction,
    ClientFailureStage,
    ClientKind,
    ClientState,
    apply_plans,
    plan_clients,
    render_command,
    server_argv,
    subprocess_runner,
)
from vellis.paths import store_path
from vellis.setup import EXIT_FAILED, EXIT_SUCCESS, main
from vellis.system import RTGSystem

FAKE_CLIENT = """#!{python}
import json
import os
import shlex
import sys
from pathlib import Path

client = Path(sys.argv[0]).name
root = Path(os.environ["FAKE_MCP_DIR"])
state_path = root / f"{{client}}-state.json"
log_path = root / f"{{client}}-log.jsonl"
with log_path.open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(sys.argv[1:]) + "\\n")
state = json.loads(state_path.read_text(encoding="utf-8"))
args = sys.argv[1:]
operation = args[1] if len(args) > 1 and args[0] == "mcp" else ""
if operation == "get":
    status = state["status"]
    if status == "absent":
        if client == "claude":
            print('No MCP server named "vellis". Configured servers: playwright', file=sys.stderr)
        else:
            print("Error: No MCP server named 'vellis' found.", file=sys.stderr)
        raise SystemExit(1)
    if status == "unparseable":
        print("this output has no fields")
        raise SystemExit(0)
    if status == "error":
        print("configured server executable not found", file=sys.stderr)
        raise SystemExit(2)
    target = state["target"]
    if client == "codex":
        transport = state.get("transport", "stdio")
        details = (
            {{
                "type": "stdio",
                "command": target[0],
                "args": target[1:],
                "env": state.get("environment"),
            }}
            if transport == "stdio"
            else {{"type": transport, "url": state.get("url", "http://localhost:8000/mcp")}}
        )
        print(json.dumps({{
            "name": "vellis",
            "enabled": state.get("enabled", True),
            "transport": details,
        }}))
    else:
        transport = state.get("transport", "stdio")
        print("vellis:")
        print(f"  Scope: {{state.get('scope', 'User')}}")
        print(f"  Type: {{transport}}")
        if transport == "stdio":
            print(f"  Command: {{target[0]}}")
            print(f"  Args: {{shlex.join(target[1:])}}")
        else:
            print(f"  URL: {{state.get('url', 'http://localhost:8000/mcp')}}")
        environment = state.get("environment", {{}})
        rendered_environment = " ".join(f"{{key}}={{value}}" for key, value in environment.items())
        print(f"  Environment: {{rendered_environment}}")
        print("  Status: Connected")
    raise SystemExit(0)
if operation == "remove":
    state_path.write_text(json.dumps({{"status": "absent"}}), encoding="utf-8")
    raise SystemExit(0)
if operation == "add":
    separator = args.index("--")
    state_path.write_text(
        json.dumps({{"status": "matching", "target": args[separator + 1:]}}),
        encoding="utf-8",
    )
    raise SystemExit(0)
raise SystemExit(2)
"""


def _install_fake_clients(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    for name in ("codex", "claude"):
        executable = bin_directory / name
        executable.write_text(FAKE_CLIENT.format(python=sys.executable), encoding="utf-8")
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
        (tmp_path / f"{name}-state.json").write_text(
            json.dumps({"status": "absent"}), encoding="utf-8"
        )
    monkeypatch.setenv("FAKE_MCP_DIR", str(tmp_path))
    monkeypatch.setenv("PATH", f"{bin_directory}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_directory


def _set_state(tmp_path: Path, client: str, state: dict[str, object]) -> None:
    (tmp_path / f"{client}-state.json").write_text(json.dumps(state), encoding="utf-8")


def _calls(tmp_path: Path, client: str) -> list[list[str]]:
    path = tmp_path / f"{client}-log.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_neither_client_executes_no_public_cli(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    assert (
        plan_clients(
            clients=(),
            replace_clients=(),
            project_directory=tmp_path,
            data_directory=tmp_path / "memory",
        )
        == ()
    )
    assert _calls(tmp_path, "codex") == []
    assert _calls(tmp_path, "claude") == []


@pytest.mark.parametrize("clients", [(ClientKind.CODEX,), (ClientKind.CLAUDE,), tuple(ClientKind)])
def test_each_or_both_clients_use_only_the_public_cli_argument_arrays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clients: tuple[ClientKind, ...]
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    destination = tmp_path / "memory with spaces"
    target = server_argv(tmp_path, destination)
    plans = plan_clients(
        clients=clients,
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=destination,
    )
    assert all(
        plan.state is ClientState.ABSENT and plan.action is ClientAction.ADD for plan in plans
    )
    outcomes = apply_plans(plans)
    assert all(outcome.succeeded and outcome.changed for outcome in outcomes)
    if ClientKind.CODEX in clients:
        assert _calls(tmp_path, "codex") == [
            ["mcp", "get", "vellis", "--json"],
            ["mcp", "get", "vellis", "--json"],
            ["mcp", "add", "vellis", "--", *target],
        ]
    if ClientKind.CLAUDE in clients:
        assert _calls(tmp_path, "claude") == [
            ["mcp", "get", "vellis"],
            ["mcp", "get", "vellis"],
            ["mcp", "add", "--scope", "user", "vellis", "--", *target],
        ]


def test_installed_setup_registers_the_interpreter_that_owns_vellis(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    installed_module = tmp_path / "environment" / "site-packages" / "vellis" / "setup.py"
    monkeypatch.setattr(setup_implementation, "__file__", str(installed_module))
    destination = tmp_path / "memory"

    assert (
        setup_implementation.main(
            [
                "--data-dir",
                str(destination),
                "--vocabulary",
                "blank",
                "--client",
                "codex",
                "--yes",
            ],
            stdout=io.StringIO(),
            stderr=io.StringIO(),
        )
        == EXIT_SUCCESS
    )

    state = json.loads((tmp_path / "codex-state.json").read_text(encoding="utf-8"))
    assert state["target"] == [
        str(Path(sys.executable).absolute()),
        "-m",
        "vellis",
        "--data-dir",
        str(destination.resolve()),
    ]


def test_installed_client_failure_reports_an_installed_retry_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(tmp_path, "codex", {"status": "unparseable"})
    installed_module = tmp_path / "environment" / "site-packages" / "vellis" / "setup.py"
    monkeypatch.setattr(setup_implementation, "__file__", str(installed_module))
    destination = tmp_path / "memory"
    error = io.StringIO()

    assert (
        setup_implementation.main(
            [
                "--data-dir",
                str(destination),
                "--vocabulary",
                "blank",
                "--client",
                "codex",
                "--yes",
            ],
            stdout=io.StringIO(),
            stderr=error,
        )
        == EXIT_FAILED
    )

    retry = render_command(
        (
            str(Path(sys.executable).absolute()),
            "-m",
            "vellis.setup",
            "--data-dir",
            str(destination.resolve()),
            "--client",
            "codex",
            "--yes",
        )
    )
    assert "failed stage: client inspection" in error.getvalue()
    assert f"Once inspection is readable, run: {retry}" in error.getvalue()
    assert "uv --directory" not in error.getvalue()


def test_a_matching_entry_is_an_idempotent_no_op(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    target = server_argv(tmp_path, tmp_path / "memory")
    _set_state(tmp_path, "codex", {"status": "matching", "target": target})
    plans = plan_clients(
        clients=(ClientKind.CODEX,),
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )
    assert plans[0].action is ClientAction.NONE
    assert apply_plans(plans)[0].succeeded
    assert _calls(tmp_path, "codex") == [
        ["mcp", "get", "vellis", "--json"],
        ["mcp", "get", "vellis", "--json"],
    ]


def test_a_differing_entry_requires_that_clients_explicit_replacement_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(tmp_path, "claude", {"status": "matching", "target": ["wrong", "server"]})
    refused = plan_clients(
        clients=(ClientKind.CLAUDE,),
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )
    assert refused[0].action is ClientAction.REFUSE
    assert not apply_plans(refused)[0].succeeded
    assert all(call[1] == "get" for call in _calls(tmp_path, "claude"))

    replacing = plan_clients(
        clients=(ClientKind.CLAUDE,),
        replace_clients=(ClientKind.CLAUDE,),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )
    assert replacing[0].action is ClientAction.REPLACE
    assert apply_plans(replacing)[0].succeeded
    assert ["mcp", "remove", "vellis"] in _calls(tmp_path, "claude")


def test_a_disabled_codex_http_entry_is_a_replaceable_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(
        tmp_path,
        "codex",
        {
            "status": "matching",
            "target": [],
            "enabled": False,
            "transport": "streamable_http",
        },
    )
    plan = plan_clients(
        clients=(ClientKind.CODEX,),
        replace_clients=(ClientKind.CODEX,),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert plan.state is ClientState.DIFFERING
    assert plan.action is ClientAction.REPLACE


@pytest.mark.parametrize("client", tuple(ClientKind))
def test_a_launch_environment_makes_an_otherwise_matching_entry_differ(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, client: ClientKind
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    target = server_argv(tmp_path, tmp_path / "memory")
    _set_state(
        tmp_path,
        client.value,
        {
            "status": "matching",
            "target": target,
            "environment": {"VELLIS_DATA_DIR": str(tmp_path / "different-memory")},
        },
    )
    plan = plan_clients(
        clients=(client,),
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert plan.state is ClientState.DIFFERING
    assert plan.action is ClientAction.REFUSE


def test_a_claude_http_entry_is_a_replaceable_difference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(
        tmp_path,
        "claude",
        {"status": "matching", "target": [], "transport": "http"},
    )
    plan = plan_clients(
        clients=(ClientKind.CLAUDE,),
        replace_clients=(ClientKind.CLAUDE,),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert plan.state is ClientState.DIFFERING
    assert plan.action is ClientAction.REPLACE


def test_a_project_scoped_claude_entry_is_replaced_only_when_explicitly_selected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    target = server_argv(tmp_path, tmp_path / "memory")
    _set_state(
        tmp_path,
        "claude",
        {"status": "matching", "target": target, "scope": "Project config"},
    )
    refused = plan_clients(
        clients=(ClientKind.CLAUDE,),
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert refused.state is ClientState.DIFFERING
    assert refused.action is ClientAction.REFUSE

    replacing = plan_clients(
        clients=(ClientKind.CLAUDE,),
        replace_clients=(ClientKind.CLAUDE,),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert replacing.action is ClientAction.REPLACE
    assert apply_plans((replacing,))[0].succeeded
    assert ["mcp", "remove", "vellis"] in _calls(tmp_path, "claude")


def test_an_ambiguous_inspection_error_is_not_mistaken_for_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(tmp_path, "codex", {"status": "error"})
    plan = plan_clients(
        clients=(ClientKind.CODEX,),
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert plan.state is ClientState.UNPARSEABLE
    assert plan.action is ClientAction.REFUSE
    outcome = apply_plans((plan,))[0]
    assert outcome.failed_stage is ClientFailureStage.INSPECTION


def test_claude_output_without_scope_is_reported_as_unparseable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(tmp_path, "claude", {"status": "unparseable"})
    plan = plan_clients(
        clients=(ClientKind.CLAUDE,),
        replace_clients=(),
        project_directory=tmp_path,
        data_directory=tmp_path / "memory",
    )[0]
    assert plan.state is ClientState.UNPARSEABLE
    assert plan.action is ClientAction.REFUSE


def test_an_unexecutable_client_is_reported_instead_of_raising(tmp_path: Path) -> None:
    unusable = tmp_path / "codex"
    unusable.write_text("not executable", encoding="utf-8")
    result = subprocess_runner((str(unusable), "mcp", "get", "vellis", "--json"))
    assert result.returncode == 126
    assert result.stderr.startswith("executable unavailable:")


def test_missing_client_reports_a_copyable_command_without_undoing_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    destination = tmp_path / "memory with spaces"
    out, error = io.StringIO(), io.StringIO()
    code = main(
        ["--data-dir", str(destination), "--vocabulary", "blank", "--client", "codex", "--yes"],
        stdout=out,
        stderr=error,
    )
    assert code == EXIT_FAILED
    assert "install or repair the codex CLI" in error.getvalue()
    assert "`codex mcp get vellis --json` runs" in error.getvalue()
    assert "then run: uv --directory" in error.getvalue()
    assert "-m vellis.setup" in error.getvalue()
    assert render_command(("--data-dir", str(destination.resolve()))) in error.getvalue()
    assert "failed stage: client inspection" in error.getvalue()
    assert "established memory: changed" in error.getvalue()
    system = RTGSystem.open(store_path(destination.resolve()))
    try:
        assert system.is_initialized
        assert materialize_state(system).revision == 0
    finally:
        system.close()


def test_unparseable_inspection_is_separate_from_successful_initialization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    _set_state(tmp_path, "codex", {"status": "unparseable"})
    destination = tmp_path / "memory"
    out, error = io.StringIO(), io.StringIO()
    code = main(
        ["--data-dir", str(destination), "--vocabulary", "blank", "--client", "codex", "--yes"],
        stdout=out,
        stderr=error,
    )
    assert code == EXIT_FAILED
    assert "inspection output could not be classified" in error.getvalue()
    assert "failed stage: client inspection" in error.getvalue()
    assert "established memory: changed" in error.getvalue()
    assert "do not rerun setup before then" in error.getvalue()
    assert "stop and seek owner direction" in error.getvalue()
    assert "Once inspection is readable, run: uv --directory" in error.getvalue()
    assert "run python -m vellis.setup --data-dir" in error.getvalue()
    assert "--vocabulary" not in error.getvalue()
    system = RTGSystem.open(store_path(destination.resolve()))
    try:
        before = materialize_state(system)
    finally:
        system.close()

    retry_error = io.StringIO()
    failed_retry = main(
        ["--data-dir", str(destination), "--client", "codex", "--yes"],
        stdout=io.StringIO(),
        stderr=retry_error,
    )
    assert failed_retry == EXIT_FAILED
    assert "failed stage: client inspection" in retry_error.getvalue()
    assert "established memory: unchanged" in retry_error.getvalue()

    _set_state(tmp_path, "codex", {"status": "absent"})
    retry_out, retry_error = io.StringIO(), io.StringIO()
    retry = main(
        ["--data-dir", str(destination), "--client", "codex", "--yes"],
        stdout=retry_out,
        stderr=retry_error,
    )
    assert retry == EXIT_SUCCESS
    assert "leave established memory unchanged" in retry_out.getvalue()
    assert retry_error.getvalue() == ""
    system = RTGSystem.open(store_path(destination.resolve()))
    try:
        assert materialize_state(system) == before
    finally:
        system.close()


def test_dry_run_inspects_but_mutates_neither_memory_nor_clients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_clients(tmp_path, monkeypatch)
    destination = tmp_path / "memory"
    out = io.StringIO()
    code = main(
        ["--data-dir", str(destination), "--client", "codex", "--dry-run"],
        stdout=out,
        stderr=io.StringIO(),
    )
    assert code == EXIT_SUCCESS
    assert not destination.exists()
    assert _calls(tmp_path, "codex") == [["mcp", "get", "vellis", "--json"]]
    assert "selected client inspection reads user-scoped MCP state" in out.getvalue()
    assert "nothing outside that directory is read or changed" not in out.getvalue()


def test_linux_and_windows_render_paths_and_non_default_destinations_without_loss(
    tmp_path: Path,
) -> None:
    linux_target = server_argv(tmp_path / "project with spaces", tmp_path / "memory with spaces")
    windows_target = (
        "uv",
        "--directory",
        r"C:\Users\Owner\Vellis Project",
        "run",
        "python",
        "-m",
        "vellis",
        "--data-dir",
        r"D:\Personal Memory\Vellis",
    )
    posix = render_command(linux_target, platform="linux")
    windows = render_command(windows_target, platform="win32")
    assert "'" in posix
    assert '"' in windows
    assert "--data-dir" in posix and "--data-dir" in windows
    assert str((tmp_path / "memory with spaces").resolve()) in posix
    assert r"C:\Users\Owner\Vellis Project" in windows
    assert r"D:\Personal Memory\Vellis" in windows
