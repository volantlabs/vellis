"""Test-only adapters from complete semantic fixtures to bounded public edits.

Production callers discover and edit definitions by natural key.  Older semantic
fixtures are intentionally convenient complete sets; this module keeps their oracle
value without restoring a whole-definition-set production API.
"""

from tests.vellis.oracle import materialize_definitions
from vellis.canonical import Provenance
from vellis.definitions import (
    DirectAssociationMultiplicityConstraint,
    GraphDefinitionSet,
    LinkMultiplicityConstraint,
    relationship_identity,
)
from vellis.governance import (
    ActivateDefinitionDeltaRequest,
    DefinitionChange,
    DirectAssociationMultiplicitySelection,
    LinkMultiplicitySelection,
)
from vellis.outcomes import ValidationRequest, ValidationRequestKind, ValidationScope
from vellis.system import RTGSystem


def change_to(system: RTGSystem, target: GraphDefinitionSet) -> DefinitionChange:
    """Derive one test edit from the current active/proposed semantic fixture."""
    proposal_present = system.store._connection.execute(  # noqa: SLF001
        "SELECT proposed_definition_set_id IS NOT NULL FROM state_head WHERE id = 0"
    ).fetchone()[0]
    active = materialize_definitions(system, prospective=bool(proposal_present))
    target_types = {
        *(value.type_key for value in target.anchor_types),
        *(value.type_key for value in target.associated_data_types),
        *(value.type_key for value in target.link_types),
    }
    active_types = {
        *(value.type_key for value in active.anchor_types),
        *(value.type_key for value in active.associated_data_types),
        *(value.type_key for value in active.link_types),
    }
    target_relationships = {
        relationship_identity(value) for value in target.relationship_constraints
    }
    link_removals: list[LinkMultiplicitySelection] = []
    direct_removals: list[DirectAssociationMultiplicitySelection] = []
    for value in active.relationship_constraints:
        if relationship_identity(value) in target_relationships:
            continue
        if isinstance(value, LinkMultiplicityConstraint):
            link_removals.append(
                LinkMultiplicitySelection(
                    value.link_type_key,
                    value.constrained_end,
                    value.constrained_endpoint_type_keys,
                    value.opposite_endpoint_type_keys,
                )
            )
        elif isinstance(value, DirectAssociationMultiplicityConstraint):
            direct_removals.append(
                DirectAssociationMultiplicitySelection(
                    value.constrained_end,
                    value.anchor_type_keys,
                    value.associated_data_type_keys,
                )
            )
    return DefinitionChange(
        anchor_type_upserts=target.anchor_types,
        associated_data_type_upserts=target.associated_data_types,
        link_type_upserts=target.link_types,
        relationship_constraint_upserts=target.relationship_constraints,
        type_removals=tuple(sorted(active_types - target_types)),
        link_multiplicity_removals=tuple(link_removals),
        direct_association_multiplicity_removals=tuple(direct_removals),
    )


def stage_complete_fixture(
    system: RTGSystem, target: GraphDefinitionSet, *, provenance: Provenance
):
    """Stage a complete test fixture through the bounded production edit boundary."""
    return system.set_definition_delta(change_to(system, target), provenance=provenance)


def activate_clean_delta(system: RTGSystem, *, provenance: Provenance):
    """Assess once, then activate by the exact durable assessment identity."""
    assessment = system.check(
        ValidationRequest(
            ValidationRequestKind.ASSESS,
            ValidationScope.DEFINITION_DELTA,
            maximum_findings=100,
        ),
        provenance=provenance,
    )
    assert assessment.accepted and assessment.assessment_id is not None
    return system.activate_definition_delta(
        ActivateDefinitionDeltaRequest(assessment.assessment_id), provenance=provenance
    )
