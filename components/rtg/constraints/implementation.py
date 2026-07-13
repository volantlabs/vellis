from __future__ import annotations

import copy
from uuid import UUID, uuid4

from components.rtg.constraints.protocol import (
    JsonObject,
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
    RtgConstraintDefinitionInvalid,
    RtgConstraintDefinitionList,
    RtgConstraintDeleteResult,
    RtgConstraintKindInvalid,
    RtgConstraintNotFound,
    RtgConstraintPayload,
    RtgConstraintPayloadInvalid,
    RtgConstraintQueryPatternPayload,
    RtgConstraintSnapshot,
    RtgConstraintSnapshotInvalid,
    RtgConstraintSystemValueInvalid,
    RtgConstraintTargetInvalid,
    RtgConstraintUuidConflict,
    RtgConstraintUuidInvalid,
    UuidInput,
)

_QUERY_PATTERN = "query_pattern"
_CARDINALITY = "cardinality"
_KINDS = {_QUERY_PATTERN, _CARDINALITY}
_EXPECTATIONS = {"must_match_at_least_one", "must_match_none"}


class InMemoryRtgConstraints:
    """In-memory implementation of the RTG Constraints component."""

    def __init__(self) -> None:
        self._constraints: dict[UUID, RtgConstraintDefinition] = {}

    @classmethod
    def empty(cls) -> InMemoryRtgConstraints:
        return cls()

    @classmethod
    def import_snapshot(cls, snapshot: RtgConstraintSnapshot) -> InMemoryRtgConstraints:
        if not isinstance(snapshot, RtgConstraintSnapshot) or not isinstance(
            snapshot.constraints, tuple
        ):
            raise RtgConstraintSnapshotInvalid("snapshot must contain a constraint tuple")
        constraints = cls.empty()
        seen_uuids: set[UUID] = set()
        for constraint in snapshot.constraints:
            if not isinstance(constraint, RtgConstraintDefinition):
                raise RtgConstraintSnapshotInvalid(
                    "snapshot constraints must be constraint definitions"
                )
            if constraint.uuid is None:
                raise RtgConstraintUuidInvalid("snapshot constraint UUID is not concrete")
            constraint_uuid = _parse_uuid(constraint.uuid)
            if constraint_uuid in seen_uuids:
                raise RtgConstraintUuidConflict(str(constraint_uuid))
            seen_uuids.add(constraint_uuid)
            constraints.put_constraint(constraint)
        return constraints

    def export_snapshot(self) -> RtgConstraintSnapshot:
        return RtgConstraintSnapshot(
            constraints=tuple(_copy_constraint(item) for item in self._sorted())
        )

    def put_constraint(self, constraint: RtgConstraintDefinition) -> RtgConstraintDefinition:
        normalized = self._normalize_constraint(constraint)
        uuid_value = _constraint_uuid(normalized)
        self._constraints[uuid_value] = normalized
        return _copy_constraint(normalized)

    def get_constraint(self, constraint_uuid: UuidInput) -> RtgConstraintDefinition:
        uuid_value = _parse_uuid(constraint_uuid)
        try:
            return _copy_constraint(self._constraints[uuid_value])
        except KeyError as error:
            raise RtgConstraintNotFound(str(uuid_value)) from error

    def list_constraints(
        self,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgConstraintDefinitionList:
        if kind is not None:
            _validate_kind(kind)
        return RtgConstraintDefinitionList(
            constraints=tuple(
                _copy_constraint(item)
                for item in self._sorted()
                if (kind is None or item.kind == kind)
                and (live is None or item.system["live"] == live)
            )
        )

    def list_constraints_by_target(
        self,
        target_type_key: str,
        kind: str | None = None,
        live: bool | None = None,
    ) -> RtgConstraintDefinitionList:
        if not isinstance(target_type_key, str) or not target_type_key:
            raise RtgConstraintTargetInvalid("target type key must be a non-empty string")
        return RtgConstraintDefinitionList(
            constraints=tuple(
                _copy_constraint(item)
                for item in self.list_constraints(kind=kind, live=live).constraints
                if target_type_key in item.target_type_keys
            )
        )

    def delete_constraint(self, constraint_uuid: UuidInput) -> RtgConstraintDeleteResult:
        uuid_value = _parse_uuid(constraint_uuid)
        try:
            deleted = self._constraints.pop(uuid_value)
        except KeyError as error:
            raise RtgConstraintNotFound(str(uuid_value)) from error
        return RtgConstraintDeleteResult(deleted_constraint=_copy_constraint(deleted))

    def _normalize_constraint(self, constraint: RtgConstraintDefinition) -> RtgConstraintDefinition:
        kind = _validate_kind(constraint.kind)
        payload = _validate_payload(kind, constraint.payload)
        uuid_value = (
            _parse_uuid(constraint.uuid) if constraint.uuid is not None else self._generate_uuid()
        )
        if uuid_value in self._constraints and self._constraints[uuid_value].kind != kind:
            raise RtgConstraintUuidConflict(str(uuid_value))
        target_type_keys = tuple(_validate_type_key(item) for item in constraint.target_type_keys)
        if len(set(target_type_keys)) != len(target_type_keys):
            raise RtgConstraintDefinitionInvalid("target type keys must be unique")
        return RtgConstraintDefinition(
            uuid=uuid_value,
            kind=kind,
            target_type_keys=tuple(sorted(target_type_keys)),
            display_name=_validate_text(constraint.display_name, "display_name"),
            description=_validate_text(constraint.description, "description"),
            payload=payload,
            system=_normalize_system(constraint.system),
        )

    def _generate_uuid(self) -> UUID:
        while True:
            uuid_value = uuid4()
            if uuid_value not in self._constraints:
                return uuid_value

    def _sorted(self) -> tuple[RtgConstraintDefinition, ...]:
        return tuple(
            sorted(self._constraints.values(), key=lambda item: str(_constraint_uuid(item)))
        )


def _parse_uuid(value: UuidInput) -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as error:
        raise RtgConstraintUuidInvalid(str(value)) from error


def _constraint_uuid(constraint: RtgConstraintDefinition) -> UUID:
    if constraint.uuid is None:
        raise RtgConstraintUuidInvalid("constraint UUID is not concrete")
    return constraint.uuid


def _validate_kind(value: str) -> str:
    if value not in _KINDS:
        raise RtgConstraintKindInvalid(str(value))
    return value


def _validate_payload(kind: str, payload: RtgConstraintPayload) -> RtgConstraintPayload:
    if kind == _QUERY_PATTERN and isinstance(payload, RtgConstraintQueryPatternPayload):
        if payload.expectation not in _EXPECTATIONS:
            raise RtgConstraintPayloadInvalid("invalid query-pattern expectation")
        return copy.deepcopy(payload)
    if kind == _CARDINALITY and isinstance(payload, RtgConstraintCardinalityPayload):
        if not payload.counted_binding:
            raise RtgConstraintPayloadInvalid("cardinality counted_binding is required")
        if payload.minimum is None and payload.maximum is None:
            raise RtgConstraintPayloadInvalid("cardinality requires minimum or maximum")
        if payload.minimum is not None and (
            isinstance(payload.minimum, bool) or not isinstance(payload.minimum, int)
        ):
            raise RtgConstraintPayloadInvalid("minimum must be an integer")
        if payload.maximum is not None and (
            isinstance(payload.maximum, bool) or not isinstance(payload.maximum, int)
        ):
            raise RtgConstraintPayloadInvalid("maximum must be an integer")
        if payload.minimum is not None and payload.minimum < 0:
            raise RtgConstraintPayloadInvalid("minimum must be non-negative")
        if payload.maximum is not None and payload.maximum < 0:
            raise RtgConstraintPayloadInvalid("maximum must be non-negative")
        if (
            payload.minimum is not None
            and payload.maximum is not None
            and payload.minimum > payload.maximum
        ):
            raise RtgConstraintPayloadInvalid("minimum must not exceed maximum")
        if not isinstance(payload.group_by_bindings, tuple):
            raise RtgConstraintPayloadInvalid("group_by_bindings must be a tuple")
        if len(set(payload.group_by_bindings)) != len(payload.group_by_bindings):
            raise RtgConstraintPayloadInvalid("group_by_bindings must be unique")
        if any(not isinstance(item, str) or not item for item in payload.group_by_bindings):
            raise RtgConstraintPayloadInvalid("group_by_bindings must be non-empty names")
        return copy.deepcopy(payload)
    raise RtgConstraintDefinitionInvalid(f"payload does not match constraint kind {kind!r}")


def _validate_type_key(value: str) -> str:
    if not isinstance(value, str) or value == "" or value != value.strip():
        raise RtgConstraintDefinitionInvalid("target type keys must be non-empty strings")
    return value


def _validate_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise RtgConstraintDefinitionInvalid(f"{field_name} must be a string")
    return value


def _normalize_system(value: JsonObject) -> JsonObject:
    if not isinstance(value, dict):
        raise RtgConstraintSystemValueInvalid("system must be a JSON object")
    system = copy.deepcopy(value)
    live = system.get("live", True)
    if not isinstance(live, bool):
        raise RtgConstraintSystemValueInvalid("system.live must be boolean")
    system["live"] = live
    return system


def _copy_constraint(constraint: RtgConstraintDefinition) -> RtgConstraintDefinition:
    return copy.deepcopy(constraint)
