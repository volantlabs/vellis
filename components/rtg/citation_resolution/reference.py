from __future__ import annotations

from components.rtg.citation_resolution.implementation import (
    DeterministicRtgCitationResolver,
)
from components.rtg.citation_resolution.protocol import (
    RtgCitationProjectionRead,
    RtgCitationProjectionSpec,
    RtgCitationResolutionRequest,
)


class ExampleProjectionCatalog:
    def get_projection(self, graph_id: str) -> RtgCitationProjectionSpec | None:
        if graph_id != "example_graph":
            return None
        return RtgCitationProjectionSpec(
            graph_id=graph_id,
            query_name="example_sources",
            anchor_bucket="source",
        )


class ExampleProjectionReader:
    def read_projection(
        self,
        projection: RtgCitationProjectionSpec,
    ) -> RtgCitationProjectionRead:
        return RtgCitationProjectionRead(
            projection=projection,
            rows=(
                {
                    "anchors": {"source": "11111111-1111-4111-8111-111111111111"},
                    "properties": {"facts": {"title": "Example source"}},
                },
            ),
            provenance={"snapshot": "example.json"},
        )


def create_reference_component() -> DeterministicRtgCitationResolver:
    return DeterministicRtgCitationResolver.open(
        ExampleProjectionCatalog(),
        ExampleProjectionReader(),
    )


def main() -> None:
    resolver = create_reference_component()
    print(
        resolver.resolve(
            RtgCitationResolutionRequest(
                graph_id="example_graph",
                local_uuid="11111111-1111-4111-8111-111111111111",
            )
        )
    )


if __name__ == "__main__":
    main()
