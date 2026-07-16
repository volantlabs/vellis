from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _wheel() -> Path:
    wheels = sorted((ROOT / "dist").glob("vellis-*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected one built wheel, found {len(wheels)}")
    return wheels[0]


def _required_resources() -> set[str]:
    resources = {
        path.relative_to(ROOT).as_posix()
        for root in (ROOT / "components", ROOT / "apps")
        for path in root.glob("**/resources/*.json")
        if "tests" not in path.parts
    }
    if not resources:
        raise SystemExit("no generated package resources found")
    return resources


def _verify_wheel_inventory(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        packaged = set(archive.namelist())
    missing = sorted(_required_resources() - packaged)
    if missing:
        raise SystemExit("wheel omits package resources:\n" + "\n".join(missing))


def _verify_isolated_install(wheel: Path) -> None:
    script = """
import asyncio
import importlib
import tempfile
from pathlib import Path

from apps.rtg_knowledge_graph.composition import build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
modules = (
    "components.rtg.change_validation.runtime_binding",
    "components.rtg.constraints.runtime_binding",
    "components.rtg.controller.runtime_binding",
    "components.rtg.graph.runtime_binding",
    "components.rtg.migration.runtime_binding",
    "components.rtg.query.runtime_binding",
    "components.rtg.schema.runtime_binding",
    "components.storage.json_file.runtime_binding",
    "components.storage.sql.runtime_binding",
)
for name in modules:
    module = importlib.import_module(name)
    binding = getattr(module, "_RUNTIME_BINDING", None)
    if binding is None:
        binding = getattr(module, "CONTROLLER_RUNTIME_BINDING")
    assert binding.actions

from components.interface.mcp_gateway import RuntimeMcpGateway
gateway_binding = RuntimeMcpGateway().create_adapter().describe()
assert gateway_binding.binding_id == "binding.python.interface.mcp_gateway.v2"
assert gateway_binding.actions == ()

async def main() -> None:
    with tempfile.TemporaryDirectory() as value:
        root = Path(value)
        app = await build_app(
            RtgKnowledgeGraphConfig(
                storage_root=root / "documents",
                runtime_database_path=root / "runtime.sqlite",
                install_starter_schema=False,
            )
        )
        await app.close()

asyncio.run(main())
"""
    with tempfile.TemporaryDirectory() as workdir:
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        command = [
            shutil.which("uv") or os.fspath(Path.home() / ".local" / "bin" / "uv"),
            "run",
            "--isolated",
            "--no-project",
            "--python",
            "3.14",
            "--with",
            os.fspath(wheel),
            "python",
            "-c",
            script,
        ]
        subprocess.run(command, cwd=workdir, env=env, check=True)


def main() -> int:
    wheel = _wheel()
    _verify_wheel_inventory(wheel)
    _verify_isolated_install(wheel)
    print(f"Verified installed package: {wheel.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
