package VellisSystems {
    private import VellisFoundation::*;
    private import RTGDomain::*;
    private import VellisServiceContracts::*;

    /*
     * Minimal system definitions needed by the current use cases.
     * Detailed internal behavior, protocol adapters, deployment, and storage
     * technology are deliberately deferred.
     */

    // =================================================================
    // RTG memory subsystem
    // =================================================================

    part def RTG_System {
        doc /*
         * A reusable, journaled, constraint-governed graph memory system.
         *
         * The canonical anchor/data/link graph and durable ledger are
         * constitutive state of the RTG black box. The implementation of
         * query evaluation, constraint evaluation, derived indexes,
         * snapshots, and persistence is not specified here.
         */

        item graph : RTG_Graph;
        item activityLedger : RTG_Activity_Ledger;

        ref item activeConstraintModel : Constraint_Model;
        ref item stagedConstraintModel [0..1] : Constraint_Model;

        attribute currentRevision : ScalarValues::Natural;

        port memoryService : ~RTG_Client_Port;
    }

    // =================================================================
    // Vellis product system
    // =================================================================

    part def Vellis_System {
        doc /*
         * A single-owner personal AI runtime providing durable memory,
         * hosted applications, automations, and agent-facing capabilities.
         */

        port vellisService : ~Vellis_Client_Port;
    }

    part def Hosted_Application :> Software {
        doc /*
         * An owner-controlled GUI application hosted by Vellis. Its concrete
         * web technology and service binding are deferred.
         */
    }

    part def Personal_Automation :> Software {
        doc /*
         * An owner-controlled automation hosted and executed by Vellis. Its
         * implementation language is deferred.
         */
    }

    part def Application_Runtime {
        part applications [*] : Hosted_Application;
    }

    part def Automation_Runtime {
        part automations [*] : Personal_Automation;
    }

    part def Vellis_System_Composition :> Vellis_System {
        doc /*
         * The smallest stable first-level composition currently justified by
         * the product concept. Internal coordination remains unspecified.
         */

        part memory : RTG_System;
        part applications : Application_Runtime;
        part automations : Automation_Runtime;
    }
}
