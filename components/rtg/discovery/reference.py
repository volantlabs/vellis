from __future__ import annotations

from components.rtg.discovery.implementation import InMemoryRtgDiscovery
from components.rtg.discovery.protocol import RtgDiscovery


def create_reference_component() -> RtgDiscovery:
    return InMemoryRtgDiscovery.empty()
