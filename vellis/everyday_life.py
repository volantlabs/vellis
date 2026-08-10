"""The optional Everyday Life starter vocabulary.

Realizes ``EverydayLifeStarter::'Everyday Life Starter Definition Set'`` and
``EverydayLifeStarter::everydayLifeStarter``.

This is one ordinary graph definition set. It is not a registry, a protected platform
ontology, or a second canonical authority: once an owner starts with it, it is theirs to
change through the same definition governance as any other vocabulary, and nothing here
treats its type keys as special. It contains no graph data.

The date properties constrain lexical shape only. ``2023-02-31`` matches, because the
pattern says what a date looks like, not which dates exist.
"""

from __future__ import annotations

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    DirectAssociationEnd,
    DirectAssociationMultiplicityConstraint,
    EndpointConstraint,
    GraphDefinitionSet,
    LinkTypeDefinition,
    PropertyConstraint,
    RelationshipConstraint,
    StringPattern,
)
from vellis.json_value import JsonKind

__all__ = ["DATE_PATTERN", "everyday_life_starter"]

DATE_PATTERN = "[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])"

_DATE_SHAPE = "in the starter's lexical YYYY-MM-DD shape"

PERSON = "life.person"
GROUP = "life.group"
AREA = "life.area"
GOAL = "life.goal"
PROJECT = "life.project"
TASK = "life.task"
EVENT = "life.event"
ROUTINE = "life.routine"
DECISION = "life.decision"
NOTE = "life.note"
RESOURCE = "life.resource"
PLACE = "life.place"

_ANCHOR_TYPES: tuple[tuple[str, str], ...] = (
    (
        PERSON,
        "A person known to the owner. Use the anchor display name for the person's name.",
    ),
    (
        GROUP,
        "A household, family, team, organization, or community. Use the anchor display "
        "name for its name.",
    ),
    (
        AREA,
        "An ongoing sphere of responsibility such as health, home, family, finances, or "
        "work. Use the anchor display name for its title.",
    ),
    (
        GOAL,
        "An outcome the owner wants to achieve. Use the anchor display name for its title.",
    ),
    (
        PROJECT,
        "A coordinated body of work with a desired outcome. Use the anchor display name "
        "for its title.",
    ),
    (TASK, "A discrete piece of work. Use the anchor display name for its title."),
    (
        EVENT,
        "An occurrence the owner wants to remember. Use the anchor display name for its title.",
    ),
    (
        ROUTINE,
        "A recurring responsibility or practice. Use the anchor display name for its title.",
    ),
    (
        DECISION,
        "A decision whose outcome or reasoning matters later. Use the anchor display name "
        "for its title.",
    ),
    (
        NOTE,
        "A captured piece of knowledge or observation. Use the anchor display name for its title.",
    ),
    (
        RESOURCE,
        "A useful source, object, or reference. Use the anchor display name for its title.",
    ),
    (
        PLACE,
        "A place relevant to the owner's life. Use the anchor display name for its name.",
    ),
)

# (anchor key, label, details description, ((property, kind, description), ...))
_STRING = "string"
_BOOLEAN = "boolean"
_DATE = "date"

_DETAILS: tuple[tuple[str, str, str, tuple[tuple[str, str, str], ...]], ...] = (
    (
        PERSON,
        "Person",
        "Optional current everyday details about one Person; other independently typed "
        "data may also describe that Person.",
        (
            ("relationship", _STRING, "The person's relationship to the owner or household."),
            ("preferredContact", _STRING, "The person's preferred contact method when known."),
            ("notes", _STRING, "Additional owner-provided notes about the person."),
        ),
    ),
    (
        GROUP,
        "Group",
        "Optional current everyday details about one Group.",
        (
            ("kind", _STRING, "The owner-written kind of group."),
            ("description", _STRING, "A description of the group."),
        ),
    ),
    (
        AREA,
        "Area",
        "Optional current everyday details about one Area.",
        (
            ("domain", _STRING, "The owner-written domain of responsibility."),
            ("focus", _STRING, "The Area's current focus when known."),
            ("active", _BOOLEAN, "Whether the Area is currently active when known."),
        ),
    ),
    (
        GOAL,
        "Goal",
        "Optional current everyday details about one Goal.",
        (
            ("status", _STRING, "The Goal status exactly as the owner expresses it."),
            ("priority", _STRING, "The Goal priority exactly as the owner expresses it."),
            ("targetDate", _DATE, f"The Goal target date {_DATE_SHAPE}."),
            ("desiredOutcome", _STRING, "The desired outcome of the Goal."),
        ),
    ),
    (
        PROJECT,
        "Project",
        "Optional current everyday details about one Project.",
        (
            ("status", _STRING, "The Project status exactly as the owner expresses it."),
            ("priority", _STRING, "The Project priority exactly as the owner expresses it."),
            ("desiredOutcome", _STRING, "The desired outcome of the Project."),
            ("nextReviewDate", _DATE, f"The next Project review date {_DATE_SHAPE}."),
        ),
    ),
    (
        TASK,
        "Task",
        "Optional current everyday details about one Task.",
        (
            ("status", _STRING, "The Task status exactly as the owner expresses it."),
            ("priority", _STRING, "The Task priority exactly as the owner expresses it."),
            ("dueDate", _DATE, f"The Task due date {_DATE_SHAPE}."),
            ("context", _STRING, "Owner-provided context for completing the Task."),
        ),
    ),
    (
        EVENT,
        "Event",
        "Optional current everyday details about one Event.",
        (
            ("status", _STRING, "The Event status exactly as the owner expresses it."),
            ("start", _DATE, f"The Event start date {_DATE_SHAPE}."),
            ("end", _DATE, f"The Event end date {_DATE_SHAPE}."),
            ("summary", _STRING, "A concise summary of the Event."),
        ),
    ),
    (
        ROUTINE,
        "Routine",
        "Optional current everyday details about one Routine.",
        (
            ("cadence", _STRING, "The owner-written recurrence cadence."),
            ("active", _BOOLEAN, "Whether the Routine is currently active when known."),
            ("nextDueDate", _DATE, f"The Routine's next due date {_DATE_SHAPE}."),
            ("context", _STRING, "Owner-provided context for carrying out the Routine."),
        ),
    ),
    (
        DECISION,
        "Decision",
        "Optional current everyday details about one Decision.",
        (
            ("status", _STRING, "The Decision status exactly as the owner expresses it."),
            ("decisionDate", _DATE, f"The Decision date {_DATE_SHAPE}."),
            ("rationale", _STRING, "The recorded rationale for the Decision."),
        ),
    ),
    (
        NOTE,
        "Note",
        "Optional current everyday details about one Note.",
        (
            ("topic", _STRING, "The Note's topic."),
            ("summary", _STRING, "A concise summary of the Note."),
            ("captureDate", _DATE, f"The Note capture date {_DATE_SHAPE}."),
        ),
    ),
    (
        RESOURCE,
        "Resource",
        "Optional current everyday details about one Resource.",
        (
            ("kind", _STRING, "The owner-written kind of Resource."),
            (
                "locationOrWebAddress",
                _STRING,
                "A physical location or web address for the Resource.",
            ),
            ("summary", _STRING, "A concise summary of the Resource."),
        ),
    ),
    (
        PLACE,
        "Place",
        "Optional current everyday details about one Place.",
        (
            ("kind", _STRING, "The owner-written kind of Place."),
            ("address", _STRING, "The Place address when known."),
            ("notes", _STRING, "Additional owner-provided notes about the Place."),
        ),
    ),
)

_ALL_ANCHORS: tuple[str, ...] = tuple(key for key, _ in _ANCHOR_TYPES)

# (type key, description, endpoint description, sources, targets)
_LINK_TYPES: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "life.belongs_to",
        "Connects work or knowledge to the Area it belongs to.",
        "Sources are Goals, Projects, Tasks, Events, Routines, Decisions, Notes, or "
        "Resources; target is an Area.",
        (GOAL, PROJECT, TASK, EVENT, ROUTINE, DECISION, NOTE, RESOURCE),
        (AREA,),
    ),
    (
        "life.supports",
        "Connects work or knowledge to a Goal or Project it supports. Future agents should "
        "avoid self-links and circular support chains; those judgments are advisory.",
        "Sources are Projects, Tasks, Events, Routines, Decisions, Notes, or Resources; "
        "targets are Goals or Projects.",
        (PROJECT, TASK, EVENT, ROUTINE, DECISION, NOTE, RESOURCE),
        (GOAL, PROJECT),
    ),
    (
        "life.responsible_for",
        "Connects a Person or Group to an Area or work item for which it is responsible.",
        "Sources are Persons or Groups; targets are Areas, Goals, Projects, Tasks, Events, "
        "or Routines.",
        (PERSON, GROUP),
        (AREA, GOAL, PROJECT, TASK, EVENT, ROUTINE),
    ),
    (
        "life.member_of",
        "Connects a Person to a Group of which the Person is a member.",
        "Source is a Person; target is a Group.",
        (PERSON,),
        (GROUP,),
    ),
    (
        "life.involves",
        "Connects a Goal, Project, Task, Event, Routine, or Decision to a participating "
        "Person or Group.",
        "Sources are Goals, Projects, Tasks, Events, Routines, or Decisions; targets are "
        "Persons or Groups.",
        (GOAL, PROJECT, TASK, EVENT, ROUTINE, DECISION),
        (PERSON, GROUP),
    ),
    (
        "life.located_at",
        "Connects a Task, Event, Routine, or Group to a Place where it occurs or is located.",
        "Sources are Tasks, Events, Routines, or Groups; target is a Place.",
        (TASK, EVENT, ROUTINE, GROUP),
        (PLACE,),
    ),
    (
        "life.documents",
        "Connects a Note or Resource to an everyday item it documents. Future agents should "
        "avoid linking an object to itself; that judgment is advisory.",
        "Sources are Notes or Resources; targets are any Everyday Life starter anchor type.",
        (NOTE, RESOURCE),
        _ALL_ANCHORS,
    ),
    (
        "life.mentions",
        "Connects a Note to an everyday item it mentions. Future agents should avoid linking "
        "a Note to itself; that judgment is advisory.",
        "Source is a Note; targets are any Everyday Life starter anchor type.",
        (NOTE,),
        _ALL_ANCHORS,
    ),
    (
        "life.depends_on",
        "Connects a Goal, Project, or Task to another Goal, Project, or Task on which it "
        "depends. Future agents should avoid self-links and circular dependency chains; "
        "those judgments are advisory.",
        "Sources and targets are Goals, Projects, or Tasks.",
        (GOAL, PROJECT, TASK),
        (GOAL, PROJECT, TASK),
    ),
)


def _property(name: str, kind: str, description: str) -> PropertyConstraint:
    return PropertyConstraint(
        property_name=name,
        required=False,
        json_kind=JsonKind.BOOLEAN if kind is _BOOLEAN else JsonKind.STRING,
        description=description,
        pattern=StringPattern(expression=DATE_PATTERN) if kind is _DATE else None,
    )


def _details_key(anchor_key: str) -> str:
    return f"{anchor_key}.details"


def _build() -> GraphDefinitionSet:
    anchor_types = tuple(
        AnchorTypeDefinition(type_key=key, description=description)
        for key, description in _ANCHOR_TYPES
    )
    data_types = tuple(
        AssociatedDataTypeDefinition(
            type_key=_details_key(anchor_key),
            permitted_anchor_type_keys=(anchor_key,),
            property_constraints=tuple(_property(*each) for each in properties),
            description=description,
        )
        for anchor_key, _, description, properties in _DETAILS
    )
    link_types = tuple(
        LinkTypeDefinition(
            type_key=key,
            endpoint_constraint=EndpointConstraint(
                permitted_source_type_keys=sources,
                permitted_target_type_keys=targets,
                description=endpoint_description,
            ),
            description=description,
        )
        for key, description, endpoint_description, sources, targets in _LINK_TYPES
    )

    constraints: list[RelationshipConstraint] = []
    for anchor_key, label, _, _ in _DETAILS:
        details_key = _details_key(anchor_key)
        constraints.append(
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ASSOCIATED_DATA,
                anchor_type_keys=(anchor_key,),
                associated_data_type_keys=(details_key,),
                lower_bound=1,
                upper_bound=1,
                description=f"Each {label} details object describes exactly one {label}.",
            )
        )
        constraints.append(
            DirectAssociationMultiplicityConstraint(
                constrained_end=DirectAssociationEnd.ANCHOR,
                anchor_type_keys=(anchor_key,),
                associated_data_type_keys=(details_key,),
                lower_bound=0,
                upper_bound=1,
                description=f"Each {label} has at most one {label} details object.",
            )
        )

    return GraphDefinitionSet(
        anchor_types=anchor_types,
        associated_data_types=data_types,
        link_types=link_types,
        relationship_constraints=tuple(constraints),
    )


def everyday_life_starter() -> GraphDefinitionSet:
    """Return the complete Everyday Life starter definition set."""
    return _build()
