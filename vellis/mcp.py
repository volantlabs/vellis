"""The selected ten-tool boundary an agent reaches Vellis through.

Realizes ``RTGSystem::rtg_definition_summary``, ``rtg_definition_inspect``,
``rtg_definition_delta``, ``rtg_query``, ``rtg_change``, ``rtg_set_definition_delta``,
``rtg_activate_definition_delta``, ``rtg_discard_definition_delta``, ``rtg_check``, and
``rtg_history``, carrying ``VellisRequirements::mcpAgentToolContract`` and
``VellisRequirements::mcpOutcomeIntegrity``.

Ten tools and no more. The surface is small because an agent has to be able to hold the
whole of it, and stable because an agent that learned it last month should not have to
relearn it. Each one exposes behavior that already exists in the system boundary; nothing
here decides anything.

That is the discipline this module keeps. It translates nothing and validates nothing: a
refusal is the refusal the system produced, a payload is the payload the system built.
Anything decided here would be a second authority, and the difference between "the memory
refused this" and "the tool layer refused this" is exactly the difference an owner needs
to be able to trust.

The three outcome shapes stay distinct and stay separate things. A semantic rejection is
a typed result the system returned. Malformed input never forms a domain request at all —
the framework rejects it before a tool body runs. An unexpected failure produces no
completed result. Collapsing any two of those would leave a caller unable to tell "your
memory says no" from "your request made no sense" from "something broke".

Tool descriptions are advisory. They say what a tool does; nothing reads them, and
changing one cannot change what any operation permits, validates, or preserves.

The wire form is written out here rather than derived, for one reason: a stored number
must arrive as a JSON number. The obvious automatic rendering turns every one into a
string, and because the model permits only complete-object upserts, an agent that read an
object and wrote it back whole would be rewriting its owner's numbers into text — quietly,
and into canonical state. Everything else follows the ordinary shape of the value.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import cast

from fastmcp import FastMCP
from fastmcp.tools.base import ToolResult

from vellis.activity import HistoryQuery, HistoryResult
from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.discovery import (
    DefinitionInspectionRequest,
    DefinitionInspectionResult,
    DefinitionSummaryResult,
)
from vellis.governance import DefinitionDeltaResult, SetDefinitionDeltaRequest
from vellis.history import HistoricalSelection
from vellis.json_value import MAXIMUM_STORED_INTEGER_EXPONENT, JsonValueError
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationScope,
)
from vellis.query import GraphQuery, GraphQueryResult
from vellis.store import StoreError
from vellis.system import RTGSystem

__all__ = ["TOOL_NAMES", "ServeError", "build_server", "serve"]


class ServeError(RuntimeError):
    """Raised when the boundary cannot serve a memory at the requested destination.

    Carries a corrective action rather than only a message. A client that cannot start
    the server is one of the two failures ``VellisVerification::simpleOperation`` requires
    to be actionable, and a bare exception string is exactly the generic failure it says
    does not pass.
    """

    def __init__(self, summary: str, corrective_action: str) -> None:
        super().__init__(summary)
        self.summary = summary
        self.corrective_action = corrective_action


# The selected surface, in the order the model declares it. Named here so a test can hold
# the boundary to exactly this set rather than to whatever happens to be registered.
TOOL_NAMES = (
    "rtg_definition_summary",
    "rtg_definition_inspect",
    "rtg_definition_delta",
    "rtg_query",
    "rtg_change",
    "rtg_set_definition_delta",
    "rtg_activate_definition_delta",
    "rtg_discard_definition_delta",
    "rtg_check",
    "rtg_history",
)


def build_server(system: RTGSystem, *, name: str = "vellis") -> FastMCP:
    """Expose one system through the selected tools.

    Every tool body is one call. Where a parameter would carry no meaning it is absent
    rather than empty: an optional selector rides directly on the summary, and the
    parameterless tools take nothing, so no empty request type enters the vocabulary an
    agent has to learn.
    """
    server: FastMCP = FastMCP(name)

    @server.tool
    def rtg_definition_summary(
        historical_selection: HistoricalSelection | None = None,
    ) -> DefinitionSummaryResult:
        """Discover every anchor type active at current or selected historical state."""
        return _result(
            system.definition_summary(selection=historical_selection, provenance=_agent()),
            lambda reason: DefinitionSummaryResult(
                status=OperationStatus.FAILED,
                summary=f"the summary could not be returned completely: {reason}",
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    @server.tool
    def rtg_definition_inspect(
        request: DefinitionInspectionRequest,
    ) -> DefinitionInspectionResult:
        """Inspect complete evaluated neighborhoods for selected anchors."""
        return _result(
            system.inspect_definitions(request, provenance=_agent()),
            lambda reason: DefinitionInspectionResult(
                status=OperationStatus.FAILED,
                summary=f"the neighborhoods could not be returned completely: {reason}",
                request=request,
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    @server.tool
    def rtg_definition_delta() -> DefinitionDeltaResult:
        """Retrieve the complete sole proposal and current assessment, or normal absence."""
        return _result(
            system.definition_delta(provenance=_agent()),
            lambda reason: DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be returned completely: {reason}",
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    @server.tool
    def rtg_query(query: GraphQuery) -> GraphQueryResult:
        """Query current or selected historical graph meaning with one complete bound."""
        return _result(
            system.query_graph(query, provenance=_agent()),
            lambda reason: GraphQueryResult(
                status=OperationStatus.FAILED,
                summary=f"the result could not be returned completely: {reason}",
                query=query,
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    @server.tool
    def rtg_change(change: GraphChange) -> RevisionedOutcome:
        """Validate explicit upserts and removals, then atomically commit an effective change."""
        return _result(
            system.apply_graph_change(change, provenance=_agent()),
            _unreturnable_outcome,
        )

    @server.tool
    def rtg_set_definition_delta(request: SetDefinitionDeltaRequest) -> DefinitionDeltaResult:
        """Create or replace the sole complete proposal and return its current assessment."""
        return _result(
            system.set_definition_delta(request.proposed_definitions, provenance=_agent()),
            lambda reason: DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the assessment could not be returned completely: {reason}",
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    @server.tool
    def rtg_activate_definition_delta() -> RevisionedOutcome:
        """Activate the valid sole proposal atomically or preserve all current canonical state."""
        return _result(
            system.activate_definition_delta(provenance=_agent()),
            _unreturnable_outcome,
        )

    @server.tool
    def rtg_discard_definition_delta() -> RevisionedOutcome:
        """Discard the sole proposal atomically or report normal absence."""
        return _result(
            system.discard_definition_delta(provenance=_agent()),
            _unreturnable_outcome,
        )

    @server.tool
    def rtg_check() -> ValidationReport:
        """Assess complete current-graph conformance against active definitions without mutation."""
        return _result(
            system.check(provenance=_agent()),
            lambda reason: ValidationReport(
                scope=ValidationScope.GRAPH_CONFORMANCE,
                conforms=False,
                evaluated_revision=0,
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    @server.tool
    def rtg_history(query: HistoryQuery) -> HistoryResult:
        """Return one complete bounded canonical or activity history-entry interval."""
        return _result(
            system.history(query, provenance=_agent()),
            lambda reason: HistoryResult(
                status=OperationStatus.FAILED,
                summary=f"the history could not be returned completely: {reason}",
                query=query,
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    return server


def _wire(value: object) -> object:
    """Render one result for the wire, preserving JSON kind.

    A number goes out as a number: exactly for an integer of any size, and for a
    fractional value only when it survives the trip. One that would arrive rounded is
    refused, because an approximated memory is worse than one that says it could not
    answer completely.
    """
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            if abs(value.adjusted()) > MAXIMUM_STORED_INTEGER_EXPONENT:
                raise JsonValueError(f"the number {value} is larger than a stored integer may be")
            return int(value)
        rendered = float(value)
        if Decimal(repr(rendered)) != value:
            raise JsonValueError(
                f"the number {value} cannot be returned as a JSON number without rounding"
            )
        return rendered
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _wire(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _wire(member) for key, member in value.items()}
    if isinstance(value, Sequence):
        return [_wire(each) for each in value]
    # This module owns the wire form, so an unrecognized value is a hole in it rather
    # than something to hand on and hope.
    raise JsonValueError(f"no wire form for {type(value).__name__}")


def _result[T](value: T, unreturnable: Callable[[str], T]) -> T:
    """Hand back one outcome in both representations, saying the same thing.

    A value the wire cannot carry becomes a typed refusal of the same shape rather than a
    crash. The system said this operation succeeded; the boundary is only reporting that
    it cannot hand the answer over completely, which is a thing the caller can be told
    rather than a thing that breaks.

    Typed as the outcome it carries because that is what a caller receives and what the
    tool's declared return type must stay: FastMCP derives the output schema from the
    annotation and accepts a prepared result at run time. The one cast is here so the ten
    tools read as what they are.
    """
    try:
        wired = _wire(value)
    except JsonValueError as error:
        wired = _wire(unreturnable(str(error)))
    return cast("T", ToolResult(structured_content=wired))  # pyright: ignore[reportArgumentType]


def _unreturnable_outcome(reason: str) -> RevisionedOutcome:
    """Report a change whose outcome could not be handed back completely."""
    return RevisionedOutcome(
        status=OperationStatus.FAILED,
        summary=f"the outcome could not be returned completely: {reason}",
        findings=(ValidationFinding(summary=reason),),
    )


def _agent() -> Provenance:
    """Attribute a tool call to the agent the owner configured.

    The boundary knows only that something reached it through the configured client. It
    does not decide who that is or what they may do — the model is explicit that RTG
    operations neither create nor evaluate an authorization scope — so this records the
    one true thing available and claims nothing further.
    """
    return Provenance(initiator="agent", source="mcp")


def serve(path: Path, *, name: str = "vellis") -> None:
    """Run the boundary over local standard input and output.

    STDIO is the whole transport. One owner, one machine, one process the client starts —
    nothing is listening on a port, so there is no surface to authorize and none to
    expose. HTTP, OAuth, remote hosting, and packaging stay out until something asks for
    them.
    """
    if not path.exists():
        # Opening would create one. A server that quietly established a memory would be
        # making the owner's decision for them, and on a mistyped path it would make it
        # in the wrong place.
        raise ServeError(
            f"no Vellis memory is established at {path}",
            # The destination is named in the advice, not only in the diagnosis. A bare
            # "run setup" would establish a system at the default location, which is not
            # this one, and the next launch would fail exactly as this one did.
            f"run `python -m vellis.setup --data-dir {path.parent}` to begin one here, or "
            "point --data-dir at the directory that already holds your system",
        )
    try:
        system = RTGSystem.open(path)
    except StoreError as error:
        # Whatever is at that path, this could not open it as one owner's memory. Nothing
        # was written; the destination is exactly as it was found.
        raise ServeError(
            f"the memory at {path} could not be opened: {error}",
            "check that this account can read and write that file and the directory "
            "holding it, and that --data-dir names your Vellis system's directory",
        ) from error
    try:
        try:
            established = system.is_initialized
        except StoreError as error:
            raise ServeError(
                f"the memory at {path} could not be read: {error}",
                "check that this account can read and write that file, and that nothing "
                "else is holding it open",
            ) from error
        if not established:
            # The ten tools read and change a memory; none of them makes one. Starting
            # here would leave every first call refusing for a reason the surface cannot
            # express, so this says the one useful thing instead.
            raise ServeError(
                f"no Vellis memory is established at {path}",
                f"run `python -m vellis.setup --data-dir {path.parent}` to begin one "
                "here, or point --data-dir at the directory that already holds your "
                "system",
            )
        build_server(system, name=name).run(transport="stdio")
    finally:
        system.close()
