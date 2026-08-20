"""The ordinary, owner-editable Everyday Life starter definition set."""

from __future__ import annotations

from vellis.domain import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    Cardinality,
    LinkTypeDefinition,
    PropertyDefinition,
    TypeDefinition,
    ValueKind,
)

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

_ANCHORS = (
    (PERSON, "A person known to the owner. Use the anchor display name for the person's name."),
    (
        GROUP,
        "A household, family, team, organization, or community. Use the anchor display name "
        "for its name.",
    ),
    (
        AREA,
        "An ongoing sphere of responsibility such as health, home, family, finances, or "
        "work. Use the anchor display name for its title.",
    ),
    (GOAL, "An outcome the owner wants to achieve. Use the anchor display name for its title."),
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
    (ROUTINE, "A recurring responsibility or practice. Use the anchor display name for its title."),
    (
        DECISION,
        "A decision whose outcome or reasoning matters later. Use the anchor display name "
        "for its title.",
    ),
    (
        NOTE,
        "A captured piece of knowledge or observation. Use the anchor display name for its title.",
    ),
    (RESOURCE, "A useful source, object, or reference. Use the anchor display name for its title."),
    (PLACE, "A place relevant to the owner's life. Use the anchor display name for its name."),
)

_DETAILS = (
    (
        PERSON,
        "Optional current everyday details about one Person; other independently typed data "
        "may also describe that Person.",
        (
            (
                "relationship",
                ValueKind.TEXT,
                "The person's relationship to the owner or household.",
            ),
            (
                "preferredContact",
                ValueKind.TEXT,
                "The person's preferred contact method when known.",
            ),
            ("notes", ValueKind.TEXT, "Additional owner-provided notes about the person."),
        ),
    ),
    (
        GROUP,
        "Optional current everyday details about one Group.",
        (
            ("kind", ValueKind.TEXT, "The owner-written kind of group."),
            ("description", ValueKind.TEXT, "A description of the group."),
        ),
    ),
    (
        AREA,
        "Optional current everyday details about one Area.",
        (
            ("domain", ValueKind.TEXT, "The owner-written domain of responsibility."),
            ("focus", ValueKind.TEXT, "The Area's current focus when known."),
            ("active", ValueKind.BOOLEAN, "Whether the Area is currently active when known."),
        ),
    ),
    (
        GOAL,
        "Optional current everyday details about one Goal.",
        (
            ("status", ValueKind.TEXT, "The Goal status exactly as the owner expresses it."),
            ("priority", ValueKind.TEXT, "The Goal priority exactly as the owner expresses it."),
            ("targetDate", ValueKind.DATE, "The Goal target date."),
            ("desiredOutcome", ValueKind.TEXT, "The desired outcome of the Goal."),
        ),
    ),
    (
        PROJECT,
        "Optional current everyday details about one Project.",
        (
            ("status", ValueKind.TEXT, "The Project status exactly as the owner expresses it."),
            ("priority", ValueKind.TEXT, "The Project priority exactly as the owner expresses it."),
            ("desiredOutcome", ValueKind.TEXT, "The desired outcome of the Project."),
            ("nextReviewDate", ValueKind.DATE, "The next Project review date."),
        ),
    ),
    (
        TASK,
        "Optional current everyday details about one Task.",
        (
            ("status", ValueKind.TEXT, "The Task status exactly as the owner expresses it."),
            ("priority", ValueKind.TEXT, "The Task priority exactly as the owner expresses it."),
            ("dueDate", ValueKind.DATE, "The Task due date."),
            ("context", ValueKind.TEXT, "Owner-provided context for completing the Task."),
        ),
    ),
    (
        EVENT,
        "Optional current everyday details about one Event.",
        (
            ("status", ValueKind.TEXT, "The Event status exactly as the owner expresses it."),
            ("start", ValueKind.DATE, "The Event start date."),
            ("end", ValueKind.DATE, "The Event end date."),
            ("summary", ValueKind.TEXT, "A concise summary of the Event."),
        ),
    ),
    (
        ROUTINE,
        "Optional current everyday details about one Routine.",
        (
            ("cadence", ValueKind.TEXT, "The owner-written recurrence cadence."),
            ("active", ValueKind.BOOLEAN, "Whether the Routine is currently active when known."),
            ("nextDueDate", ValueKind.DATE, "The Routine's next due date."),
            ("context", ValueKind.TEXT, "Owner-provided context for carrying out the Routine."),
        ),
    ),
    (
        DECISION,
        "Optional current everyday details about one Decision.",
        (
            ("status", ValueKind.TEXT, "The Decision status exactly as the owner expresses it."),
            ("decisionDate", ValueKind.DATE, "The Decision date."),
            ("rationale", ValueKind.TEXT, "The recorded rationale for the Decision."),
        ),
    ),
    (
        NOTE,
        "Optional current everyday details about one Note.",
        (
            ("topic", ValueKind.TEXT, "The Note's topic."),
            ("summary", ValueKind.TEXT, "A concise summary of the Note."),
            ("captureDate", ValueKind.DATE, "The Note capture date."),
        ),
    ),
    (
        RESOURCE,
        "Optional current everyday details about one Resource.",
        (
            ("kind", ValueKind.TEXT, "The owner-written kind of Resource."),
            (
                "locationOrWebAddress",
                ValueKind.TEXT,
                "A physical location or web address for the Resource.",
            ),
            ("summary", ValueKind.TEXT, "A concise summary of the Resource."),
        ),
    ),
    (
        PLACE,
        "Optional current everyday details about one Place.",
        (
            ("kind", ValueKind.TEXT, "The owner-written kind of Place."),
            ("address", ValueKind.TEXT, "The Place address when known."),
            ("notes", ValueKind.TEXT, "Additional owner-provided notes about the Place."),
        ),
    ),
)

_ALL_ANCHORS = tuple(key for key, _ in _ANCHORS)
_LINKS = (
    (
        "life.belongs_to",
        "Connects work or knowledge to the Area it belongs to.",
        (GOAL, PROJECT, TASK, EVENT, ROUTINE, DECISION, NOTE, RESOURCE),
        (AREA,),
    ),
    (
        "life.supports",
        "Connects work or knowledge to a Goal or Project it supports.",
        (PROJECT, TASK, EVENT, ROUTINE, DECISION, NOTE, RESOURCE),
        (GOAL, PROJECT),
    ),
    (
        "life.responsible_for",
        "Connects a Person or Group to an Area or work item for which it is responsible.",
        (PERSON, GROUP),
        (AREA, GOAL, PROJECT, TASK, EVENT, ROUTINE),
    ),
    (
        "life.member_of",
        "Connects a Person to a Group of which the Person is a member.",
        (PERSON,),
        (GROUP,),
    ),
    (
        "life.involves",
        "Connects a Goal, Project, Task, Event, Routine, or Decision to a participating "
        "Person or Group.",
        (GOAL, PROJECT, TASK, EVENT, ROUTINE, DECISION),
        (PERSON, GROUP),
    ),
    (
        "life.located_at",
        "Connects a Task, Event, Routine, or Group to a Place where it occurs or is located.",
        (TASK, EVENT, ROUTINE, GROUP),
        (PLACE,),
    ),
    (
        "life.documents",
        "Connects a Note or Resource to an everyday item it documents.",
        (NOTE, RESOURCE),
        _ALL_ANCHORS,
    ),
    (
        "life.mentions",
        "Connects a Note to an everyday item it mentions.",
        (NOTE,),
        _ALL_ANCHORS,
    ),
    (
        "life.depends_on",
        "Connects a Goal, Project, or Task to another Goal, Project, or Task on which it depends.",
        (GOAL, PROJECT, TASK),
        (GOAL, PROJECT, TASK),
    ),
)


def everyday_life_starter() -> tuple[TypeDefinition, ...]:
    anchors = tuple(AnchorTypeDefinition(key, description) for key, description in _ANCHORS)
    details = tuple(
        AssociatedDataTypeDefinition(
            f"{anchor_key}.details",
            description,
            (anchor_key,),
            tuple(PropertyDefinition(name, text, kind) for name, kind, text in properties),
            Cardinality(1, 1),
            Cardinality(0, 1),
        )
        for anchor_key, description, properties in _DETAILS
    )
    links = tuple(
        LinkTypeDefinition(
            key,
            description,
            sources,
            targets,
            Cardinality(0),
            Cardinality(0),
        )
        for key, description, sources, targets in _LINKS
    )
    return (*anchors, *details, *links)
