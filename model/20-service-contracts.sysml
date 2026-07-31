package VellisServiceContracts {
    private import VellisFoundation::*;
    private import RTGDomain::*;

    /*
     * Technology-independent request/response contracts. Any future binding
     * is a separate realization decision and is not selected by this model.
     */

    // =================================================================
    // RTG service contract
    // =================================================================

    abstract item def RTG_Service_Request;
    abstract item def RTG_Service_Response;

    item def Apply_Graph_Change_Request :> RTG_Service_Request {
        item change : Graph_Change;
    }

    item def Apply_Graph_Change_Response :> RTG_Service_Response {
        item result : Graph_Change_Result;
        attribute resultingRevision [0..1] : ScalarValues::Natural;
    }

    item def Query_Current_Memory_Request :> RTG_Service_Request {
        item query : Memory_Query;
    }

    item def Query_Current_Memory_Response :> RTG_Service_Response {
        item result : Memory_Query_Result;
    }

    item def Query_Historical_Memory_Request :> RTG_Service_Request {
        item query : Memory_Query;
        attribute revision : ScalarValues::Natural;
    }

    item def Query_Historical_Memory_Response :> RTG_Service_Response {
        item result : Memory_Query_Result;
    }

    item def Inspect_Activity_History_Request :> RTG_Service_Request {
        item query : Activity_History_Query;
    }

    item def Inspect_Activity_History_Response :> RTG_Service_Response {
        item result : Activity_History_Result;
    }

    item def Restore_Prior_State_Request :> RTG_Service_Request {
        attribute revision : ScalarValues::Natural;
    }

    item def Restore_Prior_State_Response :> RTG_Service_Response {
        attribute resultingRevision [0..1] : ScalarValues::Natural;
    }

    item def Stage_Constraint_Model_Request :> RTG_Service_Request {
        item model : Constraint_Model;
    }

    item def Edit_Staged_Constraint_Model_Request :> RTG_Service_Request {
        item change : Constraint_Model_Change;
    }

    item def Assess_Staged_Constraint_Model_Request :> RTG_Service_Request;

    item def Activate_Staged_Constraint_Model_Request :> RTG_Service_Request;

    item def Discard_Staged_Constraint_Model_Request :> RTG_Service_Request;

    item def Constraint_Model_Operation_Response :> RTG_Service_Response {
        item assessment [0..1] : Constraint_Model_Assessment;
    }

    port def RTG_Client_Port {
        doc /* Directions are stated from the RTG client perspective. */

        out item request : RTG_Service_Request;
        in item response : RTG_Service_Response;
    }

    part def RTG_Client :> Software {
        port memoryService : RTG_Client_Port;
    }

    // =================================================================
    // Vellis service contract
    // =================================================================

    abstract item def Vellis_Service_Request;
    abstract item def Vellis_Service_Response;

    item def Owner_Intent;
    item def Agent_Outcome;

    item def AI_Memory_Request :> Vellis_Service_Request;
    item def AI_Memory_Response :> Vellis_Service_Response;

    item def Application_Interaction_Request :> Vellis_Service_Request;
    item def Application_Interaction_Response :> Vellis_Service_Response;

    item def Run_Automation_Request :> Vellis_Service_Request;
    item def Run_Automation_Response :> Vellis_Service_Response;

    item def Review_Activity_Request :> Vellis_Service_Request;
    item def Review_Activity_Response :> Vellis_Service_Response;

    item def Explore_Prior_Memory_Request :> Vellis_Service_Request {
        attribute revision : ScalarValues::Natural;
    }

    item def Explore_Prior_Memory_Response :> Vellis_Service_Response;

    item def Restore_Personal_Memory_Request :> Vellis_Service_Request {
        attribute revision : ScalarValues::Natural;
    }

    item def Restore_Personal_Memory_Response :> Vellis_Service_Response;

    port def Vellis_Client_Port {
        doc /* Directions are stated from the Vellis client perspective. */

        out item request : Vellis_Service_Request;
        in item response : Vellis_Service_Response;
    }

    part def Vellis_Client :> Software {
        port vellisService : Vellis_Client_Port;
    }

    part def External_AI_Agent :> Vellis_Client {
        doc /*
         * An AI agent, operating in an external AI application, that invokes
         * Vellis capabilities on behalf of the owner.
         */
    }
}
