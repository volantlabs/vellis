from __future__ import annotations

from components.app.catalog.reference import create_reference_component as create_reference_catalog
from components.app.launcher.implementation import InMemoryAppLauncher, InMemoryRuntimeAdapter
from components.app.launcher.protocol import AppLauncher, LaunchRequest


def create_reference_component() -> AppLauncher:
    return InMemoryAppLauncher.open(
        app_catalog=create_reference_catalog(),
        runtime_adapter=InMemoryRuntimeAdapter(),
    )


def main() -> None:
    launcher = create_reference_component()
    result = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    print(result)


if __name__ == "__main__":
    main()
