from __future__ import annotations

import copy

import pytest

from components.rtg.citation_resolution import (
    DeterministicRtgCitationResolver,
    RtgCitationProjectionRead,
    RtgCitationProjectionSpec,
    RtgCitationResolutionInvalid,
    RtgCitationResolutionRequest,
)
from components.rtg.citation_resolution.reference import create_reference_component

MODEL_EVIDENCE = {
    "GetCitationProjectionContractVerification": (
        "test_open_retains_dependencies_without_reading",
        "test_resolve_returns_exact_graph_local_row_and_preserves_inputs",
        "test_resolve_returns_unsupported_without_reading",
        "test_resolve_rejects_catalog_projection_for_different_graph_without_reading",
    ),
    "ReadCitationProjectionContractVerification": (
        "test_resolve_returns_exact_graph_local_row_and_preserves_inputs",
        "test_resolve_rejects_projection_mismatch",
        "test_resolve_rejects_rows_without_declared_anchor_identity",
        "test_resolve_rejects_non_finite_rows_and_provenance",
    ),
    "ResolveCitationContractVerification": (
        "test_resolve_returns_exact_graph_local_row_and_preserves_inputs",
        "test_resolve_returns_not_found_with_projection_provenance",
        "test_resolve_returns_unsupported_without_reading",
        "test_resolve_rejects_malformed_graph_qualified_identity",
        "test_resolve_rejects_projection_mismatch",
        "test_resolve_preserves_multiple_rows_for_one_anchor",
        "test_resolve_rejects_rows_without_declared_anchor_identity",
        "test_resolve_rejects_catalog_projection_for_different_graph_without_reading",
        "test_resolve_rejects_non_finite_rows_and_provenance",
    ),
    "OpenRtgCitationResolverContractVerification": (
        "test_open_retains_dependencies_without_reading",
        "test_reference_component_resolves_example",
    ),
    "RtgCitationResolverBoundaryVerification": (
        "test_open_retains_dependencies_without_reading",
        "test_resolve_returns_exact_graph_local_row_and_preserves_inputs",
        "test_resolve_returns_not_found_with_projection_provenance",
        "test_resolve_returns_unsupported_without_reading",
        "test_resolve_rejects_malformed_graph_qualified_identity",
        "test_resolve_preserves_multiple_rows_for_one_anchor",
        "test_resolve_rejects_rows_without_declared_anchor_identity",
        "test_resolver_surface_does_not_expose_adjacent_operations",
    ),
}

LOCAL_UUID = "11111111-1111-4111-8111-111111111111"
OTHER_UUID = "22222222-2222-4222-8222-222222222222"


class FakeCatalog:
    def __init__(self, projection: RtgCitationProjectionSpec | None) -> None:
        self.projection = projection
        self.calls: list[str] = []

    def get_projection(self, graph_id: str) -> RtgCitationProjectionSpec | None:
        self.calls.append(graph_id)
        return self.projection


class FakeReader:
    def __init__(self, projection_read: RtgCitationProjectionRead) -> None:
        self.projection_read = projection_read
        self.calls: list[RtgCitationProjectionSpec] = []

    def read_projection(
        self,
        projection: RtgCitationProjectionSpec,
    ) -> RtgCitationProjectionRead:
        self.calls.append(projection)
        return self.projection_read


def test_open_retains_dependencies_without_reading() -> None:
    catalog = FakeCatalog(projection())
    reader = FakeReader(projection_read(()))

    resolver = DeterministicRtgCitationResolver.open(catalog, reader)

    assert resolver is not None
    assert catalog.calls == []
    assert reader.calls == []


def projection() -> RtgCitationProjectionSpec:
    return RtgCitationProjectionSpec(
        graph_id="repo_twin",
        query_name="component_sources",
        anchor_bucket="component",
    )


def projection_read(
    rows: tuple[dict[str, object], ...],
) -> RtgCitationProjectionRead:
    return RtgCitationProjectionRead(
        projection=projection(),
        rows=rows,  # type: ignore[arg-type]
        provenance={"snapshot": "snapshots/current.json"},
    )


def test_resolve_returns_exact_graph_local_row_and_preserves_inputs() -> None:
    rows = (
        {
            "anchors": {"component": OTHER_UUID},
            "properties": {"facts": {"title": "Other"}},
        },
        {
            "anchors": {"component": LOCAL_UUID.upper()},
            "properties": {"facts": {"title": "Target"}},
        },
    )
    read = projection_read(rows)
    original = copy.deepcopy(read)
    catalog = FakeCatalog(projection())
    reader = FakeReader(read)
    resolver = DeterministicRtgCitationResolver.open(catalog, reader)

    result = resolver.resolve(
        RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID.upper())
    )

    assert result.status == "resolved"
    assert result.graph_id == "repo_twin"
    assert result.local_uuid == LOCAL_UUID
    assert result.query_name == "component_sources"
    assert result.anchor_bucket == "component"
    assert result.records == (rows[1],)
    assert result.records[0] is not rows[1]
    assert result.provenance == {"snapshot": "snapshots/current.json"}
    assert read == original
    assert catalog.calls == ["repo_twin"]
    assert reader.calls == [projection()]


def test_resolve_returns_not_found_with_projection_provenance() -> None:
    resolver = DeterministicRtgCitationResolver.open(
        FakeCatalog(projection()),
        FakeReader(projection_read(())),
    )

    result = resolver.resolve(
        RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID)
    )

    assert result.status == "not_found"
    assert result.records == ()
    assert result.query_name == "component_sources"
    assert result.provenance == {"snapshot": "snapshots/current.json"}


def test_resolve_returns_unsupported_without_reading() -> None:
    catalog = FakeCatalog(None)
    reader = FakeReader(projection_read(()))
    resolver = DeterministicRtgCitationResolver.open(catalog, reader)

    result = resolver.resolve(
        RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID)
    )

    assert result.status == "unsupported"
    assert result.query_name is None
    assert result.provenance == {}
    assert reader.calls == []


@pytest.mark.parametrize(
    ("graph_id", "local_uuid"),
    (("repo-twin", LOCAL_UUID), ("repo_twin", "component.rtg.query")),
)
def test_resolve_rejects_malformed_graph_qualified_identity(
    graph_id: str,
    local_uuid: str,
) -> None:
    resolver = DeterministicRtgCitationResolver.open(
        FakeCatalog(projection()),
        FakeReader(projection_read(())),
    )

    with pytest.raises(RtgCitationResolutionInvalid):
        resolver.resolve(RtgCitationResolutionRequest(graph_id=graph_id, local_uuid=local_uuid))


def test_resolve_rejects_projection_mismatch() -> None:
    mismatched = RtgCitationProjectionRead(
        projection=RtgCitationProjectionSpec(
            graph_id="repo_twin",
            query_name="different_query",
            anchor_bucket="component",
        ),
        rows=(),
    )
    resolver = DeterministicRtgCitationResolver.open(
        FakeCatalog(projection()),
        FakeReader(mismatched),
    )
    with pytest.raises(RtgCitationResolutionInvalid, match="requested projection unchanged"):
        resolver.resolve(RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID))


def test_resolve_rejects_catalog_projection_for_different_graph_without_reading() -> None:
    catalog = FakeCatalog(
        RtgCitationProjectionSpec(
            graph_id="personal_ops",
            query_name="component_sources",
            anchor_bucket="component",
        )
    )
    reader = FakeReader(projection_read(()))
    resolver = DeterministicRtgCitationResolver.open(catalog, reader)

    with pytest.raises(RtgCitationResolutionInvalid, match="must match request.graph_id"):
        resolver.resolve(RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID))

    assert reader.calls == []


def test_resolve_preserves_multiple_rows_for_one_anchor() -> None:
    rows = (
        {"anchors": {"component": LOCAL_UUID}, "properties": {"evidence": {"id": 1}}},
        {"anchors": {"component": LOCAL_UUID}, "properties": {"evidence": {"id": 2}}},
    )
    resolver = DeterministicRtgCitationResolver.open(
        FakeCatalog(projection()),
        FakeReader(projection_read(rows)),
    )

    result = resolver.resolve(
        RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID)
    )

    assert result.status == "resolved"
    assert result.records == rows


def test_resolve_rejects_rows_without_declared_anchor_identity() -> None:
    resolver = DeterministicRtgCitationResolver.open(
        FakeCatalog(projection()),
        FakeReader(projection_read(({"anchors": {}, "properties": {}},))),
    )

    with pytest.raises(RtgCitationResolutionInvalid, match="must return anchor bucket component"):
        resolver.resolve(RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID))


@pytest.mark.parametrize(
    "read",
    (
        projection_read(
            (
                {
                    "anchors": {"component": LOCAL_UUID},
                    "properties": {"score": float("nan")},
                },
            )
        ),
        RtgCitationProjectionRead(
            projection=projection(),
            rows=(),
            provenance={"position": float("inf")},
        ),
    ),
)
def test_resolve_rejects_non_finite_rows_and_provenance(
    read: RtgCitationProjectionRead,
) -> None:
    resolver = DeterministicRtgCitationResolver.open(
        FakeCatalog(projection()),
        FakeReader(read),
    )

    with pytest.raises(RtgCitationResolutionInvalid, match="JSON numbers must be finite"):
        resolver.resolve(RtgCitationResolutionRequest(graph_id="repo_twin", local_uuid=LOCAL_UUID))


def test_reference_component_resolves_example() -> None:
    result = create_reference_component().resolve(
        RtgCitationResolutionRequest(
            graph_id="example_graph",
            local_uuid=LOCAL_UUID,
        )
    )

    assert result.status == "resolved"
    assert result.records[0]["properties"] == {"facts": {"title": "Example source"}}


def test_resolver_surface_does_not_expose_adjacent_operations() -> None:
    resolver = create_reference_component()

    for forbidden_name in (
        "compile_intent",
        "execute_query",
        "put_bridge",
        "traverse_bridge",
        "restore_snapshot",
        "run_mcp_server",
        "write",
    ):
        assert not hasattr(resolver, forbidden_name)
