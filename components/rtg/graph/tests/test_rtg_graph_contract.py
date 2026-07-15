from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from components.rtg.graph import (
    InMemoryRtgGraph,
    RtgAnchor,
    RtgDataObject,
    RtgGraph,
    RtgGraphAnchorDataIndexEntryNotFound,
    RtgGraphAnchorNotFound,
    RtgGraphDataObjectNotFound,
    RtgGraphEndpointNotFound,
    RtgGraphJsonValueInvalid,
    RtgGraphObjectNotFound,
    RtgGraphReferenceInvalid,
    RtgGraphSnapshot,
    RtgGraphSystemValueInvalid,
    RtgGraphTypeInvalid,
    RtgGraphTypeKindConflict,
    RtgGraphUuidConflict,
    RtgGraphUuidInvalid,
    RtgLink,
    RtgTypeCount,
)
from components.rtg.graph.reference import create_reference_component


def empty_graph() -> RtgGraph:
    return InMemoryRtgGraph.empty()


def concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


MODEL_EVIDENCE = {
    "ExportGraphSnapshotContractVerification": (
        "test_anchor_display_name_is_optional_preserved_and_non_unique",
        "test_association_is_idempotent_and_metadata_free",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_snapshot_round_trip_and_missing_live_default",
    ),
    "ReplaceGraphSnapshotContractVerification": (
        "test_replace_snapshot_is_atomic_and_idempotent",
    ),
    "PutAnchorContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_writes_generate_missing_uuids_and_preserve_supplied_uuids",
        "test_anchor_display_name_is_optional_preserved_and_non_unique",
        "test_data_requires_existing_anchor_and_type_namespace_is_global",
        "test_type_validation",
        "test_uuid_conflicts_and_invalid_values_are_rejected",
        "test_json_and_system_validation",
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_link_endpoints_must_be_anchors_or_data_not_links",
        "test_type_counts_can_filter_by_kind_and_live_status",
        "test_delete_result_order_is_deterministic",
        "test_reference_component_is_usable",
    ),
    "PutDataObjectContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_writes_generate_missing_uuids_and_preserve_supplied_uuids",
        "test_data_requires_existing_anchor_and_type_namespace_is_global",
        "test_uuid_conflicts_and_invalid_values_are_rejected",
        "test_json_and_system_validation",
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_type_counts_can_filter_by_kind_and_live_status",
        "test_delete_result_order_is_deterministic",
        "test_reference_component_is_usable",
    ),
    "PutLinkContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_writes_generate_missing_uuids_and_preserve_supplied_uuids",
        "test_data_requires_existing_anchor_and_type_namespace_is_global",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_link_endpoints_must_be_anchors_or_data_not_links",
        "test_type_counts_can_filter_by_kind_and_live_status",
    ),
    "AssociateDataContractVerification": ("test_association_is_idempotent_and_metadata_free",),
    "DissociateDataContractVerification": (
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
    ),
    "DeleteAnchorContractVerification": (
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_delete_result_order_is_deterministic",
    ),
    "DeleteDataObjectContractVerification": (
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_delete_result_order_is_deterministic",
    ),
    "DeleteLinkContractVerification": (
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
    ),
    "PreviewDeleteAnchorContractVerification": (
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
    ),
    "PreviewDeleteDataObjectContractVerification": (
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
    ),
    "PreviewDissociateDataContractVerification": (
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
    ),
    "GetGraphObjectContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_writes_generate_missing_uuids_and_preserve_supplied_uuids",
        "test_anchor_display_name_is_optional_preserved_and_non_unique",
        "test_data_requires_existing_anchor_and_type_namespace_is_global",
        "test_uuid_conflicts_and_invalid_values_are_rejected",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_snapshot_round_trip_and_missing_live_default",
        "test_type_counts_can_filter_by_kind_and_live_status",
    ),
    "ListGraphObjectsByTypeContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_reference_component_is_usable",
    ),
    "ListAnchorDataContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_reference_component_is_usable",
    ),
    "ListDataAnchorsContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
    ),
    "ListIncidentLinksContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
    ),
    "CountGraphObjectsByTypeContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_snapshot_round_trip_and_missing_live_default",
        "test_type_counts_can_filter_by_kind_and_live_status",
        "test_import_rejects_unreferenced_data_and_missing_references",
        "test_import_preserves_invalid_uuid_errors",
        "test_delete_result_order_is_deterministic",
        "test_reference_component_is_usable",
    ),
    "CreateEmptyRtgGraphContractVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_writes_generate_missing_uuids_and_preserve_supplied_uuids",
        "test_anchor_display_name_is_optional_preserved_and_non_unique",
        "test_data_requires_existing_anchor_and_type_namespace_is_global",
        "test_type_validation",
        "test_uuid_conflicts_and_invalid_values_are_rejected",
        "test_json_and_system_validation",
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_link_endpoints_must_be_anchors_or_data_not_links",
        "test_type_counts_can_filter_by_kind_and_live_status",
        "test_delete_result_order_is_deterministic",
        "test_reference_component_is_usable",
    ),
    "ImportRtgGraphSnapshotContractVerification": (
        "test_anchor_display_name_is_optional_preserved_and_non_unique",
        "test_snapshot_round_trip_and_missing_live_default",
        "test_import_rejects_unreferenced_data_and_missing_references",
        "test_import_preserves_invalid_uuid_errors",
    ),
    "RtgGraphBoundaryVerification": (
        "test_anchor_data_link_round_trip_and_indexes",
        "test_writes_generate_missing_uuids_and_preserve_supplied_uuids",
        "test_anchor_display_name_is_optional_preserved_and_non_unique",
        "test_data_requires_existing_anchor_and_type_namespace_is_global",
        "test_type_validation",
        "test_uuid_conflicts_and_invalid_values_are_rejected",
        "test_json_and_system_validation",
        "test_association_is_idempotent_and_metadata_free",
        "test_dissociating_final_anchor_deletes_data_and_incident_links",
        "test_delete_anchor_cascades_only_ungrounded_data",
        "test_delete_data_object_removes_pairs_and_links_but_not_anchors",
        "test_delete_previews_match_mutations_without_mutating_graph",
        "test_dissociation_and_data_delete_previews_match_mutations_without_mutating",
        "test_put_data_object_replaces_anchor_indexes_without_deleting_data",
        "test_link_endpoints_must_be_anchors_or_data_not_links",
        "test_snapshot_round_trip_and_missing_live_default",
        "test_type_counts_can_filter_by_kind_and_live_status",
        "test_import_rejects_unreferenced_data_and_missing_references",
        "test_import_preserves_invalid_uuid_errors",
        "test_delete_result_order_is_deterministic",
        "test_reference_component_is_usable",
        "test_no_forbidden_dependency_imports",
    ),
}


def test_anchor_data_link_round_trip_and_indexes() -> None:
    graph = empty_graph()
    anchor_uuid = uuid4()
    data_uuid = uuid4()
    link_uuid = uuid4()

    anchor = graph.put_anchor(RtgAnchor(uuid=anchor_uuid, type="Person", system={"source": "test"}))
    data = graph.put_data_object(
        RtgDataObject(uuid=data_uuid, type="Profile", properties={"name": "Ada"}),
        (anchor_uuid,),
    )
    link = graph.put_link(
        RtgLink(uuid=link_uuid, type="grounded_by", source_uuid=anchor_uuid, target_uuid=data_uuid)
    )

    assert anchor.system == {"source": "test", "live": True}
    assert data.system == {"live": True}
    assert link.system == {"live": True}
    assert graph.get_object(anchor_uuid) == anchor
    assert graph.get_object(data_uuid) == data
    assert graph.list_by_type("Person").objects == (anchor,)
    assert graph.list_by_type("Profile").objects == (data,)
    assert graph.list_anchor_data(anchor_uuid).data_objects == (data,)
    assert graph.list_data_anchors(data_uuid).anchors == (anchor,)
    assert graph.list_incident_links(anchor_uuid).links == (link,)
    assert graph.list_incident_links(data_uuid, "target").links == (link,)
    assert graph.list_incident_links(data_uuid, "source").links == ()


def test_writes_generate_missing_uuids_and_preserve_supplied_uuids() -> None:
    graph = empty_graph()
    supplied_anchor_uuid = uuid4()

    supplied_anchor = graph.put_anchor(RtgAnchor(uuid=supplied_anchor_uuid, type="Supplied"))
    generated_anchor = graph.put_anchor(RtgAnchor(uuid=None, type="Generated Anchor"))
    generated_data = graph.put_data_object(
        RtgDataObject(uuid=None, type="Generated Data"),
        (concrete_uuid(generated_anchor.uuid),),
    )
    generated_link = graph.put_link(
        RtgLink(
            uuid=None,
            type="Generated Link",
            source_uuid=concrete_uuid(generated_anchor.uuid),
            target_uuid=concrete_uuid(generated_data.uuid),
        )
    )

    assert supplied_anchor.uuid == supplied_anchor_uuid
    assert generated_anchor.uuid is not None
    assert generated_data.uuid is not None
    assert generated_link.uuid is not None
    assert (
        len(
            {
                supplied_anchor.uuid,
                generated_anchor.uuid,
                generated_data.uuid,
                generated_link.uuid,
            }
        )
        == 4
    )


def test_anchor_display_name_is_optional_preserved_and_non_unique() -> None:
    graph = empty_graph()
    first = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="First", display_name="Shared label"))
    second = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Second", display_name="Shared label"))
    unnamed = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Unnamed"))

    exported = graph.export_snapshot()
    restored = InMemoryRtgGraph.import_snapshot(exported)

    assert first.display_name == "Shared label"
    assert second.display_name == "Shared label"
    assert unnamed.display_name is None
    assert restored.get_object(concrete_uuid(first.uuid)) == first
    assert restored.get_object(concrete_uuid(second.uuid)) == second
    assert restored.get_object(concrete_uuid(unnamed.uuid)) == unnamed


def test_data_requires_existing_anchor_and_type_namespace_is_global() -> None:
    graph = empty_graph()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Shared"))

    with pytest.raises(RtgGraphAnchorNotFound):
        graph.put_data_object(RtgDataObject(uuid=uuid4(), type="Profile"), ())
    with pytest.raises(RtgGraphTypeKindConflict):
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="Shared"), (concrete_uuid(anchor.uuid),)
        )

    graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Profile"), (concrete_uuid(anchor.uuid),)
    )
    with pytest.raises(RtgGraphTypeKindConflict):
        graph.put_link(
            RtgLink(
                uuid=uuid4(),
                type="Profile",
                source_uuid=concrete_uuid(anchor.uuid),
                target_uuid=concrete_uuid(anchor.uuid),
            )
        )


@pytest.mark.parametrize("bad_type", ["", " ", " Person", "Person ", "Bad\nType"])
def test_type_validation(bad_type: str) -> None:
    graph = empty_graph()

    with pytest.raises(RtgGraphTypeInvalid):
        graph.put_anchor(RtgAnchor(uuid=uuid4(), type=bad_type))


def test_uuid_conflicts_and_invalid_values_are_rejected() -> None:
    graph = empty_graph()
    same_uuid = uuid4()
    graph.put_anchor(RtgAnchor(uuid=same_uuid, type="Anchor"))

    with pytest.raises(RtgGraphUuidConflict):
        graph.put_data_object(RtgDataObject(uuid=same_uuid, type="Data"), (same_uuid,))
    with pytest.raises(RtgGraphUuidInvalid):
        graph.get_object("not-a-uuid")


def test_json_and_system_validation() -> None:
    graph = empty_graph()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))

    with pytest.raises(RtgGraphJsonValueInvalid):
        graph.put_data_object(
            RtgDataObject(uuid=uuid4(), type="Data", properties={"bad": object()}),  # type: ignore[dict-item]
            (concrete_uuid(anchor.uuid),),
        )
    with pytest.raises(RtgGraphSystemValueInvalid):
        graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Other", system={"live": "yes"}))


def test_association_is_idempotent_and_metadata_free() -> None:
    graph = empty_graph()
    anchor_a = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor A"))
    anchor_b = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor B"))
    anchor_c = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor C"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(anchor_a.uuid),)
    )

    graph.associate_data(concrete_uuid(anchor_b.uuid), concrete_uuid(data.uuid))
    graph.associate_data(concrete_uuid(anchor_b.uuid), concrete_uuid(data.uuid))

    assert {
        anchor.uuid for anchor in graph.list_data_anchors(concrete_uuid(data.uuid)).anchors
    } == {
        anchor_a.uuid,
        anchor_b.uuid,
    }
    with pytest.raises(RtgGraphAnchorDataIndexEntryNotFound):
        graph.dissociate_data(concrete_uuid(anchor_c.uuid), concrete_uuid(data.uuid))
    snapshot = graph.export_snapshot()
    assert snapshot.anchor_data_index == {
        str(anchor_a.uuid): (str(data.uuid),),
        str(anchor_b.uuid): (str(data.uuid),),
    }


def test_dissociating_final_anchor_deletes_data_and_incident_links() -> None:
    graph = empty_graph()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(anchor.uuid),)
    )
    link = graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Link",
            source_uuid=concrete_uuid(anchor.uuid),
            target_uuid=concrete_uuid(data.uuid),
        )
    )

    result = graph.dissociate_data(concrete_uuid(anchor.uuid), concrete_uuid(data.uuid))

    assert result.deleted_data_objects == (data,)
    assert result.deleted_links == (link,)
    assert result.removed_anchor_data_pairs == ((anchor.uuid, data.uuid),)
    with pytest.raises(RtgGraphDataObjectNotFound):
        graph.list_data_anchors(concrete_uuid(data.uuid))
    with pytest.raises(RtgGraphObjectNotFound):
        graph.get_object(concrete_uuid(link.uuid))
    with pytest.raises(RtgGraphDataObjectNotFound):
        graph.dissociate_data(concrete_uuid(anchor.uuid), concrete_uuid(data.uuid))


def test_delete_anchor_cascades_only_ungrounded_data() -> None:
    graph = empty_graph()
    anchor_a = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor A"))
    anchor_b = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor B", system={"live": False}))
    shared = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Shared Data"),
        (concrete_uuid(anchor_a.uuid), concrete_uuid(anchor_b.uuid)),
    )
    orphaned = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Orphaned Data"), (concrete_uuid(anchor_a.uuid),)
    )
    link = graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Link",
            source_uuid=concrete_uuid(anchor_a.uuid),
            target_uuid=concrete_uuid(orphaned.uuid),
        )
    )

    result = graph.delete_anchor(concrete_uuid(anchor_a.uuid))

    assert result.deleted_anchors == (anchor_a,)
    assert result.deleted_data_objects == (orphaned,)
    assert result.deleted_links == (link,)
    assert graph.list_data_anchors(concrete_uuid(shared.uuid)).anchors == (anchor_b,)
    with pytest.raises(RtgGraphObjectNotFound):
        graph.get_object(concrete_uuid(orphaned.uuid))


def test_delete_data_object_removes_pairs_and_links_but_not_anchors() -> None:
    graph = empty_graph()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(anchor.uuid),)
    )
    link = graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Link",
            source_uuid=concrete_uuid(data.uuid),
            target_uuid=concrete_uuid(anchor.uuid),
        )
    )

    result = graph.delete_data_object(concrete_uuid(data.uuid))

    assert result.deleted_data_objects == (data,)
    assert result.deleted_links == (link,)
    assert result.removed_anchor_data_pairs == ((anchor.uuid, data.uuid),)
    assert graph.get_object(concrete_uuid(anchor.uuid)) == anchor
    assert graph.list_anchor_data(concrete_uuid(anchor.uuid)).data_objects == ()


def test_delete_previews_match_mutations_without_mutating_graph() -> None:
    graph = empty_graph()
    anchor_a = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor A"))
    anchor_b = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor B"))
    shared = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Shared Data"),
        (concrete_uuid(anchor_a.uuid), concrete_uuid(anchor_b.uuid)),
    )
    orphaned = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Orphaned Data"), (concrete_uuid(anchor_a.uuid),)
    )
    link = graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Link",
            source_uuid=concrete_uuid(anchor_a.uuid),
            target_uuid=concrete_uuid(orphaned.uuid),
        )
    )
    before = graph.export_snapshot()

    preview = graph.preview_delete_anchor(concrete_uuid(anchor_a.uuid))

    assert graph.export_snapshot() == before
    assert preview == graph.delete_anchor(concrete_uuid(anchor_a.uuid))
    assert graph.list_data_anchors(concrete_uuid(shared.uuid)).anchors == (anchor_b,)
    assert preview.deleted_anchors == (anchor_a,)
    assert preview.deleted_data_objects == (orphaned,)
    assert preview.deleted_links == (link,)


def test_dissociation_and_data_delete_previews_match_mutations_without_mutating() -> None:
    dissociation_graph = empty_graph()
    anchor = dissociation_graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))
    data = dissociation_graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(anchor.uuid),)
    )
    link = dissociation_graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Link",
            source_uuid=concrete_uuid(data.uuid),
            target_uuid=concrete_uuid(anchor.uuid),
        )
    )
    before_dissociation = dissociation_graph.export_snapshot()

    dissociation_preview = dissociation_graph.preview_dissociate_data(
        concrete_uuid(anchor.uuid), concrete_uuid(data.uuid)
    )

    assert dissociation_graph.export_snapshot() == before_dissociation
    assert dissociation_preview == dissociation_graph.dissociate_data(
        concrete_uuid(anchor.uuid), concrete_uuid(data.uuid)
    )
    assert dissociation_preview.deleted_data_objects == (data,)
    assert dissociation_preview.deleted_links == (link,)

    delete_graph = empty_graph()
    delete_anchor = delete_graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))
    delete_data = delete_graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(delete_anchor.uuid),)
    )
    before_delete = delete_graph.export_snapshot()

    delete_preview = delete_graph.preview_delete_data_object(concrete_uuid(delete_data.uuid))

    assert delete_graph.export_snapshot() == before_delete
    assert delete_preview == delete_graph.delete_data_object(concrete_uuid(delete_data.uuid))


def test_put_data_object_replaces_anchor_indexes_without_deleting_data() -> None:
    graph = empty_graph()
    anchor_a = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor A"))
    anchor_b = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor B"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(anchor_a.uuid),)
    )

    updated = graph.put_data_object(
        RtgDataObject(uuid=data.uuid, type="Data", properties={"updated": True}),
        (concrete_uuid(anchor_b.uuid),),
    )

    assert graph.list_anchor_data(concrete_uuid(anchor_a.uuid)).data_objects == ()
    assert graph.list_anchor_data(concrete_uuid(anchor_b.uuid)).data_objects == (updated,)


def test_link_endpoints_must_be_anchors_or_data_not_links() -> None:
    graph = empty_graph()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))
    link = graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Link",
            source_uuid=concrete_uuid(anchor.uuid),
            target_uuid=concrete_uuid(anchor.uuid),
        )
    )

    with pytest.raises(RtgGraphEndpointNotFound):
        graph.put_link(
            RtgLink(
                uuid=uuid4(),
                type="Other Link",
                source_uuid=concrete_uuid(link.uuid),
                target_uuid=concrete_uuid(anchor.uuid),
            )
        )


def test_snapshot_round_trip_and_missing_live_default() -> None:
    anchor_uuid = uuid4()
    data_uuid = uuid4()
    link_uuid = uuid4()
    snapshot = RtgGraphSnapshot(
        anchors=({"uuid": str(anchor_uuid), "type": "Anchor", "system": {}},),
        data_objects=(
            {"uuid": str(data_uuid), "type": "Data", "properties": {"n": 1}, "system": {}},
        ),
        links=(
            {
                "uuid": str(link_uuid),
                "type": "Link",
                "source_uuid": str(anchor_uuid),
                "target_uuid": str(data_uuid),
                "system": {},
            },
        ),
        anchor_data_index={str(anchor_uuid): (str(data_uuid),)},
    )

    graph = InMemoryRtgGraph.import_snapshot(snapshot)
    exported = graph.export_snapshot()

    assert exported.anchors[0]["system"] == {"live": True}
    assert exported.data_objects[0]["system"] == {"live": True}
    assert exported.links[0]["system"] == {"live": True}
    assert InMemoryRtgGraph.import_snapshot(exported).export_snapshot() == exported


def test_replace_snapshot_is_atomic_and_idempotent() -> None:
    source = InMemoryRtgGraph.empty()
    source.put_anchor(RtgAnchor(UUID(int=701), "Person", "Source"))
    target = InMemoryRtgGraph.empty()
    target.put_anchor(RtgAnchor(UUID(int=702), "Place", "Prior"))

    replacement = source.export_snapshot()
    target.replace_snapshot(replacement)
    target.replace_snapshot(replacement)

    assert target.export_snapshot() == replacement
    before_rejection = target.export_snapshot()
    malformed = RtgGraphSnapshot(
        anchors=replacement.anchors,
        data_objects=replacement.data_objects,
        links=replacement.links,
        anchor_data_index={str(UUID(int=999)): (str(UUID(int=998)),)},
    )
    with pytest.raises(RtgGraphReferenceInvalid):
        target.replace_snapshot(malformed)
    assert target.export_snapshot() == before_rejection


def test_type_counts_can_filter_by_kind_and_live_status() -> None:
    graph = empty_graph()
    live_person = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person"))
    graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Person", system={"live": False}))
    graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Profile"), (concrete_uuid(live_person.uuid),)
    )
    graph.put_link(
        RtgLink(
            uuid=uuid4(),
            type="Knows",
            source_uuid=concrete_uuid(live_person.uuid),
            target_uuid=concrete_uuid(live_person.uuid),
        )
    )

    assert graph.count_by_type(kind="anchor", live=True).counts == (
        RtgTypeCount(type="Person", kind="anchor", live=True, count=1),
    )
    assert graph.count_by_type(kind="anchor", live=False).counts == (
        RtgTypeCount(type="Person", kind="anchor", live=False, count=1),
    )
    assert graph.count_by_type().counts == (
        RtgTypeCount(type="Person", kind="anchor", live=None, count=2),
        RtgTypeCount(type="Profile", kind="data_object", live=None, count=1),
        RtgTypeCount(type="Knows", kind="link", live=None, count=1),
    )

    with pytest.raises(RtgGraphTypeInvalid):
        graph.count_by_type(kind="invalid")


def test_import_rejects_unreferenced_data_and_missing_references() -> None:
    anchor_uuid = uuid4()
    data_uuid = uuid4()

    with pytest.raises(RtgGraphReferenceInvalid):
        InMemoryRtgGraph.import_snapshot(
            RtgGraphSnapshot(
                anchors=({"uuid": str(anchor_uuid), "type": "Anchor", "system": {}},),
                data_objects=(
                    {"uuid": str(data_uuid), "type": "Data", "properties": {}, "system": {}},
                ),
                links=(),
                anchor_data_index={},
            )
        )

    with pytest.raises(RtgGraphReferenceInvalid):
        InMemoryRtgGraph.import_snapshot(
            RtgGraphSnapshot(
                anchors=({"uuid": str(anchor_uuid), "type": "Anchor", "system": {}},),
                data_objects=(
                    {"uuid": str(data_uuid), "type": "Data", "properties": {}, "system": {}},
                ),
                links=(),
                anchor_data_index={str(uuid4()): (str(data_uuid),)},
            )
        )


def test_import_preserves_invalid_uuid_errors() -> None:
    with pytest.raises(RtgGraphUuidInvalid):
        InMemoryRtgGraph.import_snapshot(
            RtgGraphSnapshot(
                anchors=({"uuid": "not-a-uuid", "type": "Anchor", "system": {}},),
                data_objects=(),
                links=(),
                anchor_data_index={},
            )
        )


def test_delete_result_order_is_deterministic() -> None:
    graph = empty_graph()
    anchor = graph.put_anchor(
        RtgAnchor(uuid=UUID("00000000-0000-0000-0000-000000000001"), type="Anchor")
    )
    data_b = graph.put_data_object(
        RtgDataObject(uuid=UUID("00000000-0000-0000-0000-000000000003"), type="Data B"),
        (concrete_uuid(anchor.uuid),),
    )
    data_a = graph.put_data_object(
        RtgDataObject(uuid=UUID("00000000-0000-0000-0000-000000000002"), type="Data A"),
        (concrete_uuid(anchor.uuid),),
    )

    result = graph.delete_anchor(concrete_uuid(anchor.uuid))

    assert result.deleted_data_objects == (data_a, data_b)
    assert result.removed_anchor_data_pairs == (
        (anchor.uuid, data_a.uuid),
        (anchor.uuid, data_b.uuid),
    )


def test_reference_component_is_usable() -> None:
    graph = create_reference_component()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Anchor"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Data"), (concrete_uuid(anchor.uuid),)
    )

    assert graph.list_anchor_data(concrete_uuid(anchor.uuid)).data_objects == (data,)


def test_no_forbidden_dependency_imports() -> None:
    component_root = Path(__file__).parents[1]
    forbidden_terms = (
        "sqlalchemy",
        "sqlite3",
        "neo4j",
        "networkx",
        "requests",
        "boto3",
        "elasticsearch",
    )

    for path in component_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert not any(term in source for term in forbidden_terms), path
