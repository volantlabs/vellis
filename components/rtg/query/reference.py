from __future__ import annotations

from components.rtg.query.implementation import SimpleRtgQueryEngine
from components.rtg.query.protocol import RtgQueryEngine


def create_reference_component() -> RtgQueryEngine:
    return SimpleRtgQueryEngine()
