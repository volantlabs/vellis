from __future__ import annotations

from components.rtg.schema.implementation import InMemoryRtgSchema
from components.rtg.schema.protocol import RtgSchema


def create_reference_component() -> RtgSchema:
    return InMemoryRtgSchema.empty()
