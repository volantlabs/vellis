from __future__ import annotations

from components.app.catalog.implementation import InMemoryAppCatalog
from components.app.catalog.protocol import AppCatalog, AppDescriptor, LaunchSurface


def create_reference_component() -> AppCatalog:
    catalog = InMemoryAppCatalog.open()
    catalog.register_app(
        AppDescriptor(
            app_id="rtg_knowledge_graph",
            title="RTG Knowledge Graph",
            summary="Local RTG knowledge system exposed through MCP.",
            status="available",
            tags=("knowledge", "rtg", "mcp"),
            launch_surfaces=(
                LaunchSurface(
                    surface_id="mcp_stdio",
                    kind="mcp_stdio",
                    mode="launch",
                    label="MCP stdio",
                    details={"server_name": "rtg_knowledge_graph"},
                ),
            ),
            recommended_surface="mcp_stdio",
        )
    )
    return catalog


def main() -> None:
    catalog = create_reference_component()
    print(catalog.list_apps())


if __name__ == "__main__":
    main()
