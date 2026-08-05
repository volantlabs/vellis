# RTG Domain and Governance Review

This reference supplies reasoning heuristics and counterexamples. The current SysML model remains the
authority for selected Vellis behavior.

## Contents

- [Canonical graph distinctions](#canonical-graph-distinctions)
- [Identity and authority](#identity-and-authority)
- [Prospective change](#prospective-change)
- [Agent definition discovery](#agent-definition-discovery)
- [Query precision](#query-precision-without-a-query-platform)
- [Validation, history, and observability](#validation-history-and-observability)
- [Compatibility and review](#compatibility-and-review)

## Canonical graph distinctions

- **Anchor:** a stable independently identifiable concept with UUID, type key, metadata, and optional
  display name.
- **Associated data object:** an identity-bearing typed fact group with lossless JSON properties,
  associated with one or more anchors.
- **Link:** an identity-bearing typed directed relationship whose endpoints may be anchors or
  associated data objects, never links.
- **Direct anchor/data association:** an identity-free many-to-many relation. It is neither a link nor
  a graph object.

Graph-object UUIDs are globally unique in canonical graph state. Type keys share one namespace and do
not change object kind. Preserve missing `system.live` normalization to `true` and Boolean supplied
values as compatibility meaning; let the current model decide whether that meaning is stored or
derived.

## Identity and authority

Before adding an identifier, ask what must address the concept independently over time. Prefer:

- a type key for a type definition;
- an owning type plus property name for a property definition;
- participating type keys and counted role for a relationship rule;
- a UUID only for an identity-bearing graph object or another independently addressed concept.

Treat rename of a natural key as remove-and-add unless current behavior intentionally gives the
definition identity independent of its key. Do not give definitions, constraints, snapshots, archives,
or requests UUIDs merely because a persistence design could.

Keep one authority for a relationship's meaning. Before separating permitted types, endpoint rules,
multiplicity, and validation, test whether one typed relationship rule could express permission and
bounds without contradiction. Split them only when different owners, lifecycles, or use cases require
independent change.

Derive values already determined by authoritative state. Avoid storing a live flag, status, count, or
projection independently when ownership, membership, omission, or the governing operation determines
it.

## Prospective change

When the owner needs one current prospective change, compare three representations:

1. a complete next-state copy;
2. a keyed overlay of upserts and removals;
3. an ordered intent history.

Prefer the least expressive form that preserves deliberate edits. A small complete proposed set can
make inspection, replacement, and activation clearest; a keyed overlay can avoid material copying;
an intent history is justified only when edit order matters. Use natural keys for definition entries,
UUIDs for graph-object entries, and endpoint UUID pairs for identity-free associations when those are
the selected domain identities. Do not replace an explicitly selected complete proposal with an
overlay merely because patch formats are common.

A proposal for an existing identity is proposed state, not automatically a second graph-object
occurrence. Specify how deletion is represented; do not introduce an intent framework solely because
absence cannot express removal. Within one request, contradictory changes to the same key need an
explicit rejection rule. Across edits, distinguish replacing the current staged entry from retaining
an edit log.

Define equivalence against both current active meaning and the sole proposal. A request equal to the
current proposal can be a no-op; a request equal to active meaning can be a no-op when no proposal
exists. Do not let active-equivalent content silently discard a different proposal when the public
workflow already has an explicit discard operation.

For deletion, separate invalidated references from product policy. Removing an endpoint while an
incident link or direct association remains would make the resulting graph invalid; that does not
authorize the system to remove or rewrite the relationship implicitly. Require the caller to state
every consequential removal or update unless an owner use case explicitly selects cascade behavior.
For associated data, test singly and multiply associated cases before selecting orphan behavior.

Complete-object upserts plus explicit UUID removals can be simpler than a graph patch language. Keep
direct anchor/data association under the associated-data object's anchor references so it has one
authority. Reject conflicts, unknown removals, kind changes, invalid final references, and any change
that assumes an unstated cascade. Validate the resulting graph before an atomic commit; an effective
no-op need not advance revision.

## Agent definition discovery

A cold agent needs meaning before it can formulate a safe graph query or prospective change. Prefer
three deliberately different views:

1. a complete shallow summary of currently active anchor type keys and owner-readable descriptions;
2. complete focused inspection of selected active anchor neighborhoods with its own evaluated
   revision, including directly permitted
   associated-data types, property rules, permitted link roles, endpoint eligibility, relationship
   multiplicity, and rule descriptions;
3. the sole proposed definition set returned whole because it is already the bounded unit of work.

The current summary should reveal whether proposed state exists without mixing it into the active
view. Compare summary and inspection revisions; when they differ, repeat discovery rather than
adding a session, lock, or historical discovery contract. Historical queries must still evaluate
against the definitions active at their resolved revision, but the initial discovery tools are not a
historical schema browser. Until a later owner use case adds that capability, historical querying
requires caller-known vocabulary valid at the selected revision; do not imply that current discovery
makes a cold historical query constructible. Focused inspection must not silently omit a requested
neighborhood; reject an unknown, ambiguous, unresolved, or unanswerable selection instead of
returning a misleading partial description. Let the agent compare current active and proposed meaning
rather than adding server-side diff machinery.

Descriptions are definition data when agents must retrieve them. They explain owner meaning but do
not replace structured endpoint, property, or multiplicity rules. Require every active type and rule
definition to have a non-empty owner-readable description. A proposal may remain editable with a
description finding, but it cannot activate until the invariant holds. Treat presence and
non-emptiness as automatic checks; meaningful owner-readable wording remains an owner-review judgment.

## Query precision without a query platform

Start with the owner's intended questions. Make candidate grouping, type selection, UUID narrowing,
relationship direction, data conditions, projection, and evaluated state explicit only where the
selected query behavior needs them.

When links may address both anchors and associated-data objects, make the smallest endpoint-group
distinction needed by selected questions instead of silently narrowing link queries to anchors or
adding arbitrary traversal. A directly associated-data group with no property comparison can express
type-and-existence matching. Structured comparisons should carry only caller match intent; active
definitions at the evaluated revision remain authoritative for property kind, shape, range, and link
endpoint eligibility. Prefer a small closed comparison set over a textual expression language; state
which JSON kinds support equality and ordering so a generated input schema does not promise ambiguous
comparisons.

Keep these distinctions visible:

- matching participation does not authorize return;
- an absent UUID restriction, an empty restriction, and an unknown UUID may have different selected
  meanings;
- a UUID restriction described as a set is duplicate-free; do not leave duplicate handling to a
  future serializer;
- an omitted JSON property differs from a present `null` without another stored presence flag;
- relationship meaning does not imply an evaluation pipeline;
- a state-bearing graph, snapshot, or ledger is not automatically an agent-safe response.

A result row is one jointly satisfying assignment, not a bag of independently selected objects.
Specify whether every requested projection has one binding, how projected optional properties retain
absence without becoming null, and whether identical projected tuples collapse. Do not manufacture an
evaluation pipeline merely to explain these declarative semantics.

Property rules exposed to agents need closed typed meaning. Prefer a small JSON-kind-compatible size,
numeric-bound, or permitted-value vocabulary over empty `shape` or `range` placeholders. Do not add a
pattern, expression, or nested schema language before an owner query or validation case needs it.
When discovery claims to return the complete property vocabulary, decide explicitly whether that
vocabulary is closed or whether undeclared properties remain valid; do not make agents infer the
answer from implementation behavior.

Unknown, absent, empty, invalid, and not requested are different query meanings. Do not collapse them
into optionality or a universal status. Define a distinction only when callers can act differently
because of it.

Before adding graph-query pagination, consider complete-or-refused bounded results that ask the agent
to narrow the question. Treat the caller's maximum as a cap, not a promise that every request below
an arbitrarily large cap is safe to return; reject any result that cannot be returned completely.
Add ordering, cursors, traversal, OR, aggregation, sorting, computed
expressions, parser, or optimizer only for a modeled query use case.

For canonical change requests, prefer explicit complete-object upserts and UUID removals when those
operations express the selected behavior. Do not accept a whole replacement graph merely because it
is easy to model, and do not add implicit cascade semantics without an owner-visible rule.

MCP tools, protocol resources, framework decorators, and transport payloads are possible exposures of
RTG behavior, not RTG domain concepts. Use implementation affordances to test feasibility and identify
owner-visible limits; do not derive the query vocabulary or operation inventory from the framework.

## Validation, history, and observability

Canonical validation establishes product invariants; it does not automatically justify a public
whole-state validation operation. Replay and reconstruction may be required internally without
becoming public return-all-state tools. Expose an internal step only when an owner or agent has an
independent outcome for it.

Keep outcome categories distinct without a universal envelope: malformed input never forms the
typed domain request, semantic rejection refuses a well-formed request, and execution failure cannot
complete the invoked operation. A successful assessment may report nonconformance without becoming
either rejection or execution failure. For every public result family, state which payload and
revision fields exist for accepted, rejected, safely reported failed, and unexpectedly failed
invocations. Omit success payloads when the operation did not succeed; do not add a universal wrapper
solely to make unlike results symmetrical.

Every effective canonical state change should have explicit revision, atomicity, rejection, and
history effects. Before adding idempotency keys or expected-version protocols, decide whether an
accepted effective no-op is simply not a canonical change.

An ordinary transition should carry the smallest semantic change sufficient for replay. Do not hide a
complete graph snapshot inside a generically named change object. Carry complete replacement state
only for explicit restore or recovery behavior, and make kind-compatible payload rules decisive.

Do not add a second public delta-assessment path when retrieving or staging the sole delta already
returns its current assessment. Keep an independently useful whole-graph conformance check only when
the owner or agent has that distinct diagnostic question.

If canonical history is complete and identifies a lineage, a snapshot without earlier records cannot
silently continue that lineage. Choose explicitly among acceleration of a retained ledger, transfer
of complete history, or seeding a new history from captured state. Keep physical snapshot, event,
checkpoint, database, and serialization choices outside domain meaning until selected.

Capture activity for actual reflection and audit questions rather than symmetrical observability.
Read requests, rejected changes, accepted canonical changes, and bulk maintenance operations may need
different detail. Avoid duplicating full result rows or canonical payloads, inferring intent, or
adding sessions, correlations, identities, universal envelopes, archive objects, and retention
machinery before a use case needs them.

State nonmutation must name the authority it preserves. A read can leave graph, definitions, delta,
revision, and canonical history unchanged while appending one observational record. For an activity-
history read, select the result before appending that read's record so the response cannot include
itself. Keep owner-directed activity retention below the canonical revision boundary.

Do not return replay-bearing records merely because the owner wants to inspect history. A canonical
record can recursively own a complete replacement graph. Prefer one bounded owner-facing entry per
record—with time, provenance, revision or activity kind, and semantic summary—while keeping snapshots,
canonical changes, and ledger tails available only to behavior that actually reconstructs state.

A trusted owner-configured client is a boundary assumption, not an RTG authorization mechanism.
Accept only already-in-scope operations at that boundary and keep owner approval before mutation;
do not invent RBAC, tenants, tokens, or a policy subsystem to make the assumption look executable.

## Compatibility and review

Ask:

- Does the change alter the kind or meaning of an existing type key or UUID?
- Could existing objects, relationships, or truthful incomplete records become invalid?
- Are property meaning, requiredness, range, link direction, endpoint eligibility, or relationship
  counts changing?
- Does proposed state preserve the canonical identity rules?
- Can recovery preserve graph meaning without adopting predecessor storage or architecture?
- Which accepted, rejected, and counterexample instances discriminate the change?

Reject familiar-name substitution from RDF, property graphs, event sourcing, schema registries,
enterprise migrations, or predecessor code. Reject governance UUIDs without independent identity,
parallel relationship authorities, full-state agent responses, public tools that only expose internal
steps, and symmetrical request/report/test families added for completeness.

Use counterexamples: multiply associated data remains one object; a link endpoint is referenced rather
than copied; a direct association has no identity; filtering participation does not authorize return;
activity removal cannot alter replay; a snapshot cannot preserve omitted history by assertion; and an
effective no-op need not create canonical history.
