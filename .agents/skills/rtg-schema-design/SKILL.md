---
name: rtg-schema-design
description: Design, review, and evolve language-neutral Reified Type Graph (RTG) meaning and governance from owner needs and intended queries. Use for cold-agent definition discovery; anchor, associated-data, link, and direct-association classification; current or prospective graph queries; definitions and relationship rules; prospective changes; validation, revisions, canonical and activity ledgers, snapshots, replay, restore, predecessor recovery, MCP exposure, and compatibility.
---

# RTG Schema Design

Use this skill for RTG domain, query, governance, snapshot, and history meaning, not live graph
operation, executable syntax, storage layout, migration infrastructure, or constraint-engine design.
Pair it with `$sysml-modeling` when changing the system model and `$sysml-reference` for consequential
SysML or KerML choices.

## Operating biases

- Do not infer RTG behavior from the phrase “reified type graph,” another graph product, or predecessor class names. Begin with the four canonical RTG distinctions and current owner questions.
- Decide identity, independent existence, and relationship meaning before type names or schema shape.
- Keep filtering facts distinct from returned facts: participation in matching does not authorize projection.
- Keep canonical transition evidence distinct from observational activity, and distinguish replay, initialization, restore, and predecessor recovery before discussing representation.
- Distinguish replay-bearing history from bounded owner-facing history views, and canonical
  nonmutation from permitted observational activity.
- Treat a trusted owner-configured client as a boundary assumption, not an RTG authorization or
  approval mechanism.
- Make current graph state understandable to an agent without predecessor knowledge: prefer a
  complete shallow active-anchor summary followed by complete focused inspection of selected
  active-definition neighborhoods. Compare evaluated revisions and repeat discovery if they differ.
  Keep the sole current proposed definition set
  separately retrievable in full.
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
3. If discovery changes, distinguish current active summary, focused inspection with its own
   evaluated revision, and whole current proposed state. Make revision drift detectable rather than
   inventing a session or lock. Make owner-readable descriptions canonical definition
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
   reserve complete replacement state for behavior that actually replaces state. Add history,
   snapshot, restore, or activity detail only when the changed behavior depends on it.
7. If recovery or compatibility changes, preserve RTG meaning without adopting predecessor storage,
   schema, runtime, or migration architecture.
8. If a tool, protocol, or framework constrains exposure, translate only the owner-visible limit into
   model meaning. Do not mirror tool names, operation counts, envelopes, resources, or framework
   lifecycles into the RTG domain. If the public operation inventory is intentionally fixed, keep it
   at the system boundary and do not turn it into domain types or internal structure.
9. Exercise the smallest accepted case, rejected case with non-effects, and counterexample that
   exposes mistaken identity, relationship authority, projection, delta, or history meaning.
10. Perform adequacy and subtraction reviews. Stop once the affected dimensions are closed.

Apply the distinctions and review criteria in [RTG domain and governance review](references/schema-design.md).

## Output

Report the preferred answer, affected canonical meaning and consequences, compatibility impact, and
discriminating evidence. Mention an unchanged dimension only when doing so prevents a likely false
inference; do not fill an output schema for completeness.
