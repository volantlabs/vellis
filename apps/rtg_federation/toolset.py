from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from apps.rtg_federation.registry_io import (
    bridge_candidate_payload,
    bridge_candidates_payload,
    bridge_traversal_payload,
    citation_resolution_payload,
    federated_answer_payload,
    federated_capabilities_payload,
    federated_plan_payload,
    federated_preflight_payload,
    federated_semantic_answer_payload,
    list_graphs_payload,
    load_optional_bridge_store,
    mcp_info_payload,
    promote_bridge_candidate_payload,
    reject_bridge_candidate_payload,
    route_pack_gate_payload,
    route_pack_preview_payload,
    route_payload,
    route_query_payload,
)
from components.rtg.evidence_bounded_synthesis import RtgSemanticDraftGenerator
from components.rtg.graph_bridge import RtgGraphBridge
from components.rtg.graph_registry import (
    RtgGraphFederatedIntent,
    RtgGraphIntent,
    RtgGraphRegistry,
    RtgGraphRegistryError,
    RtgGraphRegistryInvalid,
)

TOOL_NAMES = (
    "vellis_list_graphs",
    "vellis_federated_capabilities",
    "vellis_federated_preflight",
    "vellis_intent_compile",
    "vellis_route_pack_preview",
    "vellis_route_pack_gate",
    "vellis_federated_plan",
    "vellis_federated_answer",
    "vellis_federated_semantic_answer",
    "vellis_resolve_citation",
    "vellis_traverse_bridge",
    "vellis_graph_mcp_info",
    "vellis_route_query",
    "vellis_bridge_candidates",
    "vellis_bridge_candidate",
    "vellis_promote_bridge_candidate",
    "vellis_reject_bridge_candidate",
)

TOOL_DESCRIPTIONS = {
    "vellis_list_graphs": (
        "List registered local RTG graph monographs with storage roots, routing vocabulary, "
        "write policies, and MCP endpoint hints."
    ),
    "vellis_federated_capabilities": (
        "List descriptor-declared federated read capabilities by graph and report whether each "
        "capability maps to a known read-only canned query. This does not execute reads."
    ),
    "vellis_federated_preflight": (
        "Check whether descriptor-declared federated reads have ready implementations, loadable "
        "snapshots, and accepted graph validation. This is read-only and does not execute query "
        "capabilities."
    ),
    "vellis_intent_compile": (
        "Compile a user or agent intent into ranked candidate RTG graph routes. Reads may "
        "auto-select one unambiguous high-confidence graph; writes require target_graph_id."
    ),
    "vellis_route_pack_preview": (
        "Assemble an advisory route pack for one intent: selected skill hand-off, scoped "
        "federation and graph-local tools, required docs, verification commands, capabilities, "
        "preflight state, route/plan records, and hazards. This does not execute graph reads, "
        "proxy writes, or perform cross-graph joins."
    ),
    "vellis_route_pack_gate": (
        "Evaluate a route pack for one intent and return an execution decision: invoke, clarify, "
        "or blocked. The gate normalizes selected skill, graph targets, allowed tools, required "
        "verification, freshness state, and hazards. It does not execute graph reads, proxy "
        "writes, or perform cross-graph joins."
    ),
    "vellis_federated_plan": (
        "Compile a read-oriented intent into graph-local plan steps across all matching "
        "registered graph monographs, including active bridge assertions and graph-local "
        "follow-up checklist items as planning hints when configured. When no confirmed bridge "
        "matches, candidate-only proposals may be returned without traversal permission. This "
        "does not execute queries, resolve identities, or perform cross-graph joins."
    ),
    "vellis_federated_answer": (
        "Compile a read-oriented federated plan, execute supported graph-local canned reads, and "
        "return a structured synthesis record with graph-qualified citations. Unsupported graph "
        "reads and candidate-only bridge hints are reported as limitations. This does not perform "
        "cross-graph joins or writes."
    ),
    "vellis_federated_semantic_answer": (
        "Run the deterministic federated answer first, then use the explicitly configured "
        "semantic generator to propose claims and validate every claim against source-bound "
        "graph-qualified citations. Model execution is opt-in at server launch. This does not "
        "perform cross-graph joins or writes."
    ),
    "vellis_resolve_citation": (
        "Resolve one canonical (graph_id, local_uuid) citation through the graph's "
        "descriptor-declared bounded projection. Returns the exact graph-local source row and "
        "snapshot/query provenance when found. This does not route by intent, join graphs, or "
        "write graph state."
    ),
    "vellis_traverse_bridge": (
        "Resolve both graph-qualified endpoints of one explicit active confirmed bridge through "
        "their descriptor-declared citation projections. Returns paired endpoint records without "
        "joining or merging them. Candidate-only and revoked bridges are not traversable; this "
        "tool does not write graph or bridge state."
    ),
    "vellis_graph_mcp_info": (
        "Return launch and MCP client configuration for one registered graph. This does not "
        "start the graph server."
    ),
    "vellis_route_query": (
        "Compile a read intent, refuse ambiguous routes, then execute one RTG query against the "
        "selected registered graph using direct in-process controller composition. This read-only "
        "tool does not perform cross-graph joins or writes."
    ),
    "vellis_bridge_candidates": (
        "List candidate bridge proposals from the configured bridge catalog. Candidate-only "
        "records are review prompts and do not grant traversal permission."
    ),
    "vellis_bridge_candidate": (
        "Inspect one candidate bridge proposal by deterministic candidate_id from the configured "
        "bridge catalog."
    ),
    "vellis_promote_bridge_candidate": (
        "Promote one candidate-only bridge proposal into a confirmed bridge assertion in the "
        "configured bridge catalog. This mutates only the bridge catalog, not graph monographs."
    ),
    "vellis_reject_bridge_candidate": (
        "Reject one candidate-only bridge proposal in the configured bridge catalog with an "
        "explicit reason. This mutates only the bridge catalog, not graph monographs."
    ),
}


class RtgFederationToolset:
    def __init__(
        self,
        registry: RtgGraphRegistry,
        bridge_store: RtgGraphBridge | None = None,
        bridge_catalog_path: Path | None = None,
        semantic_generator: RtgSemanticDraftGenerator | None = None,
    ) -> None:
        self._registry = registry
        self._bridge_store = bridge_store
        self._bridge_catalog_path = bridge_catalog_path
        self._semantic_generator = semantic_generator

    def vellis_list_graphs(self) -> dict[str, Any]:
        return self._response(lambda: list_graphs_payload(self._registry))

    def vellis_federated_capabilities(self) -> dict[str, Any]:
        return self._response(lambda: federated_capabilities_payload(self._registry))

    def vellis_federated_preflight(self) -> dict[str, Any]:
        return self._response(lambda: federated_preflight_payload(self._registry))

    def vellis_intent_compile(
        self,
        text: str,
        operation: str = "read",
        target_graph_id: str | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: route_payload(
                self._registry.compile_intent(
                    RtgGraphIntent(
                        operation=operation,
                        text=text,
                        target_graph_id=target_graph_id,
                        domain_hints=tuple(domain_hints or ()),
                        tag_hints=tuple(tag_hints or ()),
                    )
                )
            )
        )

    def vellis_graph_mcp_info(self, graph_id: str) -> dict[str, Any]:
        return self._response(lambda: mcp_info_payload(self._registry, graph_id))

    def vellis_route_pack_preview(
        self,
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: route_pack_preview_payload(
                self._registry,
                text=text,
                operation=operation,
                target_graph_ids=tuple(target_graph_ids or ()),
                domain_hints=tuple(domain_hints or ()),
                tag_hints=tuple(tag_hints or ()),
                bridge_store=self._bridge_store,
            )
        )

    def vellis_route_pack_gate(
        self,
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: route_pack_gate_payload(
                self._registry,
                text=text,
                operation=operation,
                target_graph_ids=tuple(target_graph_ids or ()),
                domain_hints=tuple(domain_hints or ()),
                tag_hints=tuple(tag_hints or ()),
                bridge_store=self._bridge_store,
            )
        )

    def vellis_federated_plan(
        self,
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: federated_plan_payload(
                self._registry.compile_federated_intent(
                    RtgGraphFederatedIntent(
                        operation=operation,
                        text=text,
                        target_graph_ids=tuple(target_graph_ids or ()),
                        domain_hints=tuple(domain_hints or ()),
                        tag_hints=tuple(tag_hints or ()),
                    )
                ),
                self._bridge_store,
            )
        )

    def vellis_federated_answer(
        self,
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
        canned_queries: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: federated_answer_payload(
                self._registry,
                text=text,
                operation=operation,
                target_graph_ids=tuple(target_graph_ids or ()),
                domain_hints=tuple(domain_hints or ()),
                tag_hints=tuple(tag_hints or ()),
                bridge_store=self._bridge_store,
                canned_queries=canned_queries,
            )
        )

    def vellis_federated_semantic_answer(
        self,
        text: str,
        operation: str = "read",
        target_graph_ids: list[str] | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
        canned_queries: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: federated_semantic_answer_payload(
                self._registry,
                text=text,
                operation=operation,
                target_graph_ids=tuple(target_graph_ids or ()),
                domain_hints=tuple(domain_hints or ()),
                tag_hints=tuple(tag_hints or ()),
                bridge_store=self._bridge_store,
                canned_queries=canned_queries,
                semantic_generator=self._require_semantic_generator(),
            )
        )

    def vellis_resolve_citation(
        self,
        graph_id: str,
        local_uuid: str,
    ) -> dict[str, Any]:
        return self._response(
            lambda: citation_resolution_payload(
                self._registry,
                graph_id=graph_id,
                local_uuid=local_uuid,
            )
        )

    def vellis_traverse_bridge(self, bridge_id: str) -> dict[str, Any]:
        return self._response(
            lambda: bridge_traversal_payload(
                self._registry,
                self._require_bridge_store(),
                bridge_id=bridge_id,
            )
        )

    def vellis_route_query(
        self,
        text: str,
        query_spec: dict[str, Any] | None = None,
        query_options: dict[str, Any] | None = None,
        response_options: dict[str, Any] | None = None,
        target_graph_id: str | None = None,
        domain_hints: list[str] | None = None,
        tag_hints: list[str] | None = None,
        canned_query: str | None = None,
    ) -> dict[str, Any]:
        return self._response(
            lambda: route_query_payload(
                self._registry,
                text=text,
                query_spec=query_spec,
                query_options=query_options,
                response_options=response_options,
                target_graph_id=target_graph_id,
                domain_hints=tuple(domain_hints or ()),
                tag_hints=tuple(tag_hints or ()),
                canned_query=canned_query,
            )
        )

    def vellis_bridge_candidates(self, status: str = "candidate_only") -> dict[str, Any]:
        return self._response(
            lambda: bridge_candidates_payload(
                self._require_bridge_catalog_path(),
                status=status,
            )
        )

    def vellis_bridge_candidate(self, candidate_id: str) -> dict[str, Any]:
        return self._response(
            lambda: bridge_candidate_payload(
                self._require_bridge_catalog_path(),
                candidate_id,
            )
        )

    def vellis_promote_bridge_candidate(
        self,
        candidate_id: str,
        asserted_at: str,
        asserted_by: str,
    ) -> dict[str, Any]:
        return self._bridge_catalog_mutation_response(
            lambda: promote_bridge_candidate_payload(
                self._require_bridge_catalog_path(),
                candidate_id=candidate_id,
                asserted_at=asserted_at,
                asserted_by=asserted_by,
            )
        )

    def vellis_reject_bridge_candidate(
        self,
        candidate_id: str,
        rejected_at: str,
        rejected_by: str,
        reason: str,
    ) -> dict[str, Any]:
        return self._bridge_catalog_mutation_response(
            lambda: reject_bridge_candidate_payload(
                self._require_bridge_catalog_path(),
                candidate_id=candidate_id,
                rejected_at=rejected_at,
                rejected_by=rejected_by,
                reason=reason,
            )
        )

    def _response(self, action: Callable[[], object]) -> dict[str, Any]:
        try:
            return {"ok": True, "result": action()}
        except RtgGraphRegistryError as error:
            return {"ok": False, "error": _error_payload(error)}
        except Exception as error:  # noqa: BLE001 - keep one error shape on the MCP boundary
            return {"ok": False, "error": _error_payload(error)}

    def _bridge_catalog_mutation_response(self, action: Callable[[], object]) -> dict[str, Any]:
        response = self._response(action)
        if response["ok"] is True and self._bridge_catalog_path is not None:
            self._bridge_store = load_optional_bridge_store(self._bridge_catalog_path)
        return response

    def _require_bridge_catalog_path(self) -> Path:
        if self._bridge_catalog_path is None:
            raise RtgGraphRegistryInvalid("bridge catalog path is not configured")
        return self._bridge_catalog_path

    def _require_bridge_store(self) -> RtgGraphBridge:
        if self._bridge_store is None:
            raise RtgGraphRegistryInvalid("bridge catalog is not configured")
        return self._bridge_store

    def _require_semantic_generator(self) -> RtgSemanticDraftGenerator:
        if self._semantic_generator is None:
            raise RtgGraphRegistryInvalid(
                "semantic synthesis is not configured; start the server with --semantic-model"
            )
        return self._semantic_generator


def mcp_tool_metadata() -> tuple[dict[str, str], ...]:
    return tuple({"name": name, "description": TOOL_DESCRIPTIONS[name]} for name in TOOL_NAMES)


def _error_payload(error: Exception) -> dict[str, str]:
    return {"type": type(error).__name__, "message": str(error)}
