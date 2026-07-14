from __future__ import annotations

from components.app.catalog.reference import create_reference_component as create_reference_catalog
from components.app.launcher import InMemoryAppLauncher, InMemoryRuntimeAdapter
from components.app.shell.implementation import InMemoryAppShell
from components.app.shell.protocol import AppOpenRequest, AppShell


def create_reference_component() -> AppShell:
    catalog = create_reference_catalog()
    launcher = InMemoryAppLauncher.open(catalog, InMemoryRuntimeAdapter())
    return InMemoryAppShell.open(catalog, launcher)


def main() -> None:
    shell = create_reference_component()
    result = shell.open_app(AppOpenRequest("rtg_knowledge_graph"))
    print(result.view)


if __name__ == "__main__":
    main()
