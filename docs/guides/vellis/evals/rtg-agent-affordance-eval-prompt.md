# RTG Agent Affordance Eval Prompt

Evaluation only: launch Vellis with a fresh data root and `--empty` before using this prompt.

Use this prompt manually with an agent after the `rtg_knowledge_graph` MCP server is
already connected. The prompt is external eval material, not an MCP tool or resource.

## Prompt To Give The Agent

You are maintaining a long-lived project memory for a human-led engineering system.
You have access to an RTG MCP server. Use the RTG system affordances intentionally:
schema definitions, constraint definitions, graph writes, validation, migrations, cutover,
query, snapshots, and runtime trace evidence.

Rules:

- Use the curated Vellis MCP tools directly. The write lanes are live graph writes
  (`rtg_apply_live_graph_changes`, with `rtg_validate_live_graph_changes` for no-mutation probes),
  schema/migration staging (`rtg_stage_schema_migration` or advanced
  `rtg_stage_knowledge_changes`), and migration cutover (`rtg_apply_migration_cutover`).
- Assume the RTG app starts empty unless the evaluator explicitly restored a snapshot.
- First call `rtg_validate_graph`, then call `rtg_get_system_state` and follow its recommended
  next steps. If examples are needed, call `rtg_get_usage_guide`.
- Initial schema and constraints are knowledge-engineering work: stage schema through
  `rtg_stage_schema_migration` when possible, or use `rtg_stage_knowledge_changes` for advanced
  constraint and non-live graph candidates, then make them live with `rtg_apply_migration_cutover`.
- Use strict writes. If a tool returns `ok: false` with `validation_report`, repair
  the submitted payload and retry; do not weaken constraints just to pass.
- Use `rtg_validate_graph` for current-state or migration-projected validation checks. Use
  `rtg_validate_live_graph_changes` before risky live graph imports or recovery probes that should
  not mutate state.
- Keep graph content separate from schema definitions, constraint definitions, migration
  records, and migration evidence.
- Use `rtg_resolve_anchor_by_fact` for exact anchor lookup before link writes when useful. Use
  `rtg_execute_query` for multi-hop questions instead of scanning every object manually.
- Preserve domain evidence through migration evidence, persisted snapshots, and snapshot readback.
  Use runtime trace IDs, runtime positions, and terminal dispositions for cross-component
  chronology when the curated runtime projections expose them.
- Produce a concise human-facing brief at the end.

Tool response shape:

- Success: `{"ok": true, "result": ...}`
- Expected failure: `{"ok": false, "error": {"type": "...", "message": "..."}, ...}`
- Validation failures may include `validation_report.findings`.
- Mutating results describe domain status, generated IDs, applied changes, and validation evidence;
  runtime trace identity and chronology belong to runtime status/history projections rather than
  controller results.

Your mission is to model a small software-component repository as an evolving knowledge graph.
The human needs this memory to answer design, implementation, test-evidence, and planning
questions over time.

Seed scenario:

The human is building an AI-native component library. The memory must track components,
implementation roots, required dependencies, invariants, tests, test evidence, open questions,
work items, and change proposals.

Initial facts:

- Component `component.rtg.graph` is accepted.
- It has implementation root `components/rtg/graph`.
- It owns invariant `global_uuid_uniqueness`.
- Test `components/rtg/graph/tests/test_rtg_graph_contract.py` provides evidence for UUID
  generation and conflict handling.
- Component `component.rtg.schema` is accepted.
- It has implementation root `components/rtg/schema`.
- It owns invariant `live_type_unique`.
- It has an open question count of zero.
- Component `component.rtg.discovery` is draft.
- It is deferred and declares planned implementation root `components/rtg/discovery`.
- It has open question `Should aliases or search terms be part of curated discovery views?`

Required tasks:

1. Design an initial RTG schema and any useful blocking constraints for components,
   implementation roots, invariants, tests, evidence records, open questions, work items, and
   change proposals.
2. Stage those schema and constraint candidates as non-live records, create a ready migration,
   validate the staged state, and apply migration cutover to make the initial model live.
3. Ingest the initial facts as live graph objects using `rtg_apply_live_graph_changes`.
4. Run queries that answer:
   - Which accepted components have invariants without test evidence?
   - Which implementation roots are affected by changing the component schema?
   - Which draft components have unresolved open questions?
5. The human then provides new data:
   - The Vellis runtime has a terminal trace for a `component.rtg.controller` request and its
     derived component calls.
   - Runtime trace evidence must record trace ID, runtime position, action name, terminal
     disposition, and whether a committed canonical effect can reconstruct managed state.
   - This data does not fit the original evidence schema.
6. Propose a non-live evidence schema replacement and a migration record that makes the
   replacement live and retires the old evidence schema.
7. Submit one intentionally invalid proposed evidence item first, inspect the blocking
   `validation_report`, explain the finding, repair the payload, and retry.
8. Apply migration cutover.
9. Query the post-cutover model to show:
   - runtime trace evidence for the controller interaction is represented
   - older test evidence still remains usable
   - accepted components without evidence are still discoverable
10. Export or persist a system snapshot and identify the migration evidence plus runtime
    trace/position evidence that supports the final state.
11. Produce a human-facing brief with:
   - what schema exists now
   - what graph facts are live
   - what changed through migration
   - what evidence supports the changes
   - what remains uncertain

Expected artifacts:

- Initial schema and constraint summary.
- Initial migration and cutover summary.
- Validated initial graph ingestion summary.
- Query results for the three initial questions.
- Failed validation report summary for the intentionally invalid evidence item.
- Repaired migration and successful validation summary.
- Cutover result summary.
- Post-cutover query results.
- Final human-facing brief.

Scoring rubric:

- Pass: The agent uses schema, constraints, validation, migration, query, snapshot, and runtime
  trace affordances in their intended roles; repairs validation failures without weakening rules;
  and produces a traceable human brief.
- Partial: The agent uses graph and query but treats schema evolution, validation, migration,
  or evidence as prose instead of RTG-managed state.
- Fail: The agent bypasses migration for schema evolution, stores schema/constraint/migration
  data as ordinary graph facts, ignores validation findings, or cannot answer multi-hop
  questions through queries.

Failure modes to watch for:

- Directly editing live schema instead of staging non-live candidates.
- Treating graph objects, schema definitions, constraints, migrations, and evidence as one
  undifferentiated document store.
- Replacing validation with narrative reasoning only.
- Weakening constraints to make bad data pass.
- Answering impact questions by scanning every object manually instead of using query patterns.
- Losing the link between human-facing conclusions and runtime trace, snapshot, test, or migration
  evidence.
