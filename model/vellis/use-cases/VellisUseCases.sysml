package VellisUseCases {
    private import Vellis::*;
    private import VellisOperations::*;

    abstract part def VellisUser { doc /* A human or software agent acting through the Vellis application facade. */ }
    part def HumanOperator :> VellisUser { doc /* A human Vellis user. */ }
    part def AiAgent :> VellisUser { doc /* An AI Vellis user. */ }

    use case def BootstrapAndEvolveSchema {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Establish or evolve a validated live schema for subsequent knowledge work. */ }
    }
    use case def ValidateAndApplyLiveKnowledge {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Validate and apply ordinary live knowledge without weakening schema or constraints. */ }
    }
    use case def StageAndCutoverKnowledge {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Stage migration-scoped knowledge work and make it live through an explicit cutover. */ }
    }
    use case def QueryAndDiscoverKnowledge {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Discover relevant schema and answer a graph question without mutation. */ }
    }
    use case def SnapshotAndRestoreSystem {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Persist, inspect, and restore a coordinated RTG snapshot, including snapshot-only transfer into a fresh runtime chronology. */ }
    }
    use case def AuditAndReplayActivity {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Inspect runtime causal traces and prove that committed canonical effects reconstruct the expected managed state. */ }
    }
    use case def InspectStateAndGuidance {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Determine current system posture and the appropriate next workflow. */ }
    }
    use case def AbandonStagedWork {
        subject application : VellisApplication;
        actor users[1..*] : VellisUser;
        objective { doc /* Remove safe non-live staged work while preserving all live state. */ }
    }

    part vellis : VellisApplication {
        part :>> facade {
            perform bootstrapAndEvolveSchema.inspectState;
            perform bootstrapAndEvolveSchema.stageSchema;
            perform bootstrapAndEvolveSchema.cutover;
            perform validateAndApplyLiveKnowledge.validate;
            perform validateAndApplyLiveKnowledge.apply;
            perform stageAndCutoverKnowledge.stage;
            perform stageAndCutoverKnowledge.cutover;
            perform queryAndDiscoverKnowledge.discover;
            perform queryAndDiscoverKnowledge.inspectSchema;
            perform queryAndDiscoverKnowledge.query;
            perform snapshotAndRestoreSystem.persist;
            perform snapshotAndRestoreSystem.load;
            perform snapshotAndRestoreSystem.restore;
            perform auditAndReplayActivity.history;
            perform auditAndReplayActivity.verifyReplay;
            perform inspectStateAndGuidance.'state';
            perform inspectStateAndGuidance.guide;
            perform abandonStagedWork.abandon;
        }
    }
    part humanActor : HumanOperator;

    use case bootstrapAndEvolveSchema : BootstrapAndEvolveSchema {
        subject application = vellis;
        actor users = humanActor;
        action inspectState : RtgGetSystemState;
        then action stageSchema : RtgStageSchemaMigration;
        then action cutover : RtgApplyMigrationCutover;
    }

    use case validateAndApplyLiveKnowledge : ValidateAndApplyLiveKnowledge {
        subject application = vellis;
        actor users = humanActor;
        action validate : RtgValidateLiveGraphChanges;
        then action apply : RtgApplyLiveGraphChanges;
    }

    use case stageAndCutoverKnowledge : StageAndCutoverKnowledge {
        subject application = vellis;
        actor users = humanActor;
        action stage : RtgStageKnowledgeChanges;
        then action cutover : RtgApplyMigrationCutover;
    }

    use case queryAndDiscoverKnowledge : QueryAndDiscoverKnowledge {
        subject application = vellis;
        actor users = humanActor;
        action discover : RtgDiscoverAnchorTypes;
        then action inspectSchema : RtgGetSchemaPack;
        then action query : RtgExecuteQuery;
    }

    use case snapshotAndRestoreSystem : SnapshotAndRestoreSystem {
        subject application = vellis;
        actor users = humanActor;
        action persist : RtgPersistSystemSnapshot;
        then action load : RtgLoadPersistedSnapshot;
        then action restore : RtgRestoreFromSnapshot;
    }

    use case auditAndReplayActivity : AuditAndReplayActivity {
        subject application = vellis;
        actor users = humanActor;
        action history : RtgListMigrationHistory;
        then action verifyReplay : RtgVerifyReplayFromLedger;
    }

    use case inspectStateAndGuidance : InspectStateAndGuidance {
        subject application = vellis;
        actor users = humanActor;
        action 'state' : RtgGetSystemState;
        then action guide : RtgGetUsageGuide;
    }

    use case abandonStagedWork : AbandonStagedWork {
        subject application = vellis;
        actor users = humanActor;
        action abandon : RtgAbandonMigration;
    }
}
