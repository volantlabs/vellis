library package BibliotekAppCatalog {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /*
     * Local authority for declarative application descriptors and launch-surface metadata.
     * The catalog deliberately owns no application process, session, health, or domain state.
     */

    enum def LaunchSurfaceMode {
        enum launch;
        enum attach;
        enum launch_or_attach;
    }

    enum def RuntimeControl {
        enum handoff;
        enum managed;
    }

    item def LaunchSurface {
        attribute surface_id : String;
        attribute kind : String;
        attribute mode : LaunchSurfaceMode;
        attribute label : String;
        attribute details : JsonObject;
        attribute runtime_control : RuntimeControl default = RuntimeControl::managed;
        doc /* Declarative launch or attachment metadata identified uniquely within one app descriptor. */
    }

    item def AppDescriptor {
        attribute app_id : String;
        attribute title : String;
        attribute summary : String;
        attribute status : String;
        attribute tags[0..*] ordered : String;
        item launch_surfaces[0..*] ordered : LaunchSurface;
        attribute recommended_surface[0..1] : String;
        attribute 'metadata' : JsonObject;
        doc /* Canonical catalog metadata for one application identity. */
    }

    attribute def CatalogQuery {
        attribute status[0..1] : String;
        attribute tags[0..*] ordered : String;
        attribute launch_surface_kind[0..1] : String;
    }

    attribute def AppDescriptorList {
        item apps[0..*] ordered : AppDescriptor;
    }

    attribute def AppCatalogUnavailable { attribute 'message' : String; }
    attribute def AppCatalogStoreInvalid { attribute 'message' : String; }
    attribute def AppDescriptorInvalid { attribute 'message' : String; }
    attribute def AppIdConflict { attribute 'message' : String; }
    attribute def AppCatalogWriteFailed { attribute 'message' : String; }
    attribute def AppNotFound { attribute 'message' : String; }
    attribute def AppCatalogReadFailed { attribute 'message' : String; }

    action def RegisterApp {
        in app_descriptor : AppDescriptor;
        out result : AppDescriptor;
        doc /* Validate and create or replace the descriptor with the same app identity. */
        @FailureContract {
            errorIds = ("AppDescriptorInvalid", "AppIdConflict", "AppCatalogWriteFailed");
        }
    }

    action def RemoveApp {
        in app_id : String;
        out result : AppDescriptor;
        doc /* Remove and return exactly one descriptor without changing application runtime state. */
        @FailureContract { errorIds = ("AppNotFound", "AppCatalogWriteFailed"); }
    }

    action def GetApp {
        in app_id : String;
        out result : AppDescriptor;
        doc /* Return a canonical copy of one descriptor without observing application runtime state. */
        @FailureContract { errorIds = ("AppNotFound", "AppCatalogReadFailed"); }
    }

    action def ListApps {
        in catalog_query[0..1] : CatalogQuery;
        out result : AppDescriptorList;
        doc /* Return matching descriptors in ascending app-identity order using metadata-only filters. */
        @FailureContract { errorIds = ("AppCatalogReadFailed"); }
    }

    part def <'component.app.catalog'> AppCatalog {
        doc /* Own the canonical local set of declarative app descriptors and deterministic metadata queries. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        item descriptors[0..*] : AppDescriptor {
            doc /* Canonical component-owned descriptor occurrences keyed by app_id. */
        }

        perform action registerApp[0..*] : RegisterApp;
        perform action removeApp[0..*] : RemoveApp;
        perform action getApp[0..*] : GetApp;
        perform action listApps[0..*] : ListApps;

        dependency registerDescriptorState from registerApp to descriptors {
            @StateAccess { kind = StateAccessKind::write; }
            doc /* Replace only the descriptor sharing the submitted app identity after full validation. */
        }
        dependency removeDescriptorState from removeApp to descriptors {
            @StateAccess { kind = StateAccessKind::delete; }
            doc /* Delete only the descriptor identified by app_id. */
        }
        dependency getDescriptorState from getApp to descriptors {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Return a canonical copy without exposing mutable owned state. */
        }
        dependency listDescriptorState from listApps to descriptors {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Filter and order canonical descriptor copies without probing applications. */
        }
    }

    action def OpenAppCatalog {
        in descriptor_store[0..1] : AppDescriptorList;
        out part catalog : AppCatalog;
        doc /* Open a catalog initialized from an optional descriptor store without launching or attaching to an application. */
        @FailureContract { errorIds = ("AppCatalogUnavailable", "AppCatalogStoreInvalid", "AppIdConflict"); }
    }

    requirement <'contract.app.catalog.register_effect'> registerEffect {
        subject operation : RegisterApp;
        require constraint {
            doc /* Success creates or fully replaces exactly one descriptor keyed by app_id and returns its canonical representation; rejection leaves every descriptor unchanged. */
        }
    }

    requirement <'contract.app.catalog.remove_effect'> removeEffect {
        subject operation : RemoveApp;
        require constraint {
            doc /* Success removes and returns exactly the named descriptor; rejection leaves the catalog unchanged and never stops an application session. */
        }
    }

    requirement <'contract.app.catalog.get_effect'> getEffect {
        subject operation : GetApp;
        require constraint {
            doc /* Success returns a canonical copy of the named descriptor and both success and failure leave catalog state unchanged. */
        }
    }

    requirement <'contract.app.catalog.list_effect'> listEffect {
        subject operation : ListApps;
        require constraint {
            doc /* Results are ordered by app_id and filtered only by exact status, inclusion of all requested tags, and launch-surface kind; reads leave state unchanged. */
        }
    }

    requirement <'contract.app.catalog.open_effect'> openEffect {
        subject operation : OpenAppCatalog;
        require constraint {
            doc /* Opening accepts zero or one descriptor collection, rejects duplicate app identities, and creates no application process, session, or network activity. */
        }
    }

    requirement <'invariant.app.catalog.unique_identity'> uniqueIdentity {
        subject catalog : AppCatalog;
        require constraint {
            doc /* At most one canonical descriptor exists for each app_id. */
        }
    }

    requirement <'invariant.app.catalog.declarative_surfaces'> declarativeSurfaces {
        subject catalog : AppCatalog;
        require constraint {
            doc /* Launch surfaces contain declarative metadata with explicit managed or handoff runtime control and never process, session, or health state. */
        }
    }

    requirement <'invariant.app.catalog.valid_visible_state'> validVisibleState {
        subject catalog : AppCatalog;
        require constraint {
            doc /* Only fully valid descriptors are visible; launch-surface identities are unique per descriptor and recommended_surface, when present, names one of them. */
        }
    }

    requirement <'invariant.app.catalog.domain_state_exclusion'> domainStateExclusion {
        subject catalog : AppCatalog;
        require constraint {
            doc /* The catalog stores no application-owned content, progress, graph data, credentials, runtime handles, or process identifiers. */
        }
    }

    requirement <'contract.app.catalog.intentional_boundary'> intentionalBoundary {
        subject catalog : AppCatalog;
        require constraint {
            doc /* The component does not launch applications, manage shell layout, supervise processes, probe health, provide remote discovery, authorize access, or import launcher, shell, RTG, or application-internal components. */
        }
    }

    requirement <'contract.app.catalog.register_app.failures'> registerAppFailureSemantics {
        subject operation : RegisterApp;
        require constraint { doc /* Invalid descriptors, identity conflicts, and write failures expose no partial descriptor. */ }
    }
    requirement <'contract.app.catalog.remove_app.failures'> removeAppFailureSemantics {
        subject operation : RemoveApp;
        require constraint { doc /* Missing identities and write failures do not mutate unrelated descriptors. */ }
    }
    requirement <'contract.app.catalog.get_app.failures'> getAppFailureSemantics {
        subject operation : GetApp;
        require constraint { doc /* Missing identities and read failures do not mutate catalog state. */ }
    }
    requirement <'contract.app.catalog.list_apps.failures'> listAppsFailureSemantics {
        subject operation : ListApps;
        require constraint { doc /* A read failure returns no partial or nondeterministically ordered result. */ }
    }
    requirement <'contract.app.catalog.open.failures'> openAppCatalogFailureSemantics {
        subject operation : OpenAppCatalog;
        require constraint { doc /* Invalid or unavailable stores and duplicate identities do not silently select another store or expose a partially opened catalog. */ }
    }

    part contractContext {
        part catalog : AppCatalog;
        satisfy registerEffect by catalog.registerApp;
        satisfy removeEffect by catalog.removeApp;
        satisfy getEffect by catalog.getApp;
        satisfy listEffect by catalog.listApps;
        satisfy uniqueIdentity by catalog;
        satisfy declarativeSurfaces by catalog;
        satisfy validVisibleState by catalog;
        satisfy domainStateExclusion by catalog;
        satisfy intentionalBoundary by catalog;
        satisfy registerAppFailureSemantics by catalog.registerApp;
        satisfy removeAppFailureSemantics by catalog.removeApp;
        satisfy getAppFailureSemantics by catalog.getApp;
        satisfy listAppsFailureSemantics by catalog.listApps;
        action openAppCatalogSubject : OpenAppCatalog;
        satisfy openEffect by openAppCatalogSubject;
        satisfy openAppCatalogFailureSemantics by openAppCatalogSubject;
    }

    verification def OpenAppCatalogContractVerification {
        subject operation : OpenAppCatalog;
        objective { verify openEffect; verify openAppCatalogFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/app/catalog/tests/test_app_catalog_contract.py#OpenAppCatalogContractVerification"; implementationScope = "InMemoryAppCatalog"; }
    }
    verification def RegisterAppContractVerification {
        subject operation : RegisterApp;
        objective { verify registerEffect; verify registerAppFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/app/catalog/tests/test_app_catalog_contract.py#RegisterAppContractVerification"; implementationScope = "InMemoryAppCatalog"; }
    }
    verification def RemoveAppContractVerification {
        subject operation : RemoveApp;
        objective { verify removeEffect; verify removeAppFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/app/catalog/tests/test_app_catalog_contract.py#RemoveAppContractVerification"; implementationScope = "InMemoryAppCatalog"; }
    }
    verification def GetAppContractVerification {
        subject operation : GetApp;
        objective { verify getEffect; verify getAppFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/app/catalog/tests/test_app_catalog_contract.py#GetAppContractVerification"; implementationScope = "InMemoryAppCatalog"; }
    }
    verification def ListAppsContractVerification {
        subject operation : ListApps;
        objective { verify listEffect; verify listAppsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/app/catalog/tests/test_app_catalog_contract.py#ListAppsContractVerification"; implementationScope = "InMemoryAppCatalog"; }
    }
    verification def AppCatalogBoundaryVerification {
        subject catalog : AppCatalog;
        objective {
            verify uniqueIdentity;
            verify declarativeSurfaces;
            verify validVisibleState;
            verify domainStateExclusion;
            verify intentionalBoundary;
        }
        @EvidenceBinding { evidenceId = "components/app/catalog/tests/test_app_catalog_contract.py#AppCatalogBoundaryVerification"; implementationScope = "InMemoryAppCatalog"; }
    }
}
