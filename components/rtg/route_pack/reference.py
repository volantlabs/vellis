from __future__ import annotations

from components.rtg.route_pack.implementation import (
    DeterministicRtgRoutePack,
    DeterministicRtgRoutePackBuilder,
    DeterministicRtgRoutePackGate,
)


def create_reference_component() -> DeterministicRtgRoutePack:
    return DeterministicRtgRoutePack()


def create_reference_builder() -> DeterministicRtgRoutePackBuilder:
    return DeterministicRtgRoutePackBuilder()


def create_reference_gate() -> DeterministicRtgRoutePackGate:
    return DeterministicRtgRoutePackGate()
