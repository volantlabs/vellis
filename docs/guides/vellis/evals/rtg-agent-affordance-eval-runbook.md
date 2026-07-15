# RTG Agent Affordance Eval Runbook

Use this runbook to launch the local Vellis RTG MCP server and evaluate whether an agent can use
RTG as an evolving memory, knowledge graph, and database. The default beta path is the individual
life graph: one person using an AI assistant to organize personal and professional domains in a
durable local graph.

The eval prompt is external material for the human evaluator; it is not exposed as an MCP tool or resource.
The prompt files are copied into the agent by the human after the MCP connection succeeds.

## Prerequisites

- `git`, plus a clone of this repository.
- [`uv`](https://docs.astral.sh/uv/) (Python 3.14 is required but `uv` provisions it
  automatically).
- [`just`](https://just.systems/) only for optional convenience recipes; native Windows users can
  use the cross-platform `uv run` commands without Bash, WSL, or `just`.
- An MCP client to evaluate with (Claude Desktop, Claude Code, or any stdio-capable or HTTP-capable client).

See the repository `README.md` Development Setup section for install commands.

## Launch

Use a fresh explicit storage root for each beta eval:

```sh
uv run vellis-rtg-knowledge-graph mcp-config --storage-root .data/vellis-beta-001 --empty --manual-recovery
```

This prints only a copy-pastable `mcpServers` block and does not initialize the application. Merge
the block into the evaluating client's configuration and restart/reload that client. The client
then launches and owns the stdio server; do not start `just rtg` or `just rtg-mcp` separately.

For troubleshooting or eval bookkeeping, `just rtg-eval-info .data/vellis-beta-001` prints the
larger diagnostic payload. That command initializes the composition and reports:

- `mcp.client_config`: copy-pastable MCP server config.
- `mcp.transports.localhost_http.client_config`: URL-based config for agents attaching to a
  running localhost server.
- `mcp.launch`: cwd-independent launch command using `uv --directory <repo-root>`.
- `mcp.launch.args`: includes both `--storage-root` and `--sql-database-path`.
- `mcp.eval_prompt_path`: local path to the recommended eval prompt for the human.
- `mcp.eval_prompts`: available prompt paths, including the individual life-graph beta prompt and
  the component-repo affordance prompt.
- `mcp.first_call`: the first MCP call to make after connecting the client.
- `mcp.state_mode`: `manual_recovery` for this evaluation launch.
- `mcp.tools`: controller-facing RTG MCP tools.

Client wiring:

- Claude Desktop (macOS): merge the `mcpServers` block into
  `~/Library/Application Support/Claude/claude_desktop_config.json` and restart the app.
- Claude Desktop (Windows): merge it into `%APPDATA%\Claude\claude_desktop_config.json` and
  restart the app.
- Claude Code: `claude mcp add rtg_knowledge_graph -- <command and args from the generated
  config>`, or place the `mcpServers` block in a project `.mcp.json`.
- Codex: run the output from
  `uv run vellis-rtg-knowledge-graph mcp-config --client codex --storage-root .data/vellis-beta-001 --empty --manual-recovery`,
  then restart or reload Codex. Do not paste the generic JSON block into Codex's TOML config.

The "MCP Interface" section of `apps/rtg_knowledge_graph/README.md` covers wiring in more
detail.

For agents that should attach to an already-running local Vellis app, launch the unauthenticated
localhost HTTP MCP server instead:

```sh
uv run vellis serve-mcp --transport http --host 127.0.0.1 --port 8765 --path /mcp --storage-root .data/vellis-beta-001 --empty --manual-recovery
```

Then configure the other same-machine agent with
`mcp.transports.localhost_http.client_config`, or connect it to
`http://127.0.0.1:8765/mcp`. Keep this mode bound to `127.0.0.1`; it does not add
authentication and is not intended for network exposure.

After the MCP client connects, make the `mcp.first_call` tool call before giving the agent a
long eval prompt. For the default metadata, call `rtg_validate_graph` with `{}`. A fresh server
should return `ok: true`, `result.accepted: true`, and no findings.
Then call `rtg_get_system_state` with `{}`. A fresh in-memory server should report `empty`; a
restarted server with ledger records may report `needs_replay`; an already bootstrapped server may
report `schema_only` or `populated`.

For the primary beta workflow, give the agent
`docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md` after the first call succeeds. Use
`docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md` as the expected shape of a successful run.
MCP-only agents can call `rtg_get_usage_guide({"topic": "workflow_patterns"})` for generic RTG
operating sequences, `rtg_get_usage_guide({"topic": "request_patterns"})` to map ordinary user
requests to workflow IDs, and `rtg_get_usage_guide({"topic": "schema_staging_minimal"})` for
generic schema payload shape. Agents should build the beta schema from the prompt rather than from
any prebuilt scenario artifact.

V1 state semantics:

- Live RTG graph, schema, constraint, and migration state is in memory for the running MCP
  server process.
- The storage root persists the app manifest, persisted snapshots, queued ledger failures, and
  the SQL ledger.
- Restart restore/replay is disabled by `--manual-recovery`. For beta evals, keep the MCP process running for the
  whole eval or explicitly use snapshot, restore, replay, and replay-verification tools.
- Persisted snapshots can be listed and loaded through MCP with
  `rtg_list_persisted_snapshots` and `rtg_load_persisted_snapshot`; agents do not need direct
  filesystem access for snapshot readback.

## Tool Primer

All RTG MCP tools return JSON objects:

```json
{"ok": true, "result": {}}
```

Successful mutating controller results include `result.transaction_id` and, when SQL audit
recording succeeded, `result.ledger_position`.

Validation failures return:

```json
{
  "ok": false,
  "error": {"type": "RtgControllerValidationFailed", "message": "..."},
  "transaction_id": "...",
  "validation_report": {"accepted": false, "findings": []}
}
```

Other expected failures return the same `ok: false` and `error` shape without
`validation_report`; use `rtg_validate_graph` with `migration_ids` when a cutover needs
projected-state findings.

Expected failures may include `error.diagnostic`, a structured generic correction object. Agents
should use `diagnostic.path`, `diagnostic.remedy`, `diagnostic.accepted_fields`,
`diagnostic.minimal_example`, and `diagnostic.guide_topics` to repair the next tool call. These
diagnostics teach RTG/MCP contracts only; they must not contain beta-specific schema answers.

References use exactly one identity:

```json
{"local_ref": "component-graph"}
```

or:

```json
{"resource_id": "11111111-1111-1111-1111-111111111111"}
```

`local_ref` values are scoped to one request. Use them to connect objects created together in the
same call. Use returned `resource_id` values for later calls, especially when adding links to
existing objects.

Prefer `rtg_stage_schema_migration` for schema-only work. If you use the advanced
`rtg_stage_knowledge_changes` surface, candidates must be non-live and referenced by a migration:

```json
{
  "knowledge_changes": {
    "schema_changes": {
      "definition_writes": [
        {
          "ref": {"resource_id": "11111111-1111-1111-1111-111111111111"},
          "definition": {
            "uuid": "11111111-1111-1111-1111-111111111111",
            "kind": "anchor",
            "type_key": "Component",
            "description": "A software component.",
            "payload": {"required_data_types": ["ComponentFacts"]},
            "system": {"live": false}
          }
        }
      ]
    },
    "migration_changes": {
      "migration_writes": [
        {
          "ref": {"resource_id": "11111111-1111-1111-1111-111111111112"},
          "migration": {
            "migration_id": "11111111-1111-1111-1111-111111111112",
            "description": "Make initial schema live.",
            "status": "ready",
            "schema_make_live": ["11111111-1111-1111-1111-111111111111"]
          }
        }
      ]
    }
  }
}
```

When staging non-live graph candidates, include every candidate object ID in the migration's
`graph_make_live` list: anchors, associated data objects, and links. Strict staging validates
migration records introduced in the same request against their projected cutover state, so invalid
candidate data should return `validation_report` findings before the records are staged.

Live graph writes go through `rtg_apply_live_graph_changes`:

```json
{
  "graph_changes": {
    "anchor_writes": [
      {
        "ref": {"local_ref": "component-graph"},
        "type": "Component",
        "display_name": "component.rtg.graph"
      }
    ],
    "data_object_writes": [
      {
        "ref": {"local_ref": "component-graph-facts"},
        "type": "ComponentFacts",
        "mode": "merge",
        "properties": {"component_id": "component.rtg.graph", "status": "accepted"},
        "anchor_refs": [{"local_ref": "component-graph"}]
      }
    ]
  }
}
```

Invalid live graph writes are the simplest way to exercise bad-write recovery: strict validation
returns `ok: false`, a controller transaction ID, and a `validation_report` with blocking findings.

Queries use anchor buckets plus optional associated data requirements:

```json
{
  "query_spec": {
    "anchor_buckets": [{"name": "component", "anchor_type_keys": ["Component"]}],
    "data_requirements": [
      {
        "name": "facts",
        "anchor_bucket": "component",
        "data_type_key": "ComponentFacts",
        "predicates": [
          {"path": ["status"], "operator": "equals", "value": "accepted"}
        ]
      }
    ],
    "return_spec": {
      "anchor_buckets": ["component"],
      "data_requirements": ["facts"],
      "properties": [["facts", ["component_id"]]]
    }
  },
  "query_options": {"live_filter": "live"}
}
```

## Agent Operator Card

Agents should operate the RTG MCP server in this order:

1. Validate the connection with `rtg_validate_graph({})`.
2. Read app state with `rtg_get_system_state({})` and follow `recommended_next_steps`.
3. Fetch examples with `rtg_get_usage_guide`; use `mcp_bootstrap_checklist` if the agent does
   not have repo docs, `workflow_patterns` for common RTG workflows, or `request_patterns` when
   the user prompt gives a goal but not a tool sequence.
4. Discover available anchor types with `rtg_discover_anchor_types`.
5. Read schema details with `rtg_get_schema_pack` before writing data or building queries.
6. Stage initial schema through `rtg_stage_schema_migration`; use `rtg_stage_knowledge_changes`
   only for advanced normalized batches.
7. Make staged schema live with `rtg_apply_migration_cutover`.
8. Resolve existing UUIDs with `rtg_resolve_anchor_by_fact` or
   `rtg_get_usage_guide({"topic": "lookup_examples"})` query payloads before link writes.
9. Dry-run risky graph writes with `rtg_validate_live_graph_changes` or
   `rtg_validate_live_anchor_records`; use `rtg_apply_live_anchor_records` for repeated anchor
   plus required-facts ingestion, `rtg_apply_live_graph_changes` for lower-level CRUD and links,
   and answer questions with `rtg_execute_query`.
10. Preserve recovery evidence with `rtg_persist_system_snapshot`,
   `rtg_list_persisted_snapshots`, `rtg_load_persisted_snapshot`, `rtg_restore_from_snapshot`,
   `rtg_replay_ledger`, `rtg_verify_replay_from_ledger`, and `rtg_list_migration_history`.

Dry-run validation tools accept `validation_options.tracks` and `validation_options.finding_limit`;
mutation tools use `validation_mode`. Use `return_snapshot:false` for compact snapshot
persistence/load. When verifying recovery, report `state_equivalent_to_live` with the replayed and
live domain-state digests; report `ledger_cursor_equivalent_to_live` separately, and use the replay
accounting plus `replay_window` to explain which ledger records were scanned, eligible, replayed,
administrative, terminal, or failed/rejected.
`rtg_get_system_state.migration_counts_by_status` is the current migration-store view; use
`rtg_list_migration_history` for ledger-backed migration audit after cutover or abandonment.

Use schema-required fields and link type rules for beta blocking validation first. Add constraints
when the rule fits one of the documented v1 payloads:

- `query_pattern`: `constraint_changes.constraint_writes[{ref, constraint}]`, where
  `constraint.kind` is `query_pattern`, `target_type_keys` names the affected schema types, and
  `payload` contains `query_spec` plus `expectation` such as `must_match_at_least_one` or
  `must_match_none`.
- `cardinality`: same wrapper shape, with `constraint.kind` set to `cardinality` and `payload`
  containing `query_spec`, `counted_binding`, optional `minimum` or `maximum`, and optional
  `group_by_bindings` when the bound must be enforced independently for each unique binding tuple.

Constraint candidates must be non-live and listed in the migration's `constraint_make_live`.
Do not invent new constraint kinds from prose alone.

## Recommended Sequenced Prompts

Use these prompts in order for the first beta. They isolate failure modes better than the single
combined prompt.

### Prompt 1: Bootstrap Model

You have a fresh RTG MCP server. Build only the initial live model. Design schema and any
useful blocking constraints for components, implementation roots, invariants, tests, evidence,
open questions, work items, and change proposals. Call `rtg_validate_graph` first, then
`rtg_get_system_state`. Use
`rtg_stage_schema_migration` for schema definitions and `rtg_stage_knowledge_changes` only when
you need advanced constraint candidates tied to a ready migration. Use `rtg_apply_migration_cutover`
to make them live. Use `rtg_discover_anchor_types`, `rtg_get_schema_pack`, and
`rtg_validate_graph` to verify the result. Stop after summarizing what schema is live and which
transaction IDs or ledger positions support it.

### Prompt 2: Ingest And Query Live Graph

Use the live schema from Prompt 1. Ingest these facts with `rtg_apply_live_graph_changes`:
`component.rtg.graph` is accepted, has implementation root `components/rtg/graph`, owns invariant
`global_uuid_uniqueness`, and has test evidence at
`components/rtg/graph/tests/test_rtg_graph_contract.py`; `component.rtg.schema` is accepted,
has implementation root `components/rtg/schema`, owns invariant `live_type_unique`, and has no
open questions; `component.rtg.discovery` is draft, is implemented at
`components/rtg/discovery` but remains outside the current Vellis application composition, and has open question `Should aliases or search terms be part
of curated discovery views?`.

Then use `rtg_execute_query` to answer: which accepted components have invariants without test
evidence, which implementation roots are affected by changing the component schema, and which
draft components have unresolved open questions. Stop after returning the query evidence and
any uncertainty.

### Prompt 3: Evolve Evidence Model

The human adds data that does not fit the current evidence schema: `component.rtg.controller`
has ledger evidence with transaction ID, ledger position, operation name, and whether replay can
use it. Propose a non-live replacement evidence schema and a migration record that makes it live
and retires the old evidence schema. Include every non-live graph candidate ID in
`graph_make_live`, including the evidence anchor, evidence facts object, component anchor, component
facts object, and links.

Submit one intentionally invalid evidence item first. Whether the invalid item is a live write or a
strict staged candidate, expect `ok: false` with `validation_report`; repair the payload, retry,
and apply migration cutover. Query post-cutover state to show ledger evidence is represented, older
test evidence remains usable, and accepted components without evidence remain discoverable. Export
or persist a snapshot and produce a concise human brief.

## Single Prompt

For a less-guided eval, use
`docs/guides/vellis/evals/rtg-agent-affordance-eval-prompt.md` after the MCP server is connected. Prefer the
sequenced prompts first while the RTG tool surface is still new.

For the initial individual open-source use case, use
`docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md`. That prompt asks the agent to model one
person's personal and professional domains, exercise realistic bad writes and recovery, and
verify snapshot or ledger evidence. The known-good walkthrough is
`docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md`.

## Scoring

- Pass: The agent uses schema, constraints, validation, migration, query, snapshot, and ledger
  affordances in their intended roles; repairs validation failures without weakening rules; and
  produces traceable human-facing conclusions.
- Partial: The agent uses graph and query but treats schema evolution, validation, migration, or
  evidence as prose instead of RTG-managed state.
- Fail: The agent bypasses migrations for schema evolution, stores schema/constraint/migration
  data as ordinary graph facts, ignores validation reports, or answers multi-hop questions by
  manually scanning all objects.

## Troubleshooting

- If the MCP client cannot import `apps.rtg_knowledge_graph`, use the `uv --directory` command
  from `mcp.client_config`.
- If an external local agent should not launch a subprocess, run `just rtg-mcp-http` and give it
  the URL from `mcp.transports.localhost_http.url`.
- If graph writes fail with `unknown_type`, bootstrap and cut over the schema first.
- If an MCP-only agent needs schema or query examples, call `rtg_get_usage_guide` instead of
  asking it to read repository files.
- If staging fails because a candidate is not migration-scoped, add the candidate UUID to the
  migration record's `schema_make_live`, `constraint_make_live`, or `graph_make_live` list.
- If staging non-live graph candidates, put all candidate anchor, data object, and link UUIDs in
  `graph_make_live`; listing only anchors is insufficient.
- If a later call needs to connect to an existing object, query or read the object and use its
  `resource_id`; do not reuse an old `local_ref` from a previous request.
- If cutover fails without `validation_report`, call `rtg_validate_graph` with the migration ID
  to get projected-state findings before retrying.
- If a failed or exploratory migration should not be retried, call `rtg_abandon_migration` to
  record abandonment and prune safe non-live candidates.
- If a validation report blocks staging or cutover, repair the staged model or graph data and
  retry; do not switch to `validation_mode: "skip"` to make invalid data pass.
- Use `validation_mode: "skip"` only for controlled recovery or for an intentional failed-cutover
  test where the next strict cutover call is expected to prove live-state preservation.
