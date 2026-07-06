# RTG Knowledge Graph

`rtg_knowledge_graph` is the first Vellis application. It is a local RTG knowledge system that
humans can use with an AI agent, or that an agent can operate directly, while also demonstrating
how Vellis components compose behind an explicit configuration and launch boundary.

The app wires the in-process RTG stack:

- `component.storage.json_file` as local JSON document storage.
- `component.storage.sql` as SQLite-backed controller ledger storage.
- `component.rtg.controller` as the black-box RTG orchestration API.
- RTG graph, schema, constraints, migration, validation, and query implementations behind the controller.

It exposes the controller through thin local MCP adapters. For beta and open-source
evaluation, that MCP surface is the turnkey application interface: agents can create and evolve
schema, write and query graph data, recover from validation failures, persist snapshots, and replay
the controller ledger. MCP remains an application interface; RTG component internals and controller
workflow stay in the component stack.

The default beta scenario is the individual life graph in
`docs/evals/rtg-individual-life-graph-beta-prompt.md`. The component-repository affordance prompt
is the advanced engineering-system example.

## Structure

```text
apps/rtg_knowledge_graph/
  composition.py  # component wiring
  config.py       # app configuration
  main.py         # CLI entry point
  mcp_codec.py    # JSON/dataclass adapter for MCP inputs and outputs
  mcp_server.py   # FastMCP server registration and launch
  mcp_toolset.py  # directly testable controller tool handlers
  runner.py       # temporary launch smoke behavior
  tests/          # full-app tests
```

Keep new component wiring in `composition.py`. Keep launch smoke behavior in `runner.py`. When an RTG Knowledge Graph facade component exists, wire that facade in `composition.py` and move domain/application rules into the component stack instead of this reference app shell.

## Configuration

The app storage root can be supplied through:

- CLI: `--storage-root <path>`
- environment: `RTG_KNOWLEDGE_GRAPH_STORAGE_ROOT`

The controller ledger SQLite database can be supplied through:

- CLI: `--sql-database-path <path>`
- environment: `RTG_KNOWLEDGE_GRAPH_SQL_DATABASE_PATH`

If neither is provided, the app uses:

```text
.data/rtg_knowledge_graph/json_file
.data/rtg_knowledge_graph/controller.sqlite
```

## Launch

```sh
just rtg
```

The current launch writes `system/app_manifest.json` through JSON File Storage and returns a status summary. This is a smoke path for composition, not the long-term RTG Knowledge Graph application facade.

When installed in the local uv environment, the same app is available through the console script:

```sh
uv run vellis-rtg-knowledge-graph --json
```

## MCP Interface

For a first beta run, use a fresh explicit storage root:

```sh
just rtg-eval-info /tmp/vellis-beta-001
```

Copy the generated `mcp.client_config` into your MCP client, start the server, then make the
metadata's `mcp.first_call`. For the default config, that first call is `rtg_validate_graph` with
`{}`. A fresh server should return `ok: true`, `result.accepted: true`, and no findings.
Then call `rtg_get_system_state` with `{}` so the agent can tell whether the app is empty, already
bootstrapped, has staged work, or needs ledger replay.

Then give the agent the recommended life-graph beta prompt. A known-good walkthrough lives in
`docs/evals/rtg-beta-known-good-walkthrough.md`. Agents without repository access can fetch generic
bootstrap, schema-staging, live-write, lookup, query, recovery, and audit examples directly through
`rtg_get_usage_guide`; those examples teach payload shape and tool sequence rather than supplying a
scenario-specific schema.

Print default MCP metadata without starting the long-running server:

```sh
just rtg-mcp-info
```

For a beta eval with another fresh explicit storage root:

```sh
just rtg-eval-info /tmp/vellis-beta-002
```

The metadata includes `mcp.launch_mode`, `mcp.client_config`, `mcp.transports`, a cwd-independent
stdio client configuration, `mcp.first_call`, `mcp.eval_prompts`, and
`mcp.recommended_eval_prompt`.
In a repository checkout, `mcp.launch_mode` is `repository_checkout` and the generated client
configuration uses `uv --directory <repo-root>` with the absolute repo, storage-root, and
SQLite paths already filled in. Always start from this generated block rather than
hand-writing paths. The metadata command runs the app composition once, so it creates the
storage root, `controller.sqlite`, and `system/app_manifest.json` as a side effect.
When the app is launched from an installed package without the repository docs available,
`mcp.launch_mode` is `installed_package`; the server launch remains available, while eval
prompt paths are reported as unavailable.
After configuring an MCP client, use the first-call tool as the connection smoke check before
giving the agent an eval prompt.

### Localhost HTTP MCP

Use stdio when your MCP client should launch and own the server process. Use localhost HTTP when
the Vellis app should keep running independently and another same-machine agent should attach to
it by URL.

Print URL-based MCP client config:

```sh
just rtg-mcp-http-info /tmp/vellis-beta-001 127.0.0.1 8765 /mcp
```

Launch the unauthenticated localhost HTTP server:

```sh
just rtg-mcp-http /tmp/vellis-beta-001 127.0.0.1 8765 /mcp
```

Then configure the other local agent with:

```json
{
  "mcpServers": {
    "rtg_knowledge_graph": {
      "url": "http://127.0.0.1:8765/mcp",
      "transport": "http"
    }
  }
}
```

The same config is emitted at `mcp.transports.localhost_http.client_config`. Keep HTTP mode bound
to `127.0.0.1`; it is intentionally unauthenticated and intended only for local agents on the same
machine.

Agent-facing RTG MCP usage guidance lives in
`.agents/skills/rtg-knowledge-graph-mcp/SKILL.md`. Claude Code sees the same source through the
`.claude/skills/rtg-knowledge-graph-mcp` symlink; run `just skills-sync` if the link is missing.

The MCP surface includes low-level controller tools plus agent-facing response shaping:

- Use `rtg_stage_schema_migration` for normal schema bootstrap/evolution and
  `rtg_stage_knowledge_changes` only for advanced normalized batches.
- Use `rtg_validate_live_anchor_records` and `rtg_apply_live_anchor_records` for repeated
  anchor-with-required-facts ingestion; they compile to canonical `graph_changes`.
- Use `rtg_validate_live_graph_changes` or `rtg_validate_live_anchor_records` before risky
  writes. Their `validation_options` support `tracks` and `finding_limit`; mutation tools use
  `validation_mode`.
- Use `rtg_resolve_anchor_by_fact` for common exact anchor lookups before link writes; it returns
  the submitted `rtg_execute_query` payload so query remains the canonical read language.
- Use `rtg_execute_query` with `response_options: {"format": "properties_only"}` for compact
  human-facing rows when UUID bindings are not needed.
- Use `rtg_persist_system_snapshot(..., return_snapshot:false)` and
  `rtg_load_persisted_snapshot(..., return_snapshot:false)` to keep MCP transcripts compact.
- Use replay `details.replay_window` and replay verification `replay_window` to explain which
  ledger positions were considered, especially when starting from `start_snapshot_path`.
- Cold agents can call `rtg_get_usage_guide` with `topic: "workflow_patterns"` for common RTG
  operating sequences, or `topic: "request_patterns"` to map ordinary user requests to workflow
  IDs. `rtg_get_system_state` returns `recommended_workflows` for the current state.

Sample generated `mcp.client_config` (your paths will differ):

```json
{
  "mcpServers": {
    "rtg_knowledge_graph": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/your/vellis/checkout",
        "run",
        "python",
        "-m",
        "apps.rtg_knowledge_graph",
        "serve-mcp",
        "--transport",
        "stdio",
        "--storage-root",
        "/tmp/vellis-beta-001",
        "--sql-database-path",
        "/tmp/vellis-beta-001/controller.sqlite"
      ],
      "cwd": "/absolute/path/to/your/vellis/checkout"
    }
  }
}
```

Wiring the stdio server into common MCP clients:

- Claude Desktop (macOS): merge the generated `mcpServers` block into
  `~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude
  Desktop.
- Claude Code: run `claude mcp add rtg_knowledge_graph -- <command and args from the
  generated config>`, or place the generated `mcpServers` block in a project `.mcp.json`.
- Other clients: any MCP client that accepts JSON stdio server configuration can consume
  the generated block directly. Clients that support remote MCP servers can instead use
  `mcp.transports.localhost_http.client_config`.

Stdio MCP mode must not print normal app status to stdout because stdout carries JSON-RPC messages. The app only prints status for normal launches and `serve-mcp --dry-run`.

For manual stdio debugging, launch the server directly:

```sh
just rtg-mcp
```

V1 beta eval state semantics:

- Live RTG graph, schema, constraint, and migration state is in memory for the running MCP process.
- The storage root persists the app manifest, persisted snapshots, queued ledger failures, and the SQL ledger.
- Restart restore/replay is not automatic. Keep the server running for one eval or explicitly use snapshot, restore, and replay tools.
- The agent affordance eval prompt lives in `docs/evals/`. Generic operational examples are also
  exposed through `rtg_get_usage_guide` for MCP-only agents.

Turnkey MCP tool groups:

- Data CRUD and dry-run: `rtg_apply_live_graph_changes`, `rtg_validate_live_graph_changes`,
  `rtg_apply_live_anchor_records`, `rtg_validate_live_anchor_records`
- Agent guidance and state: `rtg_get_system_state`, `rtg_get_usage_guide`
- Schema and data evolution: `rtg_stage_schema_migration`, `rtg_stage_knowledge_changes`,
  `rtg_apply_migration_cutover`, `rtg_abandon_migration`
- Query and discovery: `rtg_resolve_anchor_by_fact`, `rtg_execute_query`,
  `rtg_discover_anchor_types`, `rtg_get_schema_pack`
- Reads and migration inspection: `rtg_get_object`, `rtg_list_migrations`, `rtg_get_migration`
- Audit and recovery: `rtg_export_system_snapshot`, `rtg_persist_system_snapshot`,
  `rtg_list_persisted_snapshots`, `rtg_load_persisted_snapshot`, `rtg_restore_from_snapshot`,
  `rtg_replay_ledger`, `rtg_verify_replay_from_ledger`, `rtg_list_migration_history`,
  `rtg_flush_ledger_failures`

Full exposed MCP tool list:

- `rtg_apply_live_graph_changes`
- `rtg_validate_live_graph_changes`
- `rtg_apply_live_anchor_records`
- `rtg_validate_live_anchor_records`
- `rtg_get_system_state`
- `rtg_get_usage_guide`
- `rtg_stage_schema_migration`
- `rtg_stage_knowledge_changes`
- `rtg_apply_migration_cutover`
- `rtg_abandon_migration`
- `rtg_execute_query`
- `rtg_resolve_anchor_by_fact`
- `rtg_get_object`
- `rtg_list_migrations`
- `rtg_get_migration`
- `rtg_validate_graph`
- `rtg_discover_anchor_types`
- `rtg_get_schema_pack`
- `rtg_export_system_snapshot`
- `rtg_persist_system_snapshot`
- `rtg_list_persisted_snapshots`
- `rtg_load_persisted_snapshot`
- `rtg_replay_ledger`
- `rtg_verify_replay_from_ledger`
- `rtg_list_migration_history`
- `rtg_flush_ledger_failures`
- `rtg_restore_from_snapshot`

MCP tool responses use:

- success: `{"ok": true, "result": ...}`
- expected failure: `{"ok": false, "error": {"type": "...", "message": "..."}}`

Expected failures may also include `error.diagnostic`, a structured, generic correction object
with fields such as `code`, `category`, `path`, `problem`, `remedy`, `accepted_fields`,
`minimal_example`, `guide_topics`, `safe_to_retry`, and `mutation_state`. Existing clients can
continue reading `error.type` and `error.message`; agents should use `diagnostic.remedy` and
`diagnostic.guide_topics` to repair the next tool call without guessing.

Validation failures also include `transaction_id` and `validation_report` when the controller
assigned them. Successful mutating controller results include a `transaction_id` and, when SQL
audit recording succeeded, a `ledger_position` inside `result`.

Agent operation notes:

- `local_ref` values are request-local. Use `resource_id` values returned by earlier calls when
  linking to existing graph objects.
- Use `rtg_resolve_anchor_by_fact` for exact fact lookups before link writes, or
  `rtg_get_usage_guide` with `topic: "lookup_examples"` when a full query payload is more useful.
  Use `rtg_validate_live_graph_changes` before risky imports or recovery probes when validation
  evidence should not mutate planning data or ledger.
- Use `rtg_get_usage_guide` with `topic: "workflow_patterns"` or `topic: "request_patterns"` when
  the user prompt gives a goal but not an RTG operating sequence.
- `rtg_stage_schema_migration` is the preferred schema bootstrap/evolution tool for MCP-only
  agents. It accepts schema definitions with type-key payload references and generates candidate
  UUIDs for migration membership.
- Non-live graph candidates staged through `rtg_stage_knowledge_changes` must be referenced by the
  migration, including anchor, data object, and link candidate IDs in `graph_make_live`.
- Invalid live graph writes and strict staged migration candidates return validation reports before
  mutation. Use `validation_mode: "skip"` only for controlled recovery or intentional failed-cutover
  tests, then use strict cutover to prove the live state is preserved.
- Failed cutovers preserve live state and mark the migration failed when possible. Use
  `rtg_abandon_migration` when exploratory staged work should be retired instead of retried.
- Persisted snapshots can be listed and loaded through MCP; do not require an external agent to
  read files directly from the storage root. Use `return_snapshot:false` for compact persisted
  snapshot responses and `start_snapshot_path` for path-based replay.
- `rtg_verify_replay_from_ledger` checks replay in scratch state without mutating the live
  controller. Use `rtg_list_migration_history` for durable audit after successful migrations have
  been pruned from the live migration store.
- Constraint records are part of the RTG component stack. Use documented `query_pattern` and
  `cardinality` payloads through `constraint_changes.constraint_writes`; do not invent new
  constraint kinds from prose alone.

Manual eval materials:

- `docs/evals/rtg-beta-known-good-walkthrough.md`
- `docs/evals/rtg-agent-affordance-eval-runbook.md`
- `docs/evals/rtg-agent-affordance-eval-prompt.md`
- `docs/evals/rtg-individual-life-graph-beta-prompt.md`
