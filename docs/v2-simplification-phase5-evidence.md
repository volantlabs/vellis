# Vellis v2 simplification Phase 5 evidence

## Implementation frame

- Baseline: accepted model digest
  `8af0ac5250d5186b8baa693bc8ebcc2b5e69f0e130754fbc676cb2302bfa8794`;
  evolution work item `W005`; predecessor campaign authority remains unread.
- Qualified authority: `RTG::'Canonical State'`, `RTG::'Canonical Record'`,
  `RTG::'Activity Record'`, `RTG::'History Query'`, `RTGSystem::'Inspect bounded
  history'`, `RTGSystem::'Configure activity detail'`, `RTGSystem::'Restore
  historical state'`, `RTGSystem::'Audit complete RTG'`, `RTGSystem::'Back up
  complete RTG'`, `VellisRequirements::historicalState`,
  `VellisRequirements::activitySeparation`, `VellisRequirements::lifecycle`, and
  the corresponding two Phase 5 verification definitions.
- Outcome: the owner can inspect complete bounded canonical or observational
  history, restore an earlier meaning as one new transition, verify stored
  integrity without mutation, and publish a complete audited SQLite backup.
- Unread model scope: v1 conversion and external MCP/client lifecycle details are
  outside this slice; their shared initialization and filesystem consequences are
  read only where backup initialization depends on them.

## Conformance matrix

| Obligation | Coverage | Status before work | Planned realization | Decisive evidence | Required non-effect |
| --- | --- | --- | --- | --- | --- |
| Indexed canonical history and time/sequence selection | Full | Partial | Typed history request/result plus indexed SQL interval selection | Boundary, tied-time, empty interval, and maximum-plus-one tests | No replay payload, snapshot, or state reconstruction |
| Separate semantic/verbose observational activity | Full | Partial | Existing header/payload relations, normalized detail, atomic append | Mode change, rejected request, history self-exclusion, privacy and payload-shape tests | No activity hash chain, pruning, session, or canonical authority |
| Restore selected graph and definitions | Full | Absent | One immediate transaction, SQL-indexed historical load, complete validation, one revision only on difference | Revision/time restore, no-op, draft refusal, metadata preservation | No history rewrite, cascade, or snapshot replacement authority |
| Complete read-only audit | Full | Partial | Extend the existing independent row/hash checks through graph, search, activity, and validation integrity | Corrupt copied fixtures across each retained relation family | No repair, replay, or source activity |
| Online backup and empty-destination initialization | Full | Absent | SQLite online backup to private temporary sibling, audit, fsync, atomic no-replace publication | Live source use, complete copied meaning, overwrite refusal, sidecar exclusion | No source activity, token/report copy, or generated token |
| Bounded/state-wide work distinction | Full | Partial | History uses indexed range predicates; restore/audit/backup stream or scan state-wide with bounded Python working sets and connection-local keyed relations | Loader instrumentation and multi-object restore/audit; exact accumulator inventory | No numerical performance promise or checkpoint framework |

## Nearest plausible wrong system

Version tables coexist with public replay/snapshot/tail authority; history truncates
silently at the caller maximum; an activity-history read includes itself; verbose
detail leaks into semantic mode; restore overwrites or drops intervening history;
audit trusts stored hashes or projections; or backup copies sidecars and mutates the
source merely by reading it.

## Selected realization and boundaries

- Reuse the one connection factory, version intervals, canonical encoder/hash,
  state/definition resolver, and the two existing activity relations.
- Move semantic detail from the activity header into the existing payload relation;
  verbose detail remains optional in that same relation. No third activity relation
  or generic event framework is introduced.
- History, restore, configure, audit, backup, and backup initialization are explicit
  operation functions. They own their connections; no store/service class is added.
- Restore scans selected/current keys but retains only one definition or graph
  object and its owned/referenced values at a time. Differences and hash
  descriptors live in connection-local keyed SQL relations, never a complete
  Python state or lineage snapshot.
- Backup copies only the selected SQLite database file through SQLite's online
  backup API. HTTP-token and v1-report sidecars are therefore outside the copy by
  construction.

Logical relations touched: metadata/settings, canonical records, all seven
canonical version families and identity reservations, validation runs/findings,
activity headers/payloads, search documents/FTS. No new application relation is
planned.

Public boundaries affected: operation-level history, activity-mode configuration,
restore, audit, backup, and setup-from-backup. MCP and CLI adapters remain Phase 7.

Intended deletions: successor code adds no snapshot/tail/replay/preserve path.
Predecessor paths still needed by the currently runnable predecessor adapter remain
tracked by `F006` and are deleted only when Phase 7 removes reachability and Phase 8
removes residue; they are not reused here.

Explicit non-goals: activity authentication, pruning/archive, built-in analysis,
conversation capture, public replay, semantic snapshots, checkpoint acceleration,
encryption, daemon coordination, and numerical throughput targets.

## Implemented distinction

- `history_domain.py`, `history_repository.py`, and `history_operations.py`
  implement one typed, indexed, complete-or-rejected canonical/activity history
  interval. Activity selection is frozen before the history operation appends its
  own record. Canonical affected-key arrays decode only from JSON arrays and are
  domain-validated as sorted, duplicate-free nonempty type keys and canonical UUIDs;
  empty arrays remain valid. Canonical entries contain no replay payload.
- Semantic activity and optional verbose detail now live together in the existing
  payload relation, separate from the header. Discovery, query, change, draft,
  validation, activation, discard, history, restore, and configuration append
  normalized semantic detail; verbose mode alone retains complete normalized
  request/response. Dataclass discriminators such as object and selection `kind`
  are retained in stored request detail.
- `restore_operations.py` resolves revision/time through the one state resolver,
  validates the selected complete meaning record-by-record, stages definition and
  object differences as temporary keys, and publishes each key plus streamed hash
  members. Equal current meaning is an activity-only no-op; a draft or unresolved
  selection rejects without canonical effect.
- `audit.py`, `audit_observability.py`, and the bounded `audit_governance.py`
  companion independently rederive canonical hashes/descriptors, graph
  conformance, search documents/FTS, the normalized draft/fingerprint, activity
  domain records, and validation findings/backing. Draft records are also checked
  against permanent UUID/type-key kind reservations without treating proposal
  nonconformance as storage corruption. Audit uses a read-only source connection
  and adds no activity.
- `backup_operations.py` uses SQLite online backup into an owner-private temporary
  sibling, audits the copy, flushes it, and atomically publishes without overwrite.
  Empty-destination initialization first audits its source and preserves the
  database lineage without copying adjacent token or v1-report files.

No application relation was added: the schema remains at 25 logical relations.
The activity header/payload boundary was corrected within its two already selected
relations.

## Focused evidence

`tests/vellis/test_history_recovery_v2.py` supplies 91 Phase 5 cases covering:

- complete ordered canonical history, maximum-plus-one refusal, activity head and
  self-exclusion, including an ordinary graph transition with a nonempty affected
  UUID array;
- raw and persisted affected-key rejection for non-arrays, malformed JSON,
  duplicates, unsorted content, empty type keys, and noncanonical UUIDs, while
  preserving valid empty arrays;
- inclusive time, exclusive/inclusive sequence, reversed-time, empty-range, tied
  time, backward-clock behavior, and arbitrary-size natural sequence bounds
  clamped before SQLite binding for both ledgers;
- semantic versus verbose detail, complete rejected mutation request, and truthful
  first-100 bindings with the complete count, plus complete findings for every
  rejected well-formed successor operation including history and draft inspection;
  history activity contains only request/range/count/result-shape summaries even
  in verbose mode, never recursively copied selected ledger entries;
- deterministic affected type-key/UUID arrays and resulting revision for accepted
  graph changes, draft activation, and restore, matched to their canonical record;
- revision/time restore, no-op restore, draft refusal, definition/object removal,
  creation/last-change metadata, hash continuity, and serialization rollback;
- independent canonical, graph-version, search-document, FTS, activity, and
  validation corruption detection without audit activity, including every child
  version family and activity/validation structural edges;
- every normalized draft relation plus metadata, with the fingerprint recomputed
  after child corruption so relation-specific checks must detect the defect,
  including exact property-operation vocabulary and permanent kind reservations;
- malformed-but-JSON activity and validation content, nonempty header fields,
  domain finding codes/UUIDs/summaries, cursor/count/fingerprint consistency, and
  backup/setup refusal without partial publication;
- intentionally nonconforming but structurally stageable associated-data/link
  definitions whose empty permitted sets and mismatched allowed-value kind remain
  clean audit/backup content while draft validation reports proposal findings;
- persisted activity-mode corruption rejected by both audit and backup;
- a 96-object audit/restore cycle instrumented to reject any complete-state
  definition or graph load;
- deterministic canonical-writer overlap during online backup with both source and
  copy independently auditing clean, draft/settings/activity/validation
  preservation, sidecar exclusion, overwrite refusal, identical-lineage
  initialization, and no destination from a corrupt backup source;
- failure injection at online copy, copied audit, file flush, pre-publication
  directory flush, link publication, temporary cleanup/rollback, and
  post-publication directory flush, with absent, rolled-back, indeterminate, or
  published-but-durability-unconfirmed outcomes reported truthfully.

The combined successor suite passed 243 cases:

```text
uv run pytest -q tests/vellis/test_domain_v2.py \
  tests/vellis/test_canonical_encoding_v2.py tests/vellis/test_storage_v2.py \
  tests/vellis/test_query_v2_successor.py tests/vellis/test_change_draft_v2.py \
  tests/vellis/test_history_recovery_v2.py
```

## Root-cause and subtraction sweep

The sweep enumerated every successor activity append site rather than sampling one
capability. It corrected the shared issues once: semantic detail belongs in the
payload relation, verbose detail is mode-gated, rejected mutations retain the
complete request, validation retains complete findings, history never recursively
copies returned entries in either mode, and public discriminators survive
normalization. Every accepted canonical-mutation append site (`rtg_change`,
`rtg_draft_activate`, and `restore`) now derives deterministic affected type-key
and UUID arrays plus resulting revision from the canonical record; no accepted
mutation request is duplicated into semantic activity.

Both history ledgers and both range families were inventoried. Sequence ranges use
their integer primary-key order after arbitrary-size bounds are clamped in Python.
Time ranges use tuple bounds on recorded seconds/nanoseconds and explicitly select
`canonical_record_time_idx` or `activity_time_idx`; the final result remains in
ledger order and retains the maximum-plus-one complete-or-reject rule. EXPLAIN
evidence after a growing excluded prefix rejects a primary-key prefix scan.

Every finding write in `audit.py`, search-only `audit_observability.py`, and
`audit_governance.py` receives the same `_FindingCategories` accumulator created
at the audit root. Its append operation retains each fixed category once while
row scans continue, so repeated corrupt rows cannot grow Python retention. Dynamic
messages are limited to the fixed relation/scope catalogs or the single terminating
decode exception. Activity and validation sequence/head/time/revision/JSON/domain
checks now have exactly one authority and one full scan in `audit_governance.py`;
the earlier weaker duplicate scans were deleted from observability. SQL trace
evidence asserts one activity scan and one validation-run scan.

Backup and setup-from-backup share one publication state machine: failures through
copy audit, file/directory flush, or link publication leave no destination;
temporary cleanup failure either rolls the link back or reports an indeterminate
published destination; post-publication directory-fsync failure leaves the audited
destination in place and raises an explicit published-but-durability-unconfirmed
error. No path claims rollback after publication.

Audit does not trust search-document counts or the external-content FTS view. It
rebuilds a connection-local FTS vocabulary from versioned source content and
compares terms to the stored FTS vocabulary. Restore serializes its full result
before activity/commit and streams descriptor members through connection-local SQL.

### Bounded-materialization inventory

- History's two `fetchall` calls are deliberately retained output shape, limited in
  SQL to `maximumRecords + 1`, therefore at most 1,001 rows. Their tuples are the
  requested complete-or-rejected public result, not excluded population. Time
  selection begins at its indexed lower bound rather than scanning an excluded
  sequence prefix.
- Restore retains one selected/current definition or graph object at a time. A
  single object's associations/properties or a single definition's members are the
  record being validated. Population-sized key differences and canonical hash
  members remain in `restore_definition_key`, `restore_graph_key`, and
  `restore_descriptor` temporary relations and are streamed in key order.
- State-wide validation iterates definition keys, graph UUIDs, and cardinality
  subjects. Its only sets/tuples contain the direct references or type keys of one
  definition/object. Cardinality counts stream one subject row at a time and use
  Python integer comparison so modeled unbounded naturals never enter SQLite
  INTEGER parameters.
- Audit streams canonical records, storage-shape rows, timestamp rows, activity,
  validation findings, and every raw/decoded version descriptor. The scalable
  descriptor comparison is the temporary `audit_descriptor` relation; search/FTS
  equivalence uses temporary SQL projections. Python retains one row/record and a
  fixed-category finding set. It never loads a complete historical state.
- Backup uses SQLite's online page-copy API and then the same bounded audit. It
  retains no graph, history, activity, validation, search, or backup population in
  Python.
- Canonical/public JSON payloads are serialized purpose-required records, not a
  second internal state projection. Audit validates affected-key JSON through
  SQLite `json_each`/set comparison without decoding the complete arrays in Python.

### Governance storage-invariant inventory

- `draft_metadata`: singleton presence, nonempty-draft correspondence, exact
  streamed fingerprint, paired inspect-cursor fields, 32-byte cursor hash, exact
  cursor-state shape, selected revision, bounds, canonical UUID filters, and
  current fingerprint.
- `draft_definition_entry`: keyed replace/remove operation, removal child absence,
  complete replacement decoding, permanent type-key kind agreement, and
  structurally kind-compatible permitted/property members. Audit does not require
  the proposal itself to conform.
- `draft_definition_permitted_type`: definition parent and role vocabulary
  compatible with the definition kind; empty permitted sets remain valid draft
  storage and are findings only when the effective proposal is validated.
- `draft_property_definition_entry`: associated-data definition parent, Boolean
  flags, typed bounds, natural text, and property-definition decoding.
- `draft_property_definition_allowed_value`: property parent, contiguous ordinals,
  and typed scalar decoding. A scalar kind that differs from the proposed property
  kind remains decodable draft content and is owned by proposal validation.
- `draft_graph_object_patch`: canonical UUID/kind, permanent UUID-kind agreement,
  exact presence flags, kind-compatible structural fields, tombstone emptiness,
  and mechanically constructible upsert fields without requiring proposal
  conformance.
- `draft_association_operation`: associated-data patch parent, canonical anchor
  UUID, base/add/remove operation, and complete-base consistency.
- `draft_property_operation`: associated-data patch parent, nonempty property key,
  exact `set`/`remove` vocabulary and shape, null distinction, and typed scalar
  decoding.
- `activity_header`/`activity_payload`: exact one-to-one correspondence, contiguous
  ledger/head/time checks, canonical timestamps, known optional revisions,
  nonempty capability/initiator/summary, outcome enum, required semantic JSON
  object with finite values, and optional finite verbose JSON, reconstructed as
  `ActivityHistoryEntry`.
- `metadata_setting.activity_mode`: exactly `semantic` or `verbose`; invalid stored
  configuration makes audit and copied-backup publication fail.
- `validation_run`/`validation_finding`: known scope/revision, exact nonnegative
  total, contiguous ordinals, cursor hash/page/offset bounds, current/draft field
  separation, applicable fingerprint/raw/effective count agreement, and every
  finding reconstructed as a normalized domain `Finding` with canonical UUIDs.
- Draft absence implies no rows in any of the seven draft child/entry relations and
  no draft validation backing. All checks stream one entry/finding at a time or use
  scalar SQL existence/count queries.

The audit module crossed the 800-line subtraction trigger during implementation;
search/FTS projection checks are now a cohesive 87-line companion and the sole
activity/validation/draft governance authority is a 619-line companion, leaving
`audit.py` at 695 lines. New Phase 5 orchestration modules remain below the trigger;
bounded state validation is 197 lines and `database.py` is a 783-line catalog-like
schema declaration. The immediate subtraction review also split the reported
953-line Phase 3 read orchestrator by current semantic responsibility:
`discovery_operations.py` owns shallow/focused definition discovery in 420 lines,
while `read_operations.py` owns graph query in 598 lines. Call sites import the
responsible module directly; there is no forwarding compatibility layer. All new
or rewritten production functions pass C901 at 10 or below.

## Predecessor reachability and subtraction

The predecessor adapter remains reachable from `mcp.py`, `__main__.py`, `setup.py`,
and `system.py`; those paths still import the replay store, NDJSON snapshot/tail,
legacy restore, and `preserve`. The directly implicated predecessor modules total
14,077 lines. Removing them in W005 would break the only runnable adapter before
W007 publishes the successor MCP/CLI boundary. Therefore `F006` remains truthfully
`conflicting` and moves with F002/F003/F004 to W008, where reachability and residue
can be deleted together. W005 and D006 cover the complete successor recovery
behavior and do not reuse any replay/snapshot implementation.

## Evidence status

Implementation status intended for review: `W005` and `D006` conforming. `F006`
remains open at `W008` solely for predecessor reachability/subtraction. Focused
tests, C901, lint, typecheck, model/reference checks, evolution validation, and diff
checking produced:

```text
Phase 5 focused tests       91 passed
combined successor tests   243 passed
changed successor C901     passed (maximum 10, no exemptions)
just typecheck             passed (0 errors, 0 warnings)
just lint                  passed
just model-check           passed
just model-reference-check passed
just system-evolution-check passed
git diff --check           passed
```
