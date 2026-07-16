from __future__ import annotations

from components.rtg.controller.coordinator import RtgControllerCoordinator
from components.runtime.component_adapter import ComponentAdapter


def create_reference_component() -> ComponentAdapter:
    """Return the controller participation kit for an ordinary runtime composition."""
    return RtgControllerCoordinator().create_adapter()
