package EverydayLifeStarter {
    private import RTG::*;

    item def 'Optional Text Property' :> 'Property Definition' {
        attribute :>> valueKind = 'Scalar Kind'::text;
        attribute :>> required = false;
        attribute :>> nullable = false;
    }
    item def 'Optional Boolean Property' :> 'Property Definition' {
        attribute :>> valueKind = 'Scalar Kind'::boolean;
        attribute :>> required = false;
        attribute :>> nullable = false;
    }
    item def 'Optional Date Property' :> 'Property Definition' {
        attribute :>> valueKind = 'Scalar Kind'::date;
        attribute :>> required = false;
        attribute :>> nullable = false;
    }
    item def 'Starter Details Type' :> 'Associated Data Type Definition' {
        item :>> anchorsPerObject {
            attribute :>> minimum = 1;
            attribute :>> maximum = 1;
        }
        item :>> objectsPerAnchor {
            attribute :>> minimum = 0;
            attribute :>> maximum = 1;
        }
    }
    item def 'Starter Link Type' :> 'Link Type Definition' {
        item :>> linksPerSource { attribute :>> minimum = 0; }
        item :>> linksPerTarget { attribute :>> minimum = 0; }
    }

    item def 'Everyday Life Starter Definition Set' :> 'Graph Definition Set' {
        doc /*
         * The complete optional recommended fresh vocabulary. It contains no
         * graph data and is not a protected ontology or later installer.
         */
        item personType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.person";
            attribute :>> description =
                "A person known to the owner. Use the anchor display name for the person's name.";
        }
        item groupType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.group";
            attribute :>> description =
                "A household, family, team, organization, or community. Use the anchor display name for its name.";
        }
        item areaType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.area";
            attribute :>> description =
                "An ongoing sphere of responsibility such as health, home, family, finances, or work. Use the anchor display name for its title.";
        }
        item goalType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.goal";
            attribute :>> description =
                "An outcome the owner wants to achieve. Use the anchor display name for its title.";
        }
        item projectType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.project";
            attribute :>> description =
                "A coordinated body of work with a desired outcome. Use the anchor display name for its title.";
        }
        item taskType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.task";
            attribute :>> description =
                "A discrete piece of work. Use the anchor display name for its title.";
        }
        item eventType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.event";
            attribute :>> description =
                "An occurrence the owner wants to remember. Use the anchor display name for its title.";
        }
        item routineType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.routine";
            attribute :>> description =
                "A recurring responsibility or practice. Use the anchor display name for its title.";
        }
        item decisionType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.decision";
            attribute :>> description =
                "A decision whose outcome or reasoning matters later. Use the anchor display name for its title.";
        }
        item noteType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.note";
            attribute :>> description =
                "A captured piece of knowledge or observation. Use the anchor display name for its title.";
        }
        item resourceType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.resource";
            attribute :>> description =
                "A useful source, object, or reference. Use the anchor display name for its title.";
        }
        item placeType [1] : 'Anchor Type Definition' subsets anchorTypes {
            attribute :>> typeKey = "life.place";
            attribute :>> description =
                "A place relevant to the owner's life. Use the anchor display name for its name.";
        }

        item personDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.person.details";
            attribute :>> description =
                "Optional current everyday details about one Person; other independently typed data may also describe that Person.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = personType;
            item profileProperties [3] redefines properties;
            item relationship [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "relationship";
                attribute :>> description = "The person's relationship to the owner or household.";
            }
            item preferredContact [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "preferredContact";
                attribute :>> description = "The person's preferred contact method when known.";
            }
            item notes [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "notes";
                attribute :>> description = "Additional owner-provided notes about the person.";
            }
        }
        item groupDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.group.details";
            attribute :>> description = "Optional current everyday details about one Group.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = groupType;
            item profileProperties [2] redefines properties;
            item kind [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "kind"; attribute :>> description = "The owner-written kind of group.";
            }
            item descriptionProperty [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "description"; attribute :>> description = "A description of the group.";
            }
        }
        item areaDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.area.details";
            attribute :>> description = "Optional current everyday details about one Area.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = areaType;
            item profileProperties [3] redefines properties;
            item domain [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "domain"; attribute :>> description = "The owner-written domain of responsibility.";
            }
            item focus [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "focus"; attribute :>> description = "The Area's current focus when known.";
            }
            item active [1] : 'Optional Boolean Property' subsets profileProperties {
                attribute :>> name = "active"; attribute :>> description = "Whether the Area is currently active when known.";
            }
        }
        item goalDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.goal.details";
            attribute :>> description = "Optional current everyday details about one Goal.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = goalType;
            item profileProperties [4] redefines properties;
            item status [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "status"; attribute :>> description = "The Goal status exactly as the owner expresses it.";
            }
            item priority [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "priority"; attribute :>> description = "The Goal priority exactly as the owner expresses it.";
            }
            item targetDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "targetDate"; attribute :>> description = "The Goal target date.";
            }
            item desiredOutcome [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "desiredOutcome"; attribute :>> description = "The desired outcome of the Goal.";
            }
        }
        item projectDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.project.details";
            attribute :>> description = "Optional current everyday details about one Project.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = projectType;
            item profileProperties [4] redefines properties;
            item status [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "status"; attribute :>> description = "The Project status exactly as the owner expresses it.";
            }
            item priority [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "priority"; attribute :>> description = "The Project priority exactly as the owner expresses it.";
            }
            item desiredOutcome [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "desiredOutcome"; attribute :>> description = "The desired outcome of the Project.";
            }
            item nextReviewDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "nextReviewDate"; attribute :>> description = "The next Project review date.";
            }
        }
        item taskDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.task.details";
            attribute :>> description = "Optional current everyday details about one Task.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = taskType;
            item profileProperties [4] redefines properties;
            item status [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "status"; attribute :>> description = "The Task status exactly as the owner expresses it.";
            }
            item priority [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "priority"; attribute :>> description = "The Task priority exactly as the owner expresses it.";
            }
            item dueDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "dueDate"; attribute :>> description = "The Task due date.";
            }
            item context [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "context"; attribute :>> description = "Owner-provided context for completing the Task.";
            }
        }
        item eventDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.event.details";
            attribute :>> description = "Optional current everyday details about one Event.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = eventType;
            item profileProperties [4] redefines properties;
            item status [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "status"; attribute :>> description = "The Event status exactly as the owner expresses it.";
            }
            item startDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "start"; attribute :>> description = "The Event start date.";
            }
            item endDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "end"; attribute :>> description = "The Event end date.";
            }
            item summary [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "summary"; attribute :>> description = "A concise summary of the Event.";
            }
        }
        item routineDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.routine.details";
            attribute :>> description = "Optional current everyday details about one Routine.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = routineType;
            item profileProperties [4] redefines properties;
            item cadence [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "cadence"; attribute :>> description = "The owner-written recurrence cadence.";
            }
            item active [1] : 'Optional Boolean Property' subsets profileProperties {
                attribute :>> name = "active"; attribute :>> description = "Whether the Routine is currently active when known.";
            }
            item nextDueDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "nextDueDate"; attribute :>> description = "The Routine's next due date.";
            }
            item context [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "context"; attribute :>> description = "Owner-provided context for carrying out the Routine.";
            }
        }
        item decisionDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.decision.details";
            attribute :>> description = "Optional current everyday details about one Decision.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = decisionType;
            item profileProperties [3] redefines properties;
            item status [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "status"; attribute :>> description = "The Decision status exactly as the owner expresses it.";
            }
            item decisionDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "decisionDate"; attribute :>> description = "The Decision date.";
            }
            item rationale [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "rationale"; attribute :>> description = "The recorded rationale for the Decision.";
            }
        }
        item noteDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.note.details";
            attribute :>> description = "Optional current everyday details about one Note.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = noteType;
            item profileProperties [3] redefines properties;
            item topic [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "topic"; attribute :>> description = "The Note's topic.";
            }
            item summary [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "summary"; attribute :>> description = "A concise summary of the Note.";
            }
            item captureDate [1] : 'Optional Date Property' subsets profileProperties {
                attribute :>> name = "captureDate"; attribute :>> description = "The Note capture date.";
            }
        }
        item resourceDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.resource.details";
            attribute :>> description = "Optional current everyday details about one Resource.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = resourceType;
            item profileProperties [3] redefines properties;
            item kind [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "kind"; attribute :>> description = "The owner-written kind of Resource.";
            }
            item locationOrWebAddress [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "locationOrWebAddress"; attribute :>> description = "A physical location or web address for the Resource.";
            }
            item summary [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "summary"; attribute :>> description = "A concise summary of the Resource.";
            }
        }
        item placeDetails [1] : 'Starter Details Type' subsets associatedDataTypes {
            attribute :>> typeKey = "life.place.details";
            attribute :>> description = "Optional current everyday details about one Place.";
            ref item matchingAnchor [1] redefines permittedAnchorTypes = placeType;
            item profileProperties [3] redefines properties;
            item kind [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "kind"; attribute :>> description = "The owner-written kind of Place.";
            }
            item address [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "address"; attribute :>> description = "The Place address when known.";
            }
            item notes [1] : 'Optional Text Property' subsets profileProperties {
                attribute :>> name = "notes"; attribute :>> description = "Additional owner-provided notes about the Place.";
            }
        }

        item belongsTo [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.belongs_to";
            attribute :>> description = "Connects work or knowledge to the Area it belongs to.";
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
        item supports [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.supports";
            attribute :>> description = "Connects work or knowledge to a Goal or Project it supports.";
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
        item responsibleFor [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.responsible_for";
            attribute :>> description = "Connects a Person or Group to an Area or work item for which it is responsible.";
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
        item memberOf [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.member_of";
            attribute :>> description = "Connects a Person to a Group of which the Person is a member.";
            ref item source [1] redefines permittedSourceTypes = personType;
            ref item target [1] redefines permittedTargetTypes = groupType;
        }
        item involves [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.involves";
            attribute :>> description = "Connects a Goal, Project, Task, Event, Routine, or Decision to a participating Person or Group.";
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
        item locatedAt [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.located_at";
            attribute :>> description = "Connects a Task, Event, Routine, or Group to a Place where it occurs or is located.";
            ref item sources [4] redefines permittedSourceTypes;
            ref item taskSource [1] subsets sources = taskType;
            ref item eventSource [1] subsets sources = eventType;
            ref item routineSource [1] subsets sources = routineType;
            ref item groupSource [1] subsets sources = groupType;
            ref item target [1] redefines permittedTargetTypes = placeType;
        }
        item documents [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.documents";
            attribute :>> description = "Connects a Note or Resource to an everyday item it documents.";
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
        item mentions [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.mentions";
            attribute :>> description = "Connects a Note to an everyday item it mentions.";
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
        item dependsOn [1] : 'Starter Link Type' subsets linkTypes {
            attribute :>> typeKey = "life.depends_on";
            attribute :>> description = "Connects a Goal, Project, or Task to another Goal, Project, or Task on which it depends.";
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

    item everydayLifeStarter [1] : 'Everyday Life Starter Definition Set';
}
