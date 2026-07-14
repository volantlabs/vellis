from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import replace

from components.app.catalog.protocol import (
    AppDescriptor,
    AppDescriptorInvalid,
    AppDescriptorList,
    AppIdConflict,
    AppNotFound,
    CatalogQuery,
    JsonValue,
    LaunchSurface,
)

_LAUNCH_SURFACE_MODES = {"launch", "attach", "launch_or_attach"}
_RUNTIME_CONTROL_VALUES = {"handoff", "managed"}


class InMemoryAppCatalog:
    """In-memory implementation of the App Catalog component."""

    def __init__(self, descriptors: Iterable[AppDescriptor] | None = None) -> None:
        self._descriptors: dict[str, AppDescriptor] = {}
        if descriptors is None:
            return
        seen: set[str] = set()
        for descriptor in descriptors:
            normalized = self._normalize_descriptor(descriptor)
            if normalized.app_id in seen:
                raise AppIdConflict(f"duplicate app_id in descriptor store: {normalized.app_id}")
            seen.add(normalized.app_id)
            self._descriptors[normalized.app_id] = normalized

    @classmethod
    def open(cls, descriptor_store: Iterable[AppDescriptor] | None = None) -> InMemoryAppCatalog:
        return cls(descriptor_store)

    def register_app(self, app_descriptor: AppDescriptor) -> AppDescriptor:
        normalized = self._normalize_descriptor(app_descriptor)
        self._descriptors[normalized.app_id] = normalized
        return normalized

    def remove_app(self, app_id: str) -> AppDescriptor:
        self._validate_identifier(app_id, "app_id")
        try:
            return self._descriptors.pop(app_id)
        except KeyError as error:
            raise AppNotFound(app_id) from error

    def get_app(self, app_id: str) -> AppDescriptor:
        self._validate_identifier(app_id, "app_id")
        try:
            return self._copy_descriptor(self._descriptors[app_id])
        except KeyError as error:
            raise AppNotFound(app_id) from error

    def list_apps(self, catalog_query: CatalogQuery | None = None) -> AppDescriptorList:
        query = catalog_query or CatalogQuery()
        apps = tuple(
            self._copy_descriptor(descriptor)
            for descriptor in sorted(self._descriptors.values(), key=lambda item: item.app_id)
            if self._matches_query(descriptor, query)
        )
        return AppDescriptorList(apps=apps)

    @classmethod
    def _normalize_descriptor(cls, descriptor: AppDescriptor) -> AppDescriptor:
        app_id = cls._validate_identifier(descriptor.app_id, "app_id")
        title = cls._validate_required_text(descriptor.title, "title")
        summary = cls._validate_text(descriptor.summary, "summary")
        status = cls._validate_identifier(descriptor.status, "status")
        tags = cls._normalize_tags(descriptor.tags)
        surfaces = cls._normalize_launch_surfaces(descriptor.launch_surfaces)
        surface_ids = {surface.surface_id for surface in surfaces}

        recommended_surface = descriptor.recommended_surface
        if recommended_surface is not None:
            recommended_surface = cls._validate_identifier(
                recommended_surface,
                "recommended_surface",
            )
            if recommended_surface not in surface_ids:
                raise AppDescriptorInvalid(
                    f"recommended_surface must reference a launch surface: {recommended_surface}"
                )

        metadata = cls._canonical_json_object(descriptor.metadata, "metadata")
        return AppDescriptor(
            app_id=app_id,
            title=title,
            summary=summary,
            status=status,
            tags=tags,
            launch_surfaces=surfaces,
            recommended_surface=recommended_surface,
            metadata=metadata,
        )

    @classmethod
    def _normalize_launch_surfaces(
        cls,
        launch_surfaces: tuple[LaunchSurface, ...],
    ) -> tuple[LaunchSurface, ...]:
        if not isinstance(launch_surfaces, tuple):
            raise AppDescriptorInvalid("launch_surfaces must be a tuple")

        normalized: list[LaunchSurface] = []
        seen: set[str] = set()
        for surface in launch_surfaces:
            surface_id = cls._validate_identifier(surface.surface_id, "surface_id")
            if surface_id in seen:
                raise AppDescriptorInvalid(f"duplicate launch surface: {surface_id}")
            seen.add(surface_id)

            kind = cls._validate_identifier(surface.kind, "kind")
            mode = cls._validate_identifier(surface.mode, "mode")
            if mode not in _LAUNCH_SURFACE_MODES:
                allowed = ", ".join(sorted(_LAUNCH_SURFACE_MODES))
                raise AppDescriptorInvalid(f"mode must be one of {allowed}: {mode}")
            label = cls._validate_required_text(surface.label, "label")
            runtime_control = cls._validate_identifier(
                surface.runtime_control,
                "runtime_control",
            )
            if runtime_control not in _RUNTIME_CONTROL_VALUES:
                allowed = ", ".join(sorted(_RUNTIME_CONTROL_VALUES))
                raise AppDescriptorInvalid(
                    f"runtime_control must be one of {allowed}: {runtime_control}"
                )
            details = cls._canonical_json_object(surface.details, f"{surface_id}.details")
            normalized.append(
                LaunchSurface(
                    surface_id=surface_id,
                    kind=kind,
                    mode=mode,
                    label=label,
                    details=details,
                    runtime_control=runtime_control,
                )
            )

        return tuple(sorted(normalized, key=lambda item: item.surface_id))

    @staticmethod
    def _normalize_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
        if not isinstance(tags, tuple):
            raise AppDescriptorInvalid("tags must be a tuple")

        normalized: list[str] = []
        seen: set[str] = set()
        for tag in tags:
            clean_tag = InMemoryAppCatalog._validate_identifier(tag, "tag")
            if clean_tag in seen:
                continue
            seen.add(clean_tag)
            normalized.append(clean_tag)
        return tuple(normalized)

    @staticmethod
    def _matches_query(descriptor: AppDescriptor, query: CatalogQuery) -> bool:
        if query.status is not None and descriptor.status != query.status:
            return False
        if query.tags and not set(query.tags).issubset(descriptor.tags):
            return False
        if query.launch_surface_kind is not None and not any(
            surface.kind == query.launch_surface_kind for surface in descriptor.launch_surfaces
        ):
            return False
        return True

    @staticmethod
    def _validate_identifier(value: str, field_name: str) -> str:
        text = InMemoryAppCatalog._validate_required_text(value, field_name)
        if any(character.isspace() for character in text):
            raise AppDescriptorInvalid(f"{field_name} must not contain whitespace")
        return text

    @staticmethod
    def _validate_required_text(value: str, field_name: str) -> str:
        text = InMemoryAppCatalog._validate_text(value, field_name)
        if text == "":
            raise AppDescriptorInvalid(f"{field_name} must not be empty")
        return text

    @staticmethod
    def _validate_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise AppDescriptorInvalid(f"{field_name} must be a string")
        return value.strip()

    @staticmethod
    def _canonical_json_object(
        value: dict[str, JsonValue],
        field_name: str,
    ) -> dict[str, JsonValue]:
        if not isinstance(value, dict):
            raise AppDescriptorInvalid(f"{field_name} must be a JSON object")
        try:
            serialized = json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True)
            loaded = json.loads(serialized)
        except (TypeError, ValueError) as error:
            raise AppDescriptorInvalid(
                f"{field_name} must be JSON-serializable: {error}"
            ) from error
        if not isinstance(loaded, dict):
            raise AppDescriptorInvalid(f"{field_name} must be a JSON object")
        return loaded

    @classmethod
    def _copy_descriptor(cls, descriptor: AppDescriptor) -> AppDescriptor:
        return replace(
            descriptor,
            launch_surfaces=tuple(
                replace(surface, details=cls._canonical_json_object(surface.details, "details"))
                for surface in descriptor.launch_surfaces
            ),
            metadata=cls._canonical_json_object(descriptor.metadata, "metadata"),
        )
