"""Shared one-entry conversion helpers for the v1 import boundary."""

from __future__ import annotations

from collections.abc import Mapping

from vellis.domain import SystemEnvelope, canonical_uuid
from vellis.v1_import_domain import V1Disposition, V1ImportError
from vellis.v1_json import canonical_legacy_json
from vellis.v1_pointer import append_pointer
from vellis.v1_report import add_disposition


def is_live(value: Mapping[str, object], pointer: str) -> bool:
    system = value.get("system", {})
    if not isinstance(system, dict):
        raise V1ImportError(f"{append_pointer(pointer, 'system')} is not an object")
    live = system.get("live", True)
    if type(live) is not bool:
        raise V1ImportError(f"{append_pointer(pointer, 'system', 'live')} is not Boolean")
    return live


def legacy_system(value: Mapping[str, object], pointer: str) -> SystemEnvelope:
    system = value.get("system", {})
    if not isinstance(system, dict):
        raise V1ImportError(f"{append_pointer(pointer, 'system')} is not an object")
    retained = {key: item for key, item in system.items() if key != "live"}
    legacy = canonical_legacy_json(retained) if retained else None
    return SystemEnvelope(0, 0, legacy)


def required_text(value: Mapping[str, object], name: str, pointer: str) -> str:
    item = value.get(name)
    if not isinstance(item, str) or item == "":
        raise V1ImportError(f"{append_pointer(pointer, name)} must be nonempty text")
    return item


def imported_uuid(connection, value: object, pointer: str) -> str:
    if not isinstance(value, str):
        raise V1ImportError(f"{pointer} is not a UUID string")
    canonical = canonical_uuid(value)
    if canonical != value and not _normalization_reported(connection, pointer, canonical):
        add_disposition(
            connection,
            V1Disposition.CONVERTED,
            "uuid-normalized",
            pointer,
            f"UUID spelling {value!r} was normalized to {canonical}",
            target_uuid=canonical,
        )
    return canonical


def _normalization_reported(connection, pointer: str, canonical: str) -> bool:
    from vellis.v1_stage import STAGE_RELATION

    row = connection.execute(
        f"SELECT 1 FROM {STAGE_RELATION} WHERE category='disposition' "
        "AND source_pointer=? AND json_extract(payload,'$.code')='uuid-normalized' "
        "AND json_extract(payload,'$.targetUuid')=? LIMIT 1",
        (pointer, canonical),
    ).fetchone()
    return row is not None


def omit_nonlive(connection, category: str, pointer: str, identity: object) -> None:
    add_disposition(
        connection,
        V1Disposition.OMITTED,
        "non-live",
        pointer,
        f"non-live v1 {category} {identity!r} is omitted",
    )
