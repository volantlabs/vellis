from __future__ import annotations

from components.rtg.migration.implementation import InMemoryRtgMigration
from components.rtg.migration.protocol import RtgMigration


def create_reference_component() -> RtgMigration:
    return InMemoryRtgMigration.empty()
