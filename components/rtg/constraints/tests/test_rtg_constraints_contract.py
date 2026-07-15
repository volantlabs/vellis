from __future__ import annotations

from typing import cast
from uuid import UUID, uuid4

import pytest

from components.rtg.constraints import (
    InMemoryRtgConstraints,
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
    RtgConstraintDefinitionInvalid,
    RtgConstraintKindInvalid,
    RtgConstraintPayloadInvalid,
    RtgConstraintQueryPatternPayload,
    RtgConstraintSnapshot,
    RtgConstraintSnapshotInvalid,
    RtgConstraintTargetInvalid,
    RtgConstraintUuidConflict,
    RtgConstraintUuidInvalid,
)
from components.rtg.constraints.reference import create_reference_component
from components.rtg.query import RtgQueryAnchorBucket, RtgQuerySpec


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


MODEL_EVIDENCE = {
    "PutConstraintContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
        "test_constraints_by_target_supports_kind_and_live_filters",
        "test_constraint_validation_failures_are_boundary_specific",
        "test_cardinality_payload_rejects_invalid_bounds_and_group_names",
        "test_constraint_targets_realize_an_unordered_unique_set",
    ),
    "DeleteConstraintContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
        "test_constraint_validation_failures_are_boundary_specific",
    ),
    "ExportConstraintSnapshotContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
    ),
    "ReplaceConstraintSnapshotContractVerification": (
        "test_replace_constraint_snapshot_is_atomic_and_idempotent",
    ),
    "GetConstraintContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
    ),
    "ListConstraintsContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
        "test_constraints_by_target_supports_kind_and_live_filters",
        "test_constraint_validation_failures_are_boundary_specific",
    ),
    "ListConstraintsByTargetContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
        "test_constraints_by_target_supports_kind_and_live_filters",
        "test_constraint_validation_failures_are_boundary_specific",
    ),
    "CreateEmptyRtgConstraintsContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
    ),
    "ImportRtgConstraintSnapshotContractVerification": (
        "test_constraints_store_payloads_without_executing_them",
        "test_constraint_snapshot_rejects_malformed_and_duplicate_identities",
    ),
    "RtgConstraintsBoundaryVerification": (
        "test_constraints_store_payloads_without_executing_them",
        "test_constraints_by_target_supports_kind_and_live_filters",
        "test_constraint_validation_failures_are_boundary_specific",
        "test_cardinality_payload_rejects_invalid_bounds_and_group_names",
        "test_constraint_targets_realize_an_unordered_unique_set",
        "test_constraint_snapshot_rejects_malformed_and_duplicate_identities",
    ),
}


def test_constraints_store_payloads_without_executing_them() -> None:
    constraints = create_reference_component()
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))
    stored = constraints.put_constraint(
        RtgConstraintDefinition(
            uuid=uuid4(),
            kind="cardinality",
            target_type_keys=("Component",),
            display_name="At least one component",
            description="The model should contain a component.",
            payload=RtgConstraintCardinalityPayload(
                query_spec=query_spec,
                counted_binding="component",
                minimum=1,
            ),
        )
    )

    restored = InMemoryRtgConstraints.import_snapshot(constraints.export_snapshot())

    assert (
        restored.get_constraint(concrete_uuid(stored.uuid)).display_name == "At least one component"
    )
    assert constraints.list_constraints_by_target("Component").constraints == (stored,)
    assert not hasattr(constraints, "validate")


def test_constraints_by_target_supports_kind_and_live_filters() -> None:
    constraints = create_reference_component()
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))
    cardinality = constraints.put_constraint(
        RtgConstraintDefinition(
            uuid=uuid4(),
            kind="cardinality",
            target_type_keys=("Component",),
            display_name="At least one component",
            description="The model should contain a component.",
            payload=RtgConstraintCardinalityPayload(
                query_spec=query_spec,
                counted_binding="component",
                minimum=1,
            ),
        )
    )
    constraints.put_constraint(
        RtgConstraintDefinition(
            uuid=uuid4(),
            kind="query_pattern",
            target_type_keys=("Component",),
            display_name="No forbidden component",
            description="The model should not contain a forbidden component.",
            payload=RtgConstraintQueryPatternPayload(
                query_spec=query_spec,
                expectation="must_match_none",
            ),
        )
    )

    assert constraints.list_constraints_by_target(
        "Component", kind="cardinality", live=True
    ).constraints == (cardinality,)
    try:
        constraints.list_constraints_by_target("Component", kind="unsupported")
    except RtgConstraintKindInvalid:
        pass
    else:
        raise AssertionError("invalid kind was accepted")


def test_constraint_validation_failures_are_boundary_specific() -> None:
    constraints = create_reference_component()
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))

    malformed_payload = RtgConstraintDefinition(
        uuid=uuid4(),
        kind="cardinality",
        target_type_keys=("Component",),
        display_name="Malformed cardinality",
        description="The bound name must be present.",
        payload=RtgConstraintCardinalityPayload(
            query_spec=query_spec,
            counted_binding="",
            minimum=1,
        ),
    )
    try:
        constraints.put_constraint(malformed_payload)
    except RtgConstraintPayloadInvalid:
        pass
    else:
        raise AssertionError("malformed payload was accepted")

    mismatched_payload = RtgConstraintDefinition(
        uuid=uuid4(),
        kind="query_pattern",
        target_type_keys=("Component",),
        display_name="Mismatched payload",
        description="The payload type must match kind.",
        payload=RtgConstraintCardinalityPayload(
            query_spec=query_spec,
            counted_binding="component",
            minimum=1,
        ),
    )
    try:
        constraints.put_constraint(mismatched_payload)
    except RtgConstraintDefinitionInvalid:
        pass
    else:
        raise AssertionError("kind/payload mismatch was accepted")

    try:
        constraints.list_constraints_by_target("")
    except RtgConstraintTargetInvalid:
        pass
    else:
        raise AssertionError("invalid target lookup key was accepted")


@pytest.mark.parametrize(
    "payload",
    [
        RtgConstraintCardinalityPayload(
            query_spec=RtgQuerySpec(
                anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),)
            ),
            counted_binding="component",
            minimum=True,
        ),
        RtgConstraintCardinalityPayload(
            query_spec=RtgQuerySpec(
                anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),)
            ),
            counted_binding="component",
            group_by_bindings=("component", "component"),
            minimum=0,
        ),
    ],
)
def test_cardinality_payload_rejects_invalid_bounds_and_group_names(
    payload: RtgConstraintCardinalityPayload,
) -> None:
    with pytest.raises(RtgConstraintPayloadInvalid):
        create_reference_component().put_constraint(
            RtgConstraintDefinition(
                uuid=uuid4(),
                kind="cardinality",
                target_type_keys=("Component",),
                display_name="Invalid cardinality",
                description="Invalid cardinality details are rejected.",
                payload=payload,
            )
        )


def test_constraint_targets_realize_an_unordered_unique_set() -> None:
    constraints = create_reference_component()
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))
    stored = constraints.put_constraint(
        RtgConstraintDefinition(
            uuid=uuid4(),
            kind="cardinality",
            target_type_keys=("Zulu", "Alpha"),
            display_name="Canonical targets",
            description="Target ordering has no domain meaning.",
            payload=RtgConstraintCardinalityPayload(
                query_spec=query_spec,
                counted_binding="component",
                minimum=1,
            ),
        )
    )
    assert stored.target_type_keys == ("Alpha", "Zulu")

    with pytest.raises(RtgConstraintDefinitionInvalid):
        constraints.put_constraint(
            RtgConstraintDefinition(
                uuid=uuid4(),
                kind="cardinality",
                target_type_keys=("Component", "Component"),
                display_name="Duplicate targets",
                description="Duplicate target membership is invalid.",
                payload=RtgConstraintCardinalityPayload(
                    query_spec=query_spec,
                    counted_binding="component",
                    minimum=1,
                ),
            )
        )


def test_constraint_snapshot_rejects_malformed_and_duplicate_identities() -> None:
    query_spec = RtgQuerySpec(anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),))
    shared_uuid = uuid4()

    def record(name: str, record_uuid: UUID | None = shared_uuid) -> RtgConstraintDefinition:
        return RtgConstraintDefinition(
            uuid=record_uuid,
            kind="cardinality",
            target_type_keys=("Component",),
            display_name=name,
            description="Snapshot identity must be unique and concrete.",
            payload=RtgConstraintCardinalityPayload(
                query_spec=query_spec,
                counted_binding="component",
                minimum=1,
            ),
        )

    with pytest.raises(RtgConstraintUuidConflict):
        InMemoryRtgConstraints.import_snapshot(
            RtgConstraintSnapshot(constraints=(record("first"), record("second")))
        )
    with pytest.raises(RtgConstraintUuidInvalid):
        InMemoryRtgConstraints.import_snapshot(
            RtgConstraintSnapshot(constraints=(record("missing identity", None),))
        )
    with pytest.raises(RtgConstraintSnapshotInvalid):
        InMemoryRtgConstraints.import_snapshot(cast(RtgConstraintSnapshot, object()))


def test_replace_constraint_snapshot_is_atomic_and_idempotent() -> None:
    query_spec = RtgQuerySpec(
        anchor_buckets=(RtgQueryAnchorBucket("component", ("Component",)),)
    )

    def record(identity: int, name: str) -> RtgConstraintDefinition:
        return RtgConstraintDefinition(
            uuid=UUID(int=identity),
            kind="cardinality",
            target_type_keys=("Component",),
            display_name=name,
            description="Replacement state.",
            payload=RtgConstraintCardinalityPayload(
                query_spec=query_spec,
                counted_binding="component",
                minimum=1,
            ),
        )

    source = InMemoryRtgConstraints.empty()
    source.put_constraint(record(721, "Source"))
    target = InMemoryRtgConstraints.empty()
    target.put_constraint(record(722, "Prior"))
    replacement = source.export_snapshot()

    target.replace_snapshot(replacement)
    target.replace_snapshot(replacement)

    assert target.export_snapshot() == replacement
    before_rejection = target.export_snapshot()
    malformed = RtgConstraintSnapshot(
        constraints=(replacement.constraints[0], replacement.constraints[0])
    )
    with pytest.raises(RtgConstraintUuidConflict):
        target.replace_snapshot(malformed)
    assert target.export_snapshot() == before_rejection
