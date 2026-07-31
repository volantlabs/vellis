package RTGUseCases {
    private import RTGDomain::*;
    private import VellisServiceContracts::*;
    private import VellisSystems::*;

    /*
     * Reusable black-box use cases for the RTG memory subsystem.
     * Internal engines, controllers, repositories, and action sequences are
     * intentionally excluded.
     */

    use case def 'Apply graph change' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * A requested graph change is committed completely when valid
             * against one coherent graph revision and active constraint
             * model, or the graph remains unchanged. The client receives the
             * authoritative outcome and resulting or unchanged revision.
             */
        }

        message of Apply_Graph_Change_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Apply_Graph_Change_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Query current memory' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The client receives a result evaluated against one coherent
             * current graph revision, and the result identifies that
             * revision.
             */
        }

        message of Query_Current_Memory_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Query_Current_Memory_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Query memory at revision' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The client receives a result evaluated against a requested
             * retained graph revision without changing current state.
             */
        }

        message of Query_Historical_Memory_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Query_Historical_Memory_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Inspect activity history' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The client receives retained activity records or projections
             * matching the requested owner-audit criteria.
             */
        }

        message of Inspect_Activity_History_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Inspect_Activity_History_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Restore prior graph state' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The state represented by a retained revision becomes the
             * basis of a new committed current revision. Existing history is
             * preserved rather than rewound or rewritten.
             */
        }

        message of Restore_Prior_State_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Restore_Prior_State_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Stage constraint model' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * One candidate successor to the active constraint model is
             * retained without changing the model governing ordinary graph
             * changes.
             */
        }

        message of Stage_Constraint_Model_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Constraint_Model_Operation_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Edit staged constraint model' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The staged candidate is changed without changing the active
             * model or ordinary graph validation.
             */
        }

        message of Edit_Staged_Constraint_Model_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Constraint_Model_Operation_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Assess staged constraint model' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The client receives the validity and activation impact of the
             * staged model assessed against one coherent graph revision.
             */
        }

        message of Assess_Staged_Constraint_Model_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Constraint_Model_Operation_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Activate staged constraint model' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * A valid staged model atomically becomes active together with
             * its complete validated activation effects, or graph state and
             * active-model selection remain unchanged.
             */
        }

        message of Activate_Staged_Constraint_Model_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Constraint_Model_Operation_Response
            from system.issuesResponse to client.receivesResponse;
    }

    use case def 'Discard staged constraint model' {
        subject system : RTG_System {
            event occurrence receivesRequest;
            then event occurrence issuesResponse;
        }

        actor client : RTG_Client {
            event occurrence issuesRequest;
            then event occurrence receivesResponse;
        }

        objective {
            doc /*
             * The staged candidate is removed without changing the active
             * model or the graph state governed by it.
             */
        }

        message of Discard_Staged_Constraint_Model_Request
            from client.issuesRequest to system.receivesRequest;

        then message of Constraint_Model_Operation_Response
            from system.issuesResponse to client.receivesResponse;
    }
}
