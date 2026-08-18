# Semantic Work-Locality Implementation Handoff

This is the durable execution handoff for evolution `vellis-2-semantic-work-locality`. Product
meaning remains authoritative in `model/`; `system-evolution.yaml` owns lifecycle and evidence.
This document records selected realization, deletion, and verification work so a cold agent can
resume W002–W005 without reconstructing decisions from a conversation.

The proposed authority baseline is model digest
`sha256:a7e08c7ae2c82ee3f78d1d1fc4cc6e525026bdef682ceadb7369fcb7b93463d4`.
Implementation must not begin until the owner accepts the exact checkpoint recorded in the
evolution record. This is a prerelease schema break, not a compatibility-middleware campaign.

## Completion boundary

The completed evolution has one production query path and one active/prospective invariant-impact
kernel. Queries restrict relational identities, express hidden branches existentially, bound
distinct answer identities, then hydrate or aggregate. Mutation work is derived from exact
old/proposed reasons and deduplicated by `(rule_key, subject_uuid, constrained_end)`. Canonical JSON
collection operations are linear in supplied members. SQLite capacity is derived from compiled
statements. No dormant fallback retains the old algorithms.

Legitimate work may still scale with selected candidates, matching edges, genuine projected
combinations, exact affected subjects, changed-rule populations, historical replay, and explicit
complete assessment. It must not scale with disconnected populations, hidden witness products,
unrelated rules, far endpoints promoted only because a relationship was inspected, collection
placeholder counts, or parallel capacity formulas.

## W002 — canonical JSON collection equality

Add one internal immutable, recursively hashable equality key in `vellis/json_value.py`:

- null: a kind-tagged singleton;
- Boolean: kind tagged and distinct from numbers;
- number: kind-tagged exact `Decimal`, preserving `1 == 1.0` and exact signed-zero equality;
- string: exact Unicode without normalization;
- array: kind-tagged ordered tuple of member keys;
- object: kind-tagged tuple of exact-name/key pairs sorted by property name.

Inputs have already passed existing normalization. Do not make serialization or a digest equality
authority. Replace permitted-value uniqueness and membership scans with set operations, and use
counters where duplicate multiplicity affects unordered canonical comparison. Do not change
persisted identities, ledger hashes, snapshots, serialization, ordering, or missing/null meaning.

Evidence must cover numeric spelling equivalence, Boolean/number distinction, object-key order,
array order, nested values, counter multiplicity, unchanged snapshot/canonical fixtures, and the
500–8,000 member series with one key construction per input and no pairwise `json_equal` calls.

## W003 — query contract and single SQLite path

### Public contract and analyzer

Implement the accepted `GraphQuery` contract directly. Do not translate the old request shape.
Update query, definition-summary, and definition-inspection state inputs to the tagged selection
family. Preserve the ten MCP tool names while regenerating typed schemas.

`vellis/query.py` owns public immutable values and one pure analyzer. `AnalyzedGraphQuery` contains:

- validated selector lookup and references;
- connected-tree adjacency and a compilation orientation;
- projection-to-selector mapping and aggregate target;
- visible selector and projected-link sets;
- the minimal answer-relevant backbone;
- hidden branch attachment roots;
- referenced type/property keys; and
- ordered output identity columns.

The analyzer accesses no database, candidates, indexes, or graph objects. It does not split
components, translate legacy shapes, or evaluate the query. State-dependent UUID existence/kind/type
validation occurs relationally after filter population.

### State context

Resolve selection once in `store.py` into a private immutable context containing semantic kind,
evaluated revision, object and association relation descriptions, definition source, exact
historical predicates/parameters, and prospective-delta presence. The compiler receives this
context and must not rediscover state independently. Summary and inspection reuse the resolver but
retain focused retrieval. Current/prospective report the current canonical revision; historical
reports the resolved revision; rejection/failure reports none.

### Unified collection relation

Create one connection-local temporary `query_selector_member` relation:

```sql
query_selector_member(
    member_kind TEXT NOT NULL,
    selector_name TEXT NOT NULL,
    value TEXT NOT NULL,
    PRIMARY KEY(member_kind, selector_name, value)
) WITHOUT ROWID
```

Member kinds cover anchor types, anchor UUIDs, associated-data UUIDs, link UUIDs, and aggregate
properties when needed. Create once, clear inside each query transaction, populate with
`executemany`, use indexed membership, and clear on success. Rollback plus defensive clearing handles
failure. Never interpolate public collection lengths into placeholder lists. Delete the specialized
filter tables and small/large-list branch.

### Compiler and answer backbone

Add `vellis/sqlite_query.py`. `CompiledQuery` owns ordered statements, exact ordered parameters for
each statement, per-`SELECT` table counts, selected-column counts, generated expression/subquery
depth, identity/hydration columns, output bound and kind, and cleanup needs. Compilation and
preflight finish before answer SQL executes.

For row output:

1. A selector is visible when directly projected or supplying a projected property; a required-link
   edge is visible when the link is projected.
2. Compute the minimal connected subtree joining all visible vertices and projected link edges.
3. Join only this backbone. A hidden branch becomes a correlated `EXISTS` rooted at its attachment.
4. A hidden connector between visible selectors may be traversed, but its identity is absent from
   the row key.
5. Insert ordered projected identities into a query-specific temporary answer table with a primary
   key, stopping at `maximum_rows + 1` distinct identities.
6. Reject whole when over bound; otherwise hydrate projected identities only.

Identity includes projection name plus anchor/link/data UUID. A property identity includes
projection name, source associated-data UUID, presence, and canonical value. Equal values from
different sources remain distinct; hidden witnesses do not distinguish rows.

For aggregate output, the named data condition is the sole visible selector. Populate one temporary
target table keyed by its data UUID with every other branch existential, stopping at
`maximum_matches + 1`. Reject before arithmetic when over bound. Count the target table and stream
requested property rows through existing exact reducers. Retain sparse SQLite-backed exact-sum
terms. There is no per-target loop because one request has one target population.

SQLite may push any selective type, UUID, association, link, or property predicate. The semantic
constraint is elimination of forbidden logical witness products, not a prescribed physical order.

### Exact capacity

Preflight actual compiled statements and parameter sequences against variable, result-column,
table-per-scope, expression/subquery-depth, and integer-limit capacities. Historical predicates and
answer `LIMIT` bindings are present automatically. Delete hand-maintained field-count estimates.
Capacity excess is a typed whole-result rejection before answer execution.

### Oracle and integration

Rewrite `tests/vellis/oracle.py` as small brute-force tree semantics importing only public graph and
query values. It independently implements row identity, recursive JSON comparison, and aggregate
reduction; it imports no production analyzer, planner, evaluator, identity, or reducer. Add fixed-seed
generated connected-tree cases and prove a deliberately mutated production result is detected.

`store.py` retains locking, transaction/state ownership, hydration, complete-return screening, and
error translation. `system.py` owns dispatch/observation. `mcp.py` exposes generated schemas and the
unchanged `rtg_query` name. Do not add a modeled subsystem or persistent migration. If existing
indexes plus temporary relations cannot achieve locality, stop W003 with exact `EXPLAIN QUERY PLAN`
and VM-step evidence instead of changing schema speculatively.

### W003 deletion inventory

Delete, not merely bypass:

- `QueryCandidateIndex`, `evaluate_indexed_query`, `_Assignment`, `_walk`, `_assignments`;
- `_component_assignments`, `_distinct_component_assignments`, `_selector_components`;
- both `_component_query` implementations, `_query_component_names`, and component reconstruction;
- recursive SQL `validate=False` / `existence_only=True` paths and disconnected existence gates;
- `_SQLiteQueryIndex`, `_query_requires_relational_filters_unlocked`, and manual capacity formulas;
- specialized query filter tables, conditional `IN (...)` collection compilation, and Python
  post-hydration deduplication;
- multi-target aggregation loops and `maximum_aggregation_batch_rows` /
  `maximum_aggregation_reducer_count`;
- `ReturnShape`, `EvaluatedStateScope`, `AnchorUuidFilter`, `LinkUuidFilter`, old root query fields,
  per-aggregation target, query/inspection `selection=` overloads, legacy anchor spelling middleware,
  and its registration/tests.

Retain complete-return text screening, rewritten independently of the assignment evaluator.

## W004 — exact active/prospective mutation impact

Keep four transient roles separate: changed objects, structural validation subjects, multiplicity
impact reasons, and lookup-only identities. Both active and prospective validation expose old and
proposed object membership, endpoint/link facts, direct associations, affected type definitions,
and rule participation. Prospective compares current with the sole proposal. Active builds a
noncanonical transient overlay and must not touch that proposal.

Use a temporary reason relation equivalent to:

```sql
multiplicity_impact_reason(
    rule_key TEXT NOT NULL,
    subject_uuid TEXT NOT NULL,
    constrained_end TEXT NOT NULL,
    reason_kind TEXT NOT NULL,
    PRIMARY KEY(rule_key, subject_uuid, constrained_end, reason_kind)
) WITHOUT ROWID
```

The closed reason kinds are `relationshipMembershipChanged`, `subjectMembershipChanged`,
`oppositeMembershipChanged`, and `ruleMeaningChanged`. `multiplicity_work` is the distinct first
three columns. Do not create a generic event/rule engine.

For link rules, enqueue old/new constrained endpoints only where link type/endpoints and endpoint
membership change applicability. A constrained participant type change enqueues that participant
only when membership differs. An opposite-end type change examines incident links of the exact link
type and enqueues only their constrained endpoints whose eligibility changed. The changed opposite
participant is lookup-only unless another exact reason makes it a subject. A rule-meaning change may
enqueue every old/proposed subject of that exact rule/end. Description-only rule edits enqueue none.

For direct-association rules, association insertion/removal/anchor-set change enqueues exact old/new
anchors for anchor-constrained rules and the data object for data-constrained rules. Subject type
changes enqueue that subject when membership differs. Opposite type changes enqueue directly
associated constrained subjects whose eligibility changes. Rule meaning may expand only over that
exact rule. Display/property-only changes enqueue no multiplicity work.

Structural validation is separate and remains complete: endpoint type changes may recheck incident
link objects; removals must detect dangling links/associations; exact type-definition changes may
recheck all objects of that type. Relationship objects are subjects and unchanged endpoints are
lookup-only. No cascade is introduced. Explicit complete assessment and exact changed-rule/type
populations may legitimately be state-wide, set-based, and bounded in process memory.

### W004 phases and deletion

1. Add changed-object, structural-subject, reason, exact-work, and lookup relations plus rolled-back
   tests that inspect exact tuples.
2. Port prospective multiplicity to exact work while keeping definition dependency validation
   separate; prove display/property/description-only zero work.
3. Normalize active changes into the transient overlay and reuse the kernel while preserving command
   conflicts, unknown removal, no cascade, atomic rejection, no-op detection, and concurrency checks.
4. Compare active/prospective findings with complete small-state assessment oracles, then delete
   `_affected_participants_unlocked`, `_incident_relationship_uuids_unlocked`, far-end promotion,
   impacted-type rule triggers, participant-by-rule products, duplicated active calculation, and
   proposal tables/branches used only by the superseded expansion. Retain bounded referencing lookup
   only for structural dangling-reference checks.

## Verification matrix

Query evidence covers broad/multi-type and UUID-restricted anchors; UUID restrictions for all three
object kinds; mixed known/unknown and wrong-kind/type refusal; data association and property
comparisons; missing versus null; directed links; paths/stars/branching trees; hidden branches;
projected links; same-object aliases; source-preserving equal property values; genuine projected
combinations; bound-plus-one refusal; unreturnable encoding; and declaration-order invariance.

Invalidity evidence covers empty/duplicate names, unknown references/types, empty/duplicate UUID
filters, disconnected branches, self/parallel edges, direct-association parallel edges, longer
cycles, empty outputs/aggregations, bad aggregate target/property/operator, nonpositive bounds,
prospective without delta, unknown revision, naive time, and structural SQLite excess. Every refusal
preserves graph, definitions, delta, revision, and canonical history and returns no partial answer or
evaluated revision.

Aggregation evidence covers zero/nonzero count, exact and cancelling sums, numeric/string extrema,
missing/all-missing properties, several operations/properties on one target, hidden witness
deduplication, equal-valued distinct targets, bound-plus-one, and all four state selections.

Differential generation uses fixed-seed small connected trees with sparse/dense links, missing/null
properties, duplicate values/witnesses, and alias reuse. Compare status, revision, canonical row
identity, returned values, aggregates, and refusal. Metamorphic cases reorder declarations, rename
aliases, duplicate hidden witnesses, add unrelated population, substitute equivalent revision state,
change multiplicity-irrelevant display/property data, and permute semantically equal object members.

Scaling evidence uses SQLite VM steps and decoded-object counts, not wall-clock budgets:

- hidden query witness fanout 10/20/40 keeps rows/decodes fixed and doubling ratio below three;
- genuine projected combinations grow only as answer mathematics requires and refuse at the bound;
- unrelated populations leave results/decodes fixed with indexed lookup plans;
- aggregate hidden witnesses leave target count fixed;
- active hub-of-hubs 10/20/40 has exact work proportional to applicable degree and ratios below three;
- display-only edits across 10/100/500/1,000 irrelevant rules produce zero multiplicity work;
- K independent changes/rules at 5/10/20/40 produce K exact tuples, not K squared;
- changed rules expand only over their applicable subjects; complete assessment remains explicitly
  state-wide with bounded process materialization.

MCP evidence keeps exactly ten tool names, exposes output/state discriminators, rejects rather than
translates every removed shape, distinguishes typed semantic refusal from malformed boundary input,
opens existing databases without migration, and keeps snapshot/replay/restore/restart/v1 evidence
green.

## W005 closure and subtraction

Run the documentation-sync workflow and reconcile `model/README.md`, `README.md`,
`docs/mcp-realization.md`, examples, and test descriptions with implemented truth. Remove obsolete
workaround prose rather than memorializing it. Search model, source, tests, README, and docs for every
deleted name and inverse claim. The transitional trigger file
`tests/vellis/test_semantic_work_locality_triggers.py` is replaced by target conformance/scaling
evidence and deleted because it asserts superseded source shape and exact conflicting costs.

Confirm persistent schema/version and snapshot fixtures did not change and exactly ten MCP names
remain. Run focused query/equality/mutation tests, `just model-check`,
`just system-evolution-check`, `just package-check`, `just check`, and `git diff --check`. Freeze one
token and obtain fresh authority/conformance and engineering/evidence reviews at that same token.
Only deterministic evolution bookkeeping may follow a clean pair; commit and independently validate
the committed checkpoint.

## Resume and change control

At every resumed turn, confirm path/status/worktrees, validate the evolution record, confirm the sole
active work item/checkpoint, recompute the relevant baseline, reconcile all changes, and reread the
work item's qualified authority and current model diff. New evidence becomes a finding when it has an
independent consequence. Widen an item only when authority, approval, outcome, and review surface are
unchanged; otherwise add a dependent item or stop for model acceptance. Sweep a root cause before
review. Do not add an optimizer, runtime-selectable planner, fallback evaluator, generic rule engine,
persistent cache/view, schema migration, new public tool, or new authorization/session/worker concept.

The evolution intentionally removes atomic single-query disconnected, cyclic, mixed-output, and
multi-target aggregate questions and changes prerelease request schemas/property row identity. It
does not change graph/type meaning, direct associations, link meaning, property comparison,
persistence/history/snapshots/restore/v1 initialization, tool names, launch/registration, approval,
or canonical mutation boundaries.
