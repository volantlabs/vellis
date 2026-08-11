"""Evidence for confirmed first use from a Vellis v1 snapshot.

Carries ``VellisVerification::v1Compatibility``: live v1 content arrives unchanged,
everything the translation cost is named before an owner confirms it, an accepted import
establishes one new lineage at revision 0, and every condition the requirement lists as a
refusal establishes nothing at all.

Snapshots here are built from the v1 shapes rather than copied from a v1 system, so each
case says exactly which piece of v1 meaning it is about. ``_snapshot`` is the smallest
complete one; every test states its own difference from it.
"""

from __future__ import annotations

import io
import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from vellis.definitions import (
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    LinkEnd,
    LinkMultiplicityConstraint,
    definition_set_equal,
)
from vellis.everyday_life import everyday_life_starter
from vellis.graph import graph_equal
from vellis.json_value import JsonKind, loads
from vellis.outcomes import OperationStatus
from vellis.paths import store_path
from vellis.patterns import compile_pattern
from vellis.query import AnchorGroup, AnchorProjection, GraphQuery, ReturnShape
from vellis.setup import EXIT_DECLINED, EXIT_FAILED, EXIT_SUCCESS, main
from vellis.system import RTGSystem
from vellis.v1 import (
    ImportPreview,
    RecoveryDisposition,
    SnapshotError,
    analyze_v1_snapshot,
    looks_like_v1_snapshot,
    snapshot_identity,
)


def _snapshot() -> dict[str, Any]:
    """One complete v1 snapshot: a named person, their facts, and a link to a place."""
    base: dict[str, Any] = {
        "graph": {
            "anchors": [
                {"uuid": "a1", "type": "Person", "display_name": "Ada", "system": {"live": True}},
                {"uuid": "a2", "type": "Place", "display_name": "Home", "system": {}},
            ],
            "data_objects": [
                {
                    "uuid": "d1",
                    "type": "PersonFacts",
                    "properties": {"name": "Ada", "notes": {"kept": ["one", 2]}},
                    "system": {"live": True, "origin": "import"},
                }
            ],
            "links": [
                {
                    "uuid": "l1",
                    "type": "lives_in",
                    "source_uuid": "a1",
                    "target_uuid": "a2",
                    "system": {},
                }
            ],
            "anchor_data_index": {"a1": ["d1"]},
        },
        "schema": {
            "definitions": [
                {
                    "uuid": "s1",
                    "kind": "anchor",
                    "type_key": "Person",
                    "description": "A person.",
                    "payload": {"required_data_types": ["PersonFacts"]},
                    "system": {"live": True},
                },
                {
                    "uuid": "s2",
                    "kind": "anchor",
                    "type_key": "Place",
                    "description": "A place.",
                    "payload": {},
                    "system": {},
                },
                {
                    "uuid": "s3",
                    "kind": "data_object",
                    "type_key": "PersonFacts",
                    "description": "Facts about a person.",
                    "payload": {
                        "properties": {
                            "name": {"required": True, "value_kinds": ["string"]},
                            "notes": {"required": False, "value_kinds": ["object"]},
                        }
                    },
                    "system": {},
                },
                {
                    "uuid": "s4",
                    "kind": "link",
                    "type_key": "lives_in",
                    "description": "Someone lives somewhere.",
                    "payload": {
                        "allowed_source_types": ["Person"],
                        "allowed_target_types": ["Place"],
                    },
                    "system": {},
                },
            ]
        },
        "constraints": {"constraints": []},
        "migration": {"migrations": []},
    }
    return base


def _write(tmp_path: Path, content: Mapping[str, Any], name: str = "snap.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def _run(argv: list[str], answer: str = "y\n") -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(argv, stdout=out, stderr=err, stdin=io.StringIO(answer))
    return code, out.getvalue(), err.getvalue()


def _analyzed(content: Mapping[str, Any]) -> ImportPreview:
    """Analyze the way the command does: through the JSON the owner's file actually holds.

    A snapshot read from a file carries exact decimals where a Python mapping carries
    machine integers, and a rule an owner wrote must not depend on which door it came in.
    """
    return analyze_v1_snapshot(loads(json.dumps(content)))


def _findings(content: Mapping[str, Any], disposition: RecoveryDisposition) -> tuple[str, ...]:
    preview = _analyzed(content)
    return tuple(
        each.summary for each in preview.report.findings if each.disposition is disposition
    )


def _established(destination: Path) -> RTGSystem:
    return RTGSystem.open(store_path(destination.resolve()))


# --- What a snapshot is -------------------------------------------------------------


def test_a_section_that_says_nothing_is_not_a_section_that_says_none() -> None:
    """An explicit null is a snapshot this cannot read, not an empty one."""
    content = _snapshot()
    content["graph"]["links"] = None

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any("links is not a list" in each.summary for each in preview.report.blocking_findings)


def test_a_document_missing_a_section_is_not_a_snapshot() -> None:
    """A v1 snapshot names no format, so its four sections are the whole of what says so."""
    for section in ("graph", "schema", "constraints", "migration"):
        content = _snapshot()
        del content[section]
        assert not looks_like_v1_snapshot(content)
        with pytest.raises(SnapshotError):
            _analyzed(content)


def test_the_same_content_is_the_same_snapshot_however_it_is_written() -> None:
    """Identity is over what the snapshot says, not how the file was formatted."""
    content = _snapshot()
    reordered = json.loads(json.dumps(content, sort_keys=True))

    assert snapshot_identity(content) == snapshot_identity(reordered)
    changed = _snapshot()
    changed["graph"]["anchors"][0]["display_name"] = "Ada L"
    assert snapshot_identity(changed) != snapshot_identity(content)


@pytest.mark.parametrize("section", ["schema", "constraints", "migration"])
def test_a_change_anywhere_in_the_snapshot_is_a_different_snapshot(section: str) -> None:
    """Identity binds the confirmation, so it has to cover everything a snapshot says."""
    changed = _snapshot()
    if section == "schema":
        changed["schema"]["definitions"][2]["payload"]["properties"]["name"]["required"] = False
    elif section == "constraints":
        changed["constraints"]["constraints"] = [
            {"uuid": "c1", "kind": "query_pattern", "display_name": "n", "payload": {}}
        ]
    else:
        changed["migration"]["migrations"] = [{"migration_id": "m1", "status": "applied"}]

    assert snapshot_identity(changed) != snapshot_identity(_snapshot())


# --- What arrives unchanged ---------------------------------------------------------


def test_live_graph_content_arrives_exactly_as_v1_stored_it() -> None:
    """Excludes an import that renames, renumbers, or tidies anything on the way in."""
    graph = _analyzed(_snapshot()).candidate.graph

    anchor = next(each for each in graph.anchors if each.uuid == "a1")
    assert (anchor.type_key, anchor.display_name) == ("Person", "Ada")
    data = graph.associated_data[0]
    assert (data.uuid, data.type_key) == ("d1", "PersonFacts")
    assert data.properties == {"name": "Ada", "notes": {"kept": ["one", Decimal(2)]}}
    assert data.system_metadata.members["origin"] == "import"
    assert data.anchor_uuids == ("a1",)
    link = graph.links[0]
    assert (link.uuid, link.type_key) == ("l1", "lives_in")
    assert (link.source_uuid, link.target_uuid) == ("a1", "a2")


def test_a_record_that_does_not_say_it_is_live_is_live() -> None:
    """The v1 convention: absent means live, and an absent metadata object means it too."""
    graph = _analyzed(_snapshot()).candidate.graph

    assert {each.uuid for each in graph.anchors} == {"a1", "a2"}
    assert graph.links[0].system_metadata.members["live"] is True


def test_non_live_content_is_left_behind_and_named() -> None:
    """Excludes importing staged v1 content, and excludes doing it silently."""
    content = _snapshot()
    content["graph"]["anchors"].append(
        {"uuid": "a9", "type": "Place", "display_name": "Draft", "system": {"live": False}}
    )

    preview = _analyzed(content)

    assert {each.uuid for each in preview.candidate.graph.anchors} == {"a1", "a2"}
    assert any("a9" in each for each in _findings(content, RecoveryDisposition.OMITTED))


def test_only_an_unnamed_anchor_is_given_a_recovered_name() -> None:
    """Built from the anchor's own stored values, and only where v1 stored no name."""
    content = _snapshot()
    del content["graph"]["anchors"][1]["display_name"]

    preview = _analyzed(content)

    named = {each.uuid: each.display_name for each in preview.candidate.graph.anchors}
    assert named == {"a1": "Ada", "a2": "[recovered] Place a2"}
    assert any(
        "[recovered] Place a2" in each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


# --- What is translated -------------------------------------------------------------


def test_definitions_translate_by_natural_identity_and_drop_v1_bookkeeping() -> None:
    """A v2 type is its type key; a v1 definition UUID and lifecycle say nothing here."""
    definitions = _analyzed(_snapshot()).candidate.active_definitions

    assert {each.type_key for each in definitions.anchor_types} == {"Person", "Place"}
    assert [each.type_key for each in definitions.associated_data_types] == ["PersonFacts"]
    person = definitions.anchor_type("Person")
    assert person is not None
    assert person.description == "A person."
    facts = definitions.associated_data_type("PersonFacts")
    assert facts is not None
    assert facts.permitted_anchor_type_keys == ("Person",)
    assert {each.property_name: each.required for each in facts.property_constraints} == {
        "name": True,
        "notes": False,
    }
    assert {each.property_name: each.json_kind for each in facts.property_constraints} == {
        "name": JsonKind.STRING,
        "notes": JsonKind.OBJECT,
    }


def test_a_required_data_type_becomes_the_rule_it_was() -> None:
    """v1 says requiredness on the anchor; v2 says it as a multiplicity on the association."""
    definitions = _analyzed(_snapshot()).candidate.active_definitions

    required = definitions.relationship_constraints
    assert len(required) == 1
    rule = required[0]
    assert isinstance(rule, DirectAssociationMultiplicityConstraint)
    assert rule.constrained_end is DirectAssociationEnd.ANCHOR
    assert rule.anchor_type_keys == ("Person",)
    assert rule.associated_data_type_keys == ("PersonFacts",)
    assert rule.lower_bound == 1


def test_link_endpoints_are_preserved_in_both_directions() -> None:
    definitions = _analyzed(_snapshot()).candidate.active_definitions

    link = definitions.link_type("lives_in")
    assert link is not None
    assert link.endpoint_constraint.permitted_source_type_keys == ("Person",)
    assert link.endpoint_constraint.permitted_target_type_keys == ("Place",)


def test_ranges_and_permitted_values_are_preserved() -> None:
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["age"] = {
        "required": False,
        "value_kinds": ["integer"],
        "minimum": 0,
        "maximum": 200,
    }
    content["schema"]["definitions"][2]["payload"]["properties"]["mood"] = {
        "required": False,
        "value_kinds": ["string"],
        "allowed_values": ["well", "tired"],
    }

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    rules = {each.property_name: each for each in facts.property_constraints}
    assert rules["age"].value_range is not None
    assert rules["age"].value_range.lower_bound == Decimal(0)
    assert rules["age"].value_range.upper_bound == Decimal(200)
    assert rules["mood"].value_range is not None
    assert rules["mood"].value_range.permitted_values == ("well", "tired")


def test_a_pattern_keeps_the_values_v1_let_through() -> None:
    """v1 asked whether the expression appeared in a value; v2 asks about the whole of it.

    Excludes carrying the expression as written, which would tighten every v1 pattern into
    a rule the owner never wrote — refusing their own stored values, or silently governing
    what they may store next.
    """
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"]["pattern"] = "[A-Z]"
    content["graph"]["data_objects"][0]["properties"]["name"] = "of Ada"

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    name = next(each for each in facts.property_constraints if each.property_name == "name")
    assert name.pattern is not None
    matches = compile_pattern(name.pattern.expression).matches
    assert matches("of Ada") and matches("Ada")
    assert not matches("ada")


def test_a_pattern_still_means_by_a_dot_what_v1_meant() -> None:
    """Excludes letting what this added to the expression change the expression."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"]["pattern"] = "A.a"
    content["graph"]["data_objects"][0]["properties"]["name"] = "Ada"

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")

    assert facts is not None
    name = next(each for each in facts.property_constraints if each.property_name == "name")
    assert name.pattern is not None
    matches = compile_pattern(name.pattern.expression).matches
    assert matches("Ada") and matches("of Ada")
    # v1 read a dot as any character but a newline, and so does what arrives here.
    assert not matches("A\na")


def test_a_pattern_anchored_in_v1_stays_anchored() -> None:
    """An expression that could only match at the start still can, and only there."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"]["pattern"] = "^[A-Z]"
    content["graph"]["data_objects"][0]["properties"]["name"] = "Ada"

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")

    assert facts is not None
    name = next(each for each in facts.property_constraints if each.property_name == "name")
    assert name.pattern is not None
    matches = compile_pattern(name.pattern.expression).matches
    assert matches("Ada Lovelace")
    assert not matches("of Ada")


# --- What the translation costs, said before it is agreed to ------------------------


def test_a_refinement_v2_cannot_say_is_removed_rather_than_approximated() -> None:
    """Excludes turning a v1 format into an invented pattern nobody wrote."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["born"] = {
        "required": False,
        "value_kinds": ["string"],
        "format": "date",
    }

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    born = next(each for each in facts.property_constraints if each.property_name == "born")
    assert born.pattern is None
    assert born.value_range is None
    assert any("format" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_a_property_of_several_kinds_narrows_to_what_the_values_say() -> None:
    """The owner's own values decide, and the narrowing is named."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["either"] = {
        "required": False,
        "value_kinds": ["string", "integer"],
    }
    content["graph"]["data_objects"][0]["properties"]["either"] = "text"

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    either = next(each for each in facts.property_constraints if each.property_name == "either")
    assert either.json_kind is JsonKind.STRING
    assert any("either" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_a_property_of_several_kinds_nothing_uses_is_left_out() -> None:
    """Nothing depends on it, so leaving it out costs no meaning — and it is still said."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["either"] = {
        "required": False,
        "value_kinds": ["string", "integer"],
    }

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    assert all(each.property_name != "either" for each in facts.property_constraints)
    assert any("either" in each for each in _findings(content, RecoveryDisposition.OMITTED))


def test_a_description_v1_never_had_is_written_and_declared() -> None:
    """v2 wants every rule readable; the words that were not the owner's are named."""
    synthesized = _findings(_snapshot(), RecoveryDisposition.SIMPLIFIED)

    assert any("PersonFacts.name" in each for each in synthesized)
    assert any("lives_in" in each for each in synthesized)


def test_a_v1_query_constraint_is_left_out_and_named() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "query_pattern",
            "display_name": "everyone is named",
            "target_type_keys": ["PersonFacts"],
            "description": "d",
            "payload": {},
            "system": {},
        }
    ]

    assert any(
        "everyone is named" in each for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_v1_migrations_and_ledger_positions_are_left_out_and_named() -> None:
    """How a v1 system changed is not memory, and its ledger is not this lineage's."""
    content = _snapshot()
    content["migration"]["migrations"] = [
        {"migration_id": "m1", "description": "install", "status": "applied"}
    ]
    # Nothing about position zero makes it less of a position.
    content["last_ledger_position"] = 0

    omitted = _findings(content, RecoveryDisposition.OMITTED)
    assert any("migration" in each for each in omitted)
    assert any("ledger position" in each for each in omitted)


def test_a_grounding_by_a_soft_deleted_anchor_is_left_out_with_that_anchor() -> None:
    """Only live content becomes memory, and that is as true of a grounding as of an anchor.

    The fact group is still grounded by the anchor that is live, so nothing an owner has is
    lost. Excludes refusing a v1 system that was valid over a grounding this had already
    decided not to import, and excludes keeping a grounding to something that is not here.
    """
    content = _snapshot()
    content["graph"]["anchors"].append(
        {"uuid": "a9", "type": "Person", "display_name": "Gone", "system": {"live": False}}
    )
    content["graph"]["anchor_data_index"]["a9"] = ["d1"]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.graph.associated_data[0].anchor_uuids == ("a1",)
    assert any(
        "grounded by the anchor a9" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_fact_group_left_with_no_live_anchor_at_all_is_refused() -> None:
    """Nothing grounds it once its only anchor is not memory, and v2 holds nothing loose.

    Excludes repairing the graph by inventing a grounding, and excludes importing a fact
    group that belongs to nothing.
    """
    content = _snapshot()
    content["graph"]["anchors"][0]["system"] = {"live": False}

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert preview.candidate.graph.associated_data[0].anchor_uuids == ()


def test_an_optional_data_type_stays_optional() -> None:
    """Excludes making every v1 association mandatory on the way in."""
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}

    definitions = _analyzed(content).candidate.active_definitions

    assert definitions.relationship_constraints == ()
    facts = definitions.associated_data_type("PersonFacts")
    assert facts is not None
    assert facts.permitted_anchor_type_keys == ("Person",)


def test_a_v1_kind_that_says_more_than_a_v2_kind_says_so() -> None:
    """A whole number and a UUID are refinements v2 has no word for."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["age"] = {
        "required": False,
        "value_kinds": ["integer"],
    }
    content["schema"]["definitions"][2]["payload"]["properties"]["ref"] = {
        "required": False,
        "value_kinds": ["uuid"],
    }

    removed = _findings(content, RecoveryDisposition.SIMPLIFIED)

    assert any("whole numbers" in each for each in removed)
    assert any("UUID" in each for each in removed)


@pytest.mark.parametrize(
    ("rule", "expected"),
    [
        ({"required": False, "value_kinds": ["string"], "minimum": 0}, "numeric bounds"),
        ({"required": False, "value_kinds": ["integer"], "pattern": "x"}, "no value can match"),
        ({"required": False, "value_kinds": ["string"], "pattern": "(unclosed"}, "cannot evaluate"),
        ({"required": False, "value_kinds": ["string"], "pattern": 7}, "not text"),
    ],
)
def test_a_condition_that_says_nothing_about_its_values_is_removed_and_named(
    rule: dict[str, Any], expected: str
) -> None:
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["odd"] = rule

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    odd = next(each for each in facts.property_constraints if each.property_name == "odd")
    assert odd.pattern is None
    assert odd.value_range is None
    assert _analyzed(content).is_acceptable
    assert any(expected in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_the_translated_vocabulary_is_the_same_however_the_file_is_written() -> None:
    """One snapshot means one candidate; identity would say nothing otherwise."""
    content = _snapshot()
    content["schema"]["definitions"][1]["payload"] = {"required_data_types": ["PersonFacts"]}
    reordered = json.loads(json.dumps(content, sort_keys=True))

    assert definition_set_equal(
        _analyzed(content).candidate.active_definitions,
        _analyzed(reordered).candidate.active_definitions,
    )
    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    assert facts.permitted_anchor_type_keys == ("Person", "Place")


def test_a_cardinality_rule_about_types_is_carried_across() -> None:
    """v1 states it over a query; where that query is just types, v2 states the same rule."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "one set of facts per person",
            "description": "A person carries exactly one set of facts.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 1,
            },
            "system": {},
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    definitions = preview.candidate.active_definitions
    carried = [
        each
        for each in definitions.relationship_constraints
        if isinstance(each, DirectAssociationMultiplicityConstraint) and each.upper_bound == 1
    ]
    assert len(carried) == 1
    assert carried[0].anchor_type_keys == ("Person",)
    assert carried[0].associated_data_type_keys == ("PersonFacts",)
    assert carried[0].lower_bound == 1
    assert any(
        "one set of facts per person is carried across" in each
        for each in _findings(content, RecoveryDisposition.PRESERVED)
    )


def test_a_link_cardinality_rule_says_which_end_it_counts() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c2",
            "kind": "cardinality",
            "display_name": "one home each",
            "description": "A person lives in one place.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "p", "anchor_type_keys": ["Person"]},
                        {"name": "h", "anchor_type_keys": ["Place"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "l",
                            "source_bucket": "p",
                            "target_bucket": "h",
                            "link_type_keys": ["lives_in"],
                        }
                    ],
                },
                "counted_binding": "l",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 1,
            },
            "system": {},
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    carried = [
        each
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint)
    ]
    assert len(carried) == 1
    assert carried[0].link_type_key == "lives_in"
    assert carried[0].constrained_end is LinkEnd.SOURCE
    assert carried[0].constrained_endpoint_type_keys == ("Person",)
    assert carried[0].opposite_endpoint_type_keys == ("Place",)
    assert carried[0].upper_bound == 1
    # A rule that asked for none lost no floor, so the report has nothing to say about one.
    assert not any(
        "the floor is not" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_a_cardinality_rule_refining_a_v1_requirement_is_one_rule_here(
    tmp_path: Path,
) -> None:
    """v1 says it twice — required on the anchor, counted in a rule — and v2 says it once."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "exactly one set of facts",
            "description": "A person carries exactly one set of facts.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert rules[0].upper_bound == 1
    assert any(
        "bounded 1..1, which is what both of them said (1..* and 1..1)" in each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )
    # And it survives the whole command, not only the analysis.
    destination = tmp_path / "v"
    assert (
        _run(["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))])[0]
        == EXIT_SUCCESS
    )
    system = _established(destination)
    try:
        carried = system.current_state().active_definitions.relationship_constraints
    finally:
        system.close()
    assert len(carried) == 1
    assert carried[0].upper_bound == 1


@pytest.mark.parametrize(
    ("bounds", "expected"),
    [
        ({"minimum": 0, "maximum": 3}, (1, 3)),
        ({"minimum": 2}, (2, None)),
        ({"minimum": 0, "maximum": 9}, (1, 9)),
    ],
)
def test_two_v1_rules_about_one_thing_become_the_one_rule_both_of_them_meant(
    bounds: dict[str, Any], expected: tuple[int, int | None]
) -> None:
    """Excludes keeping whichever rule says more, which drops what the other said."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "how many",
            "description": "How many sets of facts a person carries.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                **bounds,
            },
        }
    ]

    rules = _analyzed(content).candidate.active_definitions.relationship_constraints

    assert len(rules) == 1
    assert (rules[0].lower_bound, rules[0].upper_bound) == expected


def test_two_bounded_v1_rules_become_the_range_both_of_them_allowed() -> None:
    """Neither file order nor which rule says more decides; what both said does."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": f"c{index}",
            "kind": "cardinality",
            "display_name": f"count {index}",
            "description": "How many sets of facts a person carries.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": lower,
                "maximum": upper,
            },
        }
        for index, (lower, upper) in enumerate(((1, 5), (2, 3)))
    ]

    rules = _analyzed(content).candidate.active_definitions.relationship_constraints

    assert len(rules) == 1
    assert (rules[0].lower_bound, rules[0].upper_bound) == (2, 3)


def test_the_owner_s_own_words_survive_a_merge() -> None:
    """Excludes writing over a description the owner wrote, and saying they wrote none."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "one set of facts",
            "description": "A person carries exactly one set of facts.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert rules[0].description == "A person carries exactly one set of facts."
    assert not any(
        "the rule counting" in each and "had no readable description" in each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


@pytest.mark.parametrize(
    "difference",
    [
        {"query_spec": {"anchor_buckets": [{"name": "w", "anchor_type_keys": ["Place"]}]}},
        {"link_type_keys": ["lives_in", "visits"]},
        {"group_by_bindings": ["l"]},
    ],
    ids=["a third bucket", "two link types", "grouped by the count itself"],
)
def test_a_link_count_over_more_than_the_types_it_names_is_left_out(
    difference: dict[str, Any],
) -> None:
    payload: dict[str, Any] = {
        "query_spec": {
            "anchor_buckets": [
                {"name": "p", "anchor_type_keys": ["Person"]},
                {"name": "h", "anchor_type_keys": ["Place"]},
            ],
            "link_requirements": [
                {
                    "name": "l",
                    "source_bucket": "p",
                    "target_bucket": "h",
                    "link_type_keys": ["lives_in"],
                }
            ],
        },
        "counted_binding": "l",
        "group_by_bindings": ["p"],
        "minimum": 0,
        "maximum": 1,
    }
    if "query_spec" in difference:
        payload["query_spec"]["anchor_buckets"].extend(difference["query_spec"]["anchor_buckets"])
    elif "link_type_keys" in difference:
        payload["query_spec"]["link_requirements"][0]["link_type_keys"] = difference[
            "link_type_keys"
        ]
    else:
        payload["group_by_bindings"] = difference["group_by_bindings"]
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {"uuid": "c1", "kind": "cardinality", "display_name": "odd count", "payload": payload}
    ]

    preview = _analyzed(content)

    assert all(
        not isinstance(each, LinkMultiplicityConstraint)
        for each in preview.candidate.active_definitions.relationship_constraints
    )
    assert any(
        "counts what a query selected" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_count_with_no_lower_bound_asks_for_none() -> None:
    """v1 wrote a ceiling and no floor; adding a floor would be writing a rule for them."""
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at most two",
            "description": "At most two sets of facts.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "maximum": 2,
            },
        }
    ]

    rules = _analyzed(content).candidate.active_definitions.relationship_constraints

    assert len(rules) == 1
    assert (rules[0].lower_bound, rules[0].upper_bound) == (0, 2)


@pytest.mark.parametrize(
    ("difference", "expected"),
    [
        ({"counted_binding": 42}, "does not say what it counts"),
        ({"group_by_bindings": "p"}, "does not say what it counts by"),
        ({"query_spec": "everything"}, "names a query that is not an object"),
        ({"counted_binding": "ghost"}, "counts what a query selected"),
    ],
    ids=["an unreadable count", "an unreadable grouping", "no query", "a count of nothing named"],
)
def test_a_count_this_cannot_read_is_never_reported_as_a_query_it_could(
    difference: dict[str, Any], expected: str
) -> None:
    """Excludes telling an owner their rule was inexpressible when it was unreadable."""
    payload: dict[str, Any] = {
        "query_spec": {
            "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
            "data_requirements": [
                {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
            ],
        },
        "counted_binding": "f",
        "group_by_bindings": ["p"],
        "minimum": 1,
        **difference,
    }
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {"uuid": "c1", "kind": "cardinality", "display_name": "odd count", "payload": payload}
    ]

    preview = _analyzed(content)

    if expected == "counts what a query selected":
        # Readable, and simply not a rule about types: left out, and said so truthfully.
        assert preview.is_acceptable
        assert any(expected in each for each in _findings(content, RecoveryDisposition.OMITTED))
        return
    assert not preview.is_acceptable
    assert any(expected in each.summary for each in preview.report.blocking_findings)
    assert not any(
        "counts what a query selected" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_count_referring_to_a_set_its_query_never_names_is_refused() -> None:
    """Excludes carrying a rule that names no types and calling it preserved."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at most two",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "people", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "ghost", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["ghost"],
                "minimum": 0,
                "maximum": 2,
            },
        }
    ]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "which its query does not name" in each.summary for each in preview.report.blocking_findings
    )
    assert not any(
        "carried across as it stands" in each
        for each in _findings(content, RecoveryDisposition.PRESERVED)
    )


def test_a_floor_over_a_required_join_is_not_carried_as_a_floor_over_a_type() -> None:
    """v1 counted the rows a query returned; a required part kept only the rows it matched.

    So the floor never reached anything that had none of what it counted. Excludes turning
    'of those that have any, at least one' into 'every one of these, at least one', which
    would refuse a v1 system that was valid.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["graph"]["anchors"].append(
        {"uuid": "a3", "type": "Person", "display_name": "Grace", "system": {}}
    )
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "one set of facts each",
            "description": "Exactly one set of facts.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert (rules[0].lower_bound, rules[0].upper_bound) == (0, 1)
    assert any(
        "only of those that had any" in each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_a_rule_counting_a_type_this_left_out_is_left_out_with_it() -> None:
    """Excludes refusing an import whose pieces are each supported on their own."""
    content = _snapshot()
    content["schema"]["definitions"].append(
        {
            "uuid": "s9",
            "kind": "data_object",
            "type_key": "Stale",
            "description": "Nothing carries these.",
            "payload": {"properties": {}},
            "system": {},
        }
    )
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at most two stale",
            "description": "At most two.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "Stale"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 2,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.active_definitions.associated_data_type("Stale") is None
    omitted = _findings(content, RecoveryDisposition.OMITTED)
    assert any("Stale" in each and "left out" in each for each in omitted)
    assert any("counts a type this vocabulary left out" in each for each in omitted)


@pytest.mark.parametrize(
    "second",
    ["another fact requirement", "another link requirement", "one bucket joined to itself"],
)
def test_a_count_over_a_query_that_narrowed_what_it_reached_is_left_out(second: str) -> None:
    """v1 counted the rows its query returned; a second requirement kept only some of them.

    Excludes carrying a rule about the people who also had a job as a rule about everyone.
    """
    query: dict[str, Any] = {
        "anchor_buckets": [
            {"name": "p", "anchor_type_keys": ["Person"]},
            {"name": "h", "anchor_type_keys": ["Place"]},
        ],
    }
    counted = "f"
    if second == "another fact requirement":
        query["anchor_buckets"] = [{"name": "p", "anchor_type_keys": ["Person"]}]
        query["data_requirements"] = [
            {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"},
            {"name": "job", "anchor_bucket": "p", "data_type_key": "Employment"},
        ]
    elif second == "another link requirement":
        counted = "l"
        query["link_requirements"] = [
            {
                "name": "l",
                "source_bucket": "p",
                "target_bucket": "h",
                "link_type_keys": ["lives_in"],
            },
            {
                "name": "w",
                "source_bucket": "p",
                "target_bucket": "h",
                "link_type_keys": ["visits"],
            },
        ]
    else:
        counted = "l"
        query["link_requirements"] = [
            {
                "name": "l",
                "source_bucket": "p",
                "target_bucket": "p",
                "link_type_keys": ["lives_in"],
            }
        ]
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "a narrowed count",
            "payload": {
                "query_spec": query,
                "counted_binding": counted,
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 2,
            },
        }
    ]

    preview = _analyzed(content)

    assert all(
        each.upper_bound is None
        for each in preview.candidate.active_definitions.relationship_constraints
    )
    assert any(
        "counts what a query selected" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_floor_counted_at_the_end_a_link_may_not_reach_is_not_carried() -> None:
    """v1 kept a row for a target with no link by dropping the target from it.

    So that row formed no group, and the floor never reached it. Excludes refusing a v1
    system over a rule that never bound the thing it is now said to bind.
    """
    content = _snapshot()
    content["graph"]["anchors"].append(
        {"uuid": "a3", "type": "Place", "display_name": "Empty", "system": {}}
    )
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at least one resident",
            "description": "A place has residents.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "p", "anchor_type_keys": ["Person"]},
                        {"name": "h", "anchor_type_keys": ["Place"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "l",
                            "source_bucket": "p",
                            "target_bucket": "h",
                            "link_type_keys": ["lives_in"],
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "l",
                "group_by_bindings": ["h"],
                "minimum": 1,
                "maximum": 3,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    counted = next(
        each
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint)
    )
    assert (counted.lower_bound, counted.upper_bound) == (0, 3)
    assert any(
        "only of those that had any" in each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


@pytest.mark.parametrize(
    "retired",
    ["a required fact type", "an endpoint type", "an endpoint list v1 left empty"],
)
def test_a_definition_that_names_what_v1_retired_is_left_out_not_refused(retired: str) -> None:
    """v1 retires a type by making it non-live and leaves the definitions that mention it.

    Nothing imported depends on any of them, so leaving them out costs no meaning — and
    refusing the whole system over a tidy-up the owner did in v1 would.
    """
    content = _snapshot()
    content["graph"]["anchors"] = []
    content["graph"]["data_objects"] = []
    content["graph"]["links"] = []
    content["graph"]["anchor_data_index"] = {}
    if retired == "a required fact type":
        content["schema"]["definitions"][2]["system"] = {"live": False}
    elif retired == "an endpoint type":
        content["schema"]["definitions"][0]["payload"] = {}
        content["schema"]["definitions"][2]["system"] = {"live": False}
        content["schema"]["definitions"][1]["system"] = {"live": False}
    else:
        content["schema"]["definitions"][0]["payload"] = {}
        content["schema"]["definitions"][2]["system"] = {"live": False}
        content["schema"]["definitions"][3]["payload"] = {"allowed_source_types": ["Person"]}

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert any("left out" in each for each in _findings(content, RecoveryDisposition.OMITTED))


def test_a_count_grouped_by_anything_but_what_carries_it_is_left_out() -> None:
    """A ceiling over a whole system, or over the count itself, is not a rule about a type."""
    for grouping in ([], ["f"], ["h"]):
        content = _snapshot()
        content["constraints"]["constraints"] = [
            {
                "uuid": "c1",
                "kind": "cardinality",
                "display_name": "odd grouping",
                "payload": {
                    "query_spec": {
                        "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                        "data_requirements": [
                            {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                        ],
                    },
                    "counted_binding": "f",
                    "group_by_bindings": grouping,
                    "minimum": 0,
                    "maximum": 5,
                },
            }
        ]

        preview = _analyzed(content)

        assert all(
            each.upper_bound is None
            for each in preview.candidate.active_definitions.relationship_constraints
        ), grouping
        assert any(
            "counts what a query selected" in each
            for each in _findings(content, RecoveryDisposition.OMITTED)
        ), grouping


def test_a_cardinality_rule_that_cannot_be_read_is_one_reason_among_the_others() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c9",
            "kind": "cardinality",
            "display_name": "unnamed parts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [{"anchor_bucket": "p", "data_type_key": "PersonFacts"}],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "unnamed parts cannot be read" in each.summary for each in preview.report.blocking_findings
    )
    # And the rest of the account is still there.
    assert preview.candidate.active_definitions.anchor_type("Person") is not None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"minimum": "many"}, "not a whole number"),
        ({"minimum": 1, "maximum": 1.5}, "not a whole number"),
        ({"minimum": True}, "not a whole number"),
    ],
)
def test_a_count_bounded_by_something_that_is_not_one_is_refused(
    payload: dict[str, Any], expected: str
) -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "odd bounds",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                **payload,
            },
        }
    ]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(expected in each.summary for each in preview.report.blocking_findings)


def test_a_type_named_in_a_count_that_is_not_text_is_refused() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "odd types",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person", 7]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "anchor type that is not a type" in each.summary
        for each in preview.report.blocking_findings
    )


def test_a_link_count_can_be_about_either_end() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c2",
            "kind": "cardinality",
            "display_name": "one resident each",
            "description": "A place holds one resident.",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "p", "anchor_type_keys": ["Person"]},
                        {"name": "h", "anchor_type_keys": ["Place"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "l",
                            "source_bucket": "p",
                            "target_bucket": "h",
                            "link_type_keys": ["lives_in"],
                        }
                    ],
                },
                "counted_binding": "l",
                "group_by_bindings": ["h"],
                "minimum": 0,
                "maximum": 1,
            },
        }
    ]

    carried = [
        each
        for each in _analyzed(content).candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint)
    ]

    assert len(carried) == 1
    assert carried[0].constrained_end is LinkEnd.TARGET
    assert carried[0].constrained_endpoint_type_keys == ("Place",)
    assert carried[0].opposite_endpoint_type_keys == ("Person",)


def test_a_cardinality_rule_about_a_selection_is_left_out_and_named() -> None:
    """A count of what a filtered query found is not a rule about a type."""
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c3",
            "kind": "cardinality",
            "display_name": "at most two recent notes",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "predicates": [{"path": "name", "operator": "equals", "value": "Ada"}],
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 2,
            },
            "system": {},
        }
    ]

    preview = _analyzed(content)

    assert preview.candidate.active_definitions.relationship_constraints[0].lower_bound == 1
    assert any(
        "counts what a query selected" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_constraint_of_a_kind_this_does_not_know_gets_no_invented_reason() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {"uuid": "c4", "kind": "uniqueness", "display_name": "one name each", "payload": {}}
    ]

    omitted = _findings(content, RecoveryDisposition.OMITTED)

    assert any("does not recognise" in each for each in omitted)
    assert not any("counts what a query selected" in each for each in omitted)


def test_a_non_live_constraint_is_left_behind_as_one() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {"uuid": "c5", "kind": "cardinality", "display_name": "retired", "system": {"live": False}}
    ]

    assert any(
        "the non-live constraint" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_definition_payload_says_things_this_does_not_carry() -> None:
    """Excludes a report that names lost property rules but not lost type rules."""
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"]["display_template"] = "{name}"
    content["schema"]["definitions"][3]["payload"]["symmetric"] = True

    simplified = _findings(content, RecoveryDisposition.SIMPLIFIED)

    assert any("display_template" in each for each in simplified)
    assert any("symmetric" in each for each in simplified)


def test_a_v1_list_that_says_the_same_thing_twice_says_it_once_here() -> None:
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"]["required_data_types"] = [
        "PersonFacts",
        "PersonFacts",
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable
    assert len(preview.candidate.active_definitions.relationship_constraints) == 1


def test_an_anchor_that_already_grounds_facts_may_still_ground_them_here() -> None:
    """v1 checked that required facts were present; it never said which anchors could hold a
    fact group. So a v1 system where a Place carries PersonFacts is valid v1, and refusing
    it here would refuse a system v1 accepted. Excludes reading v1's required and optional
    lists as a grounding whitelist.
    """
    content = _snapshot()
    content["graph"]["data_objects"].append(
        {"uuid": "d2", "type": "PersonFacts", "properties": {"name": "Home"}, "system": {}}
    )
    content["graph"]["anchor_data_index"]["a2"] = ["d2"]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    assert facts.permitted_anchor_type_keys == ("Person", "Place")
    assert any("Place" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_a_link_type_keeps_the_ends_this_vocabulary_still_describes() -> None:
    """A retired v1 type leaves its name behind in the definitions that mentioned it.

    Excludes dropping a whole link type over one retired name, which would leave the live
    links of that type with nothing describing them and refuse the import.
    """
    content = _snapshot()
    content["schema"]["definitions"][3]["payload"]["allowed_source_types"] = ["Person", "Ghost"]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    lives_in = preview.candidate.active_definitions.link_type("lives_in")
    assert lives_in is not None
    assert lives_in.endpoint_constraint.permitted_source_type_keys == ("Person",)
    assert any("lives_in" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_a_rule_counting_a_link_whose_ends_were_narrowed_is_still_carried() -> None:
    """Narrowing a link type's ends keeps the type, so a rule counting it counts something
    this vocabulary still describes. Excludes dropping the owner's rule while the report
    says the link type arrived, which would both lose a rule and contradict itself.
    """
    content = _snapshot()
    content["schema"]["definitions"][3]["payload"]["allowed_source_types"] = ["Person", "Ghost"]
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "one home each",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "p", "anchor_type_keys": ["Person"]},
                        {"name": "h", "anchor_type_keys": ["Place"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "l",
                            "source_bucket": "p",
                            "target_bucket": "h",
                            "link_type_keys": ["lives_in"],
                        }
                    ],
                },
                "counted_binding": "l",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert any(
        isinstance(each, LinkMultiplicityConstraint)
        for each in preview.candidate.active_definitions.relationship_constraints
    )
    assert not any("left out" in each for each in _findings(content, RecoveryDisposition.OMITTED))


def test_a_rule_counting_a_link_this_vocabulary_left_out_is_left_out_with_it() -> None:
    """A link type with nothing describable at an end cannot be kept, and neither can a rule
    that counts it. Excludes keeping a count over a link type that is no longer here.
    """
    content = _snapshot()
    content["schema"]["definitions"][3]["payload"]["allowed_target_types"] = ["Ghost"]
    content["graph"]["links"] = []
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "somewhere to live",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "p", "anchor_type_keys": ["Person"]},
                        {"name": "h", "anchor_type_keys": ["Place"]},
                    ],
                    "link_requirements": [
                        {
                            "name": "l",
                            "source_bucket": "p",
                            "target_bucket": "h",
                            "link_type_keys": ["lives_in"],
                        }
                    ],
                },
                "counted_binding": "l",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.active_definitions.link_types == ()
    assert all(
        isinstance(each, DirectAssociationMultiplicityConstraint)
        for each in preview.candidate.active_definitions.relationship_constraints
    )
    omitted = _findings(content, RecoveryDisposition.OMITTED)
    assert any("may join nothing this vocabulary describes" in each for each in omitted)
    assert any("counts a type this vocabulary left out" in each for each in omitted)


def test_what_v1_recorded_about_an_anchor_arrives_with_it() -> None:
    """v1's system metadata is the owner's content, not bookkeeping this may replace."""
    content = _snapshot()
    content["graph"]["anchors"][0]["system"] = {"live": True, "origin": "import", "batch": 4}

    anchor = next(each for each in _analyzed(content).candidate.graph.anchors if each.uuid == "a1")

    assert anchor.system_metadata.members["origin"] == "import"
    assert anchor.system_metadata.members["batch"] == Decimal(4)


def test_what_v1_recorded_about_a_link_arrives_with_it() -> None:
    """The same for a link: excludes beginning it from an empty record of its own."""
    content = _snapshot()
    content["graph"]["links"][0]["system"] = {"origin": "import", "batch": 4}

    link = _analyzed(content).candidate.graph.links[0]

    assert link.system_metadata.members["origin"] == "import"
    assert link.system_metadata.members["batch"] == Decimal(4)


def test_a_v1_pattern_offering_alternatives_still_matches_anywhere_in_a_value() -> None:
    """v1 searched for a match anywhere; v2 matches the whole value.

    An expression with alternatives means the whole of what the owner wrote, so it has to
    be held together before the surrounding text is allowed. Excludes an anywhere-match
    that binds only the first alternative and refuses values v1 matched.
    """
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"]["pattern"] = "cat|dog"

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    name = next(each for each in facts.property_constraints if each.property_name == "name")
    assert name.pattern is not None
    matches = compile_pattern(name.pattern.expression).matches

    assert matches("my dog Ada")
    assert matches("a cat here")
    assert not matches("a bird here")


def test_a_floor_v1_reached_only_where_a_group_formed_is_kept_when_one_always_forms() -> None:
    """Another v1 rule about the same thing may require at least one, and then the group
    always formed and the floor was in force after all. Excludes dropping a floor v2 can
    state exactly, which would accept a v1 system v1 itself refused.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["graph"]["data_objects"].append(
        {"uuid": "d2", "type": "PersonFacts", "properties": {"name": "Ada"}, "system": {}}
    )
    content["graph"]["anchor_data_index"]["a1"] = ["d1", "d2"]
    query = {
        "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
        "data_requirements": [{"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}],
    }
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at least two sets of facts, of those that have any",
            "payload": {
                "query_spec": query,
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 2,
                "maximum": 4,
            },
        },
        {
            "uuid": "c2",
            "kind": "cardinality",
            "display_name": "everyone has facts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
            },
        },
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert (rules[0].lower_bound, rules[0].upper_bound) == (2, 4)
    assert any(
        "carried across as it stands" in each
        for each in _findings(content, RecoveryDisposition.PRESERVED)
    )


def test_a_floor_over_several_anchor_types_is_kept_when_each_of_them_requires_what_it_counts() -> (
    None
):
    """A v1 rule may count one thing across several types at once. Its count reached only
    those that had any, but where each of those types requires what is counted, none could
    have none — so the floor was universal and v2 can say it exactly. Excludes dropping it
    because no single rule about the same set of types happened to state it.
    """
    content = _snapshot()
    content["schema"]["definitions"][1] = {
        "uuid": "s2",
        "kind": "anchor",
        "type_key": "Robot",
        "description": "A robot.",
        "payload": {"required_data_types": ["PersonFacts"]},
        "system": {},
    }
    content["schema"]["definitions"][3]["payload"] = {
        "allowed_source_types": ["Person"],
        "allowed_target_types": ["Robot"],
    }
    content["graph"]["anchors"][1] = {
        "uuid": "a2",
        "type": "Robot",
        "display_name": "Unit",
        "system": {},
    }
    content["graph"]["data_objects"].extend(
        {"uuid": uuid, "type": "PersonFacts", "properties": {"name": "Ada"}, "system": {}}
        for uuid in ("d2", "d3")
    )
    content["graph"]["anchor_data_index"] = {"a1": ["d1", "d2"], "a2": ["d3"]}
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at least one set of facts, whoever carries it",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person", "Robot"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 3,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    across = next(
        each
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, DirectAssociationMultiplicityConstraint)
        and set(each.anchor_type_keys) == {"Person", "Robot"}
    )
    assert (across.lower_bound, across.upper_bound) == (1, 3)
    assert not any(
        "the floor is not" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_a_link_end_naming_a_link_type_is_left_out_rather_than_carried() -> None:
    """v1 refused a link as the end of a link, so that permission was never satisfiable.

    Excludes refusing a v1 system that was valid over a permission nothing in it could
    ever have used.
    """
    content = _joined()
    content["schema"]["definitions"][5]["payload"]["allowed_target_types"] = ["Pet", "owns"]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    feeds = preview.candidate.active_definitions.link_type("feeds")
    assert feeds is not None
    assert feeds.endpoint_constraint.permitted_target_type_keys == ("Pet",)
    assert any("feeds" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_a_rule_counting_a_name_that_is_not_a_fact_type_is_left_out() -> None:
    """A v1 query could name any key anywhere, and one naming a link type as facts counted
    nothing. Excludes keeping it as a rule about facts that cannot exist.
    """
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "one lives_in each",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "lives_in"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 1,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert all(
        each.associated_data_type_keys == ("PersonFacts",)
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, DirectAssociationMultiplicityConstraint)
    )
    assert any(
        "left out with it" in each for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_kind_is_not_read_off_values_v1_would_not_have_allowed() -> None:
    """Stored values settle which of the kinds v1 allowed a property holds — not which
    kind it holds. Values of a kind v1 refused say what went wrong, not what the rule was.

    Excludes establishing a rule the owner never wrote and calling it a narrowing.
    """
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"] = {
        "required": True,
        "value_kinds": ["string", "integer"],
    }
    content["graph"]["data_objects"][0]["properties"]["name"] = ["Ada"]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "values v1 itself would not have allowed" in each.summary
        for each in preview.report.blocking_findings
    )
    assert not any(
        "narrowed to" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_a_permitted_value_v1s_own_pattern_rejected_is_not_carried_across() -> None:
    """v1 required both the list and the pattern, so such a value was one nothing could be.

    Excludes refusing a v1 system that was valid, and excludes saying its content is what
    could not be held when what could not be held is a rule that allows what it forbids.
    """
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"] = {
        "required": True,
        "value_kinds": ["string"],
        "pattern": "^(Ada|Bo)$",
        "allowed_values": ["Ada", "Bo", "Cy"],
    }

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    name = next(each for each in facts.property_constraints if each.property_name == "name")
    assert name.value_range is not None
    assert name.value_range.permitted_values == ("Ada", "Bo")
    dropped = [
        each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
        if "nothing could ever be that" in each
    ]
    assert len(dropped) == 1
    assert "'Cy'" in dropped[0]


def test_a_permitted_list_v1s_own_pattern_rejected_entirely_leaves_the_pattern() -> None:
    """When no permitted value could ever have matched, the list said nothing v1 enforced."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"] = {
        "required": True,
        "value_kinds": ["string"],
        "pattern": "^Ada$",
        "allowed_values": ["Bo", "Cy"],
    }

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    name = next(each for each in facts.property_constraints if each.property_name == "name")
    assert name.value_range is None
    assert name.pattern is not None


def _joined() -> dict[str, Any]:
    """A v1 system of owners, keepers, pets and toys, joined by links and nothing else."""
    return {
        "graph": {
            "anchors": [
                {"uuid": "o1", "type": "Owner", "display_name": "Ada", "system": {}},
                {"uuid": "k1", "type": "Keeper", "display_name": "Bo", "system": {}},
                {"uuid": "p1", "type": "Pet", "display_name": "Cat", "system": {}},
                {"uuid": "t1", "type": "Toy", "display_name": "Ball", "system": {}},
            ],
            "data_objects": [],
            "links": [
                {"uuid": "l1", "type": "owns", "source_uuid": "o1", "target_uuid": "p1"},
                {"uuid": "l2", "type": "owns", "source_uuid": "k1", "target_uuid": "p1"},
            ],
            "anchor_data_index": {},
        },
        "schema": {
            "definitions": [
                {
                    "uuid": f"s{index}",
                    "kind": "anchor",
                    "type_key": key,
                    "description": f"A {key.lower()}.",
                    "payload": {},
                    "system": {},
                }
                for index, key in enumerate(("Owner", "Keeper", "Pet", "Toy"), start=1)
            ]
            + [
                {
                    "uuid": "s5",
                    "kind": "link",
                    "type_key": "owns",
                    "description": "Someone owns something.",
                    "payload": {
                        "allowed_source_types": ["Owner", "Keeper"],
                        "allowed_target_types": ["Pet", "Toy"],
                    },
                    "system": {},
                },
                {
                    "uuid": "s6",
                    "kind": "link",
                    "type_key": "feeds",
                    "description": "Someone feeds something.",
                    "payload": {
                        "allowed_source_types": ["Owner"],
                        "allowed_target_types": ["Pet"],
                    },
                    "system": {},
                },
            ]
        },
        "constraints": {"constraints": []},
        "migration": {"migrations": []},
    }


def _link_rule(
    uuid: str,
    *,
    link_type: str = "owns",
    constrained: list[str],
    opposite: list[str],
    at_source: bool = True,
    required: bool = True,
    minimum: int,
    maximum: int | None = None,
) -> dict[str, Any]:
    """One v1 rule counting links of a type at one end of them."""
    source, target = ("c", "o") if at_source else ("o", "c")
    return {
        "uuid": uuid,
        "kind": "cardinality",
        "display_name": f"{uuid} counting {link_type}",
        "payload": {
            "query_spec": {
                "anchor_buckets": [
                    {"name": "c", "anchor_type_keys": constrained},
                    {"name": "o", "anchor_type_keys": opposite},
                ],
                "link_requirements": [
                    {
                        "name": "l",
                        "source_bucket": source,
                        "target_bucket": target,
                        "link_type_keys": [link_type],
                        "required": required,
                    }
                ],
            },
            "counted_binding": "l",
            "group_by_bindings": ["c"],
            "minimum": minimum,
            **({} if maximum is None else {"maximum": maximum}),
        },
    }


def _link_bounds(content: Mapping[str, Any], link_type: str = "owns") -> tuple[int, int | None]:
    """What the recovered vocabulary says about how many links of one type there are."""
    preview = _analyzed(content)
    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    counted = next(
        each
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint) and each.link_type_key == link_type
    )
    return counted.lower_bound, counted.upper_bound


def test_a_link_floor_is_kept_when_every_type_it_counts_for_is_required_to_have_one() -> None:
    """The link half of the same question: what makes a count reach every one of them.

    Excludes dropping a floor v1 enforced universally because no single rule said so of
    every type at once.
    """
    content = _joined()
    content["constraints"]["constraints"] = [
        _link_rule("g1", constrained=["Owner"], opposite=["Pet"], required=False, minimum=1),
        _link_rule("g2", constrained=["Keeper"], opposite=["Pet"], required=False, minimum=1),
        _link_rule("c1", constrained=["Owner", "Keeper"], opposite=["Pet"], minimum=1, maximum=2),
    ]

    across = next(
        each
        for each in _analyzed(content).candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint)
        and set(each.constrained_endpoint_type_keys) == {"Owner", "Keeper"}
    )

    assert (across.lower_bound, across.upper_bound) == (1, 2)


def test_a_link_floor_is_not_kept_when_only_some_of_what_it_counts_for_is_required() -> None:
    """A guarantee about owners says nothing about keepers. Excludes rescuing a floor from
    a rule that covers only part of what the counting rule counts for.
    """
    content = _joined()
    content["constraints"]["constraints"] = [
        _link_rule("g1", constrained=["Owner"], opposite=["Pet"], required=False, minimum=1),
        _link_rule("c1", constrained=["Owner", "Keeper"], opposite=["Pet"], minimum=1, maximum=2),
    ]

    across = next(
        each
        for each in _analyzed(content).candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint)
        and set(each.constrained_endpoint_type_keys) == {"Owner", "Keeper"}
    )

    assert (across.lower_bound, across.upper_bound) == (0, 2)


def test_a_floor_over_links_of_one_type_is_not_kept_by_a_rule_about_another_type() -> None:
    """Being fed does not make anyone owned. Excludes rescuing a floor from a rule that
    guarantees links of a different type.
    """
    content = _joined()
    content["graph"]["links"].append(
        {"uuid": "l3", "type": "feeds", "source_uuid": "o1", "target_uuid": "p1"}
    )
    content["constraints"]["constraints"] = [
        _link_rule(
            "g1",
            link_type="feeds",
            constrained=["Owner"],
            opposite=["Pet"],
            required=False,
            minimum=1,
        ),
        _link_rule("c1", constrained=["Owner"], opposite=["Pet"], minimum=1, maximum=2),
    ]

    assert _link_bounds(content) == (0, 2)


def test_a_floor_counted_at_one_end_is_not_kept_by_a_rule_about_the_other_end() -> None:
    """Every owner having a pet says nothing about every pet having an owner. Excludes
    rescuing a floor from a guarantee stated at the opposite end of the same links.
    """
    content = _joined()
    content["constraints"]["constraints"] = [
        _link_rule("g1", constrained=["Owner"], opposite=["Pet"], required=False, minimum=1),
        _link_rule(
            "c1",
            constrained=["Owner"],
            opposite=["Pet"],
            at_source=False,
            minimum=1,
            maximum=2,
        ),
    ]

    counted = [
        each
        for each in _analyzed(content).candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint) and each.constrained_end is LinkEnd.TARGET
    ]

    assert len(counted) == 1
    assert (counted[0].lower_bound, counted[0].upper_bound) == (0, 2)


def test_a_floor_over_links_to_one_thing_is_not_kept_by_a_rule_about_links_to_another() -> None:
    """Owning a toy is not owning a pet. Excludes rescuing a floor from a guarantee about
    links of the same type reaching something else.
    """
    content = _joined()
    content["constraints"]["constraints"] = [
        _link_rule("g1", constrained=["Owner"], opposite=["Toy"], required=False, minimum=1),
        _link_rule("c1", constrained=["Owner"], opposite=["Pet"], minimum=1, maximum=2),
    ]

    counted = next(
        each
        for each in _analyzed(content).candidate.active_definitions.relationship_constraints
        if isinstance(each, LinkMultiplicityConstraint)
        and set(each.opposite_endpoint_type_keys) == {"Pet"}
    )

    assert (counted.lower_bound, counted.upper_bound) == (0, 2)


def test_a_rule_that_allows_none_guarantees_nothing() -> None:
    """A rule bounded from zero permits having none, so it cannot be what makes a count
    reach everything. Excludes reading any always-reached rule as a guarantee.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["constraints"]["constraints"] = [
        {
            "uuid": "g1",
            "kind": "cardinality",
            "display_name": "at most five sets of facts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 5,
            },
        },
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at least two sets of facts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 2,
            },
        },
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert (rules[0].lower_bound, rules[0].upper_bound) == (0, 5)


def test_a_floor_over_several_anchor_types_is_not_kept_when_only_some_of_them_require_it() -> None:
    """Requiring facts of persons says nothing about robots. Excludes rescuing a floor
    from a requirement that covers only part of what the counting rule counts for.
    """
    content = _snapshot()
    content["schema"]["definitions"][1] = {
        "uuid": "s2",
        "kind": "anchor",
        "type_key": "Robot",
        "description": "A robot.",
        "payload": {"optional_data_types": ["PersonFacts"]},
        "system": {},
    }
    content["schema"]["definitions"][3]["payload"] = {
        "allowed_source_types": ["Person"],
        "allowed_target_types": ["Robot"],
    }
    content["graph"]["anchors"][1] = {
        "uuid": "a2",
        "type": "Robot",
        "display_name": "Unit",
        "system": {},
    }
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at least one set of facts, whoever carries it",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person", "Robot"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 1,
                "maximum": 3,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    across = next(
        each
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, DirectAssociationMultiplicityConstraint)
        and set(each.anchor_type_keys) == {"Person", "Robot"}
    )
    assert (across.lower_bound, across.upper_bound) == (0, 3)


def test_two_v1_rules_nothing_can_satisfy_at_once_say_so_in_the_owners_terms() -> None:
    """v1 held both rules and refused only a system that had one of these to refuse.

    v2 says one rule per thing counted, and there is no one rule that says what both said.
    Excludes inventing a range neither of them stated, and excludes a refusal that blames
    the owner's graph for a contradiction between two rules they wrote.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["graph"]["anchors"] = [content["graph"]["anchors"][1]]
    content["graph"]["data_objects"] = []
    content["graph"]["anchor_data_index"] = {}
    content["graph"]["links"] = []
    content["constraints"]["constraints"] = [
        {
            "uuid": f"c{index}",
            "kind": "cardinality",
            "display_name": name,
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": minimum,
                **({} if maximum is None else {"maximum": maximum}),
            },
        }
        for index, (name, minimum, maximum) in enumerate(
            [("at least two", 2, None), ("at most one", 0, 1)], start=1
        )
    ]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    blocking = [each.summary for each in preview.report.blocking_findings]
    assert any("cannot all be met" in each for each in blocking)
    assert not any("upper bound below its lower bound" in each for each in blocking)
    assert not any(
        "carried across as it stands" in each
        for each in _findings(content, RecoveryDisposition.PRESERVED)
    )


@pytest.mark.parametrize("section", ["schema", "constraints", "migration"])
def test_a_section_that_cannot_be_read_does_not_make_the_owners_content_wrong(
    section: str,
) -> None:
    """The reading stopped; the owner's graph did not become invalid because it did.

    Excludes a report that names one true reason and then says every anchor and object in
    a memory uses a type nothing describes, which would send the owner to repair a v1
    system whose content is fine.
    """
    content = _snapshot()
    content[section] = []

    preview = _analyzed(content)

    assert not preview.is_acceptable
    blocking = [each.summary for each in preview.report.blocking_findings]
    assert len(blocking) == 1
    assert f"the snapshot's {section} section is not an object" in blocking[0]


def test_a_count_over_a_query_that_asked_for_a_summary_is_not_newly_enforced() -> None:
    """v1 counted the rows its query returned, and a query asked for a summary returned none.

    So the rule bound nothing in v1, whatever its bounds say. Excludes enforcing it here,
    which would refuse a v1 system that was valid or hold the owner to a rule they never
    had — and excludes saying it was carried across.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {}
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "five sets of facts each",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                    "return_spec": {"aggregations": [{"name": "facts", "function": "count"}]},
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 5,
                "maximum": 9,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.active_definitions.relationship_constraints == ()
    omitted = _findings(content, RecoveryDisposition.OMITTED)
    assert any("asks its query for a summary" in each for each in omitted)
    # One rule, one reason: it is not also left out for counting what a query selected.
    assert not any("counts what a query selected" in each for each in omitted)
    assert not any(
        "five sets of facts each" in each
        for each in _findings(content, RecoveryDisposition.PRESERVED)
    )


def test_a_requirement_for_something_else_does_not_keep_a_floor_over_what_is_counted() -> None:
    """What makes a count reach everything is that everything has some of what it counts.

    Requiring a different kind of facts says nothing about that. Excludes keeping a floor
    v1 never reached, which would refuse a system v1 itself accepted.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {
        "required_data_types": ["ContactFacts"],
        "optional_data_types": ["PersonFacts"],
    }
    content["schema"]["definitions"].append(
        {
            "uuid": "s5",
            "kind": "data_object",
            "type_key": "ContactFacts",
            "description": "How to reach a person.",
            "payload": {"properties": {"address": {"required": True, "value_kinds": ["string"]}}},
            "system": {},
        }
    )
    content["graph"]["data_objects"].extend(
        [
            {
                "uuid": "d2",
                "type": "ContactFacts",
                "properties": {"address": "Home"},
                "system": {},
            },
            {"uuid": "d3", "type": "PersonFacts", "properties": {"name": "Ada"}, "system": {}},
        ]
    )
    content["graph"]["anchor_data_index"]["a1"] = ["d1", "d2", "d3"]
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at least two sets of facts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 2,
                "maximum": 3,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    counted = next(
        each
        for each in preview.candidate.active_definitions.relationship_constraints
        if isinstance(each, DirectAssociationMultiplicityConstraint)
        and each.associated_data_type_keys == ("PersonFacts",)
    )
    assert (counted.lower_bound, counted.upper_bound) == (0, 3)
    assert any(
        "the floor is not" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_a_requirement_on_a_type_left_out_is_not_reported_as_carried_across() -> None:
    """v1 can retire a data type and leave the anchors that required it saying so.

    The rule about that association goes out with the type. Excludes telling the owner it
    was carried across as a multiplicity rule in the same report that leaves it out.
    """
    content = _snapshot()
    content["schema"]["definitions"][2]["system"] = {"live": False}
    content["graph"]["data_objects"] = []
    content["graph"]["anchor_data_index"] = {}

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.active_definitions.relationship_constraints == ()
    assert not any(
        "requires PersonFacts" in each for each in _findings(content, RecoveryDisposition.PRESERVED)
    )
    assert any(
        "left out with it" in each for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_count_of_a_type_left_out_is_not_reported_as_carried_across() -> None:
    """The same for a rule the owner wrote: it is left out, so it did not arrive."""
    content = _snapshot()
    content["schema"]["definitions"][2]["system"] = {"live": False}
    content["graph"]["data_objects"] = []
    content["graph"]["anchor_data_index"] = {}
    content["schema"]["definitions"][0]["payload"] = {}
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "at most two sets of facts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 2,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.active_definitions.relationship_constraints == ()
    assert not any(
        "at most two sets of facts" in each
        for each in _findings(content, RecoveryDisposition.PRESERVED)
    )


def _two_floors(minimums: tuple[int, int], required: bool) -> dict[str, Any]:
    """A snapshot with two v1 rules counting one association, each asking for a floor."""
    content = _snapshot()
    if not required:
        content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["graph"]["data_objects"].extend(
        {"uuid": uuid, "type": "PersonFacts", "properties": {"name": "Ada"}, "system": {}}
        for uuid in ("d2", "d3")
    )
    content["graph"]["anchor_data_index"]["a1"] = ["d1", "d2", "d3"]
    content["constraints"]["constraints"] = [
        {
            "uuid": f"c{index}",
            "kind": "cardinality",
            "display_name": f"at least {minimum} sets of facts",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": minimum,
            },
        }
        for index, minimum in enumerate(minimums, start=1)
    ]
    return content


@pytest.mark.parametrize("minimums", [(3, 2), (2, 3)])
def test_two_floors_over_one_thing_ask_for_what_the_stricter_of_them_asked(
    minimums: tuple[int, int],
) -> None:
    """Both v1 rules were in force, so what they jointly required is the greater floor.

    Excludes keeping whichever arrived last, which would accept a system v1 refused and
    would depend on the order v1 happened to write its constraints in.
    """
    content = _two_floors(minimums, required=True)

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert rules[0].lower_bound == 3


def test_two_floors_v1_reached_only_where_a_group_formed_are_reported_as_v1_stated_them() -> None:
    """Neither floor can be said here, and the account of that has to name what v1 said.

    Excludes reporting the merge as though both rules had asked for none, which would tell
    an owner that nothing was lost while the stricter floor was being dropped.
    """
    content = _two_floors((3, 2), required=False)

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    rules = preview.candidate.active_definitions.relationship_constraints
    assert len(rules) == 1
    assert rules[0].lower_bound == 0
    merged = _findings(content, RecoveryDisposition.SIMPLIFIED)
    assert any("3..* and 2..*" in each for each in merged)
    assert any("at least 3 only of those that had any" in each for each in merged)


def test_a_count_whose_floor_was_not_carried_is_not_reported_as_carried_whole() -> None:
    """The report is what an owner agrees to, so it cannot say a rule arrived as it stands
    while its floor was left behind. Excludes a true finding paired with a false one.
    """
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"] = {"optional_data_types": ["PersonFacts"]}
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "two sets of facts each",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [{"name": "p", "anchor_type_keys": ["Person"]}],
                    "data_requirements": [
                        {"name": "f", "anchor_bucket": "p", "data_type_key": "PersonFacts"}
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 2,
                "maximum": 4,
            },
        }
    ]

    preserved = _findings(content, RecoveryDisposition.PRESERVED)

    assert not any("carried across as it stands" in each for each in preserved)
    assert any(
        "only of those that had any" in each
        for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


# --- What is refused ----------------------------------------------------------------


def test_a_used_type_with_no_live_definition_is_refused() -> None:
    content = _snapshot()
    content["schema"]["definitions"][1]["system"] = {"live": False}

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any("Place" in each.summary for each in preview.report.blocking_findings)


def test_a_link_whose_endpoint_is_not_live_is_refused_rather_than_repaired() -> None:
    """Excludes dropping the dangling link, which would change what the owner had."""
    content = _snapshot()
    content["graph"]["anchors"][1]["system"] = {"live": False}

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert preview.candidate.graph.links[0].target_uuid == "a2"
    assert any("a2" in each.summary for each in preview.report.blocking_findings)


def test_one_property_holding_two_kinds_is_refused() -> None:
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["either"] = {
        "required": False,
        "value_kinds": ["string", "integer"],
    }
    content["graph"]["data_objects"][0]["properties"]["either"] = "text"
    content["graph"]["data_objects"].append(
        {
            "uuid": "d2",
            "type": "PersonFacts",
            "properties": {"name": "Grace", "either": 2},
            "system": {},
        }
    )
    content["graph"]["anchors"].append(
        {"uuid": "a3", "type": "Person", "display_name": "Grace", "system": {}}
    )
    content["graph"]["anchor_data_index"]["a3"] = ["d2"]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any("one kind" in each.summary for each in preview.report.blocking_findings)


def test_two_objects_sharing_one_identity_are_refused() -> None:
    content = _snapshot()
    content["graph"]["anchors"].append(
        {"uuid": "a1", "type": "Place", "display_name": "Twice", "system": {}}
    )

    preview = _analyzed(content)
    assert not preview.is_acceptable
    assert any("a1" in each.summary for each in preview.report.blocking_findings)


def test_a_definition_this_cannot_read_is_reported_with_the_rest() -> None:
    """One unreadable rule may not hide every other reason the import cannot happen."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["odd"] = {
        "required": False,
        "value_kinds": ["date"],
    }
    content["schema"]["definitions"].append(
        {
            "uuid": "s9",
            "kind": "data_object",
            "type_key": "PersonFacts",
            "description": "Again.",
            "payload": {"properties": {}},
            "system": {},
        }
    )

    preview = _analyzed(content)

    blocking = [each.summary for each in preview.report.blocking_findings]
    assert any("unknown v1 value kind" in each for each in blocking)
    assert any("described once" in each for each in blocking)


def test_a_rule_that_does_not_say_whether_it_is_required_is_refused() -> None:
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"]["required"] = "yes"

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "whether it is required" in each.summary for each in preview.report.blocking_findings
    )


@pytest.mark.parametrize(
    "rule", [{"value_kinds": ["string"]}, {"required": "yes", "value_kinds": ["string"]}]
)
def test_a_rule_that_does_not_say_plainly_whether_it_is_required_is_refused(
    rule: dict[str, Any],
) -> None:
    """Absent and unreadable are the same here: neither is an answer to guess at."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["odd"] = rule

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "whether it is required" in each.summary for each in preview.report.blocking_findings
    )


def test_a_value_permitted_twice_is_permitted_once() -> None:
    """A list of permitted values names a set, exactly as a list of type keys does."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["mood"] = {
        "required": False,
        "value_kinds": ["string"],
        "allowed_values": ["well", "well", "tired"],
    }

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    mood = next(each for each in facts.property_constraints if each.property_name == "mood")
    assert mood.value_range is not None
    assert mood.value_range.permitted_values == ("well", "tired")


@pytest.mark.parametrize("kinds", [["integer", "number"], ["uuid", "string"]])
def test_a_rule_that_also_permitted_the_wider_kind_lost_nothing(kinds: list[str]) -> None:
    """Excludes charging an owner for a narrowing their own rule had already allowed past."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["odd"] = {
        "required": False,
        "value_kinds": kinds,
    }

    simplified = _findings(content, RecoveryDisposition.SIMPLIFIED)

    assert not any("permitted only" in each for each in simplified)


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        (
            lambda s: s["graph"]["data_objects"][0].update(properties=["not", "an", "object"]),
            "properties that are not an object",
        ),
        (
            lambda s: s["schema"]["definitions"][2]["payload"]["properties"]["name"].update(
                minimum="low", value_kinds=["number"]
            ),
            "bound that is not a number",
        ),
        (
            lambda s: s["schema"]["definitions"][2]["payload"]["properties"]["name"].update(
                allowed_values="well"
            ),
            "allowed_values that are not a list",
        ),
    ],
    ids=["properties", "a bound", "permitted values"],
)
def test_a_rule_or_record_this_cannot_read_never_establishes_less_than_it_said(
    tmp_path: Path, break_it: Any, expected: str
) -> None:
    """Excludes carrying an object or rule with content silently missing from it."""
    content = _snapshot()
    break_it(content)

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(expected in each.summary for each in preview.report.blocking_findings)
    destination = tmp_path / "v"
    assert (
        _run(["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))])[0]
        == EXIT_FAILED
    )
    assert not destination.exists()


@pytest.mark.parametrize(
    "where",
    ["a link definition's endpoints", "a count's types"],
)
def test_a_type_named_twice_names_the_same_set(where: str) -> None:
    """A list of type keys is a set; saying one twice is not a reason to refuse a system."""
    content = _snapshot()
    if where == "a link definition's endpoints":
        content["schema"]["definitions"][3]["payload"]["allowed_source_types"] = [
            "Person",
            "Person",
        ]
    else:
        content["constraints"]["constraints"] = [
            {
                "uuid": "c1",
                "kind": "cardinality",
                "display_name": "one home each",
                "description": "A person lives in one place.",
                "payload": {
                    "query_spec": {
                        "anchor_buckets": [
                            {"name": "p", "anchor_type_keys": ["Person", "Person"]},
                            {"name": "h", "anchor_type_keys": ["Place"]},
                        ],
                        "link_requirements": [
                            {
                                "name": "l",
                                "source_bucket": "p",
                                "target_bucket": "h",
                                "link_type_keys": ["lives_in"],
                            }
                        ],
                    },
                    "counted_binding": "l",
                    "group_by_bindings": ["p"],
                    "minimum": 0,
                    "maximum": 1,
                },
            }
        ]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    definitions = preview.candidate.active_definitions
    if where == "a link definition's endpoints":
        link = definitions.link_type("lives_in")
        assert link is not None
        assert link.endpoint_constraint.permitted_source_type_keys == ("Person",)
    else:
        counted = next(
            each
            for each in definitions.relationship_constraints
            if isinstance(each, LinkMultiplicityConstraint)
        )
        assert counted.constrained_endpoint_type_keys == ("Person",)


def test_a_type_key_that_is_not_text_is_refused_rather_than_skipped() -> None:
    content = _snapshot()
    content["schema"]["definitions"][3]["payload"]["allowed_source_types"] = ["Person", 7]

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any("not a type" in each.summary for each in preview.report.blocking_findings)


def test_one_type_s_values_never_decide_another_type_s_rule() -> None:
    """A rule is narrowed by the owner's data for that type, not by a name it shares."""
    content = _snapshot()
    content["schema"]["definitions"].append(
        {
            "uuid": "s9",
            "kind": "data_object",
            "type_key": "PlaceFacts",
            "description": "Facts about a place.",
            "payload": {
                "properties": {"name": {"required": False, "value_kinds": ["string", "integer"]}}
            },
            "system": {},
        }
    )
    content["schema"]["definitions"][1]["payload"] = {"optional_data_types": ["PlaceFacts"]}

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PlaceFacts")

    assert facts is not None
    assert all(each.property_name != "name" for each in facts.property_constraints)


def test_a_type_named_as_both_required_and_optional_is_permitted_once() -> None:
    content = _snapshot()
    content["schema"]["definitions"][0]["payload"]["optional_data_types"] = ["PersonFacts"]

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    assert facts.permitted_anchor_type_keys == ("Person",)


def test_a_record_that_says_nothing_about_itself_is_live(tmp_path: Path) -> None:
    """v1 wrote no metadata at all for some records; that is not a reason to leave them."""
    content = _snapshot()
    del content["graph"]["anchors"][1]["system"]
    del content["schema"]["definitions"][3]["system"]

    preview = _analyzed(content)

    assert {each.uuid for each in preview.candidate.graph.anchors} == {"a1", "a2"}
    assert preview.candidate.active_definitions.link_type("lives_in") is not None


def test_a_stored_display_name_is_never_rewritten() -> None:
    """Only an absent name is recovered; an empty one is a value, and v2 refuses it."""
    content = _snapshot()
    content["graph"]["anchors"][0]["display_name"] = ""

    preview = _analyzed(content)

    assert preview.candidate.graph.anchors[0].display_name == ""
    assert not preview.is_acceptable


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        (lambda s: s["graph"]["links"][0].pop("target_uuid"), "link l1 has no target_uuid"),
        (lambda s: s["schema"]["definitions"][3].pop("type_key"), "has no type_key"),
        (lambda s: s["schema"]["definitions"][3].update(kind="view"), "unknown kind"),
        (
            lambda s: s["schema"]["definitions"][3].update(payload=[]),
            "payload that is not an object",
        ),
        (
            lambda s: s["graph"]["anchors"][0].update(system={"live": "yes"}),
            "system.live is not a boolean",
        ),
    ],
)
def test_a_record_this_cannot_read_is_a_reason_stated_with_the_others(
    break_it: Any, expected: str
) -> None:
    """One unreadable record is a reason the import cannot happen, not the end of reading."""
    content = _snapshot()
    break_it(content)

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(expected in each.summary for each in preview.report.blocking_findings)
    # The account continues: what was understood before it is still in the report.
    assert any(
        each.disposition is RecoveryDisposition.SIMPLIFIED for each in preview.report.findings
    )


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        (
            lambda s: s["graph"]["anchor_data_index"].update(a2="d1"),
            "associations recorded for anchor a2 are not a list",
        ),
        (lambda s: s.update(graph=[]), "graph section is not an object"),
    ],
)
def test_a_section_this_cannot_read_stops_the_reading_and_says_so(
    break_it: Any, expected: str
) -> None:
    """What was understood stays in the report; what stopped it joins them."""
    content = _snapshot()
    break_it(content)

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(expected in each.summary for each in preview.report.blocking_findings)
    # And nothing claims content arrived from a snapshot that was not read through.
    assert all(
        each.disposition is not RecoveryDisposition.PRESERVED
        or "arrive exactly" not in each.summary
        for each in preview.report.findings
    )


@pytest.mark.parametrize(
    ("break_it", "expected"),
    [
        (lambda s: s["graph"]["anchors"][0].update(uuid=""), "an anchor has no uuid"),
        (lambda s: s["graph"]["anchors"].append("oops"), "an entry in anchors is not an object"),
        (lambda s: s["graph"].update(anchor_data_index="none"), "anchor_data_index is not an"),
    ],
)
def test_a_record_that_says_nothing_where_something_is_required_is_refused(
    break_it: Any, expected: str
) -> None:
    content = _snapshot()
    break_it(content)

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(expected in each.summary for each in preview.report.blocking_findings)


def test_the_first_unreadable_definition_does_not_hide_the_rest_of_the_account() -> None:
    """Excludes a reading that stops at the first thing it could not understand."""
    content = _snapshot()
    del content["schema"]["definitions"][0]["type_key"]
    content["constraints"]["constraints"] = [
        {"uuid": "c1", "kind": "query_pattern", "display_name": "a query rule", "payload": {}}
    ]

    preview = _analyzed(content)

    assert any("has no type_key" in each.summary for each in preview.report.blocking_findings)
    assert any("a query rule" in each for each in _findings(content, RecoveryDisposition.OMITTED))
    assert any(
        "PersonFacts.name" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_two_v1_kinds_that_mean_one_v2_kind_are_one_kind_here() -> None:
    """Ordinary translation, not a narrowing: v2 has one number and one text."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["age"] = {
        "required": False,
        "value_kinds": ["integer", "number"],
    }

    facts = _analyzed(content).candidate.active_definitions.associated_data_type("PersonFacts")

    assert facts is not None
    age = next(each for each in facts.property_constraints if each.property_name == "age")
    assert age.json_kind is JsonKind.NUMBER
    assert not any(
        "narrowed" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED)
    )


def test_an_empty_v1_description_is_written_over_rather_than_carried() -> None:
    content = _snapshot()
    content["schema"]["definitions"][0]["description"] = ""

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    person = preview.candidate.active_definitions.anchor_type("Person")
    assert person is not None
    assert person.description == "a Person, recovered from Vellis v1"


def test_one_fact_group_may_be_grounded_by_several_anchors() -> None:
    content = _snapshot()
    content["graph"]["anchor_data_index"]["a2"] = ["d1"]
    content["schema"]["definitions"][1]["payload"] = {"optional_data_types": ["PersonFacts"]}

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    assert preview.candidate.graph.associated_data[0].anchor_uuids == ("a1", "a2")


def test_a_count_over_more_than_the_types_it_names_is_left_out() -> None:
    content = _snapshot()
    content["constraints"]["constraints"] = [
        {
            "uuid": "c1",
            "kind": "cardinality",
            "display_name": "only residents",
            "payload": {
                "query_spec": {
                    "anchor_buckets": [
                        {"name": "p", "anchor_type_keys": ["Person"]},
                        {"name": "h", "anchor_type_keys": ["Place"]},
                    ],
                    "data_requirements": [
                        {
                            "name": "f",
                            "anchor_bucket": "p",
                            "data_type_key": "PersonFacts",
                            "required": False,
                        }
                    ],
                },
                "counted_binding": "f",
                "group_by_bindings": ["p"],
                "minimum": 0,
                "maximum": 2,
            },
        }
    ]

    preview = _analyzed(content)

    assert preview.is_acceptable
    assert all(
        each.upper_bound is None
        for each in preview.candidate.active_definitions.relationship_constraints
    )
    assert any(
        "counts what a query selected" in each
        for each in _findings(content, RecoveryDisposition.OMITTED)
    )


def test_a_rule_that_does_not_say_what_it_holds_is_refused() -> None:
    """Excludes inventing a rule out of whatever the owner's data happens to be."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["nick"] = {"required": False}
    content["graph"]["data_objects"][0]["properties"]["nick"] = "Ada"

    preview = _analyzed(content)

    assert not preview.is_acceptable
    assert any(
        "what kind of value it holds" in each.summary for each in preview.report.blocking_findings
    )


def test_a_condition_this_does_not_carry_is_named_whatever_v1_called_it() -> None:
    """The list of things v2 can say is knowable; the list of things v1 might say is not."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["name"]["unique"] = True

    assert any("unique" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_a_kind_the_rule_did_not_settle_on_is_not_reported_as_lost() -> None:
    """What a narrowing removed outright is removed, not held in some wider form."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["ref"] = {
        "required": False,
        "value_kinds": ["uuid", "number"],
    }
    content["graph"]["data_objects"][0]["properties"]["ref"] = 7

    simplified = _findings(content, RecoveryDisposition.SIMPLIFIED)

    assert not any("uuid" in each for each in simplified)
    assert any("narrowed to numberValue" in each for each in simplified)


def test_a_permitted_value_the_narrowed_kind_cannot_hold_is_dropped_and_named() -> None:
    """Excludes narrowing a rule and then refusing the import over what the narrowing left."""
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["tag"] = {
        "required": False,
        "value_kinds": ["string", "integer"],
        "allowed_values": ["auto", 0],
    }
    content["graph"]["data_objects"][0]["properties"]["tag"] = "auto"

    preview = _analyzed(content)

    assert preview.is_acceptable, [each.summary for each in preview.report.blocking_findings]
    facts = preview.candidate.active_definitions.associated_data_type("PersonFacts")
    assert facts is not None
    tag = next(each for each in facts.property_constraints if each.property_name == "tag")
    assert tag.value_range is not None
    assert tag.value_range.permitted_values == ("auto",)
    assert any("cannot hold" in each for each in _findings(content, RecoveryDisposition.SIMPLIFIED))


def test_the_report_says_exactly_what_this_import_costs() -> None:
    """Excludes a report that names a cost that is not one, or misses one that is."""
    said = [(each.disposition, each.summary) for each in _analyzed(_snapshot()).report.findings]

    assert said[0] == (
        RecoveryDisposition.PRESERVED,
        "2 anchors, 1 associated-data object, and 1 link arrive exactly as v1 stored them",
    )
    assert set(said) == {
        (
            RecoveryDisposition.PRESERVED,
            "2 anchors, 1 associated-data object, and 1 link arrive exactly as v1 stored them",
        ),
        (
            RecoveryDisposition.PRESERVED,
            "Person requires PersonFacts, carried across as a multiplicity rule on the association",
        ),
        (
            RecoveryDisposition.SIMPLIFIED,
            "the rule counting PersonFacts facts a Person carries had no readable description "
            "in v1 and is described as 'how many PersonFacts facts a Person carries, as v1 said'",
        ),
        (
            RecoveryDisposition.SIMPLIFIED,
            "PersonFacts.name had no readable description in v1 and is described as 'the name "
            "of a PersonFacts, recovered from Vellis v1'",
        ),
        (
            RecoveryDisposition.SIMPLIFIED,
            "PersonFacts.notes had no readable description in v1 and is described as 'the "
            "notes of a PersonFacts, recovered from Vellis v1'",
        ),
        (
            RecoveryDisposition.SIMPLIFIED,
            "the endpoints of lives_in had no readable description in v1 and is described as "
            "'which types a lives_in link may join, as v1 allowed'",
        ),
    }
    assert len(said) == len(set(said))


def test_a_narrowed_rule_still_says_what_the_wider_kind_lost() -> None:
    content = _snapshot()
    content["schema"]["definitions"][2]["payload"]["properties"]["age"] = {
        "required": False,
        "value_kinds": ["integer", "string"],
    }
    content["graph"]["data_objects"][0]["properties"]["age"] = 36

    simplified = _findings(content, RecoveryDisposition.SIMPLIFIED)

    assert any("whole numbers" in each for each in simplified)
    assert any("narrowed to numberValue" in each for each in simplified)


def test_a_type_nothing_can_carry_is_left_out_rather_than_refused() -> None:
    """Leaving out a definition nothing depends on costs no meaning, and is still said."""
    content = _snapshot()
    content["schema"]["definitions"].append(
        {
            "uuid": "s9",
            "kind": "data_object",
            "type_key": "Stale",
            "description": "Nothing carries these.",
            "payload": {"properties": {}},
            "system": {},
        }
    )

    preview = _analyzed(content)

    assert preview.is_acceptable
    assert preview.candidate.active_definitions.associated_data_type("Stale") is None
    assert any("Stale" in each for each in _findings(content, RecoveryDisposition.OMITTED))


def test_a_permission_to_carry_facts_no_definition_describes_is_named() -> None:
    content = _snapshot()
    content["schema"]["definitions"][1]["payload"] = {"optional_data_types": ["Notes"]}

    assert any("Notes" in each for each in _findings(content, RecoveryDisposition.OMITTED))


# --- Beginning from an accepted candidate --------------------------------------------


def test_a_confirmed_import_establishes_one_new_lineage(tmp_path: Path) -> None:
    """Revision 0, the graph unchanged, and no history claimed from the system it left."""
    content = _snapshot()
    destination = tmp_path / "v"

    code, out, err = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))]
    )

    assert code == EXIT_SUCCESS, err
    assert "starting from a Vellis v1 snapshot" in out
    system = _established(destination)
    try:
        state = system.current_state()
        assert state.revision == 0
        assert state.definition_delta is None
        assert graph_equal(state.graph, _analyzed(content).candidate.graph)
        assert definition_set_equal(
            state.active_definitions, _analyzed(content).candidate.active_definitions
        )
        assert system.store.canonical_record_count() == 1
        assert system.store.activity_record_count() == 0
        record = system.initial_record()
        assert record.provenance.source == "vellis setup: v1 recovery"
        assert "recovery from a Vellis v1 snapshot" in record.initialization_summary
        replayed = system.replay()
        assert graph_equal(replayed.graph, state.graph)
        assert definition_set_equal(replayed.active_definitions, state.active_definitions)
        assert replayed.revision == 0
        assert replayed.definition_delta is None
    finally:
        system.close()


def test_a_recovered_system_answers_for_what_was_imported(tmp_path: Path) -> None:
    """Current query is how an owner meets their memory again, so it is what must agree."""
    destination = tmp_path / "v"
    content = _snapshot()
    assert (
        _run(["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))])[0]
        == EXIT_SUCCESS
    )

    system = _established(destination)
    try:
        result = system.query_graph(
            GraphQuery(
                anchor_groups=(AnchorGroup(name="people", anchor_type="Person"),),
                return_shape=ReturnShape(
                    projections=(AnchorProjection(name="who", anchor_group="people"),)
                ),
                maximum_rows=10,
            )
        )
    finally:
        system.close()

    assert result.status is OperationStatus.ACCEPTED
    assert {binding.anchor.display_name for row in result.rows for binding in row.anchors} == {
        "Ada"
    }


def test_no_starting_vocabulary_is_overlaid_on_a_recovered_system(tmp_path: Path) -> None:
    """A v1 system arrives with its own words; the v2 starter is not added to them."""
    destination = tmp_path / "v"
    content = _snapshot()

    started = _run(["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))])
    assert started[0] == EXIT_SUCCESS

    system = _established(destination)
    try:
        active = system.current_state().active_definitions
    finally:
        system.close()
    starter = {each.type_key for each in everyday_life_starter().anchor_types}
    assert {each.type_key for each in active.anchor_types} == {"Person", "Place"}
    assert not starter & {each.type_key for each in active.anchor_types}


def test_the_owner_sees_every_finding_before_confirming(tmp_path: Path) -> None:
    """What an import costs is part of what is being agreed to."""
    content = _snapshot()
    content["migration"]["migrations"] = [
        {"migration_id": "m1", "description": "x", "status": "applied"}
    ]

    code, out, _ = _run(
        ["--data-dir", str(tmp_path / "v"), "--from-v1", str(_write(tmp_path, content))],
        answer="n\n",
    )

    assert code == EXIT_DECLINED
    for finding in _analyzed(content).report.findings:
        assert finding.summary in out


def test_declining_a_recovery_establishes_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "v"

    code, out, _ = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, _snapshot()))],
        answer="n\n",
    )

    assert code == EXIT_DECLINED
    assert "Declined" in out
    assert not destination.exists()


def test_a_snapshot_that_changed_after_the_preview_is_not_the_one_confirmed(
    tmp_path: Path,
) -> None:
    """Confirmation is of one exact candidate and report, not of an import in general."""
    destination = tmp_path / "v"
    path = _write(tmp_path, _snapshot())

    class _ChangingStream(io.StringIO):
        def readline(self, *arguments: object) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
            changed = _snapshot()
            changed["graph"]["anchors"][0]["display_name"] = "Ada Lovelace"
            path.write_text(json.dumps(changed), encoding="utf-8")
            return "y\n"

    out, err = io.StringIO(), io.StringIO()
    code = main(
        ["--data-dir", str(destination), "--from-v1", str(path)],
        stdout=out,
        stderr=err,
        stdin=_ChangingStream(),
    )

    assert code == EXIT_FAILED
    assert "changed after it was previewed" in err.getvalue()
    assert not store_path(destination.resolve()).exists()


def test_a_snapshot_that_stops_being_readable_after_the_preview_establishes_nothing(
    tmp_path: Path,
) -> None:
    """The re-read is what makes confirmation about one exact pair; it has to hold both ways."""
    destination = tmp_path / "v"
    path = _write(tmp_path, _snapshot())

    class _VanishingStream(io.StringIO):
        def readline(self, *arguments: object) -> str:  # pyright: ignore[reportIncompatibleMethodOverride]
            path.unlink()
            return "y\n"

    out, err = io.StringIO(), io.StringIO()
    code = main(
        ["--data-dir", str(destination), "--from-v1", str(path)],
        stdout=out,
        stderr=err,
        stdin=_VanishingStream(),
    )

    assert code == EXIT_FAILED
    assert "changed after it was previewed" in err.getvalue()
    assert not store_path(destination.resolve()).exists()


def test_a_recovery_into_an_established_system_is_refused(tmp_path: Path) -> None:
    """There is no merge and no replacement; an existing system is simply not a first use."""
    destination = tmp_path / "v"
    assert _run(["--data-dir", str(destination), "--vocabulary", "blank"])[0] == EXIT_SUCCESS
    before = _established(destination)
    try:
        established = before.current_state()
    finally:
        before.close()

    code, out, err = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, _snapshot()))]
    )

    assert code == EXIT_FAILED
    assert "already holds memory" in err
    assert "starting from a Vellis v1 snapshot" not in out
    system = _established(destination)
    try:
        assert graph_equal(system.current_state().graph, established.graph)
        assert system.current_state().revision == established.revision
    finally:
        system.close()


def test_a_snapshot_that_cannot_be_recovered_establishes_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "v"
    content = _snapshot()
    content["schema"]["definitions"][1]["system"] = {"live": False}

    code, out, err = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))]
    )

    assert code == EXIT_FAILED
    assert "blocking" in out
    assert "cannot be recovered as it stands" in err
    assert not destination.exists()


def test_a_dry_run_recovery_shows_the_report_and_creates_nothing(tmp_path: Path) -> None:
    destination = tmp_path / "v"

    code, out, _ = _run(
        [
            "--data-dir",
            str(destination),
            "--from-v1",
            str(_write(tmp_path, _snapshot())),
            "--dry-run",
        ]
    )

    assert code == EXIT_SUCCESS
    assert "starting from a Vellis v1 snapshot" in out
    assert "Dry run: nothing was created." in out
    assert not destination.exists()


def test_the_report_is_shown_before_the_noninteractive_path_establishes(tmp_path: Path) -> None:
    """--yes is the agent path; an owner who sees nothing has confirmed nothing."""
    destination = tmp_path / "v"

    code, out, err = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, _snapshot())), "--yes"]
    )

    assert code == EXIT_SUCCESS, err
    assert out.index("starting from a Vellis v1 snapshot") < out.index("established revision 0")


def test_a_snapshot_that_cannot_be_recovered_is_not_previewed_as_a_system(
    tmp_path: Path,
) -> None:
    """Excludes promising a system on the line above the reasons there will not be one."""
    content = _snapshot()
    content["schema"]["definitions"][1]["system"] = {"live": False}

    _, out, _ = _run(
        ["--data-dir", str(tmp_path / "v"), "--from-v1", str(_write(tmp_path, content))]
    )

    assert out.splitlines()[0] == "Vellis setup cannot prepare a system here."


def test_the_permanent_record_says_what_was_recovered_and_from_where(tmp_path: Path) -> None:
    """The report is transient; this sentence is what the system says about itself later."""
    destination = tmp_path / "v"
    content = _snapshot()
    assert (
        _run(["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content))])[0]
        == EXIT_SUCCESS
    )

    system = _established(destination)
    try:
        summary = system.initial_record().initialization_summary
    finally:
        system.close()

    assert snapshot_identity(content)[:12] in summary
    assert "2 anchors" in summary
    assert "1 associated-data object," in summary
    assert "1 link," in summary


@pytest.mark.parametrize(
    ("content", "expected"),
    [("not json at all", "does not hold JSON"), ("[]", "not a Vellis v1 system snapshot")],
)
def test_a_file_that_is_not_a_snapshot_says_which_way_it_is_not(
    tmp_path: Path, content: str, expected: str
) -> None:
    path = tmp_path / "other.json"
    path.write_text(content, encoding="utf-8")

    code, out, err = _run(["--data-dir", str(tmp_path / "v"), "--from-v1", str(path)])

    assert code == EXIT_FAILED
    assert expected in out
    assert "complete Vellis v1 system snapshot" in err


def test_a_file_this_cannot_decode_is_an_actionable_failure(tmp_path: Path) -> None:
    """A v1 system written in another encoding is a file, not a traceback."""
    path = tmp_path / "latin.json"
    path.write_bytes(json.dumps(_snapshot()).encode("utf-8").replace(b"Ada", b"Ad\xeb"))

    code, out, err = _run(["--data-dir", str(tmp_path / "v"), "--from-v1", str(path)])

    assert code == EXIT_FAILED
    assert out.splitlines()[0] == "Vellis setup cannot prepare a system here."
    assert "this snapshot cannot be read" in out
    assert str(path) in out
    assert "complete Vellis v1 system snapshot" in err


@pytest.mark.parametrize("mode", ["--dry-run", "--yes"])
def test_a_snapshot_that_cannot_be_recovered_is_refused_whichever_way_it_is_run(
    tmp_path: Path, mode: str
) -> None:
    """Neither flag is a way past a report that says the import cannot happen."""
    destination = tmp_path / "v"
    content = _snapshot()
    content["schema"]["definitions"][1]["system"] = {"live": False}

    code, out, err = _run(
        ["--data-dir", str(destination), "--from-v1", str(_write(tmp_path, content)), mode]
    )

    assert code == EXIT_FAILED
    assert "Dry run" not in out
    assert "cannot be recovered as it stands" in err
    assert not destination.exists()


def test_every_finding_is_shown_under_the_disposition_it_carries(tmp_path: Path) -> None:
    """The label is the first thing an owner reads about a finding, so it has to be right."""
    content = _snapshot()
    content["graph"]["anchors"].append(
        {"uuid": "a9", "type": "Place", "display_name": "Draft", "system": {"live": False}}
    )

    _, out, _ = _run(
        ["--data-dir", str(tmp_path / "v"), "--from-v1", str(_write(tmp_path, content))],
        answer="n\n",
    )

    assert "    preserved: 2 anchors, 1 associated-data object, and 1 link arrive" in out
    assert "    omitted: the non-live anchor a9 is not imported" in out
    assert "    simplified: the endpoints of lives_in had no readable description in v1" in out


def test_a_recovery_is_never_offered_a_starting_vocabulary(tmp_path: Path) -> None:
    """The snapshot brought its own words; there is no second question to ask."""
    code, out, _ = _run(
        ["--data-dir", str(tmp_path / "v"), "--from-v1", str(_write(tmp_path, _snapshot()))]
    )

    assert code == EXIT_SUCCESS
    assert "  starting vocabulary:" not in out


def test_an_established_system_is_refused_before_the_snapshot_is_even_read(
    tmp_path: Path,
) -> None:
    """Excludes an unreadable snapshot replacing the real reason setup cannot proceed."""
    destination = tmp_path / "v"
    assert _run(["--data-dir", str(destination), "--vocabulary", "blank"])[0] == EXIT_SUCCESS
    missing = tmp_path / "absent.json"

    code, _, err = _run(["--data-dir", str(destination), "--from-v1", str(missing)])

    assert code == EXIT_FAILED
    assert "already holds memory" in err
    assert "snapshot" not in err


def test_a_snapshot_that_is_not_there_is_an_actionable_failure(tmp_path: Path) -> None:
    code, out, err = _run(
        ["--data-dir", str(tmp_path / "v"), "--from-v1", str(tmp_path / "no.json")]
    )

    assert code == EXIT_FAILED
    assert "this snapshot cannot be read" in out
    assert "complete Vellis v1 system snapshot" in err


def test_a_snapshot_and_a_starting_vocabulary_are_not_both_a_start(tmp_path: Path) -> None:
    """A recovered system already has its words; asking for others says nothing."""
    with pytest.raises(SystemExit) as refusal:
        _run(
            [
                "--data-dir",
                str(tmp_path / "v"),
                "--from-v1",
                str(_write(tmp_path, _snapshot())),
                "--vocabulary",
                "blank",
            ]
        )
    assert refusal.value.code == 2
