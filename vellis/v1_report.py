"""Deterministic complete v1 disposition reporting."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from vellis.domain import canonical_uuid
from vellis.v1_import_domain import V1Counts, V1Disposition, V1DispositionCounts
from vellis.v1_json import decode_legacy_json
from vellis.v1_stage import STAGE_RELATION, put_payload


def add_disposition(
    connection,
    disposition: V1Disposition,
    code: str,
    source_pointer: str,
    summary: str,
    *,
    target_uuid: object | None = None,
    target_type_key: object | None = None,
    target_property: object | None = None,
) -> None:
    normalized_uuid = _target_uuid(target_uuid)
    normalized_type = _target_text(target_type_key)
    normalized_property = _target_text(target_property)
    ordinal = int(
        connection.execute(
            f"SELECT count(*) FROM {STAGE_RELATION} WHERE category='disposition'"
        ).fetchone()[0]
    )
    payload = {
        "disposition": disposition.value,
        "code": code,
        "sourcePointer": source_pointer,
        "summary": summary,
    }
    for key, value in (
        ("targetUuid", normalized_uuid),
        ("targetTypeKey", normalized_type),
        ("targetProperty", normalized_property),
    ):
        if value is not None:
            payload[key] = value
    put_payload(connection, "disposition", code, source_pointer, payload, ordinal=ordinal)


def _target_uuid(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return canonical_uuid(value)
    except ValueError:
        return None


def _target_text(value: object) -> str | None:
    return value if isinstance(value, str) and value != "" else None


def disposition_counts(connection) -> V1DispositionCounts:
    values = {value.value: 0 for value in V1Disposition}
    rows = connection.execute(f"SELECT payload FROM {STAGE_RELATION} WHERE category='disposition'")
    for row in rows:
        payload = decode_legacy_json(str(row[0]))
        assert isinstance(payload, dict)
        values[str(payload["disposition"])] += 1
    return V1DispositionCounts(
        values["preserved"], values["converted"], values["omitted"], values["blocking"]
    )


def render_machine_report(
    connection,
    path: Path,
    *,
    source_sha256: str,
    source_byte_count: int,
    candidate_sha256: str,
    counts: V1Counts,
) -> str:
    summary = disposition_counts(connection)
    digest = hashlib.sha256()
    with path.open("wb") as raw:
        os.chmod(path, 0o600)

        def write(value: str) -> None:
            encoded = value.encode("utf-8")
            raw.write(encoded)
            digest.update(encoded)

        prefix = {
            "format": "vellis-v1-import-report",
            "version": 1,
            "source": {"sha256": source_sha256, "byteCount": source_byte_count},
            "candidate": {
                "digest": candidate_sha256,
                "counts": {
                    "definitions": counts.definitions,
                    "anchors": counts.anchors,
                    "associatedData": counts.associated_data,
                    "links": counts.links,
                },
            },
            "summary": {
                "preserved": summary.preserved,
                "converted": summary.converted,
                "omitted": summary.omitted,
                "blocking": summary.blocking,
            },
        }
        text = json.dumps(prefix, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        write(text[:-1] + ',"dispositions":[')
        first = True
        for value in _ordered_dispositions(connection):
            if not first:
                write(",")
            first = False
            write(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        write("]}")
        raw.flush()
        os.fsync(raw.fileno())
    return digest.hexdigest()


def write_human_report(
    connection, path: Path, *, source_sha256: str, candidate_sha256: str
) -> None:
    counts = disposition_counts(connection)
    with path.open("w", encoding="utf-8") as output:
        os.chmod(path, 0o600)
        output.write("Vellis v1 import preview\n")
        output.write(f"source sha256: {source_sha256}\n")
        output.write(f"candidate sha256: {candidate_sha256}\n")
        output.write(
            "dispositions: "
            f"preserved={counts.preserved}, converted={counts.converted}, "
            f"omitted={counts.omitted}, blocking={counts.blocking}\n"
        )
        for value in _ordered_dispositions(connection):
            identity = " | ".join(
                f"{label}={value[key]}"
                for key, label in (
                    ("targetUuid", "uuid"),
                    ("targetTypeKey", "type"),
                    ("targetProperty", "property"),
                )
                if key in value
            )
            separator = f" | {identity}" if identity else ""
            output.write(
                f"- [{value['disposition']}] {value['sourcePointer']}{separator} "
                f"| {value['code']}: {value['summary']}\n"
            )
        output.flush()
        os.fsync(output.fileno())


def _ordered_dispositions(connection):
    rows = connection.execute(
        f"SELECT payload FROM {STAGE_RELATION} WHERE category='disposition' "
        "ORDER BY source_pointer,"
        "coalesce(json_extract(payload,'$.targetUuid'),''),"
        "coalesce(json_extract(payload,'$.targetTypeKey'),''),"
        "coalesce(json_extract(payload,'$.targetProperty'),''),"
        "json_extract(payload,'$.code'),payload,ordinal"
    )
    for row in rows:
        value = decode_legacy_json(str(row[0]))
        assert isinstance(value, dict)
        yield value
