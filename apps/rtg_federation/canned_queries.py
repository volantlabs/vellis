from __future__ import annotations

import importlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

from components.rtg.graph_registry import RtgGraphRegistryInvalid

REPO_COMPONENTS_EVIDENCE_STATUS = "repo_components_evidence_status"
REPO_COMPONENTS_EVIDENCE_STATUS_IMPLEMENTATION = (
    "apps.rtg_federation.queries.repo_components_evidence_status:CANNED_QUERY"
)
PERSONAL_ATTENTION_OVERVIEW = "personal_attention_overview"
PERSONAL_ATTENTION_OVERVIEW_IMPLEMENTATION = (
    "apps.rtg_federation.queries.personal_attention_overview:CANNED_QUERY"
)

_BUILTIN_CANNED_QUERY_IMPLEMENTATIONS = {
    REPO_COMPONENTS_EVIDENCE_STATUS: REPO_COMPONENTS_EVIDENCE_STATUS_IMPLEMENTATION,
    PERSONAL_ATTENTION_OVERVIEW: PERSONAL_ATTENTION_OVERVIEW_IMPLEMENTATION,
}
_CANNED_QUERY_CACHE: dict[tuple[str, str], CannedQuery] = {}
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

CannedQuerySummarizer = Callable[[dict[str, Any]], dict[str, Any]]
CannedQueryCitationBuilder = Callable[[str, dict[str, Any]], tuple[dict[str, str | None], ...]]


@dataclass(frozen=True, slots=True)
class CannedQuery:
    name: str
    description: str
    query_spec: dict[str, Any]
    query_options: dict[str, Any] | None
    response_options: dict[str, Any] | None
    summarize: CannedQuerySummarizer
    citations_for_answer: CannedQueryCitationBuilder
    implementation: str | None = None


@dataclass(frozen=True, slots=True)
class FederatedReadCapability:
    query_name: str
    terms: tuple[str, ...]
    domains: tuple[str, ...]
    tags: tuple[str, ...]
    description: str | None
    implementation: str | None = None


def resolve_canned_query(
    name: str,
    *,
    implementation: str | None = None,
) -> CannedQuery:
    normalized = name.strip()
    source = _implementation_source_for_query(normalized, implementation)
    cache_key = (normalized, source)
    cached = _CANNED_QUERY_CACHE.get(cache_key)
    if cached is not None:
        return cached

    loaded = _load_canned_query(source)
    if loaded.name != normalized:
        raise RtgGraphRegistryInvalid(
            f"canned_query implementation {source} returned {loaded.name}, expected {normalized}"
        )
    canned = replace(loaded, implementation=source)
    _CANNED_QUERY_CACHE[cache_key] = canned
    return canned


def infer_federated_read_capability(
    *,
    graph_id: str,
    text: str,
    metadata: Mapping[str, Any],
    explicit_queries: dict[str, str] | None = None,
) -> FederatedReadCapability | None:
    capabilities = federated_read_capabilities_from_metadata(metadata)
    if explicit_queries is not None and graph_id in explicit_queries:
        query_name = explicit_queries[graph_id]
        for capability in capabilities:
            if capability.query_name == query_name:
                return capability
        return FederatedReadCapability(
            query_name=query_name,
            terms=(),
            domains=(),
            tags=(),
            description=None,
            implementation=None,
        )

    scored = sorted(
        (
            (score, index, capability)
            for index, capability in enumerate(capabilities)
            if (score := _score_capability(capability, text)) > 0
        ),
        key=lambda item: (-item[0], item[1], item[2].query_name),
    )
    if not scored:
        return None
    return scored[0][2]


def infer_federated_canned_query(
    *,
    graph_id: str,
    text: str,
    metadata: Mapping[str, Any],
    explicit_queries: dict[str, str] | None = None,
) -> str | None:
    capability = infer_federated_read_capability(
        graph_id=graph_id,
        text=text,
        metadata=metadata,
        explicit_queries=explicit_queries,
    )
    return None if capability is None else capability.query_name


def federated_read_capabilities_from_metadata(
    metadata: Mapping[str, Any],
) -> tuple[FederatedReadCapability, ...]:
    payload = metadata.get("federated_read_capabilities", [])
    if not isinstance(payload, list):
        raise RtgGraphRegistryInvalid("metadata.federated_read_capabilities must be a list")
    return tuple(_capability_from_payload(item) for item in payload)


def summarize_canned_query(
    canned_query: CannedQuery | str,
    query: dict[str, Any],
    *,
    implementation: str | None = None,
) -> dict[str, Any]:
    canned = (
        resolve_canned_query(canned_query, implementation=implementation)
        if isinstance(canned_query, str)
        else canned_query
    )
    return canned.summarize(query)


def citations_for_canned_answer(
    *,
    graph_id: str,
    query_name: str,
    answer: dict[str, Any],
    implementation: str | None = None,
) -> tuple[dict[str, str | None], ...]:
    canned = resolve_canned_query(query_name, implementation=implementation)
    return canned.citations_for_answer(graph_id, answer)


def graph_local_anchor_uuid(row: Mapping[str, Any], bucket_name: str) -> str | None:
    anchors = row.get("anchors")
    if not isinstance(anchors, dict):
        return None
    value = anchors.get(bucket_name)
    if not isinstance(value, str):
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _implementation_source_for_query(name: str, implementation: str | None) -> str:
    if implementation is not None:
        source = implementation.strip()
        if not source:
            raise RtgGraphRegistryInvalid("canned_query implementation must be a non-empty string")
        return source
    source = _BUILTIN_CANNED_QUERY_IMPLEMENTATIONS.get(name)
    if source is None:
        raise RtgGraphRegistryInvalid(f"unknown canned_query: {name}")
    return source


def _load_canned_query(source: str) -> CannedQuery:
    module_name, separator, attribute_path = source.partition(":")
    if not separator or not module_name or not attribute_path:
        raise RtgGraphRegistryInvalid(
            "canned_query implementation must use module:attribute format"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise RtgGraphRegistryInvalid(
            f"could not import canned_query implementation {source}: {error}"
        ) from error

    value: Any = module
    for attribute in attribute_path.split("."):
        if not attribute:
            raise RtgGraphRegistryInvalid(
                "canned_query implementation attribute path must not be empty"
            )
        try:
            value = getattr(value, attribute)
        except AttributeError as error:
            raise RtgGraphRegistryInvalid(
                f"canned_query implementation {source} is missing attribute {attribute}"
            ) from error

    if isinstance(value, CannedQuery):
        return value
    if callable(value):
        built = value()
        if isinstance(built, CannedQuery):
            return built
    raise RtgGraphRegistryInvalid(f"canned_query implementation {source} must return a CannedQuery")


def _query_tokens(text: str) -> set[str]:
    return set(_TOKEN_PATTERN.findall(text.lower()))


def _capability_from_payload(payload: object) -> FederatedReadCapability:
    if not isinstance(payload, dict):
        raise RtgGraphRegistryInvalid("federated read capability must be an object")
    description = payload.get("description")
    if description is not None and not isinstance(description, str):
        raise RtgGraphRegistryInvalid("federated read capability description must be a string")
    return FederatedReadCapability(
        query_name=_required_str(payload, "query_name"),
        terms=tuple(_optional_str_list(payload, "terms")),
        domains=tuple(_optional_str_list(payload, "domains")),
        tags=tuple(_optional_str_list(payload, "tags")),
        description=description,
        implementation=_optional_str(payload, "implementation"),
    )


def _score_capability(capability: FederatedReadCapability, text: str) -> int:
    tokens = _query_tokens(text)
    normalized_text = text.lower()
    terms = capability.terms or (*capability.domains, *capability.tags)
    return sum(1 for term in terms if _matches_term(term, tokens, normalized_text))


def _matches_term(term: str, tokens: set[str], normalized_text: str) -> bool:
    normalized = term.strip().lower()
    if not normalized:
        return False
    if normalized in normalized_text:
        return True
    term_tokens = _query_tokens(normalized)
    return bool(term_tokens) and term_tokens.issubset(tokens)


def _required_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RtgGraphRegistryInvalid(f"federated read capability {key} must be a string")
    return value.strip()


def _optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise RtgGraphRegistryInvalid(f"federated read capability {key} must be a string")
    return value.strip()


def _optional_str_list(payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise RtgGraphRegistryInvalid(f"federated read capability {key} must be a list of strings")
    return value
