package RTGSystem {
    private import RTG::*;

    part def 'RTG Client' {
        doc /*
         * A person or system outside RTG that requests an outcome within a
         * scope already established by the owner. RTG operations do not create
         * or evaluate that authorization scope.
         */
    }

    part def 'MCP Client' :> 'RTG Client' {
        doc /*
         * A trusted, owner-configured agent client that discovers and invokes
         * the selected RTG tools within its pre-established scope.
         */
    }

    part def 'RTG System' {
        doc /*
         * The one cohesive semantic and transactional boundary. It owns graph,
         * definition, revision, and history state. Query, validation, history,
         * and recovery are capabilities, not independently existing subsystems.
         */
        item currentGraph : Graph;
        item activeDefinitions : 'Graph Definition Set';
        item definitionDelta [0..1] : 'Definition Delta';
        attribute currentRevision : 'Revision Number';
        item stateChanges : 'State Change Ledger';
        item activities : 'Activity Ledger';

        perform action definitionSummary : rtg_definition_summary;
        perform action definitionInspect : rtg_definition_inspect;
        perform action retrieveDefinitionDelta : rtg_definition_delta;
        perform action graphQuery : rtg_query;
        perform action graphChange : rtg_change;
        perform action setDefinitionDelta : rtg_set_definition_delta;
        perform action activateDefinitionDelta : rtg_activate_definition_delta;
        perform action discardDefinitionDelta : rtg_discard_definition_delta;
        perform action checkConformance : rtg_check;
        perform action inspectHistory : rtg_history;
    }

    /* Black-box owner-visible use-case landscape. */

    use case def 'Discover active graph definitions' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: none for the shallow summary, followed by a non-empty
             * unique selection of anchor type keys for focused inspection.
             * Success: return the complete shallow anchor vocabulary and, for
             * each later selection, its complete relevant data, link, endpoint,
             * property, and multiplicity meaning at the current evaluated revision.
             * The summary reports whether a definition delta currently exists.
             * A summary that cannot be returned completely returns no summaries.
             * Unknown, duplicate, or incompletely answerable selections
             * return findings and no partial details. Canonical state and
             * revision never change. One observational activity record for the
             * completed read, rejection, or failure is appended after its
             * outcome is determined.
             * Evidence: a client with no prior graph knowledge can construct a
             * valid bounded current query or proposed graph change.
             */
        }
    }

    use case def 'Query graph' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: named anchor and directly associated-data endpoint groups,
             * optional known anchor UUIDs, required typed directed links with
             * optional known link UUIDs, associated-data value conditions, a
             * return shape, a positive maximum row count,
             * and optionally exactly one revision or time selector. Success:
             * return the complete shaped named bindings and evaluated revision.
             * Refusal or failure: return findings for unknown or incompatible
             * names, types, identities, properties, projections, history
             * targets, a result that exceeds the caller's bound, or a result the
             * system cannot return completely; return no partial
             * rows. Canonical state and revision never change. One observational
             * activity record for the completed read, rejection, or failure is
             * appended after its outcome is determined. Historical evaluation
             * requires caller-supplied vocabulary known to be valid at the
             * selected revision; current-only definition discovery does not
             * discover retired vocabulary. Evidence: current and historical
             * evaluation preserve identical query meaning.
             */
        }
    }

    use case def 'Apply graph change' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: complete-object anchor, associated-data, and link upserts
             * plus explicit UUID removals. Success: validate the complete
             * resulting graph and commit it once with one new revision and
             * contiguous transition record. Direct associations change only
             * through associated-data anchor references; no implicit cascade
             * occurs. An effective no-op is accepted without a revision.
             * Refusal or failure: report why it was not applied. State effect:
             * success changes graph state, revision, and canonical history while
             * leaving active definitions and the delta unchanged; rejection or
             * failure changes no canonical state or revision. Evidence: replay reconstructs the
             * same accepted graph transition without activity history.
             */
        }
    }

    use case def 'Assess graph conformance' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: none; assess the current graph against the current active
             * definitions. Success: return a graph-conformance report at the
             * current revision. Refusal or failure is observable and produces no
             * successful validation report. Canonical state and revision never change;
             * one observational validation, rejection, or failure record is
             * appended after the outcome is determined. Evidence: findings identify
             * implicated definitions and graph objects when available.
             */
        }
    }

    use case def 'Create or edit definition delta' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: one complete proposed next definition set. Success: create
             * or replace the sole delta, return it with a current assessment,
             * and advance one revision when its canonical content changed. A
             * proposal may retain description or consistency findings while it
             * is edited. With no delta, a proposal equivalent to the active set
             * is an accepted no-op. With a delta, re-staging that same proposal
             * is an accepted no-op; attempting to use the active set as an
             * implicit discard is rejected in favor of the discard operation.
             * Every effective no-op advances nothing. Refusal or failure
             * preserves prior canonical state and returns no proposal or success
             * metadata; the client may retrieve the unchanged current delta
             * separately. Active definitions and graph never change.
             * Evidence: whole-delta retrieval and replay show exactly the
             * accepted proposal and revision while active meaning is unchanged.
             */
        }
    }

    use case def 'Review definition delta' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: none; inspect the current in-flight delta. Success: return
             * normal absence, or the complete proposal and a current assessment of its
             * description presence, internal consistency, and current-graph impact.
             * Failure is observable. Canonical state and revision never change;
             * one observational read or failure record is appended after the
             * outcome is determined. Evidence: a client can compare the whole
             * proposal with focused active-definition views without a server-side diff.
             */
        }
    }

    use case def 'Activate definition delta' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: none; operate on the sole current delta. Success: when all
             * descriptions are non-empty, its definitions are internally valid, and the graph
             * already conforms, replace the active set, clear the
             * delta, and commit one revision. Refusal or failure preserves graph,
             * active set, delta, revision, and canonical history. Evidence: replay
             * reconstructs the singular accepted activation.
             */
        }
    }

    use case def 'Discard definition delta' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: none; operate on the sole current delta. Success: clear it and
             * commit one revision. Refusal reports no delta; failure preserves
             * it. Graph and active definitions never change. Evidence: whole-
             * delta retrieval and replay show absence at the resulting revision.
             */
        }
    }

    use case def 'Inspect state-change history' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: an optional chronological range and positive maximum.
             * Success: return one owner-facing entry for every matching canonical
             * record in ledger order, with present chronological bounds included.
             * Each entry carries time, provenance, revision, transition kind when
             * applicable, and a semantic summary, but no replay payload or full
             * canonical state. A range exceeding the bound is rejected without
             * partial entries. Canonical state and revision never change; one
             * observational read, rejection, or failure record is appended after
             * the outcome is determined. Evidence: every returned entry represents
             * one canonical record in the selected inclusive interval and order.
             */
        }
    }

    use case def 'Inspect activity history' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: an optional chronological range and positive maximum.
             * Success: return one owner-facing entry for every matching record
             * in ledger order, with present chronological bounds included:
             * permitted reads, validations, rejections, failures, snapshots,
             * provenance, and summaries. The selected interval is evaluated
             * before the record of this read is appended, so it never includes
             * itself. An over-broad range returns no partial entries, nor does a
             * request the system cannot return completely. Canonical state and
             * revision never change; one observational read, rejection, or failure
             * record is appended after the outcome is determined. Evidence: changing
             * activity retention cannot change replayed canonical state.
             */
        }
    }

    use case def 'Manage activity retention' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: an owner-selected retention decision over observational
             * activity records. Success: retain or remove only the selected
             * activity records. Refusal or failure preserves every preexisting
             * activity record, while the failed attempt itself may append one
             * failure observation after its outcome is determined. Canonical
             * graph, definitions, delta, revision, and
             * state-change history never change. Evidence: replay before and
             * after an accepted retention decision reconstructs equivalent state.
             */
        }
    }

    use case def 'Reconstruct canonical state' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: exactly one initial record or complete snapshot and an
             * optional contiguous later ledger tail. Success: reconstruct
             * equivalent graph, active definitions, optional delta, and
             * revision. A gap, duplicate, reorder, incompatibility, or invalid
             * transition is rejected without partial state. Live canonical state
             * and revision never change; one observational validation, rejection,
             * or failure record is appended after the outcome is determined.
             * Evidence: the accepted result is canonically equivalent to direct
             * state at its reconstructed revision.
             */
        }
    }

    use case def 'Create canonical snapshot' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: current canonical state. Success: produce a self-contained
             * snapshot of graph, active definitions, optional delta, and total
             * revision. Refusal or failure is observable. State effect: no
             * canonical state or revision change; one observational snapshot,
             * rejection, or failure record is appended after the outcome is
             * determined. Evidence: the snapshot initializes an
             * equivalent fresh RTG.
             */
        }
    }

    use case def 'Initialize fresh RTG' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        in item initialDefinitions : 'Graph Definition Set';
        objective {
            doc /*
             * Input: one internally valid initial definition set, supplied only
             * for an RTG with no established canonical state. Success: establish
             * revision 0 with an empty graph, exactly those active definitions,
             * no definition delta, one initial-state record containing that
             * state, no transition records, and an empty activity ledger.
             * Refusal or failure establishes no partial canonical or activity
             * state. Evidence: direct state, the initial record, and replay all
             * agree on the same revision-0 state.
             */
        }
    }

    use case def 'Initialize fresh RTG from snapshot' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: a complete snapshot and optional contiguous later ledger
             * tail for an RTG with no established canonical state. Success:
             * establish the reconstructed graph, definitions, optional delta,
             * and captured or replayed revision without inventing a revision.
             * No blank or recommended fresh-start definitions are overlaid.
             * Begin the fresh RTG's canonical history with one initial record
             * containing that reconstructed state; do not claim omitted earlier
             * transitions. Refusal or failure establishes no partial canonical
             * state. Evidence: current query and replay agree with the supplied
             * snapshot and accepted tail at the established revision.
             */
        }
    }

    use case def 'Restore historical state' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: a committed historical revision. Success: when no delta
             * is in flight, commit its graph and active definitions with no
             * delta as one new revision. Refusal or failure preserves all
             * current canonical state. Earlier canonical history is never rewritten. Evidence: the
             * new current state equals the selected historical graph and active
             * definitions while the prior ledger prefix remains unchanged.
             */
        }
    }

    use case def 'Recover predecessor RTG graph' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            doc /*
             * Input: predecessor RTG meaning and optional definitions. Success:
             * validate and commit preserved graph meaning, supplied or current
             * active definitions, no delta, and one new revision. A predecessor
             * anchor without a display name receives the deterministic synthetic
             * display name defined by the recovery candidate. Refusal or
             * failure preserves all current canonical state. Recovery representation and
             * interchange mechanism remain open. Evidence: current query and
             * replay preserve the accepted predecessor RTG distinctions.
             */
        }
    }

    /* Selected external MCP tool contract. Each operation uses typed objects. */

    action def rtg_definition_summary {
        out item result : 'Definition Summary Result';
        doc /* Call first: discover every currently active anchor type and description. */
    }

    action def rtg_definition_inspect {
        in item request : 'Definition Inspection Request';
        out item result : 'Definition Inspection Result';
        bind result.request = request;
        doc /* Call after summary: inspect complete active neighborhoods for selected anchors. */
    }

    action def rtg_definition_delta {
        out item result : 'Definition Delta Result';
        doc /* Retrieve the complete sole proposal and current assessment, or normal absence. */
    }

    action def rtg_query {
        in item query : 'Graph Query';
        out item result : 'Graph Query Result';
        bind result.query = query;
        doc /* Query current or selected historical graph meaning with one complete bound. */
    }

    action def rtg_change {
        in item change : 'Graph Change';
        out item result : 'Revisioned Outcome';
        doc /* Validate explicit upserts and removals, then atomically commit an effective change. */
    }

    action def rtg_set_definition_delta {
        in item request : 'Set Definition Delta Request';
        out item result : 'Definition Delta Result';
        doc /* Create or replace the sole complete proposal and return its current assessment. */
    }

    action def rtg_activate_definition_delta {
        out item result : 'Revisioned Outcome';
        doc /* Activate the valid sole proposal atomically or preserve all current canonical state. */
    }

    action def rtg_discard_definition_delta {
        out item result : 'Revisioned Outcome';
        doc /* Discard the sole proposal atomically or report normal absence. */
    }

    action def rtg_check {
        out item result : 'Validation Report';
        doc /* Assess complete current-graph conformance against active definitions without mutation. */
    }

    action def rtg_history {
        in item query : 'History Query';
        out item result : 'History Result';
        bind result.query = query;
        doc /* Return one complete bounded canonical or activity history-entry interval. */
    }

    /*
     * Tool actions depend on the black-box behavior they expose. These abstract
     * trace relationships express change impact, not execution, control, or an
     * internal action decomposition.
     */
    dependency summaryToolBehavior
        from rtg_definition_summary to 'Discover active graph definitions';
    dependency inspectionToolBehavior
        from rtg_definition_inspect to 'Discover active graph definitions';
    dependency deltaReadToolBehavior
        from rtg_definition_delta to 'Review definition delta';
    dependency queryToolBehavior
        from rtg_query to 'Query graph';
    dependency changeToolBehavior
        from rtg_change to 'Apply graph change';
    dependency setDeltaToolBehavior
        from rtg_set_definition_delta to 'Create or edit definition delta';
    dependency activateDeltaToolBehavior
        from rtg_activate_definition_delta to 'Activate definition delta';
    dependency discardDeltaToolBehavior
        from rtg_discard_definition_delta to 'Discard definition delta';
    dependency checkToolBehavior
        from rtg_check to 'Assess graph conformance';
    dependency historyToolBehavior
        from rtg_history to 'Inspect state-change history', 'Inspect activity history';

}
