from __future__ import annotations

import os
import shlex
import signal
import subprocess
import webbrowser
from collections.abc import Callable, Sequence
from pathlib import Path

from components.app.catalog import JsonValue, LaunchSurface
from components.app.launcher import AppSession, RuntimeSurfaceResult

_KIND_COMMAND = "command"
_KIND_FILE = "file"
_KIND_URL = "url"
_RUNTIME_CONTROL_HANDOFF = "handoff"
_STARTUP_GRACE_SECONDS = 0.2


class DesktopRuntimeAdapter:
    """Local desktop runtime adapter for URL, file, and command launch surfaces."""

    def __init__(self, *, url_opener: Callable[[str], object] | None = None) -> None:
        self._url_opener = url_opener or webbrowser.open
        self._processes: dict[int, subprocess.Popen[bytes]] = {}

    def supports(self, launch_surface: LaunchSurface, operation: str) -> bool:
        if launch_surface.kind in {_KIND_FILE, _KIND_URL}:
            return operation in {"launch", "attach"}
        if launch_surface.kind == _KIND_COMMAND:
            return operation == "launch"
        return False

    def start(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        if launch_surface.kind == _KIND_URL:
            return self._open_url(launch_surface)
        if launch_surface.kind == _KIND_FILE:
            return self._open_file(launch_surface)
        if launch_surface.kind == _KIND_COMMAND:
            return self._start_command(launch_surface)
        raise ValueError(f"unsupported launch surface kind: {launch_surface.kind}")

    def attach(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        if launch_surface.kind == _KIND_URL:
            return self._open_url(launch_surface, runtime_state="attached")
        if launch_surface.kind == _KIND_FILE:
            return self._open_file(launch_surface, runtime_state="attached")
        raise ValueError(f"unsupported attach surface kind: {launch_surface.kind}")

    def stop(self, session: AppSession) -> RuntimeSurfaceResult:
        pid_value = session.details.get("pid")
        stopped = False
        if isinstance(pid_value, int):
            process = self._processes.pop(pid_value, None)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                stopped = True
            elif process is None:
                try:
                    os.kill(pid_value, signal.SIGTERM)
                    stopped = True
                except OSError:
                    stopped = False
        return RuntimeSurfaceResult(
            endpoint=session.endpoint,
            details={
                "runtime_state": "stopped",
                "stop_signal_sent": stopped,
            },
        )

    def probe(self, session: AppSession) -> RuntimeSurfaceResult:
        pid_value = session.details.get("pid")
        if not isinstance(pid_value, int):
            return RuntimeSurfaceResult(
                endpoint=session.endpoint,
                details={"runtime_state": "exited"},
            )
        process = self._processes.get(pid_value)
        if process is None:
            return RuntimeSurfaceResult(
                endpoint=session.endpoint,
                details={"runtime_state": "exited"},
            )
        return_code = process.poll()
        if return_code is None:
            return RuntimeSurfaceResult(
                endpoint=session.endpoint,
                details={"runtime_state": "running", "pid": pid_value},
            )
        self._processes.pop(pid_value, None)
        return RuntimeSurfaceResult(
            endpoint=session.endpoint,
            details={
                "runtime_state": "exited",
                "pid": pid_value,
                "exit_code": return_code,
            },
        )

    def _open_url(
        self,
        launch_surface: LaunchSurface,
        *,
        runtime_state: str = "handed_off",
    ) -> RuntimeSurfaceResult:
        url = _required_string_detail(launch_surface, "url")
        opened = self._url_opener(url)
        if opened is False:
            raise RuntimeError(f"could not open launch surface URL: {url}")
        return RuntimeSurfaceResult(
            endpoint={"kind": _KIND_URL, "url": url},
            details={"runtime_state": runtime_state},
        )

    def _open_file(
        self,
        launch_surface: LaunchSurface,
        *,
        runtime_state: str = "handed_off",
    ) -> RuntimeSurfaceResult:
        path = Path(_required_string_detail(launch_surface, "path")).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"launch surface path does not exist: {path}")
        completed = subprocess.run(
            ["open", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            message = f"could not open launch surface path: {path}"
            raise RuntimeError(f"{message}: {detail}" if detail else message)
        return RuntimeSurfaceResult(
            endpoint={"kind": _KIND_FILE, "path": str(path)},
            details={"runtime_state": runtime_state},
        )

    def _start_command(self, launch_surface: LaunchSurface) -> RuntimeSurfaceResult:
        command = _command_detail(launch_surface)
        cwd = _optional_path_detail(launch_surface, "cwd")
        if launch_surface.runtime_control == _RUNTIME_CONTROL_HANDOFF:
            completed = subprocess.run(
                command,
                cwd=cwd,
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip()
                message = f"launch command exited with status {completed.returncode}"
                raise RuntimeError(f"{message}: {detail}" if detail else message)
            details: dict[str, JsonValue] = {
                "runtime_state": "handed_off",
                "exit_code": completed.returncode,
            }
            if completed.stdout.strip():
                details["stdout"] = completed.stdout.strip()
            return RuntimeSurfaceResult(
                endpoint={"kind": _KIND_COMMAND, "command": list(command)},
                details=details,
            )

        process = subprocess.Popen(command, cwd=cwd)
        try:
            return_code = process.wait(timeout=_STARTUP_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            return_code = None
        if return_code is not None:
            if return_code != 0:
                raise RuntimeError(f"launch command exited with status {return_code}")
            return RuntimeSurfaceResult(
                endpoint={"kind": _KIND_COMMAND, "command": list(command)},
                details={"runtime_state": "handed_off", "exit_code": return_code},
            )
        self._processes[process.pid] = process
        return RuntimeSurfaceResult(
            endpoint={"kind": _KIND_COMMAND, "command": list(command)},
            details={"runtime_state": "started", "pid": process.pid},
        )


def _required_string_detail(launch_surface: LaunchSurface, key: str) -> str:
    value = launch_surface.details.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{launch_surface.surface_id}.{key} must be a non-empty string")
    return value


def _optional_path_detail(launch_surface: LaunchSurface, key: str) -> Path | None:
    value = launch_surface.details.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{launch_surface.surface_id}.{key} must be a non-empty path string")
    return Path(value)


def _command_detail(launch_surface: LaunchSurface) -> Sequence[str]:
    value: JsonValue = launch_surface.details.get("command")
    if isinstance(value, str):
        command = shlex.split(value)
    elif isinstance(value, list):
        command = [item for item in value if isinstance(item, str)]
        if len(command) != len(value):
            raise ValueError(f"{launch_surface.surface_id}.command must contain only strings")
    else:
        raise ValueError(f"{launch_surface.surface_id}.command must be a string or list")
    if not command:
        raise ValueError(f"{launch_surface.surface_id}.command must not be empty")
    return command
