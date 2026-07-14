from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import webbrowser
from collections.abc import Sequence
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from apps.personal_launcher.catalog_store import DEFAULT_CATALOG_PATH
from apps.personal_launcher.desktop import DEFAULT_HOST, DEFAULT_PORT, install_desktop_app
from apps.personal_launcher.server import run_server
from apps.personal_launcher.service import PersonalLauncherConfig, build_service


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="personal_launcher")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("serve", "install-desktop-app"),
        default="serve",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--catalog-path", type=Path, default=DEFAULT_CATALOG_PATH)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--desktop-app-path", type=Path, default=None)
    parser.add_argument("--open-browser", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = args.repo_root.expanduser()

    if args.command == "install-desktop-app":
        app_path = install_desktop_app(
            repo_root=repo_root,
            destination=args.desktop_app_path,
            host=args.host,
            port=args.port,
        )
        if args.json:
            print(json.dumps({"desktop_app_path": str(app_path)}, sort_keys=True))
        else:
            print(f"Installed {app_path}")
        return 0

    url = f"http://{args.host}:{args.port}/"
    if args.open_browser and _launcher_is_running(args.host, args.port):
        _open_browser(url)
        return 0

    service = build_service(
        PersonalLauncherConfig(
            catalog_path=args.catalog_path.expanduser(),
            repo_root=repo_root,
        )
    )
    if args.open_browser:
        threading.Timer(0.25, _open_browser, args=(url,)).start()
    print(f"Vellis Launcher: {url}", flush=True)
    run_server(service, host=args.host, port=args.port)
    return 0


def _launcher_is_running(host: str, port: int) -> bool:
    try:
        with urlopen(f"http://{host}:{port}/api/state", timeout=0.35) as response:
            return response.status == 200
    except OSError, TimeoutError, URLError:
        return False


def _open_browser(url: str) -> None:
    if sys.platform == "darwin":
        subprocess.Popen(["open", url])
        return
    webbrowser.open(url)
