from __future__ import annotations

from pathlib import Path

import pytest

from components.app.catalog import AppDescriptor, InMemoryAppCatalog, LaunchSurface
from components.app.launcher import InMemoryAppLauncher, InMemoryRuntimeAdapter, LaunchRequest
from components.app.launcher.protocol import SessionNotFound
from components.app.shell import (
    AppCloseRejected,
    AppOpenRequest,
    CloseRequest,
    InMemoryAppShell,
    ShellOptions,
    ShellQuery,
)
from components.app.shell.reference import create_reference_component

MODEL_EVIDENCE = {
    "GetHomeContractVerification": (
        "test_open_shell_does_not_launch_or_attach_apps",
        "test_home_view_filters_apps_and_remains_renderer_neutral",
        "test_restored_active_session_is_used_when_present",
    ),
    "OpenAppContractVerification": (
        "test_open_app_launches_through_launcher_and_sets_active_app",
        "test_handoff_launch_is_recent_history_without_active_session",
        "test_open_app_can_attach_through_launcher",
    ),
    "SwitchAppContractVerification": (
        "test_switch_app_uses_existing_session_without_launching",
        "test_missing_session_errors_preserve_launcher_meaning",
    ),
    "CloseAppContractVerification": (
        "test_close_app_clears_active_state_without_stopping_by_default",
        "test_close_app_can_stop_launcher_owned_session",
        "test_close_app_rejects_stopping_external_session",
        "test_missing_session_errors_preserve_launcher_meaning",
    ),
    "OpenAppShellContractVerification": (
        "test_open_shell_does_not_launch_or_attach_apps",
        "test_restored_active_session_is_used_when_present",
    ),
    "AppShellBoundaryVerification": (
        "test_open_shell_does_not_launch_or_attach_apps",
        "test_open_app_launches_through_launcher_and_sets_active_app",
        "test_handoff_launch_is_recent_history_without_active_session",
        "test_open_app_can_attach_through_launcher",
        "test_switch_app_uses_existing_session_without_launching",
        "test_close_app_clears_active_state_without_stopping_by_default",
        "test_close_app_can_stop_launcher_owned_session",
        "test_close_app_rejects_stopping_external_session",
        "test_home_view_filters_apps_and_remains_renderer_neutral",
        "test_missing_session_errors_preserve_launcher_meaning",
        "test_restored_active_session_is_used_when_present",
        "test_reference_component_is_usable",
        "test_no_forbidden_dependency_imports",
    ),
}


def descriptor(
    app_id: str,
    *,
    surface_id: str = "stdio",
    mode: str = "launch",
    kind: str = "mcp_stdio",
    runtime_control: str = "managed",
) -> AppDescriptor:
    return AppDescriptor(
        app_id=app_id,
        title=app_id.replace("_", " ").title(),
        summary=f"{app_id} summary",
        status="available",
        tags=("personal", "app"),
        launch_surfaces=(
            LaunchSurface(
                surface_id=surface_id,
                kind=kind,
                mode=mode,
                label=surface_id,
                details={"endpoint": surface_id},
                runtime_control=runtime_control,
            ),
        ),
        recommended_surface=surface_id,
    )


def shell_with_apps(
    *apps: AppDescriptor,
) -> tuple[InMemoryAppShell, InMemoryRuntimeAdapter]:
    catalog = InMemoryAppCatalog.open(apps)
    runtime = InMemoryRuntimeAdapter()
    launcher = InMemoryAppLauncher.open(catalog, runtime)
    return InMemoryAppShell.open(catalog, launcher), runtime


def test_open_shell_does_not_launch_or_attach_apps() -> None:
    shell, runtime = shell_with_apps(descriptor("rtg_knowledge_graph"))

    view = shell.get_home()

    assert [app.app_id for app in view.apps] == ["rtg_knowledge_graph"]
    assert view.sessions == ()
    assert view.recent_launches == ()
    assert view.active_app is None
    assert runtime.started_surfaces == []
    assert runtime.attached_surfaces == []


def test_open_app_launches_through_launcher_and_sets_active_app() -> None:
    shell, runtime = shell_with_apps(descriptor("rtg_knowledge_graph"))

    result = shell.open_app(AppOpenRequest("rtg_knowledge_graph"))

    assert result.app is not None
    assert result.app.app_id == "rtg_knowledge_graph"
    assert result.session is not None
    assert result.view.active_app is not None
    assert result.view.active_app.session.session_id == result.session.session_id
    assert runtime.started_surfaces == ["stdio"]
    assert shell.recent_app_ids == ("rtg_knowledge_graph",)


def test_handoff_launch_is_recent_history_without_active_session() -> None:
    shell, runtime = shell_with_apps(
        descriptor(
            "docs",
            surface_id="web",
            kind="localhost_http",
            runtime_control="handoff",
        )
    )

    result = shell.open_app(AppOpenRequest("docs"))

    assert result.session is None
    assert result.handoff is not None
    assert result.view.active_app is None
    assert result.view.sessions == ()
    assert result.view.recent_launches == (result.handoff,)
    assert runtime.started_surfaces == ["web"]
    result.handoff.endpoint["endpoint"] = "mutated"
    assert shell.get_home().recent_launches[0].endpoint["endpoint"] == "web"


def test_open_app_can_attach_through_launcher() -> None:
    shell, runtime = shell_with_apps(
        descriptor("rtg_knowledge_graph", surface_id="web", mode="attach", kind="localhost_http")
    )

    result = shell.open_app(AppOpenRequest("rtg_knowledge_graph", mode="attach"))

    assert result.session is not None
    assert result.session.ownership == "external"
    assert runtime.attached_surfaces == ["web"]


def test_switch_app_uses_existing_session_without_launching() -> None:
    shell, runtime = shell_with_apps(descriptor("alpha"), descriptor("beta"))
    alpha = shell.open_app(AppOpenRequest("alpha")).session
    beta = shell.open_app(AppOpenRequest("beta")).session
    assert alpha is not None
    assert beta is not None
    runtime.started_surfaces.clear()

    result = shell.switch_app(alpha.session_id)

    assert result.view.active_app is not None
    assert result.view.active_app.app.app_id == "alpha"
    assert runtime.started_surfaces == []


def test_close_app_clears_active_state_without_stopping_by_default() -> None:
    shell, runtime = shell_with_apps(descriptor("rtg_knowledge_graph"))
    opened = shell.open_app(AppOpenRequest("rtg_knowledge_graph"))
    assert opened.session is not None

    result = shell.close_app(CloseRequest(opened.session.session_id))

    assert result.view.active_app is None
    assert runtime.stopped_sessions == []


def test_close_app_can_stop_launcher_owned_session() -> None:
    shell, runtime = shell_with_apps(descriptor("rtg_knowledge_graph"))
    opened = shell.open_app(AppOpenRequest("rtg_knowledge_graph"))
    assert opened.session is not None

    result = shell.close_app(CloseRequest(opened.session.session_id, stop_runtime=True))

    assert result.session is not None
    assert result.session.status == "stopped"
    assert runtime.stopped_sessions == [opened.session.session_id]


def test_close_app_rejects_stopping_external_session() -> None:
    shell, runtime = shell_with_apps(
        descriptor("rtg_knowledge_graph", surface_id="web", mode="attach", kind="localhost_http")
    )
    opened = shell.open_app(AppOpenRequest("rtg_knowledge_graph", mode="attach"))
    assert opened.session is not None

    with pytest.raises(AppCloseRejected):
        shell.close_app(CloseRequest(opened.session.session_id, stop_runtime=True))

    assert runtime.stopped_sessions == []


def test_home_view_filters_apps_and_remains_renderer_neutral() -> None:
    shell, _runtime = shell_with_apps(
        descriptor("alpha"),
        AppDescriptor(
            app_id="draft",
            title="Draft",
            summary="Draft summary",
            status="draft",
            tags=("lab",),
            launch_surfaces=(LaunchSurface("stdio", "mcp_stdio", "launch", "stdio", {}),),
            recommended_surface="stdio",
        ),
    )

    view = shell.get_home(ShellQuery(status="draft"))

    assert [app.app_id for app in view.apps] == ["draft"]
    assert view.available_commands == ("open_app", "switch_app", "close_app")
    assert not hasattr(view, "html")


def test_missing_session_errors_preserve_launcher_meaning() -> None:
    shell, _runtime = shell_with_apps(descriptor("rtg_knowledge_graph"))

    with pytest.raises(SessionNotFound):
        shell.switch_app("missing")
    with pytest.raises(SessionNotFound):
        shell.close_app(CloseRequest("missing"))
    with pytest.raises(AppCloseRejected):
        shell.close_app(CloseRequest())


def test_restored_active_session_is_used_when_present() -> None:
    catalog = InMemoryAppCatalog.open((descriptor("rtg_knowledge_graph"),))
    runtime = InMemoryRuntimeAdapter()
    launcher = InMemoryAppLauncher.open(catalog, runtime)
    launched_result = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    assert launched_result.session is not None
    shell = InMemoryAppShell.open(
        catalog,
        launcher,
        ShellOptions(restored_active_session_id=launched_result.session.session_id),
    )

    assert shell.get_home().active_app is not None


def test_reference_component_is_usable() -> None:
    shell = create_reference_component()

    result = shell.open_app(AppOpenRequest("rtg_knowledge_graph"))

    assert result.view.active_app is not None


def test_no_forbidden_dependency_imports() -> None:
    component_root = Path(__file__).parents[1]
    forbidden_terms = (
        "components.app.catalog.implementation",
        "components.app.launcher.implementation",
        "components.rtg",
        "subprocess",
        "requests",
        "fastmcp",
        "flask",
        "django",
    )

    for path in component_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in forbidden_terms), path
