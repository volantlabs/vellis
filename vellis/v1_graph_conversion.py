"""One-object-at-a-time v1 graph conversion into candidate staging rows."""

from __future__ import annotations

import math
import sqlite3
from decimal import Decimal

from vellis.domain import (
    SAFE_INTEGER_MAXIMUM,
    SAFE_INTEGER_MINIMUM,
    Anchor,
    AssociatedData,
    AssociatedDataTypeDefinition,
    Link,
    ScalarValue,
    ValueKind,
)
from vellis.v1_candidate import iter_definitions, stage_object
from vellis.v1_conversion_common import (
    imported_uuid,
    legacy_system,
    omit_nonlive,
    required_text,
)
from vellis.v1_identity import identity_conflicted, source_entry_live
from vellis.v1_import_domain import V1Disposition, V1ImportError
from vellis.v1_json import canonical_legacy_json, decode_legacy_json
from vellis.v1_pointer import append_pointer
from vellis.v1_report import add_disposition
from vellis.v1_stage import STAGE_RELATION, iter_category


def convert_graph(connection) -> None:
    _convert_anchors(connection)
    _convert_data(connection)
    _convert_links(connection)
    migration_count = int(
        connection.execute(
            f"SELECT count(*) FROM {STAGE_RELATION} WHERE category='sourceMigration'"
        ).fetchone()[0]
    )
    if migration_count:
        add_disposition(
            connection,
            V1Disposition.OMITTED,
            "v1-history-omitted",
            "/migration/migrations",
            f"{migration_count} predecessor migration records are not imported",
        )


def _convert_anchors(connection) -> None:
    for _key, pointer, raw in iter_category(connection, "sourceAnchor"):
        if not isinstance(raw, dict):
            continue
        live = source_entry_live(connection, raw, pointer)
        if live is None:
            continue
        if not live:
            omit_nonlive(connection, "anchor", pointer, raw.get("uuid"))
            continue
        try:
            source_uuid = raw.get("uuid")
            uuid = imported_uuid(connection, source_uuid, append_pointer(pointer, "uuid"))
            if identity_conflicted(connection, "graph", uuid):
                continue
            value = Anchor(
                uuid,
                required_text(raw, "type", pointer),
                required_text(raw, "display_name", pointer),
                legacy_system(raw, pointer),
            )
            stage_object(connection, value, pointer)
            _preserved(connection, pointer, value.uuid, "anchor")
        except (sqlite3.IntegrityError, TypeError, ValueError, V1ImportError) as error:
            _blocking(connection, pointer, raw.get("uuid"), error)


def _convert_data(connection) -> None:
    for _key, pointer, raw in iter_category(connection, "sourceData"):
        if not isinstance(raw, dict):
            continue
        live = source_entry_live(connection, raw, pointer)
        if live is None:
            continue
        if not live:
            omit_nonlive(connection, "associated-data object", pointer, raw.get("uuid"))
            continue
        try:
            source_uuid = raw.get("uuid")
            uuid = imported_uuid(connection, source_uuid, append_pointer(pointer, "uuid"))
            if identity_conflicted(connection, "graph", uuid):
                continue
            type_key = required_text(raw, "type", pointer)
            definition = _data_definition(connection, type_key)
            anchors = _live_associations(connection, uuid)
            properties = _properties(connection, raw, definition, pointer)
            value = AssociatedData(
                uuid,
                type_key,
                anchors,
                properties,
                legacy_system(raw, pointer),
            )
            stage_object(connection, value, pointer)
            _preserved(connection, pointer, value.uuid, "associated-data object")
        except (sqlite3.IntegrityError, TypeError, ValueError, V1ImportError) as error:
            _blocking(connection, pointer, raw.get("uuid"), error)


def _convert_links(connection) -> None:
    for _key, pointer, raw in iter_category(connection, "sourceLink"):
        if not isinstance(raw, dict):
            continue
        live = source_entry_live(connection, raw, pointer)
        if live is None:
            continue
        if not live:
            omit_nonlive(connection, "link", pointer, raw.get("uuid"))
            continue
        try:
            uuid = imported_uuid(connection, raw.get("uuid"), append_pointer(pointer, "uuid"))
            if identity_conflicted(connection, "graph", uuid):
                continue
            value = Link(
                uuid,
                required_text(raw, "type", pointer),
                imported_uuid(
                    connection, raw.get("source_uuid"), append_pointer(pointer, "source_uuid")
                ),
                imported_uuid(
                    connection, raw.get("target_uuid"), append_pointer(pointer, "target_uuid")
                ),
                legacy_system(raw, pointer),
            )
            stage_object(connection, value, pointer)
            _preserved(connection, pointer, value.uuid, "link")
        except (sqlite3.IntegrityError, TypeError, ValueError, V1ImportError) as error:
            _blocking(connection, pointer, raw.get("uuid"), error)


def _data_definition(connection, type_key):
    for definition in iter_definitions(connection):
        if definition.type_key == type_key:
            if not isinstance(definition, AssociatedDataTypeDefinition):
                raise V1ImportError(f"{type_key} is not an associated-data type")
            return definition
    raise V1ImportError(f"live object uses unresolved type {type_key}")


def _live_associations(connection, data_uuid):
    rows = connection.execute(
        f"SELECT source_pointer,payload FROM {STAGE_RELATION} "
        "WHERE category='candidateAssociation' "
        "AND json_extract(payload,'$.dataUuid')=? ORDER BY payload",
        (data_uuid,),
    )
    values = []
    for pointer, payload_text in rows:
        payload = decode_legacy_json(str(payload_text))
        assert isinstance(payload, dict)
        source_uuid = payload.get("anchorUuid")
        values.append(imported_uuid(connection, source_uuid, str(pointer)))
    if not values:
        raise V1ImportError(f"live associated-data object {data_uuid} has no live anchor")
    if len(values) != len(set(values)):
        raise V1ImportError(f"live associated-data object {data_uuid} has duplicate anchors")
    return tuple(sorted(values))


def _properties(connection, raw, definition, pointer):
    values = raw.get("properties", {})
    if not isinstance(values, dict):
        raise V1ImportError(f"{pointer}/properties is not an object")
    rules = {rule.name: rule for rule in definition.properties}
    result = []
    for name in sorted(values):
        rule = rules.get(name)
        if rule is None:
            raise V1ImportError(f"{append_pointer(pointer, 'properties', name)} is undeclared")
        force_json_text = _converted_property(connection, definition.type_key, name)
        result.append(
            (
                name,
                _property_value(values[name], rule.value_kind, rule.nullable, force_json_text),
            )
        )
    return tuple(result)


def _converted_property(connection, type_key, name):
    row = connection.execute(
        f"SELECT 1 FROM {STAGE_RELATION} WHERE category='disposition' "
        "AND json_extract(payload,'$.code')='property-json-text' "
        "AND json_extract(payload,'$.targetTypeKey')=? "
        "AND json_extract(payload,'$.targetProperty')=?",
        (type_key, name),
    ).fetchone()
    return row is not None


def _property_value(value, kind, nullable, force_json_text):
    if force_json_text:
        return ScalarValue.text(canonical_legacy_json(value))
    if value is None:
        if nullable:
            return None
        if kind is ValueKind.TEXT:
            return ScalarValue.text("null")
        raise V1ImportError("null occurs in a non-nullable imported property")
    numeric = _native_numeric(value, kind)
    if numeric is not None:
        return numeric
    if kind is ValueKind.BOOLEAN and type(value) is bool:
        return ScalarValue.boolean(value)
    if kind is ValueKind.TEXT:
        if isinstance(value, str):
            return ScalarValue.text(value)
        return ScalarValue.text(canonical_legacy_json(value))
    raise V1ImportError(f"legacy value is incompatible with inferred {kind.value} property")


def _native_numeric(value, kind):
    if kind is ValueKind.INTEGER and type(value) is int:
        if SAFE_INTEGER_MINIMUM <= value <= SAFE_INTEGER_MAXIMUM:
            return ScalarValue.integer(value)
    if kind is ValueKind.NUMBER and (type(value) is int or isinstance(value, Decimal)):
        converted = float(value)
        if math.isfinite(converted):
            return ScalarValue.number(converted)
    return None


def _preserved(connection, pointer, uuid, label):
    add_disposition(
        connection,
        V1Disposition.PRESERVED,
        "graph-object-preserved",
        pointer,
        f"live {label} {uuid} is preserved",
        target_uuid=uuid,
    )


def _blocking(connection, pointer, uuid, error):
    add_disposition(
        connection,
        V1Disposition.BLOCKING,
        "graph-object-invalid",
        pointer,
        str(error),
        target_uuid=uuid,
    )
