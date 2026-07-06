from __future__ import annotations

from uuid import uuid4

import pytest

from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationCutoverPlan,
    RtgMigrationDeleteRejected,
    RtgMigrationEvidence,
    RtgMigrationRecord,
    RtgMigrationRecordInvalid,
    RtgMigrationStatusTransitionInvalid,
)
from components.rtg.migration.reference import create_reference_component


def test_migration_tracks_cutover_membership_and_evidence() -> None:
    migration = create_reference_component()
    schema_candidate = uuid4()
    stored = migration.put_migration(
        RtgMigrationRecord(
            migration_id="migrate-component-schema",
            description="Expand component schema.",
            schema_make_live=(schema_candidate,),
        )
    )

    migration.set_status("migrate-component-schema", "ready")
    with_evidence = migration.add_evidence(
        "migrate-component-schema",
        RtgMigrationEvidence(
            evidence_id="validation-1",
            kind="validation_report",
            reference="tx-1",
            summary="Validation passed.",
        ),
    )
    plan = RtgMigrationCutoverPlan.from_migration(with_evidence)
    restored = InMemoryRtgMigration.import_snapshot(migration.export_snapshot())

    assert stored.migration_id == "migrate-component-schema"
    assert plan.schema_make_live == (schema_candidate,)
    assert restored.get_migration("migrate-component-schema").status == "ready"


def test_migration_status_and_delete_rules() -> None:
    migration = create_reference_component()
    migration.put_migration(RtgMigrationRecord(migration_id="m1", description="Test migration"))

    with pytest.raises(RtgMigrationDeleteRejected):
        migration.delete_migration("m1")
    with pytest.raises(RtgMigrationStatusTransitionInvalid):
        migration.set_status("m1", "applied")

    migration.set_status("m1", "ready")
    migration.set_status("m1", "ready", {"review": "still ready"})
    assert migration.get_migration("m1").metadata["status_metadata"] == {"review": "still ready"}
    migration.set_status("m1", "draft")
    migration.set_status("m1", "ready")
    migration.set_status("m1", "applied")
    assert migration.delete_migration("m1").deleted_migration.status == "applied"


def test_migration_cutover_sets_must_be_disjoint() -> None:
    migration = create_reference_component()
    same = uuid4()

    with pytest.raises(RtgMigrationRecordInvalid):
        migration.put_migration(
            RtgMigrationRecord(
                migration_id="bad",
                description="Invalid overlap.",
                graph_make_live=(same,),
                graph_make_non_live=(same,),
            )
        )
