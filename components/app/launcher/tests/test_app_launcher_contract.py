from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from components.app.catalog import (
    AppDescriptor,
    AppNotFound,
    InMemoryAppCatalog,
    JsonValue,
    LaunchSurface,
)
from components.app.launcher import (
    AppLauncherConfigurationInvalid,
    AppLaunchResult,
    AppSession,
    InMemoryAppLauncher,
    InMemoryRuntimeAdapter,
    LaunchRequest,
    LaunchSurfaceNotFound,
    LaunchSurfaceUnsupported,
    SessionNotLauncherOwned,
    SessionQuery,
)
from components.app.launcher.protocol import AttachRequest, RuntimeSurfaceResult, SessionNotFound
from components.app.launcher.reference import create_reference_component

MODEL_EVIDENCE = {
    "LaunchAppContractVerification": (
        "test_launch_starts_declared_surface_and_records_owned_session",
        "test_handoff_launch_returns_receipt_without_recording_session",
        "test_launch_reuses_existing_owned_session_by_default",
        "test_launch_allows_multiple_sessions_when_surface_declares_policy",
        "test_missing_app_and_surface_fail_before_runtime_start",
        "test_mode_and_runtime_support_are_checked_before_runtime_start",
    ),
    "AttachAppContractVerification": (
        "test_attach_records_external_session_without_runtime_ownership",
        "test_missing_app_and_surface_fail_before_runtime_start",
    ),
    "StopSessionContractVerification": (
        "test_attach_records_external_session_without_runtime_ownership",
        "test_stop_session_only_stops_launcher_owned_sessions",
        "test_configuration_validation",
    ),
    "ListSessionsContractVerification": (
        "test_session_probe_marks_exited_managed_runtime",
        "test_list_sessions_filters_known_sessions",
        "test_sessions_are_copied_on_read",
    ),
    "OpenAppLauncherContractVerification": (
        "test_open_does_not_start_or_attach_apps",
        "test_configuration_validation",
    ),
    "SupportsRuntimeSurfaceContractVerification": (
        "test_mode_and_runtime_support_are_checked_before_runtime_start",
    ),
    "StartRuntimeSurfaceContractVerification": (
        "test_launch_starts_declared_surface_and_records_owned_session",
        "test_handoff_launch_returns_receipt_without_recording_session",
    ),
    "AttachRuntimeSurfaceContractVerification": (
        "test_attach_records_external_session_without_runtime_ownership",
    ),
    "StopRuntimeSurfaceContractVerification": (
        "test_stop_session_only_stops_launcher_owned_sessions",
        "test_attach_records_external_session_without_runtime_ownership",
    ),
    "ProbeRuntimeSurfaceContractVerification": ("test_session_probe_marks_exited_managed_runtime",),
    "AppLauncherBoundaryVerification": (
        "test_open_does_not_start_or_attach_apps",
        "test_launch_starts_declared_surface_and_records_owned_session",
        "test_handoff_launch_returns_receipt_without_recording_session",
        "test_launch_reuses_existing_owned_session_by_default",
        "test_launch_allows_multiple_sessions_when_surface_declares_policy",
        "test_attach_records_external_session_without_runtime_ownership",
        "test_stop_session_only_stops_launcher_owned_sessions",
        "test_session_probe_marks_exited_managed_runtime",
        "test_list_sessions_filters_known_sessions",
        "test_missing_app_and_surface_fail_before_runtime_start",
        "test_mode_and_runtime_support_are_checked_before_runtime_start",
        "test_sessions_are_copied_on_read",
        "test_reference_component_is_usable",
        "test_configuration_validation",
        "test_no_forbidden_dependency_imports",
    ),
}


class DeterministicClock:
    def __init__(self) -> None:
        self._next = datetime(2026, 7, 8, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self._next
        self._next = self._next + timedelta(seconds=1)
        return current


class IdFactory:
    def __init__(self) -> None:
        self._next = 1

    def __call__(self) -> str:
        value = f"session-{self._next}"
        self._next += 1
        return value


def surface(
    surface_id: str,
    kind: str,
    mode: str,
    details: dict[str, JsonValue] | None = None,
    *,
    runtime_control: str = "managed",
) -> LaunchSurface:
    return LaunchSurface(
        surface_id=surface_id,
        kind=kind,
        mode=mode,
        label=surface_id.replace("_", " ").title(),
        details=details or {"endpoint": surface_id},
        runtime_control=runtime_control,
    )


def required_session(result: AppLaunchResult) -> AppSession:
    assert result.session is not None
    return result.session


def descriptor(
    app_id: str = "rtg_knowledge_graph",
    *,
    launch_surfaces: tuple[LaunchSurface, ...] | None = None,
    recommended_surface: str | None = "stdio",
) -> AppDescriptor:
    return AppDescriptor(
        app_id=app_id,
        title=app_id.replace("_", " ").title(),
        summary=f"{app_id} summary",
        status="available",
        tags=("personal", "app"),
        launch_surfaces=launch_surfaces or (surface("stdio", "mcp_stdio", "launch"),),
        recommended_surface=recommended_surface,
    )


def launcher_with_catalog(
    *apps: AppDescriptor,
) -> tuple[InMemoryAppLauncher, InMemoryRuntimeAdapter]:
    runtime = InMemoryRuntimeAdapter()
    launcher = InMemoryAppLauncher(
        InMemoryAppCatalog.open(apps),
        runtime,
        clock=DeterministicClock(),
        id_factory=IdFactory(),
    )
    return launcher, runtime


def test_open_does_not_start_or_attach_apps() -> None:
    runtime = InMemoryRuntimeAdapter()

    InMemoryAppLauncher.open(InMemoryAppCatalog.open((descriptor(),)), runtime)

    assert runtime.started_surfaces == []
    assert runtime.attached_surfaces == []


def test_launch_starts_declared_surface_and_records_owned_session() -> None:
    launcher, runtime = launcher_with_catalog(descriptor())

    result = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))

    assert result.app.app_id == "rtg_knowledge_graph"
    assert result.reused_existing is False
    session = required_session(result)
    assert session.session_id == "session-1"
    assert session.status == "running"
    assert session.ownership == "launcher_owned"
    assert session.endpoint["kind"] == "mcp_stdio"
    assert runtime.started_surfaces == ["stdio"]
    assert [item.session_id for item in launcher.list_sessions().sessions] == [session.session_id]


def test_handoff_launch_returns_receipt_without_recording_session() -> None:
    launcher, runtime = launcher_with_catalog(
        descriptor(
            launch_surfaces=(
                surface("web", "localhost_http", "launch", runtime_control="handoff"),
            ),
            recommended_surface="web",
        )
    )

    result = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))

    assert result.session is None
    assert result.handoff is not None
    assert result.handoff.handoff_id == "session-1"
    assert result.handoff.app_id == "rtg_knowledge_graph"
    assert launcher.list_sessions().sessions == ()
    assert runtime.started_surfaces == ["web"]


def test_launch_reuses_existing_owned_session_by_default() -> None:
    launcher, runtime = launcher_with_catalog(descriptor())

    first = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    second = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    first_session = required_session(first)
    second_session = required_session(second)

    assert second.reused_existing is True
    assert second_session.session_id == first_session.session_id
    assert runtime.started_surfaces == ["stdio"]


def test_launch_allows_multiple_sessions_when_surface_declares_policy() -> None:
    launcher, runtime = launcher_with_catalog(
        descriptor(
            launch_surfaces=(
                surface(
                    "stdio",
                    "mcp_stdio",
                    "launch",
                    {"endpoint": "stdio", "session_policy": "multiple"},
                ),
            )
        )
    )

    first = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    second = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))

    assert required_session(first).session_id == "session-1"
    assert required_session(second).session_id == "session-2"
    assert runtime.started_surfaces == ["stdio", "stdio"]


def test_attach_records_external_session_without_runtime_ownership() -> None:
    launcher, runtime = launcher_with_catalog(
        descriptor(
            launch_surfaces=(
                surface("web", "localhost_http", "attach", {"url": "http://127.0.0.1"}),
            ),
            recommended_surface="web",
        )
    )

    result = launcher.attach_app(AttachRequest("rtg_knowledge_graph"))
    session = required_session(result)

    assert session.ownership == "external"
    assert session.status == "running"
    assert session.endpoint["url"] == "http://127.0.0.1"
    assert runtime.attached_surfaces == ["web"]
    with pytest.raises(SessionNotLauncherOwned):
        launcher.stop_session(session.session_id)
    assert runtime.stopped_sessions == []


def test_stop_session_only_stops_launcher_owned_sessions() -> None:
    launcher, runtime = launcher_with_catalog(descriptor())
    launched = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    launched_session = required_session(launched)

    stopped = launcher.stop_session(launched_session.session_id)

    assert stopped.status == "stopped"
    assert stopped.ownership == "launcher_owned"
    assert runtime.stopped_sessions == [launched_session.session_id]
    assert launcher.stop_session(launched_session.session_id) == stopped


def test_session_probe_marks_exited_managed_runtime() -> None:
    class ExitingRuntimeAdapter(InMemoryRuntimeAdapter):
        def probe(self, session: AppSession) -> RuntimeSurfaceResult:
            return RuntimeSurfaceResult(
                endpoint=session.endpoint,
                details={"runtime_state": "exited", "exit_code": 7},
            )

    catalog = InMemoryAppCatalog.open((descriptor(),))
    launcher = InMemoryAppLauncher(
        catalog,
        ExitingRuntimeAdapter(),
        clock=DeterministicClock(),
        id_factory=IdFactory(),
    )
    launched = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))

    listed = launcher.list_sessions().sessions

    assert required_session(launched).status == "running"
    assert listed[0].status == "exited"
    assert listed[0].details["exit_code"] == 7


def test_list_sessions_filters_known_sessions() -> None:
    launcher, _runtime = launcher_with_catalog(
        descriptor("alpha"),
        descriptor(
            "beta",
            launch_surfaces=(surface("web", "localhost_http", "attach"),),
            recommended_surface="web",
        ),
    )
    launcher.launch_app(LaunchRequest("alpha"))
    launcher.attach_app(AttachRequest("beta"))

    assert [session.session_id for session in launcher.list_sessions().sessions] == [
        "session-1",
        "session-2",
    ]
    assert [
        session.app_id for session in launcher.list_sessions(SessionQuery(app_id="beta")).sessions
    ] == ["beta"]
    assert [
        session.app_id
        for session in launcher.list_sessions(SessionQuery(ownership="launcher_owned")).sessions
    ] == ["alpha"]


def test_missing_app_and_surface_fail_before_runtime_start() -> None:
    launcher, runtime = launcher_with_catalog(descriptor())

    with pytest.raises(AppNotFound):
        launcher.launch_app(LaunchRequest("missing"))
    with pytest.raises(LaunchSurfaceNotFound):
        launcher.launch_app(LaunchRequest("rtg_knowledge_graph", surface_id="missing"))

    assert runtime.started_surfaces == []


def test_mode_and_runtime_support_are_checked_before_runtime_start() -> None:
    launcher, runtime = launcher_with_catalog(
        descriptor(
            launch_surfaces=(surface("web", "localhost_http", "attach"),),
            recommended_surface="web",
        )
    )

    with pytest.raises(LaunchSurfaceUnsupported):
        launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))

    unsupported_runtime = InMemoryAppLauncher(
        InMemoryAppCatalog.open((descriptor(),)),
        InMemoryRuntimeAdapter(supported_kinds=("localhost_http",)),
        clock=DeterministicClock(),
        id_factory=IdFactory(),
    )
    with pytest.raises(LaunchSurfaceUnsupported):
        unsupported_runtime.launch_app(LaunchRequest("rtg_knowledge_graph"))

    assert runtime.started_surfaces == []


def test_sessions_are_copied_on_read() -> None:
    launcher, _runtime = launcher_with_catalog(descriptor())
    result = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))
    session = required_session(result)
    session.endpoint["endpoint"] = "mutated"
    listed = launcher.list_sessions().sessions[0]
    listed.endpoint["endpoint"] = "mutated-again"

    fresh = launcher.list_sessions().sessions[0]
    assert fresh.endpoint["endpoint"] == "stdio"


def test_reference_component_is_usable() -> None:
    launcher = create_reference_component()

    result = launcher.launch_app(LaunchRequest("rtg_knowledge_graph"))

    assert required_session(result).status == "running"


def test_configuration_validation() -> None:
    with pytest.raises(AppLauncherConfigurationInvalid):
        InMemoryAppLauncher(None, InMemoryRuntimeAdapter())  # type: ignore[arg-type]
    with pytest.raises(AppLauncherConfigurationInvalid):
        InMemoryAppLauncher(InMemoryAppCatalog.open(), None)  # type: ignore[arg-type]
    with pytest.raises(SessionNotFound):
        launcher, _runtime = launcher_with_catalog(descriptor())
        launcher.stop_session("missing")


def test_no_forbidden_dependency_imports() -> None:
    component_root = Path(__file__).parents[1]
    forbidden_terms = (
        "components.app.shell",
        "components.rtg",
        "subprocess",
        "requests",
        "fastmcp",
    )

    for path in component_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in forbidden_terms), path
