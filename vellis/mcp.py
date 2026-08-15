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

The input schemas are made self-contained here for the mirror-image reason. A stored
property holds any JSON value, so every request type that carries one is recursive, and a
recursive schema cannot be inlined — it is published as a reference into a definitions
block instead. A client that does not resolve those references sees an untyped parameter
and sends the whole request as text, which the tool then refuses as malformed: the three
tools that carry owner values become the three tools nobody can call. The model requires
every tool to stay usable through core discovery and invocation without any additional
capability, so the recursion is replaced by the permissive value it stands for and
everything else is inlined. This changes only what a caller is told a request looks like,
never what the system accepts; validation still runs against the real types.
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import cast

import anyio
import anyio.lowlevel
import mcp_types
from fastmcp import FastMCP
from fastmcp.server.context import reset_transport, set_transport
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
from fastmcp.utilities.cli import log_server_banner
from fastmcp.utilities.json_schema import dereference_refs
from fastmcp.utilities.logging import get_logger, temporary_log_level
from mcp.server import stdio as sdk_stdio
from mcp.server.lowlevel.server import NotificationOptions
from mcp.shared._context_streams import (
    ContextReceiveStream,
    ContextSendStream,
    create_context_streams,
)
from mcp.shared.message import SessionMessage
from mcp.types import CallToolRequestParams, CallToolResult, TextContent

from vellis.activity import HistoryQuery, HistoryResult
from vellis.canonical import Provenance
from vellis.changes import GraphChangeRequest
from vellis.discovery import (
    DefinitionInspectionRequest,
    DefinitionInspectionResult,
    DefinitionSummaryRequest,
    DefinitionSummaryResult,
)
from vellis.governance import (
    ActivateDefinitionDeltaRequest,
    DefinitionDeltaResult,
    SetDefinitionDeltaRequest,
)
from vellis.json_value import MAXIMUM_STORED_INTEGER_EXPONENT, JsonValueError
from vellis.outcomes import (
    OperationStatus,
    RevisionedOutcome,
    ValidationFinding,
    ValidationReport,
    ValidationRequest,
)
from vellis.query import GraphQuery, GraphQueryResult
from vellis.store import StoreError
from vellis.system import RTGSystem

__all__ = ["TOOL_NAMES", "ServeError", "ServeStage", "build_server", "serve"]

logger = get_logger(__name__)


class ServeStage:
    """The owner-visible stage at which serving failed."""

    OPEN_MEMORY = "open-memory"
    CLOSE_MEMORY = "close-memory"


class ServeError(RuntimeError):
    """Raised when the boundary cannot serve a memory at the requested destination.

    Carries a corrective action rather than only a message. A client that cannot start
    the server is one of the two failures ``VellisVerification::simpleOperation`` requires
    to be actionable, and a bare exception string is exactly the generic failure it says
    does not pass.
    """

    def __init__(
        self,
        summary: str,
        corrective_action: str,
        *,
        stage: str = ServeStage.OPEN_MEMORY,
        memory_changed: bool | None = False,
    ) -> None:
        super().__init__(summary)
        self.summary = summary
        self.corrective_action = corrective_action
        self.stage = stage
        self.memory_changed = memory_changed


def _reject_non_json_number(spelling: str) -> None:
    """Reject the non-finite constants the standard decoder otherwise accepts."""
    raise ValueError(f"{spelling} is not a JSON number")


def _exact_json_loads(text: str) -> object:
    """Parse one wire message without routing a fractional number through binary float."""
    return json.loads(
        text,
        parse_float=Decimal,
        parse_constant=_reject_non_json_number,
    )


def _exact_json_dumps(value: object) -> str:
    """Encode one protocol value while keeping every finite Decimal a JSON number."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"{value!r} is not a JSON number")
        return str(value)
    if isinstance(value, float):
        return json.dumps(value, allow_nan=False)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, Mapping):
        members: list[str] = []
        for key, member in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"JSON object member name must be a string, not {type(key).__name__}"
                )
            members.append(f"{json.dumps(key, ensure_ascii=False)}:{_exact_json_dumps(member)}")
        return "{" + ",".join(members) + "}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ",".join(_exact_json_dumps(member) for member in value) + "]"
    raise TypeError(f"no JSON wire form for {type(value).__name__}")


def _restore_exact_structured_content(message: object) -> object:
    """Restore structured tool content from its equivalent exact textual form.

    FastMCP normalizes Decimal inside ``structuredContent`` to a string before the
    transport sees the response. Vellis constructs the adjacent text block from the same
    typed result with its exact JSON tokens intact, so that representation is the local
    source for repairing the framework's lossy copy at the final wire boundary.
    """
    if not isinstance(message, Mapping):
        return message
    result = message.get("result")
    if not isinstance(result, Mapping) or "structuredContent" not in result:
        return message
    content = result.get("content")
    if not isinstance(content, Sequence) or isinstance(content, (str, bytes)) or not content:
        return message
    first = content[0]
    if not isinstance(first, Mapping) or first.get("type") != "text":
        return message
    text = first.get("text")
    if not isinstance(text, str):
        return message
    exact = _exact_json_loads(text)
    if not isinstance(exact, Mapping):
        return message
    return {**message, "result": {**result, "structuredContent": exact}}


@asynccontextmanager
async def _exact_stdio_server(
    stdin: anyio.AsyncFile[str] | None = None,
    stdout: anyio.AsyncFile[str] | None = None,
) -> AsyncIterator[
    tuple[
        ContextReceiveStream[SessionMessage | Exception],
        ContextSendStream[SessionMessage],
    ]
]:
    """Use the SDK's safe stdio claim while preserving exact JSON-number tokens."""
    restore_stdin: Callable[[], None] | None = None
    restore_stdout: Callable[[], None] | None = None
    try:
        if stdin is None:
            stdin_buffer, restore_stdin = sdk_stdio._claim_fd(  # pyright: ignore[reportPrivateUsage]
                0,
                sys.stdin,
                "rb",
                sdk_stdio._open_stdin_diversion,  # pyright: ignore[reportPrivateUsage]
            )
            stdin = anyio.wrap_file(
                sdk_stdio._UnownedTextWrapper(  # pyright: ignore[reportPrivateUsage]
                    stdin_buffer, encoding="utf-8", errors="replace"
                )
            )
        if stdout is None:
            stdout_buffer, restore_stdout = sdk_stdio._claim_fd(  # pyright: ignore[reportPrivateUsage]
                1,
                sys.stdout,
                "wb",
                sdk_stdio._open_stdout_diversion,  # pyright: ignore[reportPrivateUsage]
            )
            stdout = anyio.wrap_file(
                sdk_stdio._UnownedTextWrapper(  # pyright: ignore[reportPrivateUsage]
                    stdout_buffer, encoding="utf-8"
                )
            )

        read_writer, read_stream = create_context_streams[SessionMessage | Exception](0)
        write_stream, write_reader = create_context_streams[SessionMessage](0)

        async def read_messages() -> None:
            assert stdin is not None
            try:
                async with read_writer:
                    async for line in stdin:
                        try:
                            raw = _exact_json_loads(line)
                            message = mcp_types.jsonrpc_message_adapter.validate_python(
                                raw, by_name=False
                            )
                        except Exception as error:
                            await read_writer.send(error)
                            continue
                        await read_writer.send(SessionMessage(message))
            except anyio.ClosedResourceError:  # pragma: no cover - transport teardown race
                await anyio.lowlevel.checkpoint()

        async def write_messages() -> None:
            assert stdout is not None
            try:
                async with write_reader:
                    async for session_message in write_reader:
                        raw = session_message.message.model_dump(
                            by_alias=True, exclude_unset=True, mode="python"
                        )
                        await stdout.write(
                            _exact_json_dumps(_restore_exact_structured_content(raw)) + "\n"
                        )
                        await stdout.flush()
            except anyio.ClosedResourceError:  # pragma: no cover - transport teardown race
                await anyio.lowlevel.checkpoint()

        async with anyio.create_task_group() as task_group:
            task_group.start_soon(read_messages)
            task_group.start_soon(write_messages)
            yield read_stream, write_stream
    finally:
        if restore_stdout is not None:
            restore_stdout()
        if restore_stdin is not None:
            restore_stdin()


class _VellisMCP(FastMCP):
    """FastMCP with the exact-number stdio realization Vellis requires."""

    async def run_stdio_async(
        self,
        show_banner: bool = True,
        log_level: str | None = None,
        stateless: bool = False,
    ) -> None:
        if show_banner:
            log_server_banner(server=self)
        token = set_transport("stdio")
        try:
            with temporary_log_level(log_level):
                async with self._lifespan_manager():  # pyright: ignore[reportPrivateUsage]
                    async with _exact_stdio_server() as (read_stream, write_stream):
                        mode = " (stateless)" if stateless else ""
                        logger.info(
                            f"Starting MCP server {self.name!r} with transport 'stdio'{mode}"
                        )
                        await self._mcp_server.run(  # pyright: ignore[reportPrivateUsage]
                            read_stream,
                            write_stream,
                            self._mcp_server.create_initialization_options(  # pyright: ignore[reportPrivateUsage]
                                notification_options=NotificationOptions(tools_changed=True)
                            ),
                        )
        finally:
            reset_transport(token)


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
    server: FastMCP = _VellisMCP(name)
    server.add_middleware(_LegacyAnchorTypeCompatibility())

    def rtg_definition_summary(
        request: DefinitionSummaryRequest,
    ) -> DefinitionSummaryResult:
        """Discover shallow definitions in the selected evaluated state."""
        return _result(
            system.definition_summary(request, provenance=_agent()),
            lambda reason: DefinitionSummaryResult(
                status=OperationStatus.FAILED,
                summary=f"the summary could not be returned completely: {reason}",
                findings=(ValidationFinding(summary=reason),),
            ),
        )

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

    def rtg_definition_delta() -> DefinitionDeltaResult:
        """Retrieve proposal identities, staged counts, and assessment status, or absence."""
        return _result(
            system.definition_delta(provenance=_agent()),
            lambda reason: DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the proposal could not be returned completely: {reason}",
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    def rtg_query(query: GraphQuery) -> GraphQueryResult:
        """Query current, prospective, or historical graph meaning, bounded, with optional totals.

        Rows carry exactly the projections asked for, and identical projected tuples occur
        once. Two objects with the same projected values are therefore one row, so adding
        up a projection does not total the objects — use an aggregation for that, or
        project something unique to each object alongside the values.
        """
        return _result(
            system.query_graph(query, provenance=_agent()),
            lambda reason: GraphQueryResult(
                status=OperationStatus.FAILED,
                summary=f"the result could not be returned completely: {reason}",
                query=query,
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    def rtg_change(request: GraphChangeRequest) -> RevisionedOutcome:
        """Validate explicit upserts and removals, then atomically commit an effective change."""
        return _result(
            system.apply_graph_change(request, provenance=_agent()),
            _unreturnable_outcome,
        )

    def rtg_set_definition_delta(request: SetDefinitionDeltaRequest) -> DefinitionDeltaResult:
        """Apply bounded keyed definition edits to the sole proposal."""
        return _result(
            system.set_definition_delta(request.change, provenance=_agent()),
            lambda reason: DefinitionDeltaResult(
                status=OperationStatus.FAILED,
                summary=f"the assessment could not be returned completely: {reason}",
                findings=(ValidationFinding(summary=reason),),
            ),
        )

    def rtg_activate_definition_delta(
        request: ActivateDefinitionDeltaRequest,
    ) -> RevisionedOutcome:
        """Activate the valid sole proposal atomically or preserve all current canonical state."""
        return _result(
            system.activate_definition_delta(request, provenance=_agent()),
            _unreturnable_outcome,
        )

    def rtg_discard_definition_delta() -> RevisionedOutcome:
        """Discard the sole proposal atomically or report normal absence."""
        return _result(
            system.discard_definition_delta(provenance=_agent()),
            _unreturnable_outcome,
        )

    def rtg_check(request: ValidationRequest) -> ValidationReport:
        """Create or page one complete SQLite-backed conformance assessment."""
        return _result(
            system.check(request, provenance=_agent()),
            lambda reason: ValidationReport(
                scope=request.scope,
                status=OperationStatus.FAILED,
                summary=f"the assessment could not be returned: {reason}",
            ),
        )

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

    # Registered explicitly rather than by decorator so each published schema can be made
    # self-contained before any client sees it. The order is the model's order, and the
    # names come from the functions, so this list and TOOL_NAMES say the same thing.
    for function in (
        rtg_definition_summary,
        rtg_definition_inspect,
        rtg_definition_delta,
        rtg_query,
        rtg_change,
        rtg_set_definition_delta,
        rtg_activate_definition_delta,
        rtg_discard_definition_delta,
        rtg_check,
        rtg_history,
    ):
        registered = server.add_tool(function)
        registered.parameters = _self_contained(registered.parameters)

    return server


class _LegacyAnchorTypeCompatibility(Middleware):
    """Accept the former single-type query spelling at the selected wire boundary.

    ``anchor_types`` remains the one canonical domain member and the only spelling
    discovery publishes. Existing clients that send ``anchor_type`` still mean the
    singleton collection they meant before multi-type groups were introduced. Keeping
    the translation here prevents a retired serialization detail from becoming RTG
    domain state or appearing in returned query objects.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        message = context.message
        if message.name != "rtg_query" or message.arguments is None:
            return await call_next(context)
        query = message.arguments.get("query")
        if not isinstance(query, Mapping):
            return await call_next(context)
        groups = query.get("anchor_groups")
        if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)):
            return await call_next(context)

        changed = False
        compatible_groups: list[object] = []
        for group in groups:
            if (
                isinstance(group, Mapping)
                and "anchor_types" not in group
                and isinstance(group.get("anchor_type"), str)
            ):
                compatible = dict(group)
                compatible["anchor_types"] = [compatible.pop("anchor_type")]
                compatible_groups.append(compatible)
                changed = True
            else:
                compatible_groups.append(group)
        if not changed:
            return await call_next(context)

        compatible_query = dict(query)
        compatible_query["anchor_groups"] = compatible_groups
        compatible_arguments = dict(message.arguments)
        compatible_arguments["query"] = compatible_query
        compatible_message = message.model_copy(update={"arguments": compatible_arguments})
        return await call_next(context.copy(message=compatible_message))


# What a recursive value stands for once it can no longer stand for itself. The real
# constraint on a stored value is the owner's own definitions, which no tool schema could
# express anyway; this says the true and useful thing instead of pretending to a bound.
_ANY_JSON_SCHEMA: dict[str, object] = {
    "description": "Any JSON value: an object, array, string, number, boolean, or null."
}


def _self_contained(schema: dict[str, object]) -> dict[str, object]:
    """Return one input schema carrying no references a client must resolve.

    Recursive definitions are replaced by the permissive value they stand for, because
    they are the reason the rest cannot be inlined. Everything else is inlined as it
    stands. A schema that was already self-contained comes back unchanged.
    """
    definitions = schema.get("$defs")
    if not isinstance(definitions, dict) or not definitions:
        return schema
    recursive = _recursive_definitions(definitions)
    if recursive:
        substituted = cast("dict[str, object]", _without_references(schema, recursive))
        remaining = cast("Mapping[str, object]", substituted.get("$defs", {}))
        # The surviving definitions are the substituted ones. Taking them from the
        # original would put back the very references this just removed, and leave the
        # schema pointing at definitions that are no longer there.
        schema = {
            **substituted,
            "$defs": {
                name: definition for name, definition in remaining.items() if name not in recursive
            },
        }
    return dereference_refs(schema)


def _recursive_definitions(definitions: Mapping[str, object]) -> frozenset[str]:
    """Return the definitions that can be reached from themselves.

    Only these actually block inlining. Replacing every reference would throw away the
    typed meaning of definitions that are perfectly capable of being written out.
    """
    reachable = {name: _referenced_names(definition) for name, definition in definitions.items()}
    recursive: set[str] = set()
    for start in reachable:
        seen: set[str] = set()
        pending = [start]
        while pending:
            for name in reachable.get(pending.pop(), frozenset()):
                if name == start:
                    recursive.add(start)
                    pending.clear()
                    break
                if name not in seen:
                    seen.add(name)
                    pending.append(name)
    return frozenset(recursive)


def _referenced_names(node: object) -> frozenset[str]:
    """Return every local definition name one schema fragment references."""
    if isinstance(node, Mapping):
        found: set[str] = set()
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.startswith("#/$defs/"):
            found.add(reference.removeprefix("#/$defs/"))
        for member in node.values():
            found |= _referenced_names(member)
        return frozenset(found)
    if isinstance(node, (list, tuple)):
        found = set()
        for member in node:
            found |= _referenced_names(member)
        return frozenset(found)
    return frozenset()


def _without_references(node: object, names: frozenset[str]) -> object:
    """Replace references to the named definitions with the permissive value.

    Sibling keywords survive the substitution. Pydantic writes a description or a default
    alongside a reference, and dropping those would lose meaning the caller can use.
    """
    if isinstance(node, Mapping):
        reference = node.get("$ref")
        if isinstance(reference, str) and reference.removeprefix("#/$defs/") in names:
            return {
                **_ANY_JSON_SCHEMA,
                **{key: value for key, value in node.items() if key != "$ref"},
            }
        return {key: _without_references(value, names) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_without_references(member, names) for member in node]
    return node


def _wire(value: object) -> object:
    """Render one result for the wire, preserving JSON kind.

    A number goes out as a number. Fractions that binary float can carry exactly keep the
    ordinary framework form; every other fraction remains Decimal for the exact stdio
    encoder rather than being rounded or turned into text.
    """
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            if abs(value.adjusted()) > MAXIMUM_STORED_INTEGER_EXPONENT:
                raise JsonValueError(f"the number {value} is larger than a stored integer may be")
            return int(value)
        rendered = float(value)
        return rendered if Decimal(repr(rendered)) == value else value
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
    # ToolResult's convenience constructor turns Decimal into a JSON string before the
    # transport can encode it. Give it an already-formed protocol result, whose raw form
    # it preserves, so both representations keep the same exact JSON-number token.
    result = ToolResult.from_mcp_result(
        CallToolResult(
            content=[TextContent(type="text", text=_exact_json_dumps(wired))],
            structured_content=wired,
            is_error=False,
        )
    )
    return cast("T", result)  # pyright: ignore[reportInvalidCast]


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
    starting_position: tuple[int, int] | None = None
    ending_position: tuple[int, int] | None = None
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
        try:
            starting_position = (
                system.store.current_revision(),
                system.store.activity_record_count(),
            )
        except StoreError as error:
            raise ServeError(
                f"the memory at {path} could not report its starting position: {error}",
                "check that this account can read and write that file, and that nothing "
                "else is holding it open",
            ) from error
        build_server(system, name=name).run(transport="stdio")
        try:
            ending_position = (
                system.store.current_revision(),
                system.store.activity_record_count(),
            )
        except StoreError as error:
            raise ServeError(
                f"the server stopped, but its memory could not report its final position: {error}",
                "resolve the reported store problem, then inspect history before restarting",
                stage=ServeStage.CLOSE_MEMORY,
                memory_changed=None,
            ) from error
    except BaseException:
        # Cleanup must not replace the boundary failure that already explains why no
        # service was provided. The connection itself is released before checkpointing,
        # so suppressing only this secondary checkpoint error leaks no live handle.
        try:
            system.close()
        except StoreError:
            pass
        raise
    try:
        system.close()
    except StoreError as error:
        raise ServeError(
            f"the server stopped, but its memory could not finish closing: {error}; "
            "changes already reported as committed remain committed",
            "close the other database reader, then start and stop Vellis once more "
            "before copying the memory file",
            stage=ServeStage.CLOSE_MEMORY,
            memory_changed=(
                starting_position is not None
                and ending_position is not None
                and ending_position != starting_position
            ),
        ) from error
