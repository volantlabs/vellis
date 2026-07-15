# RTG Beta Known-Good Walkthrough

Use this walkthrough to recognize a successful first Vellis beta run. It is not a script and it is
not an MCP resource; it is the expected shape of an agent run after the `rtg_knowledge_graph` MCP
server is connected.

## 1. Launch And Connect

Start from a fresh storage root:

```sh
uv run vellis-rtg-knowledge-graph mcp-config --data-dir .data/vellis-runtime-eval-001 --empty
```

This walkthrough does not open an earlier-version root. Transfer earlier data by exporting one
full coordinated snapshot with the source version and restoring it into a separate empty current
root; follow [`snapshot-transfer.md`](../snapshot-transfer.md).

Merge the complete generated `mcpServers` block into an MCP client and restart/reload the client;
the client starts the stdio server. If the agent should attach to an already-running local app
instead, run `uv run vellis serve-mcp --transport http --data-dir .data/vellis-runtime-eval-001 --empty` and use
`http://127.0.0.1:8765/mcp`.

The first call is:

```json
{"tool": "rtg_validate_graph", "arguments": {}}
```

Expected result: `ok: true`, `result.accepted: true`, and no findings.

Then call:

```json
{"tool": "rtg_get_system_state", "arguments": {}}
```

Expected result: a fresh data root reports `state_classification: "empty"`. A restarted server
automatically reconstructs the latest committed managed state before accepting traffic and should
report the same `schema_only` or `populated` classification it had before shutdown. The nested
`runtime` status reports health, current runtime position, and the latest terminal trace when one
exists.

Agents without repo access can call `rtg_get_usage_guide` with
`topic: "mcp_bootstrap_checklist"` for the canonical sequence.

## 2. Bootstrap The Life-Graph Schema

Give the agent `docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md`.

The agent should stage non-live schema definitions for `Person`, `Area`, `Project`, `Task`,
`Event`, `Note`, and `Resource`, plus their required facts objects and relationship links. The
preferred staging call is `rtg_stage_schema_migration`; advanced normalized batches may still use
`rtg_stage_knowledge_changes`. The cutover should use `rtg_apply_migration_cutover`.

Agents without filesystem access should use `rtg_get_usage_guide` with
`topic: "schema_staging_minimal"` or `topic: "tool_call_shapes"` only for generic schema and tool
payload shape. They should construct the life-graph schema from the beta prompt's requested
anchors, required facts, fields, and links.

The agent should choose stable machine property keys, preferably `snake_case`, and report the
mapping from prose labels to property keys. Expected examples include `preferred_contact`,
`desired_outcome`, and `next_review`.

The prompt's date-like fields are required strings rather than typed dates. When exact values are
not supplied, the agent should choose reasonable ISO-8601 placeholder strings for `due`, `start`,
and `next_review`, avoid empty required date-like values, and report those placeholder assumptions.

Expected evidence:

- staging returns `ok: true` with generated IDs and applied-change evidence when applicable
- migration cutover returns `ok: true`
- `rtg_discover_anchor_types` returns the seven live anchor types
- `rtg_get_schema_pack` can describe required facts for selected anchor types
- `rtg_get_system_state` reports `schema_only` before data ingestion or `populated` afterward

## 3. Ingest And Query Live Data

The agent should resolve existing object UUIDs before writing links. Prefer
`rtg_resolve_anchor_by_fact` for exact fact lookups; MCP-only agents can also call
`rtg_get_usage_guide` with `topic: "lookup_examples"` for copy-pastable query payloads. The agent
should use `rtg_apply_live_anchor_records` for repeated anchor plus required-facts ingestion, use
`rtg_apply_live_graph_changes` for lower-level graph CRUD and links, then answer planning
questions with `rtg_execute_query`. For human-facing summaries, compact queries may use
`response_options: {"format": "properties_only"}`.

Known-good query outcomes include:

- next professional tasks: invite first beta testers, draft the Vellis public roadmap, prepare mentor agenda
- next personal tasks: renew home insurance, schedule annual physical, review monthly budget
- active projects across personal and professional domains: four active projects and one waiting
  project unless statuses are intentionally changed
- task status counts: six next tasks and two waiting tasks unless statuses are intentionally changed
- reconciled count reporting: global counts and per-domain counts should agree; for the default
  data, professional projects are two active, and personal projects are two active plus one waiting
- title-level status check: next tasks are invite first beta testers, draft the public roadmap,
  prepare mentor agenda, renew home insurance, schedule annual physical, and review monthly budget;
  waiting tasks are collect eval feedback and gather tax documents
- tasks supporting the Vellis beta and open-source launch
- notes or resources supporting active projects

The agent should use `resource_id` values returned by earlier calls when linking to existing
objects. `local_ref` values are only valid inside the request that defines them.

Useful beta links are enough; exhaustive linking is not required. Projects should belong to one
primary area where reasonable. Tasks, events, notes, and resources should support relevant projects
only when useful for future planning or retrieval. Ownership links should be sparse and represent
genuine responsibility, not every possible association. Mention links should be used only for
explicit mentions, and dependency links should represent real sequencing or blocking.

## 4. Recover From Bad Writes

The agent should intentionally exercise strict validation and repair the payloads without weakening
the schema.

Known-good dry-run failures:

- a `Task` anchor without required `TaskFacts`, or a `TaskFacts` object missing a required
  property, returns a blocking schema finding
- a non-string `TaskFacts.due` returns `schema_object.property_kind_mismatch`
- optionally, an invalid relationship endpoint returns a link endpoint type finding

The agent should use `rtg_validate_live_graph_changes` or `rtg_validate_live_anchor_records` for
recovery probes that should not mutate state. Valid dry-run `validation_options` are `tracks` and
`finding_limit`; mutation tools use `validation_mode`. Corrected write examples should become live
only when they are real planning content. Dry-run validation evidence can stay in the final brief;
create a `Note` only when durable graph evidence is explicitly desired.

## 5. Prove Evolution Safety

The agent should stage a stricter `ProjectFacts` schema that requires a new `sponsor` field while
existing project facts do not have that field. Because strict staging catches invalid projected
cutovers early, use `validation_mode: "skip"` only for this controlled failed-cutover exercise.

Expected result:

- staging can succeed in skip mode because it records a candidate migration for the rollback test
- cutover fails with a validation report containing `schema_object.missing_required_property`
- the previous live `ProjectFacts` schema remains live
- the migration is marked `failed` with status metadata that describes the validation failure
- `rtg_list_migration_history` projects the staged and failed cutover runtime traces even if
  current migration counts later return to zero after abandonment/pruning
- `rtg_validate_graph({})` still returns accepted current state
- if the failed candidate is not going to be repaired, `rtg_abandon_migration` records the
  abandonment and prunes safe non-live make-live candidates

## 6. Preserve And Reconstruct Evidence

The agent should call `rtg_persist_system_snapshot` with `return_snapshot:false`, then
`rtg_list_persisted_snapshots` and `rtg_load_persisted_snapshot` with `return_snapshot:false`. It
should report the snapshot path and compact summary counts without dumping the full graph. The
runtime records the façade request, component calls, canonical effects, and terminal trace in its
authoritative chronology.

For a restart check, stop the server cleanly and start a new process against the same data root and
runtime database. Latest committed state reconstruction is automatic. Verify the expected task
count, call `rtg_validate_graph({})`, and use the legacy-named
`rtg_verify_replay_from_ledger({"replay_options": {}})` compatibility operation to inspect the
latest startup reconstruction report.

Expected result: reconstruction verification reports `verified: true`, the reconstructed-through
runtime position, component state digests, applied/skipped effect counts, limitations, and passing
invariant verification. It must not recontact external adapters or append playback as new business
traffic.

Historical reconstruction through an earlier runtime position is never an in-place eval step.
Copy the complete data root, attach that isolated copy to compatible empty occurrences, and request
reconstruction through the selected position. Keep the active root unchanged. A branch that accepts
new traffic must first record source-runtime, source-position, and verified-digest provenance.

## Completion Brief

A good final agent brief should tell the human:

- what live schema exists
- which prose labels were mapped to which machine property keys
- which date-like placeholder assumptions were used
- what personal and professional facts are live
- how global and domain counts reconcile
- which next actions and active projects were found through queries
- which bad writes were rejected and how they were repaired
- which schema evolution failed safely
- which snapshot, runtime trace/position evidence, migration trace history, and reconstruction
  verification support recovery
- what modeling choices remain uncertain
