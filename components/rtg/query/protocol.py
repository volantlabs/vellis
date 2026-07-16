from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from components.rtg.diagnostics import rtg_diagnostic
from components.rtg.graph.protocol import JsonObject, JsonScalar, JsonValue, RtgGraphReadView

type RtgQueryOperator = Literal[
    "exists",
    "equals",
    "not_equals",
    "lt",
    "lte",
    "gt",
    "gte",
    "contains",
    "in",
    "substring",
    "regex",
]
type RtgQueryLiveFilter = Literal["all", "live", "non_live"]
type RtgQueryOrderDirection = Literal["ascending", "descending"]
type RtgQueryUnknownTermGuidance = Literal["none", "suggest_discovery"]
type RtgQueryDiagnosticSeverity = Literal["warning", "info"]
type RtgQueryAggregationFunction = Literal["count"]


class RtgQueryValueAbsent:
    """Python codec sentinel distinguishing an omitted predicate value from JSON null."""

    __slots__ = ()
    __vellis_codec_absent__ = True


RTG_QUERY_VALUE_ABSENT = RtgQueryValueAbsent()


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
    required: bool = True


@dataclass(frozen=True, slots=True)
class RtgQueryAggregation:
    name: str
    function: RtgQueryAggregationFunction
    binding: str


@dataclass(frozen=True, slots=True)
class RtgQueryPropertyPredicate:
    path: tuple[str, ...]
    operator: RtgQueryOperator
    value: JsonValue | RtgQueryValueAbsent = field(
        default=RTG_QUERY_VALUE_ABSENT,
        metadata={"vellis_codec": "omit_when_absent"},
    )
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
    group_by: tuple[tuple[str, tuple[str, ...]], ...] = ()
    aggregations: tuple[RtgQueryAggregation, ...] = ()


@dataclass(frozen=True, slots=True)
class RtgQueryDiagnosticOptions:
    include_non_fatal: bool = True
    unknown_term_guidance: RtgQueryUnknownTermGuidance = "suggest_discovery"


@dataclass(frozen=True, slots=True)
class RtgQuerySpec:
    anchor_buckets: tuple[RtgQueryAnchorBucket, ...]
    link_requirements: tuple[RtgQueryLinkRequirement, ...] = ()
    data_requirements: tuple[RtgQueryDataRequirement, ...] = ()
    return_spec: RtgQueryReturnSpec = field(default_factory=RtgQueryReturnSpec)
    diagnostic_options: RtgQueryDiagnosticOptions = field(default_factory=RtgQueryDiagnosticOptions)


@dataclass(frozen=True, slots=True)
class RtgQueryOptions:
    live_filter: RtgQueryLiveFilter = "all"
    live_status_overlay: dict[UUID, bool] = field(default_factory=dict)
    order_by: tuple[RtgQueryOrderBy, ...] = ()
    limit: int | None = None
    offset: int = 0
    distinct_rows: bool = False


@dataclass(frozen=True, slots=True)
class RtgQueryOrderBy:
    data_requirement: str
    path: tuple[str, ...]
    direction: RtgQueryOrderDirection = "ascending"


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
    severity: RtgQueryDiagnosticSeverity
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
    aggregations: tuple[JsonObject, ...] = ()
    total_row_count: int = 0
    returned_row_count: int = 0
    next_offset: int | None = None


class RtgQueryError(Exception):
    """Base class for RTG Query errors."""

    diagnostic_code = "query.error"

    def __init__(self, message: str, *, diagnostic: JsonObject | None = None) -> None:
        super().__init__(message)
        self.diagnostic = diagnostic or rtg_diagnostic(
            code=self.diagnostic_code,
            category="query_contract",
            problem=message,
            remedy=(
                "Correct the query specification or options and retry without changing graph state."
            ),
            guide_topics=("workflow_patterns", "query_examples", "tool_call_shapes"),
        )


class RtgQuerySpecInvalid(RtgQueryError):
    """A query specification is malformed."""

    diagnostic_code = "query.spec.invalid"


class RtgQueryUnsupported(RtgQueryError):
    """A query asks for unsupported behavior."""

    diagnostic_code = "query.unsupported"


class RtgQueryEngine(Protocol):
    def execute(
        self,
        graph: RtgGraphReadView,
        query_spec: RtgQuerySpec,
        query_options: RtgQueryOptions | None = None,
    ) -> RtgQueryResult:
        """Execute an RTG query over a graph read view."""
        ...
