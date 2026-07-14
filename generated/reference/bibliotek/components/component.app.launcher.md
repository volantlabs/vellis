# component.app.launcher

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `AppLauncher`
- Lifecycle: `draft`
- Purpose: Own local launch-session lifecycle decisions for catalog-declared application surfaces.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `launchApp` | `LaunchApp` | in `launch_request: LaunchRequest`; out `result: AppLaunchResult` | `AppNotFound`, `LaunchSurfaceNotFound`, `LaunchSurfaceUnsupported`, `LaunchRejected`, `AppStartFailed` | Resolve and start only a catalog-declared launch-capable surface, returning either a managed session or a handoff receipt. |
| `attachApp` | `AttachApp` | in `attach_request: AttachRequest`; out `result: AppLaunchResult` | `AppNotFound`, `LaunchSurfaceNotFound`, `LaunchSurfaceUnsupported`, `AttachFailed` | Attach to a catalog-declared attach-capable surface and record a non-launcher-owned session. |
| `stopSession` | `StopSession` | in `session_id: String`; out `result: AppSession` | `SessionNotFound`, `SessionNotLauncherOwned`, `AppStopFailed` | Stop only a running session whose runtime lifecycle remains launcher-owned. |
| `listSessions` | `ListSessions` | in `session_query: SessionQuery[0..1]`; out `result: AppSessionList` | None | Probe eligible managed sessions and return launcher-known records in ascending session-identity order with optional exact filters. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenAppLauncher` | in `app_catalog: AppCatalog`; in `runtime_adapter: RuntimeAdapter`; out `launcher: AppLauncher` | `AppLauncherConfigurationInvalid` | Bind catalog and runtime collaborators without starting, attaching, stopping, or probing an app. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `appCatalog` | `part` | `AppCatalog` | `—` |
| `runtimeAdapter` | `part` | `RuntimeAdapter` | `—` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `sessions` | `AppSession` | `owned` | Canonical launcher-known session records and runtime ownership markers. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `launchApp` | `sessions` | `create` | Create session state only for a managed launch; handoff creates no session. |
| `attachApp` | `sessions` | `create` | Record attachment as externally owned session state. |
| `stopSession` | `sessions` | `write` | Change only one launcher-owned session to its final known status. |
| `listSessions` | `sessions` | `write` | Read, probe, and refresh eligible known sessions before deterministic filtering. |
| `launchApp` | `appCatalog` | `dependency` | Resolve the app and surface solely through catalog lookup. |
| `attachApp` | `appCatalog` | `dependency` | Resolve the app and surface solely through catalog lookup. |
| `launchApp` | `runtimeAdapter` | `dependency` | Invoke support checking and start only for the selected declared surface. |
| `attachApp` | `runtimeAdapter` | `dependency` | Invoke support checking and attachment only for the selected declared surface. |
| `stopSession` | `runtimeAdapter` | `dependency` | Stop only after launcher ownership is established. |
| `listSessions` | `runtimeAdapter` | `dependency` | Probe only launcher-owned running sessions. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.app.launcher.launch_effect` | `LaunchApp` | `launcher.launchApp` | A managed launch creates or reuses exactly one compatible launcher-owned session; a handoff returns exactly one receipt and creates no session. |
| `contract.app.launcher.attach_effect` | `AttachApp` | `launcher.attachApp` | Attachment records a running external session, never claims launcher ownership, and does not mutate catalog or app data. |
| `contract.app.launcher.stop_effect` | `StopSession` | `launcher.stopSession` | Success stops and updates only the named launcher-owned session; an already stopped owned session is returned without another runtime stop. |
| `contract.app.launcher.list_effect` | `ListSessions` | `launcher.listSessions` | Sessions are ordered by session_id and filtered by exact app_id, status, and ownership after eligible managed sessions are refreshed. |
| `contract.app.launcher.open_effect` | `OpenAppLauncher` | `openSubject` | Opening binds valid collaborators and has no application runtime side effect. |
| `invariant.app.launcher.declared_surface_only` | `AppLauncher` | `launcher` | Every start and attachment uses a launch surface returned by appCatalog; no command or endpoint is synthesized outside its descriptor. |
| `invariant.app.launcher.ownership_controls_stop` | `AppLauncher` | `launcher` | Only sessions marked launcher_owned may cause runtimeAdapter.stopSurface. |
| `invariant.app.launcher.handoff_not_session` | `AppLauncher` | `launcher` | A handoff receipt never appears in sessions and cannot be switched, stopped, or reused as a running session. |
| `invariant.app.launcher.managed_control` | `AppLauncher` | `launcher` | A launcher-owned running session has a controllable probeable runtime; an exited runtime is reported as exited. |
| `invariant.app.launcher.attach_external` | `AppLauncher` | `launcher` | Attachment does not claim runtime ownership or permit an unowned stop. |
| `contract.app.launcher.intentional_boundary` | `AppLauncher` | `launcher` | The launcher stores no catalog descriptors or app data, renders no shell, manages no undeclared command, performs no remote deployment or public exposure, and imports no shell, RTG, or app internals. |
| `contract.app.launcher.supports_runtime_surface.failures` | `SupportsRuntimeSurface` | `supportsSubject` | Capability checking has no runtime or launcher state effect. |
| `contract.app.launcher.start_runtime_surface.failures` | `StartRuntimeSurface` | `startSubject` | Failure yields no successful runtime result and is translated to AppStartFailed at the launcher boundary. |
| `contract.app.launcher.attach_runtime_surface.failures` | `AttachRuntimeSurface` | `attachSubject` | Failure yields no successful attachment result and is translated to AttachFailed at the launcher boundary. |
| `contract.app.launcher.stop_runtime_surface.failures` | `StopRuntimeSurface` | `stopSubject` | Failure does not mark the launcher session stopped and is translated to AppStopFailed. |
| `contract.app.launcher.probe_runtime_surface.failures` | `ProbeRuntimeSurface` | `probeSubject` | Probe failure is contained as diagnostic metadata and does not transfer ownership or stop a session. |
| `contract.app.launcher.launch_app.failures` | `LaunchApp` | `launcher.launchApp` | Missing or unsupported declarations, rejection, and start failure expose no partial new session. |
| `contract.app.launcher.attach_app.failures` | `AttachApp` | `launcher.attachApp` | Missing or unsupported declarations and attachment failure expose no partial new session. |
| `contract.app.launcher.stop_session.failures` | `StopSession` | `launcher.stopSession` | Missing or unowned sessions never call runtime stop; runtime stop failure does not report a successful stopped state. |
| `contract.app.launcher.list_sessions.failures` | `ListSessions` | `launcher.listSessions` | Listing contains probe failures as diagnostics and still returns deterministic launcher-known state. |
| `contract.app.launcher.open.failures` | `OpenAppLauncher` | `openSubject` | Missing collaborators create no launcher and cause no runtime side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `LaunchRequest` | `attribute` | `app_id: String`, `surface_id[0..1]: String` | Defined by its typed fields and action requirements. |
| `AttachRequest` | `attribute` | `app_id: String`, `surface_id[0..1]: String` | Defined by its typed fields and action requirements. |
| `SessionQuery` | `attribute` | `app_id[0..1]: String`, `status[0..1]: String`, `ownership[0..1]: String` | Defined by its typed fields and action requirements. |
| `RuntimeSurfaceResult` | `attribute` | `endpoint: JsonObject`, `details: JsonObject` | Defined by its typed fields and action requirements. |
| `AppSession` | `item` | `session_id: String`, `app_id: String`, `surface_id: String`, `status: String`, `ownership: String`, `endpoint: JsonObject`, `started_at[0..1]: Timestamp`, `last_checked_at[0..1]: Timestamp`, `details: JsonObject` | One launcher-known managed or externally attached runtime session. |
| `AppHandoff` | `item` | `handoff_id: String`, `app_id: String`, `surface_id: String`, `endpoint: JsonObject`, `handed_off_at[0..1]: Timestamp`, `details: JsonObject` | A successful delegation to a surface whose runtime lifecycle the launcher does not control. |
| `AppSessionList` | `attribute` | `sessions[0..*] ordered: AppSession` | Defined by its typed fields and action requirements. |
| `AppLaunchResult` | `attribute` | `app: AppDescriptor`, `session[0..1]: AppSession`, `handoff[0..1]: AppHandoff`, `reused_existing: Boolean` = `false` | Exactly one of session or handoff is present for a successful new launch or attachment. |
| `AppLauncherConfigurationInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `LaunchSurfaceNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `LaunchSurfaceUnsupported` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `LaunchRejected` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppStartFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AttachFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SessionNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `SessionNotLauncherOwned` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppStopFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `LaunchAppContractVerification` | `LaunchApp` | `launchEffect`, `launchAppFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#LaunchAppContractVerification` |
| `AttachAppContractVerification` | `AttachApp` | `attachEffect`, `attachAppFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#AttachAppContractVerification` |
| `StopSessionContractVerification` | `StopSession` | `stopEffect`, `stopSessionFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#StopSessionContractVerification` |
| `ListSessionsContractVerification` | `ListSessions` | `listEffect`, `listSessionsFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#ListSessionsContractVerification` |
| `OpenAppLauncherContractVerification` | `OpenAppLauncher` | `openEffect`, `openAppLauncherFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#OpenAppLauncherContractVerification` |
| `SupportsRuntimeSurfaceContractVerification` | `SupportsRuntimeSurface` | `supportsRuntimeSurfaceFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#SupportsRuntimeSurfaceContractVerification` |
| `StartRuntimeSurfaceContractVerification` | `StartRuntimeSurface` | `startRuntimeSurfaceFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#StartRuntimeSurfaceContractVerification` |
| `AttachRuntimeSurfaceContractVerification` | `AttachRuntimeSurface` | `attachRuntimeSurfaceFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#AttachRuntimeSurfaceContractVerification` |
| `StopRuntimeSurfaceContractVerification` | `StopRuntimeSurface` | `stopRuntimeSurfaceFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#StopRuntimeSurfaceContractVerification` |
| `ProbeRuntimeSurfaceContractVerification` | `ProbeRuntimeSurface` | `probeRuntimeSurfaceFailureSemantics` | `components/app/launcher/tests/test_app_launcher_contract.py#ProbeRuntimeSurfaceContractVerification` |
| `AppLauncherBoundaryVerification` | `AppLauncher` | `declaredSurfaceOnly`, `ownershipControlsStop`, `handoffNotSession`, `managedControl`, `attachExternal`, `intentionalBoundary` | `components/app/launcher/tests/test_app_launcher_contract.py#AppLauncherBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
