"""Independent validation and normalization of every v1 direct association."""

from __future__ import annotations

import sqlite3

from vellis.json_pointer import append_pointer
from vellis.v1_conversion_common import imported_uuid, is_live
from vellis.v1_import_domain import V1Disposition, V1ImportError
from vellis.v1_json import decode_legacy_json
from vellis.v1_report import add_disposition
from vellis.v1_stage import STAGE_RELATION, iter_category, put_payload


def convert_associations(connection) -> None:
    """Classify every source association before live object conversion selects rows."""
    for _key, pointer, raw in iter_category(connection, "sourceAssociation"):
        if not isinstance(raw, dict):
            _blocking(connection, pointer, "association is not an object")
            continue
        if isinstance(raw.get("shapeError"), str):
            _blocking(connection, pointer, str(raw["shapeError"]))
            continue
        try:
            anchor_uuid = imported_uuid(
                connection, raw["anchorUuid"], append_pointer(pointer, "anchorUuid")
            )
            data_uuid = imported_uuid(
                connection, raw["dataUuid"], append_pointer(pointer, "dataUuid")
            )
        except (KeyError, TypeError, ValueError, V1ImportError) as error:
            _blocking(connection, pointer, f"association has an invalid endpoint UUID: {error}")
            continue
        anchor = _one_source_endpoint(connection, "sourceAnchor", anchor_uuid)
        data = _one_source_endpoint(connection, "sourceData", data_uuid)
        if anchor is None or data is None:
            missing = anchor_uuid if anchor is None else data_uuid
            _blocking(connection, pointer, f"association endpoint {missing} is absent or ambiguous")
            continue
        try:
            live = is_live(anchor, pointer) and is_live(data, pointer)
        except (TypeError, ValueError) as error:
            _blocking(connection, pointer, f"association endpoint liveness is invalid: {error}")
            continue
        if not live:
            add_disposition(
                connection,
                V1Disposition.OMITTED,
                "non-live-association",
                pointer,
                "association with an explicitly non-live endpoint is omitted",
                target_uuid=data_uuid,
            )
            continue
        try:
            put_payload(
                connection,
                "candidateAssociation",
                f"{data_uuid}\x00{anchor_uuid}",
                pointer,
                {"anchorUuid": anchor_uuid, "dataUuid": data_uuid},
            )
            add_disposition(
                connection,
                V1Disposition.PRESERVED,
                "association-preserved",
                pointer,
                f"direct association from {anchor_uuid} to {data_uuid} is preserved",
                target_uuid=data_uuid,
            )
        except sqlite3.IntegrityError:
            _blocking(
                connection,
                pointer,
                f"association {data_uuid} to {anchor_uuid} is duplicated after UUID normalization",
                target_uuid=data_uuid,
            )


def _one_source_endpoint(connection, category, uuid):
    rows = connection.execute(
        f"SELECT payload FROM {STAGE_RELATION} WHERE category=? "
        "AND lower(json_extract(payload,'$.uuid'))=lower(?) ORDER BY ordinal LIMIT 2",
        (category, uuid),
    ).fetchall()
    if len(rows) != 1:
        return None
    value = decode_legacy_json(str(rows[0][0]))
    return value if isinstance(value, dict) else None


def _blocking(connection, pointer, summary, *, target_uuid=None):
    add_disposition(
        connection,
        V1Disposition.BLOCKING,
        "association-invalid",
        pointer,
        summary,
        target_uuid=target_uuid,
    )
