from __future__ import annotations

from components.rtg.change_validation.implementation import DeterministicRtgChangeValidator
from components.rtg.change_validation.protocol import RtgChangeValidator


def create_reference_component() -> RtgChangeValidator:
    return DeterministicRtgChangeValidator()
