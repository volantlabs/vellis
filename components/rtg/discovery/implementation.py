from __future__ import annotations

import copy
import math
from collections.abc import Mapping

from components.rtg.discovery.protocol import (
    JsonObject,
    JsonValue,
    RtgDiscoveryCell,
    RtgDiscoveryCoordinates,
    RtgDiscoverySelection,
    RtgDiscoverySelectionInvalid,
    RtgDiscoveryView,
    RtgDiscoveryViewInvalid,
    RtgDiscoveryViewList,
    RtgDiscoveryViewNotFound,
)


class InMemoryRtgDiscovery:
    """In-memory implementation of the RTG Discovery component."""

    def __init__(self) -> None:
        self._views: dict[str, RtgDiscoveryView] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgDiscovery:
        return cls()

    def put_view(self, view: RtgDiscoveryView) -> RtgDiscoveryView:
        normalized = _normalize_view(view)
        self._views[normalized.view_id] = normalized
        return _copy_view(normalized)

    def list_views(self) -> RtgDiscoveryViewList:
        return RtgDiscoveryViewList(
            views=tuple(
                _copy_view(view)
                for view in sorted(self._views.values(), key=lambda item: item.view_id)
            )
        )

    def select_anchor_types(
        self,
        view_id: str,
        coordinates: tuple[RtgDiscoveryCoordinates, ...],
    ) -> RtgDiscoverySelection:
        normalized_view_id = _validate_selection_text(view_id, "view_id")
        try:
            view = self._views[normalized_view_id]
        except KeyError as error:
            raise RtgDiscoveryViewNotFound(normalized_view_id) from error
        selected = _normalize_coordinates(coordinates)
        cell_index = {
            RtgDiscoveryCoordinates(cell.row_key, cell.column_key): cell for cell in view.cells
        }
        anchor_type_keys: list[str] = []
        seen_anchor_type_keys: set[str] = set()
        descriptions: dict[RtgDiscoveryCoordinates, str] = {}
        for coordinate in selected:
            if coordinate.row_key not in view.row_labels:
                raise RtgDiscoverySelectionInvalid(f"unknown row_key: {coordinate.row_key}")
            if coordinate.column_key not in view.column_labels:
                raise RtgDiscoverySelectionInvalid(f"unknown column_key: {coordinate.column_key}")
            try:
                cell = cell_index[coordinate]
            except KeyError as error:
                raise RtgDiscoverySelectionInvalid(
                    f"no discovery cell for {coordinate.row_key}/{coordinate.column_key}"
                ) from error
            descriptions[coordinate] = cell.description
            for anchor_type_key in cell.anchor_type_keys:
                if anchor_type_key not in seen_anchor_type_keys:
                    seen_anchor_type_keys.add(anchor_type_key)
                    anchor_type_keys.append(anchor_type_key)
        return RtgDiscoverySelection(
            view_id=view.view_id,
            coordinates=selected,
            anchor_type_keys=tuple(anchor_type_keys),
            cell_descriptions=descriptions,
        )


def _normalize_view(view: RtgDiscoveryView) -> RtgDiscoveryView:
    row_labels = _validate_labels(view.row_labels, "row_labels")
    column_labels = _validate_labels(view.column_labels, "column_labels")
    cells = tuple(_normalize_cell(cell, row_labels, column_labels) for cell in view.cells)
    coordinates: set[RtgDiscoveryCoordinates] = set()
    for cell in cells:
        coordinate = RtgDiscoveryCoordinates(cell.row_key, cell.column_key)
        if coordinate in coordinates:
            raise RtgDiscoveryViewInvalid(
                f"duplicate discovery cell: {cell.row_key}/{cell.column_key}"
            )
        coordinates.add(coordinate)
    return RtgDiscoveryView(
        view_id=_validate_text(view.view_id, "view_id"),
        description=_validate_text(view.description, "description"),
        row_labels=row_labels,
        column_labels=column_labels,
        cells=cells,
        metadata=_validate_metadata(view.metadata),
    )


def _normalize_cell(
    cell: RtgDiscoveryCell,
    row_labels: dict[str, str],
    column_labels: dict[str, str],
) -> RtgDiscoveryCell:
    row_key = _validate_text(cell.row_key, "row_key")
    column_key = _validate_text(cell.column_key, "column_key")
    if row_key not in row_labels:
        raise RtgDiscoveryViewInvalid(f"cell row_key is not declared: {row_key}")
    if column_key not in column_labels:
        raise RtgDiscoveryViewInvalid(f"cell column_key is not declared: {column_key}")
    return RtgDiscoveryCell(
        row_key=row_key,
        column_key=column_key,
        description=_validate_text(cell.description, "cell description"),
        anchor_type_keys=tuple(
            _validate_text(anchor_type_key, "anchor_type_key")
            for anchor_type_key in cell.anchor_type_keys
        ),
    )


def _normalize_coordinates(
    coordinates: tuple[RtgDiscoveryCoordinates, ...],
) -> tuple[RtgDiscoveryCoordinates, ...]:
    if not coordinates:
        raise RtgDiscoverySelectionInvalid("at least one coordinate is required")
    selected: list[RtgDiscoveryCoordinates] = []
    seen: set[RtgDiscoveryCoordinates] = set()
    for coordinate in coordinates:
        normalized = RtgDiscoveryCoordinates(
            row_key=_validate_selection_text(coordinate.row_key, "row_key"),
            column_key=_validate_selection_text(coordinate.column_key, "column_key"),
        )
        if normalized in seen:
            raise RtgDiscoverySelectionInvalid(
                f"duplicate coordinate: {normalized.row_key}/{normalized.column_key}"
            )
        seen.add(normalized)
        selected.append(normalized)
    return tuple(selected)


def _validate_labels(value: Mapping[str, str], name: str) -> dict[str, str]:
    if not value:
        raise RtgDiscoveryViewInvalid(f"{name} must not be empty")
    return {
        _validate_text(key, f"{name} key"): _validate_text(label, f"{name} label")
        for key, label in value.items()
    }


def _validate_metadata(value: JsonObject) -> JsonObject:
    metadata = copy.deepcopy(value)
    if not isinstance(metadata, dict):
        raise RtgDiscoveryViewInvalid("metadata must be a JSON object")
    _validate_json_value(metadata)
    return metadata


def _validate_json_value(value: JsonValue) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise RtgDiscoveryViewInvalid("metadata keys must be strings")
            _validate_json_value(item)
        return
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item)
        return
    if isinstance(value, float) and not math.isfinite(value):
        raise RtgDiscoveryViewInvalid("metadata numbers must be finite")
    if value is None or isinstance(value, str | int | float | bool):
        return
    raise RtgDiscoveryViewInvalid("metadata values must be JSON-serializable")


def _validate_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgDiscoveryViewInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _validate_selection_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RtgDiscoverySelectionInvalid(f"{name} must be a non-empty string")
    return value.strip()


def _copy_view(view: RtgDiscoveryView) -> RtgDiscoveryView:
    return copy.deepcopy(view)
