# component.app.catalog

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `AppCatalog`
- Lifecycle: `draft`
- Purpose: Own the canonical local set of declarative app descriptors and deterministic metadata queries.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `registerApp` | `RegisterApp` | in `app_descriptor: AppDescriptor`; out `result: AppDescriptor` | `AppDescriptorInvalid`, `AppIdConflict`, `AppCatalogWriteFailed` | Validate and create or replace the descriptor with the same app identity. |
| `removeApp` | `RemoveApp` | in `app_id: String`; out `result: AppDescriptor` | `AppNotFound`, `AppCatalogWriteFailed` | Remove and return exactly one descriptor without changing application runtime state. |
| `getApp` | `GetApp` | in `app_id: String`; out `result: AppDescriptor` | `AppNotFound`, `AppCatalogReadFailed` | Return a canonical copy of one descriptor without observing application runtime state. |
| `listApps` | `ListApps` | in `catalog_query: CatalogQuery[0..1]`; out `result: AppDescriptorList` | `AppCatalogReadFailed` | Return matching descriptors in ascending app-identity order using metadata-only filters. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| `OpenAppCatalog` | in `descriptor_store: AppDescriptorList[0..1]`; out `catalog: AppCatalog` | `AppCatalogUnavailable`, `AppCatalogStoreInvalid`, `AppIdConflict` | Open a catalog initialized from an optional descriptor store without launching or attaching to an application. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `descriptors` | `AppDescriptor` | `owned` | Canonical component-owned descriptor occurrences keyed by app_id. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `registerApp` | `descriptors` | `write` | Replace only the descriptor sharing the submitted app identity after full validation. |
| `removeApp` | `descriptors` | `delete` | Delete only the descriptor identified by app_id. |
| `getApp` | `descriptors` | `read` | Return a canonical copy without exposing mutable owned state. |
| `listApps` | `descriptors` | `read` | Filter and order canonical descriptor copies without probing applications. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.app.catalog.register_effect` | `RegisterApp` | `catalog.registerApp` | Success creates or fully replaces exactly one descriptor keyed by app_id and returns its canonical representation; rejection leaves every descriptor unchanged. |
| `contract.app.catalog.remove_effect` | `RemoveApp` | `catalog.removeApp` | Success removes and returns exactly the named descriptor; rejection leaves the catalog unchanged and never stops an application session. |
| `contract.app.catalog.get_effect` | `GetApp` | `catalog.getApp` | Success returns a canonical copy of the named descriptor and both success and failure leave catalog state unchanged. |
| `contract.app.catalog.list_effect` | `ListApps` | `catalog.listApps` | Results are ordered by app_id and filtered only by exact status, inclusion of all requested tags, and launch-surface kind; reads leave state unchanged. |
| `contract.app.catalog.open_effect` | `OpenAppCatalog` | `openAppCatalogSubject` | Opening accepts zero or one descriptor collection, rejects duplicate app identities, and creates no application process, session, or network activity. |
| `invariant.app.catalog.unique_identity` | `AppCatalog` | `catalog` | At most one canonical descriptor exists for each app_id. |
| `invariant.app.catalog.declarative_surfaces` | `AppCatalog` | `catalog` | Launch surfaces contain declarative metadata with explicit managed or handoff runtime control and never process, session, or health state. |
| `invariant.app.catalog.valid_visible_state` | `AppCatalog` | `catalog` | Only fully valid descriptors are visible; launch-surface identities are unique per descriptor and recommended_surface, when present, names one of them. |
| `invariant.app.catalog.domain_state_exclusion` | `AppCatalog` | `catalog` | The catalog stores no application-owned content, progress, graph data, credentials, runtime handles, or process identifiers. |
| `contract.app.catalog.intentional_boundary` | `AppCatalog` | `catalog` | The component does not launch applications, manage shell layout, supervise processes, probe health, provide remote discovery, authorize access, or import launcher, shell, RTG, or application-internal components. |
| `contract.app.catalog.register_app.failures` | `RegisterApp` | `catalog.registerApp` | Invalid descriptors, identity conflicts, and write failures expose no partial descriptor. |
| `contract.app.catalog.remove_app.failures` | `RemoveApp` | `catalog.removeApp` | Missing identities and write failures do not mutate unrelated descriptors. |
| `contract.app.catalog.get_app.failures` | `GetApp` | `catalog.getApp` | Missing identities and read failures do not mutate catalog state. |
| `contract.app.catalog.list_apps.failures` | `ListApps` | `catalog.listApps` | A read failure returns no partial or nondeterministically ordered result. |
| `contract.app.catalog.open.failures` | `OpenAppCatalog` | `openAppCatalogSubject` | Invalid or unavailable stores and duplicate identities do not silently select another store or expose a partially opened catalog. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `LaunchSurface` | `item` | `surface_id: String`, `kind: String`, `mode: LaunchSurfaceMode`, `label: String`, `details: JsonObject`, `runtime_control: RuntimeControl` = `RuntimeControl::managed` | Declarative launch or attachment metadata identified uniquely within one app descriptor. |
| `AppDescriptor` | `item` | `app_id: String`, `title: String`, `summary: String`, `status: String`, `tags[0..*] ordered: String`, `launch_surfaces[0..*] ordered: LaunchSurface`, `recommended_surface[0..1]: String`, `metadata: JsonObject` | Canonical catalog metadata for one application identity. |
| `CatalogQuery` | `attribute` | `status[0..1]: String`, `tags[0..*] ordered: String`, `launch_surface_kind[0..1]: String` | Defined by its typed fields and action requirements. |
| `AppDescriptorList` | `attribute` | `apps[0..*] ordered: AppDescriptor` | Defined by its typed fields and action requirements. |
| `AppCatalogUnavailable` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppCatalogStoreInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppDescriptorInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppIdConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppCatalogWriteFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppNotFound` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `AppCatalogReadFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `LaunchSurfaceMode` | `launch`, `attach`, `launch_or_attach` |
| `RuntimeControl` | `handoff`, `managed` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `OpenAppCatalogContractVerification` | `OpenAppCatalog` | `openEffect`, `openAppCatalogFailureSemantics` | `components/app/catalog/tests/test_app_catalog_contract.py#OpenAppCatalogContractVerification` |
| `RegisterAppContractVerification` | `RegisterApp` | `registerEffect`, `registerAppFailureSemantics` | `components/app/catalog/tests/test_app_catalog_contract.py#RegisterAppContractVerification` |
| `RemoveAppContractVerification` | `RemoveApp` | `removeEffect`, `removeAppFailureSemantics` | `components/app/catalog/tests/test_app_catalog_contract.py#RemoveAppContractVerification` |
| `GetAppContractVerification` | `GetApp` | `getEffect`, `getAppFailureSemantics` | `components/app/catalog/tests/test_app_catalog_contract.py#GetAppContractVerification` |
| `ListAppsContractVerification` | `ListApps` | `listEffect`, `listAppsFailureSemantics` | `components/app/catalog/tests/test_app_catalog_contract.py#ListAppsContractVerification` |
| `AppCatalogBoundaryVerification` | `AppCatalog` | `uniqueIdentity`, `declarativeSurfaces`, `validVisibleState`, `domainStateExclusion`, `intentionalBoundary` | `components/app/catalog/tests/test_app_catalog_contract.py#AppCatalogBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
