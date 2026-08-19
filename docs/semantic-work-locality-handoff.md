# Semantic Work-Locality Implementation Handoff

This is the durable execution handoff for evolution `vellis-2-semantic-work-locality`. Product
meaning remains authoritative in `model/`; `system-evolution.yaml` owns lifecycle and evidence.
This document records selected realization, deletion, and verification work so a cold agent can
resume W002–W006 without reconstructing decisions from a conversation.

The proposed authority baseline is model digest
`sha256:5ce0b4cbcc0785f57980d709bf903717f3323ef116f40a9f58737e6f06ac9240`.
Implementation must not begin until the owner accepts the exact checkpoint recorded in the
evolution record. This is a prerelease schema break, not a compatibility-middleware campaign.

## Completion boundary

The completed evolution has one production query path and one active/prospective invariant-impact
kernel. Queries restrict relational identities, express unreturned variables existentially, bound
distinct answer identities, then hydrate or aggregate. Mutation work is derived from exact
old/proposed reasons and deduplicated by `(rule_key, subject_uuid, constrained_end)`. Canonical JSON
collection operations are linear in supplied members. SQLite capacity is derived from compiled
statements. No dormant fallback retains the old algorithms.

Legitimate work may still scale with selected candidates, matching predicates, candidate bindings
needed to establish a conjunction, genuine projected
combinations, exact affected subjects, changed-rule populations, historical replay, and explicit
complete assessment. It must not scale with unstated or unrelated graph populations, hidden witness products,
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

The selected prerelease Python contract is exact realization guidance rather than SysML authority:

```python
from dataclasses import field
from typing import Annotated

from pydantic import ConfigDict, Field


_CLOSED_REQUEST = ConfigDict(extra="forbid")


@dataclass(frozen=True, slots=True)
class UuidFilter:
    uuids: tuple[str, ...]

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class CurrentSelection:
    kind: Literal["current"]

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class ProspectiveSelection:
    kind: Literal["prospective"]

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class RevisionSelection:
    kind: Literal["revision"]
    revision: int

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class TimeSelection:
    kind: Literal["time"]
    time: datetime

    __pydantic_config__ = _CLOSED_REQUEST


EvaluatedStateSelection = Annotated[
    CurrentSelection | ProspectiveSelection | RevisionSelection | TimeSelection,
    Field(discriminator="kind"),
]
HistoricalSelection = Annotated[
    RevisionSelection | TimeSelection,
    Field(discriminator="kind"),
]


@dataclass(frozen=True, slots=True)
class RowQueryOutput:
    kind: Literal["rows"]
    projections: tuple[ReturnProjection, ...]
    maximum_rows: int

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class QueryAggregation:
    name: str
    operator: AggregationOperator
    property_name: str | None = None

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class AggregateQueryOutput:
    kind: Literal["aggregates"]
    data_condition: str
    aggregations: tuple[QueryAggregation, ...]
    maximum_matches: int

    __pydantic_config__ = _CLOSED_REQUEST


QueryOutput = Annotated[
    RowQueryOutput | AggregateQueryOutput,
    Field(discriminator="kind"),
]


@dataclass(frozen=True, slots=True)
class GraphQuery:
    anchor_groups: tuple[AnchorGroup, ...]
    output: QueryOutput
    required_links: tuple[RequiredLink, ...] = ()
    data_conditions: tuple[AssociatedDataCondition, ...] = ()
    state: EvaluatedStateSelection = field(default_factory=lambda: CurrentSelection(kind="current"))

    __pydantic_config__ = _CLOSED_REQUEST


@dataclass(frozen=True, slots=True)
class ReturnedProperty:
    projection: str
    associated_data_uuid: str
    present: bool
    value: JsonValue = None
```

`PropertyComparison` also adds `MATCHES_PATTERN = "matchesPattern"`. It takes a string expected
value containing a Google RE2 expression and applies Unicode whole-string FullMatch semantics to a
present string property. Malformed or RE2-unsupported expressions, non-string properties, and
non-string expected values are semantic query invalidities. This reuses the installed RE2 boundary;
it does not introduce a textual expression language or make a query predicate part of definition
validity.

An explicitly supplied variant object always carries its discriminator. Omitting the entire
`state` member selects current state, but supplying `{}` does not. Every externally exposed query
request dataclass is closed to additional members at the Pydantic/FastMCP boundary, including the
existing selector, predicate, and projection values as well as the values shown above. The published
schemas contain real discriminators and closed object schemas. Consequently a current variant
carrying `revision`, a revision variant carrying `time`, an untagged explicit variant, a row output
carrying aggregate members, or any object carrying a removed legacy field is malformed input and
forms no domain request. W003 must verify both the generated schemas and real client-boundary
rejection; constructor defaults, union ordering, or ignored extras must not silently choose a
variant, discard contradictory fields, or accept a partly translated old request.

`UuidFilter | None` is used by `AnchorGroup`, `AssociatedDataCondition`, and `RequiredLink`.
`RTGSystem.query_graph`, definition summary, and definition inspection take no separate
`selection=` argument. Restore and other inherently historical operations continue to use
`HistoricalSelection`. Accepted row results populate only `rows`; accepted aggregate results
populate only `aggregates`. Rejected or failed results contain neither, contain no evaluated
revision, and echo the normalized query. Bound or encoding refusal is whole-result refusal.

The query is one finite positive must-exist pattern. Anchor groups and associated-data conditions name
object variables. Each associated-data condition adds its required direct-association predicate, and
each `RequiredLink` names a link variable plus its directed endpoint predicate. Every type, UUID,
association, link, and property predicate must hold under the same joint assignment. The pattern has
no topology restriction: disconnected variables, parallel predicates, a direct association plus a
link over the same aliases, self-links, and cycles are ordinary conjunctions. Different selector or
link aliases may bind the same graph object when their constraints permit it; aliases do not imply
inequality. Projected variables in disconnected portions produce genuine Cartesian combinations,
subject to the result bound. A disconnected portion with no projected variable is one existence gate.

`vellis/query.py` owns public immutable values and one pure analyzer. `AnalyzedGraphQuery` contains:

- validated selector and required-link variable lookup and references;
- projection-to-selector mapping and aggregate target;
- answer variables whose identities distinguish output;
- existential selector and required-link variables;
- each atomic type, UUID, direct-association, property, and link predicate's query-variable signature;
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

Every public operation that resolves state and then executes additional reads does so inside one
explicit SQLite read transaction. Definition summary, focused inspection, and proposal discovery
must not combine a revision/delta header from one committed state with definitions, objects, or a
current assessment from another connection's later commit. W003 adds deterministic two-connection
interleaving evidence for all three discovery paths as well as the four state selections.

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

### Compiler and conjunctive answer relation

Add `vellis/sqlite_query.py`. `CompiledQuery` owns ordered statements, exact ordered parameters for
each statement, each statement's UTF-8 byte length, per-`SELECT` table counts, selected-column
counts, generated expression/subquery depth, identity/hydration columns, output bound and kind, and
cleanup needs. Compilation and preflight finish before answer SQL executes.

Compile the query as one positive conjunction over named identity variables:

Let the logical joint-binding relation be the natural join of the unary candidate predicates and
the direct-association and link predicate relations on their shared named UUID columns. Row answer
identities are the set projection of that relation onto the requested output-identity columns;
aggregate targets are its set projection onto the one target UUID. This is the complete topology-
independent semantic reference. The compiler realizes an equivalent relation with semijoins and
`EXISTS`; it must not materialize the full hidden-witness bag merely to project it away.

1. Each anchor or associated-data selector begins as an indexed candidate UUID relation narrowed by
   its named types and optional UUID members. Property comparisons, including RE2, are unary
   predicates on associated-data candidates; direct associations and required links are relational
   predicates between candidates. Compile their shared UUID columns as semijoins, intersections, or
   equivalent `EXISTS` relations so any selective predicate may reduce candidates and that reduction
   propagates through the conjunction. Do not prescribe whether connectivity or a value predicate is
   physically evaluated first, and do not hydrate objects during this reduction.
2. Each unprojected required-link alias contributes a distinct endpoint-pair relation. Link UUIDs are
   omitted because only existence can affect an answer. A projected link contributes its UUID plus
   its endpoint pair because that UUID distinguishes rows.
3. Direct association contributes an anchor/data UUID-pair relation. Parallel link predicates and a
   direct-association/link pair over the same aliases are ordinary intersections on shared identity
   columns. A self-link predicate restricts its endpoint pair to one bound selector UUID. A cyclic
   pattern closes additional predicates over the same joint assignment.
4. Semijoin candidate UUID relations against incident relationship relations, or use an equivalent
   relational plan, so impossible identities are removed before hydration. Existential variables
   are projected away after all predicates incident to them are satisfied or are evaluated in a
   correlated `EXISTS` over every answer variable on their boundary.
5. Relations that share no variables form a genuine Cartesian product only when both contribute an
   answer identity. A disjoint subpattern with no answer variable is an uncorrelated `EXISTS` gate
   evaluated once. A disjoint subpattern with answer variables contributes its bounded combinations;
   hidden variables within it remain existential.
6. Once one joint hidden assignment establishes existence for an answer identity, do not enumerate,
   count, or materialize additional hidden assignments for that identity. Proving that no cyclic or
   otherwise constrained assignment exists may still examine the candidate bindings and relationship
   tuples the conjunction genuinely requires.
7. Insert ordered projected identities into a query-specific temporary answer table with a primary
   key, stopping at `maximum_rows + 1` distinct identities. Reject whole when over bound; otherwise
   hydrate projected identities only.

Identity includes projection name plus anchor/link/data UUID. A property identity includes
projection name, source associated-data UUID, presence, and canonical value. Equal values from
different sources remain distinct; hidden witnesses do not distinguish rows. Physically, the selected
object-value ID for that source functionally determines its UUID, property presence, and value at one
evaluated state, so the temporary identity key need not copy the JSON value before the bound passes.

For aggregate output, the named data condition is the sole answer selector. Populate one temporary
target table keyed by its data UUID with every other variable existential under the same
conjunction, stopping at `maximum_matches + 1`. Reject before arithmetic when over bound. Count the target table and stream
requested property rows through existing exact reducers. Retain sparse SQLite-backed exact-sum
terms. There is no per-target loop because one request has one target population.

SQLite may push any selective type, UUID, association, link, or property predicate. The semantic
constraint is elimination of forbidden logical witness bags, not a prescribed physical order or a
new general-purpose optimizer.

`matchesPattern` is intentionally non-sargable. It filters the present string properties of the
associated-data UUIDs in that selector's logical candidate relation; it does not generate candidates
or license a scan of same-named properties on unrelated types or associations. A genuinely broad
candidate relation may require one RE2 evaluation per candidate carrying the property. The compiler
may choose any equivalent physical order, but its relation and indexes must keep regex work tied to
that relevant candidate population.

### Exact capacity and preparation

Do not replace the old field-count formulas with a longer set of guessed formulas. W003 begins by
inventorying every active SQLite limit category exercised by generated statements, bound parameters,
or temporary query rows. Each `CompiledStatement` carries its exact SQL, parameters, and structural
profile. A preparation-only probe of that same statement under the connection's active limits—using
`EXPLAIN` or an equivalent non-stepping preparation boundary—complements properties known directly
from the compiled artifact. No answer statement executes until every statement prepares.

The inventory has these dispositions:

- `SQLITE_LIMIT_SQL_LENGTH`: compare each generated statement's UTF-8 byte length exactly;
- `SQLITE_LIMIT_VARIABLE_NUMBER`: compare the actual highest sequential parameter index and retain
  the historical-state and answer-limit bindings naturally;
- `SQLITE_LIMIT_COLUMN`: cover generated table/index columns, result columns, `INSERT` values, and
  ordering/grouping terms rather than only public projections;
- the 64-table join limit and `SQLITE_LIMIT_EXPR_DEPTH`: derive each generated `SELECT` scope and
  expression/subquery depth from the compiled statement;
- `SQLITE_LIMIT_PARSER_DEPTH` and `SQLITE_LIMIT_VDBE_OP`: use the preparation probe, including a
  capability-gated parser-depth category when SQLite exposes it before Python gives it a symbolic
  constant. A parser recursion failure or bare prepare-time memory error is called a configured-limit
  rejection only when a controlled retry under the connection's hard parser or VDBE limit proves that
  cause; restore every temporarily changed limit in `finally`. Otherwise it remains an execution or
  allocation failure, not a guessed rejection;
- `SQLITE_LIMIT_LENGTH`: preflight bound text/blob byte lengths, retain only integer object-value IDs
  and bounded scalar metadata in temporary identity rows, and translate deterministic
  `SQLITE_TOOBIG` while populating selector/answer work inside the rollback boundary into typed
  whole-result refusal;
- `SQLITE_LIMIT_FUNCTION_ARG`: generated functions have fixed arity, including the two-argument RE2
  predicate, and preparation proves that arity fits the active limit;
- `SQLITE_LIMIT_COMPOUND_SELECT` and `SQLITE_LIMIT_LIKE_PATTERN_LENGTH`: the compiler emits no
  compound select and no `LIKE`/`GLOB`; RE2 does not inherit the `LIKE` limit; and
- attached-database, trigger-depth, and worker-thread limits are not query-shape drivers because the
  compiler attaches no database, installs or invokes no trigger, and requests no worker.

Maximum values and `maximum + 1` arithmetic must also fit SQLite's integer range. Historical
predicates and answer `LIMIT` bindings are present automatically. Delete every hand-maintained
query-field estimate. A confirmed deterministic request-shape or generated-statement capacity excess
is a typed `REJECTED` whole result before hydration or arithmetic, with no payload or evaluated
revision. Actual I/O, locking, corruption, or allocation failures remain safely reportable `FAILED`
outcomes—or unexpected boundary failures when no domain result can safely be formed—rather than
being mislabeled as semantic capacity refusal.

### Oracle and integration

Rewrite `tests/vellis/oracle.py` as small brute-force conjunctive-pattern semantics importing only
public graph and query values. It independently implements row identity, recursive JSON comparison,
and aggregate reduction; it imports no production analyzer, planner, evaluator, identity, or
reducer. Add fixed-seed generated finite-pattern cases, including disconnected projected and hidden
portions, parallel predicates, self-links, and cycles, and prove a deliberately mutated production
result is detected.

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
- recursive SQL `validate=False` / `existence_only=True` paths and the legacy component-specific
  disconnected-aggregation workaround;
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

Decisive evidence covers link insertion, removal, endpoint change, type change, and tombstone;
anchor/data type changes at either constrained end; data anchor-set changes; simultaneous endpoint
and relationship changes; overlapping rules; rule addition, removal, and meaning change;
description-only rules; display/property-only graph edits; active/prospective equivalence; exact
lookup-only endpoints; atomic rejection; and preservation of the stored proposal during active
validation. Rolled-back internal tests inspect exact reason and `(rule, subject, end)` work tuples.

## Transitional evidence retirement

The conflicting-baseline characterizations are temporary evidence, not permanent regressions or
performance budgets. Retire them with the work that makes each old assertion false:

- W002 replaces the pairwise-equality characterization with permanent canonical-key semantics and
  linear key-construction evidence while retaining unrelated trigger cases.
- W003 replaces historical-capacity and query/evaluator source-shape assertions with compiled-binding,
  hidden-witness, and independent-oracle conformance evidence.
- W004 replaces exact quadratic active/prospective costs with exact-work-cardinality and
  sub-quadratic scaling regressions.
- W006 replaces mixed-assessment-page and retained assessment/restore work-table characterizations
  with snapshot-consistency and empty-after-success/failure lifecycle regressions.
- W005 verifies that no transitional source-shape or old-cost assertion remains; it does not defer
  every replacement until closure.

The exact old VM-step and decode counts remain pinned only until their owning work item replaces
them. They characterize the selected execution environment and are not public budgets.

## Verification matrix

Query evidence covers broad/multi-type and UUID-restricted anchors; UUID restrictions for all three
object kinds; mixed known/unknown and wrong-kind/type refusal; data association and property
comparisons and RE2 whole-string matching; missing versus null; directed links;
paths/stars/branching patterns; parallel links over
the same aliases; direct-association/link conjunction; self-links; cycles; disconnected projected
combinations; disconnected hidden existence gates; hidden variables;
projected links; same-object and same-link aliases; source-preserving equal property values; genuine
projected combinations; bound-plus-one refusal; unreturnable encoding; and declaration-order
invariance.

Invalidity evidence covers empty/duplicate names, unknown references/types, empty/duplicate UUID
filters, malformed or unsupported RE2 expressions, pattern comparisons on
non-string properties, empty outputs/aggregations, bad aggregate target/property/operator, nonpositive bounds,
prospective without delta, unknown revision, naive time, and structural SQLite excess. Lower each
applicable SQL-length, bound-value/row-length, variable, column, expression, parser, VDBE-op, and
function-argument limit around one generated boundary and exercise the nonconfigurable table
boundary; each deterministic excess is typed `REJECTED` before hydration/arithmetic, with no partial
answer or evaluated revision and every canonical non-effect. Avoided categories are verified absent
from compiled statements rather than assigned synthetic tests. Inject genuine preparation allocation
and execution faults separately so they are not mislabeled as semantic refusal.

Aggregation evidence covers zero/nonzero count, exact and cancelling sums, numeric/string extrema,
missing/all-missing properties, several operations/properties on one target, hidden witness
deduplication, equal-valued distinct targets, bound-plus-one, and all four state selections.

Differential generation uses fixed-seed small finite positive patterns with connected and disconnected
variables, sparse/dense links, parallel and cyclic predicates, missing/null properties, duplicate
values/witnesses, and alias reuse.
Compare status, revision, canonical row identity, returned values, aggregates, and refusal.
Metamorphic cases reorder declarations, rename aliases, duplicate hidden witnesses, add unrelated
population, substitute equivalent revision state, change multiplicity-irrelevant display/property
data, and permute semantically equal object members.

Scaling evidence uses SQLite VM steps and decoded-object counts, not wall-clock budgets:

- hidden query witness fanout 10/20/40 keeps rows/decodes fixed and doubling ratio below three;
- genuine projected combinations grow only as answer mathematics requires and refuse at the bound;
- unrelated populations leave results/decodes fixed with indexed lookup plans;
- aggregate hidden witnesses leave target count fixed;
- regex locality holds relevant selector/association candidates and answers fixed while unrelated
  objects carrying the same property name and string kind grow: RE2 calls and property-row visits stay
  tied to relevant candidates and VM-step growth remains indexed; a broad relevant population is
  separately allowed to require one RE2 call per present candidate value;
- active hub-of-hubs 10/20/40 has exact work proportional to applicable degree and ratios below three;
- display-only edits across 10/100/500/1,000 irrelevant rules produce zero multiplicity work;
- K independent changes/rules at 5/10/20/40 produce K exact tuples, not K squared;
- changed rules expand only over their applicable subjects; complete assessment remains explicitly
  state-wide with bounded process materialization.

MCP evidence keeps exactly ten tool names, exposes output/state discriminators, rejects rather than
translates every removed shape, distinguishes typed semantic refusal from malformed boundary input,
opens existing databases without migration, and keeps snapshot/replay/restore/restart/v1 evidence
green. Negative boundary cases include absent explicit discriminators, wrong discriminator values,
variant-specific members attached to another state kind, aggregate members attached to row output,
row members attached to aggregate output, and otherwise unknown members of the closed state/output
variants. Each malformed case proves that no domain operation or observation ran.

## W006 — bounded transient read and work-state lifetimes

After W004 has replaced prospective assessment internals, close the two lifecycle gaps that are not
query or multiplicity semantics:

- Read every published assessment interval in one explicit SQLite read transaction. A concurrent
  replacement may occur before or after that transaction, but cannot combine an old assessment
  header/count with missing or newer finding rows.
- Clear every population-bearing `assessment_*` working relation after successful assessment and
  after failure. Preserve only the normalized published assessment and its bounded retrieval rows.
- Clear `restore_candidate`, `restore_current`, and every other population-bearing `restore_*`
  working relation after successful restoration and after failure. Preserve the committed restored
  current projection and canonical transition, not the transient comparison population.
- Keep temporary relation definitions connection-local for reuse; clear their rows. Cleanup is part
  of the owning transaction/failure discipline and must not hide the original operation error.

Deterministic two-connection evidence replaces a published assessment between the header and
finding reads and accepts only a complete old or complete new interval. Success/failure fixtures
inspect every assessment/restore temporary relation and require zero retained population rows before
the next invocation. Scale fixtures use a multi-object population so a constant-row residue cannot
masquerade as cleanup. Restoration meaning, schema version, snapshots, replay, and canonical history
remain unchanged.

## W005 closure and subtraction

Run the documentation-sync workflow and reconcile `model/README.md`, `README.md`,
`docs/mcp-realization.md`, examples, and test descriptions with implemented truth. Remove obsolete
workaround prose rather than memorializing it. Search model, source, tests, README, and docs for every
deleted name and inverse claim. Confirm that the owning W002–W004 replacements have emptied or
deleted `tests/vellis/test_semantic_work_locality_triggers.py` and that no source-shape or exact
old-cost assertion survives.

Confirm persistent schema/version and snapshot fixtures did not change and exactly ten MCP names
remain. Run focused query/equality/mutation tests, `just model-check`,
`just system-evolution-check`, `just package-check`, `just check`, and `git diff --check`. Freeze one
token and obtain fresh authority/conformance and engineering/evidence reviews at that same token.
Only deterministic evolution bookkeeping may follow a clean pair; commit and independently validate
the committed checkpoint.

## Downstream rebaseline after W001

Before W001 can be accepted, every remaining work item is interpreted against the finite positive
conjunction above, not the superseded tree or connected-only plans:

- W002 is unchanged in meaning and remains a prerequisite that supplies canonical JSON keys without
  changing persistence or query topology.
- W003 owns the entire atomic query cutover: closed request values, topology-independent analyzer and
  oracle, one relational compiler, regex candidate locality, complete compiled/preparation capacity
  handling, read-snapshot repair, public integration, and deletion of the old evaluator/component
  paths. Its sections above are resumable internal phases, not separately conforming product states;
  no phase may introduce an adapter, feature flag, fallback evaluator, or second public language.
- W004 remains the exact active/prospective mutation-impact kernel. None of its work, evidence, or
  locality rules may infer selector trees, query components, or query-planner abstractions.
- W006 remains the independent assessment/restore read-snapshot and temporary-work-lifetime repair;
  it neither reopens query semantics nor absorbs W003 work.
- W005 must search model, source, tests, and documentation for stale `tree`, `connected-only`,
  `backbone`, component-reconstruction, legacy capacity-formula, and regex-unrelated-population claims,
  in addition to the deletion inventory already listed. It closes only after the implemented system
  and public truth reflect this rebased handoff.

This rebaseline supersedes the earlier detailed plan wherever it required connected acyclic selector
graphs, answer-relevant backbones, or removal of disconnected queries. All other accepted non-goals
and non-effects remain in force.

## Execution status

W001 authority and W002 canonical collection equality are complete. W003 now has an implementation
candidate: the closed public schema, independent brute-force oracle, conjunctive SQLite compiler,
unified selector-member relation, bounded row/target identity materialization, compiled-statement
capacity checks, tagged state integration, one-snapshot definition discovery, and legacy query-path
deletion are present and locally evidenced. W003 remains active until its clean review pair and
checkpoint bookkeeping complete. W007, W004, W006, and final W005 closure retain the dependencies,
evidence obligations, and deletion scope stated above.

## Resume and change control

At every resumed turn, confirm path/status/worktrees, validate the evolution record, confirm the sole
active work item/checkpoint, recompute the relevant baseline, reconcile all changes, and reread the
work item's qualified authority and current model diff. New evidence becomes a finding when it has an
independent consequence. Widen an item only when authority, approval, outcome, and review surface are
unchanged; otherwise add a dependent item or stop for model acceptance. Sweep a root cause before
review. Do not add an optimizer, runtime-selectable planner, fallback evaluator, generic rule engine,
persistent cache/view, schema migration, new public tool, or new authorization/session/worker concept.

The evolution intentionally removes mixed-output and multi-target aggregate questions and changes
prerelease request schemas/property row identity. It retains the complete finite positive graph-pattern
conjunction: disconnected, parallel, self-link, and cyclic relationship patterns remain valid under
one joint binding. Server-side anchor/link aggregation remains
an explicit non-goal rather than a lost capability of this change. The evolution does not change
graph/type meaning, direct associations, link meaning, property comparison,
persistence/history/snapshots/restore/v1 initialization, tool names, launch/registration, approval,
or canonical mutation boundaries.
