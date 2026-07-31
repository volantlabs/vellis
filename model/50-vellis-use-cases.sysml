package VellisUseCases {
    private import VellisFoundation::*;
    private import VellisServiceContracts::*;
    private import VellisSystems::*;

    /*
     * Product-level use cases centered on owner value.
     *
     * Hosted applications and automations are part of the Vellis subject,
     * not external enterprise actors. The external AI agent is an actor
     * because it operates outside Vellis and invokes Vellis on the owner's
     * behalf.
     */

    use case def 'Use AI with persistent personal context' {
        subject system : Vellis_System {
            event occurrence receivesRequest;
            then event occurrence returnsResult;
        }

        actor owner : Vellis_Owner {
            event occurrence expressesIntent;
            then event occurrence receivesOutcome;
        }

        actor agent : External_AI_Agent {
            event occurrence receivesIntent;
            then event occurrence invokesVellis;
            then event occurrence receivesVellisResult;
            then event occurrence presentsOutcome;
        }

        objective {
            doc /*
             * The owner uses an external AI agent that accesses the owner's
             * durable Vellis memory to provide continuity, context, and
             * personalized assistance. Vellis retains provenance showing
             * that the agent acted within the owner's experience.
             */
        }

        message of Owner_Intent
            from owner.expressesIntent to agent.receivesIntent;

        then message of AI_Memory_Request
            from agent.invokesVellis to system.receivesRequest;

        then message of AI_Memory_Response
            from system.returnsResult to agent.receivesVellisResult;

        then message of Agent_Outcome
            from agent.presentsOutcome to owner.receivesOutcome;
    }

    use case def 'Use personal application' {
        subject system : Vellis_System {
            event occurrence receivesInteraction;
            then event occurrence presentsResponse;
        }

        actor owner : Vellis_Owner {
            event occurrence interacts;
            then event occurrence observesResponse;
        }

        objective {
            doc /*
             * The owner uses a Vellis-hosted GUI application that can apply
             * Vellis memory and other system capabilities without requiring
             * the owner to operate a separate application infrastructure.
             */
        }

        message of Application_Interaction_Request
            from owner.interacts to system.receivesInteraction;

        then message of Application_Interaction_Response
            from system.presentsResponse to owner.observesResponse;
    }

    use case def 'Run personal automation' {
        subject system : Vellis_System {
            event occurrence receivesRequest;
            then event occurrence presentsOutcome;
        }

        actor owner : Vellis_Owner {
            event occurrence requestsRun;
            then event occurrence observesOutcome;
        }

        objective {
            doc /*
             * The owner runs an owner-controlled automation that uses Vellis
             * capabilities and receives its outcome. Consequential activity
             * is attributable to the automation and the owning experience.
             */
        }

        message of Run_Automation_Request
            from owner.requestsRun to system.receivesRequest;

        then message of Run_Automation_Response
            from system.presentsOutcome to owner.observesOutcome;
    }

    use case def 'Review personal memory and activity' {
        subject system : Vellis_System {
            event occurrence receivesRequest;
            then event occurrence presentsHistory;
        }

        actor owner : Vellis_Owner {
            event occurrence requestsReview;
            then event occurrence reviewsHistory;
        }

        objective {
            doc /*
             * The owner reviews consequential activity performed directly,
             * by AI agents, by hosted applications, by automations, or by the
             * system, together with the effects on personal memory.
             */
        }

        message of Review_Activity_Request
            from owner.requestsReview to system.receivesRequest;

        then message of Review_Activity_Response
            from system.presentsHistory to owner.reviewsHistory;
    }

    use case def 'Explore prior personal memory' {
        subject system : Vellis_System {
            event occurrence receivesRequest;
            then event occurrence presentsHistoricalState;
        }

        actor owner : Vellis_Owner {
            event occurrence requestsHistoricalState;
            then event occurrence exploresHistoricalState;
        }

        objective {
            doc /*
             * The owner explores personal memory as it existed at a retained
             * prior revision without changing current memory.
             */
        }

        message of Explore_Prior_Memory_Request
            from owner.requestsHistoricalState to system.receivesRequest;

        then message of Explore_Prior_Memory_Response
            from system.presentsHistoricalState
            to owner.exploresHistoricalState;
    }

    use case def 'Restore prior personal memory' {
        subject system : Vellis_System {
            event occurrence receivesRequest;
            then event occurrence presentsOutcome;
        }

        actor owner : Vellis_Owner {
            event occurrence requestsRestore;
            then event occurrence observesOutcome;
        }

        objective {
            doc /*
             * The owner restores a retained historical memory state as the
             * basis of a new current revision while preserving all existing
             * history for later review.
             */
        }

        message of Restore_Personal_Memory_Request
            from owner.requestsRestore to system.receivesRequest;

        then message of Restore_Personal_Memory_Response
            from system.presentsOutcome to owner.observesOutcome;
    }
}
