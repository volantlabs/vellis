---
name: rtg-schema-design
description: Design or evolve language-neutral RTG graph schemas from user and system needs. Use when choosing anchors, associated data, links, required properties, type keys, migration boundaries, or compatibility rules; when reviewing an RTG schema for clarity and extensibility; or before making consequential schema changes to a live RTG graph.
---

# RTG Schema Design

Turn domain meaning into the smallest precise RTG schema that supports identity, typed facts,
relationships, queries, and safe evolution. Preserve partial knowledge and implementation freedom.

Read [schema-design.md](references/schema-design.md) before authoring or approving a schema.

## Workflow

1. Elicit the questions, decisions, and ordinary requests the graph must support.
2. Inspect the existing schema and representative live data when evolving a graph.
3. Identify independently addressable things as anchors, coherent typed facts as associated data,
   and meaningful navigable relationships as links.
4. Define stable type keys, property kinds, required fields, deliberate field refinements, and
   allowed link endpoints.
5. Walk through incomplete, duplicate, evolving, and query scenarios. Remove requirements that
   would force agents to invent facts.
6. Explain the proposed semantics and compatibility impact. Obtain human approval before a
   consequential live-schema change.
7. Stage and validate the migration, inspect findings, cut over atomically, then validate live
   data and representative queries.

## Output Standard

Produce a reviewable schema proposal containing:

- the user outcomes and queries it supports;
- anchor, associated-data, and link definitions with rationale;
- exact property kinds, optionality, justified refinements, and link endpoint sets;
- identity, naming, and duplicate-handling rules;
- compatibility and migration effects on existing data;
- validation and acceptance scenarios;
- intentional freedoms and deferred specializations.

Stop when the schema is sufficient for correct storage, linking, querying, extension, and
black-box validation. Do not model agent prompts, private implementation structure, or speculative
domain detail as schema.
