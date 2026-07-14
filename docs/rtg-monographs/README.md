# RTG Monograph Registry

This directory describes independent RTG graph roots that can be run side by side from one Vellis
checkout.

The registry is an experiment-facing catalog, not the graph source of truth. Each entry names a
local storage root, SQLite ledger path, routing vocabulary, write policy, and optional MCP endpoint
hint. The graph contents still live inside each root and are governed by the RTG controller.

## Current Registry

The default registry is:

```text
docs/rtg-monographs/registry.json
```

Optional bridge assertions live beside it:

```text
docs/rtg-monographs/bridges.json
```

The `application_portfolio` monograph is the meta-level graph for comparing applications such as
Nocturne Archive and Channel Drift. Its second snapshot contains four applications plus reusable
capabilities, experience patterns, audiences, domains, maturity stages, component usage, and
repository evidence. Similarity is derived by querying shared relationships rather than storing
subjective `similar_to` links.

Comparison claims are reified as `PortfolioAssertion` records. Each assertion carries a rationale,
verification status, confidence, and an explicit uncertainty note, then links to its application,
comparison target or shared dimension, and supporting evidence. Direct application relationships
remain traversal projections; assertions are the source for evidence-backed interpretation. The
current graph-local comparison contract returns shared pattern matches, dependency evaluations, and
coverage gaps so an absent relationship is not mistaken for a negative finding. The graph
intentionally declares no federated read capability yet; add one only after this graph-local contract
has a descriptor-declared canned-query implementation and citation projection.

Useful commands:

```sh
just rtg-graphs
just rtg-route "Which component specs lack evidence?"
just rtg-route-pack-preview "Compare component evidence, personal attention, and Gothic sources."
just rtg-route-pack-gate "Compare component evidence, personal attention, and Gothic sources."
just rtg-federated-plan "Compare component evidence with personal decisions."
just rtg-federated-capabilities
just rtg-federated-capabilities-check
just rtg-federation-eval
just rtg-federation-workload-eval
just rtg-federation-preflight
just rtg-federated-capability-template gothic_source_index
just rtg-federated-answer "Compare component evidence, personal attention, and Gothic sources."
just rtg-citation-resolve repo_twin <local_uuid>
just rtg-bridge-traverse <bridge_id>
uv run python -m tools.rtg_graph_registry route --json "Which component specs lack evidence?"
just rtg-route-query "Which component specs lack evidence?"
just rtg-bridge-candidates
just rtg-bridge-candidate <candidate_id>
just rtg-monograph-init repo_twin
just rtg-monograph-init application_portfolio
just rtg-monograph-mcp-info repo_twin
just rtg-monograph-mcp-info application_portfolio
just rtg-monograph-mcp repo_twin
just rtg-monograph-mcp application_portfolio
just rtg-federation-mcp-info
just rtg-federation-mcp
```

Run each HTTP MCP server on its descriptor's localhost port. Configure agents with the client config
emitted by `just rtg-monograph-mcp-info <graph_id>`.

The federation MCP server exposes only graph-control tools:

- `vellis_list_graphs`
- `vellis_federated_capabilities`
- `vellis_federated_preflight`
- `vellis_intent_compile`
- `vellis_route_pack_preview`
- `vellis_route_pack_gate`
- `vellis_federated_plan`
- `vellis_federated_answer`
- `vellis_resolve_citation`
- `vellis_traverse_bridge`
- `vellis_graph_mcp_info`
- `vellis_route_query`
- `vellis_bridge_candidates`
- `vellis_bridge_candidate`
- `vellis_promote_bridge_candidate`
- `vellis_reject_bridge_candidate`

`vellis_federated_plan` compiles a read-oriented request into graph-local plan steps across every
matching registered graph. When a bridge catalog is configured, it also returns active bridge
assertions connecting the planned graph ids as planning hints, plus a `follow_up_checklist` with
graph-local read items and an outside-graph synthesis item. It does not execute queries, resolve
identity, create bridge assertions, or perform a cross-graph join.

`vellis_federated_capabilities` reports each graph's descriptor-declared federated reads and whether
their `query_name` maps to a known read-only canned query. Use it before broad synthesis to see
which monographs can currently execute graph-local reads.

`vellis_federated_preflight` checks runtime readiness for those declared reads. It restores each
declared snapshot, validates the restored graph, and reports capability, snapshot, and validation
status per graph without executing the query capability. Graphs with no declared federated reads
are reported as `no_federated_reads` and do not fail the check. It also validates any declared
citation projection against its query capability and returned anchor bucket.

Snapshots authored by the predecessor kernel are projected in memory for read compatibility. The
projection reports and removes recognized schema metadata the current kernel cannot represent,
converts legacy `datetime` value kinds to current `date_time`-formatted strings, and never rewrites
the stored snapshot. This is read permission only; schema-domain write readiness is reported
separately by the schema-domain catalog.

`vellis_route_pack_preview` assembles the advisory route pack before an agent acts. The pack includes
the selected skill and hand-off chain, scoped federation and graph-local tools, `just` recipes,
required docs, verification commands, capability/preflight context, route and plan records, identity
rules, and hazards. `component.rtg.route_pack` owns the assembly and gate semantics; the federation
app supplies graph registry, preflight, capability, bridge, and evidence records as adapter input. It
does not execute graph reads, proxy writes, or perform cross-graph joins.

`vellis_route_pack_gate` evaluates the same pack and returns `invoke`, `clarify`, or `blocked`.
`invoke` exposes only the scoped tools and returns a bounded next action for the selected or planned
graph flow. `clarify` keeps execution stopped until ambiguity or warning hazards are resolved.
`blocked` reports blocker hazards such as missing write targets or failed preflight.

A graph may declare one `metadata.route_pack_read` profile that names a ready
`federated_read_capabilities` query plus a bounded local `command`, `verification_commands`,
optional `stale_recovery_command`, and `required_docs`. The adapter uses that profile only when the
route has one high-confidence graph context and the named capability is ready. In that case the
gate returns `execute_descriptor_read` and omits graph-local MCP hand-off. Multi-graph contexts keep
the federated-plan path, and descriptors without a profile retain graph-local hand-off.

`vellis_federated_answer` executes the first read-only synthesis loop. It compiles the same
federated plan, runs supported graph-local canned reads, preserves graph-qualified citations, and
returns a structured synthesis record. Unsupported graph-local reads are limitations. Confirmed
bridge assertions are context; candidate-only records are limitations until promoted. It does not
perform cross-graph joins or writes. Each citation uses canonical `(graph_id, local_uuid)` identity;
labels and domain keys remain descriptive fields rather than identity substitutes.

`component.rtg.evidence_bounded_synthesis` is the separate consumer boundary for future
model-driven claims over that deterministic record. It rejects uncited claims, unknown citations,
one-graph claims presented as comparisons, and inference claims that omit uncertainty. Citation
presence bounds the generator's evidence surface but does not prove semantic entailment. No MCP
tool or model adapter is wired to this draft component yet.

`vellis_resolve_citation` makes one of those citations actionable. It accepts only canonical
`(graph_id, local_uuid)` identity, restores the owning graph's declared snapshot, executes the one
bounded `metadata.citation_projection`, and returns every projection row carrying that exact anchor
UUID plus snapshot and query provenance. It does not infer a graph, accept an arbitrary query,
traverse a bridge, join graphs, or write graph state.

`vellis_traverse_bridge` is the controlled bridge follow-up. It accepts one explicit confirmed
`bridge_id`, rejects inactive assertions, resolves source and target independently through their
bounded citation projections, and returns the paired records with bridge confidence and provenance.
It does not accept candidate ids, expand paths, merge identities, or produce a joined row.

Supported graph-local reads are descriptor-driven. A graph advertises automatic federated reads
with `metadata.federated_read_capabilities`; each capability names a `query_name` and matching
`terms`, `domains`, or `tags`. New reads should also name an `implementation` in
`module:attribute` format that resolves to a `CannedQuery` object or factory. Explicit
`graph_id=query_name` overrides may still be supplied for experiments, but new automatic federated
reads should be added to the descriptor metadata and query module rather than hardcoded into the
router.

The current descriptor-declared reads cover repo component evidence, Personal Ops attention,
Gothic source verification, and Experience Studio publication readiness. The Experience Studio
read returns ordered publication checks, unresolved review gates, and check-qualified citations;
its readiness result is reviewable planning evidence rather than legal certification.

Use `just rtg-federated-capability-template <query_name>` to print a descriptor snippet and module
skeleton for a new read, then add the descriptor metadata and module implementation. Run
`just rtg-federated-capabilities-check` before relying on the read; it exits non-zero when any
declared capability cannot load.

Use `just rtg-federation-eval` after changing descriptor domains or tags, route scoring, intent
normalization, or write-target rules. It evaluates the versioned cases in
`docs/guides/vellis/evals/rtg-federation-routing-cases.json` and exits non-zero with field-level mismatches when
observed routes, plans, route-pack preview fields, or route-pack gate decisions drift from the
expected contract.

Use `just rtg-federation-workload-eval` after changing executable federation behavior. It runs the
versioned cases in `docs/guides/vellis/evals/rtg-federation-workload-cases.json` against declared snapshots and
scores execution coverage, limitations, sampled citation resolution, confirmed-bridge traversal,
temporal scope, answer usefulness, source-bounded semantic claim grounding, and no-join/write
boundary safety. Semantic scenarios use deterministic fixture drafts and do not call a model. This
is intentionally a separate gate from the deterministic routing matrix.

The ordinary federation server is model-free. To opt into semantic prose, set `OPENAI_API_KEY` and
launch `just rtg-federation-mcp-semantic <model>`, then call
`vellis_federated_semantic_answer`. That tool executes the deterministic federated answer first and
passes only its evidence envelope to OpenAI Responses Structured Outputs with storage disabled.
Generated claims remain subject to the evidence-bounded component and report entailment as
unverified.

When no confirmed bridge matches a planned graph pair, `candidate_hints` may list `candidate_only`
proposals from `bridges.json`. Candidate hints include confidence, evidence refs, and a review
checklist, but `traversal_permission` is always `false` until the candidate is promoted to a bridge
assertion.

Use `vellis_bridge_candidates` / `just rtg-bridge-candidates` to list unresolved proposals, inspect
one with `vellis_bridge_candidate` / `just rtg-bridge-candidate <candidate_id>`, then either promote
or reject it. Promotion appends or replaces a confirmed bridge assertion in `bridges.json` and marks
the candidate `promoted`; rejection marks only the candidate record. These operations mutate the
bridge catalog, not any graph monograph.

`vellis_route_query` is a read-only shortcut for one selected graph. It compiles a route, refuses
ambiguous routes, restores the descriptor's `metadata.snapshot_path` when present, and executes one
RTG query in-process. It does not perform cross-graph joins or writes. For broader graph-local work,
use `vellis_graph_mcp_info` or `just rtg-monograph-mcp-info <graph_id>` to attach to that graph's
own RTG MCP server.

Current canned routed queries include:

- `repo_components_evidence_status`, which answers which repo-twin components lack associated
  evidence records. Its implementation lives at
  `apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY`.
- `personal_attention_overview`, which summarizes personal operating graph commitments, routines,
  decisions, evidence gaps, and relationship open loops needing attention. Its implementation lives
  at `apps.rtg_federation.queries.personal_attention_overview:CANNED_QUERY`.
- `gothic_source_index`, which indexes Gothic archive works, sources, passages, reading trails, and
  source-verification gaps. Its implementation lives at
  `apps.rtg_federation.queries.gothic_source_index:CANNED_QUERY`.

The agent runbook is
[`../guides/vellis/evals/rtg-federation-control-plane-runbook.md`](../guides/vellis/evals/rtg-federation-control-plane-runbook.md).

## Routing Rules

- Reads may auto-route when one graph is a high-confidence match.
- Ambiguous reads return candidates and require a human or agent to choose.
- Writes require an explicit graph target.
- Cross-graph references and citations must carry `(graph_id, local_uuid)`; never pass a raw UUID,
  title, or domain key as if it were globally meaningful.
- Bridge hints are reified assertions from `bridges.json`; they guide graph-local follow-up reads
  but do not authorize joins or writes.
- Checklist items are plans only; agents must still invoke graph-local MCP tools deliberately.
- Candidate hints are review prompts only; they must be promoted or rejected before traversal.
- Candidate promotion and rejection mutate only `bridges.json`; graph monographs remain untouched.
- Bridge traversal requires one explicit active confirmed bridge and keeps endpoint projections
  separate; it does not authorize path expansion or cross-graph joins.

## Adding A Monograph

Add a descriptor to `registry.json` with:

- `graph_id`: stable registry id.
- `storage_root`: JSON File Storage root for the RTG app.
- `sql_database_path`: controller SQLite ledger path.
- `authority`: where truth comes from, such as `derived_from_repo` or `user_authored`.
- `write_policy`: routing guidance, such as `sync_only` or `explicit_target_required`.
- `domains` and `tags`: vocabulary the intent compiler can match.
- `mcp_endpoint`: localhost MCP launch/client hint.
- `metadata.federated_read_capabilities`: optional read-only query capabilities for
  `vellis_federated_answer`, each with `query_name`, an optional `implementation` module path, and
  matching vocabulary.
- `metadata.citation_projection`: optional bounded citation dereference capability with a
  `query_name` identifying exactly one declared federated read and an `anchor_bucket` returned by
  that canned query.

Then run:

```sh
just rtg-graphs
just rtg-federated-capabilities
just rtg-federated-capabilities-check
just rtg-federation-eval
just rtg-federation-preflight
just rtg-route read "<a representative question>"
```
