"""Operation outcomes, validation findings, and reports.

Realizes ``RTG::'Operation Status'``, ``RTG::'Validation Finding'``, and
``RTG::'Revisioned Outcome'``.

``RTG::'Validation Report'`` and the parameterless public check operation belong to the
typed-validation authority that later slices carry, so they are deliberately absent
here: this slice reports findings, and the slice that owns reports will wrap them.

The model gives a finding references to the definitions and graph objects it
implicates. This realization carries their natural identities instead of the objects
themselves, so a finding stays a bounded report rather than a second copy of canonical
state that could drift from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

__all__ = [
    "OperationStatus",
    "RevisionedOutcome",
    "ValidationFinding",
]


class OperationStatus(Enum):
    """The outcome of a completed domain operation.

    ``ACCEPTED`` means the operation completed, including an accepted no-op.
    ``REJECTED`` means a well-formed semantic request was not accepted. ``FAILED``
    means an invoked operation did not complete but safely reported that status with
    its promised non-effects intact.
    """

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One typed reason a subject does not conform."""

    summary: str
    implicated_definitions: tuple[str, ...] = ()
    implicated_objects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RevisionedOutcome:
    """An outcome that may have advanced the one total revision.

    The resulting revision is present only when an accepted operation changed
    canonical state; an accepted effective no-op has none.
    """

    status: OperationStatus
    summary: str
    findings: tuple[ValidationFinding, ...] = field(default=())
    resulting_revision: int | None = None

    @property
    def accepted(self) -> bool:
        return self.status is OperationStatus.ACCEPTED
