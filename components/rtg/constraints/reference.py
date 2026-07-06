from __future__ import annotations

from components.rtg.constraints.implementation import InMemoryRtgConstraints
from components.rtg.constraints.protocol import RtgConstraints


def create_reference_component() -> RtgConstraints:
    return InMemoryRtgConstraints.empty()
