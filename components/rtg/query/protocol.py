from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID

from components.rtg.graph.protocol import JsonObject, JsonScalar, JsonValue, RtgGraph


@dataclass(frozen=True, slots=True)
class RtgQueryAnchorBucket:
    name: str
    anchor_type_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RtgQueryLinkRequirement:
    name: str
    source_bucket: str
    target_bucket: str
    link_type_keys: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RtgQueryPropertyPredicate:
    path: tuple[str, ...]
    operator: str
    value: JsonValue = None
    values: tuple[JsonScalar, ...] = ()
    case_sensitive: bool = False
    regex_flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgQueryDataRequirement:
    name: str
    anchor_bucket: str
    data_type_key: str
    required: bool = True
    predicates: tuple[RtgQueryPropertyPredicate, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgQueryReturnSpec:
    anchor_buckets: tuple[str, ...] = ()
    link_requirements: tuple[str, ...] = ()
    data_requirements: tuple[str, ...] = ()
    properties: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class RtgQueryDiagnosticOptions:
    include_non_fatal: bool = True
    unknown_term_guidance: str = "suggest_discovery"


@dataclass(frozen=True, slots=True)
class RtgQuerySpec:
    anchor_buckets: tuple[RtgQueryAnchorBucket, ...]
    link_requirements: tuple[RtgQueryLinkRequirement, ...] = ()
    data_requirements: tuple[RtgQueryDataRequirement, ...] = ()
    return_spec: RtgQueryReturnSpec = field(default_factory=RtgQueryReturnSpec)
    diagnostic_options: RtgQueryDiagnosticOptions = field(default_factory=RtgQueryDiagnosticOptions)


@dataclass(frozen=True, slots=True)
class RtgQueryOptions:
    live_filter: str = "all"
    live_status_overlay: dict[UUID, bool] = field(default_factory=dict)
    order_by: tuple[RtgQueryOrderBy, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgQueryOrderBy:
    data_requirement: str
    path: tuple[str, ...]
    direction: str = "ascending"


@dataclass(frozen=True, slots=True)
class RtgQueryBindingRow:
    row_index: int
    anchors: dict[str, UUID]
    links: dict[str, UUID] = field(default_factory=dict)
    data_objects: dict[str, UUID] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgQueryReturnRow:
    row_index: int
    anchors: dict[str, UUID] = field(default_factory=dict)
    links: dict[str, UUID] = field(default_factory=dict)
    data_objects: dict[str, UUID] = field(default_factory=dict)
    properties: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgQueryDiagnostic:
    severity: str
    code: str
    message: str
    suggestion: str | None = None
    affected_terms: tuple[str, ...] = ()
    diagnostic: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RtgQueryResult:
    bindings: tuple[RtgQueryBindingRow, ...]
    returns: tuple[RtgQueryReturnRow, ...]
    diagnostics: tuple[RtgQueryDiagnostic, ...] = ()


class RtgQueryError(Exception):
    """Base class for RTG Query errors."""

    def __init__(self, message: str, *, diagnostic: JsonObject | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic or {}


class RtgQuerySpecInvalid(RtgQueryError):
    """A query specification is malformed."""


class RtgQueryUnsupported(RtgQueryError):
    """A query asks for unsupported behavior."""


class RtgQueryEngine(Protocol):
    def execute(
        self,
        graph: RtgGraph,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        """Execute an RTG query over a graph read view."""
        ...
