---
name: rtg-federation-control-plane
description: Route work across Vellis RTG graph monographs through the federation control plane. Use when an agent needs to choose which local graph to query, operate several graph monographs side by side, use vellis_* federation MCP tools, run rtg-federated-* or rtg-route commands, inspect bridge candidates, or add descriptor-declared federated read capabilities.
---

# RTG Federation Control Plane

Use this skill when the task involves more than one registered RTG graph, an unknown or ambiguous
graph target, policy-sensitive routing, unresolved freshness or evidence, graph-qualified citations,
bridge candidates, or `vellis_*` federation tools. A simple stable read with one known graph and one
known bounded capability should use native skill discovery and direct graph-local guidance instead.

The federation control plane is a router and planner. It lists graph monographs, compiles user intents into graph routes, reports descriptor-declared read capabilities, returns per-graph MCP launch metadata, and can execute limited read-only graph-local canned reads. It does not own graph data, proxy writes, merge identities, resolve cross-graph objects, or perform cross-graph joins.

## Routing Escalation Gate

Stay on the native path only when all of these are true:

- the operation is read-only
- one target graph is already known
- the bounded read capability and its narrow verification or repository command are already known
- current guidance exposes no freshness, evidence, policy, citation, or bridge hazard
- no federated synthesis or cross-graph comparison is required

Use the federation control plane when any condition is false. Writes remain explicit-target
operations and are policy-sensitive even when the target is already named. The measured bounded
route-pack pilot removed broad discovery work but still cost more than twice the tokens and time of
native execution on a simple stable read, so route packs are an escalation mechanism rather than a
universal preflight.

The capability-routing v1-v4 experiment is concluded and frozen. Its narrow supported result is a
host behavior, not an agent preflight rule: for escalation-eligible multi-graph reads, a host may
supply already-resolved route context and suppress duplicate discovery of this selected source skill
for that fresh task. Do not launch new capability-routing trials or suppress this skill in ordinary
work without explicit human reactivation. The archived protocol remains available in predecessor
history for reproducibility; it is not an active current-tree workflow.

## References

- Read `docs/architecture/graph-routed-agent-context.md` first when reconstructing the whole system
  or deciding which layer owns a cross-component behavior.
- Read `docs/rtg-monographs/README.md` for registry shape, available `just` recipes, bridge candidate rules, and current canned routed reads.
- Read `docs/guides/vellis/evals/rtg-federation-control-plane-runbook.md` for the agent loop and MCP
  tool sequence.
- Read `generated/reference/bibliotek/components/component.rtg.graph_registry.md` as the generated
  human view when changing graph registry behavior, then make contract changes only in
  `model/bibliotek/components/component.rtg.graph_registry.sysml`.
- Skim `docs/architecture/agent-first-graph-modeling.md` before revising monograph boundaries, federation rules, graph identity behavior, provenance, bridge semantics, or schema-domain modeling.

## Operator Card

After the escalation gate selects federation:

1. Start with the local registry at `docs/rtg-monographs/registry.json`.
2. Use `just rtg-graphs` or `vellis_list_graphs` to inspect registered graph roots.
3. Use `just rtg-federated-capabilities` or `vellis_federated_capabilities` before broad read synthesis to see which graph-local reads are ready.
4. Use `just rtg-federation-preflight` or `vellis_federated_preflight` before broad execution.
5. Use `just rtg-route-pack-preview "<intent>"` or `vellis_route_pack_preview` to assemble the advisory route pack before acting.
6. Use `just rtg-route-pack-gate "<intent>"` or `vellis_route_pack_gate` to classify the pack. Continue only on `invoke`; ask for confirmation on `clarify`; stop on `blocked`.
7. Use `just rtg-route "<intent>"` or `vellis_intent_compile` when one graph may answer the request.
8. Use `just rtg-federated-plan "<intent>"` or `vellis_federated_plan` when a read may need graph-local work from several monographs.
9. Use `just rtg-federated-answer "<intent>"` or `vellis_federated_answer` only for supported read-only synthesis with graph-qualified citations.
10. Use `vellis_federated_semantic_answer` only when the server was explicitly launched with `just rtg-federation-mcp-semantic <model>` and model-generated prose is needed. Treat its claims as source-bounded but not entailment-verified.
11. Use `just rtg-citation-resolve <graph_id> <local_uuid>` or `vellis_resolve_citation` to inspect one returned citation through its descriptor-declared bounded projection.
12. Use `just rtg-bridge-traverse <bridge_id>` or `vellis_traverse_bridge` only for one explicit active confirmed bridge; keep endpoint projections separate.
13. Use `just rtg-route-query "<intent>"` or `vellis_route_query` only for one selected graph, read-only operation, and no cross-graph join.
14. After selecting one graph for deeper work, call `just rtg-monograph-mcp-info <graph_id>` or `vellis_graph_mcp_info`, then operate that graph through the graph-local RTG Knowledge Graph MCP workflow.
15. For writes, require an explicit target graph. Do not infer a write target from route confidence.

## Routing Regression Gate

Run `just rtg-federation-eval` after changing graph descriptor domains or tags, route scoring,
intent normalization, or write-target safety. The versioned matrix must pass before treating the
new routing behavior as stable. It does not validate graph snapshots or runtime health.

## Workload Regression Gate

Run `just rtg-federation-workload-eval` after changing federated read implementations, citation
projections, confirmed bridges, temporal filtering, or answer contracts. The versioned workload
matrix executes real descriptor snapshots and scores execution coverage, limitations, sampled
citation resolution, bridge traversal, temporal scope, answer usefulness, source-bounded semantic
claim grounding, and boundary safety. Semantic fixtures do not call a model or require credentials.
Keep it separate from `just rtg-federation-eval`, which tests routing and planning without asserting
end-to-end answer behavior.

## Runtime Preflight

Run `just rtg-federation-preflight` or call `vellis_federated_preflight` before broad execution.
Every graph with descriptor-declared federated reads must report ready query implementations, a
loadable snapshot, and accepted validation. Graphs without declared federated reads are skipped.
Any declared citation projection must identify one ready capability and an anchor bucket returned
by that capability.

## Route Evidence

Before acting on an escalated graph route, use `just rtg-route-pack-preview "<intent>"` or
`vellis_route_pack_preview` to assemble the route pack described in
`docs/architecture/graph-routed-agent-context.md`: selected skill and hand-off chain, scoped
`vellis_*`/`rtg_*` tools and `just` recipes, required docs, verification commands,
freshness/evidence findings, and known hazards.

Then call `just rtg-route-pack-gate "<intent>"` or `vellis_route_pack_gate`. Treat `invoke` as the
only execution state. Treat `clarify` as a request for target confirmation or warning resolution.
Treat `blocked` as a hard stop until blocker hazards such as missing write targets or failed
preflight are fixed.

- Run `just graph-query evidence <component-id>` when a routed task depends on current component
  evidence.
- Run `just graph-query blast-radius <component-id>` before changing shared graph-routing or RTG
  component behavior.
- Run `just graph-verify` after docs, skills, specs, app metadata, tests, or repo structure change.
- Cite graph-local facts and federated answer citations as `(graph_id, local_uuid)`. Treat route
  records, bridge hints, and route packs as advisory until their verification commands pass in the
  current worktree.

## Bridge Discipline

- Bridge hints are planning facts, not executed joins.
- Cross-graph references and federated citations must carry canonical `(graph_id, local_uuid)`
  identity. Labels and domain keys are descriptive, not identity, and a raw UUID is not globally
  meaningful without its graph ID.
- A `candidate_only` bridge record is a review prompt. Inspect it with `just rtg-bridge-candidate <candidate_id>` or `vellis_bridge_candidate`, then promote or reject it explicitly.
- Candidate promotion and rejection mutate only `docs/rtg-monographs/bridges.json`; they are not graph monograph writes.
- Do not treat a candidate as traversal permission until it is promoted to a confirmed bridge assertion.
- Traverse only one explicitly named active bridge at a time. Resolve source and target independently;
  do not expand a path, merge identities, or produce a joined row.

## Federated Read Capabilities

Automatic `vellis_federated_answer` dispatch comes from each graph descriptor's `metadata.federated_read_capabilities`, not graph-id hardcoding.

When adding or changing a federated read:

1. Generate a descriptor and module skeleton with `just rtg-federated-capability-template <query_name>`.
2. Add descriptor metadata under the relevant graph in `docs/rtg-monographs/registry.json`.
3. Add or update a query module that exposes an `apps.rtg_federation.canned_queries.CannedQuery`.
4. Run `just rtg-federated-capabilities-check`.
5. Update docs or runbook examples only when the public workflow changes.

To make citations from that graph dereferenceable, add one `metadata.citation_projection` object
that names a declared `query_name` and one `anchor_bucket` returned by that canned query. Resolution
accepts only `(graph_id, local_uuid)` and never accepts an arbitrary query specification.

## Hand-Off To Graph-Local RTG

Use `$rtg-knowledge-graph-mcp` after this skill has selected or confirmed a specific graph and the task needs graph-local schema inspection, validation, query execution, writes, snapshots, ledger replay, or migration work.
