from __future__ import annotations

from typing import Any, cast

from components.rtg.change_validation.protocol import (
    RtgChangeBatch,
    RtgChangeValidator,
    RtgValidationError,
    RtgValidationInputInvalid,
    RtgValidationOptions,
    RtgValidationReport,
)
from components.rtg.constraints.implementation import InMemoryRtgConstraints
from components.rtg.constraints.protocol import RtgConstraintSnapshot
from components.rtg.graph.implementation import InMemoryRtgGraph
from components.rtg.graph.protocol import RtgGraphSnapshot
from components.rtg.migration.implementation import InMemoryRtgMigration
from components.rtg.migration.protocol import RtgMigrationSnapshot
from components.rtg.schema.implementation import InMemoryRtgSchema
from components.rtg.schema.protocol import RtgSchemaSnapshot
from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeArgumentDescriptor,
    RuntimeClient,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.component_adapter.typed_binding import decode_typed
from components.runtime.message_runtime import (
    JsonObject,
    MessageRuntime,
    RuntimeAddress,
    RuntimeMessageKind,
    RuntimeReplayMode,
)

_CONTRACT = "component.rtg.change_validation"
_REQUEST_CODEC = f"codec.python.{_CONTRACT}.request.json"


class _BoundValidationService:
    def __init__(self, validator: RtgChangeValidator, query: object) -> None:
        self._validator = validator
        self._query = query

    def validate_batch(
        self,
        graph_snapshot: RtgGraphSnapshot,
        schema_snapshot: RtgSchemaSnapshot,
        constraint_snapshot: RtgConstraintSnapshot,
        migration_snapshot: RtgMigrationSnapshot | None,
        change_batch: RtgChangeBatch,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        return self._validator.validate_batch(
            InMemoryRtgGraph.import_snapshot(graph_snapshot),
            InMemoryRtgSchema.import_snapshot(schema_snapshot),
            InMemoryRtgConstraints.import_snapshot(constraint_snapshot),
            _migration_from_snapshot(migration_snapshot),
            self._query,
            change_batch,
            validation_options,
        )

    def validate_graph_state(
        self,
        graph_snapshot: RtgGraphSnapshot,
        schema_snapshot: RtgSchemaSnapshot,
        constraint_snapshot: RtgConstraintSnapshot,
        migration_snapshot: RtgMigrationSnapshot | None,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        return self._validator.validate_graph_state(
            InMemoryRtgGraph.import_snapshot(graph_snapshot),
            InMemoryRtgSchema.import_snapshot(schema_snapshot),
            InMemoryRtgConstraints.import_snapshot(constraint_snapshot),
            _migration_from_snapshot(migration_snapshot),
            self._query,
            migration_ids,
            validation_options,
        )


def create_rtg_change_validator_adapter(
    validator: RtgChangeValidator,
    *,
    query: object,
) -> ExplicitComponentAdapter:
    service = _BoundValidationService(validator, query)
    return ExplicitComponentAdapter(
        tuple(
            ActionBinding(
                descriptor=RuntimeActionBindingDescriptor(
                    component_contract_id=_CONTRACT,
                    action_id=f"{_CONTRACT}.{name}",
                    binding_id="binding.python.rtg.change_validation.v1",
                    binding_version=1,
                    schema_version=1,
                    request_codec_id=_REQUEST_CODEC,
                    result_codec_id=f"codec.python.{_CONTRACT}.result.json",
                    failure_codec_id=f"codec.python.{_CONTRACT}.failure.json",
                    idempotency=RuntimeActionIdempotency.IDEMPOTENT,
                    replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
                    request_arguments=_request_arguments(name),
                ),
                invoke=getattr(service, name),
                decode_request=decoder,
                encode_result=encode_json,
                failure_types=(RtgValidationInputInvalid,),
            )
            for name, decoder in (
                ("validate_batch", _decode_validate_batch),
                ("validate_graph_state", _decode_validate_graph_state),
            )
        )
    )


def _request_arguments(name: str) -> tuple[RuntimeArgumentDescriptor, ...]:
    collaborator_snapshots = (
        RuntimeArgumentDescriptor("graph_snapshot", required=True),
        RuntimeArgumentDescriptor("schema_snapshot", required=True),
        RuntimeArgumentDescriptor("constraint_snapshot", required=True),
        RuntimeArgumentDescriptor("migration_snapshot", required=True),
    )
    if name == "validate_batch":
        return (
            *collaborator_snapshots,
            RuntimeArgumentDescriptor("change_batch", required=True),
            RuntimeArgumentDescriptor("validation_options", required=False, default=None),
        )
    return (
        *collaborator_snapshots,
        RuntimeArgumentDescriptor("migration_ids", required=False, default=None),
        RuntimeArgumentDescriptor("validation_options", required=False, default=None),
    )


class RtgChangeValidatorMessageProxy:
    def __init__(
        self, runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
    ) -> None:
        self._client = RuntimeClient(
            runtime,
            source=source,
            target=target,
            component_contract_id=_CONTRACT,
            request_codec_id=_REQUEST_CODEC,
        )

    def validate_batch(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        change_batch: RtgChangeBatch,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        del query
        snapshots = _encode_collaborator_snapshots(graph, schema, constraints, migration)
        return self._request(
            "validate_batch",
            {
                **snapshots,
                "change_batch": encode_json(change_batch),
                "validation_options": encode_json(validation_options),
            },
        )

    def validate_graph_state(
        self,
        graph: object,
        schema: object,
        constraints: object,
        migration: object | None,
        query: object,
        migration_ids: tuple[str, ...] | None = None,
        validation_options: RtgValidationOptions | None = None,
    ) -> RtgValidationReport:
        del query
        snapshots = _encode_collaborator_snapshots(graph, schema, constraints, migration)
        return self._request(
            "validate_graph_state",
            {
                **snapshots,
                "migration_ids": encode_json(migration_ids),
                "validation_options": encode_json(validation_options),
            },
        )

    def _request(self, name: str, arguments: JsonObject) -> RtgValidationReport:
        outcome = self._client.request_sync(f"{_CONTRACT}.{name}", arguments)
        payload = outcome.response.payload.value
        if not isinstance(payload, dict):
            raise RtgValidationError("validation response payload is not an object")
        if outcome.response.kind is RuntimeMessageKind.FAULT:
            error = (
                RtgValidationInputInvalid
                if payload.get("type") == "RtgValidationInputInvalid"
                else RtgValidationError
            )
            raise error(str(payload.get("message", "validation failed")))
        return cast(
            RtgValidationReport,
            decode_typed(payload.get("result"), RtgValidationReport),
        )


def create_rtg_change_validator_proxy(
    runtime: MessageRuntime, source: RuntimeAddress, target: RuntimeAddress
) -> RtgChangeValidator:
    return RtgChangeValidatorMessageProxy(runtime, source, target)


def _decode_validate_batch(payload: JsonObject):
    return (), {
        **_decode_collaborator_snapshots(payload),
        "change_batch": decode_typed(payload["change_batch"], RtgChangeBatch),
        "validation_options": decode_typed(
            payload.get("validation_options"), RtgValidationOptions | None
        ),
    }


def _decode_validate_graph_state(payload: JsonObject):
    return (), {
        **_decode_collaborator_snapshots(payload),
        "migration_ids": decode_typed(payload.get("migration_ids"), tuple[str, ...] | None),
        "validation_options": decode_typed(
            payload.get("validation_options"), RtgValidationOptions | None
        ),
    }


def _decode_collaborator_snapshots(payload: JsonObject) -> dict[str, object]:
    return {
        "graph_snapshot": decode_typed(payload["graph_snapshot"], RtgGraphSnapshot),
        "schema_snapshot": decode_typed(payload["schema_snapshot"], RtgSchemaSnapshot),
        "constraint_snapshot": decode_typed(payload["constraint_snapshot"], RtgConstraintSnapshot),
        "migration_snapshot": decode_typed(
            payload.get("migration_snapshot"), RtgMigrationSnapshot | None
        ),
    }


def _encode_collaborator_snapshots(
    graph: object,
    schema: object,
    constraints: object,
    migration: object | None,
) -> JsonObject:
    return {
        "graph_snapshot": encode_json(cast(Any, graph).export_snapshot()),
        "schema_snapshot": encode_json(cast(Any, schema).export_snapshot()),
        "constraint_snapshot": encode_json(cast(Any, constraints).export_snapshot()),
        "migration_snapshot": encode_json(
            cast(Any, migration).export_snapshot() if migration is not None else None
        ),
    }


def _migration_from_snapshot(
    snapshot: RtgMigrationSnapshot | None,
) -> InMemoryRtgMigration | None:
    return InMemoryRtgMigration.import_snapshot(snapshot) if snapshot is not None else None
