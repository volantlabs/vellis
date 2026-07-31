package RTGDomain {
    /*
     * Minimal domain concepts required by the current RTG use cases and
     * requirements. The canonical user-graph structure is explicit because it
     * is a compatibility boundary. Detailed schema, query, ledger-storage, and
     * persistence representations remain intentionally deferred.
     */

    // -----------------------------------------------------------------
    // Graph and constraint-model concepts
    // -----------------------------------------------------------------

    attribute def RTG_UUID :> ScalarValues::String {
        doc /* Stable UUID text preserved across storage and realization changes. */
    }

    attribute def JSON_Object {
        doc /*
         * A JSON-serializable object value. Its physical encoding and storage
         * are realization choices; object-valued content and JSON value kinds
         * are part of the portability boundary.
         */
    }

    attribute def RTG_System_Metadata :> JSON_Object {
        attribute live [0..1] : ScalarValues::Boolean default = true;

        doc /*
         * JSON-safe system metadata preserved on every graph object. Missing
         * live normalizes to true; supplied live is Boolean. Other keys are
         * preserved without meaning assigned by the base graph.
         */
    }

    abstract item def RTG_Object {
        doc /*
         * An identity-bearing canonical record in the RTG user graph. UUIDs
         * are globally unique across anchors, associated data objects, and
         * links. Type keys share one global namespace across those kinds.
         */

        attribute uuid : RTG_UUID;
        attribute type : ScalarValues::String;
        attribute system : RTG_System_Metadata;
    }

    abstract item def RTG_Link_Endpoint :> RTG_Object {
        doc /* An RTG object kind that a directed link may address. */
    }

    item def RTG_Anchor :> RTG_Link_Endpoint {
        doc /*
         * A stable typed ontological identity. It is independently
         * addressable even when its descriptive facts change.
         */

        attribute displayName [0..1] : ScalarValues::String;
    }

    item def RTG_Associated_Data_Object :> RTG_Link_Endpoint {
        doc /*
         * A typed JSON fact group directly associated with one or more
         * anchors. It has its own UUID but is not a substitute for the stable
         * identity of an anchor.
         */

        attribute properties : JSON_Object;
    }

    item def RTG_Link :> RTG_Object {
        doc /*
         * An identity-bearing typed directed relationship. Source and target
         * UUIDs resolve to anchors or associated data objects, never links.
         */

        attribute sourceUuid : RTG_UUID;
        attribute targetUuid : RTG_UUID;
    }

    attribute def RTG_Anchor_Data_Association {
        doc /*
         * One direct, identity-free anchor-to-data association. This is
         * canonical graph state, not a link or a fourth graph-object kind.
         */

        attribute anchorUuid : RTG_UUID;
        attribute dataUuid : RTG_UUID;
    }

    item def Constraint_Model {
        doc /*
         * A versioned model that governs the validity of RTG Graph changes.
         * It governs user-graph records but is not itself assumed to be an
         * anchor, associated data object, or link. Its detailed schema and
         * rule structure are deferred.
         */

        attribute version : ScalarValues::String;
    }

    item def RTG_Graph {
        doc /*
         * Canonical user graph state owned by an RTG System. Derived indexes,
         * snapshots, tables, documents, and graph-database projections are
         * realization choices rather than additional domain objects.
         */

        item anchors [*] : RTG_Anchor;
        item dataObjects [*] : RTG_Associated_Data_Object;
        item links [*] : RTG_Link;
        attribute anchorDataAssociations [*] :
            RTG_Anchor_Data_Association;
    }

    // -----------------------------------------------------------------
    // Operations and results
    // -----------------------------------------------------------------

    item def Graph_Change {
        doc /*
         * A requested or committed semantic delta over anchors, associated
         * data objects, links, or direct anchor-data associations. Atomic
         * operation and transport-envelope details are deferred.
         */
    }

    item def Graph_Change_Result {
        doc /*
         * The authoritative committed, rejected, or failed outcome of a
         * graph-change request.
         */
    }

    item def Memory_Query {
        doc /* A request for information derived from an RTG Graph revision. */
    }

    item def Memory_Query_Result {
        doc /*
         * A memory-query result associated with the graph revision against
         * which it was evaluated.
         */

        attribute evaluatedRevision : ScalarValues::Natural;
    }

    item def Constraint_Model_Change {
        doc /* A semantic change to a staged constraint model. */
    }

    item def Constraint_Model_Assessment {
        doc /*
         * The result of validating a staged constraint model and assessing
         * the effects of activation against a coherent graph revision.
         */
    }

    item def Activity_History_Query {
        doc /* A request to inspect selected retained RTG activity. */
    }

    item def Activity_History_Result {
        doc /* Activity records or projections matching an audit request. */
    }

    // -----------------------------------------------------------------
    // Activity provenance and durable ledger
    // -----------------------------------------------------------------

    enum def Activity_Initiator_Kind {
        owner;
        agent;
        application;
        automation;
        system;
    }

    item def Activity_Provenance {
        doc /*
         * Minimal provenance needed to distinguish owner actions from
         * actions performed by agents, applications, automations, or Vellis
         * itself, without introducing enterprise identity or RBAC semantics.
         */

        attribute initiatorKind : Activity_Initiator_Kind;
        attribute initiatorId : ScalarValues::String;
        attribute interactionId : ScalarValues::String;
        attribute correlationId : ScalarValues::String;
    }

    abstract item def RTG_Activity_Record {
        doc /* A durable record of activity observed by the RTG System. */

        attribute activityId : ScalarValues::String;
        attribute sequenceNumber : ScalarValues::Natural;
        item provenance : Activity_Provenance;
    }

    abstract item def RTG_State_Change_Record :> RTG_Activity_Record {
        doc /*
         * A committed RTG state transition required to reconstruct the
         * system's historical state.
         */

        attribute resultingRevision : ScalarValues::Natural;
    }

    abstract item def RTG_Observation_Record :> RTG_Activity_Record {
        doc /*
         * A non-state-changing activity retained for audit, provenance, or
         * diagnostics.
         */
    }

    item def Graph_Change_Record :> RTG_State_Change_Record {
        item committedChange : Graph_Change;
    }

    item def Constraint_Model_Change_Record :> RTG_State_Change_Record {
        item committedChange : Constraint_Model_Change;
    }

    item def Restore_State_Record :> RTG_State_Change_Record {
        attribute restoredFromRevision : ScalarValues::Natural;
    }

    item def Query_Activity_Record :> RTG_Observation_Record {
        item query : Memory_Query;
        attribute evaluatedRevision : ScalarValues::Natural;
    }

    item def Rejected_Change_Record :> RTG_Observation_Record {
        item requestedChange : Graph_Change;
    }

    item def RTG_Activity_Ledger {
        doc /*
         * The durable logical history of RTG activity. Every committed state
         * transition is retained. Selected non-state-changing activity may
         * also be retained for owner review and audit.
         */

        item records [*] : RTG_Activity_Record;
    }
}
