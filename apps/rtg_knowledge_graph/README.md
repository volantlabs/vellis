# RTG Knowledge Graph

`rtg_knowledge_graph` is the first Vellis application. It is a local RTG knowledge system that
humans can use with an AI agent, or that an agent can operate directly, while also demonstrating
how Vellis components compose behind an explicit configuration and launch boundary.

The app starts the accepted local Bibliotek message runtime and registers named occurrences for:

- `component.storage.json_file` as local JSON document storage.
- `component.rtg.controller` as the runtime-neutral RTG saga and coordinated-snapshot API.
- RTG graph, schema, constraints, migration, validation, and query components.
- the Vellis façade, curated MCP gateway, starter installer, and application runner.

It exposes the modeled Vellis application façade through a curated generic MCP gateway. FastMCP
maps stdio/HTTP protocol inputs to the generated registration inventory; the gateway validates and
dispatches runtime messages to the façade, which delegates canonical operations to the controller
and owns application request shaping and response policy. The façade and controller boundaries are
runtime-managed. In the application composition, the accepted controller receives only runtime
proxies for its retained collaborators; direct construction remains available to library consumers.
For beta and open-source evaluation, that MCP surface is the turnkey application interface: agents
can create and evolve schema, write and query graph data, recover from validation failures, persist
snapshots, and inspect runtime-backed reconstruction and history. RTG component internals and
controller workflow remain in the component stack.

Ordinary installations include the modeled Everyday Life ontology and recover durable state
automatically. Evaluation prompts deliberately opt into blank/manual-recovery mode.

## Structure

```text
apps/rtg_knowledge_graph/
  composition.py  # component wiring
  config.py       # app configuration
  gateway_registration.py # generated MCP registration loader
  main.py         # CLI entry point
  mcp_codec.py    # JSON/dataclass adapter for MCP inputs and outputs
  mcp_server.py   # FastMCP server registration and launch
  mcp_toolset.py  # directly testable Vellis façade handlers
  runner.py       # application status and manifest launch behavior
  tests/          # full-app tests
```

Keep component wiring in `composition.py` and launch/status behavior in `runner.py`. Application
request shaping belongs to the modeled Vellis façade and its `mcp_toolset.py` realization; reusable
RTG invariants and orchestration remain in Bibliotek components and the controller.

## Configuration

The app storage root can be supplied through:

- CLI: `--storage-root <path>`
- environment: `RTG_KNOWLEDGE_GRAPH_STORAGE_ROOT`

The component runtime SQLite database can be supplied through:

- CLI: `--runtime-database-path <path>`
- environment: `RTG_KNOWLEDGE_GRAPH_RUNTIME_DATABASE_PATH`

If neither is provided, the app uses:

```text
.data/rtg_knowledge_graph/json_file
.data/rtg_knowledge_graph/runtime.sqlite
```

The runtime database is an internal bootstrap ledger, not a message-managed SQL occurrence. It is
the authority for cross-component chronology and reconstruction. Earlier controller ledgers are
not imported; transfer their managed state through a coordinated snapshot into a new data root.

## Launch

```sh
just rtg
```

The normal non-MCP launch writes `system/app_manifest.json` through JSON File Storage and returns a
status summary. It is a composition and configuration smoke path; MCP is the primary agent-facing
application interface.

When installed in the local uv environment, the same app is available through the console script:

```sh
uv run vellis setup
uv run vellis doctor
```

## MCP Interface

The ordinary first run is:

```sh
uv run vellis setup
```

Setup reconstructs managed state from committed runtime effects, installs the starter schema only
for a genuinely empty graph, validates
the result, and registers the stdio MCP server user-wide with Codex, Claude Code, Claude Desktop,
or a generic JSON client. The generated launch uses absolute paths and the client owns the server
process. The same `uv run vellis setup` path works on native Windows without Bash or `just`. Use
`uv run vellis doctor` for a non-destructive check.

The `setup --json` and `doctor --json` forms are non-interactive interfaces for scripts and agents.
They emit exactly one JSON document on stdout and never prompt. Pass `--yes` to authorize setup and
pass `--client` when automatic detection would be ambiguous, for example:

```sh
uv run vellis setup --json --client codex --yes
uv run vellis doctor --json --client codex
```

`mcp-config`, `just rtg-mcp`, `just rtg-mcp-info`, and the evaluation prompts remain developer and
protocol-debugging surfaces. Evaluations may use `--empty --manual-recovery` to inspect explicit
runtime reconstruction behavior before accepting normal application traffic.

### Localhost HTTP MCP

Use stdio when your MCP client should launch and own the server process. Use localhost HTTP when
the Vellis app should keep running independently and another same-machine agent should attach to
it by URL.

Print URL-based MCP client config:

```sh
just rtg-mcp-http-info .data/vellis-beta-001 127.0.0.1 8765 /mcp
```

Launch the unauthenticated localhost HTTP server:

```sh
just rtg-mcp-http .data/vellis-beta-001 127.0.0.1 8765 /mcp
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

On restart, recovered nonempty schema that is not the exact deterministic Everyday Life ontology is
served as `custom`, even when it uses keys such as `Person`, `Project`, or `Task`. Type-key overlap
never installs or overlays starter schema. Reuse of a deterministic ontology UUID for an
incompatible definition, or a partial deterministic ontology installation, fails closed with
`vellis doctor` guidance and leaves recovered state unchanged. `--empty` disables starter
installation; it does not reject healthy custom state.

Agent-facing RTG MCP usage guidance lives in
`.agents/skills/rtg-knowledge-graph-mcp/SKILL.md`. Claude Code sees the same source through the
`.claude/skills/rtg-knowledge-graph-mcp` symlink; run `just skills-sync` if the link is missing.

The MCP surface includes low-level controller tools plus agent-facing response shaping:

- Use `rtg_stage_schema_migration` for normal schema bootstrap/evolution and
  `rtg_stage_knowledge_changes` only for advanced normalized batches. Definition `(kind,
  type_key)` pairs must be unique within one ergonomic request; compact results correlate every
  generated candidate UUID through `generated_schema_ids["kind:type_key"]`.
- Use `rtg_validate_live_anchor_records` and `rtg_apply_live_anchor_records` for repeated
  anchor-with-required-facts ingestion; they compile to canonical `graph_changes`. Successful
  applies default to `response_options: {"format":"compact"}`, return durable UUIDs in
  `generated_ids`, and retain generated fact-position mapping. Use `format:"full"` only when the
  submitted canonical payload is needed for debugging.
- Use `rtg_validate_live_graph_changes` or `rtg_validate_live_anchor_records` before risky
  writes. Their `validation_options` support `tracks` and `finding_limit`; mutation tools use
  `validation_mode`.
- Use `rtg_resolve_anchor_by_fact` for common exact anchor lookups before link writes; it returns
  the submitted `rtg_execute_query` payload so query remains the canonical read language.
- Use `rtg_execute_query` with `response_options: {"format": "properties_only"}` for compact
  human-facing rows when UUID bindings are not needed. Non-aggregate rows contain selected
  `properties`; aggregate rows retain `group_by` and caller-named count fields directly. Response
  `kind` is `full` or `properties_only`. Binding names are unique across anchor, link, and data
  requirements, and aggregation cannot be combined with `distinct_rows`.
- Use `rtg_persist_system_snapshot(..., return_snapshot:false)` and
  `rtg_load_persisted_snapshot(..., return_snapshot:false)` to keep MCP transcripts compact.
  Direct snapshot exports identify their response as `kind:"full"` or `kind:"summary"`.
- Use `rtg_verify_replay_from_ledger` to inspect the verified latest-startup runtime reconstruction
  report. Verify an earlier cursor only in an isolated copy of the complete data root.
- Use `rtg_list_migration_history` for successful, abandoned, rejected, and failed schema
  proposals even when current migration-store counts are zero.
- Use `rtg_get_usage_guide(topic="capabilities")` for lanes, mutation/runtime behavior, dry-run
  predecessors, and audience metadata for all registered tools.
- Query options support deterministic `limit`/`offset` pagination and `distinct_rows`; return
  aggregation supports grouping returned property paths and distinct UUID `count`.
- Cold agents can call `rtg_get_usage_guide` with `topic: "workflow_patterns"` for common RTG
  operating sequences, or `topic: "request_patterns"` to map ordinary user requests to workflow
  IDs. `rtg_get_system_state` returns `recommended_workflows` for the current state.

### Manual client configuration (advanced fallback)

`vellis setup` performs client registration in the ordinary path. The following generated shape is
for client integration development or unsupported clients; your paths will differ:

```json
{
  "mcpServers": {
    "rtg_knowledge_graph": {
      "command": "/absolute/path/to/uv",
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
        "/absolute/path/to/your/vellis/checkout/.data/rtg_knowledge_graph/json_file",
        "--runtime-database-path",
        "/absolute/path/to/your/vellis/checkout/.data/rtg_knowledge_graph/runtime.sqlite"
      ],
      "cwd": "/absolute/path/to/your/vellis/checkout"
    }
  }
}
```

Manual fallback locations and commands are:

- Claude Desktop (macOS): merge the generated `mcpServers` block into
  `~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude
  Desktop.
- Claude Desktop (Windows): merge it into
  `%APPDATA%\Claude\claude_desktop_config.json`, then restart Claude Desktop.
- Claude Code: run `claude mcp add rtg_knowledge_graph -- <command and args from the
  generated config>`, or place the generated `mcpServers` block in a project `.mcp.json`.
- Codex: use `mcp-config --client codex`, run the exact `codex mcp add` command it prints, then
  restart or reload Codex. Codex stores MCP entries in `~/.codex/config.toml`.
- Other clients: any MCP client that accepts JSON stdio server configuration can consume
  the generated block directly. Clients that support remote MCP servers can instead use
  `mcp.transports.localhost_http.client_config`.

Stdio MCP mode must not print normal app status to stdout because stdout carries JSON-RPC messages. The app only prints status for normal launches and `serve-mcp --dry-run`.

For manual stdio debugging, launch the server directly:

```sh
just rtg-mcp
```

This command intentionally appears to wait: an stdio MCP server stays attached to its client and
uses standard input/output for JSON-RPC. It is not the normal setup step and should not be running
at the same time as a client-owned stdio instance.

### Setup troubleshooting

- **Windows asks for Bash, WSL, `just`, or a manual Python install:** stop using the convenience
  recipe and run `uv run vellis setup` from PowerShell. `uv` manages Python 3.14 and installs the
  locked dependencies.
- **Setup or the client reports a path/configuration problem:** run `uv run vellis doctor` (or use
  `uv run vellis doctor --json --client CLIENT` for a non-interactive, agent-readable report).
  Setup records the absolute `uv`, repository, data, and SQLite paths rather than relying on the
  GUI application's working directory or `PATH`.
- **The config command prints pages of tool metadata:** that is the diagnostic `*-info` command.
  Use `mcp-config` for the small client block.
- **The raw server command seems frozen:** stdio is waiting for JSON-RPC on standard input. Stop it
  and let the configured MCP client own the process.
- **The client shows no RTG tools:** verify that the generated top-level `mcpServers` object was
  merged at the level required by that client, then fully restart or reload the client. Inspect its
  MCP process logs if the first `rtg_validate_graph({})` call is unavailable.
- **Dependency installation fails:** run `uv sync` in the checkout to surface the package error
  directly. The lock includes Windows x64, ARM64, and 32-bit wheels for the native RE2 dependency;
  include the OS, architecture, and complete `uv sync` output in a bug report.

Runtime recovery semantics:

- Live RTG graph, schema, constraint, and migration state is reconstructed from committed canonical
  effects in the runtime ledger before an ordinary MCP server accepts connections.
- Recovery fails closed if reconstruction, binding compatibility, or resulting graph validation
  fails.
- An indeterminate causal trace also closes ordinary ingress across restart until verified
  reconstruction succeeds. A trace is not terminal until every accepted causal descendant has
  completed.
- `--manual-recovery` is a developer/evaluation mode that leaves recovery explicitly pending;
  ordinary façade and component calls remain closed, and only the explicitly recovery-authorized
  `rtg_replay_ledger` façade action may initiate reconstruction.
- Earlier Vellis installations move state only through a validated coordinated snapshot restored
  into a fresh current data root; see [snapshot transfer](../../docs/guides/vellis/snapshot-transfer.md).
- The agent affordance eval prompt lives in `docs/guides/vellis/evals/`. Generic operational examples are also
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

The canonical 27-tool inventory, typed façade mappings, parameters, defaults, outcomes, and
failures are generated from the model in the
[Vellis application reference](../../generated/reference/vellis/index.md).

MCP tool responses use:

- success: `{"ok": true, "result": ...}`
- expected failure: `{"ok": false, "error": {"type": "...", "message": "..."}}`

Expected failures may also include `error.diagnostic`, a structured, generic correction object
with fields such as `code`, `category`, `path`, `problem`, `remedy`, `accepted_fields`,
`minimal_example`, `guide_topics`, `safe_to_retry`, and `mutation_state`. Existing clients can
continue reading `error.type` and `error.message`; agents should use `diagnostic.remedy` and
`diagnostic.guide_topics` to repair the next tool call without guessing.

Validation failures include modeled validation evidence. Runtime trace identity and terminal
position are envelope/history metadata, not controller-domain result fields; system state exposes
the current runtime health and cursor.

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
  snapshot responses. Restore a snapshot only through `rtg_restore_from_snapshot`; snapshots are
  not runtime-reconstruction seeds.
- `rtg_verify_replay_from_ledger` reports available verified startup reconstruction evidence
  without mutating live state. Use `rtg_list_migration_history` for runtime-trace audit after
  successful migrations have been pruned from the live migration store.
- Constraint records are part of the RTG component stack. Use documented `query_pattern` and
  `cardinality` payloads through `constraint_changes.constraint_writes`; do not invent new
  constraint kinds from prose alone.

Manual eval materials:

- `docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md`
- `docs/guides/vellis/evals/rtg-broad-beta-gates.md`
- `docs/guides/vellis/evals/rtg-agent-affordance-eval-runbook.md`
- `docs/guides/vellis/evals/rtg-agent-affordance-eval-prompt.md`
- `docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md`
