from __future__ import annotations

from typing import cast
from uuid import uuid4

import pytest

from components.rtg.migration import (
    InMemoryRtgMigration,
    RtgMigrationCutoverPlan,
    RtgMigrationDeleteNotAllowed,
    RtgMigrationEvidence,
    RtgMigrationIdConflict,
    RtgMigrationRecord,
    RtgMigrationRecordInvalid,
    RtgMigrationReplacement,
    RtgMigrationSnapshot,
    RtgMigrationSnapshotInvalid,
    RtgMigrationStatusTransitionInvalid,
)
from components.rtg.migration.reference import create_reference_component

MODEL_EVIDENCE = {
    "PutMigrationContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
        "test_migration_status_and_delete_rules",
        "test_migration_replacement_obeys_lifecycle_and_has_no_effect_on_rejection",
        "test_migration_status_metadata_is_replaced_even_when_empty_or_same_status",
        "test_migration_membership_is_unique_consistent_and_canonical",
        "test_migration_cutover_sets_must_be_disjoint",
    ),
    "SetMigrationStatusContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
        "test_migration_status_and_delete_rules",
        "test_migration_status_metadata_is_replaced_even_when_empty_or_same_status",
    ),
    "AddMigrationEvidenceContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
    ),
    "DeleteMigrationContractVerification": ("test_migration_status_and_delete_rules",),
    "BuildMigrationCutoverPlanContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
    ),
    "ExportMigrationSnapshotContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
    ),
    "ReplaceMigrationSnapshotContractVerification": (
        "test_replace_migration_snapshot_is_atomic_and_idempotent",
    ),
    "GetMigrationContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
        "test_migration_status_and_delete_rules",
        "test_migration_replacement_obeys_lifecycle_and_has_no_effect_on_rejection",
        "test_migration_snapshot_accepts_independent_terminal_records",
    ),
    "ListMigrationsContractVerification": (
        "test_migration_status_and_delete_rules",
        "test_migration_replacement_obeys_lifecycle_and_has_no_effect_on_rejection",
        "test_migration_membership_is_unique_consistent_and_canonical",
        "test_migration_snapshot_import_rejects_duplicate_and_malformed_records_atomically",
        "test_migration_snapshot_accepts_independent_terminal_records",
    ),
    "CreateEmptyRtgMigrationContractVerification": (
        "test_migration_status_metadata_is_replaced_even_when_empty_or_same_status",
    ),
    "ImportRtgMigrationSnapshotContractVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
        "test_migration_snapshot_import_rejects_duplicate_and_malformed_records_atomically",
        "test_migration_snapshot_accepts_independent_terminal_records",
    ),
    "RtgMigrationBoundaryVerification": (
        "test_migration_tracks_cutover_membership_and_evidence",
        "test_migration_status_and_delete_rules",
        "test_migration_replacement_obeys_lifecycle_and_has_no_effect_on_rejection",
        "test_migration_status_metadata_is_replaced_even_when_empty_or_same_status",
        "test_migration_membership_is_unique_consistent_and_canonical",
        "test_migration_snapshot_import_rejects_duplicate_and_malformed_records_atomically",
        "test_migration_snapshot_accepts_independent_terminal_records",
        "test_migration_cutover_sets_must_be_disjoint",
    ),
}


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

    with pytest.raises(RtgMigrationDeleteNotAllowed):
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


def test_migration_replacement_obeys_lifecycle_and_has_no_effect_on_rejection() -> None:
    migration = create_reference_component()
    migration.put_migration(
        RtgMigrationRecord(migration_id="m1", description="Lifecycle", status="draft")
    )

    with pytest.raises(RtgMigrationStatusTransitionInvalid):
        migration.put_migration(
            RtgMigrationRecord(migration_id="m1", description="Skip", status="applied")
        )

    assert migration.get_migration("m1").description == "Lifecycle"
    assert migration.get_migration("m1").status == "draft"
    assert (
        migration.put_migration(
            RtgMigrationRecord(migration_id="m1", description="Ready", status="ready")
        ).status
        == "ready"
    )


def test_migration_status_metadata_is_replaced_even_when_empty_or_same_status() -> None:
    migration = create_reference_component()
    migration.put_migration(
        RtgMigrationRecord(
            migration_id="m1",
            description="Metadata",
            metadata={"owner": "team", "status_metadata": {"review": "old"}},
        )
    )

    updated = migration.set_status("m1", "draft")

    assert updated.metadata == {"owner": "team", "status_metadata": {}}


def test_migration_membership_is_unique_consistent_and_canonical() -> None:
    migration = create_reference_component()
    old_b, old_a, new_b, new_a = (uuid4() for _ in range(4))
    stored = migration.put_migration(
        RtgMigrationRecord(
            migration_id="m1",
            description="Replace resources",
            schema_make_live=(new_b, new_a),
            schema_make_non_live=(old_b, old_a),
            schema_replacements=(
                RtgMigrationReplacement(old_b, new_b),
                RtgMigrationReplacement(old_a, new_a),
            ),
        )
    )

    assert stored.schema_make_live == tuple(sorted((new_a, new_b), key=str))
    assert stored.schema_make_non_live == tuple(sorted((old_a, old_b), key=str))
    assert stored.schema_replacements == tuple(
        sorted(stored.schema_replacements, key=lambda value: str(value.old_resource_id))
    )

    for invalid in (
        RtgMigrationRecord(
            migration_id="duplicate",
            description="Duplicate",
            graph_make_live=(new_a, new_a),
        ),
        RtgMigrationRecord(
            migration_id="self",
            description="Self replacement",
            graph_make_live=(new_a,),
            graph_make_non_live=(old_a,),
            graph_replacements=(RtgMigrationReplacement(old_a, old_a),),
        ),
        RtgMigrationRecord(
            migration_id="unlisted",
            description="Unlisted replacement",
            graph_replacements=(RtgMigrationReplacement(old_a, new_a),),
        ),
    ):
        with pytest.raises(RtgMigrationRecordInvalid):
            migration.put_migration(invalid)


def test_migration_snapshot_import_rejects_duplicate_and_malformed_records_atomically() -> None:
    record = RtgMigrationRecord(migration_id="m1", description="One")
    with pytest.raises(RtgMigrationIdConflict):
        InMemoryRtgMigration.import_snapshot(RtgMigrationSnapshot((record, record)))

    malformed = RtgMigrationSnapshot(cast(tuple[RtgMigrationRecord, ...], (record, object())))
    with pytest.raises(RtgMigrationSnapshotInvalid):
        InMemoryRtgMigration.import_snapshot(malformed)


def test_migration_snapshot_accepts_independent_terminal_records() -> None:
    restored = InMemoryRtgMigration.import_snapshot(
        RtgMigrationSnapshot(
            (
                RtgMigrationRecord(
                    migration_id="terminal", description="Already applied", status="applied"
                ),
            )
        )
    )

    assert restored.get_migration("terminal").status == "applied"


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


def test_replace_migration_snapshot_is_atomic_and_idempotent() -> None:
    source = InMemoryRtgMigration.empty()
    source.put_migration(RtgMigrationRecord(migration_id="source", description="Source"))
    target = InMemoryRtgMigration.empty()
    target.put_migration(RtgMigrationRecord(migration_id="prior", description="Prior"))
    replacement = source.export_snapshot()

    target.replace_snapshot(replacement)
    target.replace_snapshot(replacement)

    assert target.export_snapshot() == replacement
    before_rejection = target.export_snapshot()
    malformed = RtgMigrationSnapshot(
        migrations=(replacement.migrations[0], replacement.migrations[0])
    )
    with pytest.raises(RtgMigrationIdConflict):
        target.replace_snapshot(malformed)
    assert target.export_snapshot() == before_rejection
