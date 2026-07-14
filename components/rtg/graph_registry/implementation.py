from __future__ import annotations

import copy
import math
import re
from collections.abc import Iterable, Mapping

from components.rtg.graph_registry.protocol import (
    JsonObject,
    JsonValue,
    RtgGraphDescriptor,
    RtgGraphFederatedIntent,
    RtgGraphFederatedPlan,
    RtgGraphFederatedPlanStep,
    RtgGraphIntent,
    RtgGraphList,
    RtgGraphMcpEndpoint,
    RtgGraphNotFound,
    RtgGraphRegistryInvalid,
    RtgGraphRouteCandidate,
    RtgGraphRouteRecord,
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_AUTO_SELECT_READ_THRESHOLD = 0.5


class InMemoryRtgGraphRegistry:
    """In-memory implementation of the RTG Graph Registry component."""

    def __init__(self) -> None:
        self._graphs: dict[str, RtgGraphDescriptor] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgGraphRegistry:
        return cls()

    def put_graph(self, graph: RtgGraphDescriptor) -> RtgGraphDescriptor:
        normalized = _normalize_graph(graph)
        self._graphs[normalized.graph_id] = normalized
        return _copy_descriptor(normalized)

    def list_graphs(self) -> RtgGraphList:
        return RtgGraphList(
            graphs=tuple(
                _copy_descriptor(graph)
                for graph in sorted(self._graphs.values(), key=lambda item: item.graph_id)
            )
        )

    def get_graph(self, graph_id: str) -> RtgGraphDescriptor:
        normalized_id = _validate_identifier(graph_id, "graph_id")
        try:
            graph = self._graphs[normalized_id]
        except KeyError as error:
            raise RtgGraphNotFound(normalized_id) from error
        return _copy_descriptor(graph)

    def compile_intent(self, intent: RtgGraphIntent) -> RtgGraphRouteRecord:
        normalized = _normalize_intent(intent)
        if normalized.target_graph_id is not None:
            graph = self.get_graph(normalized.target_graph_id)
            candidate = RtgGraphRouteCandidate(
                graph_id=graph.graph_id,
                score=1.0,
                reasons=("explicit target_graph_id",),
            )
            return RtgGraphRouteRecord(
                intent=normalized,
                candidates=(candidate,),
                selected_graph_id=graph.graph_id,
                requires_confirmation=False,
                reason="explicit target_graph_id selected the graph",
            )

        candidates = tuple(
            sorted(
                (
                    candidate
                    for graph in self._graphs.values()
                    if (candidate := _score_candidate(graph, normalized)).score > 0
                ),
                key=lambda item: (-item.score, item.graph_id),
            )
        )
        selected_graph_id: str | None = None
        requires_confirmation = True
        reason = "no candidate graph matched the intent"
        if candidates:
            top = candidates[0]
            tied = len(candidates) > 1 and candidates[1].score == top.score
            if (
                normalized.operation == "read"
                and top.score >= _AUTO_SELECT_READ_THRESHOLD
                and not tied
            ):
                selected_graph_id = top.graph_id
                requires_confirmation = False
                reason = "read intent matched one high-confidence graph"
            elif normalized.operation != "read":
                reason = "write intents require an explicit target_graph_id"
            elif tied:
                reason = "multiple graphs tied for the strongest match"
            else:
                reason = "best graph match was below the read auto-selection threshold"
        return RtgGraphRouteRecord(
            intent=normalized,
            candidates=candidates,
            selected_graph_id=selected_graph_id,
            requires_confirmation=requires_confirmation,
            reason=reason,
        )

    def compile_federated_intent(self, intent: RtgGraphFederatedIntent) -> RtgGraphFederatedPlan:
        normalized = _normalize_federated_intent(intent)
        if normalized.target_graph_ids:
            steps = tuple(
                RtgGraphFederatedPlanStep(
                    graph_id=self.get_graph(graph_id).graph_id,
                    operation=normalized.operation,
                    intent_text=normalized.text,
                    score=1.0,
                    reasons=("explicit target_graph_ids",),
                )
                for graph_id in normalized.target_graph_ids
            )
            if normalized.operation == "read":
                return RtgGraphFederatedPlan(
                    intent=normalized,
                    steps=steps,
                    requires_confirmation=False,
                    executable=True,
                    reason="explicit target_graph_ids selected graph-local read steps",
                )
            return RtgGraphFederatedPlan(
                intent=normalized,
                steps=steps,
                requires_confirmation=True,
                executable=False,
                reason="federated write and admin plans require graph-local execution flow",
            )

        candidates = tuple(
            sorted(
                (
                    candidate
                    for graph in self._graphs.values()
                    if (
                        candidate := _score_candidate(
                            graph,
                            RtgGraphIntent(
                                operation=normalized.operation,
                                text=normalized.text,
                                domain_hints=normalized.domain_hints,
                                tag_hints=normalized.tag_hints,
                            ),
                        )
                    ).score
                    > 0
                ),
                key=lambda item: (-item.score, item.graph_id),
            )
        )
        steps = tuple(
            RtgGraphFederatedPlanStep(
                graph_id=candidate.graph_id,
                operation=normalized.operation,
                intent_text=normalized.text,
                score=candidate.score,
                reasons=candidate.reasons,
            )
            for candidate in candidates
        )
        if normalized.operation != "read":
            return RtgGraphFederatedPlan(
                intent=normalized,
                steps=steps,
                requires_confirmation=True,
                executable=False,
                reason="federated write and admin plans require explicit target_graph_ids",
            )
        if not steps:
            return RtgGraphFederatedPlan(
                intent=normalized,
                steps=(),
                requires_confirmation=True,
                executable=False,
                reason="no candidate graph matched the federated intent",
            )
        return RtgGraphFederatedPlan(
            intent=normalized,
            steps=steps,
            requires_confirmation=False,
            executable=True,
            reason="read plan includes all matching graph candidates",
        )


def _normalize_graph(graph: RtgGraphDescriptor) -> RtgGraphDescriptor:
    domains = _normalize_text_sequence(graph.domains, "domains", require_one=True)
    tags = _normalize_text_sequence(graph.tags, "tags", require_one=False)
    endpoint = None if graph.mcp_endpoint is None else _normalize_mcp_endpoint(graph.mcp_endpoint)
    return RtgGraphDescriptor(
        graph_id=_validate_identifier(graph.graph_id, "graph_id"),
        title=_validate_text(graph.title, "title"),
        storage_root=_validate_text(graph.storage_root, "storage_root"),
        sql_database_path=_validate_text(graph.sql_database_path, "sql_database_path"),
        authority=_validate_text(graph.authority, "authority"),
        write_policy=_validate_text(graph.write_policy, "write_policy"),
        domains=domains,
        tags=tags,
        mcp_endpoint=endpoint,
        metadata=_validate_metadata(graph.metadata),
    )


def _normalize_mcp_endpoint(endpoint: RtgGraphMcpEndpoint) -> RtgGraphMcpEndpoint:
    transport = _validate_text(endpoint.transport, "transport").lower()
    if transport not in {"http", "stdio"}:
        raise RtgGraphRegistryInvalid("mcp_endpoint.transport must be http or stdio")
    host = None if endpoint.host is None else _validate_text(endpoint.host, "mcp_endpoint.host")
    port = endpoint.port
    if transport == "http":
        if host is None:
            raise RtgGraphRegistryInvalid("http mcp_endpoint.host is required")
        if not isinstance(port, int) or port <= 0 or port > 65535:
            raise RtgGraphRegistryInvalid("http mcp_endpoint.port must be a valid TCP port")
    else:
        port = None
    path = _validate_text(endpoint.path, "mcp_endpoint.path")
    if not path.startswith("/"):
        raise RtgGraphRegistryInvalid("mcp_endpoint.path must start with /")
    server_name = (
        None
        if endpoint.server_name is None
        else _validate_identifier(endpoint.server_name, "mcp_endpoint.server_name")
    )
    return RtgGraphMcpEndpoint(
        transport=transport,
        host=host,
        port=port,
        path=path,
        server_name=server_name,
    )


def _normalize_intent(intent: RtgGraphIntent) -> RtgGraphIntent:
    operation = _validate_text(intent.operation, "operation").lower()
    if operation not in {"read", "write", "admin"}:
        raise RtgGraphRegistryInvalid("operation must be read, write, or admin")
    target_graph_id = (
        None
        if intent.target_graph_id is None
        else _validate_identifier(intent.target_graph_id, "target_graph_id")
    )
    return RtgGraphIntent(
        operation=operation,
        text=_validate_text(intent.text, "text"),
        target_graph_id=target_graph_id,
        domain_hints=_normalize_text_sequence(
            intent.domain_hints, "domain_hints", require_one=False
        ),
        tag_hints=_normalize_text_sequence(intent.tag_hints, "tag_hints", require_one=False),
    )


def _normalize_federated_intent(intent: RtgGraphFederatedIntent) -> RtgGraphFederatedIntent:
    operation = _validate_text(intent.operation, "operation").lower()
    if operation not in {"read", "write", "admin"}:
        raise RtgGraphRegistryInvalid("operation must be read, write, or admin")
    target_graph_ids = _normalize_text_sequence(
        intent.target_graph_ids, "target_graph_ids", require_one=False
    )
    for graph_id in target_graph_ids:
        _validate_identifier(graph_id, "target_graph_ids")
    return RtgGraphFederatedIntent(
        operation=operation,
        text=_validate_text(intent.text, "text"),
        target_graph_ids=target_graph_ids,
        domain_hints=_normalize_text_sequence(
            intent.domain_hints, "domain_hints", require_one=False
        ),
        tag_hints=_normalize_text_sequence(intent.tag_hints, "tag_hints", require_one=False),
    )


def _score_candidate(graph: RtgGraphDescriptor, intent: RtgGraphIntent) -> RtgGraphRouteCandidate:
    query_tokens = _token_set(intent.text)
    query_text = intent.text.lower()
    units = 0
    reasons: list[str] = []
    matched_terms: set[str] = set()

    graph_id_token = _tokenize_phrase(graph.graph_id)
    if graph.graph_id in query_tokens or graph.graph_id.lower() in query_text:
        units += 5
        reasons.append(f"graph_id:{graph.graph_id}")
    elif graph_id_token and graph_id_token.issubset(query_tokens):
        units += 4
        reasons.append(f"graph_id_words:{graph.graph_id}")

    for domain in graph.domains:
        if _matches_phrase(domain, query_tokens, query_text):
            units += 3
            reasons.append(f"domain:{domain}")
            matched_terms.add(_normalize_match_term(domain))
    for tag in graph.tags:
        normalized_tag = _normalize_match_term(tag)
        if normalized_tag not in matched_terms and _matches_phrase(tag, query_tokens, query_text):
            units += 2
            reasons.append(f"tag:{tag}")
            matched_terms.add(normalized_tag)
    for domain in intent.domain_hints:
        if domain in graph.domains:
            units += 4
            reasons.append(f"domain_hint:{domain}")
    for tag in intent.tag_hints:
        if tag in graph.tags:
            units += 3
            reasons.append(f"tag_hint:{tag}")

    score = min(1.0, units / 10)
    return RtgGraphRouteCandidate(
        graph_id=graph.graph_id,
        score=score,
        reasons=tuple(reasons),
    )


def _matches_phrase(phrase: str, query_tokens: set[str], query_text: str) -> bool:
    if phrase.lower() in query_text:
        return True
    phrase_tokens = _tokenize_phrase(phrase)
    return bool(phrase_tokens) and phrase_tokens.issubset(query_tokens)


def _tokenize_phrase(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in _TOKEN_PATTERN.findall(value.lower()):
        normalized = _normalize_token(token)
        tokens.add(normalized)
        if normalized.endswith("s") and len(normalized) > 1:
            tokens.add(normalized[:-1])
        elif normalized:
            tokens.add(f"{normalized}s")
    return tokens


def _token_set(value: str) -> set[str]:
    return _tokenize_phrase(value)


def _normalize_token(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _normalize_match_term(value: str) -> str:
    tokens = sorted(_tokenize_phrase(value))
    return " ".join(tokens)


def _normalize_text_sequence(
    values: Iterable[str],
    name: str,
    *,
    require_one: bool,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _validate_text(value, name)
        if item in seen:
            raise RtgGraphRegistryInvalid(f"{name} contains duplicate value: {item}")
        seen.add(item)
        normalized.append(item)
    if require_one and not normalized:
        raise RtgGraphRegistryInvalid(f"{name} must contain at least one value")
    return tuple(normalized)


def _validate_metadata(value: JsonObject) -> JsonObject:
    metadata = copy.deepcopy(value)
    if not isinstance(metadata, dict):
        raise RtgGraphRegistryInvalid("metadata must be a JSON object")
    _validate_json_value(metadata)
    return metadata


def _validate_json_value(value: JsonValue) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RtgGraphRegistryInvalid("metadata keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise RtgGraphRegistryInvalid("metadata numbers must be finite")
    if value is None or isinstance(value, str | int | float | bool):
        return
    raise RtgGraphRegistryInvalid("metadata values must be JSON-serializable")


def _validate_identifier(value: str, name: str) -> str:
    item = _validate_text(value, name)
    if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]*", item):
        raise RtgGraphRegistryInvalid(f"{name} must be an identifier")
    return item


def _validate_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgGraphRegistryInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _copy_descriptor(graph: RtgGraphDescriptor) -> RtgGraphDescriptor:
    return copy.deepcopy(graph)
