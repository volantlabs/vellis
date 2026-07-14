from __future__ import annotations

from components.rtg.graph_registry.implementation import InMemoryRtgGraphRegistry


def create_reference_component() -> InMemoryRtgGraphRegistry:
    """Create a reference RTG Graph Registry component."""

    return InMemoryRtgGraphRegistry.empty()
