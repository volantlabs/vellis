from __future__ import annotations

from collections.abc import Callable
from typing import cast
from uuid import UUID

from components.rtg.graph.protocol import (
    JsonObject,
    JsonValue,
    RtgAnchor,
    RtgDataObject,
    RtgGraph,
    RtgGraphAnchorDataIndexEntryNotFound,
    RtgGraphAnchorNotFound,
    RtgGraphChangeSet,
    RtgGraphDataObjectNotFound,
    RtgGraphDeleteResult,
    RtgGraphEndpointNotFound,
    RtgGraphError,
    RtgGraphJsonValueInvalid,
    RtgGraphLinkNotFound,
    RtgGraphObjectNotFound,
    RtgGraphReferenceInvalid,
    RtgGraphSnapshot,
    RtgGraphSnapshotInvalid,
    RtgGraphSystemValueInvalid,
    RtgGraphTypeInvalid,
    RtgGraphTypeKindConflict,
    RtgGraphUuidConflict,
    RtgGraphUuidInvalid,
    RtgLink,
    RtgObject,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ReplayStateBinding,
    RuntimeBindingInvalid,
    create_action_catalog,
    load_runtime_binding_resource,
    runtime_binding_descriptor,
)
from components.runtime.component_adapter.implementation import (
    ReplayEffectApplier,
    ReplayEffectBuilder,
    RequestDecoder,
    encode_json,
)
from components.runtime.component_adapter.typed_binding import decode_typed

_CONTRACT_ID = "component.rtg.graph"
_BINDING_ID = "binding.python.rtg.graph.v1"
_REQUEST_CODEC = "codec.python.rtg.graph.request.json"
_RESULT_CODEC = "codec.python.rtg.graph.result.json"
_FAILURE_CODEC = "codec.python.rtg.graph.failure.json"

_FAILURES: dict[str, type[RtgGraphError]] = {
    failure.__name__: failure
    for failure in (
        RtgGraphSnapshotInvalid,
        RtgGraphUuidInvalid,
        RtgGraphUuidConflict,
        RtgGraphReferenceInvalid,
        RtgGraphTypeInvalid,
        RtgGraphTypeKindConflict,
        RtgGraphJsonValueInvalid,
        RtgGraphSystemValueInvalid,
        RtgGraphAnchorNotFound,
        RtgGraphDataObjectNotFound,
        RtgGraphLinkNotFound,
        RtgGraphEndpointNotFound,
        RtgGraphAnchorDataIndexEntryNotFound,
        RtgGraphObjectNotFound,
    )
}
_ACTION_FAILURES: dict[str, tuple[type[RtgGraphError], ...]] = {
    "export_snapshot": (),
    "replace_snapshot": (
        RtgGraphSnapshotInvalid,
        RtgGraphUuidInvalid,
        RtgGraphUuidConflict,
        RtgGraphReferenceInvalid,
        RtgGraphTypeInvalid,
        RtgGraphTypeKindConflict,
        RtgGraphJsonValueInvalid,
        RtgGraphSystemValueInvalid,
    ),
    "apply_batch": (
        RtgGraphUuidInvalid,
        RtgGraphUuidConflict,
        RtgGraphReferenceInvalid,
        RtgGraphTypeInvalid,
        RtgGraphTypeKindConflict,
        RtgGraphJsonValueInvalid,
        RtgGraphSystemValueInvalid,
        RtgGraphAnchorNotFound,
        RtgGraphDataObjectNotFound,
        RtgGraphLinkNotFound,
        RtgGraphEndpointNotFound,
        RtgGraphAnchorDataIndexEntryNotFound,
        RtgGraphObjectNotFound,
    ),
    "put_anchor": (
        RtgGraphUuidInvalid,
        RtgGraphUuidConflict,
        RtgGraphTypeInvalid,
        RtgGraphTypeKindConflict,
        RtgGraphSystemValueInvalid,
    ),
    "put_data_object": (
        RtgGraphUuidInvalid,
        RtgGraphUuidConflict,
        RtgGraphAnchorNotFound,
        RtgGraphTypeInvalid,
        RtgGraphTypeKindConflict,
        RtgGraphJsonValueInvalid,
        RtgGraphSystemValueInvalid,
    ),
    "put_link": (
        RtgGraphUuidInvalid,
        RtgGraphUuidConflict,
        RtgGraphEndpointNotFound,
        RtgGraphTypeInvalid,
        RtgGraphTypeKindConflict,
        RtgGraphSystemValueInvalid,
    ),
    "associate_data": (
        RtgGraphUuidInvalid,
        RtgGraphAnchorNotFound,
        RtgGraphDataObjectNotFound,
    ),
    "dissociate_data": (
        RtgGraphUuidInvalid,
        RtgGraphAnchorNotFound,
        RtgGraphDataObjectNotFound,
        RtgGraphAnchorDataIndexEntryNotFound,
    ),
    "delete_anchor": (RtgGraphUuidInvalid, RtgGraphAnchorNotFound),
    "delete_data_object": (RtgGraphUuidInvalid, RtgGraphDataObjectNotFound),
    "delete_link": (RtgGraphUuidInvalid, RtgGraphLinkNotFound),
    "preview_delete_anchor": (RtgGraphUuidInvalid, RtgGraphAnchorNotFound),
    "preview_delete_data_object": (
        RtgGraphUuidInvalid,
        RtgGraphDataObjectNotFound,
    ),
    "preview_dissociate_data": (
        RtgGraphUuidInvalid,
        RtgGraphAnchorNotFound,
        RtgGraphDataObjectNotFound,
        RtgGraphAnchorDataIndexEntryNotFound,
    ),
    "get_object": (RtgGraphUuidInvalid, RtgGraphObjectNotFound),
    "list_by_type": (RtgGraphTypeInvalid, RtgGraphReferenceInvalid),
    "list_anchor_data": (
        RtgGraphUuidInvalid,
        RtgGraphAnchorNotFound,
        RtgGraphReferenceInvalid,
    ),
    "list_data_anchors": (
        RtgGraphUuidInvalid,
        RtgGraphDataObjectNotFound,
        RtgGraphReferenceInvalid,
    ),
    "list_incident_links": (
        RtgGraphUuidInvalid,
        RtgGraphObjectNotFound,
        RtgGraphReferenceInvalid,
    ),
    "count_by_type": (RtgGraphTypeInvalid,),
}
_RUNTIME_BINDING = load_runtime_binding_resource(
    __package__,
    failure_types=_ACTION_FAILURES,
)
RTG_GRAPH_ACTIONS = create_action_catalog(_RUNTIME_BINDING)


def create_rtg_graph_adapter(
    graph: RtgGraph,
    *,
    replay_state: ReplayStateBinding | None = None,
) -> ComponentAdapter:
    """Create the standard explicit message binding for one RTG graph occurrence."""
    host = graph
    return ComponentAdapter(
        (
            _read_binding(
                "export_snapshot", _host_method(host, "export_snapshot"), lambda _: ((), {})
            ),
            _mutation_binding(
                "replace_snapshot",
                _host_method(host, "replace_snapshot"),
                lambda payload: ((_snapshot(payload["snapshot"]),), {}),
                lambda args, _kwargs, _result: {"snapshot": encode_json(args[0])},
                lambda payload: host.replace_snapshot(_snapshot(payload["snapshot"])),
            ),
            _mutation_binding(
                "apply_batch",
                _host_method(host, "apply_batch"),
                lambda payload: ((decode_typed(payload["changes"], RtgGraphChangeSet),), {}),
                lambda args, _kwargs, _result: {"changes": encode_json(args[0])},
                lambda payload: host.apply_batch(
                    decode_typed(payload["changes"], RtgGraphChangeSet)
                ),
            ),
            _mutation_binding(
                "put_anchor",
                _host_method(host, "put_anchor"),
                lambda payload: ((_anchor(payload["anchor"]),), {}),
                lambda _args, _kwargs, result: {"anchor": encode_json(result)},
                lambda payload: host.put_anchor(_anchor(payload["anchor"])),
            ),
            _mutation_binding(
                "put_data_object",
                _host_method(host, "put_data_object"),
                lambda payload: (
                    (
                        _data_object(payload["data_object"]),
                        tuple(_uuid(value) for value in _list(payload["anchor_uuids"])),
                    ),
                    {},
                ),
                lambda args, _kwargs, result: {
                    "data_object": encode_json(result),
                    "anchor_uuids": encode_json(args[1]),
                },
                lambda payload: host.put_data_object(
                    _data_object(payload["data_object"]),
                    tuple(_uuid(value) for value in _list(payload["anchor_uuids"])),
                ),
            ),
            _mutation_binding(
                "put_link",
                _host_method(host, "put_link"),
                lambda payload: ((_link(payload["link"]),), {}),
                lambda _args, _kwargs, result: {"link": encode_json(result)},
                lambda payload: host.put_link(_link(payload["link"])),
            ),
            _mutation_binding(
                "associate_data",
                _host_method(host, "associate_data"),
                lambda payload: ((_uuid(payload["anchor_uuid"]), _uuid(payload["data_uuid"])), {}),
                lambda args, _kwargs, _result: {
                    "anchor_uuid": str(args[0]),
                    "data_uuid": str(args[1]),
                },
                lambda payload: host.associate_data(
                    _uuid(payload["anchor_uuid"]), _uuid(payload["data_uuid"])
                ),
            ),
            _simple_mutation(
                "dissociate_data",
                _host_method(host, "dissociate_data"),
                ("anchor_uuid", "data_uuid"),
            ),
            _simple_mutation(
                "delete_anchor", _host_method(host, "delete_anchor"), ("anchor_uuid",)
            ),
            _simple_mutation(
                "delete_data_object", _host_method(host, "delete_data_object"), ("data_uuid",)
            ),
            _simple_mutation("delete_link", _host_method(host, "delete_link"), ("link_uuid",)),
            _read_binding(
                "preview_delete_anchor",
                _host_method(host, "preview_delete_anchor"),
                lambda payload: ((_uuid(payload["anchor_uuid"]),), {}),
            ),
            _read_binding(
                "preview_delete_data_object",
                _host_method(host, "preview_delete_data_object"),
                lambda payload: (
                    (_uuid(payload["data_uuid"]),),
                    {"offset": int(payload.get("offset", 0)), "limit": payload.get("limit")},
                ),
            ),
            _read_binding(
                "preview_dissociate_data",
                _host_method(host, "preview_dissociate_data"),
                lambda payload: (
                    (_uuid(payload["anchor_uuid"]), _uuid(payload["data_uuid"])),
                    {},
                ),
            ),
            _read_binding(
                "get_object",
                _host_method(host, "get_object"),
                lambda payload: ((_uuid(payload["object_uuid"]),), {}),
            ),
            _read_binding(
                "list_by_type",
                _host_method(host, "list_by_type"),
                lambda payload: (
                    (str(payload["object_type"]),),
                    {"offset": int(payload.get("offset", 0)), "limit": payload.get("limit")},
                ),
            ),
            _read_binding(
                "list_anchor_data",
                _host_method(host, "list_anchor_data"),
                lambda payload: (
                    (_uuid(payload["anchor_uuid"]),),
                    {"offset": int(payload.get("offset", 0)), "limit": payload.get("limit")},
                ),
            ),
            _read_binding(
                "list_data_anchors",
                _host_method(host, "list_data_anchors"),
                lambda payload: ((_uuid(payload["data_uuid"]),), {}),
            ),
            _read_binding(
                "list_incident_links",
                _host_method(host, "list_incident_links"),
                lambda payload: (
                    (_uuid(payload["object_uuid"]),),
                    {
                        "direction": str(payload.get("direction", "both")),
                        "offset": int(payload.get("offset", 0)),
                        "limit": payload.get("limit"),
                    },
                ),
            ),
            _read_binding(
                "count_by_type",
                _host_method(host, "count_by_type"),
                lambda payload: (
                    (),
                    {"kind": payload.get("kind"), "live": payload.get("live")},
                ),
            ),
        ),
        replay_state=replay_state,
    )


def _host_method(host: object, name: str) -> Callable[..., object]:
    def invoke(*args: object, **kwargs: object) -> object:
        method = getattr(host, name)
        if not callable(method):
            raise RuntimeBindingInvalid(f"graph host member is not callable: {name}")
        return method(*args, **kwargs)

    return invoke


def _descriptor(
    action: str,
):
    return runtime_binding_descriptor(_RUNTIME_BINDING, action)


def _read_binding(
    action: str, invoke: Callable[..., object], decoder: RequestDecoder
) -> ActionBinding:
    return ActionBinding(
        descriptor=_descriptor(action),
        invoke=invoke,
        decode_request=decoder,
        encode_result=encode_json,
        failure_types=_ACTION_FAILURES[action],
    )


def _mutation_binding(
    action: str,
    invoke: Callable[..., object],
    decoder: RequestDecoder,
    effect_builder: ReplayEffectBuilder,
    effect_applier: ReplayEffectApplier,
) -> ActionBinding:
    return ActionBinding(
        descriptor=_descriptor(action),
        invoke=invoke,
        decode_request=decoder,
        encode_result=encode_json,
        failure_types=_ACTION_FAILURES[action],
        build_replay_effect=effect_builder,
        apply_replay_effect=effect_applier,
    )


def _simple_mutation(
    action: str, invoke: Callable[..., object], parameters: tuple[str, ...]
) -> ActionBinding:
    def decode(payload: JsonObject) -> tuple[tuple[object, ...], dict[str, object]]:
        return tuple(_uuid(payload[name]) for name in parameters), {}

    def effect(args: tuple[object, ...], _kwargs: dict[str, object], _result: object) -> JsonObject:
        return {name: str(args[index]) for index, name in enumerate(parameters)}

    def apply(payload: JsonObject) -> object:
        return invoke(*(_uuid(payload[name]) for name in parameters))

    return _mutation_binding(action, invoke, decode, effect, apply)


def _action_id(action: str) -> str:
    return f"{_CONTRACT_ID}.{action}"


def _object(value: object) -> RtgObject:
    record = _object_value(value)
    if "source_uuid" in record:
        return _link(record)
    if "properties" in record:
        return _data_object(record)
    return _anchor(record)


def _anchor(value: object) -> RtgAnchor:
    record = _object_value(value)
    return RtgAnchor(
        uuid=_optional_uuid(record.get("uuid")),
        type=str(record["type"]),
        display_name=(
            str(record["display_name"]) if record.get("display_name") is not None else None
        ),
        system=_json_object(record.get("system", {})),
    )


def _data_object(value: object) -> RtgDataObject:
    record = _object_value(value)
    return RtgDataObject(
        uuid=_optional_uuid(record.get("uuid")),
        type=str(record["type"]),
        properties=_json_object(record.get("properties", {})),
        system=_json_object(record.get("system", {})),
    )


def _link(value: object) -> RtgLink:
    record = _object_value(value)
    return RtgLink(
        uuid=_optional_uuid(record.get("uuid")),
        type=str(record["type"]),
        source_uuid=_uuid(record["source_uuid"]),
        target_uuid=_uuid(record["target_uuid"]),
        system=_json_object(record.get("system", {})),
    )


def _delete_result(value: object) -> RtgGraphDeleteResult:
    record = _object_value(value)
    return RtgGraphDeleteResult(
        deleted_anchors=tuple(_anchor(item) for item in _list(record["deleted_anchors"])),
        deleted_data_objects=tuple(
            _data_object(item) for item in _list(record["deleted_data_objects"])
        ),
        deleted_links=tuple(_link(item) for item in _list(record["deleted_links"])),
        removed_anchor_data_pairs=tuple(
            (_uuid(pair[0]), _uuid(pair[1]))
            for value in _list(record["removed_anchor_data_pairs"])
            if len(pair := _list(value)) == 2
        ),
    )


def _snapshot(value: object) -> RtgGraphSnapshot:
    record = _object_value(value)
    index = _object_value(record["anchor_data_index"])
    return RtgGraphSnapshot(
        anchors=tuple(_json_object(item) for item in _list(record["anchors"])),
        data_objects=tuple(_json_object(item) for item in _list(record["data_objects"])),
        links=tuple(_json_object(item) for item in _list(record["links"])),
        anchor_data_index={
            key: tuple(str(item) for item in _list(items)) for key, items in index.items()
        },
    )


def _uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _optional_uuid(value: object) -> UUID | None:
    return None if value is None else _uuid(value)


def _object_value(value: object) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError("expected JSON object")
    return cast(JsonObject, value)


def _json_object(value: object) -> JsonObject:
    return _object_value(value)


def _list(value: object) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError("expected JSON array")
    return cast(list[JsonValue], value)
