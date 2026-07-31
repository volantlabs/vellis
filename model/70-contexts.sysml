package VellisContexts {
    private import VellisFoundation::*;
    private import VellisServiceContracts::*;
    private import VellisSystems::*;
    private import RTGUseCases::*;
    private import VellisUseCases::*;
    private import VellisRequirements::*;

    /*
     * Concrete contexts instantiate the black-box use-case definitions with
     * actual participants. The use-case definitions remain reusable and
     * independent of these particular compositions.
     */

    part def RTG_System_Context {
        part system : RTG_System;
        ref part client : RTG_Client;

        interface memoryService
            connect client.memoryService to system.memoryService;

        use case applyGraphChange : 'Apply graph change' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case queryCurrentMemory : 'Query current memory' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case queryMemoryAtRevision : 'Query memory at revision' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case inspectActivityHistory : 'Inspect activity history' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case restorePriorGraphState : 'Restore prior graph state' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case stageConstraintModel : 'Stage constraint model' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case editStagedConstraintModel : 'Edit staged constraint model' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case assessStagedConstraintModel : 'Assess staged constraint model' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case activateStagedConstraintModel : 'Activate staged constraint model' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        use case discardStagedConstraintModel : 'Discard staged constraint model' {
            subject redefines system = RTG_System_Context::system;
            actor redefines client = RTG_System_Context::client;
        }

        requirement durableHistory : RTG_Ledger_Requirements {
            subject redefines system = RTG_System_Context::system;
        }

        requirement graphData : RTG_Graph_Data_Requirements {
            subject redefines graph =
                RTG_System_Context::system.graph;
        }

        requirement constraintModelManagement :
            Constraint_Model_Management_Requirements {

            subject redefines system = RTG_System_Context::system;
        }
    }

    part def Vellis_System_Context {
        part system : Vellis_System_Composition;

        ref part owner : Vellis_Owner;
        ref part agent : External_AI_Agent;

        interface externalService
            connect agent.vellisService to system.vellisService;

        use case useAIWithPersistentContext :
            'Use AI with persistent personal context' {

            subject redefines system = Vellis_System_Context::system;
            actor redefines owner = Vellis_System_Context::owner;
            actor redefines agent = Vellis_System_Context::agent;
        }

        use case usePersonalApplication : 'Use personal application' {
            subject redefines system = Vellis_System_Context::system;
            actor redefines owner = Vellis_System_Context::owner;
        }

        use case runPersonalAutomation : 'Run personal automation' {
            subject redefines system = Vellis_System_Context::system;
            actor redefines owner = Vellis_System_Context::owner;
        }

        use case reviewPersonalMemoryAndActivity :
            'Review personal memory and activity' {

            subject redefines system = Vellis_System_Context::system;
            actor redefines owner = Vellis_System_Context::owner;
        }

        use case explorePriorPersonalMemory :
            'Explore prior personal memory' {

            subject redefines system = Vellis_System_Context::system;
            actor redefines owner = Vellis_System_Context::owner;
        }

        use case restorePriorPersonalMemory :
            'Restore prior personal memory' {

            subject redefines system = Vellis_System_Context::system;
            actor redefines owner = Vellis_System_Context::owner;
        }

        requirement ownership : Vellis_Ownership_Requirements {
            subject redefines system = Vellis_System_Context::system;
        }

        requirement simplicity : Vellis_Simplicity_Requirements {
            subject redefines system = Vellis_System_Context::system;
        }
    }
}
