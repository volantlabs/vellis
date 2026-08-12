# MCP realization

This note is non-normative. The SysML model selects the agent-visible RTG behavior; `vellis/mcp.py`
exposes it over local standard input and output.

## Agent path

An unfamiliar agent first calls `rtg_definition_summary`, omitting its optional revision-or-time
selector for current state or supplying one for historical state, to learn every active anchor type
and its owner-readable description at the evaluated revision. It then calls
`rtg_definition_inspect` with the same selection for only the anchor types relevant to its question.
Each result identifies its evaluated revision; if the revisions differ, the agent repeats discovery
instead of relying on stale vocabulary. After a time-based summary, it reuses the returned exact
revision for inspection and graph query. If
the current summary reports an in-flight proposal, an agent continuing definition work uses
`rtg_definition_delta` to retrieve that sole proposed set and its current assessment whole.

The remaining selected tools query and change the graph, stage or resolve the sole definition delta,
check conformance, and inspect bounded history. Historical summary and inspection allow cold discovery
of vocabulary later retired; `rtg_definition_delta` remains current-only. History results contain
bounded owner-facing entries rather than canonical state or replay-sufficient changes. Results are
complete or rejected rather than silently truncated.
Activity-history results are selected before the current read is recorded, so a read never includes
its own observation. Activity summaries identify capability, outcome category, provenance, applicable
evaluated revision, and bounded semantic scope without copying result rows or canonical payloads.
Activity retention, snapshot, replay, initialization, restoration, and v1 first-use onboarding are
not in the initial MCP surface.

`rtg_check` is a parameterless current-graph conformance check. Delta retrieval and staging already
return the sole proposal's current assessment, so the realization must not create a duplicate delta-
check path. A completed check returns a validation report; nonconformance is a successful assessment,
not a tool rejection. An unexpected check failure produces no successful report.

Completed invocations return their modeled typed result. Accepted results carry their complete
purpose-specific payload. Semantic rejection and a safely reported failure carry no success payload;
malformed input forms no RTG request, and an unexpected tool failure produces no completed RTG
result. A rejected delta-staging request does not echo the unchanged proposal—the agent retrieves it
explicitly with `rtg_definition_delta`.

## FastMCP discipline

The current implementation campaign selects direct pins for `fastmcp==4.0.0b1` and its pre-release
companion `fastmcp-slim==4.0.0b1`. Their pre-release status is an explicit owner decision for this
proving campaign; S009 must not enable prereleases globally, select unrelated prereleases, or upgrade
opportunistically, and it must update the lock and prove `uv sync --locked`. It will use typed input
and return models and keep text and structured content semantically equivalent. FastMCP, Python
models, decorators, the selected local STDIO transport, and serialization remain realization rather
than RTG domain meaning.

FastMCP may represent a parameterless tool with an empty object schema, but that representation does
not create an empty RTG request concept. The optional selector for `rtg_definition_summary` belongs
directly to that tool input and likewise does not create an empty wrapper. Public input schemas must
advertise only caller-valid choices; internal validation scopes do not become `rtg_check` targets by
reuse.

Only core MCP tool discovery and invocation are required. Resources, prompts, elicitation, tasks,
sampling, sessions, notifications, subscriptions, application UI, transforms, tool search,
authentication, HTTP, remote hosting, and plugin packaging remain outside the initial contract.
Advisory annotations may describe modeled state effects but never enforce authorization, validation,
or atomicity.

The initial boundary assumes one trusted, owner-configured MCP client. Tool invocation neither
establishes nor evaluates per-call authorization. An owner-declined context proposal is never
submitted to `rtg_change`; exposing graph mutation does not by itself implement Vellis's higher-level
owner approval of personal context. The first implementation must preserve that distinction without
inventing roles, tenants, or an authentication subsystem inside RTG.

Current operations must use the current canonical-state projection rather than replaying history.
Bounded history and revision/time selection must avoid scanning excluded ledger prefixes, and
historical definition discovery must avoid replaying unrelated graph-only transitions. Materialized
projections, revision/time indexes, definition checkpoints, caches, and snapshot cadence are allowed
realization choices, not selected architecture. Conformance should use semantic record-access counts
or equivalent traces; wall-clock targets wait for representative runtime, hardware, and owner data.

The implementation PR must verify two realization-only properties that do not belong in the RTG
domain model: text and structured content communicate the same typed outcome, and removing or
changing advisory annotations cannot change authorization, validation, atomicity, or any promised
failure non-effect.

## Local setup path

The campaign selects a Python setup program as the primary local onboarding path, with the
repository README pointing both agents and developers to it. It previews every effect and confirms
before applying it, and complete non-interactive arguments plus `--yes` support agent-driven setup;
`--dry-run` changes nothing.

The setup path selects blank or Everyday Life initialization, v2 snapshot plus optional tail, and v1
preview and exact confirmation. All three starting inputs are implemented, and a companion command
writes the snapshot document the second one takes. It accepts a configurable data
location with a platform-appropriate user-data default; tests use temporary directories, and neither
tests nor the runtime default use the repository's protected `.data/` directory.

## Client configuration

Registering Vellis with an MCP client changes that client's own user-scoped state rather than
anything in this repository. Whichever way that happens, it goes through the public `codex mcp` and
`claude mcp` commands and never edits a configuration file directly, a matching `vellis` entry is a
no-op, a differing entry is replaced only deliberately, and client tool approval settings stay
entirely client-owned.

The selected owner of this behavior is the setup program. Repeating `--client codex` or
`--client claude` selects either or both clients; omitting `--client` selects neither. Setup previews
the public inspection and mutation commands before confirmation, treats a matching entry as a no-op,
and requires `--replace-client CLIENT` before replacing a differing entry. Matching includes the
enabled user scope, STDIO command and arguments, and an empty launch environment; another transport,
destination-bearing environment, scope, or enabled state is a difference. Client inspection and
connection outcomes are reported separately from memory initialization, with an exact client-only
retry command. An unavailable client gets a platform-correct copyable command without undoing
established memory. Linux and Windows command rendering, paths containing spaces, and non-default
destinations have fake-client evidence.

Corrective slice S018 implements decisions D004 and D005. Closure decision D006 then ran the matching
live dry run, applied only the authorized registrations, and reread both matching entries. Codex's
existing approval policy cancelled the required bounded read-only MCP invocation, so closure paused
without changing that policy. Authority A017 and runnable closure remain `partial` until both real
clients complete the bounded invocation.

The commands below are a fallback when a supported client CLI is unavailable, not the selected
primary workflow and not evidence that campaign closure has occurred. Establish a system first with
`uv run python -m vellis.setup`, then, with `VELLIS` standing for the absolute path of this clone:

```sh
VELLIS=/absolute/path/to/this/clone

codex mcp list                       # what is registered now
codex mcp remove vellis              # only if that list shows a vellis entry that differs
codex mcp add vellis -- uv --directory "$VELLIS" run python -m vellis

claude mcp list                      # what is registered now
claude mcp remove vellis             # only if that list shows a vellis entry that differs
claude mcp add --scope user vellis -- uv --directory "$VELLIS" run python -m vellis
```

The two `list` commands come first because they, not this page, are what say where the entries
actually stand: skip both the `remove` and the `add` for a client whose `vellis` entry already
matches, and skip only the `remove` for one that has no entry at all. Codex is user-scoped already,
which is why only `claude mcp add` carries `--scope user`. `--directory` is what makes the launch
work from wherever the client starts it, since the module is resolved out of this project, so
`VELLIS` has to be a real absolute path before either `add` runs — neither CLI checks the command it
stores, and a wrong one fails at launch instead. Add `--data-dir DESTINATION` after `-m vellis` when
setup put the system somewhere other than its default, and list again afterwards to confirm. Any
state drift, different destination, unsupported CLI behavior, or permission-policy change stops for
the owner's direction instead.

After approved S018 checkpoints, macOS is to supply the first clean-environment runnable evidence,
including real Codex and Claude Code discovery and invocation. Closure may perform the live change
only when the first public-CLI dry run observes exactly the authorized transition. After an
interruption, an entry already matching the enabled user-scoped STDIO destination is an idempotent
no-op and closure may apply only the remaining authorized transition. Conflicting or unparseable
state, another destination, unsupported behavior, or any approval-policy consequence pauses before
further mutation. Linux and Windows are compatibility targets rather than initial closure blockers.
The client command contracts are
documented by
[OpenAI](https://learn.chatgpt.com/docs/extend/mcp) and
[Anthropic](https://docs.anthropic.com/en/docs/claude-code/mcp).
