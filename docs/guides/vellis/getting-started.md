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
  runtime.sqlite
```

The directory is ignored by Git, so normal pulls leave it untouched. `git clean -x` deletes ignored
files and can remove it. To back up Vellis while it is stopped, copy the entire
`.data/rtg_knowledge_graph/` directory. To reset, first make a backup, stop the MCP client, and then
delete that directory; rerunning setup creates a new empty graph with the starter schema. There is
no automatic destructive cleanup command.

Vellis automatically reconstructs managed component state from its runtime ledger when its MCP
process restarts and fails closed if confirmed history cannot be reconstructed safely. Explicit
snapshot and runtime-history operations remain available for controlled recovery and audits.

## Troubleshooting

Run the non-destructive doctor and share its output with your agent:

```sh
uv run vellis doctor
uv run vellis doctor --json --client codex
```

If more than one supported client is installed, choose one with `--client codex`,
`--client claude-code`, or `--client claude-desktop`. Other MCP clients can use
`--client generic-json`; setup writes a complete configuration file and reports its location.
The `setup --json` and `doctor --json` forms are non-interactive and print exactly one JSON
document, so scripts and agents must provide an explicit `--client` when automatic detection finds
more than one client. Automated setup must also include prior human authorization through `--yes`,
for example `uv run vellis setup --json --client codex --yes`. Ordinary `vellis setup` remains
interactive.

The ordinary connection uses local stdio: the client starts Vellis directly and no network server
is opened. Localhost HTTP is an explicit advanced mode and must remain bound to `127.0.0.1`.

## Moving data from an earlier Vellis version

Do not point the current runtime at an earlier controller database or copy its ledger. Use the old
version to validate and export a full coordinated snapshot, start the current version with a new
empty data directory, and restore that snapshot through Vellis. The destination runtime records the
restore as the beginning of its own chronology. Keep the source untouched until destination
validation and restart reconstruction agree.

Agents should follow the complete [snapshot-transfer procedure](snapshot-transfer.md).

## Beta data boundaries

Vellis runs locally and does not expose a public MCP service. Its files are not encrypted. The AI
agent or model you connect can receive graph contents when it uses Vellis, subject to that client's
own data handling. Use the graph only for information you are comfortable providing to that agent.
