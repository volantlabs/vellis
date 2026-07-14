from __future__ import annotations

from components.rtg.discovery import (
    InMemoryRtgDiscovery,
    RtgDiscoveryCell,
    RtgDiscoveryCoordinates,
    RtgDiscoverySelectionInvalid,
    RtgDiscoveryView,
    RtgDiscoveryViewInvalid,
    RtgDiscoveryViewNotFound,
)
from components.rtg.discovery.reference import create_reference_component

MODEL_EVIDENCE = {
    "PutDiscoveryViewContractVerification": (
        "test_discovery_stores_lists_and_replaces_views",
        "test_discovery_lists_views_deterministically_and_returns_copies",
        "test_put_view_validates_curated_view_shape",
        "test_put_view_rejects_non_finite_metadata_without_replacing",
    ),
    "SelectDiscoveryAnchorTypesContractVerification": (
        "test_selects_anchor_types_by_view_coordinates",
        "test_select_rejects_missing_view_and_invalid_coordinates",
    ),
    "ListDiscoveryViewsContractVerification": (
        "test_empty_discovery_has_no_views",
        "test_discovery_stores_lists_and_replaces_views",
        "test_discovery_lists_views_deterministically_and_returns_copies",
    ),
    "CreateEmptyRtgDiscoveryContractVerification": ("test_empty_discovery_has_no_views",),
    "RtgDiscoveryBoundaryVerification": (
        "test_empty_discovery_has_no_views",
        "test_discovery_stores_lists_and_replaces_views",
        "test_discovery_lists_views_deterministically_and_returns_copies",
        "test_selects_anchor_types_by_view_coordinates",
        "test_select_rejects_missing_view_and_invalid_coordinates",
        "test_put_view_validates_curated_view_shape",
        "test_put_view_rejects_non_finite_metadata_without_replacing",
        "test_discovery_surface_does_not_expose_adjacent_component_operations",
    ),
}


def sample_view(view_id: str = "component-map") -> RtgDiscoveryView:
    return RtgDiscoveryView(
        view_id=view_id,
        description="Navigate component-related schema types.",
        row_labels={"component": "Components", "evidence": "Evidence"},
        column_labels={"core": "Core records", "support": "Supporting records"},
        cells=(
            RtgDiscoveryCell(
                row_key="component",
                column_key="core",
                description="Core component records.",
                anchor_type_keys=("Component", "ImplementationRoot"),
            ),
            RtgDiscoveryCell(
                row_key="evidence",
                column_key="support",
                description="Verification evidence records.",
                anchor_type_keys=("EvidenceRecord", "Component"),
            ),
        ),
        metadata={"curator": "knowledge-engineering", "version": 1},
    )


def test_empty_discovery_has_no_views() -> None:
    discovery = create_reference_component()

    assert discovery.list_views().views == ()


def test_discovery_stores_lists_and_replaces_views() -> None:
    discovery = create_reference_component()

    stored = discovery.put_view(sample_view())
    replacement = discovery.put_view(
        RtgDiscoveryView(
            view_id=stored.view_id,
            description="Replacement view.",
            row_labels={"component": "Components"},
            column_labels={"core": "Core records"},
            cells=(
                RtgDiscoveryCell(
                    row_key="component",
                    column_key="core",
                    description="Only component records.",
                    anchor_type_keys=("Component",),
                ),
            ),
        )
    )

    listed = discovery.list_views().views

    assert listed == (replacement,)
    assert listed[0].description == "Replacement view."


def test_discovery_lists_views_deterministically_and_returns_copies() -> None:
    discovery = InMemoryRtgDiscovery.empty()
    alpha = discovery.put_view(sample_view("alpha"))
    beta = discovery.put_view(sample_view("beta"))
    alpha.metadata["curator"] = "mutated"

    listed = discovery.list_views().views
    listed[0].metadata["curator"] = "also-mutated"

    assert [view.view_id for view in listed] == ["alpha", "beta"]
    assert discovery.list_views().views == (sample_view("alpha"), beta)


def test_selects_anchor_types_by_view_coordinates() -> None:
    discovery = create_reference_component()
    discovery.put_view(sample_view())

    selection = discovery.select_anchor_types(
        "component-map",
        (
            RtgDiscoveryCoordinates("component", "core"),
            RtgDiscoveryCoordinates("evidence", "support"),
        ),
    )

    assert selection.view_id == "component-map"
    assert selection.anchor_type_keys == ("Component", "ImplementationRoot", "EvidenceRecord")
    assert selection.cell_descriptions == {
        RtgDiscoveryCoordinates("component", "core"): "Core component records.",
        RtgDiscoveryCoordinates("evidence", "support"): "Verification evidence records.",
    }


def test_select_rejects_missing_view_and_invalid_coordinates() -> None:
    discovery = create_reference_component()
    discovery.put_view(sample_view())

    try:
        discovery.select_anchor_types(
            "missing",
            (RtgDiscoveryCoordinates("component", "core"),),
        )
    except RtgDiscoveryViewNotFound:
        pass
    else:
        raise AssertionError("missing view should fail")

    invalid_cases = (
        (),
        (RtgDiscoveryCoordinates("", "core"),),
        (RtgDiscoveryCoordinates("unknown", "core"),),
        (RtgDiscoveryCoordinates("component", "unknown"),),
        (RtgDiscoveryCoordinates("component", "support"),),
        (
            RtgDiscoveryCoordinates("component", "core"),
            RtgDiscoveryCoordinates("component", "core"),
        ),
    )
    for coordinates in invalid_cases:
        try:
            discovery.select_anchor_types("component-map", coordinates)
        except RtgDiscoverySelectionInvalid:
            pass
        else:
            raise AssertionError(f"invalid coordinates should fail: {coordinates!r}")


def test_put_view_validates_curated_view_shape() -> None:
    discovery = create_reference_component()
    invalid_views = (
        RtgDiscoveryView(
            view_id="bad-row",
            description="Bad row.",
            row_labels={"component": "Components"},
            column_labels={"core": "Core"},
            cells=(
                RtgDiscoveryCell(
                    row_key="missing",
                    column_key="core",
                    description="Bad cell.",
                    anchor_type_keys=("Component",),
                ),
            ),
        ),
        RtgDiscoveryView(
            view_id="duplicate",
            description="Duplicate cell.",
            row_labels={"component": "Components"},
            column_labels={"core": "Core"},
            cells=(
                RtgDiscoveryCell(
                    row_key="component",
                    column_key="core",
                    description="First.",
                    anchor_type_keys=("Component",),
                ),
                RtgDiscoveryCell(
                    row_key="component",
                    column_key="core",
                    description="Second.",
                    anchor_type_keys=("EvidenceRecord",),
                ),
            ),
        ),
        RtgDiscoveryView(
            view_id="bad-metadata",
            description="Bad metadata.",
            row_labels={"component": "Components"},
            column_labels={"core": "Core"},
            cells=(),
            metadata={"bad": object()},  # type: ignore[dict-item]
        ),
    )

    for view in invalid_views:
        try:
            discovery.put_view(view)
        except RtgDiscoveryViewInvalid:
            pass
        else:
            raise AssertionError(f"invalid view should fail: {view.view_id}")


def test_put_view_rejects_non_finite_metadata_without_replacing() -> None:
    discovery = create_reference_component()
    original = discovery.put_view(sample_view())

    for value in (float("nan"), float("inf"), float("-inf")):
        invalid = sample_view()
        invalid.metadata["number"] = value
        try:
            discovery.put_view(invalid)
        except RtgDiscoveryViewInvalid:
            pass
        else:
            raise AssertionError(f"non-finite JSON number should fail: {value!r}")

    assert discovery.list_views().views == (original,)


def test_discovery_surface_does_not_expose_adjacent_component_operations() -> None:
    discovery = create_reference_component()

    for forbidden_name in (
        "put_definition",
        "put_anchor",
        "execute",
        "validate",
        "stage_migration",
        "apply_cutover",
    ):
        assert not hasattr(discovery, forbidden_name)
