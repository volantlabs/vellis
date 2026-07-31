---
name: rtg-schema-design
description: Design, review, or evolve language-neutral RTG graph meaning and schemas from owner needs and intended queries. Use when deciding anchors, associated data objects, direct anchor-data associations, links, endpoint kinds, type keys, typed properties, incomplete records, compatibility effects, or whether a proposed concept belongs in the RTG graph.
---

# RTG Schema Design

Use this skill for domain meaning, not live graph operation or migration infrastructure. Pair it with `$sysml-modeling` when changing the system model and `$sysml-reference` when the modeling decision depends on SysML or KerML semantics.

## Workflow

1. Begin with owner questions, desired outcomes, and the queries the graph must answer.
2. Decide which concepts need independent identity and which are descriptive fact groups.
3. Apply the RTG distinctions in [RTG domain review](references/schema-design.md).
4. Keep incomplete but truthful records possible; require a property only when absence makes the record misleading or unusable.
5. Choose stable, meaningful type and property names. Avoid opaque generic JSON when callers need typed facts.
6. For each link, make direction and permitted source and target kinds and type sets explicit.
7. Avoid schema detail that no modeled use case, invariant, or intended query requires.
8. Describe compatibility effects on existing graph meaning without inventing importers, controllers, cutovers, or release machinery.
9. Obtain human approval before changing consequential domain meaning.

Do not assume that a schema decision has an immediately available operational migration path.

## Output

State the owner need, proposed domain distinction, intended queries, required and optional facts, endpoint rules, compatibility effects, unresolved questions, and the smallest verification examples that discriminate the design.
