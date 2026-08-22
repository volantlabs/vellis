"""Public-boundary evidence for the Phase 7 successor."""

from __future__ import annotations

import asyncio
import os
import socket
import sqlite3
import subprocess
import sys
import time
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import cast, get_args, get_type_hints

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from fastmcp.exceptions import ToolError
from pydantic import ValidationError as PydanticValidationError

import vellis.__main__ as main_module
import vellis.change_domain as change_domain
import vellis.domain as domain
import vellis.history_domain as history_domain
import vellis.mcp_models as wire_models
import vellis.public_wire as public_wire
import vellis.query_domain as query_domain
from vellis.__main__ import EXIT_FAILED, EXIT_SUCCESS, main
from vellis.audit import audit_database
from vellis.backup_operations import backup_database
from vellis.change_operations import apply_graph_change
from vellis.mcp import TOOL_NAMES, build_server
from vellis.onboarding import (
    ClientKind,
    CommandResult,
    RegistrationResult,
    TransportKind,
    add_command,
    entry_exists,
    register_client,
    resolve_vellis_executable,
)
from vellis.operations import initialize_blank, initialize_with_definitions
from vellis.server import BearerMiddleware, read_http_token, serve_http, write_new_http_token
from vellis.settings_operations import HttpTokenChangedError
from vellis.starter import everyday_life_starter

UUID = "00000000-0000-4000-8000-000000000001"


def _missing_entry_result(client: ClientKind) -> CommandResult:
    diagnostic = (
        "Error: No MCP server named 'vellis' found."
        if client is ClientKind.CODEX
        else 'No MCP server named "vellis". Configured servers: another-server'
    )
    return CommandResult(
        1,
        stderr=diagnostic,
    )


def _content(result) -> dict[str, object]:
    assert isinstance(result.structured_content, dict)
    return result.structured_content


def _nested_dataclass_types(annotation: object):
    if isinstance(annotation, type) and is_dataclass(annotation):
        yield annotation
    for member in get_args(annotation):
        yield from _nested_dataclass_types(member)


def _nullable_public_result_fields() -> set[str]:
    pending = [
        domain.OperationOutcome,
        query_domain.QueryResult,
        query_domain.TypeSummaryResult,
        query_domain.TypeInspectionResult,
        change_domain.DraftChangeResult,
        change_domain.DraftInspectionResult,
        change_domain.ValidationResult,
        history_domain.HistoryResult,
    ]
    seen: set[type] = set()
    nullable: set[str] = set()
    while pending:
        owner = pending.pop()
        if owner in seen:
            continue
        seen.add(owner)
        hints = get_type_hints(owner)
        for item in fields(owner):
            annotation = hints[item.name]
            if type(None) in get_args(annotation):
                nullable.add(f"{owner.__module__}.{owner.__qualname__}.{item.name}")
            pending.extend(
                value for value in _nested_dataclass_types(annotation) if value not in seen
            )
    return nullable


def test_every_nullable_public_result_field_has_one_projection_policy() -> None:
    omitted = public_wire._OMITTED_NULL_FIELDS
    required = public_wire._REQUIRED_NULL_FIELDS
    assert omitted.isdisjoint(required)
    assert _nullable_public_result_fields() == omitted | required


def test_optional_result_members_omit_while_user_null_remains_json_null() -> None:
    finding = domain.Finding(domain.FindingCode.MISSING, "missing")
    rejected = public_wire.public_result(
        domain.OperationOutcome(domain.OperationStatus.REJECTED, "rejected", (finding,))
    )
    assert rejected["findings"] == [{"code": "missing", "summary": "missing"}]
    assert "evaluatedRevision" not in rejected
    assert "resultingRevision" not in rejected

    property_definition = domain.PropertyDefinition("value", "Value", domain.ValueKind.TEXT)
    projected_definition = public_wire.public_result(property_definition)
    for name in (
        "allowedValues",
        "minimum",
        "maximum",
        "minimumLength",
        "maximumLength",
        "pattern",
    ):
        assert name not in projected_definition

    hydrated = query_domain.HydratedObject(
        UUID,
        domain.ObjectKind.ASSOCIATED_DATA,
        "wire.details",
        None,
        ("00000000-0000-4000-8000-000000000002",),
        None,
        None,
        (("value", None),),
        None,
    )
    projected_query = public_wire.public_result(
        query_domain.QueryResult(
            domain.OperationStatus.ACCEPTED,
            "selected",
            (),
            0,
            query_domain.IdentityQueryPayload((UUID,), (), (hydrated,)),
        )
    )
    projected_objects = cast(dict[str, dict[str, object]], projected_query["objects"])
    projected_object = projected_objects[UUID]
    assert projected_object["properties"] == {"value": None}
    assert "displayName" not in projected_object
    assert "sourceUuid" not in projected_object
    assert "targetUuid" not in projected_object
    assert "system" not in projected_object


@pytest.fixture
def database(tmp_path: Path) -> Path:
    value = tmp_path / "memory" / "vellis.sqlite3"
    initialize_blank(value)
    return value


@pytest.fixture
def starter_database(tmp_path: Path) -> Path:
    value = tmp_path / "starter" / "vellis.sqlite3"
    initialize_with_definitions(value, everyday_life_starter())
    return value


async def _exercise_enum_and_conditional_wire(client: Client) -> None:
    summary = await client.call_tool(
        "rtg_type_summary", {"state": {"kind": "revision", "revision": 0}}
    )
    assert _content(summary)["status"] == "accepted"
    query = await client.call_tool(
        "rtg_query",
        {
            "selection": {
                "kind": "pattern",
                "maxMatches": 10,
                "nodes": [
                    {
                        "name": "task",
                        "kind": "anchor",
                        "typeKeys": ["life.task"],
                        "predicates": [
                            {
                                "field": {"kind": "displayName"},
                                "operator": "prefix",
                                "value": "A",
                            }
                        ],
                    },
                    {"name": "area", "kind": "anchor", "typeKeys": ["life.area"]},
                ],
                "directAssociations": [],
                "links": [
                    {
                        "name": "belongs",
                        "source": "task",
                        "target": "area",
                        "typeKeys": ["life.belongs_to"],
                    }
                ],
            }
        },
    )
    assert _content(query)["matches"] == []
    staged = await client.call_tool(
        "rtg_draft_change",
        {
            "definitionUpserts": [
                {"kind": "anchor", "typeKey": "wire.anchor", "description": "Wire anchor"},
                {
                    "kind": "associatedData",
                    "typeKey": "wire.details",
                    "description": "Wire details",
                    "permittedAnchorTypeKeys": ["wire.anchor"],
                    "properties": [
                        {
                            "name": "when",
                            "description": "A date",
                            "valueKind": "date",
                            "nullable": True,
                        },
                        {
                            "name": "label",
                            "description": "A label",
                            "valueKind": "text",
                        },
                    ],
                    "anchorsPerObject": {"minimum": 1, "maximum": 1},
                    "objectsPerAnchor": {"minimum": 0, "maximum": 1},
                },
            ]
        },
    )
    assert _content(staged)["draftPresent"] is True
    await _exercise_every_predicate_operator(client)
    inspected = await client.call_tool(
        "rtg_draft_inspect", {"categories": ["definitions"], "limit": 1}
    )
    entries = list(cast(list[dict[str, object]], _content(inspected)["entries"]))
    cursor = _content(inspected).get("cursor")
    while cursor is not None:
        inspected = await client.call_tool("rtg_draft_inspect", {"cursor": cursor})
        entries.extend(cast(list[dict[str, object]], _content(inspected)["entries"]))
        cursor = _content(inspected).get("cursor")
    added = next(entry for entry in entries if entry["key"] == "wire.anchor")
    assert "current" in added and added["current"] is None
    proposed = cast(dict[str, object], added["proposed"])
    assert proposed["typeKey"] == "wire.anchor"
    validated = await client.call_tool("rtg_validate", {"scope": "draft", "limit": 10})
    assert _content(validated)["clean"] is True
    await client.call_tool("rtg_draft_change", {"definitionRemovals": ["life.area"]})
    removed_page = await client.call_tool(
        "rtg_draft_inspect", {"categories": ["definitions"], "limit": 1}
    )
    removed_entries = list(cast(list[dict[str, object]], _content(removed_page)["entries"]))
    cursor = _content(removed_page).get("cursor")
    while cursor is not None:
        removed_page = await client.call_tool("rtg_draft_inspect", {"cursor": cursor})
        removed_entries.extend(cast(list[dict[str, object]], _content(removed_page)["entries"]))
        cursor = _content(removed_page).get("cursor")
    removed = next(entry for entry in removed_entries if entry["key"] == "life.area")
    current = cast(dict[str, object], removed["current"])
    assert current["typeKey"] == "life.area"
    assert "proposed" in removed and removed["proposed"] is None
    history = await client.call_tool(
        "rtg_history",
        {
            "ledger": "canonical",
            "range": {"kind": "sequence", "through": 0},
            "maximumRecords": 10,
        },
    )
    assert _content(history)["headSequence"] == 0
    await client.call_tool("rtg_draft_discard", {})
    unresolved = await client.call_tool(
        "rtg_draft_change",
        {
            "definitionUpserts": [
                {
                    "kind": "associatedData",
                    "typeKey": "wire.unresolved",
                    "description": "Structurally valid unresolved definition",
                    "permittedAnchorTypeKeys": ["wire.missing"],
                    "properties": [],
                    "anchorsPerObject": {"minimum": 1},
                    "objectsPerAnchor": {"minimum": 0},
                }
            ]
        },
    )
    assert _content(unresolved)["status"] == "accepted"
    dirty = await client.call_tool("rtg_validate", {"scope": "draft", "limit": 10})
    assert _content(dirty)["clean"] is False
    await client.call_tool("rtg_draft_discard", {})


async def _exercise_every_predicate_operator(client: Client) -> None:
    date = {"kind": "date", "value": "2026-01-01"}
    predicates = [
        *(
            {"field": {"kind": "property", "name": "when"}, "operator": operator}
            for operator in ("present", "missing", "isNull", "isNotNull")
        ),
        *(
            {
                "field": {"kind": "property", "name": "when"},
                "operator": operator,
                "value": date,
            }
            for operator in (
                "equal",
                "notEqual",
                "lessThan",
                "lessThanOrEqual",
                "greaterThan",
                "greaterThanOrEqual",
            )
        ),
        {
            "field": {"kind": "property", "name": "when"},
            "operator": "anyOf",
            "values": [date, {"kind": "null", "value": None}],
        },
        *(
            {
                "field": {"kind": "property", "name": "label"},
                "operator": operator,
                "value": "alpha",
            }
            for operator in ("contains", "prefix", "regex")
        ),
        *(
            {
                "field": {"kind": "property", "name": "label"},
                "operator": operator,
                "terms": ["alpha"],
            }
            for operator in ("allTerms", "anyTerms")
        ),
        {
            "field": {"kind": "property", "name": "label"},
            "operator": "phrase",
            "phrase": "alpha beta",
        },
    ]
    for predicate in predicates:
        result = await client.call_tool(
            "rtg_query",
            {
                "state": {"kind": "draft"},
                "selection": {
                    "kind": "pattern",
                    "maxMatches": 10,
                    "nodes": [
                        {
                            "name": "data",
                            "kind": "associatedData",
                            "typeKeys": ["wire.details"],
                            "predicates": [predicate],
                        }
                    ],
                    "directAssociations": [],
                    "links": [],
                },
            },
        )
        assert _content(result)["status"] == "accepted"


async def _reject_malformed_canonical_values(client: Client) -> None:
    malformed = [
        (
            "rtg_query",
            {"selection": {"kind": "identities", "objects": [{"uuid": "not-a-uuid"}]}},
        ),
        ("rtg_change", {"expectedRevision": 0, "removeUuids": ["not-a-uuid"]}),
        (
            "rtg_type_summary",
            {"state": {"kind": "time", "timestamp": "2026-01-01T00:00:00"}},
        ),
        (
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [
                    {
                        "kind": "associatedData",
                        "uuid": UUID,
                        "typeKey": "missing",
                        "anchorUuids": ["00000000-0000-4000-8000-000000000002"],
                        "setProperties": {"when": {"kind": "date", "value": "2026-02-30"}},
                    }
                ],
            },
        ),
        (
            "rtg_history",
            {
                "ledger": "canonical",
                "range": {"kind": "time", "start": "2026-00-01T00:00:00Z"},
                "maximumRecords": 10,
            },
        ),
    ]
    malformed.extend(("rtg_query", value) for value in _malformed_predicate_queries())
    malformed.extend(("rtg_draft_change", value) for value in _malformed_definition_changes())
    malformed.extend(_direct_null_requests()[::5])
    for name, arguments in malformed:
        with pytest.raises(ToolError):
            await client.call_tool(name, arguments)


def _malformed_predicate_queries() -> list[dict[str, object]]:
    predicates = (
        {"field": {"kind": "property", "name": "x"}, "operator": "present", "value": "x"},
        {"field": {"kind": "displayName"}, "operator": "present"},
        {"field": {"kind": "displayName"}, "operator": "equal"},
        {
            "field": {"kind": "displayName"},
            "operator": "equal",
            "value": {"kind": "text", "value": "x"},
            "caseSensitive": True,
        },
        {"field": {"kind": "displayName"}, "operator": "anyOf", "values": []},
        {"field": {"kind": "displayName"}, "operator": "contains", "terms": ["x"]},
        {"field": {"kind": "displayName"}, "operator": "allTerms", "terms": []},
        {"field": {"kind": "displayName"}, "operator": "phrase", "phrase": ""},
        {
            "field": {"kind": "displayName"},
            "operator": "lessThan",
            "value": {"kind": "null", "value": None},
        },
        *(
            {
                "field": {"kind": "displayName"},
                "operator": operator,
                "value": {"kind": "null", "value": None},
            }
            for operator in ("equal", "notEqual")
        ),
    )
    return [
        {
            "selection": {
                "kind": "pattern",
                "maxMatches": 10,
                "nodes": [
                    {
                        "name": "item",
                        "kind": "anchor",
                        "predicates": [predicate],
                    }
                ],
                "directAssociations": [],
                "links": [],
            }
        }
        for predicate in predicates
    ]


def _direct_null_requests() -> list[tuple[str, dict[str, object]]]:
    identity = {"kind": "identities", "objects": [{"uuid": UUID}]}
    pattern_node = {
        "name": "item",
        "kind": "anchor",
    }
    pattern = {
        "kind": "pattern",
        "maxMatches": 10,
        "nodes": [pattern_node],
        "directAssociations": [],
        "links": [],
    }
    definition = {
        "kind": "associatedData",
        "typeKey": "null.data",
        "description": "Null checks",
        "permittedAnchorTypeKeys": ["null.anchor"],
        "properties": [{"name": "value", "description": "Value", "valueKind": "text"}],
        "anchorsPerObject": {"minimum": 1},
        "objectsPerAnchor": {"minimum": 0},
    }

    def property_member(name: str) -> tuple[str, dict[str, object]]:
        value = {
            **definition,
            "properties": [
                {
                    "name": "value",
                    "description": "Value",
                    "valueKind": "text",
                    name: None,
                }
            ],
        }
        return "rtg_draft_change", {"definitionUpserts": [value]}

    def node_member(name: str) -> tuple[str, dict[str, object]]:
        return "rtg_query", {"selection": {**pattern, "nodes": [{**pattern_node, name: None}]}}

    return [
        ("rtg_type_summary", {"state": None}),
        ("rtg_type_inspect", {"anchorTypeKeys": ["x"], "state": None}),
        (
            "rtg_type_inspect",
            {"anchorTypeKeys": ["x"], "includeLegacySystem": None},
        ),
        ("rtg_query", {"selection": identity, "state": None}),
        (
            "rtg_query",
            {
                "selection": {
                    "kind": "identities",
                    "objects": [{"uuid": UUID, "properties": None}],
                }
            },
        ),
        (
            "rtg_query",
            {
                "selection": {
                    "kind": "identities",
                    "objects": [{"uuid": UUID, "includeLegacySystem": None}],
                }
            },
        ),
        node_member("typeKeys"),
        node_member("uuids"),
        node_member("properties"),
        node_member("predicates"),
        node_member("includeLegacySystem"),
        ("rtg_query", {"selection": {**pattern, "directAssociations": None}}),
        ("rtg_query", {"selection": {**pattern, "links": None}}),
        (
            "rtg_query",
            {
                "selection": {
                    **pattern,
                    "nodes": [
                        {
                            **pattern_node,
                            "predicates": [
                                {
                                    "field": {"kind": "displayName"},
                                    "operator": "contains",
                                    "value": "x",
                                    "caseSensitive": None,
                                }
                            ],
                        }
                    ],
                }
            },
        ),
        (
            "rtg_query",
            {
                "selection": {
                    **pattern,
                    "nodes": [
                        {"name": "source", "kind": "anchor"},
                        {"name": "target", "kind": "anchor"},
                    ],
                    "links": [
                        {
                            "name": "edge",
                            "source": "source",
                            "target": "target",
                            "typeKeys": None,
                        }
                    ],
                }
            },
        ),
        (
            "rtg_query",
            {
                "selection": {
                    **pattern,
                    "nodes": [
                        {"name": "source", "kind": "anchor"},
                        {"name": "target", "kind": "anchor"},
                    ],
                    "links": [
                        {
                            "name": "edge",
                            "source": "source",
                            "target": "target",
                            "includeLegacySystem": None,
                        }
                    ],
                }
            },
        ),
        (
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [{"kind": "anchor", "uuid": UUID, "typeKey": None}],
            },
        ),
        ("rtg_change", {"expectedRevision": 0, "upserts": None}),
        ("rtg_change", {"expectedRevision": 0, "removeUuids": None}),
        (
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [{"kind": "anchor", "uuid": UUID, "displayName": None}],
            },
        ),
        (
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [{"kind": "associatedData", "uuid": UUID, "anchorUuids": None}],
            },
        ),
        *(
            (
                "rtg_change",
                {
                    "expectedRevision": 0,
                    "upserts": [{"kind": "associatedData", "uuid": UUID, name: None}],
                },
            )
            for name in (
                "addAnchorUuids",
                "removeAnchorUuids",
                "setProperties",
                "removeProperties",
            )
        ),
        (
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [{"kind": "link", "uuid": UUID, "sourceUuid": None}],
            },
        ),
        (
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [{"kind": "link", "uuid": UUID, "targetUuid": None}],
            },
        ),
        (
            "rtg_draft_change",
            {
                "definitionUpserts": [
                    {**definition, "anchorsPerObject": {"minimum": 1, "maximum": None}}
                ]
            },
        ),
        *(
            ("rtg_draft_change", {name: None})
            for name in (
                "definitionUpserts",
                "definitionRemovals",
                "unstageDefinitionKeys",
                "objectUpserts",
                "objectRemovals",
                "unstageObjectUuids",
            )
        ),
        *(
            property_member(name)
            for name in (
                "allowedValues",
                "minimum",
                "maximum",
                "minimumLength",
                "maximumLength",
                "pattern",
            )
        ),
        ("rtg_draft_inspect", {"categories": None, "limit": 10}),
        ("rtg_draft_inspect", {"operations": None, "limit": 10}),
        ("rtg_draft_inspect", {"typeKeys": None, "limit": 10}),
        ("rtg_draft_inspect", {"uuids": None, "limit": 10}),
        ("rtg_draft_inspect", {"cursor": None}),
        ("rtg_validate", {"scope": "current", "cursor": None}),
        ("rtg_history", {"ledger": "canonical", "maximumRecords": 10, "range": None}),
        (
            "rtg_history",
            {"ledger": "canonical", "maximumRecords": 10, "includeVerbose": None},
        ),
        (
            "rtg_history",
            {
                "ledger": "canonical",
                "maximumRecords": 10,
                "range": {"kind": "time", "start": None},
            },
        ),
        (
            "rtg_history",
            {
                "ledger": "canonical",
                "maximumRecords": 10,
                "range": {"kind": "time", "end": None},
            },
        ),
        (
            "rtg_history",
            {
                "ledger": "canonical",
                "maximumRecords": 10,
                "range": {"kind": "sequence", "after": None},
            },
        ),
        (
            "rtg_history",
            {
                "ledger": "canonical",
                "maximumRecords": 10,
                "range": {"kind": "sequence", "through": None},
            },
        ),
    ]


def _dirty_definition_cases() -> list[tuple[dict[str, object], str, str]]:
    def integer(value: int) -> dict[str, object]:
        return {"kind": "integer", "value": value}

    def text(value: str) -> dict[str, object]:
        return {"kind": "text", "value": value}

    prop: dict[str, object] = {
        "name": "value",
        "description": "Value",
        "valueKind": "integer",
    }
    data: dict[str, object] = {
        "kind": "associatedData",
        "typeKey": "audit.data",
        "description": "Data",
        "permittedAnchorTypeKeys": ["audit.anchor"],
        "properties": [prop],
        "anchorsPerObject": {"minimum": 1, "maximum": 1},
        "objectsPerAnchor": {"minimum": 0, "maximum": 1},
    }
    link: dict[str, object] = {
        "kind": "link",
        "typeKey": "audit.link",
        "description": "Link",
        "permittedSourceTypeKeys": ["audit.anchor"],
        "permittedTargetTypeKeys": ["audit.anchor"],
        "linksPerSource": {"minimum": 0},
        "linksPerTarget": {"minimum": 0},
    }
    anchor: dict[str, object] = {
        "kind": "anchor",
        "typeKey": "audit.anchor",
        "description": "Anchor",
    }

    def changed(base: dict[str, object], **members: object) -> dict[str, object]:
        value = dict(base)
        value.update(members)
        return {"definitionUpserts": [anchor, value]}

    def changed_property(**members: object) -> dict[str, object]:
        value = dict(prop)
        value.update(members)
        return changed(data, properties=[value])

    return [
        (
            {"definitionUpserts": [{"kind": "anchor", "typeKey": "", "description": "A"}]},
            "missing",
            "/typeKey",
        ),
        (
            {
                "definitionUpserts": [
                    {"kind": "anchor", "typeKey": "audit.anchor", "description": ""}
                ]
            },
            "missing",
            "/description",
        ),
        (changed(data, permittedAnchorTypeKeys=[]), "missing", "/permittedAnchorTypeKeys"),
        (changed_property(name=""), "missing", "/name"),
        (changed_property(allowedValues=[]), "invalidValue", "/allowedValues"),
        (changed_property(allowedValues=[text("wrong")]), "kindMismatch", "/allowedValues/0"),
        (changed_property(minimum=text("wrong")), "kindMismatch", "/minimum"),
        (
            changed_property(minimum=integer(2), maximum=integer(1)),
            "invalidValue",
            "/properties/value",
        ),
        (changed_property(minimumLength=2), "invalidValue", "/properties/value"),
        (
            changed_property(valueKind="text", minimumLength=2, maximumLength=1),
            "invalidValue",
            "/properties/value",
        ),
        (
            changed_property(valueKind="text", minimumLength=2, allowedValues=[text("x")]),
            "constraintViolation",
            "/allowedValues/0",
        ),
        (
            changed_property(valueKind="text", pattern="a+", allowedValues=[text("b")]),
            "constraintViolation",
            "/allowedValues/0",
        ),
        (
            changed_property(valueKind="text", minimumLength=-1),
            "invalidValue",
            "/minimumLength",
        ),
        (changed_property(valueKind="text", pattern="("), "invalidValue", "/pattern"),
        (
            changed(data, anchorsPerObject={"minimum": 0, "maximum": 1}),
            "invalidValue",
            "/anchorsPerObject/minimum",
        ),
        (changed(link, permittedSourceTypeKeys=[]), "missing", "/permittedSourceTypeKeys"),
    ]


def _dirty_definition_changes() -> list[dict[str, object]]:
    return [arguments for arguments, _, _ in _dirty_definition_cases()]


def _malformed_definition_changes() -> list[dict[str, object]]:
    base = {
        "kind": "associatedData",
        "typeKey": "malformed.data",
        "description": "Malformed",
        "permittedAnchorTypeKeys": ["anchor"],
        "properties": [],
        "anchorsPerObject": {"minimum": 1},
        "objectsPerAnchor": {"minimum": 0},
    }

    def changed(**members: object) -> dict[str, object]:
        value = dict(base)
        value.update(members)
        return {"definitionUpserts": [value]}

    return [
        changed(description=3),
        changed(unknown=True),
        changed(kind="unknown"),
        changed(permittedAnchorTypeKeys=["anchor", "anchor"]),
        changed(
            properties=[
                {"name": "value", "description": "Value", "valueKind": "integer"},
                {"name": "value", "description": "Value", "valueKind": "integer"},
            ]
        ),
        changed(
            properties=[
                {
                    "name": "value",
                    "description": "Value",
                    "valueKind": "integer",
                    "allowedValues": [
                        {"kind": "integer", "value": 1},
                        {"kind": "integer", "value": 1},
                    ],
                }
            ]
        ),
        changed(anchorsPerObject={"minimum": -1}),
        changed(objectsPerAnchor={"minimum": 2, "maximum": 1}),
        changed(
            properties=[
                {
                    "name": "value",
                    "description": "Value",
                    "valueKind": "integer",
                    "allowedValues": [{"kind": "integer", "value": 9_007_199_254_740_992}],
                }
            ]
        ),
        changed(
            properties=[
                {
                    "name": "value",
                    "description": "Value",
                    "valueKind": "number",
                    "allowedValues": [{"kind": "number", "value": float("inf")}],
                }
            ]
        ),
        changed(
            properties=[
                {
                    "name": "value",
                    "description": "Value",
                    "valueKind": "date",
                    "allowedValues": [{"kind": "date", "value": "2026-02-30"}],
                }
            ]
        ),
    ]


@pytest.mark.anyio
async def test_public_server_lists_strict_selected_tools_and_calls_successor(
    database: Path,
) -> None:
    async with Client(build_server(database)) as client:
        tools = await client.list_tools()
        summary = await client.call_tool("rtg_type_summary", {})
        changed = await client.call_tool(
            "rtg_change",
            {
                "expectedRevision": 0,
                "upserts": [
                    {
                        "kind": "anchor",
                        "uuid": UUID,
                        "typeKey": "missing.type",
                        "displayName": "Ada",
                    }
                ],
            },
        )
    assert tuple(value.name for value in tools) == TOOL_NAMES
    assert all(
        value.inputSchema.get("additionalProperties") is False or "oneOf" in value.inputSchema
        for value in tools
    )
    expected_properties = {
        "rtg_type_summary": {"state"},
        "rtg_type_inspect": {"anchorTypeKeys", "state", "includeLegacySystem"},
        "rtg_query": {"selection", "state"},
        "rtg_change": {"expectedRevision", "upserts", "removeUuids"},
        "rtg_draft_inspect": {"categories", "operations", "typeKeys", "uuids", "limit", "cursor"},
        "rtg_draft_change": {
            "definitionUpserts",
            "definitionRemovals",
            "unstageDefinitionKeys",
            "objectUpserts",
            "objectRemovals",
            "unstageObjectUuids",
        },
        "rtg_validate": {"scope", "limit", "cursor"},
        "rtg_draft_activate": set(),
        "rtg_draft_discard": set(),
        "rtg_history": {"ledger", "maximumRecords", "range", "includeVerbose"},
    }
    assert {value.name: _top_level_properties(value.inputSchema) for value in tools} == (
        expected_properties
    )
    conditional = {
        value.name: value.inputSchema
        for value in tools
        if value.name in {"rtg_draft_inspect", "rtg_validate"}
    }
    assert all(len(schema["oneOf"]) == 2 for schema in conditional.values())
    assert all("$ref" not in str(value.inputSchema) for value in tools)
    assert summary.structured_content == {
        "status": "accepted",
        "summary": "anchor types selected",
        "findings": [],
        "evaluatedRevision": 0,
        "anchorTypes": [],
    }
    changed_content = _content(changed)
    assert changed_content["status"] == "rejected"
    findings = cast(list[dict[str, object]], changed_content["findings"])
    assert findings[0]["code"] == "unknown"


@pytest.mark.anyio
async def test_discovered_schemas_encode_bounds_and_kind_compatible_scalars(
    database: Path,
) -> None:
    async with Client(build_server(database)) as client:
        schemas = {tool.name: tool.inputSchema for tool in await client.list_tools()}
    arrays = [
        value
        for schema in schemas.values()
        for value in _schema_objects_with_key(schema, "type")
        if value.get("type") == "array"
    ]
    assert arrays and all(value.get("maxItems") == 1000 for value in arrays)
    shaped_objects = [
        value
        for schema in schemas.values()
        for value in _schema_objects_with_key(schema, "properties")
        if value.get("type") == "object"
    ]
    assert shaped_objects and all(
        value.get("additionalProperties") is False for value in shaped_objects
    )
    inspect_keys = schemas["rtg_type_inspect"]["properties"]["anchorTypeKeys"]
    assert inspect_keys["minItems"] == 1 and inspect_keys["maxItems"] == 1000
    change = schemas["rtg_change"]["properties"]
    assert change["expectedRevision"]["minimum"] == 0
    assert change["upserts"]["maxItems"] == change["removeUuids"]["maxItems"] == 1000
    history_maximum = schemas["rtg_history"]["properties"]["maximumRecords"]
    assert history_maximum == {"maximum": 1000, "minimum": 1, "type": "integer"}
    query_text = str(schemas["rtg_query"])
    assert "'maxMatches': {'maximum': 1000, 'minimum': 1" in query_text

    scalar_branches = _schema_objects_with_key(schemas["rtg_change"], "properties")
    value_types: dict[object, object] = {}
    for branch in scalar_branches:
        properties = cast(dict[str, object], branch.get("properties", {}))
        kind = cast(dict[str, object], properties.get("kind", {})).get("const")
        if kind in {"boolean", "integer", "number", "text", "date", "timestamp", "null"}:
            value = cast(dict[str, object], properties["value"])
            value_types[kind] = value["type"]
    assert value_types == {
        "boolean": "boolean",
        "integer": "integer",
        "number": "number",
        "text": "string",
        "date": "string",
        "timestamp": "string",
        "null": "null",
    }
    raw_null_paths = [
        path for schema in schemas.values() for path in _raw_null_schema_paths(schema)
    ]
    assert raw_null_paths
    assert all(path[-2:] == ("properties", "value") for path in raw_null_paths)

    predicate_shapes: dict[str, tuple[set[str], set[str]]] = {}
    for branch in _schema_objects_with_key(schemas["rtg_query"], "properties"):
        properties = cast(dict[str, object], branch.get("properties", {}))
        operator = cast(dict[str, object], properties.get("operator", {}))
        names = operator.get("enum", [operator.get("const")])
        if not isinstance(names, list):
            continue
        if "anyOf" in names:
            assert cast(dict[str, object], properties["values"])["minItems"] == 1
        if set(names) & {"allTerms", "anyTerms"}:
            assert cast(dict[str, object], properties["terms"])["minItems"] == 1
        if "phrase" in names:
            assert cast(dict[str, object], properties["phrase"])["minLength"] == 1
        for name in names:
            if isinstance(name, str):
                predicate_shapes[name] = (
                    set(properties),
                    set(cast(list[str], branch.get("required", []))),
                )
    assert predicate_shapes == {
        **{
            name: ({"field", "operator"}, {"field", "operator"})
            for name in ("present", "missing", "isNull", "isNotNull")
        },
        **{
            name: ({"field", "operator", "value"}, {"field", "operator", "value"})
            for name in (
                "equal",
                "notEqual",
                "lessThan",
                "lessThanOrEqual",
                "greaterThan",
                "greaterThanOrEqual",
            )
        },
        "anyOf": ({"field", "operator", "values"}, {"field", "operator", "values"}),
        **{
            name: (
                {"field", "operator", "value", "caseSensitive"},
                {"field", "operator", "value"},
            )
            for name in ("contains", "prefix", "regex")
        },
        **{
            name: ({"field", "operator", "terms"}, {"field", "operator", "terms"})
            for name in ("allTerms", "anyTerms")
        },
        "phrase": ({"field", "operator", "phrase"}, {"field", "operator", "phrase"}),
    }


def _schema_objects_with_key(value: object, key: str) -> list[dict[str, object]]:
    if isinstance(value, dict):
        found = [value] if key in value else []
        for member in value.values():
            found.extend(_schema_objects_with_key(member, key))
        return found
    if isinstance(value, list):
        return [found for member in value for found in _schema_objects_with_key(member, key)]
    return []


def _raw_null_schema_paths(
    value: object, path: tuple[object, ...] = ()
) -> list[tuple[object, ...]]:
    if isinstance(value, dict):
        found = [path] if value.get("type") == "null" else []
        for key, member in value.items():
            found.extend(_raw_null_schema_paths(member, (*path, key)))
        return found
    if isinstance(value, list):
        found = []
        for index, member in enumerate(value):
            found.extend(_raw_null_schema_paths(member, (*path, index)))
        return found
    return []


def _top_level_properties(schema: dict[str, object]) -> set[str]:
    if "oneOf" not in schema:
        return set(cast(dict[str, object], schema.get("properties", {})))
    return {
        name
        for branch in cast(list[dict[str, object]], schema["oneOf"])
        for name in cast(dict[str, object], branch.get("properties", {}))
    }


def _activity_count(database: Path) -> int:
    with sqlite3.connect(database) as connection:
        return int(connection.execute("SELECT count(*) FROM activity_header").fetchone()[0])


async def _stage_dirty_definitions_and_validate(client: Client) -> None:
    for arguments, expected_code, expected_path_suffix in _dirty_definition_cases():
        staged = await client.call_tool("rtg_draft_change", arguments)
        assert _content(staged)["status"] == "accepted"
        validated = await client.call_tool("rtg_validate", {"scope": "draft", "limit": 1000})
        assert _content(validated)["clean"] is False
        assert _content(validated)["totalFindings"] == 1
        finding = cast(list[dict[str, object]], _content(validated)["findings"])[0]
        assert finding["code"] == expected_code
        assert str(finding["path"]).endswith(expected_path_suffix)
        await client.call_tool("rtg_draft_discard", {})


@pytest.mark.anyio
async def test_conditional_wire_shapes_fail_before_operation_or_activity(database: Path) -> None:
    invalid = [
        ("rtg_validate", {"scope": "current"}),
        ("rtg_validate", {"scope": "current", "cursor": "next", "limit": 10}),
        ("rtg_validate", {"cursor": "next"}),
        ("rtg_draft_inspect", {}),
        ("rtg_draft_inspect", {"cursor": "next", "limit": 10}),
        ("rtg_draft_inspect", {"cursor": "next", "categories": ["anchors"]}),
    ]
    invalid.extend(("rtg_query", value) for value in _malformed_predicate_queries())
    invalid.extend(("rtg_draft_change", value) for value in _malformed_definition_changes())
    before = _activity_count(database)
    async with Client(build_server(database)) as client:
        for name, arguments in invalid:
            with pytest.raises(ToolError):
                await client.call_tool(name, arguments)
    assert _activity_count(database) == before


@pytest.mark.anyio
async def test_direct_json_null_is_rejected_for_every_omissible_wire_member(
    database: Path,
) -> None:
    before = _activity_count(database)
    async with Client(build_server(database)) as client:
        for name, arguments in _direct_null_requests():
            with pytest.raises(ToolError):
                await client.call_tool(name, arguments)
    assert _activity_count(database) == before


def test_nested_wire_model_optional_member_inventory_rejects_direct_null() -> None:
    cases: dict[type[wire_models.WireModel], dict[str, object]] = {
        wire_models.CardinalityInput: {"minimum": 0},
        wire_models.PropertyDefinitionInput: {
            "name": "value",
            "description": "Value",
            "valueKind": "text",
        },
        wire_models.AnchorUpsertInput: {"kind": "anchor", "uuid": UUID},
        wire_models.AssociatedDataUpsertInput: {"kind": "associatedData", "uuid": UUID},
        wire_models.LinkUpsertInput: {"kind": "link", "uuid": UUID},
        wire_models.IdentityObjectInput: {"uuid": UUID},
        wire_models.TextPredicateInput: {
            "field": {"kind": "displayName"},
            "operator": "contains",
            "value": "x",
        },
        wire_models.PatternNodeInput: {"name": "node", "kind": "anchor"},
        wire_models.PatternLinkInput: {"name": "edge", "source": "a", "target": "b"},
        wire_models.PatternSelectionInput: {
            "kind": "pattern",
            "maxMatches": 1,
            "nodes": [{"name": "node", "kind": "anchor"}],
        },
        wire_models.TimeRangeInput: {"kind": "time"},
        wire_models.SequenceRangeInput: {"kind": "sequence"},
        wire_models.DraftInspectFreshInput: {"limit": 1},
    }
    optional_models = {
        value
        for value in vars(wire_models).values()
        if isinstance(value, type)
        and issubclass(value, wire_models.WireModel)
        and value is not wire_models.WireModel
        and any(not field.is_required() for field in value.model_fields.values())
    }
    assert set(cases) == optional_models
    discovered = {
        model: {
            field.alias or name
            for name, field in model.model_fields.items()
            if not field.is_required()
        }
        for model in cases
    }
    assert discovered == {
        wire_models.CardinalityInput: {"maximum"},
        wire_models.PropertyDefinitionInput: {
            "required",
            "nullable",
            "allowedValues",
            "minimum",
            "maximum",
            "minimumLength",
            "maximumLength",
            "pattern",
        },
        wire_models.AnchorUpsertInput: {"typeKey", "displayName"},
        wire_models.AssociatedDataUpsertInput: {
            "typeKey",
            "anchorUuids",
            "addAnchorUuids",
            "removeAnchorUuids",
            "setProperties",
            "removeProperties",
        },
        wire_models.LinkUpsertInput: {"typeKey", "sourceUuid", "targetUuid"},
        wire_models.IdentityObjectInput: {"properties", "includeLegacySystem"},
        wire_models.TextPredicateInput: {"caseSensitive"},
        wire_models.PatternNodeInput: {
            "typeKeys",
            "uuids",
            "predicates",
            "properties",
            "includeLegacySystem",
        },
        wire_models.PatternLinkInput: {"typeKeys", "uuids", "includeLegacySystem"},
        wire_models.PatternSelectionInput: {"directAssociations", "links"},
        wire_models.TimeRangeInput: {"start", "end"},
        wire_models.SequenceRangeInput: {"after", "through"},
        wire_models.DraftInspectFreshInput: {"categories", "operations", "typeKeys", "uuids"},
    }
    for model, arguments in cases.items():
        for alias in discovered[model]:
            with pytest.raises(PydanticValidationError):
                model.model_validate({**arguments, alias: None})


@pytest.mark.anyio
async def test_semantically_dirty_definitions_stage_and_validate_without_adapter_failure(
    database: Path, tmp_path: Path
) -> None:
    async with Client(build_server(database)) as client:
        await _stage_dirty_definitions_and_validate(client)

        staged = await client.call_tool("rtg_draft_change", _dirty_definition_changes()[2])
        assert _content(staged)["status"] == "accepted"
    assert audit_database(database).clean
    backup = tmp_path / "dirty-draft-backup.sqlite3"
    backup_database(database, backup)
    assert audit_database(backup).clean


@pytest.mark.anyio
async def test_explicit_empty_allowed_values_survive_draft_inspection_and_validation(
    starter_database: Path, tmp_path: Path
) -> None:
    definition = {
        "kind": "associatedData",
        "typeKey": "wire.explicit-empty",
        "description": "Explicit empty allowed values",
        "permittedAnchorTypeKeys": ["life.person"],
        "properties": [
            {
                "name": "value",
                "description": "Value",
                "valueKind": "text",
                "allowedValues": [],
            }
        ],
        "anchorsPerObject": {"minimum": 1, "maximum": 1},
        "objectsPerAnchor": {"minimum": 0, "maximum": 1},
    }
    async with Client(build_server(starter_database)) as client:
        staged = await client.call_tool("rtg_draft_change", {"definitionUpserts": [definition]})
        assert _content(staged)["status"] == "accepted"
        inspected = _content(
            await client.call_tool(
                "rtg_draft_inspect", {"typeKeys": ["wire.explicit-empty"], "limit": 10}
            )
        )
        entry = cast(list[dict[str, object]], inspected["entries"])[0]
        proposed = cast(dict[str, object], entry["proposed"])
        prop = cast(list[dict[str, object]], proposed["properties"])[0]
        assert prop["allowedValues"] == []
        assert "allowedValuesPresent" not in prop

        validated = _content(
            await client.call_tool("rtg_validate", {"scope": "draft", "limit": 10})
        )
        assert validated["clean"] is False
        assert validated["totalFindings"] == 1
        finding = cast(list[dict[str, object]], validated["findings"])[0]
        assert finding["code"] == "invalidValue"
        assert str(finding["path"]).endswith("/allowedValues")
        activated = _content(await client.call_tool("rtg_draft_activate", {}))
        assert activated["status"] == "rejected"

    assert audit_database(starter_database).clean
    backup = tmp_path / "explicit-empty-draft.sqlite3"
    backup_database(starter_database, backup)
    assert audit_database(backup).clean

    definition["typeKey"] = "wire.omitted-allowed"
    cast(dict[str, object], cast(list[object], definition["properties"])[0]).pop("allowedValues")
    async with Client(build_server(starter_database)) as client:
        await client.call_tool("rtg_draft_discard", {})
        await client.call_tool("rtg_draft_change", {"definitionUpserts": [definition]})
        inspected = _content(
            await client.call_tool(
                "rtg_draft_inspect", {"typeKeys": ["wire.omitted-allowed"], "limit": 10}
            )
        )
        entry = cast(list[dict[str, object]], inspected["entries"])[0]
        proposed = cast(dict[str, object], entry["proposed"])
        prop = cast(list[dict[str, object]], proposed["properties"])[0]
        assert "allowedValues" not in prop
        validated = _content(
            await client.call_tool("rtg_validate", {"scope": "draft", "limit": 10})
        )
        assert validated["clean"] is True
        await client.call_tool("rtg_draft_discard", {})


@pytest.mark.anyio
async def test_unknown_wire_member_is_invalid_arguments_not_domain_result(database: Path) -> None:
    async with Client(build_server(database)) as client:
        with pytest.raises(ToolError, match="unexpected"):
            await client.call_tool("rtg_type_summary", {"unexpected": True})
        with pytest.raises(ToolError):
            await client.call_tool(
                "rtg_change",
                {
                    "expectedRevision": 0,
                    "upserts": [
                        {
                            "kind": "associatedData",
                            "uuid": UUID,
                            "typeKey": "missing",
                            "anchorUuids": [UUID],
                            "setProperties": {"when": {"kind": "date", "value": True}},
                        }
                    ],
                },
            )
        with pytest.raises(ToolError):
            await client.call_tool(
                "rtg_type_inspect",
                {"anchor_type_keys": ["not-a-public-wire-member"]},
            )


@pytest.mark.anyio
async def test_non_utf8_unicode_surrogate_is_invalid_arguments_without_activity(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    operation_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal operation_called
        operation_called = True
        raise AssertionError("malformed wire text reached the domain operation")

    monkeypatch.setattr("vellis.mcp.apply_graph_change", fail_if_called)
    before = _activity_count(database)
    async with Client(build_server(database)) as client:
        with pytest.raises(ToolError, match="Unicode scalar values"):
            await client.call_tool(
                "rtg_change",
                {
                    "expectedRevision": 0,
                    "upserts": [
                        {
                            "kind": "anchor",
                            "uuid": UUID,
                            "typeKey": "missing",
                            "displayName": "\ud800",
                        }
                    ],
                },
            )
    assert not operation_called
    assert _activity_count(database) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "operation_name"),
    (
        ("rtg_type_inspect", {"anchorTypeKeys": ["\ud800"]}, "type_inspect"),
        ("rtg_draft_change", {"definitionRemovals": ["\ud800"]}, "change_draft"),
        ("rtg_draft_change", {"unstageDefinitionKeys": ["\ud800"]}, "change_draft"),
    ),
)
async def test_top_level_text_surrogates_reject_before_domain_operation(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    arguments: dict[str, object],
    operation_name: str,
) -> None:
    operation_called = False

    def fail_if_called(*_args, **_kwargs):
        nonlocal operation_called
        operation_called = True
        raise AssertionError("malformed wire text reached the domain operation")

    monkeypatch.setattr(f"vellis.mcp.{operation_name}", fail_if_called)
    before = _activity_count(database)
    async with Client(build_server(database)) as client:
        with pytest.raises(ToolError, match="Unicode scalar values"):
            await client.call_tool(tool_name, arguments)
    assert not operation_called
    assert _activity_count(database) == before


@pytest.mark.anyio
async def test_every_selected_tool_reaches_one_successor_operation(database: Path) -> None:
    calls = {
        "rtg_type_summary": {},
        "rtg_type_inspect": {"anchorTypeKeys": ["missing"]},
        "rtg_query": {"selection": {"kind": "identities", "objects": [{"uuid": UUID}]}},
        "rtg_change": {"expectedRevision": 0},
        "rtg_draft_inspect": {"limit": 10},
        "rtg_draft_change": {},
        "rtg_validate": {"scope": "current", "limit": 10},
        "rtg_draft_activate": {},
        "rtg_draft_discard": {},
        "rtg_history": {"ledger": "canonical", "maximumRecords": 10},
    }
    async with Client(build_server(database)) as client:
        results: dict[str, dict[str, object]] = {
            name: _content(await client.call_tool(name, arguments))
            for name, arguments in calls.items()
        }
    assert tuple(results) == TOOL_NAMES
    assert all(result["status"] in {"accepted", "rejected"} for result in results.values())
    assert results["rtg_query"]["missingUuids"] == [UUID]
    assert results["rtg_history"]["headSequence"] == 0


@pytest.mark.anyio
async def test_json_native_nested_enums_reach_operations(
    starter_database: Path, caplog: pytest.LogCaptureFixture
) -> None:
    async with Client(build_server(starter_database)) as client:
        await _exercise_enum_and_conditional_wire(client)
        before = _activity_count(starter_database)
        await _reject_malformed_canonical_values(client)
    assert _activity_count(starter_database) == before
    assert not any("Error calling tool" in record.message for record in caplog.records)


@pytest.mark.anyio
async def test_unexpected_operation_failure_is_an_mcp_error(tmp_path: Path) -> None:
    async with Client(build_server(tmp_path / "absent.sqlite3")) as client:
        with pytest.raises(ToolError):
            await client.call_tool("rtg_type_summary", {})


@pytest.mark.anyio
async def test_real_stdio_initialize_list_and_call(starter_database: Path) -> None:
    directory = starter_database.parent
    transport = StdioTransport(
        str(resolve_vellis_executable()),
        [
            "serve",
            "--transport",
            "stdio",
            "--data-dir",
            str(directory),
        ],
    )
    async with Client(transport) as client:
        assert tuple(value.name for value in await client.list_tools()) == TOOL_NAMES
        await _exercise_enum_and_conditional_wire(client)
        await _stage_dirty_definitions_and_validate(client)
        before = _activity_count(starter_database)
        await _reject_malformed_canonical_values(client)
    assert _activity_count(starter_database) == before


@pytest.mark.anyio
async def test_bearer_middleware_protects_complete_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    comparisons: list[tuple[bytes, bytes]] = []

    def compare_digest(left: bytes, right: bytes) -> bool:
        comparisons.append((left, right))
        return left == right

    monkeypatch.setattr("vellis.server.secrets.compare_digest", compare_digest)

    async def target(scope, receive, send):
        calls.append(scope["path"])
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = BearerMiddleware(target, b"secret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        missing = await client.get("/mcp")
        assert missing.status_code == 401
        assert missing.headers["www-authenticate"] == "Bearer"
        assert (
            await client.get("/anything", headers={"Authorization": "Bearer wrong"})
        ).status_code == 401
        duplicate = await client.get(
            "/mcp",
            headers=[
                ("Authorization", "Bearer secret"),
                ("Authorization", "Bearer secret"),
            ],
        )
        assert duplicate.status_code == 401
        accepted = await client.get("/mcp", headers={"Authorization": "Bearer secret"})
    assert accepted.status_code == 204
    assert calls == ["/mcp"]
    assert comparisons == [(b"wrong", b"secret"), (b"secret", b"secret")]


def test_token_file_is_private_nonempty_and_non_loopback_requires_it(
    database: Path, tmp_path: Path
) -> None:
    token_file = tmp_path / "token"
    write_new_http_token(token_file)
    token = read_http_token(token_file)
    assert len(token) >= 43
    if os.name == "posix":
        assert token_file.stat().st_mode & 0o077 == 0
        token_file.chmod(0o644)
        with pytest.raises(PermissionError, match="owner-private"):
            read_http_token(token_file)
    with pytest.raises(RuntimeError, match="token validation failed.*non-loopback"):
        serve_http(database, host="192.0.2.1", token_file=None)


@pytest.mark.anyio
async def test_token_file_bytes_are_exact_and_never_whitespace_normalized(tmp_path: Path) -> None:
    calls = 0

    async def target(scope, receive, send):
        nonlocal calls
        calls += 1
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def status(token: bytes, supplied: bytes) -> int:
        messages: list[dict[str, object]] = []

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        app = BearerMiddleware(target, token)
        await app(
            {
                "type": "http",
                "path": "/mcp",
                "headers": [(b"authorization", b"Bearer " + supplied)],
            },
            receive,
            send,
        )
        return cast(int, messages[0]["status"])

    token_file = tmp_path / "exact-token"
    token_file.write_bytes(b" leading-and-trailing ")
    token_file.chmod(0o600)
    exact = read_http_token(token_file)
    assert exact == b" leading-and-trailing "
    assert await status(exact, exact) == 204
    assert await status(exact, b"leading-and-trailing") == 401

    token_file.write_bytes(b"line-token\n")
    with_newline = read_http_token(token_file)
    assert with_newline == b"line-token\n"
    assert await status(with_newline, b"line-token") == 401
    assert calls == 1


def test_server_startup_failures_name_stage_action_and_leave_memory_unchanged(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    before = _activity_count(database)
    assert (
        main(
            [
                "serve",
                "--transport",
                "http",
                "--data-dir",
                str(tmp_path / "missing"),
            ]
        )
        == EXIT_FAILED
    )
    database_error = capsys.readouterr().err
    assert "database probe failed" in database_error
    assert "audit or setup" in database_error

    empty_token = tmp_path / "empty-token"
    empty_token.write_bytes(b"")
    empty_token.chmod(0o600)
    assert (
        main(
            [
                "serve",
                "--transport",
                "http",
                "--data-dir",
                str(database.parent),
                "--token-file",
                str(empty_token),
            ]
        )
        == EXIT_FAILED
    )
    token_error = capsys.readouterr().err
    assert "HTTP token validation failed" in token_error
    assert "readable, nonempty owner-private token file" in token_error
    assert _activity_count(database) == before

    for invalid_port in ("0", "65536", "not-a-port"):
        failed_port = subprocess.run(
            [
                sys.executable,
                "-m",
                "vellis",
                "serve",
                "--transport",
                "http",
                "--data-dir",
                str(database.parent),
                "--port",
                invalid_port,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert failed_port.returncode == 2
        assert "HTTP bind port must be" in failed_port.stderr
        assert "Traceback" not in failed_port.stderr
        assert _activity_count(database) == before

    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        port = int(occupied.getsockname()[1])
        failed = subprocess.run(
            [
                sys.executable,
                "-m",
                "vellis",
                "serve",
                "--transport",
                "http",
                "--data-dir",
                str(database.parent),
                "--port",
                str(port),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    assert failed.returncode == EXIT_FAILED
    assert "HTTP bind/start failed" in failed.stderr
    assert "choose an available host/port and retry" in failed.stderr
    assert _activity_count(database) == before


def _free_port() -> int:
    with socket.socket() as stream:
        stream.bind(("127.0.0.1", 0))
        return int(stream.getsockname()[1])


@pytest.mark.anyio
async def test_real_token_protected_http_initialize_list_and_call(
    starter_database: Path,
) -> None:
    port = _free_port()
    token_file = starter_database.parent / "http-token"
    write_new_http_token(token_file)
    token = token_file.read_text(encoding="ascii")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vellis",
            "serve",
            "--transport",
            "http",
            "--data-dir",
            str(starter_database.parent),
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        await _wait_http(url, token)
        transport = StreamableHttpTransport(url, headers={"Authorization": f"Bearer {token}"})
        async with Client(transport) as client:
            assert tuple(value.name for value in await client.list_tools()) == TOOL_NAMES
            await _exercise_enum_and_conditional_wire(client)
            await _stage_dirty_definitions_and_validate(client)
            before = _activity_count(starter_database)
            await _reject_malformed_canonical_values(client)
        assert _activity_count(starter_database) == before
        concurrent = await asyncio.gather(
            _http_summary(url, token),
            _http_summary(url, token),
        )
        assert concurrent == [0, 0]
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.anyio
async def test_token_rotation_requires_server_restart_before_new_credential_is_live(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    port = _free_port()
    token_file = database.parent / "http-token"
    write_new_http_token(token_file)
    old_token = token_file.read_text(encoding="ascii")

    def start_server() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "vellis",
                "serve",
                "--transport",
                "http",
                "--data-dir",
                str(database.parent),
                "--port",
                str(port),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    url = f"http://127.0.0.1:{port}/mcp"
    process = start_server()
    try:
        await _wait_http(url, old_token)
        monkeypatch.setattr("vellis.__main__.shutil.which", lambda name: None)
        assert (
            main(
                [
                    "configure",
                    "--data-dir",
                    str(database.parent),
                    "--rotate-http-token",
                    "--yes",
                ]
            )
            == EXIT_SUCCESS
        )
        guidance = capsys.readouterr().out
        assert "still accepts the old credential until it is restarted" in guidance
        assert "Stop and restart the foreground server" in guidance
        assert "reconnect every HTTP client" in guidance
        new_token = token_file.read_text(encoding="ascii")
        assert new_token != old_token
        assert await _http_auth_status(url, old_token) != 401
        assert await _http_auth_status(url, new_token) == 401
    finally:
        process.terminate()
        process.wait(timeout=10)

    process = start_server()
    try:
        await _wait_http(url, new_token)
        assert await _http_auth_status(url, new_token) != 401
        assert await _http_auth_status(url, old_token) == 401
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.anyio
async def test_default_rotation_does_not_change_a_custom_token_server(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    port = _free_port()
    default_file = database.parent / "http-token"
    custom_file = tmp_path / "custom-token"
    write_new_http_token(default_file)
    previous_default = default_file.read_text(encoding="ascii")
    write_new_http_token(custom_file)
    custom_token = custom_file.read_text(encoding="ascii")

    def start_server() -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            [
                sys.executable,
                "-m",
                "vellis",
                "serve",
                "--transport",
                "http",
                "--data-dir",
                str(database.parent),
                "--port",
                str(port),
                "--token-file",
                str(custom_file),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    url = f"http://127.0.0.1:{port}/mcp"
    process = start_server()
    try:
        await _wait_http(url, custom_token)
        monkeypatch.setattr("vellis.__main__.shutil.which", lambda name: None)
        assert (
            main(
                [
                    "configure",
                    "--data-dir",
                    str(database.parent),
                    "--rotate-http-token",
                    "--yes",
                ]
            )
            == EXIT_SUCCESS
        )
        new_default = default_file.read_text(encoding="ascii")
        assert new_default != previous_default
        assert custom_file.read_text(encoding="ascii") == custom_token
        assert await _http_auth_status(url, custom_token) != 401
        assert await _http_auth_status(url, new_default) == 401
        guidance = capsys.readouterr().out
        assert "changes only the default <data-directory>/http-token" in guidance
        assert "--token-file uses a custom file" in guidance
        assert "does not change" in guidance
    finally:
        process.terminate()
        process.wait(timeout=10)

    process = start_server()
    try:
        await _wait_http(url, custom_token)
        assert await _http_auth_status(url, custom_token) != 401
        assert await _http_auth_status(url, new_default) == 401
    finally:
        process.terminate()
        process.wait(timeout=10)


@pytest.mark.anyio
async def test_real_loopback_http_without_token_initialize_list_and_call(database: Path) -> None:
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "vellis",
            "serve",
            "--transport",
            "http",
            "--data-dir",
            str(database.parent),
            "--port",
            str(port),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        url = f"http://127.0.0.1:{port}/mcp"
        await _wait_http(url, None)
        async with Client(StreamableHttpTransport(url)) as client:
            assert tuple(value.name for value in await client.list_tools()) == TOOL_NAMES
            result = await client.call_tool("rtg_type_summary", {})
        assert _content(result)["evaluatedRevision"] == 0
    finally:
        process.terminate()
        process.wait(timeout=10)


async def _wait_http(url: str, token: str | None) -> None:
    deadline = time.monotonic() + 10
    async with httpx.AsyncClient() as client:
        while time.monotonic() < deadline:
            try:
                headers = None if token is None else {"Authorization": f"Bearer {token}"}
                response = await client.get(url, headers=headers)
                if response.status_code != 503:
                    return
            except httpx.TransportError:
                pass
            await asyncio.sleep(0.05)
    raise AssertionError("HTTP server did not become reachable")


async def _http_summary(url: str, token: str) -> int:
    transport = StreamableHttpTransport(url, headers={"Authorization": f"Bearer {token}"})
    async with Client(transport) as client:
        result = await client.call_tool("rtg_type_summary", {})
    return cast(int, _content(result)["evaluatedRevision"])


async def _http_auth_status(url: str, token: str) -> int:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    return response.status_code


def test_setup_noninteractive_is_explicit_and_connection_failure_does_not_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert main(["setup", "--data-dir", str(tmp_path / "missing")]) == EXIT_FAILED

    def fail_registration(*args, **kwargs):
        raise RuntimeError("client unavailable")

    monkeypatch.setattr("vellis.__main__.register_client", fail_registration)
    directory = tmp_path / "memory"
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(directory),
                "--blank",
                "--connect",
                "codex",
                "--transport",
                "stdio",
            ]
        )
        == EXIT_FAILED
    )
    assert (directory / "vellis.sqlite3").exists()


def test_setup_from_backup_reports_the_preserved_head_revision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_directory = tmp_path / "source"
    source = source_directory / "vellis.sqlite3"
    initialize_with_definitions(source, everyday_life_starter())
    changed = apply_graph_change(
        source,
        domain.GraphChangeRequest(
            0,
            (domain.AnchorUpsert(UUID, "life.person", "Owner"),),
        ),
    )
    assert changed.resulting_revision == 1
    backup = tmp_path / "backup.sqlite3"
    assert backup_database(source, backup) == backup

    destination = tmp_path / "recovered"
    assert (
        main(
            [
                "setup",
                "--from-backup",
                str(backup),
                "--data-dir",
                str(destination),
                "--no-connect",
            ]
        )
        == EXIT_SUCCESS
    )
    assert (
        f"Vellis initialized revision 1 at {destination / 'vellis.sqlite3'}"
        in capsys.readouterr().out
    )


def test_setup_parser_has_no_unselected_yes_option(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        main(["setup", "--help"])
    assert error.value.code == 0
    assert "--yes" not in capsys.readouterr().out

    with pytest.raises(SystemExit) as error:
        main(["setup", "--blank", "--no-connect", "--yes"])
    assert error.value.code != 0
    capsys.readouterr()

    for command in ("connect", "restore", "configure"):
        with pytest.raises(SystemExit) as error:
            main([command, "--help"])
        assert error.value.code == 0
        assert "--yes" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    (
        ("--blank", "--report-out", "report.json", "--no-connect"),
        ("--starter", "--confirm-source-digest", "a", "--no-connect"),
        (
            "--from-backup",
            "backup.sqlite3",
            "--confirm-source-digest",
            "a",
            "--confirm-report-digest",
            "b",
            "--no-connect",
        ),
        ("--from-v1", "v1.json", "--preview", "--no-connect"),
        (
            "--from-v1",
            "v1.json",
            "--preview",
            "--connect",
            "codex",
            "--transport",
            "stdio",
        ),
        (
            "--from-v1",
            "v1.json",
            "--preview",
            "--confirm-source-digest",
            "a",
            "--confirm-report-digest",
            "b",
        ),
        ("--from-v1", "v1.json", "--confirm-source-digest", "a", "--no-connect"),
        ("--from-v1", "v1.json", "--confirm-report-digest", "b", "--no-connect"),
        (
            "--from-v1",
            "v1.json",
            "--confirm-source-digest",
            "a",
            "--confirm-report-digest",
            "b",
            "--report-out",
            "report.json",
            "--no-connect",
        ),
    ),
)
def test_setup_rejects_context_incompatible_v1_flags_without_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    arguments: tuple[str, ...],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "vellis.__main__.initialize_blank",
        lambda *args, **kwargs: pytest.fail("invalid setup flags must not publish"),
    )
    monkeypatch.setattr(
        "vellis.__main__.initialize_with_definitions",
        lambda *args, **kwargs: pytest.fail("invalid setup flags must not publish"),
    )
    monkeypatch.setattr(
        "vellis.__main__.initialize_from_backup",
        lambda *args, **kwargs: pytest.fail("invalid setup flags must not publish"),
    )
    monkeypatch.setattr(
        "vellis.__main__.initialize_from_v1",
        lambda *args, **kwargs: pytest.fail("invalid setup flags must not publish"),
    )
    monkeypatch.setattr(
        "vellis.__main__.preview_v1_import",
        lambda *args, **kwargs: pytest.fail("invalid preview flags must not read or report"),
    )
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: pytest.fail("invalid setup flags must not register"),
    )
    destination = tmp_path / "memory"
    assert main(["setup", "--data-dir", str(destination), *arguments]) == EXIT_FAILED
    assert not destination.exists()


@pytest.mark.parametrize("transport", ("stdio", "http"))
def test_setup_reports_registration_partial_effect_and_keeps_initialized_memory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    transport: str,
) -> None:
    directory = tmp_path / transport
    monkeypatch.setattr(
        "vellis.__main__._capture_invocation_executable",
        lambda: resolve_vellis_executable(),
    )
    if transport == "http":

        def fixed_token(path: Path) -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("token", encoding="ascii")
            path.chmod(0o600)

        monkeypatch.setattr("vellis.__main__.probe_target", lambda *args, **kwargs: None)
        monkeypatch.setattr("vellis.__main__.write_new_http_token", fixed_token)
        monkeypatch.setenv("VELLIS_HTTP_TOKEN", "token")
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: RegistrationResult(
            True,
            "client entry changed; readiness unconfirmed",
            "codex mcp add recovery",
            readiness_confirmed=False,
        ),
    )
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(directory),
                "--blank",
                "--connect",
                "codex",
                "--transport",
                transport,
            ]
        )
        == EXIT_FAILED
    )
    output = capsys.readouterr().out
    assert "entry changed" in output and "Recovery command" in output
    assert (directory / "vellis.sqlite3").exists()


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (["", "yes", "none"], "starter"),
        (["blank", "yes", "none"], "blank"),
        (["backup", "/tmp/source.sqlite3", "yes", "none"], "backup"),
    ],
)
def test_interactive_setup_explicitly_offers_each_non_v1_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    answers: list[str],
    expected: str,
) -> None:
    selected: list[str] = []
    events: list[str] = []
    iterator = iter(answers)

    def recorded_input(prompt: str) -> str:
        events.append(f"prompt:{prompt}")
        return next(iterator)

    monkeypatch.setattr("builtins.input", recorded_input)
    monkeypatch.setattr("vellis.__main__.sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("vellis.__main__.shutil.which", lambda name: "/bin/client")
    monkeypatch.setattr(
        "vellis.__main__._initialize",
        lambda arguments, mode, database: (selected.append(mode), events.append("published")),
    )
    assert main(["setup", "--data-dir", str(tmp_path / "owner")]) == 0
    assert selected == [expected]
    assert events.index("published") < next(
        index
        for index, event in enumerate(events)
        if event.startswith("prompt:Connection transport")
    )

    if expected != "starter":
        return
    events.clear()
    iterator = iter(["starter", "no"])
    assert main(["setup", "--data-dir", str(tmp_path / "refused")]) == EXIT_SUCCESS
    assert "published" not in events
    assert not any("Connection transport" in event for event in events)

    events.clear()
    iterator = iter(["starter", "yes"])

    def fail_initialization(arguments, mode, database) -> None:
        events.append("initialization-failed")
        raise RuntimeError("publication failed")

    monkeypatch.setattr("vellis.__main__._initialize", fail_initialization)
    assert main(["setup", "--data-dir", str(tmp_path / "failed")]) == EXIT_FAILED
    assert events[-1] == "initialization-failed"
    assert not any("Connection transport" in event for event in events)


def test_interactive_v1_previews_and_binds_exact_confirmation_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[tuple[str, str, str]] = []
    iterator = iter(["v1", "/tmp/v1.json", "/tmp/report.json", "yes", "yes", "none"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(iterator))
    monkeypatch.setattr("vellis.__main__.sys.stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr("vellis.__main__.shutil.which", lambda name: "/bin/client")
    monkeypatch.setattr(
        "vellis.__main__.preview_v1_import",
        lambda source, report_out=None: SimpleNamespace(
            source_sha256="source-digest",
            report_sha256="report-digest",
            disposition_counts=SimpleNamespace(preserved=1, converted=2, omitted=3, blocking=0),
            acceptable=True,
        ),
    )

    def capture(arguments, mode, database):
        captured.append((mode, arguments.confirm_source_digest, arguments.confirm_report_digest))

    monkeypatch.setattr("vellis.__main__._initialize", capture)
    assert main(["setup", "--data-dir", str(tmp_path / "owner")]) == 0
    assert captured == [("v1", "source-digest", "report-digest")]


def test_guided_http_setup_and_rotation_never_print_or_store_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "memory"
    monkeypatch.setattr(
        "vellis.__main__._capture_invocation_executable", lambda: resolve_vellis_executable()
    )
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: pytest.fail("--no-connect must not register a client"),
    )
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(directory),
                "--blank",
                "--no-connect",
                "--transport",
                "http",
            ]
        )
        == 0
    )
    token_file = directory / "http-token"
    previous = token_file.read_text(encoding="ascii")
    setup_output = capsys.readouterr()
    assert previous not in setup_output.out + setup_output.err
    monkeypatch.setattr("vellis.__main__.entry_exists", lambda client: False)
    assert (
        main(
            [
                "configure",
                "--data-dir",
                str(directory),
                "--rotate-http-token",
                "--yes",
            ]
        )
        == 0
    )
    current = token_file.read_text(encoding="ascii")
    rotation_output = capsys.readouterr()
    assert current != previous
    assert current not in rotation_output.out + rotation_output.err
    with sqlite3.connect(directory / "vellis.sqlite3") as connection:
        payloads = " ".join(
            str(row[0])
            for row in connection.execute("SELECT semantic_payload FROM activity_payload")
        )
    assert current not in payloads and previous not in payloads


def test_http_setup_with_selected_client_prints_ordered_secret_free_next_steps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "owner memory"
    exact = resolve_vellis_executable()
    monkeypatch.setattr("vellis.__main__._capture_invocation_executable", lambda: exact)
    monkeypatch.setattr(
        "vellis.__main__.probe_target",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("not listening")),
    )
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(directory),
                "--blank",
                "--connect",
                "codex",
                "--transport",
                "http",
            ]
        )
        == 0
    )
    token = (directory / "http-token").read_text(encoding="ascii")
    output = capsys.readouterr().out
    assert output.index("1. Prepare") < output.index("2. Start") < output.index("3. Connect")
    assert "'" in output  # the data path with a space is shell quoted
    assert f"{exact} connect --client codex --transport http" in output
    assert " vellis serve " not in output and " vellis connect " not in output
    assert token not in output


def test_reachable_http_setup_registers_selected_client_when_environment_is_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registered: list[tuple[ClientKind, TransportKind]] = []
    monkeypatch.setattr(
        "vellis.__main__._capture_invocation_executable", lambda: resolve_vellis_executable()
    )

    def fixed_token(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("known-token", encoding="ascii")
        path.chmod(0o600)

    def register(client, transport, **kwargs):
        registered.append((client, transport))
        return RegistrationResult(True, "configured", readiness_confirmed=True)

    monkeypatch.setenv("VELLIS_HTTP_TOKEN", "known-token")
    monkeypatch.setattr("vellis.__main__.write_new_http_token", fixed_token)
    monkeypatch.setattr("vellis.__main__.probe_target", lambda *args, **kwargs: None)
    monkeypatch.setattr("vellis.__main__.register_client", register)
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(tmp_path / "owner"),
                "--blank",
                "--connect",
                "claude",
                "--transport",
                "http",
            ]
        )
        == 0
    )
    assert registered == [(ClientKind.CLAUDE, TransportKind.HTTP)]


def test_reachable_http_setup_without_environment_skips_redundant_start_step(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "vellis.__main__._capture_invocation_executable", lambda: resolve_vellis_executable()
    )
    monkeypatch.delenv("VELLIS_HTTP_TOKEN", raising=False)
    monkeypatch.setattr("vellis.__main__.probe_target", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: pytest.fail("missing runtime environment must not register"),
    )
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(tmp_path / "owner"),
                "--blank",
                "--connect",
                "codex",
                "--transport",
                "http",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Start the foreground server" not in output
    assert "2. Connect codex" in output
    assert 'export VELLIS_HTTP_TOKEN="$(<' in output


def test_rotation_activity_failure_reports_that_token_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "memory"
    monkeypatch.setattr(
        "vellis.__main__._capture_invocation_executable", lambda: resolve_vellis_executable()
    )
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(directory),
                "--blank",
                "--no-connect",
                "--transport",
                "http",
            ]
        )
        == 0
    )
    previous = (directory / "http-token").read_text(encoding="ascii")

    def fail_activity(path: Path, publish) -> None:
        publish()
        raise HttpTokenChangedError("token changed; injected activity failure")

    monkeypatch.setattr("vellis.__main__.record_http_token_rotation", fail_activity)
    assert (
        main(
            [
                "configure",
                "--data-dir",
                str(directory),
                "--rotate-http-token",
                "--yes",
            ]
        )
        == EXIT_FAILED
    )
    current = (directory / "http-token").read_text(encoding="ascii")
    output = capsys.readouterr()
    assert current != previous
    assert "token changed" in output.err
    assert "still accepts the old credential until it is restarted" in output.err
    assert "reconnect every HTTP client" in output.err
    assert "--token-file uses a custom file" in output.err
    assert current not in output.out + output.err


def test_rotation_enumeration_failure_reports_complete_post_effect_truth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    directory = tmp_path / "memory"
    assert main(["setup", "--data-dir", str(directory), "--blank", "--no-connect"]) == 0
    monkeypatch.setattr("vellis.__main__.shutil.which", lambda name: "/bin/client")
    monkeypatch.setattr(
        "vellis.__main__.entry_exists",
        lambda client: (_ for _ in ()).throw(OSError("enumeration failed")),
    )
    assert (
        main(
            [
                "configure",
                "--data-dir",
                str(directory),
                "--rotate-http-token",
                "--yes",
            ]
        )
        == EXIT_FAILED
    )
    error = capsys.readouterr().err
    assert "token changed" in error
    assert "still accepts the old credential until it is restarted" in error
    assert "reconnect every HTTP client" in error
    assert "enumeration is incomplete" in error
    assert "manual clients cannot be enumerated" in error
    assert "--token-file uses a custom file" in error


def test_rotation_reporting_print_failure_retains_post_effect_truth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vellis.__main__.shutil.which", lambda name: None)
    monkeypatch.setattr(
        "builtins.print", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("pipe closed"))
    )
    with pytest.raises(HttpTokenChangedError) as captured:
        main_module._report_rotated_token_clients()
    message = str(captured.value)
    assert "token changed" in message
    assert "still accepts the old credential until it is restarted" in message
    assert "reconnect every HTTP client" in message
    assert "enumeration is incomplete" in message
    assert "manual clients cannot be enumerated" in message
    assert "--token-file uses a custom file" in message


def test_token_permissions_are_fixed_before_atomic_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, Path]] = []
    real_chmod = os.chmod
    real_replace = os.replace

    def chmod(path: Path, mode: int) -> None:
        events.append(("chmod", Path(path)))
        real_chmod(path, mode)

    def replace(source: Path, destination: Path) -> None:
        events.append(("replace", Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr("vellis.server.os.chmod", chmod)
    monkeypatch.setattr("vellis.server.os.replace", replace)
    target = tmp_path / "http-token"
    write_new_http_token(target)
    assert [name for name, _ in events] == ["chmod", "replace"]
    assert events[0][1] != target and events[1][1] == target


def test_post_publication_token_durability_failure_says_token_changed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    directory = tmp_path / "memory"
    assert main(["setup", "--data-dir", str(directory), "--blank", "--no-connect"]) == 0
    monkeypatch.setattr(
        "vellis.server._flush_directory",
        lambda directory: (_ for _ in ()).throw(OSError("injected durability failure")),
    )
    assert (
        main(
            [
                "configure",
                "--data-dir",
                str(directory),
                "--rotate-http-token",
                "--yes",
            ]
        )
        == EXIT_FAILED
    )
    assert read_http_token(directory / "http-token")
    error = capsys.readouterr().err
    assert "token changed" in error
    assert "still accepts the old credential until it is restarted" in error
    assert "reconnect every HTTP client" in error
    assert "--token-file uses a custom file" in error


def test_client_replacement_probes_before_remove_and_reports_recovery(tmp_path: Path) -> None:
    events: list[object] = []
    probes: list[TransportKind] = []

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        events.append(arguments)
        if arguments[1:4] == ("mcp", "get", "vellis"):
            return CommandResult(0)
        if arguments[1:4] == ("mcp", "remove", "vellis"):
            return CommandResult(0)
        return CommandResult(1, stderr="add failed")

    def probe(transport, **kwargs):
        probes.append(transport)
        events.append(("probe", transport))

    result = register_client(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path,
        url="",
        token_environment="TOKEN",
        replace=True,
        confirmed=True,
        runner=runner,
        probe=probe,
    )
    assert probes == [TransportKind.STDIO]
    calls = [event for event in events if isinstance(event, tuple) and event[0] != "probe"]
    assert calls[0] == ("codex", "mcp", "get", "vellis")
    assert calls[1] == ("codex", "mcp", "remove", "vellis")
    assert events.index(("probe", TransportKind.STDIO)) < events.index(calls[1])
    assert result.changed and result.recovery_command == " ".join(calls[2])
    assert not result.readiness_confirmed
    assert result.recovery_command is not None
    assert "TOKEN" not in result.recovery_command


@pytest.mark.parametrize("client", tuple(ClientKind))
def test_client_enumeration_distinguishes_absence_from_uncertain_failure(
    client: ClientKind,
) -> None:
    assert not entry_exists(client, lambda _arguments: _missing_entry_result(client))
    other_client = ClientKind.CLAUDE if client is ClientKind.CODEX else ClientKind.CODEX
    uncertain_results = (
        CommandResult(1, stderr="failed to load configuration"),
        CommandResult(
            1,
            stderr=(
                f"{_missing_entry_result(client).stderr}\nfatal: configuration could not be parsed"
            ),
        ),
        _missing_entry_result(other_client),
    )
    for result in uncertain_results:
        with pytest.raises(RuntimeError, match="external configuration state is uncertain"):
            entry_exists(client, lambda _arguments, result=result: result)


def test_add_invocation_exception_after_removal_reports_changed_state_and_recovery(
    tmp_path: Path,
) -> None:
    def runner(arguments: tuple[str, ...]) -> CommandResult:
        if arguments == ("codex", "mcp", "get", "vellis"):
            return CommandResult(0)
        if arguments == ("codex", "mcp", "remove", "vellis"):
            return CommandResult(0)
        raise FileNotFoundError("client disappeared")

    result = register_client(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path,
        url="",
        token_environment="TOKEN",
        replace=True,
        confirmed=True,
        runner=runner,
        probe=lambda *args, **kwargs: None,
    )
    assert result.changed
    assert not result.readiness_confirmed
    assert result.recovery_command is not None
    assert "after removal" in result.summary


@pytest.mark.parametrize("raises", (False, True))
def test_remove_failure_reports_uncertain_state_and_does_not_attempt_add(
    tmp_path: Path, raises: bool
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        if arguments == ("codex", "mcp", "get", "vellis"):
            return CommandResult(0)
        if arguments == ("codex", "mcp", "remove", "vellis"):
            if raises:
                raise OSError("remove invocation failed")
            return CommandResult(1, stderr="remove failed")
        pytest.fail("add must not be attempted after uncertain removal")

    result = register_client(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path,
        url="",
        token_environment="TOKEN",
        replace=True,
        confirmed=True,
        runner=runner,
        probe=lambda *args, **kwargs: None,
    )
    assert not result.changed and not result.readiness_confirmed
    assert "state is uncertain" in result.summary
    assert result.recovery_command is not None
    assert "mcp get vellis" in result.recovery_command
    assert "mcp remove vellis" in result.recovery_command
    assert "mcp add vellis" in result.recovery_command
    assert len(calls) == 2


def test_http_client_commands_pass_only_environment_references(tmp_path: Path) -> None:
    codex = add_command(
        ClientKind.CODEX,
        TransportKind.HTTP,
        data_directory=tmp_path,
        url="https://example.test/mcp",
        token_environment="MY_TOKEN",
    )
    claude = add_command(
        ClientKind.CLAUDE,
        TransportKind.HTTP,
        data_directory=tmp_path,
        url="https://example.test/mcp",
        token_environment="MY_TOKEN",
    )
    assert "--bearer-token-env-var" in codex and "MY_TOKEN" in codex
    assert "Authorization: Bearer ${MY_TOKEN}" in claude
    assert os.environ.get("MY_TOKEN", "not-a-token") not in " ".join(codex + claude)

    stdio = add_command(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path / "owner memory",
        url="",
        token_environment="MY_TOKEN",
    )
    separator = stdio.index("--")
    assert stdio[separator + 1 :] == (
        str(resolve_vellis_executable()),
        "serve",
        "--transport",
        "stdio",
        "--data-dir",
        str((tmp_path / "owner memory").resolve()),
    )


def test_existing_client_requires_replace_without_external_mutation(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        return CommandResult(0)

    result = register_client(
        ClientKind.CODEX,
        TransportKind.HTTP,
        data_directory=tmp_path,
        url="https://example.test/mcp",
        token_environment="TOKEN",
        replace=False,
        confirmed=False,
        runner=runner,
        environ={},
        probe=lambda *args, **kwargs: pytest.fail("existing entry must not preflight"),
    )
    assert not result.changed and not result.readiness_confirmed
    assert "--replace" in result.summary
    assert calls == [("codex", "mcp", "get", "vellis")]

    calls.clear()
    with pytest.raises(ValueError, match="environment variable TOKEN"):
        register_client(
            ClientKind.CODEX,
            TransportKind.HTTP,
            data_directory=tmp_path,
            url="https://example.test/mcp",
            token_environment="TOKEN",
            replace=True,
            confirmed=True,
            runner=runner,
            environ={},
            probe=lambda *args, **kwargs: pytest.fail("missing environment must not preflight"),
        )
    assert calls == [("codex", "mcp", "get", "vellis")]


def test_successful_add_with_failed_final_probe_reports_changed_unconfirmed_readiness(
    tmp_path: Path,
) -> None:
    probes = 0

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        if arguments == ("codex", "mcp", "get", "vellis"):
            return _missing_entry_result(ClientKind.CODEX)
        return CommandResult(0)

    def probe(*args, **kwargs):
        nonlocal probes
        probes += 1
        if probes == 2:
            raise RuntimeError("lost after add")

    result = register_client(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path,
        url="",
        token_environment="TOKEN",
        replace=False,
        confirmed=False,
        runner=runner,
        probe=probe,
    )
    assert result.changed
    assert not result.readiness_confirmed
    assert "entry changed" in result.summary
    assert "readiness" in result.summary
    assert "rollback" not in result.summary


def test_claude_http_registration_checks_public_help_and_keeps_token_out_of_argv(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        if arguments == ("claude", "mcp", "get", "vellis"):
            return _missing_entry_result(ClientKind.CLAUDE)
        if arguments == ("claude", "mcp", "add", "--help"):
            return CommandResult(
                0,
                stdout="--header 'Authorization: Bearer ${ENV_VAR}' environment variable "
                "template expansion",
            )
        return CommandResult(0)

    result = register_client(
        ClientKind.CLAUDE,
        TransportKind.HTTP,
        data_directory=tmp_path,
        url="https://example.test/mcp",
        token_environment="MY_TOKEN",
        replace=False,
        confirmed=False,
        runner=runner,
        environ={"MY_TOKEN": "literal-secret"},
        probe=lambda *args, **kwargs: None,
    )
    assert result.changed and result.readiness_confirmed
    addition = calls[-1]
    assert "Authorization: Bearer ${MY_TOKEN}" in addition
    assert "literal-secret" not in " ".join(addition)


@pytest.mark.parametrize("exists", (False, True))
def test_registration_success_is_ready_only_after_both_target_probes(
    tmp_path: Path, exists: bool
) -> None:
    events: list[object] = []

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        events.append(arguments)
        if arguments == ("codex", "mcp", "get", "vellis"):
            return CommandResult(0) if exists else _missing_entry_result(ClientKind.CODEX)
        return CommandResult(0)

    def probe(*args, **kwargs) -> None:
        events.append("probe")

    result = register_client(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path,
        url="",
        token_environment="TOKEN",
        replace=exists,
        confirmed=True,
        runner=runner,
        probe=probe,
    )
    assert result.changed and result.readiness_confirmed
    assert result.recovery_command is None
    assert events.count("probe") == 2
    mutation = [
        value for value in events if isinstance(value, tuple) and value[1:3] == ("mcp", "add")
    ]
    assert len(mutation) == 1
    if exists:
        remove = ("codex", "mcp", "remove", "vellis")
        assert events.index("probe") < events.index(remove) < events.index(mutation[0])


def test_confirmation_and_preflight_failures_never_report_readiness_or_mutate(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, ...]] = []

    def existing(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        return CommandResult(0)

    confirmation = register_client(
        ClientKind.CODEX,
        TransportKind.STDIO,
        data_directory=tmp_path,
        url="",
        token_environment="TOKEN",
        replace=True,
        confirmed=False,
        runner=existing,
        probe=lambda *args, **kwargs: None,
    )
    assert not confirmation.changed and not confirmation.readiness_confirmed
    assert confirmation.recovery_command is None
    assert calls == [("codex", "mcp", "get", "vellis")]

    calls.clear()

    def absent(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        return _missing_entry_result(ClientKind.CODEX)

    with pytest.raises(OSError, match="preflight failed"):
        register_client(
            ClientKind.CODEX,
            TransportKind.STDIO,
            data_directory=tmp_path,
            url="",
            token_environment="TOKEN",
            replace=False,
            confirmed=False,
            runner=absent,
            probe=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("preflight failed")),
        )
    assert calls == [("codex", "mcp", "get", "vellis")]


def test_claude_http_refuses_help_that_only_mentions_headers(tmp_path: Path) -> None:
    calls: list[tuple[str, ...]] = []

    def runner(arguments: tuple[str, ...]) -> CommandResult:
        calls.append(arguments)
        if arguments == ("claude", "mcp", "get", "vellis"):
            return _missing_entry_result(ClientKind.CLAUDE)
        if arguments == ("claude", "mcp", "add", "--help"):
            return CommandResult(0, stdout="--header HTTP header")
        pytest.fail("unsupported automation must not mutate the client")

    with pytest.raises(RuntimeError, match="template expansion"):
        register_client(
            ClientKind.CLAUDE,
            TransportKind.HTTP,
            data_directory=tmp_path,
            url="https://example.test/mcp",
            token_environment="MY_TOKEN",
            replace=False,
            confirmed=False,
            runner=runner,
            environ={"MY_TOKEN": "literal-secret"},
            probe=lambda *args, **kwargs: pytest.fail("must refuse before target preflight"),
        )
    assert calls == [
        ("claude", "mcp", "get", "vellis"),
        ("claude", "mcp", "add", "--help"),
    ]


def test_connect_rejects_stdio_http_options_without_probing(tmp_path: Path) -> None:
    assert (
        main(
            [
                "connect",
                "--client",
                "codex",
                "--transport",
                "stdio",
                "--data-dir",
                str(tmp_path),
                "--url",
                "http://127.0.0.1:8000/mcp",
            ]
        )
        == EXIT_FAILED
    )


def test_connect_reports_failed_readiness_after_external_entry_changed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: RegistrationResult(
            True,
            "public client entry changed, but readiness is unconfirmed",
            readiness_confirmed=False,
        ),
    )
    assert (
        main(
            [
                "connect",
                "--client",
                "codex",
                "--transport",
                "stdio",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == EXIT_FAILED
    )


def test_existing_entry_guidance_is_not_reported_as_ready_by_connect_or_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exact = resolve_vellis_executable()
    monkeypatch.setattr("vellis.__main__._capture_invocation_executable", lambda: exact)
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: RegistrationResult(
            False, "vellis already exists; pass --replace to replace it"
        ),
    )
    assert (
        main(
            [
                "connect",
                "--client",
                "codex",
                "--transport",
                "stdio",
                "--data-dir",
                str(tmp_path / "connect"),
            ]
        )
        == EXIT_FAILED
    )
    assert "--replace" in capsys.readouterr().out

    directory = tmp_path / "setup"
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(directory),
                "--blank",
                "--connect",
                "codex",
                "--transport",
                "stdio",
            ]
        )
        == EXIT_FAILED
    )
    assert "--replace" in capsys.readouterr().out
    assert (directory / "vellis.sqlite3").exists()

    def existing_runner(arguments: tuple[str, ...]) -> CommandResult:
        assert arguments == ("codex", "mcp", "get", "vellis")
        return CommandResult(0)

    def existing_http(client, transport, **kwargs):
        return register_client(client, transport, **kwargs, runner=existing_runner)

    monkeypatch.setattr("vellis.__main__.register_client", existing_http)
    monkeypatch.delenv("VELLIS_HTTP_TOKEN", raising=False)
    assert (
        main(
            [
                "connect",
                "--client",
                "codex",
                "--transport",
                "http",
                "--data-dir",
                str(tmp_path / "http-connect"),
            ]
        )
        == EXIT_FAILED
    )
    assert "--replace" in capsys.readouterr().out

    def fixed_token(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("known-token", encoding="ascii")
        path.chmod(0o600)

    monkeypatch.setenv("VELLIS_HTTP_TOKEN", "known-token")
    monkeypatch.setattr("vellis.__main__.write_new_http_token", fixed_token)
    monkeypatch.setattr("vellis.__main__.probe_target", lambda *args, **kwargs: None)
    http_directory = tmp_path / "http-setup"
    assert (
        main(
            [
                "setup",
                "--data-dir",
                str(http_directory),
                "--blank",
                "--connect",
                "codex",
                "--transport",
                "http",
            ]
        )
        == EXIT_FAILED
    )
    assert "--replace" in capsys.readouterr().out
    assert (http_directory / "vellis.sqlite3").exists()


def test_cli_passes_one_captured_absolute_executable_without_path_reresolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    exact = resolve_vellis_executable()
    captured: list[Path | None] = []
    monkeypatch.setattr("vellis.__main__._capture_invocation_executable", lambda: exact)
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: (
            captured.append(kwargs["executable"]),
            RegistrationResult(True, "configured", readiness_confirmed=True),
        )[1],
    )
    monkeypatch.setattr(
        "vellis.__main__.shutil.which",
        lambda name: pytest.fail("PATH must not be searched after startup capture"),
    )
    assert (
        main(
            [
                "connect",
                "--client",
                "codex",
                "--transport",
                "stdio",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert captured == [exact]


def test_claude_http_connect_explains_literal_runtime_template(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "vellis.__main__.register_client",
        lambda *args, **kwargs: RegistrationResult(True, "configured", readiness_confirmed=True),
    )
    assert (
        main(
            [
                "connect",
                "--client",
                "claude",
                "--transport",
                "http",
                "--data-dir",
                str(tmp_path),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "literal Authorization header template" in output
    assert "${VELLIS_HTTP_TOKEN}" in output
    assert "responsible for supplying and protecting" in output
