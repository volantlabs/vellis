"""One shared derivation of converted v1 permitted endpoint populations."""

from __future__ import annotations

from vellis.domain import canonical_uuid
from vellis.v1_conversion_common import is_live
from vellis.v1_identity import source_entry_live
from vellis.v1_json import decode_legacy_json
from vellis.v1_stage import STAGE_RELATION, iter_category


def permitted_anchor_keys(connection, data_type: str) -> tuple[str, ...]:
    permitted: set[str] = set()
    for _key, pointer, raw in iter_category(connection, "sourceDefinition"):
        if (
            not isinstance(raw, dict)
            or not source_entry_live(connection, raw, pointer)
            or raw.get("kind") != "anchor"
        ):
            continue
        anchor_key = raw.get("type_key")
        payload = raw.get("payload", {})
        if not isinstance(anchor_key, str) or not isinstance(payload, dict):
            continue
        required = payload.get("required_data_types", [])
        optional = payload.get("optional_data_types", [])
        if isinstance(required, list) and data_type in required:
            permitted.add(anchor_key)
        if isinstance(optional, list) and data_type in optional:
            permitted.add(anchor_key)
    rows = connection.execute(
        f"""SELECT DISTINCT d.payload, a.payload
            FROM {STAGE_RELATION} d
            JOIN {STAGE_RELATION} x ON x.category='candidateAssociation'
              AND json_extract(x.payload,'$.dataUuid')=lower(json_extract(d.payload,'$.uuid'))
            JOIN {STAGE_RELATION} a ON a.category='sourceAnchor'
              AND json_extract(x.payload,'$.anchorUuid')=lower(json_extract(a.payload,'$.uuid'))
            WHERE d.category='sourceData' AND json_extract(d.payload,'$.type')=?""",
        (data_type,),
    )
    for data_text, anchor_text in rows:
        data = decode_legacy_json(str(data_text))
        anchor = decode_legacy_json(str(anchor_text))
        if not isinstance(data, dict) or not isinstance(anchor, dict):
            continue
        if is_live(data, "/graph/data_objects") and is_live(anchor, "/graph/anchors"):
            anchor_key = anchor.get("type")
            if isinstance(anchor_key, str):
                permitted.add(anchor_key)
    return tuple(sorted(permitted))


def permitted_link_keys(connection, link_type: str, role: str, declared: object) -> tuple[str, ...]:
    permitted = set(_text_members(declared))
    endpoint_field = "source_uuid" if role == "source" else "target_uuid"
    for _key, pointer, raw in iter_category(connection, "sourceLink"):
        if (
            not isinstance(raw, dict)
            or not source_entry_live(connection, raw, pointer)
            or raw.get("type") != link_type
        ):
            continue
        endpoint = raw.get(endpoint_field)
        if not isinstance(endpoint, str):
            continue
        try:
            uuid = canonical_uuid(endpoint)
        except ValueError:
            continue
        endpoint_type = _live_endpoint_type(connection, uuid)
        if endpoint_type is not None:
            permitted.add(endpoint_type)
    return tuple(sorted(permitted))


def _live_endpoint_type(connection, uuid):
    matches: list[str] = []
    for category in ("sourceAnchor", "sourceData"):
        rows = connection.execute(
            f"SELECT source_pointer,payload FROM {STAGE_RELATION} WHERE category=? "
            "AND lower(json_extract(payload,'$.uuid'))=lower(?) ORDER BY ordinal LIMIT 2",
            (category, uuid),
        )
        for pointer, payload_text in rows:
            raw = decode_legacy_json(str(payload_text))
            if not isinstance(raw, dict) or not source_entry_live(connection, raw, str(pointer)):
                continue
            type_key = raw.get("type")
            if isinstance(type_key, str):
                matches.append(type_key)
    return matches[0] if len(matches) == 1 else None


def _text_members(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return ()
    return tuple(value)
