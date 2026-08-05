# Future MCP realization

This note is non-normative. The SysML model selects the agent-visible RTG behavior; it does not yet
implement an MCP server.

## Agent path

An unfamiliar agent first calls parameterless `rtg_definition_summary` to learn every currently
active anchor type and its owner-readable description. It then calls `rtg_definition_inspect` for
only the anchor types relevant to its question. Each result identifies its evaluated revision; if
the revisions differ, the agent repeats discovery instead of relying on stale vocabulary. If
the current summary reports an in-flight proposal, an agent continuing definition work uses
`rtg_definition_delta` to retrieve that sole proposed set and its current assessment whole.

The remaining selected tools query and change the graph, stage or resolve the sole definition delta,
check conformance, and inspect bounded history. A historical query uses vocabulary the caller already
knows was valid at the selected revision; current-only summary and inspection are deliberately not a
historical schema browser. History results contain bounded owner-facing entries rather than canonical
state or replay-sufficient changes. Results are complete or rejected rather than silently truncated.
Activity-history results are selected before the current read is recorded, so a read never includes
its own observation. Activity retention, snapshot, replay, initialization, restoration, and
predecessor recovery are not in the initial MCP surface.

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

The first implementation PR will verify and pin the latest stable non-prerelease FastMCP version and
use documentation for that exact major version. It will use typed input and return models and keep
text and structured content semantically equivalent. FastMCP, Python models, decorators, transport,
and serialization are realization choices rather than RTG domain meaning.

FastMCP may represent a parameterless tool with an empty object schema, but that representation does
not create an empty RTG request concept. Public input schemas must advertise only caller-valid
choices; internal validation scopes do not become `rtg_check` targets by reuse.

Only core MCP tool discovery and invocation are required. Resources, prompts, elicitation, tasks,
sampling, sessions, notifications, subscriptions, application UI, transforms, tool search,
authentication, and transport selection remain outside the initial contract. Advisory annotations
may describe modeled state effects but never enforce authorization, validation, or atomicity.

The initial boundary assumes one trusted, owner-configured MCP client. Tool invocation neither
establishes nor evaluates per-call authorization. An owner-declined context proposal is never
submitted to `rtg_change`; exposing graph mutation does not by itself implement Vellis's higher-level
owner approval of personal context. The first implementation must preserve that distinction without
inventing roles, tenants, or an authentication subsystem inside RTG.

The implementation PR must verify two realization-only properties that do not belong in the RTG
domain model: text and structured content communicate the same typed outcome, and removing or
changing advisory annotations cannot change authorization, validation, atomicity, or any promised
failure non-effect.
