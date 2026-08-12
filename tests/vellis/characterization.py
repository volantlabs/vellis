"""Measuring what Vellis's work actually depends on.

Shared by the evidence for ``VellisVerification::currentWorkScaling``,
``historicalSelectionScaling``, ``replayCharacterization``, and the
``historyGrowth`` analysis. The requirements those cases carry are stated over
*semantic record processing* — how many canonical or activity records an operation
handles — rather than over pages, plans, or wall-clock time, so that is the primary
measure here. Duration is recorded too, in seconds, because the replay case asks for it
with its units; nothing asserts on it, because a number measured on one laptop is not a
budget and the analysis says so explicitly.

Three measures, because one would not discriminate:

* the two record counters say how much of each ledger an operation handled, which is
  what the requirements bound, but they are incremented in the store and so cannot
  notice a path that reaches the database another way;
* the traced statements say what was really issued, which catches that path;
* the query plan of those statements says whether a bounded read *seeks* to its interval
  or walks everything before it — a distinction the counters cannot make, because a
  linear scan filtered down to three rows returns three rows either way.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from vellis.canonical import Provenance
from vellis.changes import GraphChange
from vellis.definitions import AnchorTypeDefinition, GraphDefinitionSet
from vellis.graph import Anchor
from vellis.system import RTGSystem

LEDGER_TABLES = ("canonical_record", "activity_record")

OWNER = Provenance(initiator="owner", source="the desk")


def establish(path: Path) -> RTGSystem:
    """Open one system at ``path`` and establish its history base.

    One anchor type, because a characterization varies one thing at a time and the
    vocabulary's own shape is not one of the dimensions being varied.
    """
    system = RTGSystem.open(path)
    outcome = system.initialize_fresh(
        GraphDefinitionSet(
            anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),)
        ),
        provenance=OWNER,
        initialization_summary="a fresh start",
    )
    assert outcome.accepted, outcome.findings
    return system


# --- Building histories along one dimension at a time --------------------------------


def commit_graph_transitions(system: RTGSystem, count: int, *, prefix: str = "g") -> None:
    """Append ``count`` graph mutations that touch no definition."""
    for index in range(count):
        outcome = system.apply_graph_change(
            GraphChange(
                anchor_upserts=(
                    Anchor(uuid=f"{prefix}-{index}", type_key="person", display_name=f"P{index}"),
                )
            ),
            provenance=OWNER,
        )
        assert outcome.accepted, outcome.findings


def commit_definition_changes(system: RTGSystem, count: int, *, prefix: str = "kind") -> None:
    """Widen the vocabulary ``count`` times, each as a staged and activated proposal.

    Two canonical records per change, both definition-changing, and no graph work at all
    — which is what lets a test hold definition history fixed while graph history grows.
    """
    for index in range(count):
        state = system.current_state()
        proposed = GraphDefinitionSet(
            anchor_types=(
                *state.active_definitions.anchor_types,
                AnchorTypeDefinition(type_key=f"{prefix}-{index}", description="Another kind."),
            ),
            associated_data_types=state.active_definitions.associated_data_types,
            link_types=state.active_definitions.link_types,
            relationship_constraints=state.active_definitions.relationship_constraints,
        )
        staged = system.set_definition_delta(proposed, provenance=OWNER)
        assert staged.accepted, staged.findings
        activated = system.activate_definition_delta(provenance=OWNER)
        assert activated.accepted, activated.findings


def observe(system: RTGSystem, count: int) -> None:
    """Grow the activity ledger by ``count`` records through ordinary observed reads."""
    for _ in range(count):
        assert system.definition_summary(provenance=OWNER).accepted


def storage_bytes(system: RTGSystem) -> int:
    """Return how much local storage this system occupies, including its write-ahead log."""
    base = system.store.path
    companions = (base, base.with_name(base.name + "-wal"), base.with_name(base.name + "-shm"))
    return sum(candidate.stat().st_size for candidate in companions if candidate.exists())


# --- Measuring one piece of work ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Measurement:
    """What one piece of work cost, in the units the model's cases are stated in."""

    canonical_record_visits: int
    activity_record_visits: int
    duration_seconds: float
    statements: tuple[str, ...]

    def touches(self, table: str) -> tuple[str, ...]:
        """Return the statements this work issued against ``table``."""
        return tuple(statement for statement in self.statements if table in statement)


@dataclass(frozen=True, slots=True)
class Measured[T]:
    """One piece of work's answer and what it cost."""

    value: T
    cost: Measurement


def measure[T](system: RTGSystem, work: Callable[[], T]) -> Measured[T]:
    """Run ``work`` once and report both its answer and what it cost.

    The trace callback is installed around the work rather than for the whole session so
    that setup statements are not counted as the operation's own.
    """
    statements: list[str] = []
    system.store.reset_instrumentation()
    system.store._connection.set_trace_callback(statements.append)  # noqa: SLF001
    started = time.perf_counter()
    try:
        value = work()
    finally:
        elapsed = time.perf_counter() - started
        system.store._connection.set_trace_callback(None)  # noqa: SLF001
    return Measured(
        value=value,
        cost=Measurement(
            canonical_record_visits=system.store.record_reads,
            activity_record_visits=system.store.activity_reads,
            duration_seconds=elapsed,
            statements=tuple(statements),
        ),
    )


def ledger_scans(system: RTGSystem, cost: Measurement) -> tuple[str, ...]:
    """Return every ledger statement in ``cost`` that the database plans as a scan.

    Asked of the real store, so the plan is the one the real schema and its real indexes
    produce. Traced statements carry their parameters already bound, which is what makes
    them explainable at all.
    """
    scans: list[str] = []
    for statement in cost.statements:
        if not statement.lstrip().upper().startswith("SELECT"):
            continue
        if not any(table in statement for table in LEDGER_TABLES):
            continue
        try:
            plan = system.store._connection.execute(  # noqa: SLF001
                f"EXPLAIN QUERY PLAN {statement}"
            ).fetchall()
        except sqlite3.Error:  # pragma: no cover - a statement no longer explainable
            continue
        detail = " ".join(str(row[-1]) for row in plan)
        if any(f"SCAN {table}" in detail for table in LEDGER_TABLES):
            scans.append(f"{statement} -> {detail}")
    return tuple(scans)
