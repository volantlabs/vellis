package EverydayLifeStarter {
    private import RTG::*;

    item def 'Optional String Property' :> 'Property Constraint' {
        attribute :>> required = false;
        attribute :>> jsonKind = 'JSON Kind'::stringValue;
    }

    item def 'Optional Boolean Property' :> 'Property Constraint' {
        attribute :>> required = false;
        attribute :>> jsonKind = 'JSON Kind'::booleanValue;
    }

    item def 'Optional Date String Property' :> 'Optional String Property' {
        attribute datePattern [1] redefines pattern {
            attribute :>> expression =
                "[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])";
        }
        doc /*
         * A lexical YYYY-MM-DD shape with month 01 through 12 and day 01
         * through 31. It does not establish Gregorian calendar validity or
         * chronological ordering; for example, 2023-02-31 matches.
         */
    }

    item def 'Profile Has Exactly One Matching Anchor'
        :> 'Direct Association Multiplicity Constraint' {
        attribute :>> constrainedEnd = 'Direct Association End'::associatedData;
        attribute :>> lowerBound = 1;
        attribute :>> upperBound = 1;
    }

    item def 'Anchor Has At Most One Matching Profile'
        :> 'Direct Association Multiplicity Constraint' {
        attribute :>> constrainedEnd = 'Direct Association End'::anchor;
        attribute :>> lowerBound = 0;
        attribute :>> upperBound = 1;
    }

    item def 'Everyday Life Starter Definition Set' :> 'Graph Definition Set' {
        doc /*
         * The complete optional Everyday Life starter vocabulary. It is one
         * ordinary graph definition set, not a registry, protected platform
         * ontology, or second canonical authority. It contains no graph data.
         */

        item starterAnchorTypes [12] redefines anchorTypes;
        item starterAssociatedDataTypes [12] redefines associatedDataTypes;
        item starterLinkTypes [9] redefines linkTypes;
        item starterRelationshipConstraints [24] redefines relationshipConstraints;

        /* Stable, independently identifiable everyday concepts. */

        item personType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.person";
            attribute :>> description =
                "A person known to the owner. Use the anchor display name for the person's name.";
        }
        item groupType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.group";
            attribute :>> description =
                "A household, family, team, organization, or community. Use the anchor display name for its name.";
        }
        item areaType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.area";
            attribute :>> description =
                "An ongoing sphere of responsibility such as health, home, family, finances, or work. Use the anchor display name for its title.";
        }
        item goalType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.goal";
            attribute :>> description =
                "An outcome the owner wants to achieve. Use the anchor display name for its title.";
        }
        item projectType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.project";
            attribute :>> description =
                "A coordinated body of work with a desired outcome. Use the anchor display name for its title.";
        }
        item taskType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.task";
            attribute :>> description =
                "A discrete piece of work. Use the anchor display name for its title.";
        }
        item eventType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.event";
            attribute :>> description =
                "An occurrence the owner wants to remember. Use the anchor display name for its title.";
        }
        item routineType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.routine";
            attribute :>> description =
                "A recurring responsibility or practice. Use the anchor display name for its title.";
        }
        item decisionType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.decision";
            attribute :>> description =
                "A decision whose outcome or reasoning matters later. Use the anchor display name for its title.";
        }
        item noteType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.note";
            attribute :>> description =
                "A captured piece of knowledge or observation. Use the anchor display name for its title.";
        }
        item resourceType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.resource";
            attribute :>> description =
                "A useful source, object, or reference. Use the anchor display name for its title.";
        }
        item placeType [1] : 'Anchor Type Definition' subsets starterAnchorTypes {
            attribute :>> typeKey = "life.place";
            attribute :>> description =
                "A place relevant to the owner's life. Use the anchor display name for its name.";
        }

        /* Optional current convenience profiles. */

        item personDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.person.details";
            attribute :>> description =
                "Optional current everyday details about one Person; other independently typed data may also describe that Person.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = personType;
            item profileProperties [3] redefines propertyConstraints;
            item relationship [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "relationship";
                attribute :>> description = "The person's relationship to the owner or household.";
            }
            item preferredContact [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "preferredContact";
                attribute :>> description = "The person's preferred contact method when known.";
            }
            item notes [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "notes";
                attribute :>> description = "Additional owner-provided notes about the person.";
            }
        }

        item groupDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.group.details";
            attribute :>> description = "Optional current everyday details about one Group.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = groupType;
            item profileProperties [2] redefines propertyConstraints;
            item kind [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "kind";
                attribute :>> description = "The owner-written kind of group.";
            }
            item descriptionProperty [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "description";
                attribute :>> description = "A description of the group.";
            }
        }

        item areaDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.area.details";
            attribute :>> description = "Optional current everyday details about one Area.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = areaType;
            item profileProperties [3] redefines propertyConstraints;
            item domain [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "domain";
                attribute :>> description = "The owner-written domain of responsibility.";
            }
            item focus [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "focus";
                attribute :>> description = "The Area's current focus when known.";
            }
            item active [1] : 'Optional Boolean Property' subsets profileProperties {
                attribute :>> propertyName = "active";
                attribute :>> description = "Whether the Area is currently active when known.";
            }
        }

        item goalDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.goal.details";
            attribute :>> description = "Optional current everyday details about one Goal.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = goalType;
            item profileProperties [4] redefines propertyConstraints;
            item status [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "status";
                attribute :>> description = "The Goal status exactly as the owner expresses it.";
            }
            item priority [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "priority";
                attribute :>> description = "The Goal priority exactly as the owner expresses it.";
            }
            item targetDate [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "targetDate";
                attribute :>> description = "The Goal target date in the starter's lexical YYYY-MM-DD shape.";
            }
            item desiredOutcome [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "desiredOutcome";
                attribute :>> description = "The desired outcome of the Goal.";
            }
        }

        item projectDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.project.details";
            attribute :>> description = "Optional current everyday details about one Project.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = projectType;
            item profileProperties [4] redefines propertyConstraints;
            item status [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "status";
                attribute :>> description = "The Project status exactly as the owner expresses it.";
            }
            item priority [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "priority";
                attribute :>> description = "The Project priority exactly as the owner expresses it.";
            }
            item desiredOutcome [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "desiredOutcome";
                attribute :>> description = "The desired outcome of the Project.";
            }
            item nextReviewDate [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "nextReviewDate";
                attribute :>> description = "The next Project review date in the starter's lexical YYYY-MM-DD shape.";
            }
        }

        item taskDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.task.details";
            attribute :>> description = "Optional current everyday details about one Task.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = taskType;
            item profileProperties [4] redefines propertyConstraints;
            item status [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "status";
                attribute :>> description = "The Task status exactly as the owner expresses it.";
            }
            item priority [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "priority";
                attribute :>> description = "The Task priority exactly as the owner expresses it.";
            }
            item dueDate [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "dueDate";
                attribute :>> description = "The Task due date in the starter's lexical YYYY-MM-DD shape.";
            }
            item context [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "context";
                attribute :>> description = "Owner-provided context for completing the Task.";
            }
        }

        item eventDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.event.details";
            attribute :>> description = "Optional current everyday details about one Event.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = eventType;
            item profileProperties [4] redefines propertyConstraints;
            item status [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "status";
                attribute :>> description = "The Event status exactly as the owner expresses it.";
            }
            item startDateProperty [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "start";
                attribute :>> description = "The Event start date in the starter's lexical YYYY-MM-DD shape.";
            }
            item endDateProperty [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "end";
                attribute :>> description = "The Event end date in the starter's lexical YYYY-MM-DD shape.";
            }
            item summary [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "summary";
                attribute :>> description = "A concise summary of the Event.";
            }
        }

        item routineDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.routine.details";
            attribute :>> description = "Optional current everyday details about one Routine.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = routineType;
            item profileProperties [4] redefines propertyConstraints;
            item cadence [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "cadence";
                attribute :>> description = "The owner-written recurrence cadence.";
            }
            item active [1] : 'Optional Boolean Property' subsets profileProperties {
                attribute :>> propertyName = "active";
                attribute :>> description = "Whether the Routine is currently active when known.";
            }
            item nextDueDate [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "nextDueDate";
                attribute :>> description = "The Routine's next due date in the starter's lexical YYYY-MM-DD shape.";
            }
            item context [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "context";
                attribute :>> description = "Owner-provided context for carrying out the Routine.";
            }
        }

        item decisionDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.decision.details";
            attribute :>> description = "Optional current everyday details about one Decision.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = decisionType;
            item profileProperties [3] redefines propertyConstraints;
            item status [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "status";
                attribute :>> description = "The Decision status exactly as the owner expresses it.";
            }
            item decisionDate [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "decisionDate";
                attribute :>> description = "The Decision date in the starter's lexical YYYY-MM-DD shape.";
            }
            item rationale [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "rationale";
                attribute :>> description = "The recorded rationale for the Decision.";
            }
        }

        item noteDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.note.details";
            attribute :>> description = "Optional current everyday details about one Note.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = noteType;
            item profileProperties [3] redefines propertyConstraints;
            item topic [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "topic";
                attribute :>> description = "The Note's topic.";
            }
            item summary [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "summary";
                attribute :>> description = "A concise summary of the Note.";
            }
            item captureDate [1] : 'Optional Date String Property' subsets profileProperties {
                attribute :>> propertyName = "captureDate";
                attribute :>> description = "The Note capture date in the starter's lexical YYYY-MM-DD shape.";
            }
        }

        item resourceDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.resource.details";
            attribute :>> description = "Optional current everyday details about one Resource.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = resourceType;
            item profileProperties [3] redefines propertyConstraints;
            item kind [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "kind";
                attribute :>> description = "The owner-written kind of Resource.";
            }
            item locationOrWebAddress [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "locationOrWebAddress";
                attribute :>> description = "A physical location or web address for the Resource.";
            }
            item summary [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "summary";
                attribute :>> description = "A concise summary of the Resource.";
            }
        }

        item placeDetails [1] : 'Associated Data Type Definition'
            subsets starterAssociatedDataTypes {
            attribute :>> typeKey = "life.place.details";
            attribute :>> description = "Optional current everyday details about one Place.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = placeType;
            item profileProperties [3] redefines propertyConstraints;
            item kind [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "kind";
                attribute :>> description = "The owner-written kind of Place.";
            }
            item address [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "address";
                attribute :>> description = "The Place address when known.";
            }
            item notes [1] : 'Optional String Property' subsets profileProperties {
                attribute :>> propertyName = "notes";
                attribute :>> description = "Additional owner-provided notes about the Place.";
            }
        }

        /* Directed connection vocabulary with exact endpoint type sets. */

        item belongsTo [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.belongs_to";
            attribute :>> description = "Connects work or knowledge to the Area it belongs to.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources are Goals, Projects, Tasks, Events, Routines, Decisions, Notes, or Resources; target is an Area.";
                ref item sources [8] redefines permittedSourceTypes;
                ref item goalSource [1] subsets sources = goalType;
                ref item projectSource [1] subsets sources = projectType;
                ref item taskSource [1] subsets sources = taskType;
                ref item eventSource [1] subsets sources = eventType;
                ref item routineSource [1] subsets sources = routineType;
                ref item decisionSource [1] subsets sources = decisionType;
                ref item noteSource [1] subsets sources = noteType;
                ref item resourceSource [1] subsets sources = resourceType;
                ref item target [1] redefines permittedTargetTypes = areaType;
            }
        }

        item supports [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.supports";
            attribute :>> description = "Connects work or knowledge to a Goal or Project it supports. Future agents should avoid self-links and circular support chains; those judgments are advisory.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources are Projects, Tasks, Events, Routines, Decisions, Notes, or Resources; targets are Goals or Projects.";
                ref item sources [7] redefines permittedSourceTypes;
                ref item projectSource [1] subsets sources = projectType;
                ref item taskSource [1] subsets sources = taskType;
                ref item eventSource [1] subsets sources = eventType;
                ref item routineSource [1] subsets sources = routineType;
                ref item decisionSource [1] subsets sources = decisionType;
                ref item noteSource [1] subsets sources = noteType;
                ref item resourceSource [1] subsets sources = resourceType;
                ref item targets [2] redefines permittedTargetTypes;
                ref item goalTarget [1] subsets targets = goalType;
                ref item projectTarget [1] subsets targets = projectType;
            }
        }

        item responsibleFor [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.responsible_for";
            attribute :>> description = "Connects a Person or Group to an Area or work item for which it is responsible.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources are Persons or Groups; targets are Areas, Goals, Projects, Tasks, Events, or Routines.";
                ref item sources [2] redefines permittedSourceTypes;
                ref item personSource [1] subsets sources = personType;
                ref item groupSource [1] subsets sources = groupType;
                ref item targets [6] redefines permittedTargetTypes;
                ref item areaTarget [1] subsets targets = areaType;
                ref item goalTarget [1] subsets targets = goalType;
                ref item projectTarget [1] subsets targets = projectType;
                ref item taskTarget [1] subsets targets = taskType;
                ref item eventTarget [1] subsets targets = eventType;
                ref item routineTarget [1] subsets targets = routineType;
            }
        }

        item memberOf [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.member_of";
            attribute :>> description = "Connects a Person to a Group of which the Person is a member.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Source is a Person; target is a Group.";
                ref item source [1] redefines permittedSourceTypes = personType;
                ref item target [1] redefines permittedTargetTypes = groupType;
            }
        }

        item involves [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.involves";
            attribute :>> description = "Connects a Goal, Project, Task, Event, Routine, or Decision to a participating Person or Group.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources are Goals, Projects, Tasks, Events, Routines, or Decisions; targets are Persons or Groups.";
                ref item sources [6] redefines permittedSourceTypes;
                ref item goalSource [1] subsets sources = goalType;
                ref item projectSource [1] subsets sources = projectType;
                ref item taskSource [1] subsets sources = taskType;
                ref item eventSource [1] subsets sources = eventType;
                ref item routineSource [1] subsets sources = routineType;
                ref item decisionSource [1] subsets sources = decisionType;
                ref item targets [2] redefines permittedTargetTypes;
                ref item personTarget [1] subsets targets = personType;
                ref item groupTarget [1] subsets targets = groupType;
            }
        }

        item locatedAt [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.located_at";
            attribute :>> description = "Connects a Task, Event, Routine, or Group to a Place where it occurs or is located.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources are Tasks, Events, Routines, or Groups; target is a Place.";
                ref item sources [4] redefines permittedSourceTypes;
                ref item taskSource [1] subsets sources = taskType;
                ref item eventSource [1] subsets sources = eventType;
                ref item routineSource [1] subsets sources = routineType;
                ref item groupSource [1] subsets sources = groupType;
                ref item target [1] redefines permittedTargetTypes = placeType;
            }
        }

        item documents [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.documents";
            attribute :>> description = "Connects a Note or Resource to an everyday item it documents. Future agents should avoid linking an object to itself; that judgment is advisory.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources are Notes or Resources; targets are any Everyday Life starter anchor type.";
                ref item sources [2] redefines permittedSourceTypes;
                ref item noteSource [1] subsets sources = noteType;
                ref item resourceSource [1] subsets sources = resourceType;
                ref item targets [12] redefines permittedTargetTypes;
                ref item personTarget [1] subsets targets = personType;
                ref item groupTarget [1] subsets targets = groupType;
                ref item areaTarget [1] subsets targets = areaType;
                ref item goalTarget [1] subsets targets = goalType;
                ref item projectTarget [1] subsets targets = projectType;
                ref item taskTarget [1] subsets targets = taskType;
                ref item eventTarget [1] subsets targets = eventType;
                ref item routineTarget [1] subsets targets = routineType;
                ref item decisionTarget [1] subsets targets = decisionType;
                ref item noteTarget [1] subsets targets = noteType;
                ref item resourceTarget [1] subsets targets = resourceType;
                ref item placeTarget [1] subsets targets = placeType;
            }
        }

        item mentions [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.mentions";
            attribute :>> description = "Connects a Note to an everyday item it mentions. Future agents should avoid linking a Note to itself; that judgment is advisory.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Source is a Note; targets are any Everyday Life starter anchor type.";
                ref item source [1] redefines permittedSourceTypes = noteType;
                ref item targets [12] redefines permittedTargetTypes;
                ref item personTarget [1] subsets targets = personType;
                ref item groupTarget [1] subsets targets = groupType;
                ref item areaTarget [1] subsets targets = areaType;
                ref item goalTarget [1] subsets targets = goalType;
                ref item projectTarget [1] subsets targets = projectType;
                ref item taskTarget [1] subsets targets = taskType;
                ref item eventTarget [1] subsets targets = eventType;
                ref item routineTarget [1] subsets targets = routineType;
                ref item decisionTarget [1] subsets targets = decisionType;
                ref item noteTarget [1] subsets targets = noteType;
                ref item resourceTarget [1] subsets targets = resourceType;
                ref item placeTarget [1] subsets targets = placeType;
            }
        }

        item dependsOn [1] : 'Link Type Definition' subsets starterLinkTypes {
            attribute :>> typeKey = "life.depends_on";
            attribute :>> description = "Connects a Goal, Project, or Task to another Goal, Project, or Task on which it depends. Future agents should avoid self-links and circular dependency chains; those judgments are advisory.";
            item endpoints redefines endpointConstraint {
                attribute :>> description = "Sources and targets are Goals, Projects, or Tasks.";
                ref item sources [3] redefines permittedSourceTypes;
                ref item goalSource [1] subsets sources = goalType;
                ref item projectSource [1] subsets sources = projectType;
                ref item taskSource [1] subsets sources = taskType;
                ref item targets [3] redefines permittedTargetTypes;
                ref item goalTarget [1] subsets targets = goalType;
                ref item projectTarget [1] subsets targets = projectType;
                ref item taskTarget [1] subsets targets = taskType;
            }
        }

        /* One current profile per matching anchor, while other data remains open. */

        item personDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Person details object describes exactly one Person.";
            ref item anchorType [1] redefines anchorTypes = personType;
            ref item dataType [1] redefines associatedDataTypes = personDetails;
        }
        item personOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Person has at most one Person details object.";
            ref item anchorType [1] redefines anchorTypes = personType;
            ref item dataType [1] redefines associatedDataTypes = personDetails;
        }
        item groupDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Group details object describes exactly one Group.";
            ref item anchorType [1] redefines anchorTypes = groupType;
            ref item dataType [1] redefines associatedDataTypes = groupDetails;
        }
        item groupOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Group has at most one Group details object.";
            ref item anchorType [1] redefines anchorTypes = groupType;
            ref item dataType [1] redefines associatedDataTypes = groupDetails;
        }
        item areaDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Area details object describes exactly one Area.";
            ref item anchorType [1] redefines anchorTypes = areaType;
            ref item dataType [1] redefines associatedDataTypes = areaDetails;
        }
        item areaOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Area has at most one Area details object.";
            ref item anchorType [1] redefines anchorTypes = areaType;
            ref item dataType [1] redefines associatedDataTypes = areaDetails;
        }
        item goalDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Goal details object describes exactly one Goal.";
            ref item anchorType [1] redefines anchorTypes = goalType;
            ref item dataType [1] redefines associatedDataTypes = goalDetails;
        }
        item goalOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Goal has at most one Goal details object.";
            ref item anchorType [1] redefines anchorTypes = goalType;
            ref item dataType [1] redefines associatedDataTypes = goalDetails;
        }
        item projectDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Project details object describes exactly one Project.";
            ref item anchorType [1] redefines anchorTypes = projectType;
            ref item dataType [1] redefines associatedDataTypes = projectDetails;
        }
        item projectOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Project has at most one Project details object.";
            ref item anchorType [1] redefines anchorTypes = projectType;
            ref item dataType [1] redefines associatedDataTypes = projectDetails;
        }
        item taskDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Task details object describes exactly one Task.";
            ref item anchorType [1] redefines anchorTypes = taskType;
            ref item dataType [1] redefines associatedDataTypes = taskDetails;
        }
        item taskOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Task has at most one Task details object.";
            ref item anchorType [1] redefines anchorTypes = taskType;
            ref item dataType [1] redefines associatedDataTypes = taskDetails;
        }
        item eventDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Event details object describes exactly one Event.";
            ref item anchorType [1] redefines anchorTypes = eventType;
            ref item dataType [1] redefines associatedDataTypes = eventDetails;
        }
        item eventOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Event has at most one Event details object.";
            ref item anchorType [1] redefines anchorTypes = eventType;
            ref item dataType [1] redefines associatedDataTypes = eventDetails;
        }
        item routineDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Routine details object describes exactly one Routine.";
            ref item anchorType [1] redefines anchorTypes = routineType;
            ref item dataType [1] redefines associatedDataTypes = routineDetails;
        }
        item routineOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Routine has at most one Routine details object.";
            ref item anchorType [1] redefines anchorTypes = routineType;
            ref item dataType [1] redefines associatedDataTypes = routineDetails;
        }
        item decisionDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Decision details object describes exactly one Decision.";
            ref item anchorType [1] redefines anchorTypes = decisionType;
            ref item dataType [1] redefines associatedDataTypes = decisionDetails;
        }
        item decisionOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Decision has at most one Decision details object.";
            ref item anchorType [1] redefines anchorTypes = decisionType;
            ref item dataType [1] redefines associatedDataTypes = decisionDetails;
        }
        item noteDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Note details object describes exactly one Note.";
            ref item anchorType [1] redefines anchorTypes = noteType;
            ref item dataType [1] redefines associatedDataTypes = noteDetails;
        }
        item noteOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Note has at most one Note details object.";
            ref item anchorType [1] redefines anchorTypes = noteType;
            ref item dataType [1] redefines associatedDataTypes = noteDetails;
        }
        item resourceDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Resource details object describes exactly one Resource.";
            ref item anchorType [1] redefines anchorTypes = resourceType;
            ref item dataType [1] redefines associatedDataTypes = resourceDetails;
        }
        item resourceOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Resource has at most one Resource details object.";
            ref item anchorType [1] redefines anchorTypes = resourceType;
            ref item dataType [1] redefines associatedDataTypes = resourceDetails;
        }
        item placeDetailsOneAnchor [1] : 'Profile Has Exactly One Matching Anchor'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Place details object describes exactly one Place.";
            ref item anchorType [1] redefines anchorTypes = placeType;
            ref item dataType [1] redefines associatedDataTypes = placeDetails;
        }
        item placeOneDetails [1] : 'Anchor Has At Most One Matching Profile'
            subsets starterRelationshipConstraints {
            attribute :>> description = "Each Place has at most one Place details object.";
            ref item anchorType [1] redefines anchorTypes = placeType;
            ref item dataType [1] redefines associatedDataTypes = placeDetails;
        }
    }

    item everydayLifeStarter [1] : 'Everyday Life Starter Definition Set';
}
