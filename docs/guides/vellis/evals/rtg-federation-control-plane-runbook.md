# RTG Federation Control Plane Runbook

Use this runbook when an agent needs to operate across several local RTG graph monographs from one
Vellis checkout.

The federation MCP server is a control plane. It lists graphs, compiles intent routes, returns
per-graph MCP launch configuration, and can include bridge assertions as planning hints. It does
not own graph data, proxy writes, merge identities, or perform cross-graph joins.

## Setup

List registered graphs:

```sh
just rtg-graphs
```

Print the federation MCP client configuration:

```sh
just rtg-federation-mcp-info
```

Launch the federation MCP server:

```sh
just rtg-federation-mcp
```

To explicitly enable OpenAI-backed semantic synthesis, set `OPENAI_API_KEY` and name the model:

```sh
just rtg-federation-mcp-semantic gpt-5.6-luna
```

The ordinary server remains model-free. Semantic mode adds no graph or MCP tools to the model
request and sends only the deterministic synthesis envelope using Responses Structured Outputs
with storage disabled.

## Routing Regression Gate

Run the versioned routing and planning matrix before relying on changed descriptor vocabulary or
router behavior:

```sh
just rtg-federation-eval
```

The source cases live in `docs/guides/vellis/evals/rtg-federation-routing-cases.json`. They cover single-graph
reads, temporal intents, ambiguous and unmatched requests, explicit targets, two- and three-graph
plans, route-pack previews, route-pack gate decisions, and write-target safety. A failed case
reports each mismatched expected field and exits non-zero. The matrix evaluates routing, planning,
and stable route-pack contract fields only; use `just rtg-federation-preflight` for snapshot and
graph-runtime health.

## Workload Regression Gate

Run the end-to-end workload scorecard after changing a federated read, citation projection,
confirmed bridge, temporal filter, or stable answer contract:

```sh
just rtg-federation-workload-eval
```

The source cases live in `docs/guides/vellis/evals/rtg-federation-workload-cases.json`. They execute registered
snapshots and score execution coverage, limitations, one resolved citation per expected graph,
confirmed-bridge endpoint resolution, temporal scope, useful answer fields, source-bounded semantic
claim grounding, and proof that no join or write occurred. Semantic cases use deterministic fixture
drafts and never call a model. Keep evolving content behind required-field assertions; reserve exact-value
assertions for stable semantics such as scope, readiness state, and open-gate count.

## Runtime Preflight

Before broad federated execution, check every descriptor-declared read:

```sh
just rtg-federation-preflight
```

The check loads each declared snapshot, applies the same read-only compatibility projection as routed
reads, and runs graph validation. A missing or invalid snapshot, unknown query implementation, or
rejected validation makes the command exit nonzero. A declared citation projection also fails
preflight when its query capability is unavailable or does not return the named anchor bucket.
Graphs without declared federated reads are skipped. The equivalent MCP tool is
`vellis_federated_preflight`.

The compatibility projection never rewrites the snapshot. It strips recognized predecessor-only
`time_shape`, `identity_criteria`, and `link_kind` schema metadata, converts legacy `datetime`
value kinds to current string fields with `date_time` format, and strips only lossless live-link
system metadata. The response reports every conversion or removal count. This projection authorizes
bounded reads only; it does not make a blocked schema domain writable on the current kernel.

## Agent Loop

1. Call `vellis_list_graphs`.
2. Call `vellis_federated_capabilities` to inspect descriptor-declared graph-local reads.
3. Call `vellis_federated_preflight` before broad execution.
4. Run `just rtg-federated-capabilities-check` after adding or changing capability descriptors or
   modules.
5. Run `just rtg-federation-workload-eval` after changing executable federation behavior or before
   claiming the end-to-end workload contract is stable.
6. Call `vellis_route_pack_preview` with the user request and inspect its hazards, scoped tools,
   required docs, and verification commands before acting.
7. Call `vellis_route_pack_gate` with the user request. Continue only on `invoke`; ask for
   clarification on `clarify`; stop and fix the blocker on `blocked`.
8. Call `vellis_intent_compile` with the user request when a single graph may answer it.
9. For broad read questions that may span multiple monographs, call `vellis_federated_plan`.
10. Inspect `selected_graph_id`, `requires_confirmation`, candidate reasons, any federated plan
   steps, and `bridge_hints`.
11. For supported read-only synthesis, call `vellis_federated_answer`.
12. When semantic mode was explicitly configured and prose claims are needed, call
   `vellis_federated_semantic_answer`. Preserve its `entailment_status=not_verified` caveat.
13. Resolve a returned citation with `vellis_resolve_citation(graph_id, local_uuid)` when its bounded
   source projection is needed.
14. Traverse one confirmed active bridge with `vellis_traverse_bridge(bridge_id)` only when both
   endpoint projections are needed; keep the results separate.
15. If the route is ambiguous, ask for the target graph or rerun with explicit hints.
16. If the route selects a graph, call `vellis_graph_mcp_info` for that `graph_id`.
17. Attach to that graph's own RTG MCP server.
18. Call the graph server's `rtg_validate_graph` before graph-local reads or writes.
19. For writes, require an explicit `target_graph_id`; do not infer a write target from route
   confidence.

## Read-Only Shortcut

For single-graph reads, `vellis_route_query` can compile the intent and execute one RTG query
against the selected graph in-process.

Use it only when:

- the operation is read-only
- one graph is selected or `target_graph_id` is explicit
- the query is for one graph, not a cross-graph join

Example route record:

```sh
uv run python -m tools.rtg_graph_registry route --json "Which component specs lack evidence?"
```

Example route pack:

```sh
just rtg-route-pack-preview "Compare component evidence with personal decisions."
```

Example route-pack gate:

```sh
just rtg-route-pack-gate "Compare component evidence with personal decisions."
```

Example federated plan:

```sh
just rtg-federated-plan "Compare component evidence with personal decisions."
```

Example federated capability report:

```sh
just rtg-federated-capabilities
just rtg-federated-capabilities-check
just rtg-federated-capability-template gothic_source_index
```

Example federated synthesis:

```sh
just rtg-federated-answer \
  "Compare repository component evidence gaps, personal commitments needing attention this week, and Gothic archive works, sources, passages, and reading trails."
```

Example Experience Studio publication-readiness read:

```sh
just rtg-federated-answer "Show Experience Studio publication readiness."
```

The result preserves individual publication checks as graph-qualified citations and surfaces any
outcome other than `pass` as an open review gate. It is product-planning evidence, not legal
certification.

`vellis_federated_answer` runs supported graph-local canned reads and returns a structured synthesis
record with graph-qualified citations. Unsupported reads are reported as limitations. It does not
perform joins or writes.

`vellis_federated_semantic_answer` runs that deterministic path first, then asks the configured
OpenAI Responses model for a strict semantic draft. The evidence-bounded component rejects unknown
citations, uncited claims, one-graph comparisons, and inference claims without uncertainty. Model
execution is opt-in, read-only, and never changes the deterministic answer contract.

Resolve one returned citation:

```sh
just rtg-citation-resolve repo_twin <local_uuid>
```

`vellis_resolve_citation` uses the owning graph's `metadata.citation_projection`, which must name
one descriptor-declared canned read and an anchor bucket returned by that query. The result contains
only rows whose anchor UUID matches the citation, plus snapshot and projection provenance. It does
not accept caller-authored query specifications.

Traverse one active confirmed bridge:

```sh
just rtg-bridge-traverse <bridge_id>
```

`vellis_traverse_bridge` resolves the source and target citations independently and returns the
complete bridge assertion beside those two results. Candidate-only and revoked records do not grant
permission. The operation never expands another bridge or constructs a joined result.

Automatic graph-local read selection comes from each graph descriptor's
`metadata.federated_read_capabilities`. Add new supported reads there with a `query_name` and
matching vocabulary plus an `implementation` path in `module:attribute` format, then confirm they
appear as ready in `vellis_federated_capabilities` and pass
`just rtg-federated-capabilities-check`; avoid hardcoding graph ids into federation dispatch.

Bridge hints in that response are active reified assertions from `docs/rtg-monographs/bridges.json`.
Each bridge hint includes a `follow_up_checklist`: read the source endpoint in its graph, read the
target endpoint in its graph, then synthesize outside the graph. Do not treat those checklist items
as executed joins.

If `candidate_hints.status` is `candidate_only`, treat the record as a proposal to review. Inspect
its evidence and endpoints, then promote it into a bridge assertion or reject it before using it as
a traversal path.

Candidate review commands:

```sh
just rtg-bridge-candidates
just rtg-bridge-candidate <candidate_id>
just rtg-bridge-candidate-promote <candidate_id> 2026-07-09T01:00:00Z agent.codex
just rtg-bridge-candidate-reject <candidate_id> 2026-07-09T01:00:00Z agent.codex "reason"
```

The equivalent MCP tools are `vellis_bridge_candidates`, `vellis_bridge_candidate`,
`vellis_promote_bridge_candidate`, and `vellis_reject_bridge_candidate`. They mutate only the bridge
catalog file and do not write to graph monographs.

Example canned routed query:

```sh
just rtg-route-query "Which component specs lack evidence?"
```

Example routed query shape:

```json
{
  "text": "Which component specs lack evidence?",
  "target_graph_id": "repo_twin",
  "query_spec": {
    "anchor_buckets": [
      {"name": "component", "anchor_type_keys": ["Component"]}
    ]
  }
}
```

Current descriptor-declared reads are:

- `repo_components_evidence_status` for repo-twin component evidence coverage.
- `personal_attention_overview` for commitments, routines, decisions, evidence gaps, and open
  loops needing attention.
- `gothic_source_index` for Gothic works, sources, passages, reading trails, and source-verification
  gaps. The Gothic descriptor restores `snapshots/gothic-ambient-archive-alpha.json` before this
  graph-local read.

## Safety Rules

- Cross-graph references and federated citations must carry `(graph_id, local_uuid)`.
- Raw UUIDs are never globally meaningful across graph roots.
- Citation labels and domain keys are descriptive and must not replace graph-local UUID identity.
- Citation resolution must use the owning graph's descriptor-declared bounded projection.
- Bridge traversal must name one active confirmed bridge and keep endpoint projections separate.
- Bridge hints must preserve `(graph_id, local_uuid)` endpoints.
- Candidate hints have no traversal permission until promoted.
- Candidate promotion/rejection is a bridge-catalog operation, not a graph write.
- Federated answer reads must be descriptor-declared or explicitly overridden by graph id.
- Ambiguous routes stop before graph-local MCP calls.
- Federation writes are out of scope for this control plane slice.
