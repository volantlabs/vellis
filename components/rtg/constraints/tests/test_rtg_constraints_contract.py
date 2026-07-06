from __future__ import annotations

from uuid import UUID, uuid4

from components.rtg.constraints import (
    InMemoryRtgConstraints,
    RtgConstraintCardinalityPayload,
    RtgConstraintDefinition,
)
from components.rtg.constraints.reference import create_reference_component
from components.rtg.query import RtgQueryAnchorBucket, RtgQuerySpec


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


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
