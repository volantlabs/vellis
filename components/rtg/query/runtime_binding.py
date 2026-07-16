from __future__ import annotations

import asyncio
import dataclasses
from collections import defaultdict
from typing import cast
from uuid import UUID

from components.rtg.graph import RTG_GRAPH_ACTIONS
from components.rtg.graph.protocol import (
    RtgAnchor,
    RtgDataObject,
    RtgDataObjectList,
    RtgGraphObjectNotFound,
    RtgGraphReadView,
    RtgLink,
    RtgLinkList,
    RtgObject,
    RtgObjectList,
)
from components.rtg.query.protocol import (
    RtgQueryEngine,
    RtgQueryOptions,
    RtgQuerySpec,
    RtgQuerySpecInvalid,
    RtgQueryUnsupported,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentExecution,
    create_action_catalog,
    load_runtime_binding_resource,
    runtime_binding_descriptor,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.component_adapter.typed_binding import decode_typed
from components.runtime.message_runtime import JsonObject

_FAILURES = {
    "execute": (RtgQuerySpecInvalid, RtgQueryUnsupported),
    "execute_projected": (RtgQuerySpecInvalid, RtgQueryUnsupported),
}
_RUNTIME_BINDING = load_runtime_binding_resource(__package__, failure_types=_FAILURES)
RTG_QUERY_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


class _PrefetchedGraphView(RtgGraphReadView):
    """Invocation-scoped coherent view assembled from targeted public graph reads."""

    def __init__(
        self,
        *,
        by_type: dict[str, tuple[RtgObject, ...]],
        anchor_data: dict[UUID, tuple[RtgDataObject, ...]],
        source_links: dict[UUID, tuple[RtgLink, ...]],
    ) -> None:
        self._by_type = by_type
        self._anchor_data = anchor_data
        self._source_links = source_links
        self._objects: dict[UUID, RtgObject] = {}
        for objects in by_type.values():
            for item in objects:
                if item.uuid is not None:
                    self._objects[item.uuid] = item
        for objects in anchor_data.values():
            for item in objects:
                if item.uuid is not None:
                    self._objects[item.uuid] = item
        for objects in source_links.values():
            for item in objects:
                if item.uuid is not None:
                    self._objects[item.uuid] = item

    def get_object(self, object_uuid: UUID | str) -> RtgObject:
        key = UUID(str(object_uuid))
        try:
            return self._objects[key]
        except KeyError as error:
            raise RtgGraphObjectNotFound(str(key)) from error

    def list_by_type(
        self, object_type: str, offset: int = 0, limit: int | None = None
    ) -> RtgObjectList:
        values = self._by_type.get(object_type, ())
        return RtgObjectList(values[offset:] if limit is None else values[offset : offset + limit])

    def list_anchor_data(
        self, anchor_uuid: UUID | str, offset: int = 0, limit: int | None = None
    ) -> RtgDataObjectList:
        values = self._anchor_data.get(UUID(str(anchor_uuid)), ())
        return RtgDataObjectList(
            values[offset:] if limit is None else values[offset : offset + limit]
        )

    def list_incident_links(
        self,
        object_uuid: UUID | str,
        direction: str = "both",
        offset: int = 0,
        limit: int | None = None,
    ) -> RtgLinkList:
        links = self._source_links.get(UUID(str(object_uuid)), ())
        if direction == "source":
            return RtgLinkList(links[offset:] if limit is None else links[offset : offset + limit])
        key = UUID(str(object_uuid))
        if direction == "target":
            values = tuple(link for link in self._all_links() if link.target_uuid == key)
            return RtgLinkList(
                values[offset:] if limit is None else values[offset : offset + limit]
            )
        values = tuple(
            link for link in self._all_links() if link.source_uuid == key or link.target_uuid == key
        )
        return RtgLinkList(values[offset:] if limit is None else values[offset : offset + limit])

    def _all_links(self) -> tuple[RtgLink, ...]:
        unique: dict[UUID, RtgLink] = {}
        for links in self._source_links.values():
            for link in links:
                if link.uuid is not None:
                    unique[link.uuid] = link
        return tuple(unique.values())


def create_rtg_query_adapter(
    query: RtgQueryEngine,
    *,
    graph_instance_key: str = "vellis.graph.primary",
) -> ComponentAdapter:
    async def execute(
        _args: tuple[object, ...],
        kwargs: dict[str, object],
        execution: ComponentExecution,
    ) -> None:
        query_spec = decode_typed(kwargs["query_spec"], RtgQuerySpec)
        query_options = decode_typed(kwargs.get("query_options"), RtgQueryOptions | None)
        graph_changes = kwargs.get("graph_changes")
        extra_type_keys = _projected_type_keys(graph_changes)
        view = await _prefetch_query_view(
            query_spec,
            execution,
            graph_instance_key=graph_instance_key,
            extra_type_keys=extra_type_keys,
        )
        if graph_changes is not None:
            _apply_projected_changes(view, graph_changes)
        result = await asyncio.to_thread(query.execute, view, query_spec, query_options)
        await execution.complete(result)

    bindings = []
    for name in ("execute", "execute_projected"):
        bindings.append(
            ActionBinding(
                descriptor=runtime_binding_descriptor(_RUNTIME_BINDING, name),
                handler=execute,
                decode_request=lambda payload: (
                    (),
                    {
                        "query_spec": payload["query_spec"],
                        "query_options": payload.get("query_options"),
                        "graph_changes": payload.get("graph_changes"),
                    },
                ),
                encode_result=encode_json,
                failure_types=(RtgQuerySpecInvalid, RtgQueryUnsupported),
            )
        )
    return ComponentAdapter(tuple(bindings))


async def _prefetch_query_view(
    query_spec: RtgQuerySpec,
    execution: ComponentExecution,
    *,
    graph_instance_key: str,
    extra_type_keys: tuple[str, ...] = (),
) -> _PrefetchedGraphView:
    target = execution.address_for(graph_instance_key)
    type_keys = sorted(
        {
            *(key for bucket in query_spec.anchor_buckets for key in bucket.anchor_type_keys),
            *(item.data_type_key for item in query_spec.data_requirements),
            *extra_type_keys,
        }
    )
    by_type: dict[str, tuple[RtgObject, ...]] = {}
    for index, type_key in enumerate(type_keys):
        items: list[RtgObject] = []
        offset = 0
        while True:
            value = await execution.call(
                f"graph-type-{index}-{offset}",
                RTG_GRAPH_ACTIONS["list_by_type"],
                {"object_type": type_key, "offset": offset, "limit": 200},
                target=target,
            )
            page = decode_typed(value, RtgObjectList).objects
            items.extend(page)
            if len(page) < 200:
                break
            offset += len(page)
        by_type[type_key] = tuple(items)

    anchors = {
        item.uuid: item
        for bucket in query_spec.anchor_buckets
        for type_key in bucket.anchor_type_keys
        for item in by_type.get(type_key, ())
        if isinstance(item, RtgAnchor) and item.uuid is not None
    }
    anchor_data: dict[UUID, tuple[RtgDataObject, ...]] = defaultdict(tuple)
    source_links: dict[UUID, tuple[RtgLink, ...]] = defaultdict(tuple)
    needs_data = bool(query_spec.data_requirements)
    needs_links = bool(query_spec.link_requirements)
    for index, anchor_uuid in enumerate(sorted(anchors, key=str)):
        if needs_data:
            data_items: list[RtgDataObject] = []
            offset = 0
            while True:
                value = await execution.call(
                    f"graph-anchor-data-{index}-{offset}",
                    RTG_GRAPH_ACTIONS["list_anchor_data"],
                    {"anchor_uuid": str(anchor_uuid), "offset": offset, "limit": 200},
                    target=target,
                )
                page = decode_typed(value, RtgDataObjectList).data_objects
                data_items.extend(page)
                if len(page) < 200:
                    break
                offset += len(page)
            anchor_data[anchor_uuid] = tuple(data_items)
        if needs_links:
            links: list[RtgLink] = []
            offset = 0
            while True:
                value = await execution.call(
                    f"graph-source-links-{index}-{offset}",
                    RTG_GRAPH_ACTIONS["list_incident_links"],
                    {
                        "object_uuid": str(anchor_uuid),
                        "direction": "source",
                        "offset": offset,
                        "limit": 200,
                    },
                    target=target,
                )
                page = decode_typed(value, RtgLinkList).links
                links.extend(page)
                if len(page) < 200:
                    break
                offset += len(page)
            source_links[anchor_uuid] = tuple(links)
    return _PrefetchedGraphView(
        by_type=by_type,
        anchor_data=dict(anchor_data),
        source_links=dict(source_links),
    )


def _projected_type_keys(value: object) -> tuple[str, ...]:
    if not isinstance(value, dict):
        return ()
    keys: set[str] = set()
    for collection in ("anchor_writes", "data_object_writes", "link_writes"):
        items = value.get(collection, [])
        if isinstance(items, list):
            keys.update(
                str(item["type"])
                for item in items
                if isinstance(item, dict) and isinstance(item.get("type"), str)
            )
    return tuple(sorted(keys))


def _apply_projected_changes(view: _PrefetchedGraphView, value: object) -> None:
    """Apply a canonical graph delta to an invocation-local query view only."""
    if not isinstance(value, dict):
        raise RtgQuerySpecInvalid("graph_changes must be an object")
    objects = dict(view._objects)
    anchor_data = {key: list(items) for key, items in view._anchor_data.items()}

    def resource_id(item: object) -> UUID:
        if not isinstance(item, dict):
            raise RtgQuerySpecInvalid("projected graph reference must be an object")
        raw = item.get("resource_id")
        if raw is None:
            raise RtgQuerySpecInvalid("projected query requires resolved resource IDs")
        return UUID(str(raw))

    def json_object(item: object) -> JsonObject:
        return cast(JsonObject, item) if isinstance(item, dict) else {}

    for raw in value.get("anchor_writes", []):
        if not isinstance(raw, dict):
            raise RtgQuerySpecInvalid("anchor write must be an object")
        key = resource_id(raw.get("ref"))
        objects[key] = RtgAnchor(
            key,
            str(raw["type"]),
            raw.get("display_name") if isinstance(raw.get("display_name"), str) else None,
            json_object(raw.get("system")),
        )
    for raw in value.get("data_object_writes", []):
        if not isinstance(raw, dict):
            raise RtgQuerySpecInvalid("data-object write must be an object")
        key = resource_id(raw.get("ref"))
        data = RtgDataObject(
            key,
            str(raw["type"]),
            json_object(raw.get("properties")),
            json_object(raw.get("system")),
        )
        objects[key] = data
        for anchor_ref in raw.get("anchor_refs", []):
            anchor_data.setdefault(resource_id(anchor_ref), []).append(data)
    for raw in value.get("link_writes", []):
        if not isinstance(raw, dict):
            raise RtgQuerySpecInvalid("link write must be an object")
        key = resource_id(raw.get("ref"))
        objects[key] = RtgLink(
            key,
            str(raw["type"]),
            resource_id(raw.get("source_ref")),
            resource_id(raw.get("target_ref")),
            json_object(raw.get("system")),
        )
    for collection in ("delete_anchors", "delete_data_objects", "delete_links"):
        for raw in value.get(collection, []):
            objects.pop(resource_id(raw), None)
    for raw in value.get("set_live", []):
        if not isinstance(raw, dict):
            continue
        key = resource_id(raw.get("object_ref"))
        item = objects.get(key)
        if item is not None:
            objects[key] = dataclasses.replace(
                item,
                system={**item.system, "live": bool(raw.get("live"))},
            )
    by_type: dict[str, list[RtgObject]] = defaultdict(list)
    source_links: dict[UUID, list[RtgLink]] = defaultdict(list)
    for item in objects.values():
        by_type[item.type].append(item)
        if isinstance(item, RtgLink):
            source_links[item.source_uuid].append(item)
    view._objects = objects
    view._by_type = {key: tuple(items) for key, items in by_type.items()}
    view._anchor_data = {key: tuple(items) for key, items in anchor_data.items()}
    view._source_links = {key: tuple(items) for key, items in source_links.items()}
