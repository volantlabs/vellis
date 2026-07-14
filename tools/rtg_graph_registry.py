from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.rtg_federation.registry_io import (
    DEFAULT_REGISTRY_PATH,
    absolute_graph_path,
    bridge_candidate_payload,
    bridge_candidates_payload,
    bridge_traversal_payload,
    citation_resolution_payload,
    default_bridge_path_for_registry,
    federated_answer_payload,
    federated_capabilities_payload,
    federated_preflight_payload,
    init_graph_payload,
    list_graphs_payload,
    load_optional_bridge_store,
    load_registry,
    mcp_info_payload,
    promote_bridge_candidate_payload,
    reject_bridge_candidate_payload,
    route_pack_gate_payload,
    route_pack_preview_payload,
    route_payload,
)
from apps.rtg_knowledge_graph.config import RtgKnowledgeGraphConfig
from apps.rtg_knowledge_graph.mcp_server import run_mcp_server
from components.rtg.graph_registry import (
    RtgGraphFederatedIntent,
    RtgGraphIntent,
    RtgGraphRegistryInvalid,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rtg_graph_registry")
    parser.add_argument(
        "--registry",
        default=DEFAULT_REGISTRY_PATH,
        type=Path,
        help="Path to an RTG monograph registry JSON file.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List registered graphs.")
    list_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    capabilities_parser = subparsers.add_parser(
        "federated-capabilities",
        help="List descriptor-declared federated read capabilities.",
    )
    capabilities_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    preflight_parser = subparsers.add_parser(
        "federated-preflight",
        help="Check runtime readiness for descriptor-declared federated reads.",
    )
    preflight_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    preflight_parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when any graph with declared federated reads is not ready.",
    )
    capabilities_parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero if any declared federated read capability is not ready.",
    )

    capability_template_parser = subparsers.add_parser(
        "federated-capability-template",
        help="Print a descriptor snippet and module skeleton for a new federated read capability.",
    )
    capability_template_parser.add_argument("query_name", help="New canned query name.")
    capability_template_parser.add_argument(
        "--module",
        default=None,
        help="Python module path. Defaults to apps.rtg_federation.queries.<query_name>.",
    )
    capability_template_parser.add_argument(
        "--description",
        default=None,
        help="Capability description to include in the descriptor snippet.",
    )
    capability_template_parser.add_argument(
        "--term",
        action="append",
        default=[],
        help="Matching term for intent routing. Can be supplied multiple times.",
    )
    capability_template_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Matching domain for intent routing. Can be supplied multiple times.",
    )
    capability_template_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Matching tag for intent routing. Can be supplied multiple times.",
    )
    capability_template_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    route_parser = subparsers.add_parser("route", help="Compile an intent into graph candidates.")
    route_parser.add_argument("text", help="Intent text to route.")
    route_parser.add_argument(
        "--operation",
        choices=("read", "write", "admin"),
        default="read",
        help="Routing operation class.",
    )
    route_parser.add_argument("--target-graph-id", default=None, help="Explicit graph target.")
    route_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Explicit domain hint. Can be supplied multiple times.",
    )
    route_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Explicit tag hint. Can be supplied multiple times.",
    )
    route_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    route_pack_parser = subparsers.add_parser(
        "route-pack-preview",
        help="Assemble an advisory route pack for one intent.",
    )
    route_pack_parser.add_argument("text", help="Intent text to package.")
    route_pack_parser.add_argument(
        "--operation",
        choices=("read", "write", "admin"),
        default="read",
        help="Routing operation class.",
    )
    route_pack_parser.add_argument(
        "--target-graph-id",
        action="append",
        default=[],
        help="Explicit graph target. Can be supplied multiple times.",
    )
    route_pack_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Explicit domain hint. Can be supplied multiple times.",
    )
    route_pack_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Explicit tag hint. Can be supplied multiple times.",
    )
    route_pack_parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Optional bridge assertion catalog JSON file.",
    )
    route_pack_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    route_pack_gate_parser = subparsers.add_parser(
        "route-pack-gate",
        help="Gate one route pack into invoke, clarify, or blocked.",
    )
    route_pack_gate_parser.add_argument("text", help="Intent text to gate.")
    route_pack_gate_parser.add_argument(
        "--operation",
        choices=("read", "write", "admin"),
        default="read",
        help="Routing operation class.",
    )
    route_pack_gate_parser.add_argument(
        "--target-graph-id",
        action="append",
        default=[],
        help="Explicit graph target. Can be supplied multiple times.",
    )
    route_pack_gate_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Explicit domain hint. Can be supplied multiple times.",
    )
    route_pack_gate_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Explicit tag hint. Can be supplied multiple times.",
    )
    route_pack_gate_parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Optional bridge assertion catalog JSON file.",
    )
    route_pack_gate_parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero unless the gate decision is invoke.",
    )
    route_pack_gate_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    plan_parser = subparsers.add_parser(
        "federated-plan",
        help="Compile an intent into graph-local plan steps across matching graphs.",
    )
    plan_parser.add_argument("text", help="Intent text to plan.")
    plan_parser.add_argument(
        "--operation",
        choices=("read", "write", "admin"),
        default="read",
        help="Planning operation class.",
    )
    plan_parser.add_argument(
        "--target-graph-id",
        action="append",
        default=[],
        help="Explicit graph target. Can be supplied multiple times.",
    )
    plan_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Explicit domain hint. Can be supplied multiple times.",
    )
    plan_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Explicit tag hint. Can be supplied multiple times.",
    )
    plan_parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Optional bridge assertion catalog JSON file.",
    )
    plan_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    answer_parser = subparsers.add_parser(
        "federated-answer",
        help="Execute supported graph-local reads and return a structured federated synthesis.",
    )
    answer_parser.add_argument("text", help="Intent text to answer.")
    answer_parser.add_argument(
        "--operation",
        choices=("read", "write", "admin"),
        default="read",
        help="Planning operation class.",
    )
    answer_parser.add_argument(
        "--target-graph-id",
        action="append",
        default=[],
        help="Explicit graph target. Can be supplied multiple times.",
    )
    answer_parser.add_argument(
        "--domain",
        action="append",
        default=[],
        help="Explicit domain hint. Can be supplied multiple times.",
    )
    answer_parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Explicit tag hint. Can be supplied multiple times.",
    )
    answer_parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Optional bridge assertion catalog JSON file.",
    )
    answer_parser.add_argument(
        "--canned-query",
        action="append",
        default=[],
        help="Graph-local canned query override in graph_id=query_name form.",
    )
    answer_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    resolve_citation_parser = subparsers.add_parser(
        "resolve-citation",
        help="Resolve one graph-qualified citation through a descriptor-declared projection.",
    )
    resolve_citation_parser.add_argument("graph_id", help="Owning graph id.")
    resolve_citation_parser.add_argument("local_uuid", help="Graph-local object UUID.")
    resolve_citation_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    bridge_traversal_parser = subparsers.add_parser(
        "bridge-traverse",
        help="Resolve both endpoints of one explicit active confirmed bridge.",
    )
    bridge_traversal_parser.add_argument("bridge_id", help="Confirmed bridge identifier.")
    bridge_traversal_parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Optional bridge assertion catalog JSON file.",
    )
    bridge_traversal_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    route_query_parser = subparsers.add_parser(
        "route-query",
        help="Run a read-only routed query. Currently intended for canned query experiments.",
    )
    route_query_parser.add_argument("text", help="Intent text to route.")
    route_query_parser.add_argument(
        "--canned-query",
        required=True,
        help="Named canned query to execute.",
    )
    route_query_parser.add_argument(
        "--target-graph-id", default=None, help="Explicit graph target."
    )
    route_query_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    bridge_candidates_parser = subparsers.add_parser(
        "bridge-candidates",
        help="List, inspect, promote, or reject bridge candidates in the bridge catalog.",
    )
    bridge_candidates_parser.add_argument(
        "--bridges",
        type=Path,
        default=None,
        help="Optional bridge assertion catalog JSON file.",
    )
    bridge_candidate_subparsers = bridge_candidates_parser.add_subparsers(
        dest="bridge_candidate_command",
        required=True,
    )
    bridge_candidate_list_parser = bridge_candidate_subparsers.add_parser(
        "list",
        help="List bridge candidates.",
    )
    bridge_candidate_list_parser.add_argument(
        "--status",
        choices=("candidate_only", "promoted", "rejected", "all"),
        default="candidate_only",
        help="Candidate status filter.",
    )
    bridge_candidate_list_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    bridge_candidate_inspect_parser = bridge_candidate_subparsers.add_parser(
        "inspect",
        help="Inspect one bridge candidate.",
    )
    bridge_candidate_inspect_parser.add_argument("candidate_id", help="Candidate id.")
    bridge_candidate_inspect_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    bridge_candidate_promote_parser = bridge_candidate_subparsers.add_parser(
        "promote",
        help="Promote one candidate into a confirmed bridge assertion.",
    )
    bridge_candidate_promote_parser.add_argument("candidate_id", help="Candidate id.")
    bridge_candidate_promote_parser.add_argument(
        "--asserted-at",
        required=True,
        help="Assertion timestamp to record on the promoted bridge.",
    )
    bridge_candidate_promote_parser.add_argument(
        "--asserted-by",
        required=True,
        help="Actor to record on the promoted bridge.",
    )
    bridge_candidate_promote_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    bridge_candidate_reject_parser = bridge_candidate_subparsers.add_parser(
        "reject",
        help="Reject one bridge candidate.",
    )
    bridge_candidate_reject_parser.add_argument("candidate_id", help="Candidate id.")
    bridge_candidate_reject_parser.add_argument(
        "--rejected-at",
        required=True,
        help="Rejection timestamp to record on the candidate.",
    )
    bridge_candidate_reject_parser.add_argument(
        "--rejected-by",
        required=True,
        help="Actor to record on the rejected candidate.",
    )
    bridge_candidate_reject_parser.add_argument(
        "--reason",
        required=True,
        help="Reason for rejection.",
    )
    bridge_candidate_reject_parser.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )

    init_parser = subparsers.add_parser(
        "init", help="Create and smoke-check one registered graph root."
    )
    init_parser.add_argument("graph_id", help="Registered graph id.")
    init_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    mcp_parser = subparsers.add_parser(
        "mcp-info", help="Print launch and client config for one graph."
    )
    mcp_parser.add_argument("graph_id", help="Registered graph id.")
    mcp_parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")

    serve_parser = subparsers.add_parser(
        "serve-http", help="Run one registered graph as a localhost HTTP MCP server."
    )
    serve_parser.add_argument("graph_id", help="Registered graph id.")

    args = parser.parse_args(argv)

    if args.command == "federated-capability-template":
        payload = _federated_capability_template_payload(
            query_name=args.query_name,
            module=args.module,
            description=args.description,
            terms=tuple(args.term),
            domains=tuple(args.domain),
            tags=tuple(args.tag),
        )
        if args.json:
            _print_json(payload)
        else:
            print("descriptor=")
            print(json.dumps(payload["descriptor"], indent=2, sort_keys=True))
            print(f"module_path={payload['module_path']}")
            print("module_template=")
            print(payload["module_template"])
        return 0

    registry = load_registry(args.registry)

    if args.command == "list":
        payload = list_graphs_payload(registry)
        if args.json:
            _print_json(payload)
        else:
            for graph in payload["graphs"]:
                print(
                    f"{graph['graph_id']}: {graph['title']} [domains={', '.join(graph['domains'])}]"
                )
        return 0

    if args.command == "federated-capabilities":
        payload = federated_capabilities_payload(registry)
        check: dict[str, object] | None = None
        if args.check:
            check = _federated_capabilities_check(payload)
            payload["check"] = check
        if args.json:
            _print_json(payload)
        else:
            print(
                f"graph_count={payload['graph_count']} "
                f"ready_capability_count={payload['ready_capability_count']}"
            )
            for graph in payload["graphs"]:
                print(
                    f"- {graph['graph_id']} "
                    f"status={graph['status']} "
                    f"ready={graph['ready_capability_count']}/{graph['capability_count']}"
                )
                for capability in graph["capabilities"]:
                    implementation = (
                        capability["implementation"]
                        or capability.get("resolved_implementation")
                        or "builtin"
                    )
                    print(
                        f"  - {capability['query_name']} "
                        f"status={capability['status']} "
                        f"implementation={implementation}"
                    )
            if check is not None:
                print(f"check={check['status']}")
                failed_graph_ids = check["failed_graph_ids"]
                if isinstance(failed_graph_ids, list):
                    for failed_graph_id in failed_graph_ids:
                        print(f"failed_graph={failed_graph_id}")
        return 0 if check is None or check["status"] == "passed" else 1

    if args.command == "federated-preflight":
        payload = federated_preflight_payload(registry)
        if args.json:
            _print_json(payload)
        else:
            print(
                f"status={payload['status']} graph_count={payload['graph_count']} "
                f"ready={payload['ready_graph_count']} "
                f"skipped={payload['skipped_graph_count']} "
                f"not_ready={payload['not_ready_graph_count']}"
            )
            for graph in payload["graphs"]:
                print(
                    f"- {graph['graph_id']} status={graph['status']} "
                    f"capabilities={graph['capabilities']['status']} "
                    f"citation_projection={graph['citation_projection']['status']} "
                    f"snapshot={graph['snapshot']['status']} "
                    f"validation={graph['validation']['status']}"
                )
                for reason in graph["reasons"]:
                    print(f"  reason={reason}")
        return 0 if not args.check or payload["status"] == "passed" else 1

    if args.command == "route":
        route = registry.compile_intent(
            RtgGraphIntent(
                operation=args.operation,
                text=args.text,
                target_graph_id=args.target_graph_id,
                domain_hints=tuple(args.domain),
                tag_hints=tuple(args.tag),
            )
        )
        payload = route_payload(route)
        if args.json:
            _print_json(payload)
        else:
            selected = payload["selected_graph_id"] or "(none)"
            print(
                f"selected={selected} "
                f"requires_confirmation={payload['requires_confirmation']} "
                f"reason={payload['reason']}"
            )
            for candidate in payload["candidates"]:
                print(
                    f"- {candidate['graph_id']} "
                    f"score={candidate['score']:.2f} "
                    f"reasons={', '.join(candidate['reasons'])}"
                )
        return 0

    if args.command == "route-pack-preview":
        bridge_path = args.bridges or default_bridge_path_for_registry(args.registry)
        payload = route_pack_preview_payload(
            registry,
            text=args.text,
            operation=args.operation,
            target_graph_ids=tuple(args.target_graph_id),
            domain_hints=tuple(args.domain),
            tag_hints=tuple(args.tag),
            bridge_store=load_optional_bridge_store(bridge_path),
        )
        if args.json:
            _print_json(payload)
        else:
            print(f"status={payload['status']}")
            print(f"skill={payload['selected_skill']['name']}")
            print(f"hazard_count={len(payload['hazards'])}")
            route = payload["single_graph_route"]
            print(f"selected_graph_id={route['selected_graph_id'] or '(none)'}")
            print(f"requires_confirmation={route['requires_confirmation']}")
            print(f"required_doc_count={len(payload['required_docs'])}")
            for context in payload["graph_contexts"]:
                print(
                    f"- {context['graph_id']} "
                    f"capabilities={context['capabilities']['status']} "
                    f"preflight={context['preflight']['status']}"
                )
                direct_read = context.get("route_pack_read")
                if isinstance(direct_read, dict):
                    print(f"  direct_read_command={direct_read['command']}")
            for hazard in payload["hazards"]:
                print(
                    f"hazard={hazard['code']} "
                    f"severity={hazard['severity']} "
                    f"message={hazard['message']}"
                )
        return 0

    if args.command == "route-pack-gate":
        bridge_path = args.bridges or default_bridge_path_for_registry(args.registry)
        payload = route_pack_gate_payload(
            registry,
            text=args.text,
            operation=args.operation,
            target_graph_ids=tuple(args.target_graph_id),
            domain_hints=tuple(args.domain),
            tag_hints=tuple(args.tag),
            bridge_store=load_optional_bridge_store(bridge_path),
        )
        if args.json:
            _print_json(payload)
        else:
            print(f"decision={payload['decision']}")
            print(f"reason={payload['reason']}")
            print(f"skill={payload['selected_skill']['name']}")
            targets = payload["graph_targets"]
            print(f"selected_graph_id={targets['selected_graph_id'] or '(none)'}")
            print(f"graph_context_ids={', '.join(targets['graph_context_ids']) or '(none)'}")
            print(f"blocking_hazards={', '.join(payload['blocking_hazard_codes']) or '(none)'}")
            print(
                "clarification_hazards="
                f"{', '.join(payload['clarification_hazard_codes']) or '(none)'}"
            )
            for action in payload["next_actions"]:
                details = " ".join(
                    f"{key}={value}"
                    for key, value in action.items()
                    if key != "action" and not isinstance(value, list)
                )
                print(f"next_action={action['action']}" + (f" {details}" if details else ""))
                for command in action.get("commands", []):
                    print(f"  command={command}")
            stale_recovery = payload["freshness_and_evidence"].get("stale_recovery_command")
            if stale_recovery:
                print(f"stale_recovery_command={stale_recovery}")
        return 0 if not args.check or payload["decision"] == "invoke" else 1

    if args.command == "federated-plan":
        from apps.rtg_federation.registry_io import federated_plan_payload

        bridge_path = args.bridges or default_bridge_path_for_registry(args.registry)
        plan = registry.compile_federated_intent(
            RtgGraphFederatedIntent(
                operation=args.operation,
                text=args.text,
                target_graph_ids=tuple(args.target_graph_id),
                domain_hints=tuple(args.domain),
                tag_hints=tuple(args.tag),
            )
        )
        payload = federated_plan_payload(plan, load_optional_bridge_store(bridge_path))
        if args.json:
            _print_json(payload)
        else:
            print(
                f"executable={payload['executable']} "
                f"requires_confirmation={payload['requires_confirmation']} "
                f"reason={payload['reason']}"
            )
            for step in payload["steps"]:
                print(
                    f"- {step['graph_id']} "
                    f"score={step['score']:.2f} "
                    f"reasons={', '.join(step['reasons'])}"
                )
            bridge_hints = payload["bridge_hints"]
            print(
                f"bridge_hints={bridge_hints['status']} "
                f"matching_bridge_count={bridge_hints['matching_bridge_count']}"
            )
            print(
                "candidate_hints="
                f"{bridge_hints['candidate_hints']['status']} "
                "matching_candidate_count="
                f"{bridge_hints['candidate_hints']['matching_candidate_count']}"
            )
            print(f"follow_up_count={len(bridge_hints['follow_up_checklist'])}")
        return 0

    if args.command == "federated-answer":
        bridge_path = args.bridges or default_bridge_path_for_registry(args.registry)
        payload = federated_answer_payload(
            registry,
            text=args.text,
            operation=args.operation,
            target_graph_ids=tuple(args.target_graph_id),
            domain_hints=tuple(args.domain),
            tag_hints=tuple(args.tag),
            bridge_store=load_optional_bridge_store(bridge_path),
            canned_queries=_parse_canned_query_overrides(args.canned_query),
        )
        if args.json:
            _print_json(payload)
        else:
            synthesis = payload.get("synthesis", {})
            print(f"status={payload['status']}")
            print(f"read_execution={payload['read_execution']}")
            print(f"join_execution={payload['join_execution']}")
            if isinstance(synthesis, dict):
                print(f"citation_count={len(synthesis.get('citations', []))}")
                print(f"limitation_count={len(synthesis.get('limitations', []))}")
                answer = synthesis.get("answer", {})
                if isinstance(answer, dict):
                    print(f"summary={answer.get('summary')}")
        return 0

    if args.command == "resolve-citation":
        payload = citation_resolution_payload(
            registry,
            graph_id=args.graph_id,
            local_uuid=args.local_uuid,
        )
        if args.json:
            _print_json(payload)
        else:
            print(f"status={payload['status']}")
            print(f"graph_id={payload['graph_id']}")
            print(f"local_uuid={payload['local_uuid']}")
            if payload.get("query_name") is not None:
                print(f"query_name={payload['query_name']}")
            records = payload.get("records")
            if isinstance(records, tuple | list) and records:
                print("records=")
                print(json.dumps(records, indent=2, sort_keys=True))
        return 0

    if args.command == "bridge-traverse":
        bridge_path = args.bridges or default_bridge_path_for_registry(args.registry)
        bridge_store = load_optional_bridge_store(bridge_path)
        if bridge_store is None:
            raise RtgGraphRegistryInvalid("bridge catalog is not configured")
        payload = bridge_traversal_payload(
            registry,
            bridge_store,
            bridge_id=args.bridge_id,
        )
        if args.json:
            _print_json(payload)
        else:
            print(f"status={payload['status']}")
            print(f"bridge_id={payload['bridge']['bridge_id']}")
            print(f"bridge_type={payload['bridge']['bridge_type']}")
            for endpoint_name in ("source", "target"):
                endpoint = payload[endpoint_name]
                resolution = endpoint["resolution"]
                print(
                    f"{endpoint_name}={endpoint['reference']['graph_id']}:"
                    f"{endpoint['reference']['local_uuid']} "
                    f"status={resolution['status']} records={len(resolution['records'])}"
                )
        return 0

    if args.command == "route-query":
        from apps.rtg_federation.registry_io import route_query_payload

        payload = route_query_payload(
            registry,
            text=args.text,
            target_graph_id=args.target_graph_id,
            canned_query=args.canned_query,
        )
        if args.json:
            _print_json(payload)
        else:
            answer = payload.get("answer", {})
            print(f"status={payload['status']}")
            print(f"selected_graph_id={payload['route']['selected_graph_id']}")
            if isinstance(answer, dict):
                print(f"answer_status={answer.get('status')}")
                if "attention_scope" in answer:
                    print(f"attention_scope={answer['attention_scope']}")
                attention_window = answer.get("attention_window")
                if isinstance(attention_window, dict):
                    print(
                        "attention_window="
                        f"{attention_window.get('start')}..{attention_window.get('end')}"
                    )
                for key in (
                    "component_count",
                    "missing_evidence_count",
                    "item_count",
                    "attention_item_count",
                    "evidence_gap_count",
                    "relationship_open_loop_count",
                ):
                    if key in answer:
                        print(f"{key}={answer[key]}")
                missing = answer.get("missing_evidence_component_ids", [])
                if isinstance(missing, list):
                    for component_id in missing:
                        print(f"- {component_id}")
                attention_items = answer.get("attention_items", [])
                if isinstance(attention_items, list):
                    for item in attention_items[:10]:
                        if not isinstance(item, dict):
                            continue
                        title = item.get("title")
                        kind = item.get("kind")
                        if isinstance(title, str) and isinstance(kind, str):
                            print(f"- {kind}: {title}")
        return 0

    if args.command == "bridge-candidates":
        bridge_path = args.bridges or default_bridge_path_for_registry(args.registry)
        if args.bridge_candidate_command == "list":
            payload = bridge_candidates_payload(bridge_path, status=args.status)
            if args.json:
                _print_json(payload)
            else:
                print(
                    f"candidate_count={payload['candidate_count']} "
                    f"status_filter={payload['status_filter']}"
                )
                for candidate in payload["candidates"]:
                    print(
                        f"- {candidate['candidate_id']} "
                        f"status={candidate['status']} "
                        f"confidence={candidate['confidence']:.2f} "
                        f"source={_format_reference(candidate['source'])} "
                        f"target={_format_reference(candidate['target'])}"
                    )
            return 0
        if args.bridge_candidate_command == "inspect":
            payload = bridge_candidate_payload(bridge_path, args.candidate_id)
            if args.json:
                _print_json(payload)
            else:
                candidate = payload["candidate"]
                print(f"candidate_id={candidate['candidate_id']}")
                print(f"status={candidate['status']}")
                print(f"bridge_type={candidate['bridge_type']}")
                print(f"confidence={candidate['confidence']:.2f}")
                print(f"source={_format_reference(candidate['source'])}")
                print(f"target={_format_reference(candidate['target'])}")
                print(f"evidence_count={len(candidate['evidence'])}")
            return 0
        if args.bridge_candidate_command == "promote":
            payload = promote_bridge_candidate_payload(
                bridge_path,
                candidate_id=args.candidate_id,
                asserted_at=args.asserted_at,
                asserted_by=args.asserted_by,
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"candidate_id={payload['candidate']['candidate_id']}")
                print(f"candidate_status={payload['candidate']['status']}")
                print(f"bridge_id={payload['bridge']['bridge_id']}")
                print("catalog_written=true")
            return 0
        if args.bridge_candidate_command == "reject":
            payload = reject_bridge_candidate_payload(
                bridge_path,
                candidate_id=args.candidate_id,
                rejected_at=args.rejected_at,
                rejected_by=args.rejected_by,
                reason=args.reason,
            )
            if args.json:
                _print_json(payload)
            else:
                print(f"candidate_id={payload['candidate']['candidate_id']}")
                print(f"candidate_status={payload['candidate']['status']}")
                print(f"rejection_reason={payload['candidate']['rejection_reason']}")
                print("catalog_written=true")
            return 0

    if args.command == "init":
        payload = init_graph_payload(registry, args.graph_id)
        if args.json:
            _print_json(payload)
        else:
            validation = payload["validation"]
            accepted = validation.get("result", {}).get("accepted") if validation["ok"] else False
            print(f"graph={payload['graph']['graph_id']}")
            print(f"storage_root={payload['app']['storage_root']}")
            print(f"sql_database_path={payload['app']['sql_database_path']}")
            print(f"validation_ok={validation['ok']} accepted={accepted}")
        return 0

    if args.command == "mcp-info":
        payload = mcp_info_payload(registry, args.graph_id)
        if args.json:
            _print_json(payload)
        else:
            launch = payload["launch"]
            print(f"graph={payload['graph']['graph_id']}")
            print("launch:")
            print(" ".join([launch["command"], *launch["args"]]))
            print("client_config:")
            print(json.dumps(payload["client_config"], indent=2, sort_keys=True))
        return 0

    if args.command == "serve-http":
        graph = registry.get_graph(args.graph_id)
        endpoint = graph.mcp_endpoint
        if endpoint is None or endpoint.transport != "http":
            raise RtgGraphRegistryInvalid(
                f"graph {graph.graph_id} does not declare an HTTP endpoint"
            )
        run_mcp_server(
            RtgKnowledgeGraphConfig(
                storage_root=absolute_graph_path(graph.storage_root),
                sql_database_path=absolute_graph_path(graph.sql_database_path),
            ),
            transport="http",
            host=endpoint.host or "127.0.0.1",
            port=endpoint.port or 8765,
            path=endpoint.path,
        )
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _format_reference(reference: dict[str, object]) -> str:
    return f"{reference['graph_id']}:{reference['local_uuid']}"


def _federated_capabilities_check(payload: dict[str, object]) -> dict[str, object]:
    graphs = payload.get("graphs", [])
    if not isinstance(graphs, list):
        return {"status": "failed", "failed_graph_ids": ["<invalid-payload>"]}
    failed_graph_ids: list[str] = []
    for graph in graphs:
        if not isinstance(graph, dict):
            failed_graph_ids.append("<invalid-graph>")
            continue
        status = graph.get("status")
        if status not in {"ready", "none_declared"}:
            graph_id = graph.get("graph_id")
            failed_graph_ids.append(str(graph_id) if graph_id is not None else "<unknown>")
    return {
        "status": "passed" if not failed_graph_ids else "failed",
        "failed_graph_ids": failed_graph_ids,
    }


def _federated_capability_template_payload(
    *,
    query_name: str,
    module: str | None,
    description: str | None,
    terms: tuple[str, ...],
    domains: tuple[str, ...],
    tags: tuple[str, ...],
) -> dict[str, object]:
    normalized_query_name = query_name.strip()
    if not normalized_query_name:
        raise RtgGraphRegistryInvalid("query_name must be a non-empty string")
    module_name = module.strip() if module is not None else _default_query_module(query_name)
    if not module_name:
        raise RtgGraphRegistryInvalid("--module must be a non-empty string")
    implementation = f"{module_name}:CANNED_QUERY"
    capability_description = description or f"TODO: describe {normalized_query_name}."
    descriptor = {
        "query_name": normalized_query_name,
        "implementation": implementation,
        "description": capability_description,
        "terms": list(terms),
        "domains": list(domains),
        "tags": list(tags),
    }
    return {
        "descriptor": descriptor,
        "module_path": f"{module_name.replace('.', '/')}.py",
        "module_template": _canned_query_module_template(normalized_query_name),
        "check_command": "just rtg-federated-capabilities-check",
    }


def _default_query_module(query_name: str) -> str:
    slug = "".join(
        character if character.isalnum() else "_" for character in query_name.strip().lower()
    ).strip("_")
    if not slug:
        raise RtgGraphRegistryInvalid("query_name must contain at least one alphanumeric character")
    return f"apps.rtg_federation.queries.{slug}"


def _canned_query_module_template(query_name: str) -> str:
    return "\n".join(
        [
            "from __future__ import annotations",
            "",
            "from typing import Any",
            "",
            "from apps.rtg_federation.canned_queries import CannedQuery",
            "",
            "",
            "def summarize(query: dict[str, Any]) -> dict[str, Any]:",
            '    return {"status": "TODO", "query": query}',
            "",
            "",
            "def citations_for_answer(",
            "    graph_id: str,",
            "    answer: dict[str, Any],",
            ") -> tuple[dict[str, str | None], ...]:",
            "    _ = (graph_id, answer)",
            "    return ()",
            "",
            "",
            "CANNED_QUERY = CannedQuery(",
            f'    name="{query_name}",',
            '    description="TODO: describe this federated read.",',
            "    query_spec={},",
            "    query_options=None,",
            "    response_options=None,",
            "    summarize=summarize,",
            "    citations_for_answer=citations_for_answer,",
            ")",
        ]
    )


def _parse_canned_query_overrides(values: list[str]) -> dict[str, str] | None:
    if not values:
        return None
    overrides: dict[str, str] = {}
    for value in values:
        graph_id, separator, query_name = value.partition("=")
        if not separator or not graph_id or not query_name:
            raise RtgGraphRegistryInvalid("--canned-query must use graph_id=query_name")
        overrides[graph_id] = query_name
    return overrides


if __name__ == "__main__":
    raise SystemExit(main())
