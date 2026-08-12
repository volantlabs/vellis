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
writes the snapshot document the second one takes; everything about client configuration below is
selected rather than implemented, and README states where the implementation stands. It accepts a configurable data
location with a platform-appropriate user-data default; tests use temporary directories, and neither
tests nor the runtime default use the repository's protected `.data/` directory. It can configure
Codex, Claude Code, both, or neither.
Client configuration is user-scoped and goes only through the public `codex mcp` and `claude mcp`
commands after preview and confirmation; the program never edits their configuration files directly.
A matching `vellis` entry is a no-op, a differing entry requires explicit replacement, and a missing
or unsupported client produces copyable commands without failing or undoing valid Vellis
initialization. Client tool approval settings remain entirely client-owned.

For the approved macOS closure rehearsal, a matching dry run authorizes replacing only the existing
disabled Codex `vellis` HTTP entry with the selected STDIO entry and adding the Claude Code STDIO
entry. Any observed state drift, different destination, unsupported CLI behavior, or permission-policy
change pauses for human direction. This is bounded execution authority, not implemented behavior.

macOS supplies the first clean-environment runnable evidence, including real Codex and Claude Code
discovery and invocation. Linux and Windows receive platform-correct commands, path handling,
dry-run/configuration tests, and troubleshooting guidance, but are compatibility targets rather than
initial closure blockers. The client command contracts are documented by
[OpenAI](https://learn.chatgpt.com/docs/extend/mcp) and
[Anthropic](https://docs.anthropic.com/en/docs/claude-code/mcp).
