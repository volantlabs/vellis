from __future__ import annotations

from tempfile import TemporaryDirectory

from components.rtg.graph import InMemoryRtgGraph, RtgAnchor
from components.rtg.graph.runtime_binding import create_rtg_graph_adapter, create_rtg_graph_proxy
from components.runtime.message_runtime import SqliteMessageRuntime


def run_reference() -> tuple[str, str]:
    """Prove two same-type component occurrences remain address and state isolated."""
    with TemporaryDirectory() as directory:
        runtime = SqliteMessageRuntime.open(
            f"{directory}/runtime.sqlite", runtime_key="bibliotek.reference"
        )
        try:
            left_graph = InMemoryRtgGraph.empty()
            right_graph = InMemoryRtgGraph.empty()
            left_registration = runtime.register_adapter(
                instance_key="reference.graph.left",
                component_contract_id="component.rtg.graph",
                adapter=create_rtg_graph_adapter(left_graph),
            )
            right_registration = runtime.register_adapter(
                instance_key="reference.graph.right",
                component_contract_id="component.rtg.graph",
                adapter=create_rtg_graph_adapter(right_graph),
            )
            source = runtime.address_for(right_registration.instance_key)
            left = create_rtg_graph_proxy(
                runtime, source, runtime.address_for(left_registration.instance_key)
            )
            right = create_rtg_graph_proxy(
                runtime, source, runtime.address_for(right_registration.instance_key)
            )
            left_anchor = left.put_anchor(RtgAnchor(None, "reference.left"))
            right_anchor = right.put_anchor(RtgAnchor(None, "reference.right"))
            return str(left_anchor.uuid), str(right_anchor.uuid)
        finally:
            runtime.close()


if __name__ == "__main__":
    print(run_reference())
