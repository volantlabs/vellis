# Vellis v2 simplification — Phase 2 evidence

This is the execution and evidence frame for `W002`, not product authority or a second design.
Accepted meaning remains under `model/`; the approved task plan supplies the selected realization
constraints cited by `system-evolution.yaml`.

## Conformance matrix

| Qualified authority | In-scope obligation | Required non-effect | Nearest plausible wrong implementation | Focused evidence |
|---|---|---|---|---|
| `RTG::Scalar Value`, `Scalar And Definition Integrity` | Immutable Boolean, safe-integer, binary64, text, date, timestamp, and nullable property values with exact canonicalization | No recursive user JSON or Decimal in the successor domain | A tagged value still accepts nested JSON, unsafe integers, non-finite numbers, or spelling-dependent timestamps | Scalar boundary, canonical form, null/absence, constraint, and round-trip tests |
| `RTG::Graph Object`, `Graph And Lineage Integrity` | Canonical UUIDs, immutable kind reservations, typed objects, read-only canonical envelopes, and same-kind reactivation | Draft input cannot write system metadata; no cascade or complete-object update implementation yet | UUID reuse changes kind or a patch can replace/import system fields | Identity reservation, envelope, and restart tests |
| `RTG::Graph Definition Set`, `Local Cardinality Integrity` | Small cohesive definitions with scalar property rules and four local bounds | No relationship-rule identity, participant-set rule, registry, or dimensional algebra | Old multiplicity families survive under renamed definitions | Definition validation and exact starter tests |
| `Historical State And Canonical Ledger` | Fresh VEL2 identity, indexed version intervals, one state/definition resolver, canonical binary row digests and revision hash | No replay, event-family table, whole-state document, checkpoint, or second projection authority | Current state reconstructs by traversing records or duplicate definition loaders disagree | Interval edges, hash mutation, reopen, and query-plan/instrumentation tests |
| `Fresh And V1 Initialization`, `Recommended Everyday Life Start` | Atomic blank or exact starter revision-zero publication with empty graph/activity/draft | No v1 importer, MCP, client setup, or prototype-v2 migration in this phase | Failed initialization leaves a readable partial database or retained population state | Publication failure, permissions, blank/starter content, audit, and prototype refusal tests |
| `Locality And Bounded Materialization` | Connection-local repository functions and one connection/transaction per operation | No global store, shared connection, reusable populated temporary relation, ORM, or forwarding service class | A new façade delegates into the monolith or current reads scan canonical history | Connection close/rollback and no-ledger-traversal instrumentation |

## Selected inherited realization decisions

- Direct final modules use frozen slotted domain dataclasses and `StrEnum`; the domain imports no
  SQLite, Pydantic, FastMCP, CLI, or environment facilities.
- SQLite repository functions receive a caller-owned connection and never own transactions.
- Operation functions accept a database path, open exactly one connection, own one transaction,
  serialize their complete domain result before commit where a write occurs, and close on every exit.
- New databases use application id `VEL2`, schema version 1, one random lineage UUID, foreign keys,
  WAL, full synchronization, a five-second busy timeout, and trusted schema disabled. `VEL1` schema 5
  is refused rather than migrated.
- Canonical values use the approved closed binary framing and SHA-256 rules. Current and historical
  reads use version indexes and the metadata head, never canonical replay.
- Phase 2 realizes the listed canonical/version relations and declares the remaining approved
  relations in the fresh schema without implementing their later-phase behavior twice.

## Intended subtraction and touched boundaries

This phase replaces the active successor-domain, initialization, canonical-encoding, connection,
version-storage, state-resolution, and basic-audit paths. It removes their superseded tests as each
replacement becomes final. Query compilation, draft behavior, full activity/history/restore/backup,
v1 streaming, MCP, CLI onboarding, and predecessor residue not yet replaced remain owned by later
work items; no compatibility or forwarding layer is added.

Logical relations touched are metadata/settings, canonical records, graph/type reservations,
versioned graph structure, associations, properties, definitions, permitted members, property
definitions, allowed values, and the empty later-phase draft/validation/activity/search relations
selected by the approved schema ceiling.

Public boundaries affected are domain values and operation functions for blank/starter
initialization, current/revision/time state resolution, typed current/historical reads, and basic
audit. No MCP or owner CLI contract is exposed in this phase.

## Evidence log

### Implemented distinction

- `vellis/domain.py` and `vellis/domain_validation.py` provide a framework-free frozen scalar,
  definition, object, state, finding, and field-patch domain. UUID normalization, safe integers,
  finite normalized binary64 values, Gregorian dates, UTC timestamps, null/presence, property
  constraints, definition references, graph references, and the four local cardinalities are
  explicit. Draft-only values carry no system envelope; no system field appears in a patch request.
  Raw scalar/timestamp constructors enforce the same invariants as convenience constructors, and
  every UUID-bearing canonical object or patch normalizes hyphenated input to lowercase. Fixed
  object, definition, state, and patch discriminators are not constructor inputs; revision,
  timestamp-component, and cardinality fields reject Boolean or otherwise non-integer values.
  Property, definition, object, patch, result, and system-envelope constructors enforce their
  structural runtime types and immutable tuple shapes instead of relying on annotations. Optional
  `legacyV1` content is validated as canonical JSON text.
- `vellis/canonical_encoding.py` and `vellis/version_encoding.py` provide the closed tagged binary
  encoder, row identities/digests, and canonical record hashing. It has no mapping/JSON fallback;
  absence, null, Boolean, integer, and number remain distinct, set ordering is canonical, and
  normalized negative zero hashes as positive zero. Its tag and framing assignments are explicitly
  bound to database `user_version = 1` rather than presented as freely changeable internals.
- `vellis/database.py` declares exactly the selected 25 published application relations. Draft
  relations are explicit normalized fields and typed scalar columns rather than opaque domain
  documents; the twenty-sixth initialization-staging relation remains absent until the unpublished
  v1 staging database in W006. SQLite FTS shadow tables are SQLite-owned. Version rows carry direct
  intervals and row digests; typed scalar rows use exactly one compatible representation.
- `vellis/state_repository.py` is the one state-selection path and
  `vellis/definition_repository.py::load_definitions` is the one successor definition resolver.
  Current selection reads the metadata head; current and historical repositories use interval
  predicates and never traverse the canonical ledger.
- `vellis/operations.py` owns one connection and transaction per operation. Fresh publication uses
  a mode-0600 temporary sibling, validates, hashes, audits, checkpoints WAL, flushes, and atomically
  renames. Failure removes only that temporary family and publishes no destination. Blank and
  starter initialization create revision zero, empty graph/activity/draft, and no population temp
  state. Publication uses an atomic no-replace link so a raced destination survives untouched;
  post-publication housekeeping cannot report rollback. `VEL1` schema 5 receives an actionable
  refusal.
- `vellis/starter.py` realizes 12 anchor definitions, 12 local-bound `.details` definitions, and 9
  link definitions. All details properties are optional/non-nullable; Boolean fields remain Boolean
  and the eight modeled date fields are true dates. No relationship-rule object or example graph is
  created. A complete model-derived semantic projection digest covers every key, description,
  endpoint set, property contract, and local bound.
- `vellis/audit.py` independently reads the database, verifies SQLite/schema/lineage identity,
  revision continuity and time order, intervals, reservations, full definition/graph conformance,
  introduced row digests, the canonical chain, and the empty/current FTS projection. Phase 5 owns
  activity, restore, backup, and the remaining full-ledger audit obligations.
  The metadata head is FK-bound and audited against the greatest revision. Redundant timestamp
  text/epoch/nanosecond fields are mutually compatible at storage and independently cross-checked
  by audit for records, properties, bounds, and allowed values, including exact canonical text.
  Audit owns one read snapshot. Introduced object and definition versions must carry
  `lastChangedRevision` equal to their `validFromRevision`; repository checks, schema checks, and
  audit independently enforce the rule. Canonical object, definition, and typed scalar rows have
  closed kind-specific shapes at both the SQL and independent audit boundaries; corrupt row
  decoding becomes an integrity finding rather than escaping the audit operation.

### Third-pair root-cause audit

After three consecutive non-clean Phase 2 review pairs, the required bounded audit traced the
recurring findings to one shared error: typed annotations and happy-path repository writes had been
treated as if they closed the raw-constructor, persistent-row, and filesystem boundaries. The audit
therefore swept the complete Phase 2 domain dataclass inventory, every canonical kind-discriminated
row family, audit exception behavior, numeric conversion, and SQLite path construction. It did not
broaden into Phase 3 query behavior or Phase 4 draft semantics.

The correction closes raw structural types and immutable collection shapes, normalizes the shortest
exponent spelling, translates binary64 overflow into the selected validation failure, escapes
read-only SQLite file URIs, adds kind-specific definition bounds to the schema, and independently
checks canonical graph/definition/scalar row shapes during audit. Counterexamples cover Boolean-as-
integer fields, caller-supplied discriminators, malformed/noncanonical legacy JSON, irrelevant or
missing definition bounds, equivalent noncanonical timestamps, and `?`, `#`, `%`, and space in
database filenames. No new public operation, persisted concept, compatibility path, abstraction
framework, or deferred behavior was introduced.

The following pair found two residual instances at the same persistence/publication boundary.
Initialization now refuses an existing POSIX data directory whose mode is not exactly `0700`,
rather than silently changing an arbitrary parent. Audit now requires every permanent UUID and type-
key reservation to have a corresponding earliest canonical version whose introduction revision
equals the reservation's `createdRevision`.

A subsequent engineering review found that canonical `legacyV1` validation had still passed JSON
numbers through binary64 and that initialization summaries still accepted caller prose. The
validator now parses and canonically re-encodes JSON number lexemes losslessly, including arbitrary
precision and exponent magnitude, without adding Decimal to active property values. Revision-zero
summaries are generated from complete definition-kind and graph-object counts; deterministic type-
key examples are UTF-8 bounded only after those counts.

The next authority review exposed the prior SQLite-capacity footgun in nonnegative model integers.
Revision requests are now compared with the SQLite-sized canonical head before binding. Definition
cardinality and text-length naturals are persisted as canonical decimal text, preserving arbitrary
accepted values exactly without imposing a new public maximum; repository loading and audit reject
noncanonical or inverted stored representations.

The next engineering review found that an unlink failure after no-replace hard-link publication was
silently accepted, leaving a complete hidden temporary name. Publication now removes the new
destination and reports rollback when temporary-name cleanup fails. If both cleanup and rollback
fail, it reports the published state as indeterminate rather than claiming either clean success or
rollback.

The following pair found two final integrity distinctions: RFC 3339 `-00:00` denotes an unknown
offset and is now rejected rather than silently treated as UTC; audit now derives each canonical
record's affected type keys and UUIDs from all structural versions introduced or retired at that
revision and requires the stored deterministic arrays to match.

The next authority review found that a correctly hashed child-only version transition could bypass
the parent object's or definition's `lastChangedRevision` and affected identity. Canonical child
introductions now reference the corresponding parent version, and audit requires every child
introduction or retirement boundary to coincide with a parent structural boundary. A correctly
rehashed retired-property-definition counterexample proves this is independent of hash corruption.

The following pair completed that containment rule: a child interval must equal its parent interval,
so a current child cannot outlive a retired parent. Audit also validates the database-lineage value
as a canonical hyphenated UUID independently of a coherently recomputed hash chain. Correctly hashed
parent-only retirement and malformed-lineage counterexamples isolate both checks.

### Focused evidence

- `uv run pytest -q tests/vellis/test_domain_v2.py tests/vellis/test_canonical_encoding_v2.py tests/vellis/test_storage_v2.py`
  passes 66 tests. It discriminates scalar limits and canonical forms, raw-constructor bypasses,
  canonical UUID persistence, null versus absence,
  self-inconsistent property rules, definition/graph/cardinality failures, closed encoder tags and
  ordering, digest/header/row mutation, exact schema identity and relation inventory, owner-private
  atomic publication, exact starter content, revision/time edges, prototype refusal, no-ledger
  current reads, rollback/cleanup, scalar and definition-constraint SQLite round trips, and
  same-kind-only UUID/type-key reactivation with preserved system metadata. Cardinality evidence
  exercises exact, minimum, maximum, unbounded, and unified-permitted-population behavior for all
  four local bound roles. Failure injection covers a raced destination and the post-publication
  reporting boundary. Integrity mutations additionally cover a mixed-snapshot audit,
  noncanonical-but-equivalent timestamp text in every timestamp-bearing family, stale
  last-changed metadata, nonintegral scientific-number shortest form, oversized numeric input,
  closed definition-row shapes, and escaped read-only database paths.
  It also covers non-private existing-directory refusal and orphan UUID/type-key reservations.
  Exact legacy JSON numbers and generated-summary ordinary/truncation cases are covered directly.
  An above-head `10**30` revision and round-tripped `10**30` cardinality/text-length bounds exclude
  accidental SQLite-integer limits.
  Injected post-link cleanup failure proves that no accepted initialization retains a population-
  bearing temporary name.
  Unknown-offset timestamps and mutated canonical-record affected arrays are rejected.
  Cohesive parent/child version boundaries are exercised with an otherwise valid hash chain.
  Parent retirement with current children and rehashed malformed lineage are rejected directly.
  Public finding references normalize to sorted unique type keys and canonical UUIDs, and operation
  findings normalize to the selected deterministic wire order even when directly constructed.
- `uv run ruff check --select C901 --config 'lint.mccabe.max-complexity=10'` over every Phase 2
  production file passes with no exception.
- `just lint`, `just typecheck`, `just model-check`, `just model-reference-check`,
  `just system-evolution-check`, and `git diff --check` pass.
- A diagnostic full `just test` ran 1,301 tests: 1,299 passed. Its two failures are both the already
  recorded stale completed-campaign coupling owned by F010/W008: the committed campaign model
  digest is intentionally pre-rebaseline and its obsolete qualified references no longer resolve.
  Phase 2 neither edits nor treats that completed campaign as authority; removing it from ordinary
  validation remains the explicit Phase 8 task.

### Subtraction and locality review

The successor path imports no predecessor `Store`, recursive JSON/Decimal value, FastMCP, Pydantic,
CLI, or environment module. It contains no store/service/manager class, repository interface,
trigger, replay document, event-family table, relationship-rule identity, generic domain state
table, reusable populated temporary relation, or second current projection. The still-runnable
predecessor product remains physically present only for behaviors not yet replaced; it is not called
by the successor foundation and is owned by the explicit subtraction in later work items.

The largest new catalog module is the SQL schema declaration; orchestration and repository modules
remain below the 800-line subtraction trigger, and every new production function is C901 10 or less.
Current resolution queries only the metadata singleton and indexed selected version intervals.
