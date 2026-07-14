from __future__ import annotations

from components.rtg.graph_bridge.implementation import InMemoryRtgGraphBridge


def create_reference_component() -> InMemoryRtgGraphBridge:
    """Create a reference RTG Graph Bridge component."""

    return InMemoryRtgGraphBridge.empty()
