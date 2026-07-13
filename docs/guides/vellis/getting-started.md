# Getting started with Vellis

Vellis gives your local AI agent a structured memory for everyday personal, household or family,
and work information. It starts with an extensible Everyday Life schema, but no facts: the first
people, tasks, notes, and relationships come only from what you tell or approve.

## Install and connect

Install Git and [uv](https://docs.astral.sh/uv/), clone the repository, then run:

```sh
git clone https://github.com/volantlabs/vellis.git
cd vellis
uv run vellis setup
```

Setup detects Codex, Claude Code, or Claude Desktop, shows the exact local launch and data paths,
asks once before changing user-wide MCP configuration, recovers durable state, and installs the
starter schema only when the graph is genuinely empty. Restart or reload the selected client.

Then tell the agent:

> Help me start using Vellis to remember and organize things across my personal life, household or
> family responsibilities, and work. Use the schema already installed. Ask before assuming missing
> details and show me what you propose before making a large initial write.

One graph can be personal or can represent shared household or family responsibilities; Vellis
does not create accounts, profiles, or workspaces.

## What is installed

The schema can represent people and groups; ongoing areas of responsibility; goals, projects,
tasks, events, and routines; decisions and notes; resources and places; and meaningful links among
them. Only a name or title is required, so an agent can preserve useful partial knowledge without
inventing dates, status, or priority. Ask the connected agent for the `everyday_life_schema` guide
when it needs the exact types.

## Local data and recovery

By default, state is stored unencrypted in:

```text
.data/rtg_knowledge_graph/
  json_file/
  controller.sqlite
```

The directory is ignored by Git, so normal pulls leave it untouched. `git clean -x` deletes ignored
files and can remove it. To back up Vellis while it is stopped, copy the entire
`.data/rtg_knowledge_graph/` directory. To reset, first make a backup, stop the MCP client, and then
delete that directory; rerunning setup creates a new empty graph with the starter schema. There is
no automatic destructive cleanup command.

Vellis automatically replays its durable ledger when its MCP process restarts and fails closed if
that history cannot be reconstructed safely. The explicit snapshot, replay, and verification tools
remain available for controlled recovery and audits.

## Troubleshooting

Run the non-destructive doctor and share its output with your agent:

```sh
uv run vellis doctor
uv run vellis doctor --json
```

If more than one supported client is installed, choose one with `--client codex`,
`--client claude-code`, or `--client claude-desktop`. Other MCP clients can use
`--client generic-json`; setup writes a complete configuration file and reports its location.

The ordinary connection uses local stdio: the client starts Vellis directly and no network server
is opened. Localhost HTTP is an explicit advanced mode and must remain bound to `127.0.0.1`.

## Reusing data from the private beta

The few testers who configured Vellis before the standard setup command do not need a data
migration. Their MCP registration normally contains the authoritative `--storage-root` and
`--sql-database-path` values. Stop the old Vellis process, copy those exact paths from the existing
client configuration, and run setup against them:

```sh
uv run vellis setup \
  --storage-root /absolute/path/from/the/old-registration \
  --sql-database-path /absolute/path/from/the/old-registration/controller.sqlite
```

If the registration names another SQLite path, use that exact path instead. Setup replays the old
ledger, preserves its schema as custom, and updates the client registration without overlaying the
Everyday Life ontology. Then run `uv run vellis doctor` with the same `--storage-root` and
`--sql-database-path` arguments, restart the client, and have the agent call
`rtg_get_system_state` and `rtg_validate_graph`. Confirm the expected ledger, schema, and object
counts before changing or deleting any old files.

Do not pass an old flat storage root to `--data-dir`: `--data-dir` denotes the newer parent layout
whose JSON documents live in a `json_file/` child. Reusing the old `--storage-root` is the safest
option. If a tester wants to relocate data afterward, keep the original untouched, stop Vellis,
copy the SQLite database (and any SQLite sidecar files) to the new `controller.sqlite` location,
copy the old JSON-storage contents except that database into the new `json_file/` directory, then
validate the copied instance before retiring the original.

## Beta data boundaries

Vellis runs locally and does not expose a public MCP service. Its files are not encrypted. The AI
agent or model you connect can receive graph contents when it uses Vellis, subject to that client's
own data handling. Use the graph only for information you are comfortable providing to that agent.
