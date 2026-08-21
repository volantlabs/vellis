"""Complete pre-omission identity reservation scan for one v1 snapshot."""

from __future__ import annotations

from vellis.v1_conversion_common import imported_uuid, is_live
from vellis.v1_import_domain import V1Disposition, V1ImportError
from vellis.v1_json import decode_legacy_json
from vellis.v1_pointer import append_pointer
from vellis.v1_report import add_disposition
from vellis.v1_stage import STAGE_RELATION, iter_category, put_payload

_GRAPH_FAMILIES = (
    ("sourceAnchor", "anchor"),
    ("sourceData", "associatedData"),
    ("sourceLink", "link"),
)
_DEFINITION_KINDS = {
    "anchor": "anchor",
    "data_object": "associatedData",
    "link": "link",
}


def scan_identity_reservations(connection) -> None:
    """Reserve every graph UUID and type key before liveness can omit an entry."""
    ordinal = _scan_graph_identities(connection)
    _scan_type_identities(connection, ordinal)
    _report_conflicts(connection, "identityGraph", "UUID")
    _report_conflicts(connection, "identityType", "type key")


def identity_conflicted(connection, category: str, identity: str) -> bool:
    relation = "identityGraph" if category == "graph" else "identityType"
    count = connection.execute(
        f"SELECT count(*) FROM {STAGE_RELATION} WHERE category=? AND natural_key=?",
        (relation, identity),
    ).fetchone()[0]
    return int(count) != 1


def source_entry_live(connection, raw, pointer: str) -> bool | None:
    invalid = connection.execute(
        f"SELECT 1 FROM {STAGE_RELATION} WHERE category='invalidSourceEntry' "
        "AND natural_key=? LIMIT 1",
        (pointer,),
    ).fetchone()
    return None if invalid is not None else is_live(raw, pointer)


def _scan_graph_identities(connection) -> int:
    ordinal = 0
    for category, kind in _GRAPH_FAMILIES:
        for _key, pointer, raw in iter_category(connection, category):
            if not isinstance(raw, dict):
                continue
            _record_invalid_liveness(connection, raw, pointer, ordinal)
            try:
                identity = imported_uuid(
                    connection, raw.get("uuid"), append_pointer(pointer, "uuid")
                )
            except (TypeError, ValueError, V1ImportError) as error:
                _invalid(
                    connection,
                    append_pointer(pointer, "uuid"),
                    f"invalid graph UUID: {error}",
                )
                continue
            put_payload(
                connection,
                "identityGraph",
                identity,
                pointer,
                {"kind": kind, "identity": identity},
                ordinal=ordinal,
            )
            ordinal += 1
    return ordinal


def _scan_type_identities(connection, ordinal: int) -> None:
    for _key, pointer, raw in iter_category(connection, "sourceDefinition"):
        if not isinstance(raw, dict):
            continue
        _record_invalid_liveness(connection, raw, pointer, ordinal)
        identity = raw.get("type_key")
        source_kind = raw.get("kind")
        kind = _DEFINITION_KINDS.get(source_kind) if isinstance(source_kind, str) else None
        if not isinstance(identity, str) or not identity or kind is None:
            _invalid(
                connection,
                pointer,
                "definition identity requires a nonempty exact type key and recognized kind",
            )
            continue
        put_payload(
            connection,
            "identityType",
            identity,
            pointer,
            {"kind": kind, "identity": identity},
            ordinal=ordinal,
        )
        ordinal += 1


def _record_invalid_liveness(connection, raw, pointer, ordinal):
    try:
        is_live(raw, pointer)
    except (TypeError, ValueError, V1ImportError) as error:
        put_payload(
            connection,
            "invalidSourceEntry",
            pointer,
            pointer,
            {"summary": str(error)},
            ordinal=ordinal,
        )
        add_disposition(
            connection,
            V1Disposition.BLOCKING,
            "source-entry-invalid",
            append_pointer(pointer, "system", "live"),
            str(error),
        )


def _report_conflicts(connection, category: str, label: str) -> None:
    groups = connection.execute(
        f"SELECT natural_key,count(*),count(DISTINCT json_extract(payload,'$.kind')) "
        f"FROM {STAGE_RELATION} WHERE category=? GROUP BY natural_key HAVING count(*)>1",
        (category,),
    )
    for identity, count, kinds in groups:
        code = "identity-kind-conflict" if int(kinds) > 1 else "duplicate-identity"
        summary = (
            f"{label} {identity} occurs across different kinds"
            if int(kinds) > 1
            else f"{label} {identity} occurs {count} times; v1 history is not imported"
        )
        rows = connection.execute(
            f"SELECT source_pointer,payload FROM {STAGE_RELATION} "
            "WHERE category=? AND natural_key=? ORDER BY ordinal",
            (category, identity),
        )
        for pointer, payload_text in rows:
            payload = decode_legacy_json(str(payload_text))
            assert isinstance(payload, dict)
            add_disposition(
                connection,
                V1Disposition.BLOCKING,
                code,
                str(pointer),
                summary,
                target_uuid=str(identity) if category == "identityGraph" else None,
                target_type_key=str(identity) if category == "identityType" else None,
            )


def _invalid(connection, pointer, summary):
    add_disposition(
        connection,
        V1Disposition.BLOCKING,
        "identity-invalid",
        pointer,
        summary,
    )
