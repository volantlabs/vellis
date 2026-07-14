library package BibliotekAppShell {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppCatalog::*;
    private import BibliotekAppLauncher::*;
    private import ScalarValues::*;

    doc /* Presentation-neutral shell state and commands composed over catalog and launcher contracts. */

    attribute def ShellOptions { attribute restored_active_session_id[0..1] : String; }
    attribute def ShellQuery { attribute status[0..1] : String; attribute tags[0..*] ordered : String; }
    attribute def AppOpenRequest { attribute app_id : String; attribute surface_id[0..1] : String; attribute mode : String default = "launch"; }
    attribute def CloseRequest { attribute session_id[0..1] : String; attribute stop_runtime : Boolean default = false; }
    attribute def ShellActiveApp { item app : AppDescriptor; item session : AppSession; }
    attribute def AppShellView {
        item apps[0..*] ordered : AppDescriptor;
        item sessions[0..*] ordered : AppSession;
        item recent_launches[0..*] ordered : AppHandoff;
        attribute active_app[0..1] : ShellActiveApp;
        attribute available_commands[0..*] ordered : String;
        attribute messages[0..*] ordered : String;
        doc /* Renderer-neutral home state assembled solely from public catalog, launcher, and shell state. */
    }
    attribute def AppShellCommandResult {
        attribute 'view' : AppShellView;
        item app[0..1] : AppDescriptor;
        item session[0..1] : AppSession;
        item handoff[0..1] : AppHandoff;
        attribute 'message' : String default = "";
    }
    attribute def ShellSurfaceSelection { attribute app_id : String; attribute surface_id : String; }
    item def AppShellState {
        attribute active_session_id[0..1] : String;
        attribute selected_surfaces[0..*] : ShellSurfaceSelection;
        attribute recent_app_ids[0..*] ordered : String;
        item recent_handoffs[0..10] ordered : AppHandoff;
        doc /* In-memory shell-owned navigation and bounded handoff history, never application domain data. */
    }

    attribute def AppShellConfigurationInvalid { attribute 'message' : String; }
    attribute def AppShellReadFailed { attribute 'message' : String; }
    attribute def AppCloseRejected { attribute 'message' : String; }

    action def GetHome {
        in shell_query[0..1] : ShellQuery;
        out result : AppShellView;
        doc /* Assemble catalog apps, launcher sessions, handoff history, commands, and the valid active app without rendering a UI. */
        @FailureContract { errorIds = ("AppShellReadFailed"); }
    }
    action def OpenApp {
        in open_request : AppOpenRequest;
        out result : AppShellCommandResult;
        doc /* Delegate launch or attach to the launcher, then update shell state only after one session or handoff succeeds. */
        @FailureContract { errorIds = ("AppNotFound", "LaunchSurfaceNotFound", "LaunchSurfaceUnsupported", "LaunchRejected", "AppStartFailed", "AttachFailed", "AppCloseRejected"); }
    }
    action def SwitchApp {
        in session_id : String;
        out result : AppShellCommandResult;
        doc /* Select an existing launcher-known session as active without launching, attaching, stopping, or probing directly. */
        @FailureContract { errorIds = ("SessionNotFound", "AppNotFound"); }
    }
    action def CloseApp {
        in close_request : CloseRequest;
        out result : AppShellCommandResult;
        doc /* Clear active shell state and request launcher stop only when explicitly asked for the target session. */
        @FailureContract { errorIds = ("SessionNotFound", "AppCloseRejected", "AppStopFailed"); }
    }

    part def <'component.app.shell'> AppShell {
        doc /* Own renderer-neutral shell session state and route user commands through public catalog and launcher contracts. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }
        ref part appCatalog : AppCatalog { doc /* Public descriptor listing and lookup only. */ }
        ref part appLauncher : AppLauncher { doc /* Public launch, attach, stop, and session-list operations only. */ }
        item shellState : AppShellState { doc /* Canonical shell-owned active selection, surface preference, recency, and handoff history. */ }

        perform action getHome[0..*] : GetHome;
        perform action openApp[0..*] : OpenApp;
        perform action switchApp[0..*] : SwitchApp;
        perform action closeApp[0..*] : CloseApp;

        dependency homeState from getHome to shellState { @StateAccess { kind = StateAccessKind::write; } doc /* Read shell state and clear a stale active session while assembling the view. */ }
        dependency openState from openApp to shellState { @StateAccess { kind = StateAccessKind::write; } doc /* Update active session or bounded handoff history only after launcher success. */ }
        dependency switchState from switchApp to shellState { @StateAccess { kind = StateAccessKind::write; } doc /* Replace active session identity and update app recency only after public lookup succeeds. */ }
        dependency closeState from closeApp to shellState { @StateAccess { kind = StateAccessKind::write; } doc /* Clear only matching active shell state after validating the target and any requested stop. */ }
        dependency homeCatalog from getHome to appCatalog { doc /* List descriptors through the catalog contract. */ }
        dependency homeLauncher from getHome to appLauncher { doc /* List sessions through the launcher contract. */ }
        dependency openLauncher from openApp to appLauncher { doc /* Delegate launch or attachment; never use runtime-adapter internals. */ }
        dependency switchCatalog from switchApp to appCatalog { doc /* Resolve the selected session's app through public lookup. */ }
        dependency switchLauncher from switchApp to appLauncher { doc /* Resolve only an existing launcher-known session. */ }
        dependency closeCatalog from closeApp to appCatalog { doc /* Resolve app presentation data through public lookup. */ }
        dependency closeLauncher from closeApp to appLauncher { doc /* List the target and optionally invoke the public stop operation. */ }
    }

    action def OpenAppShell {
        in app_catalog : AppCatalog;
        in app_launcher : AppLauncher;
        in shell_options[0..1] : ShellOptions;
        out part shell : AppShell;
        doc /* Bind catalog and launcher collaborators and optionally restore an active session identity without launching or attaching. */
        @FailureContract { errorIds = ("AppShellConfigurationInvalid"); }
    }

    requirement <'contract.app.shell.home_effect'> homeEffect { subject operation : GetHome; require constraint { doc /* The view contains filtered catalog descriptors, launcher-known sessions, bounded handoff history, current valid active app, stable commands, and messages with no renderer-specific objects. */ } }
    requirement <'contract.app.shell.open_effect'> openEffect { subject operation : OpenApp; require constraint { doc /* A successful session becomes active; a successful handoff becomes history only; shell state changes only after launcher success. */ } }
    requirement <'contract.app.shell.switch_effect'> switchEffect { subject operation : SwitchApp; require constraint { doc /* Success selects exactly one existing launcher-known session and catalog app without starting, attaching, or stopping runtime. */ } }
    requirement <'contract.app.shell.close_effect'> closeEffect { subject operation : CloseApp; require constraint { doc /* Closing clears matching active shell state and stops runtime only when explicitly requested through the launcher. */ } }
    requirement <'contract.app.shell.open_shell_effect'> openShellEffect { subject operation : OpenAppShell; require constraint { doc /* Opening has no runtime side effect and restores only the supplied active-session identity when present. */ } }

    requirement <'invariant.app.shell.active_public_state'> activePublicState { subject shell : AppShell; require constraint { doc /* Active app state refers to an app known through the catalog and a running session known through the launcher. */ } }
    requirement <'invariant.app.shell.handoff_history_only'> handoffHistoryOnly { subject shell : AppShell; require constraint { doc /* Recent handoffs grant no active-session, switch, or stop authority and are bounded to ten canonical receipts. */ } }
    requirement <'invariant.app.shell.runtime_delegated'> runtimeDelegated { subject shell : AppShell; require constraint { doc /* All launch, attach, stop, and probe effects occur through AppLauncher; the shell consumes no runtime-adapter internals. */ } }
    requirement <'invariant.app.shell.no_app_data'> noAppData { subject shell : AppShell; require constraint { doc /* Shell state contains no application-owned domain content, graph data, catalog storage, or runtime handles. */ } }
    requirement <'invariant.app.shell.renderer_neutral'> rendererNeutral { subject shell : AppShell; require constraint { doc /* Shell values contain only language-neutral records and no HTML, terminal, desktop, mobile, transport, or framework objects. */ } }
    requirement <'contract.app.shell.intentional_boundary'> intentionalBoundary { subject shell : AppShell; require constraint { doc /* The shell does not store descriptors, own runtime sessions, inspect app internals, render a UI, authorize users, deploy remotely, or import RTG and transport internals. */ } }

    requirement <'contract.app.shell.get_home.failures'> getHomeFailureSemantics { subject operation : GetHome; require constraint { doc /* Read failure exposes no partially updated shell state or renderer-specific fallback. */ } }
    requirement <'contract.app.shell.open_app.failures'> openAppFailureSemantics { subject operation : OpenApp; require constraint { doc /* Catalog, surface, start, attach, and invalid-mode failures preserve the owning error meaning and leave shell state unchanged. */ } }
    requirement <'contract.app.shell.switch_app.failures'> switchAppFailureSemantics { subject operation : SwitchApp; require constraint { doc /* Missing session or app leaves active and recent state unchanged. */ } }
    requirement <'contract.app.shell.close_app.failures'> closeAppFailureSemantics { subject operation : CloseApp; require constraint { doc /* Missing targets and rejected or failed stops do not clear active state or claim runtime closure. */ } }
    requirement <'contract.app.shell.open.failures'> openAppShellFailureSemantics { subject operation : OpenAppShell; require constraint { doc /* Missing collaborators create no shell and cause no runtime side effect. */ } }

    part contractContext {
        part shell : AppShell;
        satisfy homeEffect by shell.getHome; satisfy openEffect by shell.openApp; satisfy switchEffect by shell.switchApp; satisfy closeEffect by shell.closeApp;
        satisfy activePublicState by shell; satisfy handoffHistoryOnly by shell; satisfy runtimeDelegated by shell; satisfy noAppData by shell; satisfy rendererNeutral by shell; satisfy intentionalBoundary by shell;
        satisfy getHomeFailureSemantics by shell.getHome; satisfy openAppFailureSemantics by shell.openApp; satisfy switchAppFailureSemantics by shell.switchApp; satisfy closeAppFailureSemantics by shell.closeApp;
        action openShellSubject : OpenAppShell; satisfy openShellEffect by openShellSubject; satisfy openAppShellFailureSemantics by openShellSubject;
    }

    verification def GetHomeContractVerification { subject operation : GetHome; objective { verify homeEffect; verify getHomeFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/shell/tests/test_app_shell_contract.py#GetHomeContractVerification"; implementationScope = "InMemoryAppShell"; } }
    verification def OpenAppContractVerification { subject operation : OpenApp; objective { verify openEffect; verify openAppFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/shell/tests/test_app_shell_contract.py#OpenAppContractVerification"; implementationScope = "InMemoryAppShell"; } }
    verification def SwitchAppContractVerification { subject operation : SwitchApp; objective { verify switchEffect; verify switchAppFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/shell/tests/test_app_shell_contract.py#SwitchAppContractVerification"; implementationScope = "InMemoryAppShell"; } }
    verification def CloseAppContractVerification { subject operation : CloseApp; objective { verify closeEffect; verify closeAppFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/shell/tests/test_app_shell_contract.py#CloseAppContractVerification"; implementationScope = "InMemoryAppShell"; } }
    verification def OpenAppShellContractVerification { subject operation : OpenAppShell; objective { verify openShellEffect; verify openAppShellFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/shell/tests/test_app_shell_contract.py#OpenAppShellContractVerification"; implementationScope = "InMemoryAppShell"; } }
    verification def AppShellBoundaryVerification {
        subject shell : AppShell;
        objective { verify activePublicState; verify handoffHistoryOnly; verify runtimeDelegated; verify noAppData; verify rendererNeutral; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/app/shell/tests/test_app_shell_contract.py#AppShellBoundaryVerification"; implementationScope = "InMemoryAppShell"; }
    }
}
