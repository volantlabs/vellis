"""Map candidate-validation findings back to exact v1 source locations."""

from __future__ import annotations

import sqlite3

from vellis.domain import Finding
from vellis.json_pointer import append_pointer
from vellis.v1_identity import source_entry_live
from vellis.v1_json import decode_legacy_json
from vellis.v1_stage import STAGE_RELATION


def finding_source_pointer(connection: sqlite3.Connection, finding: Finding) -> str:
    """Return source provenance without retaining a source-wide lookup in memory."""
    pointer = finding.path or ""
    mapped = _cardinality_pointer(connection, finding)
    if mapped is not None:
        return mapped
    if pointer.startswith("/objects/"):
        return _object_pointer(connection, pointer, finding)
    if pointer.startswith("/definitions/"):
        return _definition_pointer(connection, pointer, finding)
    return "/"


def finding_targets(connection: sqlite3.Connection, finding: Finding):
    """Return affected v2 identity fields, never a referenced identity by accident."""
    parts = _parts(finding.path or "")
    if len(parts) >= 2 and parts[0] == "objects":
        row = _candidate_row(connection, "candidateObject", parts[1])
        payload = {} if row is None else row[1]
        property_name = _path_property_name(connection, payload, parts)
        type_key = payload.get("typeKey")
        return (
            parts[1],
            type_key if isinstance(type_key, str) else None,
            property_name or None,
        )
    if len(parts) >= 2 and parts[0] == "definitions":
        key = _affected_definition_key(connection, parts, finding)
        row = _candidate_row(connection, "candidateDefinition", key)
        payload = {} if row is None else row[1]
        property_name = _path_property_name(connection, payload, parts)
        return None, key or None, property_name or None
    return None, None, None


def _cardinality_pointer(connection, finding):
    role = next(
        (
            role
            for text, role in (
                ("anchors per object", "anchorsPerObject"),
                ("objects per anchor", "objectsPerAnchor"),
                ("links per source", "linksPerSource"),
                ("links per target", "linksPerTarget"),
            )
            if text in finding.summary
        ),
        None,
    )
    if role is None or not finding.type_keys:
        return None
    row = connection.execute(
        f"SELECT source_pointer FROM {STAGE_RELATION} "
        "WHERE category='mappedBound' AND natural_key=?",
        (f"{finding.type_keys[0]}\x00{role}",),
    ).fetchone()
    return None if row is None else str(row[0])


def _object_pointer(connection, path, finding):
    parts = _parts(path)
    if len(parts) < 2:
        return "/"
    row = _candidate_row(connection, "candidateObject", parts[1])
    if row is None:
        return "/"
    source, payload = row
    if len(parts) == 2:
        return source
    field = parts[2]
    raw_field = {
        "typeKey": "type",
        "displayName": "display_name",
        "sourceUuid": "source_uuid",
        "targetUuid": "target_uuid",
        "uuid": "uuid",
    }.get(field)
    if raw_field is not None:
        return append_pointer(source, raw_field)
    if field == "properties" and len(parts) >= 4:
        name = _path_property_name(connection, payload, parts)
        if name is not None:
            return append_pointer(source, "properties", name)
    if field == "anchorUuids":
        index = parts[3] if len(parts) >= 4 else None
        return _association_pointer(connection, parts[1], index, finding.uuids) or source
    return source


def _definition_pointer(connection, path, finding):
    parts = _parts(path)
    if len(parts) < 2:
        return "/"
    key = _affected_definition_key(connection, parts, finding)
    row = _candidate_row(connection, "candidateDefinition", key)
    if row is None:
        return "/"
    source, payload = row
    if len(parts) == 2:
        return source
    field = parts[2]
    property_pointer = _definition_property_pointer(source, payload, field, parts)
    if property_pointer is not None:
        return property_pointer
    raw_fields = {
        "description": ("description",),
        "permittedAnchorTypeKeys": ("payload",),
        "permittedSourceTypeKeys": ("payload", "allowed_source_types"),
        "permittedTargetTypeKeys": ("payload", "allowed_target_types"),
    }.get(field)
    if raw_fields is not None:
        if field.startswith("permitted") and finding.type_keys:
            member = _permitted_member_pointer(connection, key, field, finding.type_keys[0])
            if member is not None:
                return member
        suffix = _definition_member_suffix(payload, field, parts, finding)
        return append_pointer(source, *raw_fields) + suffix
    return source


def _definition_property_pointer(source, payload, field, parts):
    if field != "properties" or len(parts) < 4:
        return None
    name = _property_member(payload.get("properties"), parts[3])
    if name is None:
        return None
    suffix = "" if len(parts) < 5 else append_pointer("", _definition_property_field(parts[4]))
    return append_pointer(source, "payload", "properties", name) + suffix


def _definition_member_suffix(payload, field, parts, finding):
    if len(parts) >= 4:
        return append_pointer("", parts[3])
    if not field.startswith("permitted") or not finding.type_keys:
        return ""
    members = payload.get(field)
    if isinstance(members, list) and finding.type_keys[0] in members:
        return append_pointer("", members.index(finding.type_keys[0]))
    return ""


def _permitted_member_pointer(connection, type_key, field, member):
    if field == "permittedAnchorTypeKeys":
        return _data_population_pointer(connection, type_key, member)
    role = "source" if field == "permittedSourceTypeKeys" else "target"
    declared = _declared_link_member_pointer(connection, type_key, role, member)
    return declared or _inferred_link_member_pointer(connection, type_key, role, member)


def _data_population_pointer(connection, data_type, member):
    for pointer, raw in _source_rows(connection, "sourceDefinition"):
        if (
            not source_entry_live(connection, raw, pointer)
            or raw.get("kind") != "anchor"
            or raw.get("type_key") != member
        ):
            continue
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            continue
        for name in ("required_data_types", "optional_data_types"):
            values = payload.get(name)
            if isinstance(values, list) and data_type in values:
                return append_pointer(pointer, "payload", name, values.index(data_type))
    row = connection.execute(
        f"""SELECT a.source_pointer FROM {STAGE_RELATION} a
            JOIN {STAGE_RELATION} x ON x.category='candidateAssociation'
              AND lower(json_extract(x.payload,'$.anchorUuid'))
                  =lower(json_extract(a.payload,'$.uuid'))
            JOIN {STAGE_RELATION} d ON d.category='sourceData'
              AND lower(json_extract(x.payload,'$.dataUuid'))
                  =lower(json_extract(d.payload,'$.uuid'))
            WHERE a.category='sourceAnchor' AND json_extract(a.payload,'$.type')=?
              AND json_extract(d.payload,'$.type')=? ORDER BY a.ordinal LIMIT 1""",
        (member, data_type),
    ).fetchone()
    return None if row is None else append_pointer(str(row[0]), "type")


def _declared_link_member_pointer(connection, link_type, role, member):
    source_name = f"allowed_{role}_types"
    for pointer, raw in _source_rows(connection, "sourceDefinition"):
        if (
            not source_entry_live(connection, raw, pointer)
            or raw.get("kind") != "link"
            or raw.get("type_key") != link_type
        ):
            continue
        payload = raw.get("payload")
        if not isinstance(payload, dict):
            return None
        values = payload.get(source_name)
        if isinstance(values, list) and member in values:
            return append_pointer(pointer, "payload", source_name, values.index(member))
    return None


def _inferred_link_member_pointer(connection, link_type, role, member):
    endpoint_name = f"{role}_uuid"
    for _pointer, link in _source_rows(connection, "sourceLink"):
        if (
            not source_entry_live(connection, link, _pointer)
            or link.get("type") != link_type
            or not isinstance(link.get(endpoint_name), str)
        ):
            continue
        endpoint = str(link[endpoint_name]).lower()
        for category in ("sourceAnchor", "sourceData"):
            for pointer, value in _source_rows(connection, category):
                uuid = value.get("uuid")
                if (
                    source_entry_live(connection, value, pointer)
                    and isinstance(uuid, str)
                    and uuid.lower() == endpoint
                    and value.get("type") == member
                ):
                    return append_pointer(pointer, "type")
    return None


def _source_rows(connection, category):
    rows = connection.execute(
        f"SELECT source_pointer,payload FROM {STAGE_RELATION} WHERE category=? ORDER BY ordinal",
        (category,),
    )
    for pointer, payload_text in rows:
        payload = decode_legacy_json(str(payload_text))
        if isinstance(payload, dict):
            yield str(pointer), payload


def _candidate_row(connection, category, key):
    row = connection.execute(
        f"SELECT source_pointer,payload FROM {STAGE_RELATION} WHERE category=? AND natural_key=?",
        (category, key),
    ).fetchone()
    if row is None:
        return None
    payload = decode_legacy_json(str(row[1]))
    return str(row[0]), payload if isinstance(payload, dict) else {}


def _association_pointer(connection, data_uuid, index, uuids):
    offset = _optional_index(index)
    anchor_uuid = next((uuid for uuid in uuids if uuid != data_uuid), None)
    if offset is None and anchor_uuid is None:
        return None
    where = "AND json_extract(payload,'$.anchorUuid')=?" if anchor_uuid is not None else ""
    parameters = (data_uuid, anchor_uuid) if anchor_uuid is not None else (data_uuid, offset)
    suffix = "LIMIT 1" if anchor_uuid is not None else "ORDER BY payload LIMIT 1 OFFSET ?"
    row = connection.execute(
        f"SELECT source_pointer FROM {STAGE_RELATION} "
        "WHERE category='candidateAssociation' "
        f"AND json_extract(payload,'$.dataUuid')=? {where} {suffix}",
        parameters,
    ).fetchone()
    return None if row is None else str(row[0])


def _property_member(value, index):
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict) and item.get("name") == index:
            return index
    try:
        item = value[int(index)]
    except ValueError:
        return index
    except IndexError:
        return None
    if not isinstance(item, dict) or not isinstance(item.get("name"), str):
        return None
    return str(item["name"])


def _path_property_name(connection, payload, parts):
    if len(parts) < 4 or parts[2] != "properties":
        return None
    segment = parts[3]
    if _has_property_name(payload.get("properties"), segment):
        return segment
    type_key = payload.get("typeKey")
    if isinstance(type_key, str):
        row = _candidate_row(connection, "candidateDefinition", type_key)
        if row is not None and _has_property_name(row[1].get("properties"), segment):
            return segment
    if not segment.isdigit():
        return segment
    return _property_member(payload.get("properties"), segment)


def _affected_definition_key(connection, parts, finding):
    key = parts[1]
    if _candidate_row(connection, "candidateDefinition", key) is not None:
        return key
    offset = _optional_index(key)
    if offset is not None:
        row = connection.execute(
            f"SELECT natural_key FROM {STAGE_RELATION} "
            "WHERE category='candidateDefinition' ORDER BY natural_key LIMIT 1 OFFSET ?",
            (offset,),
        ).fetchone()
        if row is not None:
            return str(row[0])
    if len(parts) < 3 or not finding.type_keys:
        return ""
    field = parts[2]
    candidates = [
        candidate[0]
        for candidate in _candidate_definition_members(connection, field)
        if finding.type_keys[0] in candidate[1]
    ]
    return candidates[0] if len(candidates) == 1 else ""


def _candidate_definition_members(connection, field):
    rows = connection.execute(
        f"SELECT natural_key,payload FROM {STAGE_RELATION} "
        "WHERE category='candidateDefinition' ORDER BY natural_key"
    )
    for key, payload_text in rows:
        payload = decode_legacy_json(str(payload_text))
        if not isinstance(payload, dict):
            continue
        members = payload.get(field)
        if isinstance(members, list):
            yield str(key), members


def _optional_index(value):
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _has_property_name(value, name):
    return isinstance(value, list) and any(
        isinstance(item, dict) and item.get("name") == name for item in value
    )


def _definition_property_field(field: str) -> str:
    return {
        "allowedValues": "allowed_values",
        "minimumLength": "minimum_length",
        "maximumLength": "maximum_length",
        "valueKind": "value_kinds",
    }.get(field, field)


def _parts(pointer):
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")[1:]]
