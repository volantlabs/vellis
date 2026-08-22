"""The selected successor MCP boundary, built only from public FastMCP APIs."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ValidationError as FastMCPValidationError
from fastmcp.tools import Tool, ToolResult
from pydantic import BaseModel, Field, TypeAdapter
from pydantic import ValidationError as PydanticValidationError
from pydantic.json_schema import SkipJsonSchema

from vellis.change_domain import (
    DraftCategory,
    DraftChangeRequest,
    DraftInspectionRequest,
    DraftOperation,
    ValidationRequest,
    ValidationScope,
)
from vellis.change_operations import apply_graph_change
from vellis.discovery_operations import type_inspect, type_summary
from vellis.domain import PUBLIC_ITEM_LIMIT, GraphChangeRequest
from vellis.draft_inspection_operations import inspect_draft
from vellis.draft_operations import activate_draft, change_draft, discard_draft, validate_state
from vellis.history_domain import HistoryKind, HistoryRequest
from vellis.history_operations import inspect_history
from vellis.mcp_models import (
    CanonicalUuid,
    DefinitionInput,
    DraftInspectContinuationInput,
    DraftInspectFreshInput,
    DraftInspectInput,
    HistoryRangeInput,
    ObjectUpsertInput,
    OmissibleArgument,
    QuerySelectionInput,
    StateInput,
    Utf8Text,
    ValidateContinuationInput,
    ValidateFreshInput,
    ValidateInput,
)
from vellis.public_wire import public_result
from vellis.query_domain import GraphQuery
from vellis.read_operations import query_graph

TOOL_NAMES = (
    "rtg_type_summary",
    "rtg_type_inspect",
    "rtg_query",
    "rtg_change",
    "rtg_draft_inspect",
    "rtg_draft_change",
    "rtg_validate",
    "rtg_draft_activate",
    "rtg_draft_discard",
    "rtg_history",
)
HistoryKindInput = Literal["canonical", "activity"]
_OMITTED_ARGUMENT = Field(default_factory=lambda: None)

INSTRUCTIONS = """Begin with rtg_type_summary, then inspect only relevant type neighborhoods.
Use rtg_query identities directly for known UUIDs and pattern for connected graph questions; request
only needed properties and narrow maxMatches when a result is too broad. Active personal-context
mutation assumes owner approval in the surrounding workflow. A draft is one bucket of changes:
inspect it, query state draft, validate it, then activate or discard it. There is no match/get
sequence, draft status or version, assessment identity, or activation token."""


def build_server(database_path: Path) -> FastMCP:
    server = FastMCP(
        "Vellis",
        instructions=INSTRUCTIONS,
        version="2.0.0",
        dereference_schemas=True,
        strict_input_validation=True,
        mask_error_details=False,
    )
    for name, description, factory in _TOOL_FACTORIES:
        if name == "rtg_draft_inspect":
            server.add_tool(_draft_inspect_conditional_tool(database_path, description))
        elif name == "rtg_validate":
            server.add_tool(_validate_conditional_tool(database_path, description))
        else:
            assert factory is not None
            server.tool(name=name, description=description)(factory(database_path))
    return server


class _ConditionalTool(Tool):
    """A public FastMCP tool whose wire request is one of two closed shapes."""

    adapter: SkipJsonSchema[Any]
    operation: SkipJsonSchema[Any]

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            request = self.adapter.validate_python(arguments)
        except PydanticValidationError as error:
            raise FastMCPValidationError(str(error)) from error
        return self.convert_result(self.operation(request))


def _one_of_schema(*models: type[BaseModel]) -> dict[str, object]:
    return {"oneOf": [model.model_json_schema(by_alias=True) for model in models]}


def _draft_inspect_conditional_tool(database_path: Path, description: str) -> Tool:
    def operation(value: object) -> dict[str, object]:
        if isinstance(value, DraftInspectFreshInput):
            request = DraftInspectionRequest(
                tuple(DraftCategory(item) for item in value.categories),
                tuple(DraftOperation(item) for item in value.operations),
                tuple(value.type_keys),
                tuple(value.uuids),
                value.limit,
                None,
            )
        else:
            assert isinstance(value, DraftInspectContinuationInput)
            request = DraftInspectionRequest((), (), (), (), None, value.cursor)
        return public_result(inspect_draft(database_path, request))

    return _ConditionalTool(
        name="rtg_draft_inspect",
        description=description,
        parameters=_one_of_schema(DraftInspectFreshInput, DraftInspectContinuationInput),
        output_schema={"type": "object", "additionalProperties": True},
        adapter=TypeAdapter(DraftInspectInput),
        operation=operation,
    )


def _validate_conditional_tool(database_path: Path, description: str) -> Tool:
    def operation(value: object) -> dict[str, object]:
        if isinstance(value, ValidateFreshInput):
            request = ValidationRequest(ValidationScope(value.scope), value.limit, None)
        else:
            assert isinstance(value, ValidateContinuationInput)
            request = ValidationRequest(ValidationScope(value.scope), None, value.cursor)
        return public_result(validate_state(database_path, request))

    return _ConditionalTool(
        name="rtg_validate",
        description=description,
        parameters=_one_of_schema(ValidateFreshInput, ValidateContinuationInput),
        output_schema={"type": "object", "additionalProperties": True},
        adapter=TypeAdapter(ValidateInput),
        operation=operation,
    )


def _type_summary_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool(
        state: OmissibleArgument[StateInput] = _OMITTED_ARGUMENT,
    ) -> dict[str, object]:
        selected = None if state is None else state.domain()
        return public_result(type_summary(database_path, selected))

    return tool


def _type_inspect_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool(
        anchorTypeKeys: Annotated[
            list[Utf8Text], Field(min_length=1, max_length=PUBLIC_ITEM_LIMIT)
        ],
        state: OmissibleArgument[StateInput] = _OMITTED_ARGUMENT,
        includeLegacySystem: bool = False,
    ) -> dict[str, object]:
        selected = None if state is None else state.domain()
        result = type_inspect(
            database_path,
            tuple(anchorTypeKeys),
            state_selection=selected,
            include_legacy_system=includeLegacySystem,
        )
        return public_result(result)

    return tool


def _query_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool(
        selection: QuerySelectionInput,
        state: OmissibleArgument[StateInput] = _OMITTED_ARGUMENT,
    ) -> dict[str, object]:
        selected = None if state is None else state.domain()
        return public_result(query_graph(database_path, GraphQuery(selection.domain(), selected)))

    return tool


def _change_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool(
        expectedRevision: Annotated[int, Field(ge=0)],
        upserts: Annotated[tuple[ObjectUpsertInput, ...], Field(max_length=PUBLIC_ITEM_LIMIT)] = (),
        removeUuids: Annotated[tuple[CanonicalUuid, ...], Field(max_length=PUBLIC_ITEM_LIMIT)] = (),
    ) -> dict[str, object]:
        request = GraphChangeRequest(
            expectedRevision,
            tuple(value.domain() for value in upserts),
            tuple(removeUuids),
        )
        return public_result(apply_graph_change(database_path, request))

    return tool


def _draft_change_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool(
        definitionUpserts: Annotated[
            tuple[DefinitionInput, ...], Field(max_length=PUBLIC_ITEM_LIMIT)
        ] = (),
        definitionRemovals: Annotated[
            tuple[Utf8Text, ...], Field(max_length=PUBLIC_ITEM_LIMIT)
        ] = (),
        unstageDefinitionKeys: Annotated[
            tuple[Utf8Text, ...], Field(max_length=PUBLIC_ITEM_LIMIT)
        ] = (),
        objectUpserts: Annotated[
            tuple[ObjectUpsertInput, ...], Field(max_length=PUBLIC_ITEM_LIMIT)
        ] = (),
        objectRemovals: Annotated[
            tuple[CanonicalUuid, ...], Field(max_length=PUBLIC_ITEM_LIMIT)
        ] = (),
        unstageObjectUuids: Annotated[
            tuple[CanonicalUuid, ...], Field(max_length=PUBLIC_ITEM_LIMIT)
        ] = (),
    ) -> dict[str, object]:
        request = DraftChangeRequest(
            tuple(value.domain() for value in definitionUpserts),
            tuple(definitionRemovals),
            tuple(unstageDefinitionKeys),
            tuple(value.domain() for value in objectUpserts),
            tuple(objectRemovals),
            tuple(unstageObjectUuids),
        )
        return public_result(change_draft(database_path, request))

    return tool


def _activate_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool() -> dict[str, object]:
        return public_result(activate_draft(database_path))

    return tool


def _discard_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool() -> dict[str, object]:
        return public_result(discard_draft(database_path))

    return tool


def _history_tool(database_path: Path) -> Callable[..., dict[str, object]]:
    def tool(
        ledger: HistoryKindInput,
        maximumRecords: Annotated[int, Field(ge=1, le=PUBLIC_ITEM_LIMIT)],
        range: OmissibleArgument[HistoryRangeInput] = _OMITTED_ARGUMENT,
        includeVerbose: bool = False,
    ) -> dict[str, object]:
        selected_range = None if range is None else range.domain()
        request = HistoryRequest(
            HistoryKind(ledger),
            maximumRecords,
            selected_range,
            includeVerbose,
        )
        return public_result(inspect_history(database_path, request))

    return tool


_TOOL_FACTORIES = (
    ("rtg_type_summary", "Discover every shallow anchor type.", _type_summary_tool),
    (
        "rtg_type_inspect",
        "Inspect complete focused neighborhoods for selected anchor type keys.",
        _type_inspect_tool,
    ),
    (
        "rtg_query",
        "Select known UUIDs or bounded connected patterns and hydrate requested properties.",
        _query_tool,
    ),
    (
        "rtg_change",
        "Apply one field-patch/removal batch after surrounding owner approval.",
        _change_tool,
    ),
    (
        "rtg_draft_inspect",
        "Inspect filtered raw draft deltas and their mechanically composed effect.",
        None,
    ),
    (
        "rtg_draft_change",
        "Stage or unstage definition replacements and graph field deltas.",
        _draft_change_tool,
    ),
    ("rtg_validate", "Return current cleanliness and pageable findings.", None),
    ("rtg_draft_activate", "Freshly validate and publish the draft.", _activate_tool),
    ("rtg_draft_discard", "Explicitly discard the current draft.", _discard_tool),
    ("rtg_history", "Read one complete bounded ledger interval.", _history_tool),
)
