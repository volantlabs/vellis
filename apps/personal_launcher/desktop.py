from __future__ import annotations

import os
import plistlib
import shlex
import shutil
import stat
import subprocess
from pathlib import Path

DEFAULT_APP_NAME = "Vellis Launcher.app"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18777
LAUNCH_AGENT_LABEL = "com.vellis.personal-launcher"
DEFAULT_LAUNCH_AGENT_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
DEFAULT_RUNTIME_ROOT = Path.home() / ".vellis" / "personal-launcher-runtime"
APP_ICON_NAME = "AppIcon.icns"


def install_desktop_app(
    *,
    repo_root: Path,
    destination: Path | None = None,
    launch_agent_path: Path = DEFAULT_LAUNCH_AGENT_PATH,
    runtime_root: Path = DEFAULT_RUNTIME_ROOT,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    load_agent: bool = True,
) -> Path:
    app_path = destination or Path.home() / "Desktop" / DEFAULT_APP_NAME
    if app_path.exists():
        shutil.rmtree(app_path)

    _write_launch_agent(
        launch_agent_path,
        repo_root=repo_root,
        runtime_root=runtime_root,
        host=host,
        port=port,
    )
    if load_agent:
        _load_launch_agent(launch_agent_path)

    contents_dir = app_path / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"
    macos_dir.mkdir(parents=True)
    resources_dir.mkdir(parents=True)

    executable_name = "vellis-launcher"
    _write_info_plist(contents_dir / "Info.plist", executable_name)
    _write_app_icon(resources_dir / APP_ICON_NAME)
    executable_path = macos_dir / executable_name
    executable_path.write_text(
        _launcher_script(repo_root=repo_root, host=host, port=port),
        encoding="utf-8",
    )
    executable_path.chmod(
        executable_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    )
    return app_path


def _write_info_plist(path: Path, executable_name: str) -> None:
    payload = {
        "CFBundleDevelopmentRegion": "en",
        "CFBundleDisplayName": "Vellis Launcher",
        "CFBundleExecutable": executable_name,
        "CFBundleIconFile": "AppIcon",
        "CFBundleIdentifier": "com.vellis.personal-launcher",
        "CFBundleName": "Vellis Launcher",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "LSMinimumSystemVersion": "13.0",
        "NSHighResolutionCapable": True,
    }
    with path.open("wb") as file:
        plistlib.dump(payload, file)


def _write_app_icon(path: Path) -> None:
    source = Path(__file__).parent / "static" / APP_ICON_NAME
    shutil.copy2(source, path)


def _launcher_script(*, repo_root: Path, host: str, port: int) -> str:
    url = f"http://{host}:{port}/"
    label = f"gui/$(id -u)/{LAUNCH_AGENT_LABEL}"
    return f"""#!/bin/zsh
set -eu
if /usr/bin/curl -fsS {shlex.quote(url)}api/state >/dev/null 2>&1; then
  /usr/bin/open {shlex.quote(url)}
  exit 0
fi
/bin/launchctl kickstart -k {shlex.quote(label)} >/dev/null 2>&1 || true
sleep 1
/usr/bin/open {shlex.quote(url)}
exit 0
"""


def _write_launch_agent(
    path: Path,
    *,
    repo_root: Path,
    runtime_root: Path,
    host: str,
    port: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _sync_runtime_bundle(source_root=repo_root, runtime_root=runtime_root)
    log_path = Path.home() / "Library" / "Logs" / "VellisLauncher.log"
    python_path = (repo_root / ".venv" / "bin" / "python").resolve()
    command = (
        f"cd {shlex.quote(str(runtime_root))} && "
        f"exec /usr/bin/env -i "
        f"HOME={shlex.quote(str(Path.home()))} "
        f"USER={shlex.quote(os.environ.get('USER', ''))} "
        f"LOGNAME={shlex.quote(os.environ.get('LOGNAME', os.environ.get('USER', '')))} "
        f"SHELL=/bin/zsh "
        f"TMPDIR={shlex.quote(os.environ.get('TMPDIR', '/tmp'))} "
        f"LANG=C.UTF-8 LC_ALL=C.UTF-8 "
        f"PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin "
        f"PYTHONPATH={shlex.quote(str(runtime_root))} "
        f"{shlex.quote(str(python_path))} "
        f"-m apps.personal_launcher --host {shlex.quote(host)} --port {port} "
        f"--repo-root {shlex.quote(str(repo_root))}"
    )
    payload = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": ["/bin/zsh", "-lc", command],
        "RunAtLoad": True,
        "KeepAlive": True,
        "WorkingDirectory": str(runtime_root),
        "StandardOutPath": str(log_path),
        "StandardErrorPath": str(log_path),
    }
    with path.open("wb") as file:
        plistlib.dump(payload, file)


def _load_launch_agent(path: Path) -> None:
    domain = f"gui/{os.getuid()}"
    subprocess.run(["/bin/launchctl", "bootout", domain, str(path)], check=False)
    subprocess.run(["/bin/launchctl", "bootstrap", domain, str(path)], check=False)
    subprocess.run(
        ["/bin/launchctl", "kickstart", "-k", f"{domain}/{LAUNCH_AGENT_LABEL}"],
        check=False,
    )


def _sync_runtime_bundle(*, source_root: Path, runtime_root: Path) -> None:
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    (runtime_root / "apps").mkdir(parents=True)
    (runtime_root / "components").mkdir(parents=True)
    shutil.copy2(source_root / "apps" / "__init__.py", runtime_root / "apps" / "__init__.py")
    shutil.copy2(
        source_root / "components" / "__init__.py",
        runtime_root / "components" / "__init__.py",
    )
    shutil.copytree(
        source_root / "apps" / "personal_launcher",
        runtime_root / "apps" / "personal_launcher",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
    shutil.copytree(
        source_root / "components" / "app",
        runtime_root / "components" / "app",
        ignore=shutil.ignore_patterns("__pycache__", "tests"),
    )
