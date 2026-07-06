from __future__ import annotations

from uuid import UUID, uuid4

from components.rtg.graph.implementation import InMemoryRtgGraph
from components.rtg.graph.protocol import RtgAnchor, RtgDataObject, RtgGraph


def create_reference_component() -> RtgGraph:
    return InMemoryRtgGraph.empty()


def _concrete_uuid(value: UUID | None) -> UUID:
    assert value is not None
    return value


def main() -> None:
    graph = create_reference_component()
    anchor = graph.put_anchor(RtgAnchor(uuid=uuid4(), type="Example Anchor"))
    data = graph.put_data_object(
        RtgDataObject(uuid=uuid4(), type="Example Data", properties={"name": "example"}),
        (_concrete_uuid(anchor.uuid),),
    )
    print(graph.list_anchor_data(_concrete_uuid(anchor.uuid)))
    print(graph.list_data_anchors(_concrete_uuid(data.uuid)))


if __name__ == "__main__":
    main()
