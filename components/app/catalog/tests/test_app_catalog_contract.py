from __future__ import annotations

from pathlib import Path

import pytest

from components.app.catalog import (
    AppDescriptor,
    AppDescriptorInvalid,
    AppIdConflict,
    AppNotFound,
    CatalogQuery,
    InMemoryAppCatalog,
    JsonValue,
    LaunchSurface,
)
from components.app.catalog.protocol import AppCatalog
from components.app.catalog.reference import create_reference_component

MODEL_EVIDENCE = {
    "OpenAppCatalogContractVerification": (
        "test_open_rejects_duplicate_descriptor_identity",
        "test_reference_component_is_usable",
    ),
    "RegisterAppContractVerification": (
        "test_register_get_list_remove_round_trip",
        "test_register_replaces_existing_descriptor_for_same_app_id",
        "test_invalid_descriptors_are_not_visible",
        "test_catalog_returns_canonical_copies_not_mutable_input_state",
    ),
    "RemoveAppContractVerification": ("test_register_get_list_remove_round_trip",),
    "GetAppContractVerification": (
        "test_register_get_list_remove_round_trip",
        "test_catalog_returns_canonical_copies_not_mutable_input_state",
    ),
    "ListAppsContractVerification": (
        "test_list_apps_is_deterministic_and_filterable",
        "test_launch_surfaces_are_sorted_metadata_not_runtime_state",
    ),
    "AppCatalogBoundaryVerification": (
        "test_register_get_list_remove_round_trip",
        "test_register_replaces_existing_descriptor_for_same_app_id",
        "test_open_rejects_duplicate_descriptor_identity",
        "test_list_apps_is_deterministic_and_filterable",
        "test_launch_surfaces_are_sorted_metadata_not_runtime_state",
        "test_invalid_descriptors_are_not_visible",
        "test_catalog_returns_canonical_copies_not_mutable_input_state",
        "test_reference_component_is_usable",
        "test_no_forbidden_dependency_imports",
    ),
}


def descriptor(
    app_id: str = "rtg_knowledge_graph",
    *,
    status: str = "available",
    tags: tuple[str, ...] = ("knowledge", "rtg"),
    launch_surfaces: tuple[LaunchSurface, ...] | None = None,
    recommended_surface: str | None = "mcp_stdio",
    metadata: dict[str, JsonValue] | None = None,
) -> AppDescriptor:
    surfaces = launch_surfaces or (
        LaunchSurface(
            surface_id="mcp_stdio",
            kind="mcp_stdio",
            mode="launch",
            label="MCP stdio",
            details={"server_name": app_id},
        ),
    )
    return AppDescriptor(
        app_id=app_id,
        title=app_id.replace("_", " ").title(),
        summary=f"{app_id} summary",
        status=status,
        tags=tags,
        launch_surfaces=surfaces,
        recommended_surface=recommended_surface,
        metadata=metadata or {},
    )


def open_catalog(*descriptors: AppDescriptor) -> AppCatalog:
    return InMemoryAppCatalog.open(descriptors)


def test_register_get_list_remove_round_trip() -> None:
    catalog = open_catalog()
    registered = catalog.register_app(descriptor(metadata={"version": 1}))

    assert registered.app_id == "rtg_knowledge_graph"
    assert catalog.get_app("rtg_knowledge_graph") == registered
    assert catalog.list_apps().apps == (registered,)

    removed = catalog.remove_app("rtg_knowledge_graph")
    assert removed == registered
    with pytest.raises(AppNotFound):
        catalog.get_app("rtg_knowledge_graph")


def test_register_replaces_existing_descriptor_for_same_app_id() -> None:
    catalog = open_catalog(descriptor(status="draft"))

    replacement = catalog.register_app(descriptor(status="available", metadata={"new": True}))

    assert replacement.status == "available"
    assert catalog.list_apps().apps == (replacement,)


def test_open_rejects_duplicate_descriptor_identity() -> None:
    with pytest.raises(AppIdConflict):
        InMemoryAppCatalog.open((descriptor("one"), descriptor("one")))


def test_list_apps_is_deterministic_and_filterable() -> None:
    catalog = open_catalog(
        descriptor(
            "beta",
            status="draft",
            tags=("personal", "lab"),
            launch_surfaces=(
                LaunchSurface(
                    "web", "localhost_http", "attach", "Web", {"url": "http://127.0.0.1"}
                ),
            ),
            recommended_surface="web",
        ),
        descriptor("alpha", status="available", tags=("personal", "mcp")),
        descriptor("gamma", status="available", tags=("ops", "mcp")),
    )

    assert [app.app_id for app in catalog.list_apps().apps] == ["alpha", "beta", "gamma"]
    assert [app.app_id for app in catalog.list_apps(CatalogQuery(status="available")).apps] == [
        "alpha",
        "gamma",
    ]
    assert [app.app_id for app in catalog.list_apps(CatalogQuery(tags=("personal",))).apps] == [
        "alpha",
        "beta",
    ]
    assert [
        app.app_id
        for app in catalog.list_apps(CatalogQuery(launch_surface_kind="localhost_http")).apps
    ] == ["beta"]


def test_launch_surfaces_are_sorted_metadata_not_runtime_state() -> None:
    catalog = open_catalog()
    registered = catalog.register_app(
        descriptor(
            launch_surfaces=(
                LaunchSurface(
                    "web", "localhost_http", "attach", "Web", {"url": "http://127.0.0.1"}
                ),
                LaunchSurface("stdio", "mcp_stdio", "launch", "Stdio", {"server_name": "rtg"}),
            ),
            recommended_surface="stdio",
        )
    )

    assert [surface.surface_id for surface in registered.launch_surfaces] == ["stdio", "web"]
    assert [surface.runtime_control for surface in registered.launch_surfaces] == [
        "managed",
        "managed",
    ]
    assert all(not hasattr(surface, "process_id") for surface in registered.launch_surfaces)


@pytest.mark.parametrize(
    "invalid_descriptor",
    [
        descriptor(app_id=""),
        descriptor(app_id="has whitespace"),
        descriptor(status=""),
        descriptor(tags=("ok", "bad tag")),
        descriptor(
            launch_surfaces=(
                LaunchSurface("same", "mcp_stdio", "launch", "One", {}),
                LaunchSurface("same", "localhost_http", "attach", "Two", {}),
            )
        ),
        descriptor(
            launch_surfaces=(LaunchSurface("bad", "mcp_stdio", "unsupported", "Bad", {}),),
            recommended_surface="bad",
        ),
        descriptor(
            launch_surfaces=(
                LaunchSurface(
                    "bad-control",
                    "mcp_stdio",
                    "launch",
                    "Bad control",
                    {},
                    runtime_control="unmanaged",
                ),
            ),
            recommended_surface="bad-control",
        ),
        descriptor(recommended_surface="missing"),
        descriptor(metadata={"bad": object()}),  # type: ignore[dict-item]
        descriptor(
            launch_surfaces=(
                LaunchSurface(
                    "bad",
                    "mcp_stdio",
                    "launch",
                    "Bad",
                    {"nan": float("nan")},
                ),
            ),
            recommended_surface="bad",
        ),
    ],
)
def test_invalid_descriptors_are_not_visible(invalid_descriptor: AppDescriptor) -> None:
    catalog = open_catalog()

    with pytest.raises(AppDescriptorInvalid):
        catalog.register_app(invalid_descriptor)

    assert catalog.list_apps().apps == ()


def test_catalog_returns_canonical_copies_not_mutable_input_state() -> None:
    metadata: dict[str, JsonValue] = {"nested": {"value": "before"}}
    surface_details: dict[str, JsonValue] = {"server_name": "before"}
    catalog = open_catalog()
    catalog.register_app(
        descriptor(
            metadata=metadata,
            launch_surfaces=(
                LaunchSurface(
                    "stdio",
                    "mcp_stdio",
                    "launch",
                    "Stdio",
                    surface_details,
                ),
            ),
            recommended_surface="stdio",
        )
    )

    metadata["nested"] = {"value": "after"}
    surface_details["server_name"] = "after"
    first_read = catalog.get_app("rtg_knowledge_graph")
    first_read.metadata["nested"] = {"value": "mutated"}
    first_read.launch_surfaces[0].details["server_name"] = "mutated"

    second_read = catalog.get_app("rtg_knowledge_graph")
    assert second_read.metadata == {"nested": {"value": "before"}}
    assert second_read.launch_surfaces[0].details == {"server_name": "before"}


def test_reference_component_is_usable() -> None:
    catalog = create_reference_component()

    listed = catalog.list_apps()

    assert [app.app_id for app in listed.apps] == ["rtg_knowledge_graph"]


def test_no_forbidden_dependency_imports() -> None:
    component_root = Path(__file__).parents[1]
    forbidden_terms = (
        "components.app.launcher",
        "components.app.shell",
        "components.rtg",
        "subprocess",
        "requests",
        "fastmcp",
    )

    for path in component_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in forbidden_terms), path
