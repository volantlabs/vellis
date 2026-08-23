# Vellis

Vellis is one individually owned personal AI memory, run as a local MCP server for coding
agents and other MCP clients.

## Install

```sh
uv tool install git+https://github.com/volantlabs/vellis
vellis --help
```

Try it without installing:

```sh
uvx --from git+https://github.com/volantlabs/vellis vellis --help
```

Working from a clone (contributors):

```sh
git clone https://github.com/volantlabs/vellis && cd vellis
uv sync
uv run vellis --help
```

- Requires Python 3.14 or newer; `uv` fetches it automatically if it is not already installed.
- The `vellis` shim lands in `uv tool dir --bin` (usually `~/.local/bin`), and that directory must
  be on `PATH` — `vellis connect` resolves the command with `shutil.which("vellis")` and records
  the resulting absolute path into the client entry it registers.
- Every invocation needs a subcommand. Bare `vellis` or `python -m vellis` exits with a usage
  error, not a running server.

See [`docs/install.md`](docs/install.md) for troubleshooting, pinning a version, and upgrading.

## Quick start

```sh
vellis setup --starter --no-connect --data-dir ~/vellis-data
vellis serve --transport stdio --data-dir ~/vellis-data
```

In another terminal, register the server with a supported client:

```sh
vellis connect --client claude --transport stdio --data-dir ~/vellis-data
```

An agent working unattended should use a throwaway directory and skip `connect`; see
[`AGENTS.md`](AGENTS.md#running-vellis).

Vellis is an open demonstration of model-first software engineering with textual SysML v2. The
accepted model under [`model/`](model/) is product and system authority. Markdown describes how to
work with that authority without restating it as a second contract.

Vellis v2 deliberately removes prototype complexity. It is a scalar
Reified Type Graph with local cardinality, progressive discovery, one bounded identity-or-pattern
query, field-level graph patches, one durable draft, indexed current and historical state, separate
canonical and activity ledgers, restore, audit, SQLite backup, streamed v1 initialization, and
STDIO or bearer-protected HTTP for one owner.

## Repository map

- [`docs/install.md`](docs/install.md) covers installation, upgrading, pinning, and troubleshooting.
- [`model/README.md`](model/README.md) maps the authoritative textual SysML packages.
- [`docs/vision.md`](docs/vision.md) gives the engineering vision.
- [`docs/modeling-method.md`](docs/modeling-method.md) and
  [`docs/implementation-method.md`](docs/implementation-method.md) describe the model-first method.
- [`docs/mcp-realization.md`](docs/mcp-realization.md) describes the non-normative MCP realization.
- [`docs/http-operation.md`](docs/http-operation.md) covers HTTP security and external deployment.
- [`docs/backup-restore.md`](docs/backup-restore.md) covers online backup, backup initialization, and
  historical restore.
- [`docs/v1-initialization.md`](docs/v1-initialization.md) covers v1 export, preview, import, and
  remodeling review.
- [`system-evolution.yaml`](system-evolution.yaml) is the current execution and evidence index, not
  product authority.
- [`.agents/skills/`](.agents/skills/) contains the portable SysML workflow and Vellis-specific
  extensions.

Start agent-assisted work with [`AGENTS.md`](AGENTS.md). Use `$sysml-reference` for consequential
SysML or KerML interpretation, `$sysml-modeling` for system meaning, `$sysml-implementation` for a
bounded accepted slice, `$sysml-evolution` for post-build evolution, `$rtg-schema-design` for RTG
meaning, and `$documentation-sync` after public or workflow changes.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and [just](https://just.systems/), then run:

```sh
just setup
just model-setup
just check
```

Useful focused checks include:

- `just model-check` and `just model-reference-check`
- `just model-reference-find "<question>"`
- `just skills-check`
- `just system-evolution-check` and `just system-evolution-status`
- `just test`, `just package-check`, `just lint`, and `just typecheck`

`just check` validates the current model, evolution record, product, package, skills, and repository
policy.
The inactive campaign engine has separate explicit recipes and is not an ordinary product gate.

## Runnable v2 boundary

The scalar domain, SQLite persistence, discovery/query, active changes, draft governance,
history/activity, restore/audit/backup, v1 initialization, and MCP/owner boundary are implemented.
The unreleased prototype modules and compatibility paths are absent.

The owner command has seven subcommands:

```text
vellis setup
vellis connect
vellis serve
vellis backup
vellis restore
vellis audit
vellis configure
```

Initialize a blank system or the recommended Everyday Life starter explicitly in noninteractive
use:

```sh
vellis setup --blank --no-connect --data-dir /absolute/path/to/vellis-data
vellis setup --starter --no-connect --data-dir /absolute/path/to/vellis-data
```

The selected data directory must either be absent, so Vellis can create it owner-private, or be
empty and use mode `0700` on POSIX. Vellis refuses a pre-existing directory with broader
permissions rather than placing personal data there.

V1 preview options apply only to `--from-v1 --preview`; confirmed imports require both displayed
digests. Preview never connects a client or publishes a destination. Interactive setup always asks
before publication; it has no `--yes` bypass.

Serve the exact initialized database over STDIO:

```sh
vellis serve --transport stdio --data-dir /absolute/path/to/vellis-data
```

Register the fixed `vellis` entry through a supported client's public CLI:

```sh
vellis connect --client codex --transport stdio --data-dir /absolute/path/to/vellis-data
vellis connect --client claude --transport stdio --data-dir /absolute/path/to/vellis-data
```

Existing entries require `--replace`; Vellis probes the intended target before removing anything.
It never reads or edits client configuration files. A failed add after removal is reported as an
external client-state change with an exact recovery command, never as a rollback.

For HTTP, guided setup creates an owner-private token without printing it. Vellis runs in the
foreground at `/mcp` and performs no TLS termination or service management. See
[`docs/http-operation.md`](docs/http-operation.md) before using a non-loopback address.

Use `vellis backup --out ...` for an audited online copy, `vellis setup --from-backup ...` for a
separate empty destination, and `vellis restore --revision ...` or `--time ...` to publish selected
historical meaning as a new revision. See [`docs/backup-restore.md`](docs/backup-restore.md) before
recovering owner data.

The MCP boundary exposes:

- `rtg_type_summary` and `rtg_type_inspect`
- `rtg_query`
- `rtg_change`
- `rtg_draft_inspect`, `rtg_draft_change`, `rtg_validate`, `rtg_draft_activate`, and
  `rtg_draft_discard`
- `rtg_history`

Begin cold with summary and focused inspection. Use identity selection directly for known UUIDs and
pattern selection for connected graph questions. A draft is a bucket of deltas: inspect its raw
entries, query the effective draft state, validate, then activate or discard. It has no public
version, status, assessment identity, or activation token.

Vellis data, backups, activity, and migration reports are plaintext at rest. On POSIX, Vellis uses
owner-private directories and files. The ignored repository `.data/` directory may contain
user-owned data and is never part of development or migration work without explicit owner direction.
