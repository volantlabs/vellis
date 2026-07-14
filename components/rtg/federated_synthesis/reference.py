from __future__ import annotations

from components.rtg.federated_synthesis.implementation import (
    DeterministicRtgFederatedSynthesizer,
)


def create_reference_component() -> DeterministicRtgFederatedSynthesizer:
    return DeterministicRtgFederatedSynthesizer()
