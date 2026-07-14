from __future__ import annotations

import copy
import math
import re
from collections.abc import Mapping
from uuid import UUID

from components.rtg.citation_resolution.protocol import (
    JsonObject,
    JsonValue,
    RtgCitationProjectionCatalog,
    RtgCitationProjectionRead,
    RtgCitationProjectionReader,
    RtgCitationProjectionSpec,
    RtgCitationResolutionInvalid,
    RtgCitationResolutionRecord,
    RtgCitationResolutionRequest,
)

_IDENTIFIER_PATTERN = re.compile(r"[a-zA-Z][a-zA-Z0-9_]*")


class DeterministicRtgCitationResolver:
    """Deterministic read-only graph-qualified citation resolver."""

    def __init__(
        self,
        catalog: RtgCitationProjectionCatalog,
        reader: RtgCitationProjectionReader,
    ) -> None:
        self._catalog = catalog
        self._reader = reader

    @classmethod
    def open(
        cls,
        catalog: RtgCitationProjectionCatalog,
        reader: RtgCitationProjectionReader,
    ) -> DeterministicRtgCitationResolver:
        return cls(catalog, reader)

    def resolve(self, request: RtgCitationResolutionRequest) -> RtgCitationResolutionRecord:
        graph_id = _validate_identifier(request.graph_id, "request.graph_id")
        local_uuid = _validate_uuid_text(request.local_uuid, "request.local_uuid")
        projection = self._catalog.get_projection(graph_id)
        if projection is None:
            return RtgCitationResolutionRecord(
                status="unsupported",
                graph_id=graph_id,
                local_uuid=local_uuid,
            )

        normalized_projection = _normalize_projection(projection)
        if normalized_projection.graph_id != graph_id:
            raise RtgCitationResolutionInvalid("projection graph_id must match request.graph_id")
        projection_read = _normalize_read(self._reader.read_projection(normalized_projection))
        if projection_read.projection != normalized_projection:
            raise RtgCitationResolutionInvalid(
                "projection reader must return the requested projection unchanged"
            )

        indexed_rows = tuple(
            (row, _anchor_uuid(row, normalized_projection.anchor_bucket))
            for row in projection_read.rows
        )
        matches = tuple(row for row, row_uuid in indexed_rows if row_uuid == local_uuid)
        return RtgCitationResolutionRecord(
            status="resolved" if matches else "not_found",
            graph_id=graph_id,
            local_uuid=local_uuid,
            query_name=normalized_projection.query_name,
            anchor_bucket=normalized_projection.anchor_bucket,
            records=copy.deepcopy(matches),
            provenance=copy.deepcopy(projection_read.provenance),
        )


def _normalize_projection(projection: RtgCitationProjectionSpec) -> RtgCitationProjectionSpec:
    return RtgCitationProjectionSpec(
        graph_id=_validate_identifier(projection.graph_id, "projection.graph_id"),
        query_name=_validate_identifier(projection.query_name, "projection.query_name"),
        anchor_bucket=_validate_identifier(
            projection.anchor_bucket,
            "projection.anchor_bucket",
        ),
    )


def _normalize_read(projection_read: RtgCitationProjectionRead) -> RtgCitationProjectionRead:
    return RtgCitationProjectionRead(
        projection=_normalize_projection(projection_read.projection),
        rows=tuple(_validate_json_object(row, "projection row") for row in projection_read.rows),
        provenance=_validate_json_object(projection_read.provenance, "projection provenance"),
    )


def _anchor_uuid(row: JsonObject, anchor_bucket: str) -> str:
    anchors = row.get("anchors")
    if not isinstance(anchors, dict):
        raise RtgCitationResolutionInvalid("projection row anchors must be a JSON object")
    value = anchors.get(anchor_bucket)
    if not isinstance(value, str):
        raise RtgCitationResolutionInvalid(
            f"projection row must return anchor bucket {anchor_bucket}"
        )
    try:
        return str(UUID(value))
    except ValueError as error:
        raise RtgCitationResolutionInvalid(
            f"projection row anchor bucket {anchor_bucket} must be a UUID"
        ) from error


def _validate_identifier(value: str, name: str) -> str:
    text = _validate_text(value, name)
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise RtgCitationResolutionInvalid(f"{name} must be an identifier")
    return text


def _validate_uuid_text(value: str, name: str) -> str:
    text = _validate_text(value, name)
    try:
        return str(UUID(text))
    except ValueError as error:
        raise RtgCitationResolutionInvalid(f"{name} must be a UUID") from error


def _validate_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgCitationResolutionInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _validate_json_object(value: JsonObject, name: str) -> JsonObject:
    copied = copy.deepcopy(value)
    if not isinstance(copied, dict):
        raise RtgCitationResolutionInvalid(f"{name} must be a JSON object")
    _validate_json_value(copied)
    return copied


def _validate_json_value(value: JsonValue) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RtgCitationResolutionInvalid("JSON object keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise RtgCitationResolutionInvalid("JSON numbers must be finite")
    if value is None or isinstance(value, str | int | float | bool):
        return
    raise RtgCitationResolutionInvalid("JSON values must be serializable")
