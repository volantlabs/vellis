library package BibliotekAppLauncher {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekAppCatalog::*;
    private import ScalarValues::*;

    doc /* Local lifecycle control for catalog-declared application surfaces. */

    attribute def LaunchRequest {
        attribute app_id : String;
        attribute surface_id[0..1] : String;
    }
    attribute def AttachRequest {
        attribute app_id : String;
        attribute surface_id[0..1] : String;
    }
    attribute def SessionQuery {
        attribute app_id[0..1] : String;
        attribute status[0..1] : String;
        attribute ownership[0..1] : String;
    }
    attribute def RuntimeSurfaceResult {
        attribute endpoint : JsonObject;
        attribute details : JsonObject;
    }
    item def AppSession {
        attribute session_id : String;
        attribute app_id : String;
        attribute surface_id : String;
        attribute status : String;
        attribute ownership : String;
        attribute endpoint : JsonObject;
        attribute started_at[0..1] : Timestamp;
        attribute last_checked_at[0..1] : Timestamp;
        attribute details : JsonObject;
        doc /* One launcher-known managed or externally attached runtime session. */
    }
    item def AppHandoff {
        attribute handoff_id : String;
        attribute app_id : String;
        attribute surface_id : String;
        attribute endpoint : JsonObject;
        attribute handed_off_at[0..1] : Timestamp;
        attribute details : JsonObject;
        doc /* A successful delegation to a surface whose runtime lifecycle the launcher does not control. */
    }
    attribute def AppSessionList { item sessions[0..*] ordered : AppSession; }
    attribute def AppLaunchResult {
        item app : AppDescriptor;
        item session[0..1] : AppSession;
        item handoff[0..1] : AppHandoff;
        attribute reused_existing : Boolean default = false;
        doc /* Exactly one of session or handoff is present for a successful new launch or attachment. */
    }

    attribute def AppLauncherConfigurationInvalid { attribute 'message' : String; }
    attribute def LaunchSurfaceNotFound { attribute 'message' : String; }
    attribute def LaunchSurfaceUnsupported { attribute 'message' : String; }
    attribute def LaunchRejected { attribute 'message' : String; }
    attribute def AppStartFailed { attribute 'message' : String; }
    attribute def AttachFailed { attribute 'message' : String; }
    attribute def SessionNotFound { attribute 'message' : String; }
    attribute def SessionNotLauncherOwned { attribute 'message' : String; }
    attribute def AppStopFailed { attribute 'message' : String; }

    action def SupportsRuntimeSurface {
        in launch_surface : LaunchSurface;
        in operation : String;
        out result : Boolean;
        doc /* Report whether the local runtime adapter supports the declared surface and requested launch or attach operation. */
        @FailureContract { errorIds = (); }
    }
    action def StartRuntimeSurface {
        in launch_surface : LaunchSurface;
        out result : RuntimeSurfaceResult;
        doc /* Start exactly one catalog-declared local surface and return shell-visible endpoint and diagnostic metadata. */
        @FailureContract { errorIds = ("AppStartFailed"); }
    }
    action def AttachRuntimeSurface {
        in launch_surface : LaunchSurface;
        out result : RuntimeSurfaceResult;
        doc /* Attach to exactly one catalog-declared local surface without claiming runtime ownership. */
        @FailureContract { errorIds = ("AttachFailed"); }
    }
    action def StopRuntimeSurface {
        in session : AppSession;
        out result : RuntimeSurfaceResult;
        doc /* Stop the runtime underlying one launcher-owned session. */
        @FailureContract { errorIds = ("AppStopFailed"); }
    }
    action def ProbeRuntimeSurface {
        in session : AppSession;
        out result : RuntimeSurfaceResult;
        doc /* Report current surface-level availability for one launcher-known session. */
        @FailureContract { errorIds = (); }
    }

    part def RuntimeAdapter {
        doc /* Required local runtime capability; concrete process or transport mechanics remain realization choices. */
        perform action supportsSurface[0..*] : SupportsRuntimeSurface;
        perform action startSurface[0..*] : StartRuntimeSurface;
        perform action attachSurface[0..*] : AttachRuntimeSurface;
        perform action stopSurface[0..*] : StopRuntimeSurface;
        perform action probeSurface[0..*] : ProbeRuntimeSurface;
    }

    action def LaunchApp {
        in launch_request : LaunchRequest;
        out result : AppLaunchResult;
        doc /* Resolve and start only a catalog-declared launch-capable surface, returning either a managed session or a handoff receipt. */
        @FailureContract { errorIds = ("AppNotFound", "LaunchSurfaceNotFound", "LaunchSurfaceUnsupported", "LaunchRejected", "AppStartFailed"); }
    }
    action def AttachApp {
        in attach_request : AttachRequest;
        out result : AppLaunchResult;
        doc /* Attach to a catalog-declared attach-capable surface and record a non-launcher-owned session. */
        @FailureContract { errorIds = ("AppNotFound", "LaunchSurfaceNotFound", "LaunchSurfaceUnsupported", "AttachFailed"); }
    }
    action def StopSession {
        in session_id : String;
        out result : AppSession;
        doc /* Stop only a running session whose runtime lifecycle remains launcher-owned. */
        @FailureContract { errorIds = ("SessionNotFound", "SessionNotLauncherOwned", "AppStopFailed"); }
    }
    action def ListSessions {
        in session_query[0..1] : SessionQuery;
        out result : AppSessionList;
        doc /* Probe eligible managed sessions and return launcher-known records in ascending session-identity order with optional exact filters. */
        @FailureContract { errorIds = (); }
    }

    part def <'component.app.launcher'> AppLauncher {
        doc /* Own local launch-session lifecycle decisions for catalog-declared application surfaces. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        ref part appCatalog : AppCatalog { doc /* Descriptor lookup and launch-surface metadata through the catalog public contract. */ }
        ref part runtimeAdapter : RuntimeAdapter { doc /* Local start, attach, stop, and probe capability. */ }
        item sessions[0..*] : AppSession { doc /* Canonical launcher-known session records and runtime ownership markers. */ }

        perform action launchApp[0..*] : LaunchApp;
        perform action attachApp[0..*] : AttachApp;
        perform action stopSession[0..*] : StopSession;
        perform action listSessions[0..*] : ListSessions;

        dependency launchSessionState from launchApp to sessions { @StateAccess { kind = StateAccessKind::create; } doc /* Create session state only for a managed launch; handoff creates no session. */ }
        dependency attachSessionState from attachApp to sessions { @StateAccess { kind = StateAccessKind::create; } doc /* Record attachment as externally owned session state. */ }
        dependency stopSessionState from stopSession to sessions { @StateAccess { kind = StateAccessKind::write; } doc /* Change only one launcher-owned session to its final known status. */ }
        dependency listSessionState from listSessions to sessions { @StateAccess { kind = StateAccessKind::write; } doc /* Read, probe, and refresh eligible known sessions before deterministic filtering. */ }
        dependency launchCatalogLookup from launchApp to appCatalog { doc /* Resolve the app and surface solely through catalog lookup. */ }
        dependency attachCatalogLookup from attachApp to appCatalog { doc /* Resolve the app and surface solely through catalog lookup. */ }
        dependency launchRuntime from launchApp to runtimeAdapter { doc /* Invoke support checking and start only for the selected declared surface. */ }
        dependency attachRuntime from attachApp to runtimeAdapter { doc /* Invoke support checking and attachment only for the selected declared surface. */ }
        dependency stopRuntime from stopSession to runtimeAdapter { doc /* Stop only after launcher ownership is established. */ }
        dependency probeRuntime from listSessions to runtimeAdapter { doc /* Probe only launcher-owned running sessions. */ }
    }

    action def OpenAppLauncher {
        in app_catalog : AppCatalog;
        in runtime_adapter : RuntimeAdapter;
        out part launcher : AppLauncher;
        doc /* Bind catalog and runtime collaborators without starting, attaching, stopping, or probing an app. */
        @FailureContract { errorIds = ("AppLauncherConfigurationInvalid"); }
    }

    requirement <'contract.app.launcher.launch_effect'> launchEffect { subject operation : LaunchApp; require constraint { doc /* A managed launch creates or reuses exactly one compatible launcher-owned session; a handoff returns exactly one receipt and creates no session. */ } }
    requirement <'contract.app.launcher.attach_effect'> attachEffect { subject operation : AttachApp; require constraint { doc /* Attachment records a running external session, never claims launcher ownership, and does not mutate catalog or app data. */ } }
    requirement <'contract.app.launcher.stop_effect'> stopEffect { subject operation : StopSession; require constraint { doc /* Success stops and updates only the named launcher-owned session; an already stopped owned session is returned without another runtime stop. */ } }
    requirement <'contract.app.launcher.list_effect'> listEffect { subject operation : ListSessions; require constraint { doc /* Sessions are ordered by session_id and filtered by exact app_id, status, and ownership after eligible managed sessions are refreshed. */ } }
    requirement <'contract.app.launcher.open_effect'> openEffect { subject operation : OpenAppLauncher; require constraint { doc /* Opening binds valid collaborators and has no application runtime side effect. */ } }

    requirement <'invariant.app.launcher.declared_surface_only'> declaredSurfaceOnly { subject launcher : AppLauncher; require constraint { doc /* Every start and attachment uses a launch surface returned by appCatalog; no command or endpoint is synthesized outside its descriptor. */ } }
    requirement <'invariant.app.launcher.ownership_controls_stop'> ownershipControlsStop { subject launcher : AppLauncher; require constraint { doc /* Only sessions marked launcher_owned may cause runtimeAdapter.stopSurface. */ } }
    requirement <'invariant.app.launcher.handoff_not_session'> handoffNotSession { subject launcher : AppLauncher; require constraint { doc /* A handoff receipt never appears in sessions and cannot be switched, stopped, or reused as a running session. */ } }
    requirement <'invariant.app.launcher.managed_control'> managedControl { subject launcher : AppLauncher; require constraint { doc /* A launcher-owned running session has a controllable probeable runtime; an exited runtime is reported as exited. */ } }
    requirement <'invariant.app.launcher.attach_external'> attachExternal { subject launcher : AppLauncher; require constraint { doc /* Attachment does not claim runtime ownership or permit an unowned stop. */ } }
    requirement <'contract.app.launcher.intentional_boundary'> intentionalBoundary { subject launcher : AppLauncher; require constraint { doc /* The launcher stores no catalog descriptors or app data, renders no shell, manages no undeclared command, performs no remote deployment or public exposure, and imports no shell, RTG, or app internals. */ } }

    requirement <'contract.app.launcher.supports_runtime_surface.failures'> supportsRuntimeSurfaceFailureSemantics { subject operation : SupportsRuntimeSurface; require constraint { doc /* Capability checking has no runtime or launcher state effect. */ } }
    requirement <'contract.app.launcher.start_runtime_surface.failures'> startRuntimeSurfaceFailureSemantics { subject operation : StartRuntimeSurface; require constraint { doc /* Failure yields no successful runtime result and is translated to AppStartFailed at the launcher boundary. */ } }
    requirement <'contract.app.launcher.attach_runtime_surface.failures'> attachRuntimeSurfaceFailureSemantics { subject operation : AttachRuntimeSurface; require constraint { doc /* Failure yields no successful attachment result and is translated to AttachFailed at the launcher boundary. */ } }
    requirement <'contract.app.launcher.stop_runtime_surface.failures'> stopRuntimeSurfaceFailureSemantics { subject operation : StopRuntimeSurface; require constraint { doc /* Failure does not mark the launcher session stopped and is translated to AppStopFailed. */ } }
    requirement <'contract.app.launcher.probe_runtime_surface.failures'> probeRuntimeSurfaceFailureSemantics { subject operation : ProbeRuntimeSurface; require constraint { doc /* Probe failure is contained as diagnostic metadata and does not transfer ownership or stop a session. */ } }
    requirement <'contract.app.launcher.launch_app.failures'> launchAppFailureSemantics { subject operation : LaunchApp; require constraint { doc /* Missing or unsupported declarations, rejection, and start failure expose no partial new session. */ } }
    requirement <'contract.app.launcher.attach_app.failures'> attachAppFailureSemantics { subject operation : AttachApp; require constraint { doc /* Missing or unsupported declarations and attachment failure expose no partial new session. */ } }
    requirement <'contract.app.launcher.stop_session.failures'> stopSessionFailureSemantics { subject operation : StopSession; require constraint { doc /* Missing or unowned sessions never call runtime stop; runtime stop failure does not report a successful stopped state. */ } }
    requirement <'contract.app.launcher.list_sessions.failures'> listSessionsFailureSemantics { subject operation : ListSessions; require constraint { doc /* Listing contains probe failures as diagnostics and still returns deterministic launcher-known state. */ } }
    requirement <'contract.app.launcher.open.failures'> openAppLauncherFailureSemantics { subject operation : OpenAppLauncher; require constraint { doc /* Missing collaborators create no launcher and cause no runtime side effect. */ } }

    part contractContext {
        part launcher : AppLauncher;
        satisfy launchEffect by launcher.launchApp;
        satisfy attachEffect by launcher.attachApp;
        satisfy stopEffect by launcher.stopSession;
        satisfy listEffect by launcher.listSessions;
        satisfy declaredSurfaceOnly by launcher;
        satisfy ownershipControlsStop by launcher;
        satisfy handoffNotSession by launcher;
        satisfy managedControl by launcher;
        satisfy attachExternal by launcher;
        satisfy intentionalBoundary by launcher;
        satisfy launchAppFailureSemantics by launcher.launchApp;
        satisfy attachAppFailureSemantics by launcher.attachApp;
        satisfy stopSessionFailureSemantics by launcher.stopSession;
        satisfy listSessionsFailureSemantics by launcher.listSessions;
        action openSubject : OpenAppLauncher;
        satisfy openEffect by openSubject;
        satisfy openAppLauncherFailureSemantics by openSubject;
        action supportsSubject : SupportsRuntimeSurface;
        action startSubject : StartRuntimeSurface;
        action attachSubject : AttachRuntimeSurface;
        action stopSubject : StopRuntimeSurface;
        action probeSubject : ProbeRuntimeSurface;
        satisfy supportsRuntimeSurfaceFailureSemantics by supportsSubject;
        satisfy startRuntimeSurfaceFailureSemantics by startSubject;
        satisfy attachRuntimeSurfaceFailureSemantics by attachSubject;
        satisfy stopRuntimeSurfaceFailureSemantics by stopSubject;
        satisfy probeRuntimeSurfaceFailureSemantics by probeSubject;
    }

    verification def LaunchAppContractVerification { subject operation : LaunchApp; objective { verify launchEffect; verify launchAppFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#LaunchAppContractVerification"; implementationScope = "InMemoryAppLauncher"; } }
    verification def AttachAppContractVerification { subject operation : AttachApp; objective { verify attachEffect; verify attachAppFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#AttachAppContractVerification"; implementationScope = "InMemoryAppLauncher"; } }
    verification def StopSessionContractVerification { subject operation : StopSession; objective { verify stopEffect; verify stopSessionFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#StopSessionContractVerification"; implementationScope = "InMemoryAppLauncher"; } }
    verification def ListSessionsContractVerification { subject operation : ListSessions; objective { verify listEffect; verify listSessionsFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#ListSessionsContractVerification"; implementationScope = "InMemoryAppLauncher"; } }
    verification def OpenAppLauncherContractVerification { subject operation : OpenAppLauncher; objective { verify openEffect; verify openAppLauncherFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#OpenAppLauncherContractVerification"; implementationScope = "InMemoryAppLauncher"; } }
    verification def SupportsRuntimeSurfaceContractVerification { subject operation : SupportsRuntimeSurface; objective { verify supportsRuntimeSurfaceFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#SupportsRuntimeSurfaceContractVerification"; implementationScope = "InMemoryRuntimeAdapter"; } }
    verification def StartRuntimeSurfaceContractVerification { subject operation : StartRuntimeSurface; objective { verify startRuntimeSurfaceFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#StartRuntimeSurfaceContractVerification"; implementationScope = "InMemoryRuntimeAdapter"; } }
    verification def AttachRuntimeSurfaceContractVerification { subject operation : AttachRuntimeSurface; objective { verify attachRuntimeSurfaceFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#AttachRuntimeSurfaceContractVerification"; implementationScope = "InMemoryRuntimeAdapter"; } }
    verification def StopRuntimeSurfaceContractVerification { subject operation : StopRuntimeSurface; objective { verify stopRuntimeSurfaceFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#StopRuntimeSurfaceContractVerification"; implementationScope = "InMemoryRuntimeAdapter"; } }
    verification def ProbeRuntimeSurfaceContractVerification { subject operation : ProbeRuntimeSurface; objective { verify probeRuntimeSurfaceFailureSemantics; } @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#ProbeRuntimeSurfaceContractVerification"; implementationScope = "InMemoryRuntimeAdapter"; } }
    verification def AppLauncherBoundaryVerification {
        subject launcher : AppLauncher;
        objective { verify declaredSurfaceOnly; verify ownershipControlsStop; verify handoffNotSession; verify managedControl; verify attachExternal; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/app/launcher/tests/test_app_launcher_contract.py#AppLauncherBoundaryVerification"; implementationScope = "InMemoryAppLauncher"; }
    }
}
