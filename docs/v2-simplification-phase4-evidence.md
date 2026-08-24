# Vellis v2 simplification — Phase 4 evidence

## Candidate scope

Work item `W004` implements active field-level graph changes and the single durable draft through
validation, activation, and discard. The qualified authority is `model/10-rtg-domain.sysml` graph
change/draft/outcome meaning, the corresponding use cases in `model/20-rtg-system.sysml`,
requirements RTG007–RTG009 and locality in `model/40-requirements.sysml`, and the three focused
verifications in `model/50-verification.sysml`. Phase 5 ledger/history behavior and Phase 7 MCP/CLI
adapters remain outside this slice.

## Phase conformance matrix

| Concern | In-scope obligation | Required non-effect | Nearest plausible wrong implementation | Focused evidence |
|---|---|---|---|---|
| Active change | Expected-revision, bounded creates/patches/removals compose against one final state; unnamed fields survive; absence operations are idempotent | No cascade, complete-object replacement, command-order meaning, or whole-state validation | A patch reconstructs an incomplete object and loses unseen content, or removal silently cascades | One-field preservation, permutations, dependent removal/repoint, stale/no-op, locality instrumentation |
| Draft storage | One normalized entry per key; complete definition replacement and field-level object operations merge with later-field wins | No system metadata, public version/digest/status, edit log, or canonical revision | Proposal lifecycle returns under draft names, or live writes rewrite staged entries | Repeated staging, tombstone/upsert/unstage, live changes under staged fields, raw/effective counts |
| Draft reads | Latest live content is mechanically overlaid; staged fields win and unrelated live fields follow current | No snapshot base or fictional in-flight object metadata | Draft freezes its base revision or invents `createdRevision` for draft-only additions | Draft query/discovery after live writes, missing-base partial/full patches, metadata checks |
| Validation | Fresh current/draft assessment computes deterministic complete findings once; continuation pages latest backing | No assessment identity or authorization token | Validation status becomes persistent public lifecycle authority | Paging, repair/revalidate, scope/content expiry, non-clean accepted result |
| Activation/discard | Activation recomposes latest state, fully validates, publishes one revision or clears redundant draft; discard is noncanonical | No prior validation authority, stale activation, or metadata on delta rows | Activation applies an old assessment or modifies live state on rejection | Invalid preservation, effective/redundant activation, ordinary canonical envelope rules, discard no-op |
| Transactions | Each operation owns one connection and response serialization precedes commit | No shared connection, surviving temporary population, or false rollback claim | Concurrent operations share state or a post-commit failure is reported as rollback | Failure injection, two-connection contention, close/rollback checks |

## Selected inherited realization

- Reuse the single `resolve_state` and `load_definitions` paths and the existing VEL2 version tables.
- Use the already selected normalized draft and validation relations; add no logical relation.
- Keep draft entries free of system-envelope columns. Live-backed effective objects retain their live
  envelope, draft-only additions/reactivations expose none, and activation assigns canonical
  metadata exactly as an equivalent active change.
- Ordinary active validation loads only commanded identities, direct dependents, affected endpoints,
  old/new types, and cardinality subjects. Full validation and activation may stream the full state.
- Use small immutable domain requests/results and explicit connection-local repository and operation
  functions. Do not introduce a store/service class, generic patch engine, event bus, or cursor
  framework.

## Intended implementation and subtraction

The implementation touches the existing graph/definition version relations, draft relations,
validation backing, search projection, canonical record, metadata head, and the activity seam needed
for atomic observability. Public operation boundaries added in this phase are active change, draft
change/inspect, validation, activation, and discard, plus draft state support in existing discovery
and query operations.

Phase 4 implements the successor semantic service path. It does not remove the predecessor public
adapter that remains the repository's runnable boundary. W008 owns removal of that reachable
complete-object, proposal-version, assessment-identity, conflict-list, and canonical-proposal stack
after the selected adapter replacement, together with any residual campaign subtraction.

## Evidence status

### Mandatory pair-three root-cause audit

The third consecutive non-clean Phase 4 review pair triggered the required bounded root-cause
audit. The pre-correction inventory found these complete-population memory risks:

- `draft_repository.draft_fingerprint` fetched every row from seven accumulated-draft relations,
  built one `Record` per row and one complete `OrderedValues` value, then encoded the whole value.
- `draft_analysis.draft_counts` collected every staged definition key and UUID, loaded every staged
  current/proposed value, and built complete keyed maps and semantic-difference tuples.
- `draft_inspection_operations._entries` did the same complete accumulated-draft load before
  filtering and paging; `_fresh` and `_continue` also retained the complete entry tuple.
- `effective_validation._effective_definition_keys` converted the complete effective-definition
  key cursor to a tuple. Validation findings themselves were already streamed into the existing
  temporary/persistent paging backing; only the bounded public page was retained in Python.
- `draft_operations.activate_draft` collected every staged key, current/proposed value, changed
  definition/object, affected-key summary, and introduced/retired row descriptor. Repository
  insertion and closure helpers likewise returned descriptor tuples for the whole activation.
- `read_operations` draft identity/query paths were request-bounded, but draft type summary could
  collect the complete anchor-key population before enforcing the public limit. Focused inspection
  was request-bounded. Pattern matching already established `maximumMatches + 1` in SQL before
  bounded hydration. Complete `read_state(DraftState)` remains an explicitly complete internal
  state read and is not used by ordinary discovery, query, inspection, counting, validation, or
  activation.
- Per-object association/property `fetchall` sites scale only with the one selected object;
  response construction sites scale only with an already-enforced public page or request bound.
  Active-change closure sets scale with the at-most-1,000 request plus exact affected dependents and
  cardinality subjects, not the complete graph.

The absent-base associated-data audit found three coupled decisions: `_overlay_data` treated a
nonempty result made only from `addAnchorUuids` as complete; the temporary SQL overlay admitted an
absent associated-data row when either a `base` or `add` association existed; and validation/query
used absence from that view as the unmaterializable signal. The selector audit found that
unmaterializable matching considered kind, UUID, and a staged type key, but ignored conclusively
staged display-name and property predicates. The corrections below make explicit complete
`anchorUuids` the only base-independent associated-data creation shape, evaluate every staged
selector fact that is actually known without inventing missing values, and replace complete draft
and descriptor accumulators with ordered SQL cursors, bounded batches, and connection-local
working relations.

After correction, no ordinary Phase 4 discovery, query, draft inspection, draft counting,
validation, or activation path retains a complete definition population, graph population,
accumulated draft, finding population, or canonical descriptor population in Python. The remaining
size-scaling shapes are intentional and bounded as follows:

- `operations.read_state(DraftState)` still returns one explicitly complete internal state and is
  the sole caller that invokes `load_draft_definitions`/`load_draft_graph` without selected keys.
- `load_draft_definitions` and `load_draft_graph` retain keyed `fetchall`/tuple construction for one
  public request selection, one inspection entry, one validation object, or one activation key;
  their child member loads scale with that one definition/object, not the complete system.
- Type summary counts before loading and retains at most the public limit. Focused inspection and
  query retain only the requested selectors, selected neighborhood/result, or one streamed
  compatible relationship-definition witness. A complete focused neighborhood is itself the
  selected public response, not an unrelated population accumulator.
- Draft inspection selects `limit + 1` keys in SQL before keyed composition. Validation persists
  all findings in the existing paging backing while retaining only the requested page. Continuation
  `fetchall` sites are SQL-limited to that page.
- Draft fingerprinting makes two canonically ordered cursor passes and encodes one row at a time.
  Counts and activation iterate one staged key at a time. Canonical introduced/retired members are
  ordered in a connection-local temporary relation and streamed into SHA-256 with the exact frozen
  framing; affected-key JSON is generated directly inside SQLite.
- Unmaterializable pattern candidates are read as an ordered cursor and discarded one at a time;
  only conclusively staged selector facts can exclude one. Pattern bindings remain SQL-bounded to
  `maximumMatches + 1` before hydration.
- Active mutation request lists, semantic closure sets, result rows, activity request keys, and
  response tuples remain bounded by the public request/page limit or the exact affected dependency
  closure. They are not complete-state accumulators.

Implementation candidate evidence currently includes:

- `tests/vellis/test_change_draft_v2.py`: 57 focused tests covering field preservation, null versus
  absence, no cascade, final-state permutations, stale and no-op behavior, affected-closure
  locality, independent concurrent connections, transaction rollback, metadata-free draft objects,
  historical reactivation metadata, draft-only add/remove tombstones across every object kind,
  staged-field merge/tombstone/unstage behavior, complete raw definition replacements and precise
  raw object operations, inspection and
  validation paging/expiry, activation outcomes, discard, draft discovery/query, structurally
  staged untyped null and absent-base patches, potential pattern selectors, rollback at every draft
  activity boundary, post-commit response loss, complete-anchor-base materializability, conclusive
  staged predicate filtering, guarded streaming of accumulated draft and descriptor state, and
  over-limit draft-summary refusal before definition hydration, effective-key summary replacement
  at the 1,000-item boundary, and focused-neighborhood exclusion of superseded live definition
  members, and non-ASCII opaque inspection/current-validation/draft-validation cursors producing
  ordinary `expiredCursor` results rather than runtime encoding failures. Table-driven parity
  evidence runs wrong UUID kinds, typed and untyped link compatibility, direct-association
  compatibility, and valid patterns against current and equivalent effective-draft state. Separate
  tables cover staged null and unstaged-property uncertainty across presence, equality, ordering,
  and `anyOf` operators.
- Pattern-preflight locality evidence surrounds one typed node with 240 live/staged data and link
  definitions that permit its type and proves none are loaded without a relationship selector.
  Actual untyped link and direct-association selectors load one compatible definition witness at a
  time in current and effective-draft state; incompatible endpoint combinations reject after the
  same streamed, nonaccumulating scan.
- Untyped full-text property predicates, unknown properties, and unknown types reject with
  current/draft finding parity before the draft graph, property, or search overlay is installed.
- The current/draft identity route matrix rejects duplicate identities, duplicate properties, and
  property-on-anchor requests before object-value loading; missing identities skip property
  validation, valid identities remain accepted, and current/draft pattern result limits agree.
- Active locality evidence includes forty unrelated anchors of the same type and instruments every
  selected graph-object load; the changed anchor loads only its direct dependents, referents, and
  exact count-changing subjects rather than that unrelated population.
- Draft change, raw inspection, effective counts, identity query, type summary, and focused type
  inspection now select only their draft keys and relevant live identities rather than materializing
  unrelated current graph/definition populations.
- Draft pattern evaluation uses connection-local normalized SQL overlay views and the Phase 3
  compiler, establishing `maximumMatches + 1` in SQL before hydration. Full current/draft validation
  streams definition identities and graph UUIDs in batches, loads only direct referents, computes
  cardinality in SQL, and orders/stores findings through a temporary work relation. Activation
  validates that same overlay and publishes only the bounded staged keys.
- Full-text draft overlay materializes only the node kind/type/UUID/field scopes named by structured
  full-text predicates; non-full-text queries create no temporary search population. A staged,
  diacritic-bearing text phrase is found through the effective FTS relation.
- Current and draft pattern routing now share one state-dependent semantic preflight over selected
  headers and effective definitions before either compiler path runs.
- The successor domain/storage/query/change suite passes 152 tests together.
- Ruff lint and the C901 ≤10 check pass for every new or rewritten successor production file;
  Pyright reports no errors.
- `git diff --check` passes.

The primary manager independently reruns project gates, records durable evolution statuses, freezes
the exact candidate, and obtains the required review pair. The bounded subtraction pass separated
draft-overlay query evaluation and raw draft inspection at their existing semantic boundaries.
Current physical/logical line counts are: `read_operations.py` 850/791,
`draft_operations.py` 632/593, `draft_activation.py` 290/256,
`draft_inspection_operations.py` 394/369, `draft_read_operations.py` 393/351,
`effective_validation.py` 252/219, `draft_analysis.py` 59/49, and
`draft_sql_overlay.py` 198/185. Every orchestration module
remains below the 800-logical-line trigger and every production function remains within C901 10.

The predecessor complete-object/proposal/assessment stack remains reachable from the current public
adapter: `vellis/mcp.py` imports `vellis.changes`, `vellis.governance`, and `vellis.store`, while
`vellis/__main__.py` and `vellis/setup.py` still enter `vellis.store` and snapshot/import behavior.
Deleting those paths in Phase 4 would break the only runnable adapter before its Phase 7 replacement.
Their findings therefore remain implementation work; Phase 7 removes the adapter reachability and
Phase 8 deletes any residue rather than treating the Phase 4 successor as proof they are already gone.
The directly reachable predecessor production files (`changes.py`, `governance.py`, `store.py`,
`canonical.py`, `streaming.py`, `normalized.py`, and `validation.py`) currently total 11,971 physical
lines. Four clearly superseded semantic test files total another 5,158 lines; the broader
proposal/assessment/change grep inventory is 17,522 test lines. These are backlog measurements, not
authority or permission to delete the still-runnable adapter path in Phase 4.

## Implemented distinction

The successor path now applies graph changes as bounded field patches over one final state and owns
one connection and transaction per operation. It stores a single normalized, metadata-free draft
bucket, dynamically overlays that bucket on the latest live definitions and graph, pages raw
inspection and current findings without public assessment identities, and revalidates on activation.
Canonical object and definition envelopes are created or updated only when an effective active
change or activation publishes a revision. Redundant accepted work records activity without
creating canonical history.

The remaining predecessor adapter still exposes the obsolete implementation until the selected MCP
and CLI boundary is replaced. Findings F003 and F004 therefore move to W008 for final subtraction;
their status is not inferred from the completed successor service path.
