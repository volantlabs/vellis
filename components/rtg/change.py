from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RtgChangeReference:
    """Reference used by an RTG change before and after controller resolution."""

    resource_id: UUID | str | None = None
    local_ref: str | None = None
