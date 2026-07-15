from __future__ import annotations

import copy
import json
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from apps.rtg_federation.canned_queries import (
    FederatedReadCapability,
    citations_for_canned_answer,
    federated_read_capabilities_from_metadata,
    infer_federated_read_capability,
    resolve_canned_query,
    summarize_canned_query,
)
from apps.rtg_knowledge_graph.composition import RtgKnowledgeGraphComposition, build_app
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_codec import decode_system_snapshot
from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from components.rtg.bridge_traversal import (
    DeterministicRtgBridgeTraverser,
    RtgBridgeTraversalRequest,
)
from components.rtg.citation_resolution import (
    DeterministicRtgCitationResolver,
    RtgCitationProjectionRead,
    RtgCitationProjectionSpec,
    RtgCitationResolutionRequest,
)
from components.rtg.controller import (
    RtgControllerError,
    RtgControllerRestoreOptions,
    RtgControllerSnapshotFailed,
)
from components.rtg.evidence_bounded_synthesis import (
    EvidenceBoundedRtgSynthesizer,
    RtgEvidenceBoundedSynthesisRequest,
    RtgSemanticDraftGenerator,
)
from components.rtg.federated_synthesis import (
    DeterministicRtgFederatedSynthesizer,
    RtgFederatedBridgeContext,
    RtgFederatedCandidateNotice,
    RtgFederatedCitation,
    RtgFederatedGraphRead,
    RtgFederatedSynthesisRecord,
    RtgFederatedSynthesisRequest,
)
from components.rtg.graph_bridge import (
    InMemoryRtgGraphBridge,
    RtgGraphBridge,
    RtgGraphBridgeCandidate,
    RtgGraphBridgeCandidateDraft,
    RtgGraphBridgeDraft,
    RtgGraphLocalReference,
)
from components.rtg.graph_registry import (
    InMemoryRtgGraphRegistry,
    RtgGraphDescriptor,
    RtgGraphFederatedIntent,
    RtgGraphIntent,
    RtgGraphMcpEndpoint,
    RtgGraphRegistry,
    RtgGraphRegistryInvalid,
)
from components.rtg.route_pack import (
    DeterministicRtgRoutePackBuilder,
    DeterministicRtgRoutePackGate,
    JsonObject,
    RtgRoutePackAssemblyRequest,
)
from components.storage.json_file import StorageError
from components.storage.sql import SqlStorageError

DEFAULT_REGISTRY_PATH = Path("docs/rtg-monographs/registry.json")
DEFAULT_BRIDGE_FILENAME = "bridges.json"
BRIDGE_CANDIDATE_STATUSES = ("candidate_only", "promoted", "rejected")


def load_registry(path: Path) -> InMemoryRtgGraphRegistry:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("registry root must be a JSON object")
    graphs = payload.get("graphs")
    if not isinstance(graphs, list):
        raise RtgGraphRegistryInvalid("registry must contain a graphs list")
    registry = InMemoryRtgGraphRegistry.empty()
    seen: set[str] = set()
    for graph_payload in graphs:
        graph = _descriptor_from_payload(graph_payload)
        if graph.graph_id in seen:
            raise RtgGraphRegistryInvalid(f"duplicate graph_id in registry: {graph.graph_id}")
        seen.add(graph.graph_id)
        registry.put_graph(graph)
    return registry


def default_bridge_path_for_registry(registry_path: Path) -> Path:
    return registry_path.with_name(DEFAULT_BRIDGE_FILENAME)


def load_bridge_store(path: Path) -> InMemoryRtgGraphBridge:
    payload = _load_bridge_catalog_payload(path)
    bridges = payload["bridges"]
    candidates = payload["candidates"]
    store = InMemoryRtgGraphBridge.empty()
    for bridge_payload in bridges:
        store.put_bridge(_bridge_draft_from_payload(bridge_payload))
    for candidate_payload in candidates:
        if _bridge_candidate_status_from_payload(candidate_payload) == "candidate_only":
            store.put_candidate(_bridge_candidate_from_payload(candidate_payload))
    return store


def load_optional_bridge_store(path: Path) -> InMemoryRtgGraphBridge | None:
    if not path.is_file():
        return None
    return load_bridge_store(path)


def list_graphs_payload(registry: RtgGraphRegistry) -> dict[str, Any]:
    return {"graphs": [_graph_payload(graph) for graph in registry.list_graphs().graphs]}


def route_payload(route: Any) -> dict[str, Any]:
    return asdict(route)


def federated_plan_payload(
    plan: Any,
    bridge_store: RtgGraphBridge | None = None,
) -> dict[str, Any]:
    payload = asdict(plan)
    payload["cross_graph_reference_rule"] = (
        "references must carry canonical (graph_id, local_uuid) identity"
    )
    payload["bridge_hints"] = _bridge_hints_payload(plan, bridge_store)
    return payload


def federated_capabilities_payload(registry: RtgGraphRegistry) -> dict[str, Any]:
    graphs = [_graph_capabilities_payload(graph) for graph in registry.list_graphs().graphs]
    ready_capability_count = sum(
        1
        for graph in graphs
        for capability in graph["capabilities"]
        if capability["status"] == "ready"
    )
    return {
        "graph_count": len(graphs),
        "ready_capability_count": ready_capability_count,
        "graphs": graphs,
    }


def federated_preflight_payload(registry: RtgGraphRegistry) -> dict[str, Any]:
    graphs = [_graph_preflight_payload(graph) for graph in registry.list_graphs().graphs]
    not_ready_graph_ids = [graph["graph_id"] for graph in graphs if graph["status"] == "not_ready"]
    return {
        "status": "passed" if not not_ready_graph_ids else "failed",
        "graph_count": len(graphs),
        "ready_graph_count": sum(1 for graph in graphs if graph["status"] == "ready"),
        "skipped_graph_count": sum(
            1 for graph in graphs if graph["status"] == "no_federated_reads"
        ),
        "not_ready_graph_count": len(not_ready_graph_ids),
        "not_ready_graph_ids": not_ready_graph_ids,
        "graphs": graphs,
    }


def route_pack_preview_payload(
    registry: RtgGraphRegistry,
    *,
    text: str,
    operation: str = "read",
    target_graph_ids: tuple[str, ...] = (),
    domain_hints: tuple[str, ...] = (),
    tag_hints: tuple[str, ...] = (),
    bridge_store: RtgGraphBridge | None = None,
    preflight_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    single_target = target_graph_ids[0] if len(target_graph_ids) == 1 else None
    route = registry.compile_intent(
        RtgGraphIntent(
            operation=operation,
            text=text,
            target_graph_id=single_target,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )
    )
    plan = registry.compile_federated_intent(
        RtgGraphFederatedIntent(
            operation=operation,
            text=text,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )
    )
    route_record = route_payload(route)
    plan_record = federated_plan_payload(plan, bridge_store)
    capabilities = federated_capabilities_payload(registry)
    preflight = (
        copy.deepcopy(preflight_override)
        if preflight_override is not None
        else federated_preflight_payload(registry)
    )
    graph_ids = _route_pack_graph_ids(route_record, plan_record)
    graph_contexts = [
        _route_pack_graph_context(
            registry.get_graph(graph_id),
            capabilities=capabilities,
            preflight=preflight,
        )
        for graph_id in graph_ids
    ]
    direct_read = _route_pack_direct_read_profile(
        operation=operation,
        route_record=route_record,
        graph_contexts=graph_contexts,
    )
    selected_skill = _route_pack_selected_skill(direct_read)
    scoped_tools = _route_pack_scoped_tools(
        text=text,
        operation=operation,
        direct_read=direct_read,
    )
    required_docs = _route_pack_required_docs(direct_read)
    verification_commands = _route_pack_verification_commands(direct_read)
    freshness_and_evidence = _route_pack_freshness_and_evidence(
        preflight=preflight,
        capabilities=capabilities,
        direct_read=direct_read,
    )
    hazards = _route_pack_hazards(
        operation=operation,
        target_graph_ids=target_graph_ids,
        route_record=route_record,
        plan_record=plan_record,
        graph_contexts=graph_contexts,
    )
    return DeterministicRtgRoutePackBuilder().assemble(
        RtgRoutePackAssemblyRequest(
            intent={
                "text": text,
                "operation": operation,
                "target_graph_ids": list(target_graph_ids),
                "domain_hints": list(domain_hints),
                "tag_hints": list(tag_hints),
            },
            selected_skill=selected_skill,
            scoped_tools=scoped_tools,
            required_docs=required_docs,
            verification_commands=verification_commands,
            freshness_and_evidence=freshness_and_evidence,
            identity_and_citation_rules={
                "canonical_identity": "(graph_id, local_uuid)",
                "raw_uuid_scope": "graph-local only",
                "citation_resolution": "vellis_resolve_citation or just rtg-citation-resolve",
                "bridge_traversal": "vellis_traverse_bridge or just rtg-bridge-traverse",
                "cross_graph_join_execution": "not_performed",
            },
            single_graph_route=route_record,
            federated_plan=plan_record,
            graph_contexts=tuple(graph_contexts),
            hazards=tuple(hazards),
        )
    )


def route_pack_gate_payload(
    registry: RtgGraphRegistry,
    *,
    text: str,
    operation: str = "read",
    target_graph_ids: tuple[str, ...] = (),
    domain_hints: tuple[str, ...] = (),
    tag_hints: tuple[str, ...] = (),
    bridge_store: RtgGraphBridge | None = None,
    preflight_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route_pack = route_pack_preview_payload(
        registry,
        text=text,
        operation=operation,
        target_graph_ids=target_graph_ids,
        domain_hints=domain_hints,
        tag_hints=tag_hints,
        bridge_store=bridge_store,
        preflight_override=preflight_override,
    )
    return route_pack_gate_from_preview(route_pack)


def route_pack_gate_from_preview(route_pack: dict[str, Any]) -> dict[str, Any]:
    return DeterministicRtgRoutePackGate().evaluate(route_pack)


def mcp_info_payload(registry: RtgGraphRegistry, graph_id: str) -> dict[str, Any]:
    graph = registry.get_graph(graph_id)
    endpoint = _require_http_endpoint(graph)
    storage_root = absolute_graph_path(graph.storage_root)
    sql_database_path = absolute_graph_path(graph.sql_database_path)
    launch = {
        "command": "uv",
        "args": [
            "run",
            "python",
            "-m",
            "apps.rtg_knowledge_graph",
            "serve-mcp",
            "--transport",
            "http",
            "--host",
            endpoint.host or "127.0.0.1",
            "--port",
            str(endpoint.port or 8765),
            "--path",
            endpoint.path,
            "--storage-root",
            str(storage_root),
            "--sql-database-path",
            str(sql_database_path),
        ],
    }
    server_name = endpoint.server_name or f"vellis_{graph.graph_id}"
    url = f"http://{endpoint.host}:{endpoint.port}{endpoint.path}"
    return {
        "graph": _graph_payload(graph),
        "launch": launch,
        "client_config": {
            "mcpServers": {
                server_name: {
                    "transport": "http",
                    "url": url,
                }
            }
        },
    }


def citation_resolution_payload(
    registry: RtgGraphRegistry,
    *,
    graph_id: str,
    local_uuid: str,
) -> dict[str, Any]:
    resolver = DeterministicRtgCitationResolver.open(
        _RegistryCitationProjectionCatalog(registry),
        _RegistryCitationProjectionReader(registry),
    )
    return asdict(
        resolver.resolve(
            RtgCitationResolutionRequest(
                graph_id=graph_id,
                local_uuid=local_uuid,
            )
        )
    )


def bridge_traversal_payload(
    registry: RtgGraphRegistry,
    bridge_store: RtgGraphBridge,
    *,
    bridge_id: str,
) -> dict[str, Any]:
    resolver = DeterministicRtgCitationResolver.open(
        _RegistryCitationProjectionCatalog(registry),
        _RegistryCitationProjectionReader(registry),
    )
    traverser = DeterministicRtgBridgeTraverser.open(bridge_store, resolver)
    traversal = traverser.traverse(
        RtgBridgeTraversalRequest(bridge_id=bridge_id),
    )
    return {
        "status": traversal.status,
        "bridge": _bridge_assertion_payload(traversal.bridge),
        "source": {
            "reference": _bridge_reference_payload(traversal.source.reference),
            "resolution": asdict(traversal.source.resolution),
        },
        "target": {
            "reference": _bridge_reference_payload(traversal.target.reference),
            "resolution": asdict(traversal.target.resolution),
        },
        "join_execution": "not_performed",
    }


def init_graph_payload(registry: RtgGraphRegistry, graph_id: str) -> dict[str, Any]:
    graph = registry.get_graph(graph_id)
    config = RtgKnowledgeGraphConfig(
        storage_root=absolute_graph_path(graph.storage_root),
        sql_database_path=absolute_graph_path(graph.sql_database_path),
    )
    composition = build_app(config)
    run_status = composition.runner.run()
    validation = RtgMcpToolset(composition.controller).rtg_validate_graph()
    return {
        "graph": _graph_payload(graph),
        "app": run_status.to_json_value(),
        "validation": validation,
    }


def route_query_payload(
    registry: RtgGraphRegistry,
    *,
    text: str,
    query_spec: dict[str, Any] | None = None,
    query_options: dict[str, Any] | None = None,
    response_options: dict[str, Any] | None = None,
    target_graph_id: str | None = None,
    domain_hints: tuple[str, ...] = (),
    tag_hints: tuple[str, ...] = (),
    canned_query: str | None = None,
    canned_query_implementation: str | None = None,
) -> dict[str, Any]:
    canned = (
        None
        if canned_query is None
        else resolve_canned_query(canned_query, implementation=canned_query_implementation)
    )
    effective_query_spec = query_spec
    effective_query_options = query_options
    effective_response_options = response_options
    if canned is not None:
        effective_query_spec = effective_query_spec or canned.query_spec
        effective_query_options = effective_query_options or canned.query_options
        effective_response_options = effective_response_options or canned.response_options
    if effective_query_spec is None:
        raise RtgGraphRegistryInvalid("query_spec is required unless canned_query is supplied")

    route = registry.compile_intent(
        RtgGraphIntent(
            operation="read",
            text=text,
            target_graph_id=target_graph_id,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )
    )
    route_record = route_payload(route)
    if route.selected_graph_id is None:
        return {
            "status": "route_requires_confirmation",
            "route": route_record,
            "query_executed": False,
        }

    graph = registry.get_graph(route.selected_graph_id)
    config = RtgKnowledgeGraphConfig(
        storage_root=absolute_graph_path(graph.storage_root),
        sql_database_path=absolute_graph_path(graph.sql_database_path),
    )
    composition = build_app(config)
    restore = _restore_declared_snapshot(composition, graph)
    query = RtgMcpToolset(composition.controller).rtg_execute_query(
        effective_query_spec,
        query_options=effective_query_options,
        response_options=effective_response_options,
    )
    payload = {
        "status": "query_executed",
        "graph": _graph_payload(graph),
        "route": route_record,
        "snapshot_restore": restore,
        "query_executed": True,
        "submitted_query": {
            "query_spec": effective_query_spec,
            "query_options": effective_query_options,
            "response_options": effective_response_options,
        },
        "query": query,
    }
    if canned is not None:
        payload["canned_query"] = {
            "name": canned.name,
            "description": canned.description,
            "implementation": canned.implementation,
        }
        summary_query = dict(query)
        summary_query["request"] = {"text": text}
        payload["answer"] = summarize_canned_query(canned, summary_query)
    return payload


def federated_answer_payload(
    registry: RtgGraphRegistry,
    *,
    text: str,
    operation: str = "read",
    target_graph_ids: tuple[str, ...] = (),
    domain_hints: tuple[str, ...] = (),
    tag_hints: tuple[str, ...] = (),
    bridge_store: RtgGraphBridge | None = None,
    canned_queries: dict[str, str] | None = None,
) -> dict[str, Any]:
    payload, _ = _federated_answer_execution(
        registry,
        text=text,
        operation=operation,
        target_graph_ids=target_graph_ids,
        domain_hints=domain_hints,
        tag_hints=tag_hints,
        bridge_store=bridge_store,
        canned_queries=canned_queries,
    )
    return payload


def federated_semantic_answer_payload(
    registry: RtgGraphRegistry,
    *,
    text: str,
    semantic_generator: RtgSemanticDraftGenerator,
    operation: str = "read",
    target_graph_ids: tuple[str, ...] = (),
    domain_hints: tuple[str, ...] = (),
    tag_hints: tuple[str, ...] = (),
    bridge_store: RtgGraphBridge | None = None,
    canned_queries: dict[str, str] | None = None,
) -> dict[str, Any]:
    deterministic, source = _federated_answer_execution(
        registry,
        text=text,
        operation=operation,
        target_graph_ids=target_graph_ids,
        domain_hints=domain_hints,
        tag_hints=tag_hints,
        bridge_store=bridge_store,
        canned_queries=canned_queries,
    )
    if source is None:
        return {
            "status": "deterministic_answer_not_executable",
            "model_execution": "not_performed",
            "deterministic_answer": deterministic,
            "join_execution": "not_performed",
            "write_execution": "not_performed",
        }
    semantic = EvidenceBoundedRtgSynthesizer.open(semantic_generator).synthesize(
        RtgEvidenceBoundedSynthesisRequest(intent_text=text, source=source)
    )
    model_execution = (
        "not_performed"
        if source.status == "no_supported_reads" or not source.citations
        else "performed"
    )
    return {
        "status": semantic.status,
        "model_execution": model_execution,
        "deterministic_answer": deterministic,
        "semantic_synthesis": asdict(semantic),
        "join_execution": "not_performed",
        "write_execution": "not_performed",
    }


def _federated_answer_execution(
    registry: RtgGraphRegistry,
    *,
    text: str,
    operation: str,
    target_graph_ids: tuple[str, ...],
    domain_hints: tuple[str, ...],
    tag_hints: tuple[str, ...],
    bridge_store: RtgGraphBridge | None,
    canned_queries: dict[str, str] | None,
) -> tuple[dict[str, Any], RtgFederatedSynthesisRecord | None]:
    plan = registry.compile_federated_intent(
        RtgGraphFederatedIntent(
            operation=operation,
            text=text,
            target_graph_ids=target_graph_ids,
            domain_hints=domain_hints,
            tag_hints=tag_hints,
        )
    )
    plan_record = federated_plan_payload(plan, bridge_store)
    if plan.intent.operation != "read" or not plan.executable or plan.requires_confirmation:
        return (
            {
                "status": "plan_not_executable",
                "plan": plan_record,
                "read_execution": "not_performed",
                "join_execution": "not_performed",
                "write_execution": "not_performed",
            },
            None,
        )

    reads = tuple(
        _federated_graph_read_for_step(
            registry,
            step,
            text=text,
            canned_queries=canned_queries,
        )
        for step in plan.steps
    )
    bridge_hints = plan_record["bridge_hints"]
    synthesis = DeterministicRtgFederatedSynthesizer().synthesize(
        RtgFederatedSynthesisRequest(
            intent_text=text,
            reads=reads,
            bridges=_bridge_contexts_from_hints(bridge_hints),
            candidate_notices=_candidate_notices_from_hints(bridge_hints),
        )
    )
    return (
        {
            "status": synthesis.status,
            "plan": plan_record,
            "read_execution": "performed",
            "join_execution": "not_performed",
            "write_execution": "not_performed",
            "synthesis": asdict(synthesis),
        },
        synthesis,
    )


def bridge_candidates_payload(
    path: Path,
    *,
    status: str = "candidate_only",
) -> dict[str, Any]:
    status_filter = _normalize_candidate_status_filter(status)
    records = _bridge_candidate_records(path)
    candidates = [
        candidate
        for _, candidate, _ in records
        if status_filter == "all" or candidate.status == status_filter
    ]
    return {
        "bridge_catalog_path": str(path.resolve()),
        "status_filter": status_filter,
        "candidate_count": len(candidates),
        "candidates": [_bridge_candidate_payload(candidate) for candidate in candidates],
    }


def bridge_candidate_payload(path: Path, candidate_id: str) -> dict[str, Any]:
    _, candidate, _ = _find_bridge_candidate_record(path, candidate_id)
    return {
        "bridge_catalog_path": str(path.resolve()),
        "candidate": _bridge_candidate_payload(candidate),
    }


def promote_bridge_candidate_payload(
    path: Path,
    *,
    candidate_id: str,
    asserted_at: str,
    asserted_by: str,
) -> dict[str, Any]:
    catalog = _load_bridge_catalog_payload(path)
    index, candidate, raw_candidate = _find_bridge_candidate_record_in_payload(
        catalog,
        candidate_id,
    )
    if candidate.status != "candidate_only":
        raise RtgGraphRegistryInvalid("only candidate_only candidates can be promoted")

    store = InMemoryRtgGraphBridge.empty()
    store.put_candidate(_bridge_candidate_from_payload(raw_candidate))
    bridge = store.promote_candidate(
        candidate.candidate_id,
        asserted_at=asserted_at,
        asserted_by=asserted_by,
    )
    catalog["bridges"] = _upsert_bridge_catalog_payload(catalog["bridges"], bridge)
    updated_candidate = copy.deepcopy(raw_candidate)
    updated_candidate["status"] = "promoted"
    updated_candidate["promoted_bridge_id"] = bridge.bridge_id
    updated_candidate.pop("rejected_at", None)
    updated_candidate.pop("rejected_by", None)
    updated_candidate.pop("rejection_reason", None)
    catalog["candidates"][index] = updated_candidate
    _write_bridge_catalog_payload(path, catalog)
    return {
        "bridge_catalog_path": str(path.resolve()),
        "candidate": _bridge_candidate_payload(
            _bridge_candidate_record_from_payload(updated_candidate)
        ),
        "bridge": _bridge_assertion_payload(bridge),
        "catalog_written": True,
    }


def reject_bridge_candidate_payload(
    path: Path,
    *,
    candidate_id: str,
    rejected_at: str,
    rejected_by: str,
    reason: str,
) -> dict[str, Any]:
    catalog = _load_bridge_catalog_payload(path)
    index, candidate, raw_candidate = _find_bridge_candidate_record_in_payload(
        catalog,
        candidate_id,
    )
    if candidate.status != "candidate_only":
        raise RtgGraphRegistryInvalid("only candidate_only candidates can be rejected")

    store = InMemoryRtgGraphBridge.empty()
    store.put_candidate(_bridge_candidate_from_payload(raw_candidate))
    rejected = store.reject_candidate(
        candidate.candidate_id,
        rejected_at=rejected_at,
        rejected_by=rejected_by,
        reason=reason,
    )
    updated_candidate = copy.deepcopy(raw_candidate)
    updated_candidate["status"] = "rejected"
    updated_candidate["rejected_at"] = rejected.rejected_at
    updated_candidate["rejected_by"] = rejected.rejected_by
    updated_candidate["rejection_reason"] = rejected.rejection_reason
    updated_candidate.pop("promoted_bridge_id", None)
    catalog["candidates"][index] = updated_candidate
    _write_bridge_catalog_payload(path, catalog)
    return {
        "bridge_catalog_path": str(path.resolve()),
        "candidate": _bridge_candidate_payload(
            _bridge_candidate_record_from_payload(updated_candidate)
        ),
        "catalog_written": True,
    }


def absolute_graph_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else path.resolve()


def _federated_graph_read_for_step(
    registry: RtgGraphRegistry,
    step: Any,
    *,
    text: str,
    canned_queries: dict[str, str] | None,
) -> RtgFederatedGraphRead:
    graph = registry.get_graph(step.graph_id)
    capability = infer_federated_read_capability(
        graph_id=graph.graph_id,
        text=text,
        metadata=graph.metadata,
        explicit_queries=canned_queries,
    )
    if capability is None:
        return RtgFederatedGraphRead(
            graph_id=graph.graph_id,
            status="unsupported",
            query_name=None,
            notes=("no supported federated canned query for this graph",),
        )
    query_name = capability.query_name
    payload = route_query_payload(
        registry,
        text=text,
        target_graph_id=graph.graph_id,
        canned_query=query_name,
        canned_query_implementation=capability.implementation,
    )
    query = payload.get("query")
    if not isinstance(query, dict) or query.get("ok") is not True:
        return RtgFederatedGraphRead(
            graph_id=graph.graph_id,
            status="failed",
            query_name=query_name,
            summary={"query": query if isinstance(query, dict) else {}},
            notes=("graph-local query did not return ok",),
        )
    answer = payload.get("answer")
    summary = {
        "canned_query": payload.get("canned_query", {}),
        "answer": answer if isinstance(answer, dict) else {},
        "snapshot_restore": payload.get("snapshot_restore", {}),
        "row_count": query.get("result", {}).get("row_count")
        if isinstance(query.get("result"), dict)
        else None,
    }
    return RtgFederatedGraphRead(
        graph_id=graph.graph_id,
        status="executed",
        query_name=query_name,
        summary=summary,
        citations=_citations_for_federated_read(
            graph_id=graph.graph_id,
            query_name=query_name,
            implementation=capability.implementation,
            answer=answer if isinstance(answer, dict) else {},
        ),
    )


def _citations_for_federated_read(
    *,
    graph_id: str,
    query_name: str,
    implementation: str | None,
    answer: dict[str, Any],
) -> tuple[RtgFederatedCitation, ...]:
    return tuple(
        RtgFederatedCitation(
            graph_id=str(citation["graph_id"]),
            local_uuid=str(citation["local_uuid"]),
            label=None if citation["label"] is None else str(citation["label"]),
            kind=str(citation["kind"]),
        )
        for citation in citations_for_canned_answer(
            graph_id=graph_id,
            query_name=query_name,
            implementation=implementation,
            answer=answer,
        )
    )


def _graph_preflight_payload(graph: RtgGraphDescriptor) -> dict[str, Any]:
    capabilities = _graph_capabilities_payload(graph)
    citation_projection = _citation_projection_readiness_payload(graph)
    if capabilities["capability_count"] == 0 and citation_projection["status"] == "not_declared":
        return {
            "graph_id": graph.graph_id,
            "title": graph.title,
            "status": "no_federated_reads",
            "capabilities": capabilities,
            "citation_projection": citation_projection,
            "snapshot": {"status": "not_checked", "required": False},
            "validation": {"status": "not_checked", "accepted": None},
            "reasons": [],
        }

    reasons: list[str] = []
    if capabilities["status"] != "ready":
        reasons.append("descriptor-declared federated read capabilities are not ready")
    if citation_projection["status"] == "invalid":
        reasons.append("descriptor-declared citation projection is not ready")

    snapshot_path = graph.metadata.get("snapshot_path")
    snapshot: dict[str, Any]
    validation: dict[str, Any]
    if snapshot_path is None:
        snapshot = {"status": "not_configured", "required": True}
        validation = {"status": "not_run", "accepted": None}
        reasons.append("metadata.snapshot_path is required for descriptor-declared reads")
    else:
        try:
            composition = build_app(
                RtgKnowledgeGraphConfig(
                    storage_root=absolute_graph_path(graph.storage_root),
                    sql_database_path=absolute_graph_path(graph.sql_database_path),
                )
            )
            snapshot = {**_restore_declared_snapshot(composition, graph), "required": True}
            validation = _preflight_validation_payload(composition)
            if validation["status"] != "accepted":
                reasons.append("restored graph validation was not accepted")
        except (
            OSError,
            ValueError,
            RtgControllerError,
            RtgGraphRegistryInvalid,
            StorageError,
            SqlStorageError,
        ) as error:
            snapshot = {
                "status": "failed",
                "required": True,
                "snapshot_path": snapshot_path,
                "error": {"type": type(error).__name__, "message": str(error)},
            }
            validation = {"status": "not_run", "accepted": None}
            reasons.append("declared snapshot could not be loaded and restored")

    return {
        "graph_id": graph.graph_id,
        "title": graph.title,
        "status": "ready" if not reasons else "not_ready",
        "capabilities": capabilities,
        "citation_projection": citation_projection,
        "snapshot": snapshot,
        "validation": validation,
        "reasons": reasons,
    }


def _citation_projection_readiness_payload(graph: RtgGraphDescriptor) -> dict[str, Any]:
    try:
        projection = _citation_projection_for_graph(graph)
    except RtgGraphRegistryInvalid as error:
        return {
            "status": "invalid",
            "query_name": None,
            "anchor_bucket": None,
            "error": str(error),
        }
    if projection is None:
        return {
            "status": "not_declared",
            "query_name": None,
            "anchor_bucket": None,
            "error": None,
        }
    return {
        "status": "ready",
        "query_name": projection.query_name,
        "anchor_bucket": projection.anchor_bucket,
        "error": None,
    }


def _preflight_validation_payload(
    composition: RtgKnowledgeGraphComposition,
) -> dict[str, Any]:
    response = RtgMcpToolset(composition.controller).rtg_validate_graph()
    result = response.get("result")
    if response.get("ok") is not True or not isinstance(result, dict):
        error = response.get("error")
        return {
            "status": "error",
            "accepted": False,
            "finding_count": None,
            "error": error if isinstance(error, dict) else None,
        }
    evidence = result.get("evidence")
    finding_count = evidence.get("finding_count") if isinstance(evidence, dict) else None
    accepted = result.get("accepted") is True
    return {
        "status": "accepted" if accepted else "rejected",
        "accepted": accepted,
        "finding_count": finding_count,
        "error": None,
    }


def _graph_capabilities_payload(graph: RtgGraphDescriptor) -> dict[str, Any]:
    try:
        capabilities = federated_read_capabilities_from_metadata(graph.metadata)
    except RtgGraphRegistryInvalid as error:
        return {
            "graph_id": graph.graph_id,
            "title": graph.title,
            "status": "invalid_metadata",
            "capability_count": 0,
            "ready_capability_count": 0,
            "capabilities": [],
            "error": str(error),
        }
    capability_payloads = [_federated_capability_payload(capability) for capability in capabilities]
    ready_count = sum(1 for item in capability_payloads if item["status"] == "ready")
    if not capability_payloads:
        status = "none_declared"
    elif ready_count == len(capability_payloads):
        status = "ready"
    elif ready_count:
        status = "partial"
    else:
        status = "no_ready_capabilities"
    return {
        "graph_id": graph.graph_id,
        "title": graph.title,
        "status": status,
        "capability_count": len(capability_payloads),
        "ready_capability_count": ready_count,
        "capabilities": capability_payloads,
        "error": None,
    }


def _federated_capability_payload(capability: FederatedReadCapability) -> dict[str, Any]:
    try:
        canned = resolve_canned_query(
            capability.query_name,
            implementation=capability.implementation,
        )
    except RtgGraphRegistryInvalid as error:
        return {
            "query_name": capability.query_name,
            "implementation": capability.implementation,
            "description": capability.description,
            "terms": list(capability.terms),
            "domains": list(capability.domains),
            "tags": list(capability.tags),
            "status": "unknown_query",
            "known_query_description": None,
            "resolved_implementation": None,
            "error": str(error),
        }
    return {
        "query_name": capability.query_name,
        "implementation": capability.implementation,
        "description": capability.description,
        "terms": list(capability.terms),
        "domains": list(capability.domains),
        "tags": list(capability.tags),
        "status": "ready",
        "known_query_description": canned.description,
        "resolved_implementation": canned.implementation,
        "error": None,
    }


def _route_pack_graph_ids(
    route_record: dict[str, Any],
    plan_record: dict[str, Any],
) -> list[str]:
    selected = route_record.get("selected_graph_id")
    if isinstance(selected, str) and route_record.get("requires_confirmation") is False:
        high_confidence = [
            step["graph_id"]
            for step in plan_record.get("steps", [])
            if isinstance(step, dict)
            and isinstance(step.get("graph_id"), str)
            and isinstance(step.get("score"), int | float)
            and step["score"] >= 0.5
        ]
        if selected not in high_confidence:
            high_confidence.insert(0, selected)
        return list(dict.fromkeys(high_confidence))
    ordered: list[str] = []
    for graph_id in _route_pack_plan_graph_ids(plan_record):
        if graph_id not in ordered:
            ordered.append(graph_id)
    if isinstance(selected, str) and selected not in ordered:
        ordered.append(selected)
    for candidate in route_record.get("candidates", []):
        if not isinstance(candidate, dict):
            continue
        graph_id = candidate.get("graph_id")
        if isinstance(graph_id, str) and graph_id not in ordered:
            ordered.append(graph_id)
    return ordered


def _route_pack_plan_graph_ids(plan_record: dict[str, Any]) -> list[str]:
    graph_ids: list[str] = []
    for step in plan_record.get("steps", []):
        if not isinstance(step, dict):
            continue
        graph_id = step.get("graph_id")
        if isinstance(graph_id, str) and graph_id not in graph_ids:
            graph_ids.append(graph_id)
    return graph_ids


def _route_pack_selected_skill(direct_read: dict[str, Any] | None) -> JsonObject:
    handoff_chain: list[JsonObject] = []
    if direct_read is None:
        handoff_chain.append(
            {
                "name": "rtg-knowledge-graph-mcp",
                "when": "after a specific graph_id is selected or explicitly confirmed",
                "path": ".agents/skills/rtg-knowledge-graph-mcp/SKILL.md",
            }
        )
    return cast(
        JsonObject,
        {
            "name": "rtg-federation-control-plane",
            "path": ".agents/skills/rtg-federation-control-plane/SKILL.md",
            "handoff_chain": handoff_chain,
            "execution_profile": "descriptor_read" if direct_read is not None else "federated",
        },
    )


def _route_pack_scoped_tools(
    *,
    text: str,
    operation: str,
    direct_read: dict[str, Any] | None,
) -> JsonObject:
    preview = f'just rtg-route-pack-preview "{text}" {operation}'
    gate = f'just rtg-route-pack-gate "{text}" {operation}'
    if direct_read is not None:
        verification = direct_read["verification_commands"]
        return {
            "federation_mcp_tools": [
                "vellis_route_pack_preview",
                "vellis_route_pack_gate",
            ],
            "graph_local_mcp_tools_after_selection": [],
            "just_recipes": [preview, gate, *verification, direct_read["command"]],
        }
    return {
        "federation_mcp_tools": [
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
        ],
        "graph_local_mcp_tools_after_selection": [
            "rtg_validate_graph",
            "rtg_get_system_state",
            "rtg_get_schema_pack",
            "rtg_execute_query",
            "rtg_validate_live_graph_changes",
            "rtg_apply_live_graph_changes",
        ],
        "just_recipes": [
            "just rtg-graphs",
            "just rtg-federated-capabilities",
            "just rtg-federation-preflight",
            "just rtg-federation-workload-eval",
            f'just rtg-route "{text}" {operation}',
            f'just rtg-federated-plan "{text}" {operation}',
            preview,
            gate,
            "just rtg-monograph-mcp-info <graph_id>",
            "just rtg-citation-resolve <graph_id> <local_uuid>",
            "just rtg-bridge-traverse <bridge_id>",
            "just graph-verify",
        ],
    }


def _route_pack_required_docs(direct_read: dict[str, Any] | None) -> tuple[str, ...]:
    if direct_read is not None:
        return tuple(direct_read["required_docs"])
    return (
        "docs/architecture/graph-routed-agent-context.md",
        "docs/rtg-monographs/README.md",
        "docs/guides/vellis/evals/rtg-federation-control-plane-runbook.md",
        "docs/guides/vellis/evals/rtg-federation-workload-cases.json",
        "model/bibliotek/components/component.rtg.route_pack.sysml",
        "model/bibliotek/components/component.rtg.bridge_traversal.sysml",
        "model/bibliotek/components/component.rtg.graph_registry.sysml",
        "model/bibliotek/components/component.rtg.federated_synthesis.sysml",
    )


def _route_pack_verification_commands(
    direct_read: dict[str, Any] | None,
) -> tuple[JsonObject, ...]:
    if direct_read is not None:
        return tuple(
            {"command": command, "when": "before executing the descriptor-declared read"}
            for command in direct_read["verification_commands"]
        )
    return (
        {
            "command": "just rtg-federation-preflight",
            "when": "before broad federated execution",
        },
        {
            "command": "just rtg-federation-eval",
            "when": (
                "after changing graph routing vocabulary, scoring behavior, intent "
                "normalization, or write-target safety"
            ),
        },
        {
            "command": "just rtg-federation-workload-eval",
            "when": (
                "after changing federated read implementations, citation projections, bridge "
                "assertions, temporal behavior, or answer contracts"
            ),
        },
        {
            "command": "just graph-query evidence <component-id>",
            "when": "when the route depends on current component evidence",
        },
        {
            "command": "just graph-query blast-radius <component-id>",
            "when": "before changing shared graph-routing or RTG behavior",
        },
        {
            "command": "just graph-verify",
            "when": "after docs, skills, specs, app metadata, tests, or repo structure change",
        },
    )


def _route_pack_freshness_and_evidence(
    *,
    preflight: dict[str, Any],
    capabilities: dict[str, Any],
    direct_read: dict[str, Any] | None,
) -> JsonObject:
    result: JsonObject = {
        "preflight": copy.deepcopy(preflight),
        "capabilities": copy.deepcopy(capabilities),
        "repo_twin_queries": (
            [direct_read["command"]]
            if direct_read is not None
            else [
                "just graph-query evidence component.rtg.route_pack",
                "just graph-query evidence component.rtg.graph_registry",
                "just graph-query evidence component.rtg.federated_synthesis",
                "just graph-query blast-radius component.rtg.graph_registry",
            ]
        ),
        "note": (
            "Route pack preview is advisory; verification commands must pass in the current "
            "worktree before route claims are trusted."
        ),
    }
    if direct_read is not None:
        result["direct_read"] = copy.deepcopy(direct_read)
        result["stale_recovery_command"] = direct_read.get("stale_recovery_command")
    return result


def _route_pack_direct_read_profile(
    *,
    operation: str,
    route_record: dict[str, Any],
    graph_contexts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    selected = route_record.get("selected_graph_id")
    if operation != "read" or not isinstance(selected, str) or len(graph_contexts) != 1:
        return None
    context = graph_contexts[0]
    if context.get("graph_id") != selected:
        return None
    profile = context.get("route_pack_read")
    capabilities = context.get("capabilities")
    if not isinstance(profile, dict) or not isinstance(capabilities, dict):
        return None
    query_name = profile.get("query_name")
    ready_query_names = {
        capability.get("query_name")
        for capability in capabilities.get("capabilities", [])
        if isinstance(capability, dict) and capability.get("status") == "ready"
    }
    if query_name not in ready_query_names:
        return None
    return copy.deepcopy(profile)


def _route_pack_graph_context(
    graph: RtgGraphDescriptor,
    *,
    capabilities: dict[str, Any],
    preflight: dict[str, Any],
) -> dict[str, Any]:
    endpoint = graph.mcp_endpoint
    return {
        "graph_id": graph.graph_id,
        "title": graph.title,
        "authority": graph.authority,
        "write_policy": graph.write_policy,
        "domains": list(graph.domains),
        "tags": list(graph.tags),
        "mcp_endpoint": None
        if endpoint is None
        else {
            "transport": endpoint.transport,
            "host": endpoint.host,
            "port": endpoint.port,
            "path": endpoint.path,
            "server_name": endpoint.server_name,
        },
        "capabilities": _route_pack_graph_record(capabilities, graph.graph_id),
        "preflight": _route_pack_graph_record(preflight, graph.graph_id),
        "route_pack_read": _route_pack_read_profile(graph),
    }


def _route_pack_read_profile(graph: RtgGraphDescriptor) -> dict[str, Any] | None:
    payload = graph.metadata.get("route_pack_read")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("metadata.route_pack_read must be an object")
    query_name = payload.get("query_name")
    command = payload.get("command")
    verification_commands = payload.get("verification_commands")
    required_docs = payload.get("required_docs", [])
    stale_recovery = payload.get("stale_recovery_command")
    if not isinstance(query_name, str) or not query_name.strip():
        raise RtgGraphRegistryInvalid("metadata.route_pack_read.query_name must be a string")
    if not isinstance(command, str) or not command.strip():
        raise RtgGraphRegistryInvalid("metadata.route_pack_read.command must be a string")
    if not isinstance(verification_commands, list) or not all(
        isinstance(item, str) and item.strip() for item in verification_commands
    ):
        raise RtgGraphRegistryInvalid(
            "metadata.route_pack_read.verification_commands must be a string list"
        )
    if not isinstance(required_docs, list) or not all(
        isinstance(item, str) and item.strip() for item in required_docs
    ):
        raise RtgGraphRegistryInvalid(
            "metadata.route_pack_read.required_docs must be a string list"
        )
    if stale_recovery is not None and (
        not isinstance(stale_recovery, str) or not stale_recovery.strip()
    ):
        raise RtgGraphRegistryInvalid(
            "metadata.route_pack_read.stale_recovery_command must be a string"
        )
    return {
        "graph_id": graph.graph_id,
        "query_name": query_name.strip(),
        "command": command.strip(),
        "verification_commands": [str(item).strip() for item in verification_commands],
        "required_docs": [str(item).strip() for item in required_docs],
        "stale_recovery_command": stale_recovery.strip()
        if isinstance(stale_recovery, str)
        else None,
    }


def _route_pack_graph_record(payload: dict[str, Any], graph_id: str) -> dict[str, Any] | None:
    graphs = payload.get("graphs")
    if not isinstance(graphs, list):
        return None
    for graph in graphs:
        if isinstance(graph, dict) and graph.get("graph_id") == graph_id:
            return copy.deepcopy(graph)
    return None


def _route_pack_hazards(
    *,
    operation: str,
    target_graph_ids: tuple[str, ...],
    route_record: dict[str, Any],
    plan_record: dict[str, Any],
    graph_contexts: list[dict[str, Any]],
) -> list[JsonObject]:
    hazards: list[JsonObject] = []
    if operation != "read" and not target_graph_ids:
        hazards.append(
            {
                "code": "write_target_required",
                "severity": "blocker",
                "message": "writes and admin work require explicit target_graph_ids",
            }
        )
    if route_record.get("requires_confirmation") is True:
        hazards.append(
            {
                "code": "single_graph_route_requires_confirmation",
                "severity": "warning",
                "message": str(route_record.get("reason", "route requires confirmation")),
            }
        )
    if plan_record.get("requires_confirmation") is True:
        hazards.append(
            {
                "code": "federated_plan_requires_confirmation",
                "severity": "warning",
                "message": str(plan_record.get("reason", "plan requires confirmation")),
            }
        )
    candidate_hints = plan_record.get("bridge_hints", {}).get("candidate_hints")
    if isinstance(candidate_hints, dict) and candidate_hints.get("status") == "candidate_only":
        hazards.append(
            {
                "code": "candidate_only_bridge",
                "severity": "warning",
                "message": "candidate bridge hints require review and promotion before traversal",
            }
        )
    for context in graph_contexts:
        graph_id = str(context["graph_id"])
        if context.get("mcp_endpoint") is None:
            hazards.append(
                {
                    "code": "missing_mcp_endpoint",
                    "severity": "warning",
                    "message": f"{graph_id} has no descriptor-declared MCP endpoint",
                }
            )
        capabilities = context.get("capabilities")
        if isinstance(capabilities, dict) and capabilities.get("status") not in {
            "ready",
            "none_declared",
        }:
            hazards.append(
                {
                    "code": "capability_not_ready",
                    "severity": "blocker",
                    "message": f"{graph_id} federated read capabilities are not ready",
                }
            )
        preflight = context.get("preflight")
        if isinstance(preflight, dict) and preflight.get("status") == "not_ready":
            hazards.append(
                {
                    "code": "preflight_not_ready",
                    "severity": "blocker",
                    "message": f"{graph_id} failed federation preflight",
                }
            )
    return hazards


def _bridge_contexts_from_hints(
    bridge_hints: dict[str, Any],
) -> tuple[RtgFederatedBridgeContext, ...]:
    bridges = bridge_hints.get("bridges")
    if not isinstance(bridges, list):
        return ()
    contexts: list[RtgFederatedBridgeContext] = []
    for bridge in bridges:
        if not isinstance(bridge, dict):
            continue
        source = bridge.get("source")
        target = bridge.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue
        contexts.append(
            RtgFederatedBridgeContext(
                bridge_id=str(bridge.get("bridge_id", "")),
                bridge_type=str(bridge.get("bridge_type", "")),
                source_graph_id=str(source.get("graph_id", "")),
                source_local_id=str(source.get("local_uuid", "")),
                target_graph_id=str(target.get("graph_id", "")),
                target_local_id=str(target.get("local_uuid", "")),
                confidence=float(bridge.get("confidence", 0)),
            )
        )
    return tuple(contexts)


def _candidate_notices_from_hints(
    bridge_hints: dict[str, Any],
) -> tuple[RtgFederatedCandidateNotice, ...]:
    candidate_hints = bridge_hints.get("candidate_hints")
    if not isinstance(candidate_hints, dict):
        return ()
    candidates = candidate_hints.get("candidates")
    if not isinstance(candidates, list):
        return ()
    notices: list[RtgFederatedCandidateNotice] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        notices.append(
            RtgFederatedCandidateNotice(
                candidate_id=str(candidate.get("candidate_id", "")),
                status=str(candidate.get("status", "")),
                traversal_permission=bool(candidate.get("traversal_permission", False)),
                reason=str(candidate.get("rationale", "candidate requires review")),
            )
        )
    return tuple(notices)


class _RegistryCitationProjectionCatalog:
    def __init__(self, registry: RtgGraphRegistry) -> None:
        self._registry = registry

    def get_projection(self, graph_id: str) -> RtgCitationProjectionSpec | None:
        graph = self._registry.get_graph(graph_id)
        return _citation_projection_for_graph(graph)


class _RegistryCitationProjectionReader:
    def __init__(self, registry: RtgGraphRegistry) -> None:
        self._registry = registry

    def read_projection(
        self,
        projection: RtgCitationProjectionSpec,
    ) -> RtgCitationProjectionRead:
        graph = self._registry.get_graph(projection.graph_id)
        declared_projection = _citation_projection_for_graph(graph)
        if declared_projection != projection:
            raise RtgGraphRegistryInvalid(
                "citation projection changed between catalog lookup and read"
            )
        capability = _citation_projection_capability(graph, projection.query_name)
        payload = route_query_payload(
            self._registry,
            text=f"Resolve a citation in {projection.graph_id}.",
            target_graph_id=projection.graph_id,
            canned_query=projection.query_name,
            canned_query_implementation=capability.implementation,
            response_options={"format": "full"},
        )
        query = payload.get("query")
        if not isinstance(query, dict) or query.get("ok") is not True:
            raise RtgGraphRegistryInvalid("citation projection query did not execute successfully")
        result = query.get("result")
        if not isinstance(result, dict):
            raise RtgGraphRegistryInvalid("citation projection query result must be an object")
        rows = result.get("rows", result.get("returns"))
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise RtgGraphRegistryInvalid("citation projection query rows must be objects")
        snapshot_path = graph.metadata.get("snapshot_path")
        return RtgCitationProjectionRead(
            projection=projection,
            rows=tuple(copy.deepcopy(row) for row in rows),
            provenance={
                "graph": {
                    "graph_id": graph.graph_id,
                    "authority": graph.authority,
                },
                "snapshot": {
                    "declared_path": snapshot_path if isinstance(snapshot_path, str) else None,
                    "restore": copy.deepcopy(payload.get("snapshot_restore", {})),
                },
                "projection": {
                    "query_name": projection.query_name,
                    "anchor_bucket": projection.anchor_bucket,
                },
            },
        )


def _citation_projection_for_graph(
    graph: RtgGraphDescriptor,
) -> RtgCitationProjectionSpec | None:
    payload = graph.metadata.get("citation_projection")
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("metadata.citation_projection must be an object")
    unknown = sorted(set(payload) - {"query_name", "anchor_bucket"})
    if unknown:
        raise RtgGraphRegistryInvalid(
            "metadata.citation_projection has unsupported field(s): "
            f"{', '.join(map(repr, unknown))}"
        )
    query_name = payload.get("query_name")
    anchor_bucket = payload.get("anchor_bucket")
    if not isinstance(query_name, str) or not query_name.strip():
        raise RtgGraphRegistryInvalid(
            "metadata.citation_projection.query_name must be a non-empty string"
        )
    if not isinstance(anchor_bucket, str) or not anchor_bucket.strip():
        raise RtgGraphRegistryInvalid(
            "metadata.citation_projection.anchor_bucket must be a non-empty string"
        )
    normalized_query_name = query_name.strip()
    normalized_anchor_bucket = anchor_bucket.strip()
    capability = _citation_projection_capability(graph, normalized_query_name)
    canned = resolve_canned_query(
        capability.query_name,
        implementation=capability.implementation,
    )
    return_spec = canned.query_spec.get("return_spec")
    returned_anchors = return_spec.get("anchor_buckets") if isinstance(return_spec, dict) else None
    if not isinstance(returned_anchors, list) or normalized_anchor_bucket not in returned_anchors:
        raise RtgGraphRegistryInvalid(
            "metadata.citation_projection.anchor_bucket must be returned by its canned query"
        )
    return RtgCitationProjectionSpec(
        graph_id=graph.graph_id,
        query_name=normalized_query_name,
        anchor_bucket=normalized_anchor_bucket,
    )


def _citation_projection_capability(
    graph: RtgGraphDescriptor,
    query_name: str,
) -> FederatedReadCapability:
    matches = tuple(
        capability
        for capability in federated_read_capabilities_from_metadata(graph.metadata)
        if capability.query_name == query_name
    )
    if len(matches) != 1:
        raise RtgGraphRegistryInvalid(
            "metadata.citation_projection.query_name must identify exactly one declared "
            "federated read capability"
        )
    return matches[0]


def _restore_declared_snapshot(
    composition: RtgKnowledgeGraphComposition,
    graph: RtgGraphDescriptor,
) -> dict[str, Any]:
    snapshot_path = graph.metadata.get("snapshot_path")
    if snapshot_path is None:
        return {"status": "not_configured"}
    if not isinstance(snapshot_path, str) or not snapshot_path.strip():
        raise RtgGraphRegistryInvalid("metadata.snapshot_path must be a non-empty string")
    (
        snapshot,
        backfilled_time_shape_count,
        defaulted_link_kind_count,
        converted_datetime_kind_count,
    ) = _load_read_compatible_snapshot(composition, snapshot_path)
    snapshot, stripped_link_system_count = _snapshot_without_legacy_link_system(snapshot)
    restored = composition.controller.restore_from_snapshot(
        snapshot,
        RtgControllerRestoreOptions(ledger_mode="skip"),
    )
    return {
        "status": "restored",
        "snapshot_path": snapshot_path,
        "restore_status": restored.status,
        "compatibility_projection": "kernel_meta_model_harmonized",
        "legacy_link_system_stripped_count": stripped_link_system_count,
        "unsupported_schema_time_shape_stripped_count": 0,
        "unsupported_schema_identity_criteria_stripped_count": 0,
        "unsupported_schema_link_kind_stripped_count": 0,
        "legacy_datetime_kind_converted_count": converted_datetime_kind_count,
        "legacy_schema_time_shape_backfilled_count": backfilled_time_shape_count,
        "legacy_schema_link_kind_defaulted_count": defaulted_link_kind_count,
    }


def _load_read_compatible_snapshot(
    composition: RtgKnowledgeGraphComposition,
    snapshot_path: str,
) -> tuple[Any, int, int, int]:
    storage_root = Path(composition.config.storage_root).resolve()
    absolute_snapshot_path = (storage_root / snapshot_path).resolve()
    if not absolute_snapshot_path.is_relative_to(storage_root):
        raise RtgGraphRegistryInvalid(
            "metadata.snapshot_path must remain inside the graph storage root"
        )
    try:
        payload = json.loads(absolute_snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RtgControllerSnapshotFailed(str(error)) from error
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("metadata.snapshot_path must contain a JSON object")
    compatible = copy.deepcopy(payload)
    schema = compatible.get("schema")
    if not isinstance(schema, dict):
        raise RtgGraphRegistryInvalid("metadata.snapshot_path schema must be a JSON object")
    definitions = schema.get("definitions")
    if not isinstance(definitions, list):
        raise RtgGraphRegistryInvalid(
            "metadata.snapshot_path schema.definitions must be a JSON list"
        )

    backfilled_time_shape_count = 0
    defaulted_link_kind_count = 0
    converted_datetime_kind_count = 0
    for definition in definitions:
        if not isinstance(definition, dict):
            raise RtgGraphRegistryInvalid(
                "metadata.snapshot_path schema definitions must be JSON objects"
            )
        kind = definition.get("kind")
        time_shape = definition.get("time_shape")
        if kind in {"anchor", "data_object"}:
            if time_shape is None:
                definition["time_shape"] = "state_now"
                backfilled_time_shape_count += 1
            elif time_shape not in {"state_now", "state_as_of", "event"}:
                raise RtgGraphRegistryInvalid(
                    "metadata.snapshot_path contains an unrecognized schema time_shape"
                )
        elif time_shape is not None:
            if time_shape not in {"state_now", "state_as_of", "event"}:
                raise RtgGraphRegistryInvalid(
                    "metadata.snapshot_path contains an unrecognized schema time_shape"
                )
        identity_criteria = definition.get("identity_criteria")
        if identity_criteria is not None:
            if not isinstance(identity_criteria, list):
                raise RtgGraphRegistryInvalid(
                    "metadata.snapshot_path schema identity_criteria must be a JSON list"
                )
        definition_payload = definition.get("payload")
        if not isinstance(definition_payload, dict):
            continue
        properties = definition_payload.get("properties")
        if isinstance(properties, dict):
            converted_datetime_kind_count += sum(
                _convert_legacy_datetime_kind(field) for field in properties.values()
            )
        link_kind = definition_payload.get("link_kind")
        if kind == "link" and link_kind is None:
            definition_payload["link_kind"] = "semantic"
            defaulted_link_kind_count += 1
        elif link_kind is not None:
            if link_kind not in {
                "semantic",
                "structural",
                "governance",
                "provenance",
                "versioning",
                "junction",
            }:
                raise RtgGraphRegistryInvalid(
                    "metadata.snapshot_path contains an unrecognized schema link_kind"
                )
    return (
        decode_system_snapshot(compatible),
        backfilled_time_shape_count,
        defaulted_link_kind_count,
        converted_datetime_kind_count,
    )


def _convert_legacy_datetime_kind(field: Any) -> int:
    if not isinstance(field, dict):
        return 0
    converted_count = 0
    value_kinds = field.get("value_kinds")
    if isinstance(value_kinds, list) and "datetime" in value_kinds:
        field["value_kinds"] = ["string" if kind == "datetime" else kind for kind in value_kinds]
        existing_format = field.get("format")
        if existing_format not in {None, "date_time"}:
            raise RtgGraphRegistryInvalid(
                "metadata.snapshot_path datetime field has an incompatible format"
            )
        field["format"] = "date_time"
        converted_count += 1
    properties = field.get("properties")
    if isinstance(properties, dict):
        converted_count += sum(
            _convert_legacy_datetime_kind(nested) for nested in properties.values()
        )
    items = field.get("items")
    if items is not None:
        converted_count += _convert_legacy_datetime_kind(items)
    return converted_count


def _snapshot_without_legacy_link_system(snapshot: Any) -> tuple[Any, int]:
    links = tuple(snapshot.graph.links)
    cleaned_links: list[dict[str, Any]] = []
    stripped_count = 0
    for link in links:
        if not isinstance(link, dict) or "system" not in link:
            cleaned_links.append(copy.deepcopy(link))
            continue
        if link["system"] != {"live": True}:
            raise RtgGraphRegistryInvalid(
                "metadata.snapshot_path contains link system metadata that cannot be stripped "
                "losslessly; repair the snapshot before routed reads."
            )
        cleaned = copy.deepcopy(link)
        cleaned.pop("system", None)
        cleaned_links.append(cleaned)
        stripped_count += 1
    if stripped_count == 0:
        return snapshot, 0
    return replace(
        snapshot, graph=replace(snapshot.graph, links=tuple(cleaned_links))
    ), stripped_count


def _descriptor_from_payload(payload: object) -> RtgGraphDescriptor:
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("graph descriptor must be a JSON object")
    endpoint_payload = payload.get("mcp_endpoint")
    endpoint = None
    if endpoint_payload is not None:
        if not isinstance(endpoint_payload, dict):
            raise RtgGraphRegistryInvalid("mcp_endpoint must be a JSON object")
        endpoint = RtgGraphMcpEndpoint(
            transport=_required_str(endpoint_payload, "transport"),
            host=_optional_str(endpoint_payload, "host"),
            port=_optional_int(endpoint_payload, "port"),
            path=_optional_str(endpoint_payload, "path") or "/mcp",
            server_name=_optional_str(endpoint_payload, "server_name"),
        )
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise RtgGraphRegistryInvalid("metadata must be a JSON object")
    return RtgGraphDescriptor(
        graph_id=_required_str(payload, "graph_id"),
        title=_required_str(payload, "title"),
        storage_root=_required_str(payload, "storage_root"),
        sql_database_path=_required_str(payload, "sql_database_path"),
        authority=_required_str(payload, "authority"),
        write_policy=_required_str(payload, "write_policy"),
        domains=tuple(_required_str_list(payload, "domains")),
        tags=tuple(_optional_str_list(payload, "tags")),
        mcp_endpoint=endpoint,
        metadata=metadata,
    )


def _bridge_draft_from_payload(payload: object) -> RtgGraphBridgeDraft:
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("bridge descriptor must be a JSON object")
    provenance = payload.get("provenance")
    if not isinstance(provenance, list):
        raise RtgGraphRegistryInvalid("bridge provenance must be a list")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise RtgGraphRegistryInvalid("bridge metadata must be a JSON object")
    return RtgGraphBridgeDraft(
        bridge_type=_required_str(payload, "bridge_type"),
        source=_bridge_reference_from_payload(payload.get("source"), "source"),
        target=_bridge_reference_from_payload(payload.get("target"), "target"),
        confidence=_required_float(payload, "confidence"),
        asserted_at=_required_str(payload, "asserted_at"),
        asserted_by=_required_str(payload, "asserted_by"),
        provenance=tuple(_bridge_reference_from_payload(item, "provenance") for item in provenance),
        metadata=metadata,
    )


def _bridge_candidate_from_payload(payload: object) -> RtgGraphBridgeCandidateDraft:
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("bridge candidate must be a JSON object")
    evidence = payload.get("evidence")
    if not isinstance(evidence, list):
        raise RtgGraphRegistryInvalid("bridge candidate evidence must be a list")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise RtgGraphRegistryInvalid("bridge candidate metadata must be a JSON object")
    return RtgGraphBridgeCandidateDraft(
        bridge_type=_required_str(payload, "bridge_type"),
        source=_bridge_reference_from_payload(payload.get("source"), "source"),
        target=_bridge_reference_from_payload(payload.get("target"), "target"),
        confidence=_required_float(payload, "confidence"),
        proposed_at=_required_str(payload, "proposed_at"),
        proposed_by=_required_str(payload, "proposed_by"),
        evidence=tuple(_bridge_reference_from_payload(item, "evidence") for item in evidence),
        rationale=_required_str(payload, "rationale"),
        metadata=metadata,
    )


def _bridge_reference_from_payload(payload: object, name: str) -> RtgGraphLocalReference:
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid(f"{name} must be a JSON object")
    local_uuid = payload.get("local_uuid")
    if not isinstance(local_uuid, str):
        raise RtgGraphRegistryInvalid(f"{name}.local_uuid must be a string")
    try:
        parsed_uuid = UUID(local_uuid)
    except ValueError as error:
        raise RtgGraphRegistryInvalid(f"{name}.local_uuid must be a UUID") from error
    return RtgGraphLocalReference(
        graph_id=_required_str(payload, "graph_id"),
        local_uuid=parsed_uuid,
    )


def _load_bridge_catalog_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RtgGraphRegistryInvalid(f"bridge catalog does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("bridge catalog root must be a JSON object")
    bridges = payload.get("bridges")
    if not isinstance(bridges, list):
        raise RtgGraphRegistryInvalid("bridge catalog must contain a bridges list")
    candidates = payload.get("candidates", [])
    if not isinstance(candidates, list):
        raise RtgGraphRegistryInvalid("bridge catalog candidates must be a list")
    return {"bridges": bridges, "candidates": candidates}


def _write_bridge_catalog_payload(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _bridge_candidate_records(
    path: Path,
) -> list[tuple[int, RtgGraphBridgeCandidate, dict[str, Any]]]:
    return _bridge_candidate_records_from_payload(_load_bridge_catalog_payload(path))


def _bridge_candidate_records_from_payload(
    catalog: dict[str, Any],
) -> list[tuple[int, RtgGraphBridgeCandidate, dict[str, Any]]]:
    records: list[tuple[int, RtgGraphBridgeCandidate, dict[str, Any]]] = []
    candidates = catalog["candidates"]
    for index, payload in enumerate(candidates):
        if not isinstance(payload, dict):
            raise RtgGraphRegistryInvalid("bridge candidate must be a JSON object")
        records.append((index, _bridge_candidate_record_from_payload(payload), payload))
    return records


def _find_bridge_candidate_record(
    path: Path,
    candidate_id: str,
) -> tuple[int, RtgGraphBridgeCandidate, dict[str, Any]]:
    return _find_bridge_candidate_record_in_payload(
        _load_bridge_catalog_payload(path),
        candidate_id,
    )


def _find_bridge_candidate_record_in_payload(
    catalog: dict[str, Any],
    candidate_id: str,
) -> tuple[int, RtgGraphBridgeCandidate, dict[str, Any]]:
    for record in _bridge_candidate_records_from_payload(catalog):
        if record[1].candidate_id == candidate_id:
            return record
    raise RtgGraphRegistryInvalid(f"bridge candidate not found: {candidate_id}")


def _bridge_candidate_record_from_payload(payload: dict[str, Any]) -> RtgGraphBridgeCandidate:
    draft = _bridge_candidate_from_payload(payload)
    store = InMemoryRtgGraphBridge.empty()
    candidate = store.put_candidate(draft)
    status = _bridge_candidate_status_from_payload(payload)
    if status == "candidate_only":
        return candidate
    if status == "promoted":
        return _candidate_with_status(
            candidate,
            status="promoted",
            promoted_bridge_id=_required_str(payload, "promoted_bridge_id"),
        )
    return _candidate_with_status(
        candidate,
        status="rejected",
        rejected_at=_required_str(payload, "rejected_at"),
        rejected_by=_required_str(payload, "rejected_by"),
        rejection_reason=_required_str(payload, "rejection_reason"),
    )


def _candidate_with_status(
    candidate: RtgGraphBridgeCandidate,
    *,
    status: str,
    promoted_bridge_id: str | None = None,
    rejected_at: str | None = None,
    rejected_by: str | None = None,
    rejection_reason: str | None = None,
) -> RtgGraphBridgeCandidate:
    return RtgGraphBridgeCandidate(
        candidate_id=candidate.candidate_id,
        bridge_type=candidate.bridge_type,
        source=candidate.source,
        target=candidate.target,
        confidence=candidate.confidence,
        proposed_at=candidate.proposed_at,
        proposed_by=candidate.proposed_by,
        evidence=candidate.evidence,
        rationale=candidate.rationale,
        metadata=candidate.metadata,
        status=status,
        promoted_bridge_id=promoted_bridge_id,
        rejected_at=rejected_at,
        rejected_by=rejected_by,
        rejection_reason=rejection_reason,
    )


def _bridge_candidate_status_from_payload(payload: object) -> str:
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("bridge candidate must be a JSON object")
    value = payload.get("status", "candidate_only")
    if not isinstance(value, str) or value not in BRIDGE_CANDIDATE_STATUSES:
        raise RtgGraphRegistryInvalid(
            "bridge candidate status must be candidate_only, promoted, or rejected"
        )
    return value


def _normalize_candidate_status_filter(status: str) -> str:
    if status == "all":
        return status
    if status not in BRIDGE_CANDIDATE_STATUSES:
        raise RtgGraphRegistryInvalid(
            "bridge candidate status filter must be all, candidate_only, promoted, or rejected"
        )
    return status


def _upsert_bridge_catalog_payload(
    bridges: list[Any],
    bridge: Any,
) -> list[Any]:
    next_bridge = _bridge_assertion_catalog_payload(bridge)
    updated: list[Any] = []
    replaced = False
    for bridge_payload in bridges:
        bridge_id = _bridge_id_from_payload(bridge_payload)
        if bridge_id == bridge.bridge_id:
            updated.append(next_bridge)
            replaced = True
        else:
            updated.append(bridge_payload)
    if not replaced:
        updated.append(next_bridge)
    return updated


def _bridge_id_from_payload(payload: object) -> str:
    store = InMemoryRtgGraphBridge.empty()
    return store.put_bridge(_bridge_draft_from_payload(payload)).bridge_id


def _bridge_hints_payload(
    plan: Any,
    bridge_store: RtgGraphBridge | None,
) -> dict[str, Any]:
    if bridge_store is None:
        return {
            "status": "not_configured",
            "matching_bridge_count": 0,
            "bridges": [],
            "follow_up_checklist": [],
            "candidate_hints": {
                "status": "not_configured",
                "matching_candidate_count": 0,
                "candidates": [],
                "review_checklist": [],
                "traversal_permission": False,
            },
            "join_execution": "not_performed",
        }
    step_graph_ids = {step.graph_id for step in plan.steps}
    matching = [
        bridge
        for bridge in bridge_store.list_bridges(status="active").bridges
        if bridge.source.graph_id in step_graph_ids and bridge.target.graph_id in step_graph_ids
    ]
    candidates = []
    if not matching:
        candidates = [
            candidate
            for candidate in bridge_store.list_candidates(status="candidate_only").candidates
            if candidate.source.graph_id in step_graph_ids
            and candidate.target.graph_id in step_graph_ids
        ]
    return {
        "status": "available",
        "matching_bridge_count": len(matching),
        "bridges": [_bridge_assertion_payload(bridge) for bridge in matching],
        "follow_up_checklist": [_bridge_follow_up_payload(bridge) for bridge in matching],
        "candidate_hints": _candidate_hints_payload(
            candidates, confirmed_bridge_count=len(matching)
        ),
        "join_execution": "not_performed",
    }


def _bridge_assertion_payload(bridge: Any) -> dict[str, Any]:
    return {
        "bridge_id": bridge.bridge_id,
        "bridge_type": bridge.bridge_type,
        "source": _bridge_reference_payload(bridge.source),
        "target": _bridge_reference_payload(bridge.target),
        "confidence": bridge.confidence,
        "asserted_at": bridge.asserted_at,
        "asserted_by": bridge.asserted_by,
        "provenance": [_bridge_reference_payload(item) for item in bridge.provenance],
        "metadata": bridge.metadata,
        "status": bridge.status,
        "revoked_at": bridge.revoked_at,
        "revoked_by": bridge.revoked_by,
        "revocation_reason": bridge.revocation_reason,
    }


def _bridge_assertion_catalog_payload(bridge: Any) -> dict[str, Any]:
    return {
        "bridge_type": bridge.bridge_type,
        "source": _bridge_reference_payload(bridge.source),
        "target": _bridge_reference_payload(bridge.target),
        "confidence": bridge.confidence,
        "asserted_at": bridge.asserted_at,
        "asserted_by": bridge.asserted_by,
        "provenance": [_bridge_reference_payload(item) for item in bridge.provenance],
        "metadata": bridge.metadata,
    }


def _bridge_follow_up_payload(bridge: Any) -> dict[str, Any]:
    return {
        "bridge_id": bridge.bridge_id,
        "bridge_type": bridge.bridge_type,
        "status": "planned_not_executed",
        "items": [
            {
                "action": "graph_local_read",
                "graph_id": bridge.source.graph_id,
                "local_uuid": str(bridge.source.local_uuid),
                "purpose": "read the source endpoint inside its owning graph",
                "executed": False,
            },
            {
                "action": "graph_local_read",
                "graph_id": bridge.target.graph_id,
                "local_uuid": str(bridge.target.local_uuid),
                "purpose": "read the target endpoint inside its owning graph",
                "executed": False,
            },
            {
                "action": "synthesize_outside_graph",
                "graph_id": None,
                "local_uuid": None,
                "purpose": (
                    "compare the graph-local results using the bridge assertion; do not write a "
                    "cross-graph join result"
                ),
                "executed": False,
            },
        ],
    }


def _candidate_hints_payload(
    candidates: list[Any],
    *,
    confirmed_bridge_count: int,
) -> dict[str, Any]:
    if confirmed_bridge_count:
        return {
            "status": "suppressed_by_confirmed_bridge",
            "matching_candidate_count": 0,
            "candidates": [],
            "review_checklist": [],
            "traversal_permission": False,
        }
    if not candidates:
        return {
            "status": "none",
            "matching_candidate_count": 0,
            "candidates": [],
            "review_checklist": [],
            "traversal_permission": False,
        }
    return {
        "status": "candidate_only",
        "matching_candidate_count": len(candidates),
        "candidates": [_bridge_candidate_payload(candidate) for candidate in candidates],
        "review_checklist": [_candidate_review_payload(candidate) for candidate in candidates],
        "traversal_permission": False,
    }


def _bridge_candidate_payload(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "bridge_type": candidate.bridge_type,
        "source": _bridge_reference_payload(candidate.source),
        "target": _bridge_reference_payload(candidate.target),
        "confidence": candidate.confidence,
        "proposed_at": candidate.proposed_at,
        "proposed_by": candidate.proposed_by,
        "evidence": [_bridge_reference_payload(item) for item in candidate.evidence],
        "rationale": candidate.rationale,
        "metadata": candidate.metadata,
        "status": candidate.status,
        "promoted_bridge_id": candidate.promoted_bridge_id,
        "rejected_at": candidate.rejected_at,
        "rejected_by": candidate.rejected_by,
        "rejection_reason": candidate.rejection_reason,
        "traversal_permission": False,
    }


def _candidate_review_payload(candidate: Any) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "status": "candidate_only",
        "items": [
            {
                "action": "review_candidate_evidence",
                "graph_id": None,
                "local_uuid": None,
                "purpose": "inspect the candidate evidence before treating endpoints as related",
                "executed": False,
            },
            {
                "action": "graph_local_read",
                "graph_id": candidate.source.graph_id,
                "local_uuid": str(candidate.source.local_uuid),
                "purpose": "read the source endpoint only for candidate review",
                "executed": False,
            },
            {
                "action": "graph_local_read",
                "graph_id": candidate.target.graph_id,
                "local_uuid": str(candidate.target.local_uuid),
                "purpose": "read the target endpoint only for candidate review",
                "executed": False,
            },
            {
                "action": "promote_or_reject_candidate",
                "graph_id": None,
                "local_uuid": None,
                "purpose": "promote to a bridge before traversal, or reject the candidate",
                "executed": False,
            },
        ],
    }


def _bridge_reference_payload(reference: RtgGraphLocalReference) -> dict[str, str]:
    return {"graph_id": reference.graph_id, "local_uuid": str(reference.local_uuid)}


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise RtgGraphRegistryInvalid(f"{key} must be a string")
    return value


def _required_float(payload: dict[str, object], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RtgGraphRegistryInvalid(f"{key} must be a number")
    return float(value)


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RtgGraphRegistryInvalid(f"{key} must be a string")
    return value


def _optional_int(payload: dict[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise RtgGraphRegistryInvalid(f"{key} must be an integer")
    return value


def _required_str_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RtgGraphRegistryInvalid(f"{key} must be a list of strings")
    return value


def _optional_str_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RtgGraphRegistryInvalid(f"{key} must be a list of strings")
    return value


def _graph_payload(graph: RtgGraphDescriptor) -> dict[str, Any]:
    return asdict(graph)


def _require_http_endpoint(graph: RtgGraphDescriptor) -> RtgGraphMcpEndpoint:
    endpoint = graph.mcp_endpoint
    if endpoint is None or endpoint.transport != "http":
        raise RtgGraphRegistryInvalid(f"graph {graph.graph_id} does not declare an HTTP endpoint")
    return endpoint
