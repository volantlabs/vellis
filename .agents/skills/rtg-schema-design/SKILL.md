---
name: rtg-schema-design
description: Design, review, evolve, and prepare implementation-ready handoffs for language-neutral Reified Type Graph (RTG) meaning and governance from owner needs and intended queries. Use for cold-agent current or historical definition discovery; anchor, associated-data, link, and direct-association classification; current or prospective graph queries; definitions and relationship rules; prospective changes; validation, revisions, canonical and activity ledgers, snapshots, replay, restore, first-use compatibility initialization, MCP exposure, and RTG implementation feedback.
---

# RTG Schema Design

This is an optional domain extension to the portable SysML modeling and implementation method. Other
projects do not need it, and portable core skills must not depend on it.

Use this skill for RTG domain, query, governance, snapshot, and history meaning, not live graph
operation, executable syntax, storage layout, migration infrastructure, or constraint-engine design.
Pair it with `$sysml-modeling` when changing the system model and `$sysml-reference` for consequential
SysML or KerML choices.

## Operating biases

- Do not infer RTG behavior from the phrase “reified type graph,” another graph product, or predecessor class names. Begin with the four canonical RTG distinctions and current owner questions.
- Decide identity, independent existence, and relationship meaning before type names or schema shape.
- Keep filtering facts distinct from returned facts: participation in matching does not authorize projection.
- Keep canonical transition evidence distinct from observational activity, and distinguish replay,
  fresh initialization, snapshot-based initialization, restore, and first-use compatibility
  initialization before discussing representation.
- Distinguish replay-bearing history from bounded owner-facing history views, and canonical
  nonmutation from permitted observational activity.
- Treat a trusted owner-configured client as a boundary assumption, not an RTG authorization or
  approval mechanism.
- Make current or selected historical graph state understandable to an agent without predecessor
  knowledge: prefer a complete shallow active-anchor summary followed by complete focused inspection
  of selected active-definition neighborhoods at the same evaluated revision. Reuse a time summary's
  resolved revision for inspection and query, and compare evaluated revisions before relying on the
  result. Keep the sole current proposed definition set separately retrievable in full, and rediscover
  current definitions before preparing a current mutation.
- Prefer discriminating examples and invalid cases over a generic schema vocabulary. Do not invent a query, constraint, migration, or storage language to make the model look executable.
- Treat query, governance, validation, history, recovery, and compatibility as conditional
  dimensions. Address only those changed by the current owner question; do not create one public
  operation or artifact per dimension.
- Prefer natural keys, derived meaning, one authoritative prospective state, and one relationship
  authority before adding UUIDs, stored lifecycle flags, intent logs, subtype families, or
  generalized rule objects. Choose a complete bounded proposal or keyed overlay from the owner need;
  neither is a universal default.

## Workflow

1. Read the current model, recover explicit owner decisions and selected RTG meaning, and state one
   owner question and observable distinction. This skill supplies heuristics, not a parallel RTG
   contract. An explicit review may reassess in-scope structure; otherwise preserve selected meaning.
2. Establish the affected canonical distinctions: identity, object kind, direct grounding, link
   direction and endpoints, type keys, associated-data properties, and compatibility defaults.
3. If discovery changes, distinguish current or selected historical active summary, focused
   inspection with its own evaluated revision, and whole current proposed state. Make revision drift
   detectable rather than inventing a session or lock, and keep delta retrieval current-only. Make owner-readable descriptions canonical definition
   data rather than comments; keep structured rules authoritative and do not invent a prose
   constraint language.
4. If querying changes, define only the selected anchor or associated-data endpoint groups,
   narrowing, relationships, structured value comparisons, projection, and result bounds required by
   the owner question. Let active definitions at the evaluated revision govern property and endpoint
   validity. Define one row's joint binding meaning, projection completeness, duplicate behavior, and
   missing-versus-null result semantics. Distinguish absent, empty, unknown, and invalid inputs. Do not
   imply an evaluation pipeline or add paging and traversal by habit.
5. If governance changes, test natural identity, one relationship authority, and the smallest
   prospective representation against the owner need. A small complete next state can be simpler for
   agent inspection; a keyed overlay can be simpler when copying is material. Distinguish either
   proposal from a second canonical occurrence.
6. If canonical state changes, state validation, atomicity, effective no-op, revision, rejection, and
   replay effects. Carry the smallest replay-sufficient semantic change for ordinary transitions;
   reserve complete replacement state for an ordinary transition only when restore actually replaces
   state. Add history,
   snapshot, restore, or activity detail only when the changed behavior depends on it.
7. If recovery or compatibility changes, distinguish ordinary restart, fresh snapshot-based lineage,
   restore, and first-use v1 initialization. Preserve RTG meaning without adopting predecessor
   storage, schema, runtime, ledger history, or migration architecture.
8. If a tool, protocol, or framework constrains exposure, translate only the owner-visible limit into
   model meaning. Do not mirror tool names, operation counts, envelopes, resources, or framework
   lifecycles into the RTG domain. If the public operation inventory is intentionally fixed, keep it
   at the system boundary and do not turn it into domain types or internal structure.
9. Exercise the smallest accepted case, rejected case with non-effects, and counterexample that
   exposes mistaken identity, relationship authority, projection, delta, or history meaning.
10. When the result will guide implementation, surface the applicable RTG semantic commitments below
    through `$sysml-modeling`'s implementation-handoff pattern. When code returns feedback, reproduce
    its failing graph instance or transition before deciding whether the model or implementation is
    wrong.
11. Perform adequacy and subtraction reviews. Stop once the affected dimensions are closed.

Apply the distinctions and review criteria in [RTG domain and governance review](references/schema-design.md).

## Implementation leverage

Expose only the dimensions the selected implementation slice needs:

- canonical object kinds, identity, natural keys, ownership, direct associations, and link direction;
- exact semantic equality, ordered and unordered collections, missing versus null, and no-op meaning;
- definition closure, property and relationship rules, and the smallest valid and invalid graph;
- query selector, participation, projection, row, duplicate, absence, revision, and bound semantics;
- canonical state tuple, prospective-state cardinality, valid transition combinations, atomicity,
  revision, replay, and every rejection or failure non-effect;
- canonical versus observational history, recovery and first-use compatibility meaning, and selected public
  operation boundaries;
- storage, indexing, serialization, algorithms, runtime, and deployment choices that remain open.

Use concrete instances and qualified model authority rather than proposing tables, classes, graph
engines, repositories, event stores, validators, or API envelopes. If implementation evidence reveals
that two modeled states cannot be distinguished, one invariant cannot be enforced, or one promised
transition cannot be made atomic under a selected boundary, return that exact counterexample and
changed consequence to model review. Do not promote the implementation's current data structures into
RTG meaning.

For software realization, expose graph/value/equality, active-definition and prospective-definition
meaning, conformance assessment, query evaluation and projection, canonical transition and replay,
observational history, and external exposure as possible cohesion neighborhoods. They are neither an
exhaustive class inventory nor modeled subsystems. An implementation may isolate them into classes or
modules for clarity and testing while preserving the RTG System as the one semantic and transactional
owner of graph, definitions, delta, revision, and canonical history. Finer code must not create
competing stores, revisions, transaction boundaries, or authorities.

## Output

Report the preferred answer, affected canonical meaning and consequences, compatibility impact, and
discriminating conformance evidence. For an implementation handoff, use `$sysml-modeling`'s shared
producer contract: qualified authority, the in-scope obligation, full or partial authority coverage,
remaining obligations, decisive instances, evidence intent, applicable invariants and transition
non-effects, and deliberately open realization. For implementation feedback, classify the issue as
language question, model gap, realization decision, feasibility consequence, implementation defect,
or stale baseline. Treat an out-of-scope request as a scope disposition rather than a divergence
class. Mention an unchanged dimension only when doing so prevents a likely false inference; do not
fill an output schema for completeness.
