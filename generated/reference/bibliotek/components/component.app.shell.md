# component.app.shell

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `AppShell`
- Lifecycle: `draft`
- Purpose: Own renderer-neutral shell session state and route user commands through public catalog and launcher contracts.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `getHome` | `GetHome` | in `shell_query: ShellQuery[0..1]`; out `result: AppShellView` | `AppShellReadFailed` | Assemble catalog apps, launcher sessions, handoff history, commands, and the valid active app without rendering a UI. |
| `openApp` | `OpenApp` | in `open_request: AppOpenRequest`; out `result: AppShellCommandResult` | `AppNotFound`, `LaunchSurfaceNotFound`, `LaunchSurfaceUnsupported`, `LaunchRejected`, `AppStartFailed`, `AttachFailed`, `AppCloseRejected` | Delegate launch or attach to the launcher, then update shell state only after one session or handoff succeeds. |
| `switchApp` | `SwitchApp` | in `session_id: String`; out `result: AppShellCommandResult` | `SessionNotFound`, `AppNotFound` | Select an existing launcher-known session as active without launching, attaching, stopping, or probing directly. |
| `closeApp` | `CloseApp` | in `close_request: CloseRequest`; out `result: AppShellCommandResult` | `SessionNotFound`, `AppCloseRejected`, `AppStopFailed` | Clear active shell state and request launcher stop only when explicitly asked for the target session. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenAppShell` | in `app_catalog: AppCatalog`; in `app_launcher: AppLauncher`; in `shell_options: ShellOptions[0..1]`; out `shell: AppShell` | `AppShellConfigurationInvalid` | Bind catalog and launcher collaborators and optionally restore an active session identity without launching or attaching. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `appCatalog` | `part` | `AppCatalog` | `—` |
| `appLauncher` | `part` | `AppLauncher` | `—` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `shellState` | `AppShellState` | `owned` | Canonical shell-owned active selection, surface preference, recency, and handoff history. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `getHome` | `shellState` | `write` | Read shell state and clear a stale active session while assembling the view. |
| `openApp` | `shellState` | `write` | Update active session or bounded handoff history only after launcher success. |
| `switchApp` | `shellState` | `write` | Replace active session identity and update app recency only after public lookup succeeds. |
| `closeApp` | `shellState` | `write` | Clear only matching active shell state after validating the target and any requested stop. |
| `getHome` | `appCatalog` | `dependency` | List descriptors through the catalog contract. |
| `getHome` | `appLauncher` | `dependency` | List sessions through the launcher contract. |
| `openApp` | `appLauncher` | `dependency` | Delegate launch or attachment; never use runtime-adapter internals. |
| `switchApp` | `appCatalog` | `dependency` | Resolve the selected session's app through public lookup. |
| `switchApp` | `appLauncher` | `dependency` | Resolve only an existing launcher-known session. |
| `closeApp` | `appCatalog` | `dependency` | Resolve app presentation data through public lookup. |
| `closeApp` | `appLauncher` | `dependency` | List the target and optionally invoke the public stop operation. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.app.shell.home_effect` | `GetHome` | `shell.getHome` | The view contains filtered catalog descriptors, launcher-known sessions, bounded handoff history, current valid active app, stable commands, and messages with no renderer-specific objects. |
| `contract.app.shell.open_effect` | `OpenApp` | `shell.openApp` | A successful session becomes active; a successful handoff becomes history only; shell state changes only after launcher success. |
| `contract.app.shell.switch_effect` | `SwitchApp` | `shell.switchApp` | Success selects exactly one existing launcher-known session and catalog app without starting, attaching, or stopping runtime. |
| `contract.app.shell.close_effect` | `CloseApp` | `shell.closeApp` | Closing clears matching active shell state and stops runtime only when explicitly requested through the launcher. |
| `contract.app.shell.open_shell_effect` | `OpenAppShell` | `openShellSubject` | Opening has no runtime side effect and restores only the supplied active-session identity when present. |
| `invariant.app.shell.active_public_state` | `AppShell` | `shell` | Active app state refers to an app known through the catalog and a running session known through the launcher. |
| `invariant.app.shell.handoff_history_only` | `AppShell` | `shell` | Recent handoffs grant no active-session, switch, or stop authority and are bounded to ten canonical receipts. |
| `invariant.app.shell.runtime_delegated` | `AppShell` | `shell` | All launch, attach, stop, and probe effects occur through AppLauncher; the shell consumes no runtime-adapter internals. |
| `invariant.app.shell.no_app_data` | `AppShell` | `shell` | Shell state contains no application-owned domain content, graph data, catalog storage, or runtime handles. |
| `invariant.app.shell.renderer_neutral` | `AppShell` | `shell` | Shell values contain only language-neutral records and no HTML, terminal, desktop, mobile, transport, or framework objects. |
| `contract.app.shell.intentional_boundary` | `AppShell` | `shell` | The shell does not store descriptors, own runtime sessions, inspect app internals, render a UI, authorize users, deploy remotely, or import RTG and transport internals. |
| `contract.app.shell.get_home.failures` | `GetHome` | `shell.getHome` | Read failure exposes no partially updated shell state or renderer-specific fallback. |
| `contract.app.shell.open_app.failures` | `OpenApp` | `shell.openApp` | Catalog, surface, start, attach, and invalid-mode failures preserve the owning error meaning and leave shell state unchanged. |
| `contract.app.shell.switch_app.failures` | `SwitchApp` | `shell.switchApp` | Missing session or app leaves active and recent state unchanged. |
| `contract.app.shell.close_app.failures` | `CloseApp` | `shell.closeApp` | Missing targets and rejected or failed stops do not clear active state or claim runtime closure. |
| `contract.app.shell.open.failures` | `OpenAppShell` | `openShellSubject` | Missing collaborators create no shell and cause no runtime side effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `ShellOptions` | `attribute` | `restored_active_session_id[0..1]: String` | Defined by its typed fields and action requirements. |
| `ShellQuery` | `attribute` | `status[0..1]: String`, `tags[0..*] ordered: String` | Defined by its typed fields and action requirements. |
| `AppOpenRequest` | `attribute` | `app_id: String`, `surface_id[0..1]: String`, `mode: String` = `"launch"` | Defined by its typed fields and action requirements. |
| `CloseRequest` | `attribute` | `session_id[0..1]: String`, `stop_runtime: Boolean` = `false` | Defined by its typed fields and action requirements. |
| `ShellActiveApp` | `attribute` | `app: AppDescriptor`, `session: AppSession` | Defined by its typed fields and action requirements. |
| `AppShellView` | `attribute` | `apps[0..*] ordered: AppDescriptor`, `sessions[0..*] ordered: AppSession`, `recent_launches[0..*] ordered: AppHandoff`, `active_app[0..1]: ShellActiveApp`, `available_commands[0..*] ordered: String`, `messages[0..*] ordered: String` | Renderer-neutral home state assembled solely from public catalog, launcher, and shell state. |
| `AppShellCommandResult` | `attribute` | `view: AppShellView`, `app[0..1]: AppDescriptor`, `session[0..1]: AppSession`, `handoff[0..1]: AppHandoff`, `message: String` = `""` | Defined by its typed fields and action requirements. |
| `ShellSurfaceSelection` | `attribute` | `app_id: String`, `surface_id: String` | Defined by its typed fields and action requirements. |
| `AppShellState` | `item` | `active_session_id[0..1]: String`, `selected_surfaces[0..*]: ShellSurfaceSelection`, `recent_app_ids[0..*] ordered: String`, `recent_handoffs[0..10] ordered: AppHandoff` | In-memory shell-owned navigation and bounded handoff history, never application domain data. |
| `AppShellConfigurationInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppShellReadFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppCloseRejected` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `GetHomeContractVerification` | `GetHome` | `homeEffect`, `getHomeFailureSemantics` | `components/app/shell/tests/test_app_shell_contract.py#GetHomeContractVerification` |
| `OpenAppContractVerification` | `OpenApp` | `openEffect`, `openAppFailureSemantics` | `components/app/shell/tests/test_app_shell_contract.py#OpenAppContractVerification` |
| `SwitchAppContractVerification` | `SwitchApp` | `switchEffect`, `switchAppFailureSemantics` | `components/app/shell/tests/test_app_shell_contract.py#SwitchAppContractVerification` |
| `CloseAppContractVerification` | `CloseApp` | `closeEffect`, `closeAppFailureSemantics` | `components/app/shell/tests/test_app_shell_contract.py#CloseAppContractVerification` |
| `OpenAppShellContractVerification` | `OpenAppShell` | `openShellEffect`, `openAppShellFailureSemantics` | `components/app/shell/tests/test_app_shell_contract.py#OpenAppShellContractVerification` |
| `AppShellBoundaryVerification` | `AppShell` | `activePublicState`, `handoffHistoryOnly`, `runtimeDelegated`, `noAppData`, `rendererNeutral`, `intentionalBoundary` | `components/app/shell/tests/test_app_shell_contract.py#AppShellBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
