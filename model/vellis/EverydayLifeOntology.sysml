package VellisEverydayLifeOntology {
    private import SoftwareComponentModeling::*;
    private import ScalarValues::*;

    doc /*
     * Vellis-owned starter ontology for one immediately useful personal, household/family,
     * and work graph. The model defines schema only and introduces no user facts.
     */

    metadata def StarterAnchorDefinition {
        :>> annotatedElement : SysML::PartDefinition;
        attribute typeKey : String;
        attribute factsTypeKey : String;
        attribute description : String;
    }

    metadata def StarterLinkDefinition {
        :>> annotatedElement : SysML::ItemDefinition;
        attribute typeKey : String;
        attribute description : String;
        attribute sourceTypes[1..*] : String;
        attribute targetTypes[1..*] : String;
    }

    attribute def EverydayLifeOntologyIdentity {
        attribute ontologyId : String = "ontology.vellis.everyday_life";
        attribute version : String = "1";
        attribute bootstrapMigrationId : String = "migration.vellis.everyday_life.v1";
    }
    enum def EverydayLifeInstallationStatus { enum installed; enum alreadyInstalled; enum customPreserved; }
    attribute def EverydayLifeInstallationResult {
        attribute status : EverydayLifeInstallationStatus;
        attribute ontology : EverydayLifeOntologyIdentity;
        attribute schemaDefinitionCount : Integer;
    }

    attribute def PersonFacts { attribute name : String; attribute relationship[0..1] : String; attribute preferredContact[0..1] : String; attribute notes[0..1] : String; }
    attribute def GroupFacts { attribute name : String; attribute kind[0..1] : String; attribute description[0..1] : String; }
    attribute def AreaFacts { attribute title : String; attribute domain[0..1] : String; attribute focus[0..1] : String; attribute active[0..1] : Boolean; }
    attribute def GoalFacts { attribute title : String; attribute domain[0..1] : String; attribute status[0..1] : String; attribute priority[0..1] : String; attribute targetDate[0..1] : String; attribute desiredOutcome[0..1] : String; }
    attribute def ProjectFacts { attribute title : String; attribute domain[0..1] : String; attribute status[0..1] : String; attribute priority[0..1] : String; attribute desiredOutcome[0..1] : String; attribute nextReview[0..1] : String; }
    attribute def TaskFacts { attribute title : String; attribute domain[0..1] : String; attribute status[0..1] : String; attribute priority[0..1] : String; attribute due[0..1] : String; attribute context[0..1] : String; }
    attribute def EventFacts { attribute title : String; attribute domain[0..1] : String; attribute status[0..1] : String; attribute start[0..1] : String; attribute 'end'[0..1] : String; attribute summary[0..1] : String; }
    attribute def RoutineFacts { attribute title : String; attribute domain[0..1] : String; attribute cadence[0..1] : String; attribute active[0..1] : Boolean; attribute nextDue[0..1] : String; attribute context[0..1] : String; }
    attribute def DecisionFacts { attribute title : String; attribute domain[0..1] : String; attribute status[0..1] : String; attribute decidedOn[0..1] : String; attribute rationale[0..1] : String; }
    attribute def NoteFacts { attribute title : String; attribute domain[0..1] : String; attribute topic[0..1] : String; attribute summary[0..1] : String; attribute capturedAt[0..1] : String; }
    attribute def ResourceFacts { attribute title : String; attribute domain[0..1] : String; attribute kind[0..1] : String; attribute locator[0..1] : String; attribute summary[0..1] : String; }
    attribute def PlaceFacts { attribute name : String; attribute kind[0..1] : String; attribute address[0..1] : String; attribute notes[0..1] : String; }

    part def <'ontology.vellis.everyday_life.Person'> Person { @StarterAnchorDefinition { typeKey = "Person"; factsTypeKey = "PersonFacts"; description = "A person known to the individual or shared graph."; } attribute facts : PersonFacts; }
    part def <'ontology.vellis.everyday_life.Group'> Group { @StarterAnchorDefinition { typeKey = "Group"; factsTypeKey = "GroupFacts"; description = "A household, family, team, organization, or community."; } attribute facts : GroupFacts; }
    part def <'ontology.vellis.everyday_life.Area'> Area { @StarterAnchorDefinition { typeKey = "Area"; factsTypeKey = "AreaFacts"; description = "An ongoing sphere of personal, household, family, or work responsibility."; } attribute facts : AreaFacts; }
    part def <'ontology.vellis.everyday_life.Goal'> Goal { @StarterAnchorDefinition { typeKey = "Goal"; factsTypeKey = "GoalFacts"; description = "A desired outcome that work or routines may support."; } attribute facts : GoalFacts; }
    part def <'ontology.vellis.everyday_life.Project'> Project { @StarterAnchorDefinition { typeKey = "Project"; factsTypeKey = "ProjectFacts"; description = "A finite coordinated effort intended to produce an outcome."; } attribute facts : ProjectFacts; }
    part def <'ontology.vellis.everyday_life.Task'> Task { @StarterAnchorDefinition { typeKey = "Task"; factsTypeKey = "TaskFacts"; description = "An actionable unit of work."; } attribute facts : TaskFacts; }
    part def <'ontology.vellis.everyday_life.Event'> Event { @StarterAnchorDefinition { typeKey = "Event"; factsTypeKey = "EventFacts"; description = "A time-bound occurrence, appointment, or meeting."; } attribute facts : EventFacts; }
    part def <'ontology.vellis.everyday_life.Routine'> Routine { @StarterAnchorDefinition { typeKey = "Routine"; factsTypeKey = "RoutineFacts"; description = "A recurring practice or responsibility."; } attribute facts : RoutineFacts; }
    part def <'ontology.vellis.everyday_life.Decision'> Decision { @StarterAnchorDefinition { typeKey = "Decision"; factsTypeKey = "DecisionFacts"; description = "A choice or conclusion worth retaining with rationale."; } attribute facts : DecisionFacts; }
    part def <'ontology.vellis.everyday_life.Note'> Note { @StarterAnchorDefinition { typeKey = "Note"; factsTypeKey = "NoteFacts"; description = "A captured observation, idea, or piece of context."; } attribute facts : NoteFacts; }
    part def <'ontology.vellis.everyday_life.Resource'> Resource { @StarterAnchorDefinition { typeKey = "Resource"; factsTypeKey = "ResourceFacts"; description = "A document, URL, artifact, or other useful resource."; } attribute facts : ResourceFacts; }
    part def <'ontology.vellis.everyday_life.Place'> Place { @StarterAnchorDefinition { typeKey = "Place"; factsTypeKey = "PlaceFacts"; description = "A physical or named place relevant to the graph."; } attribute facts : PlaceFacts; }

    item def BelongsTo { attribute typeKey : String = "belongs_to"; @StarterLinkDefinition { typeKey = "belongs_to"; description = "An item belongs to an ongoing area."; sourceTypes = ("Goal", "Project", "Task", "Event", "Routine", "Decision", "Note", "Resource"); targetTypes = ("Area"); } }
    item def Supports { attribute typeKey : String = "supports"; @StarterLinkDefinition { typeKey = "supports"; description = "An item supports a goal or project."; sourceTypes = ("Project", "Task", "Event", "Routine", "Decision", "Note", "Resource"); targetTypes = ("Goal", "Project"); } }
    item def ResponsibleFor { attribute typeKey : String = "responsible_for"; @StarterLinkDefinition { typeKey = "responsible_for"; description = "A person or group is responsible for an area or work item."; sourceTypes = ("Person", "Group"); targetTypes = ("Area", "Goal", "Project", "Task", "Event", "Routine"); } }
    item def MemberOf { attribute typeKey : String = "member_of"; @StarterLinkDefinition { typeKey = "member_of"; description = "A person is a member of a group."; sourceTypes = ("Person"); targetTypes = ("Group"); } }
    item def Involves { attribute typeKey : String = "involves"; @StarterLinkDefinition { typeKey = "involves"; description = "An outcome, activity, or decision involves a person or group."; sourceTypes = ("Goal", "Project", "Task", "Event", "Routine", "Decision"); targetTypes = ("Person", "Group"); } }
    item def LocatedAt { attribute typeKey : String = "located_at"; @StarterLinkDefinition { typeKey = "located_at"; description = "An activity or group is associated with a place."; sourceTypes = ("Task", "Event", "Routine", "Group"); targetTypes = ("Place"); } }
    item def Documents { attribute typeKey : String = "documents"; @StarterLinkDefinition { typeKey = "documents"; description = "A note or resource documents another starter-schema anchor."; sourceTypes = ("Note", "Resource"); targetTypes = ("Person", "Group", "Area", "Goal", "Project", "Task", "Event", "Routine", "Decision", "Note", "Resource", "Place"); } }
    item def Mentions { attribute typeKey : String = "mentions"; @StarterLinkDefinition { typeKey = "mentions"; description = "A note mentions another starter-schema anchor."; sourceTypes = ("Note"); targetTypes = ("Person", "Group", "Area", "Goal", "Project", "Task", "Event", "Routine", "Decision", "Note", "Resource", "Place"); } }
    item def DependsOn { attribute typeKey : String = "depends_on"; @StarterLinkDefinition { typeKey = "depends_on"; description = "An outcome or work item depends on another outcome or work item."; sourceTypes = ("Goal", "Project", "Task"); targetTypes = ("Goal", "Project", "Task"); } }

    action def InstallEverydayLifeOntology { out result : EverydayLifeInstallationResult; doc /* Recover durable state first; on a genuinely empty graph, stage and strictly cut over the generated schema bundle as one atomic, ledgered bootstrap migration. */ }
    part def EverydayLifeOntologyInstaller {
        perform action install[0..*] : InstallEverydayLifeOntology;
    }

    requirement <'contract.vellis.everyday_life.schema_only'> schemaOnly { subject installation : InstallEverydayLifeOntology; require constraint { doc /* Installation creates schema definitions only and creates no user graph objects. */ } }
    requirement <'contract.vellis.everyday_life.empty_only'> emptyOnly { subject installation : InstallEverydayLifeOntology; require constraint { doc /* Exact prior installation is idempotent; existing custom schema or graph state is preserved without overlay. */ } }
    requirement <'contract.vellis.everyday_life.extension'> extensionCompatibility { subject installation : InstallEverydayLifeOntology; require constraint { doc /* Additive application schema evolution may extend the installed ontology through ordinary validated migrations without changing its stable identities or causing bootstrap to overwrite the extension. */ } }
    requirement <'contract.vellis.everyday_life.atomic'> atomicInstallation { subject installation : InstallEverydayLifeOntology; require constraint { doc /* Identity collisions, validation failures, or cutover failures leave pre-installation state unchanged. */ } }
    requirement <'contract.vellis.startup.recovery_first'> recoveryFirst { subject installation : InstallEverydayLifeOntology; require constraint { doc /* Startup reconstructs durable ledger state before inspecting or installing starter schema and fails closed if replay cannot reproduce it. */ } }

    part ontologyInstaller : EverydayLifeOntologyInstaller {
        satisfy schemaOnly by ontologyInstaller.install;
        satisfy emptyOnly by ontologyInstaller.install;
        satisfy extensionCompatibility by ontologyInstaller.install;
        satisfy atomicInstallation by ontologyInstaller.install;
        satisfy recoveryFirst by ontologyInstaller.install;
    }

    verification def EverydayLifeOntologyVerification {
        subject installation : InstallEverydayLifeOntology;
        objective { verify schemaOnly; verify emptyOnly; verify extensionCompatibility; verify atomicInstallation; verify recoveryFirst; }
        @EvidenceBinding { evidenceId = "apps/rtg_knowledge_graph/tests/test_starter_schema.py#EverydayLifeOntologyVerification"; implementationScope = "VellisLocalPython"; }
    }
}
