# Bibliotek model reference

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

Bibliotek is a reusable SysML library package. It imports the generic modeling foundation privately and publicly exposes its supported component and shared-value packages. It has no dependency on Vellis or its realizations.

## Components

| Component | Status | Generated view |
|---|---|---|
| `component.app.catalog` | `draft` | [component view](components/component.app.catalog.md) |
| `component.app.launcher` | `draft` | [component view](components/component.app.launcher.md) |
| `component.app.shell` | `draft` | [component view](components/component.app.shell.md) |
| `component.rtg.change_validation` | `accepted` | [component view](components/component.rtg.change_validation.md) |
| `component.rtg.constraints` | `accepted` | [component view](components/component.rtg.constraints.md) |
| `component.rtg.controller` | `accepted` | [component view](components/component.rtg.controller.md) |
| `component.rtg.discovery` | `draft` | [component view](components/component.rtg.discovery.md) |
| `component.rtg.graph` | `accepted` | [component view](components/component.rtg.graph.md) |
| `component.rtg.migration` | `accepted` | [component view](components/component.rtg.migration.md) |
| `component.rtg.query` | `accepted` | [component view](components/component.rtg.query.md) |
| `component.rtg.schema` | `accepted` | [component view](components/component.rtg.schema.md) |
| `component.storage.json_file` | `accepted` | [component view](components/component.storage.json_file.md) |
| `component.storage.sql` | `accepted` | [component view](components/component.storage.sql.md) |

## Shared public packages

| Shared package | Ownership |
|---|---|
| `BibliotekSoftwareValues` | Bibliotek-wide public values with no single component owner. |
| `BibliotekRtgDiagnostics` | Bibliotek-wide public values with no single component owner. |

## Shared public values

| Package | Public definition | Kind | Fields / literals | Meaning |
|---|---|---|---|---|
| `BibliotekSoftwareValues` | `Uuid` | `attribute` | `value: String` | Canonical lowercase textual UUID representation. |
| `BibliotekSoftwareValues` | `Timestamp` | `attribute` | `iso8601: String` | An ISO-8601 timestamp with an explicit offset. |
| `BibliotekSoftwareValues` | `JsonValue` | `abstract attribute` | `kind: JsonKind` | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonScalar` | `abstract attribute` | — | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonNull` | `attribute` | — | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonBoolean` | `attribute` | `value: Boolean` | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonNumber` | `attribute` | `value: Real` | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonString` | `attribute` | `value: String` | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonArray` | `attribute` | `kind: JsonKind`, `values[0..*] ordered: JsonValue` | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonMember` | `attribute` | `key: String`, `value: JsonValue` | Defined by its typed alternatives or fields. |
| `BibliotekSoftwareValues` | `JsonObject` | `attribute` | `kind: JsonKind`, `members[0..*]: JsonMember` | Member keys are unique; member order has no semantic meaning. JsonValueEqual therefore compares objects by their key-to-value mapping rather than member occurrence order. |
| `BibliotekSoftwareValues` | `FileSystemRootPath` | `attribute` | `value: String` | Caller-supplied filesystem root; unlike a document path, it is not relative to itself. |
| `BibliotekSoftwareValues` | `FileSystemFilePath` | `attribute` | `value: String` | Caller-supplied filesystem file path, not a directory root or component-relative document path. |
| `BibliotekSoftwareValues` | `JsonKind` | `enum` | `nullValue`, `booleanValue`, `numberValue`, `stringValue`, `arrayValue`, `objectValue` | Closed public literal vocabulary. |
| `BibliotekRtgDiagnostics` | `RtgDiagnostic` | `attribute` | `code: String`, `category: String`, `problem: String`, `remedy: String`, `path[0..1]: String`, `acceptedFields[0..*]: String`, `minimalExample[0..1]: JsonObject`, `guideTopics[0..*]: String`, `safeToRetry: Boolean` = `true`, `mutationState: String` = `"not_mutated"` | Generic JSON-safe corrective guidance. code is stable within its owning contract; category groups the problem; optional fields refine location, accepted shape, examples, workflow guidance, retry safety, and the observable mutation outcome. |

## Retained component dependency topology

| Consumer | Retained role | Required component type | Provider |
|---|---|---|---|
| `component.rtg.controller` | `graph` | `RtgGraph` | `component.rtg.graph` |
| `component.rtg.controller` | `schema` | `RtgSchema` | `component.rtg.schema` |
| `component.rtg.controller` | `constraints` | `RtgConstraints` | `component.rtg.constraints` |
| `component.rtg.controller` | `migration` | `RtgMigration` | `component.rtg.migration` |
| `component.rtg.controller` | `jsonStorage` | `JsonFileStorage` | `component.storage.json_file` |
| `component.rtg.controller` | `sqlStorage` | `SqlStorage` | `component.storage.sql` |
