package RTG {
    /*
     * Language-neutral RTG graph, definition, query, validation, revision,
     * snapshot, and history vocabulary. Physical storage, serialization,
     * executable query syntax, and recovery mechanisms remain open.
     */

    attribute def 'Graph UUID' :> ScalarValues::String {
        doc /* The stable UUID of one identity-bearing graph object. */
    }

    attribute def 'Type Key' :> ScalarValues::String {
        doc /* A non-empty key in the single namespace shared by all RTG types. */
    }

    attribute def 'Query Name' :> ScalarValues::String {
        doc /* A non-empty query-local name for one group, link condition, data condition, or projection. */
    }

    attribute def 'Revision Number' :> ScalarValues::Natural {
        doc /* A position in the monotonically increasing total revision order. */
    }

    attribute def 'Recorded Time' {
        doc /* A language-neutral chronological instant; representation remains open. */
    }

    attribute def 'JSON Value' {
        doc /*
         * Any JSON value preserved without loss of kind or nested content.
         * Semantic equality is JSON-kind-sensitive. Numbers compare by exact
         * mathematical value, strings exactly, arrays recursively in order, and
         * objects recursively without member-order significance. A missing
         * property remains distinct from a present JSON null value.
         */
    }

    attribute def 'JSON Object' :> 'JSON Value' {
        doc /* An object-valued collection of named JSON values. */
    }

    attribute def 'Value Shape' {
        attribute minimumSize [0..1] : ScalarValues::Natural;
        attribute maximumSize [0..1] : ScalarValues::Natural;
        doc /*
         * A closed size condition for a string, array, or object value. Size means
         * characters, elements, or members respectively. At least one bound is
         * present, and a present maximum is not less than a present minimum.
         * Other JSON kinds cannot carry a value-shape condition.
         */
    }

    attribute def 'String Pattern' {
        attribute expression : ScalarValues::String;
        doc /*
         * A Google RE2 regular expression evaluated over a Unicode string with
         * whole-string FullMatch semantics. RE2-supported inline flags are part
         * of the expression; there is no separate flags value. An expression
         * that RE2 rejects, including lookaround or a backreference, is invalid.
         * The selected language and semantics do not select a runtime engine.
         */
    }

    attribute def 'Value Range' {
        attribute lowerBound [0..1] : 'JSON Value';
        attribute upperBound [0..1] : 'JSON Value';
        attribute permittedValues [*] : 'JSON Value';
        doc /*
         * A closed permitted-value condition. At least one bound or permitted
         * value is present. Bounds are lossless numberValue values with a lower
         * not greater than an upper; both bounds are inclusive.
         * Permitted values have the governed property's JSON kind and are unique
         * by lossless JSON equality. When bounds and permitted values coexist, a
         * value must satisfy both.
         */
    }

    enum def 'JSON Kind' {
        enum nullValue;
        enum booleanValue;
        enum numberValue;
        enum stringValue;
        enum arrayValue;
        enum objectValue;
    }

    enum def 'Operation Status' {
        enum accepted;
        enum rejected;
        enum failed;
        doc /*
         * Accepted means the invoked domain operation completed, including an
         * accepted no-op. Rejected means a well-formed semantic request was not
         * accepted. Failed means an invoked operation did not complete but could
         * safely report that status, and its promised failure non-effects hold.
         * Input that cannot form
         * the tool's typed domain object is malformed before an RTG operation
         * outcome exists.
         */
    }

    enum def 'Validation Scope' {
        enum graphConformance;
        enum definitionDelta;
    }

    enum def 'Property Comparison' {
        enum equal;
        enum notEqual;
        enum lessThan;
        enum lessThanOrEqual;
        enum greaterThan;
        enum greaterThanOrEqual;
    }

    enum def 'History Kind' {
        enum canonical;
        enum activity;
    }

    enum def 'Transition Kind' {
        enum graphMutation;
        enum definitionDeltaChange;
        enum definitionActivation;
        enum historicalRestoration;
    }

    enum def 'Recovery Finding Disposition' {
        enum preserved;
        enum simplified;
        enum omitted;
        enum blocking;
    }

    enum def 'Definition Delta Disposition' {
        enum unchanged;
        enum present;
        enum absent;
    }

    enum def 'Link End' {
        enum source;
        enum target;
    }

    enum def 'Direct Association End' {
        enum anchor;
        enum associatedData;
    }

    attribute def 'System Metadata' :> 'JSON Object' {
        attribute live : ScalarValues::Boolean default = true;

        doc /*
         * Canonical metadata has a Boolean live value. V1 translation normalizes
         * a missing source value to true and preserves other JSON values.
         */
    }

    abstract item def 'Graph Object' {
        doc /*
         * An identity-bearing RTG object. UUIDs are globally unique across
         * object kinds. A type key never changes an object's kind.
         */

        attribute uuid : 'Graph UUID';
        attribute typeKey : 'Type Key';
        attribute systemMetadata : 'System Metadata';
    }

    abstract item def 'Link Endpoint' :> 'Graph Object';

    item def Anchor :> 'Link Endpoint' {
        doc /*
         * A stable, independently identifiable concept. Its required non-empty
         * display name is an editable human and agent convenience; UUID remains
         * identity and type key remains ontology.
         */
        attribute displayName : ScalarValues::String;
    }

    item def 'Associated Data Object' :> 'Link Endpoint' {
        doc /*
         * An identity-bearing typed fact group grounded by one or more
         * anchors. The many-to-many references are identity-free direct
         * associations, not links or graph objects.
         */

        ref item anchors [1..*] : Anchor;
        attribute properties : 'JSON Object';
    }

    item def Link :> 'Graph Object' {
        doc /*
         * An identity-bearing typed directed relationship. Source and target
         * are independently existing anchors or associated data objects;
         * links are never endpoints.
         */

        ref item source : 'Link Endpoint';
        ref item target : 'Link Endpoint';
    }

    item def Graph {
        doc /*
         * Canonical graph state. Every direct association and link endpoint
         * resolves to an object owned by this graph. Semantic equality compares
         * graph-object UUID, kind, type key, display name when applicable,
         * metadata, properties, direct anchor associations, and directed link
         * endpoints. Owned graph-object collections and direct-association sets
         * are unordered; reordering them does not change graph meaning.
         */

        item anchors [*] : Anchor;
        item associatedData [*] : 'Associated Data Object';
        item links [*] : Link;
    }

    /* Definition and constraint governance. */

    abstract item def 'Definition Object' {
        attribute description [0..1] : ScalarValues::String;
        doc /*
         * Governance state that is not an RTG graph object. Active definitions
         * require one non-empty owner-readable description; proposed definitions
         * may temporarily omit it and report an activation-blocking finding.
         * Automatic assessment establishes presence and non-emptiness; the
         * owner judges whether the wording communicates the intended meaning.
         * Descriptions and all structured rules participate in semantic
         * equality. Definition collections and referenced type sets are
         * unordered unless explicitly declared ordered.
         */
    }

    abstract item def 'Type Definition' :> 'Definition Object' {
        attribute typeKey : 'Type Key';
    }

    abstract item def 'Endpoint Type Definition' :> 'Type Definition';

    item def 'Anchor Type Definition' :> 'Endpoint Type Definition';

    item def 'Associated Data Type Definition' :> 'Endpoint Type Definition' {
        item propertyConstraints [*] : 'Property Constraint';
        ref item permittedAnchorTypes [1..*] : 'Anchor Type Definition';
        doc /*
         * Governs the complete allowed property vocabulary and the anchor types
         * that may ground this associated-data type. A required property must be
         * present; an optional property may be absent; an undeclared property is
         * invalid for an object of this type.
         */
    }

    item def 'Link Type Definition' :> 'Type Definition' {
        item endpointConstraint : 'Endpoint Constraint';
    }

    item def 'Property Constraint' :> 'Definition Object' {
        doc /*
         * Governs one associated-data property with requiredness, one JSON kind,
         * and optional closed size, permitted-value, and string-pattern
         * conditions. A pattern is valid only for stringValue and every listed
         * permitted string must also match it. Present conditions apply
         * conjunctively; no satisfiability proof between pattern and size is
         * required. A condition incompatible with the selected JSON kind is
         * invalid. No serialized schema or general constraint language is selected.
         * The property name is non-empty and unique within its owning
         * associated-data type definition. Its natural identity is that owning
         * type key plus property name. Pattern expression text participates
         * exactly in equality; equivalent expressions are not normalized.
         */
        attribute propertyName : ScalarValues::String;
        attribute required : ScalarValues::Boolean;
        attribute jsonKind : 'JSON Kind';
        attribute valueShape [0..1] : 'Value Shape';
        attribute range [0..1] : 'Value Range';
        attribute pattern [0..1] : 'String Pattern';
    }

    item def 'Endpoint Constraint' :> 'Definition Object' {
        doc /* States permitted source and target endpoint types. */
        ref item permittedSourceTypes [1..*] : 'Endpoint Type Definition';
        ref item permittedTargetTypes [1..*] : 'Endpoint Type Definition';
    }

    abstract item def 'Relationship Constraint' :> 'Definition Object';

    abstract item def 'Multiplicity Constraint' :> 'Relationship Constraint' {
        doc /*
         * The lower bound is required. An absent upper bound is unbounded;
         * otherwise the upper bound is not less than the lower bound.
         */
        attribute lowerBound : ScalarValues::Natural;
        attribute upperBound [0..1] : ScalarValues::Natural;
    }

    item def 'Link Multiplicity Constraint' :> 'Multiplicity Constraint' {
        doc /*
         * Counts links of one type at a selected source or target end for
         * constrained endpoint types and permitted opposite endpoint types. Its
         * natural identity is the link type key, constrained end, and the two
         * unordered participating type-key sets.
         */
        ref item linkType : 'Link Type Definition';
        attribute constrainedEnd : 'Link End';
        ref item constrainedEndpointTypes [1..*] : 'Endpoint Type Definition';
        ref item oppositeEndpointTypes [1..*] : 'Endpoint Type Definition';
    }

    item def 'Direct Association Multiplicity Constraint' :> 'Multiplicity Constraint' {
        doc /*
         * Counts identity-free anchor/data associations at the selected end
         * between the stated anchor and associated-data type populations. Its
         * natural identity is the constrained end and the two unordered
         * participating type-key sets.
         */
        attribute constrainedEnd : 'Direct Association End';
        ref item anchorTypes [1..*] : 'Anchor Type Definition';
        ref item associatedDataTypes [1..*] : 'Associated Data Type Definition';
    }

    item def 'Graph Definition Set' {
        doc /*
         * The complete active graph vocabulary and constraints. Type keys are
         * unique in one namespace and every reference resolves within the set.
         * A type definition's natural identity is its type key; its definition
         * kind is semantic content. Endpoint constraints are identified by their
         * owning link type. Property and multiplicity constraints use their
         * stated natural identities. Duplicate natural identities and duplicate
         * members of any set are invalid. Distinct overlapping multiplicity
         * constraints apply conjunctively. Unordered definition and referenced
         * type collections compare without order significance.
         */
        item anchorTypes [*] : 'Anchor Type Definition';
        item associatedDataTypes [*] : 'Associated Data Type Definition';
        item linkTypes [*] : 'Link Type Definition';
        item relationshipConstraints [*] : 'Relationship Constraint';
    }

    item def 'Definition Delta' {
        doc /*
         * The sole prospective next definition set. The difference from the
         * active set is the in-flight change; diff representation remains open.
         * When present in canonical state, the proposed set is semantically
         * different from the active set by canonical semantic equality.
         */
        item proposedDefinitions : 'Graph Definition Set';
    }

    /* Agent-oriented definition discovery. */

    item def 'Anchor Type Summary' {
        ref item definition : 'Anchor Type Definition';
        doc /* Projects the authoritative type key and description without copying their authority. */
    }

    item def 'Definition Inspection Request' {
        attribute anchorTypeKeys [1..*] : 'Type Key';
        item historicalSelection [0..1] : 'Historical State Selection';
        doc /*
         * Selects a non-empty unique set of anchor keys from the definitions
         * active at the current state when selection is absent, or at exactly
         * one selected revision or time when present.
         */
    }

    item def 'Anchor Definition Detail' {
        ref item anchorType : 'Anchor Type Definition';
        ref item associatedDataTypes [*] : 'Associated Data Type Definition';
        ref item linkTypes [*] : 'Link Type Definition';
        ref item relationshipConstraints [*] : 'Relationship Constraint';
        doc /*
         * A complete active-definition neighborhood for one selected anchor.
         * Associated-data property and link endpoint constraints are carried by
         * their referenced type definitions. Link roles include those involving
         * the anchor or its permitted associated-data types. Unrelated
         * definitions are omitted.
         */
    }

    item def 'Set Definition Delta Request' {
        item proposedDefinitions : 'Graph Definition Set';
    }

    /* Simple semantic query vocabulary. */

    item def 'Anchor UUID Filter' {
        attribute uuids [1..*] : 'Graph UUID';
        doc /* Narrows one anchor group to a non-empty set of unique known anchor identities. */
    }

    item def 'Link UUID Filter' {
        attribute uuids [1..*] : 'Graph UUID';
        doc /* Narrows one required link to a non-empty set of unique known link identities. */
    }

    abstract item def 'Endpoint Group' {
        attribute name : 'Query Name';
        doc /* A named candidate set whose members may participate as link endpoints. */
    }

    item def 'Anchor Group' :> 'Endpoint Group' {
        attribute anchorType : 'Type Key';
        item uuidFilter [0..1] : 'Anchor UUID Filter';
        doc /*
         * A named anchor candidate set of exactly one active anchor type. An
         * absent UUID filter considers all anchors of that type.
         */
    }

    item def 'Required Link' {
        attribute name : 'Query Name';
        ref item sourceGroup : 'Endpoint Group';
        ref item targetGroup : 'Endpoint Group';
        attribute linkType : 'Type Key';
        item uuidFilter [0..1] : 'Link UUID Filter';
        doc /*
         * Requires a directed link of one active link type from a source-group
         * candidate to a target-group candidate. Groups may select anchors or
         * directly associated data. An optional UUID filter restricts the
         * matching identity-bearing links.
         */
    }

    item def 'Data Property Condition' {
        doc /*
         * A structured comparison against one present property value. A missing
         * property does not satisfy the condition. The active
         * property definition remains authoritative for JSON kind, shape,
         * permitted range, and stored-value pattern validation. Equal and
         * notEqual compare lossless JSON values;
         * ordered comparisons are valid only for numberValue properties. Other
         * combinations are rejected.
         */
        attribute propertyName : ScalarValues::String;
        attribute comparison : 'Property Comparison';
        attribute expectedValue : 'JSON Value';
    }

    item def 'Associated Data Condition' :> 'Endpoint Group' {
        ref item anchorGroup : 'Anchor Group';
        attribute associatedDataType : 'Type Key';
        item propertyConditions [*] : 'Data Property Condition';
        doc /*
         * Selects directly associated data of the active type that satisfies
         * every stated property condition. With no property conditions, the
         * condition expresses existence of directly associated data of that
         * type. Its selected objects may participate as required-link endpoints.
         */
    }

    abstract item def 'Return Projection' {
        attribute name : 'Query Name';
    }

    item def 'Anchor Projection' :> 'Return Projection' {
        ref item anchorGroup : 'Anchor Group';
    }

    item def 'Link Projection' :> 'Return Projection' {
        ref item requiredLink : 'Required Link';
    }

    item def 'Associated Data Projection' :> 'Return Projection' {
        ref item dataCondition : 'Associated Data Condition';
    }

    item def 'Data Property Projection' :> 'Return Projection' {
        ref item dataCondition : 'Associated Data Condition';
        attribute propertyName : ScalarValues::String;
    }

    item def 'Return Shape' {
        item projections [1..*] : 'Return Projection';
        doc /*
         * Selects named anchor, link, associated-data, and property bindings.
         * Every projection references a selector owned by its graph query, and
         * every projection name is unique within that query.
         * Aggregation, sorting, pagination, traversal, and computed expressions
         * are outside this query model.
         */
    }

    item def 'Graph Query' {
        item anchorGroups [1..*] : 'Anchor Group';
        item requiredLinks [*] : 'Required Link';
        item dataConditions [*] : 'Associated Data Condition';
        item returnShape : 'Return Shape';
        item historicalSelection [0..1] : 'Historical State Selection';
        attribute maximumRows : ScalarValues::Positive;
        doc /*
         * Named anchor selection, required-link restriction, associated-data
         * filtering, and projection define meaning, not evaluation order. All
         * group, link-condition, data-condition, and projection names are
         * unique within the query. Every reference resolves to an element owned
         * by the same query. An absent historical selection evaluates current
         * state; a present revision or time selection evaluates the resolved
         * historical state with identical query meaning. The caller may discover
         * the definitions active at that selected state and reuse its exact
         * evaluated revision for this query. The positive maximum bounds a
         * complete result rather than requesting a page.
         */
    }

    item def 'Anchor Binding' {
        ref item projection : 'Anchor Projection';
        ref item anchor : Anchor;
    }

    item def 'Link Binding' {
        ref item projection : 'Link Projection';
        ref item link : Link;
    }

    item def 'Associated Data Binding' {
        ref item projection : 'Associated Data Projection';
        ref item associatedData : 'Associated Data Object';
    }

    item def 'Returned Property' {
        ref item projection : 'Data Property Projection';
        attribute value [0..1] : 'JSON Value';
        doc /* Absence means the projected optional property is missing; present null remains JSON null. */
    }

    item def 'Graph Query Row' {
        item anchors [*] : 'Anchor Binding';
        item links [*] : 'Link Binding';
        item associatedData [*] : 'Associated Data Binding';
        item properties [*] : 'Returned Property';
        doc /*
         * One jointly satisfying assignment of every selector needed by the
         * return shape. The row contains exactly one binding for each projection
         * and no unrequested binding. Matching objects that are not projected do
         * not appear. Rows with identical projected bindings and property
         * presence or values are one result row, not duplicates.
         */
    }

    /* Outcomes and validation. */

    item def 'Operation Outcome' {
        attribute status : 'Operation Status';
        attribute summary : ScalarValues::String;
        item findings [*] : 'Validation Finding';
        doc /*
         * A completed semantic operation always has one status. An accepted
         * outcome carries the success payload defined by its specialization. A
         * rejected or failed outcome carries no success payload unless that
         * specialization explicitly states otherwise. Malformed input forms no
         * domain request, and an unexpected tool failure produces no completed
         * domain outcome.
         */
    }

    item def 'Revisioned Outcome' :> 'Operation Outcome' {
        attribute resultingRevision [0..1] : 'Revision Number';
        doc /*
         * The resulting revision is present only when an accepted operation
         * changes canonical state. An accepted effective no-op has no resulting
         * revision or canonical transition.
         */
    }

    item def 'Validation Finding' {
        attribute summary : ScalarValues::String;
        ref item implicatedDefinitions [*] : 'Definition Object';
        ref item implicatedObjects [*] : 'Graph Object';
    }

    item def 'Validation Report' {
        attribute scope : 'Validation Scope';
        attribute conforms : ScalarValues::Boolean;
        attribute evaluatedRevision : 'Revision Number';
        item findings [*] : 'Validation Finding';
        doc /*
         * A report is the successful result of an assessment. A false conforms
         * value describes the assessed subject and is not an execution failure.
         */
    }

    item def 'Graph Query Result' :> 'Operation Outcome' {
        ref item query : 'Graph Query';
        attribute evaluatedRevision [0..1] : 'Revision Number';
        item rows [*] : 'Graph Query Row';
        doc /*
         * Accepted results contain exactly the bindings requested by the
         * referenced query's return shape and the evaluated revision. Rejected
         * or failed queries contain no rows or evaluated revision. Invalid
         * queries contain findings and change no canonical state. A
         * result that would exceed maximumRows, or cannot be returned completely,
         * is rejected whole and never truncated. The operation attempt may still
         * produce observational activity.
         */
    }

    item def 'Definition Summary Result' :> 'Operation Outcome' {
        attribute evaluatedRevision [0..1] : 'Revision Number';
        attribute deltaPresent [0..1] : ScalarValues::Boolean;
        item anchorTypes [*] : 'Anchor Type Summary';
        doc /*
         * Contains every active anchor type exactly once. Each summary refers to
         * its authoritative type key and description. The result is complete
         * for the definitions active at the evaluated current or historical
         * state and changes no canonical state. Evaluated revision and delta
         * presence are present exactly for an accepted result. A rejected or failed result
         * returns no summaries, evaluated revision, or delta-presence value. The
         * operation attempt may still produce observational activity.
         */
    }

    item def 'Definition Inspection Result' :> 'Operation Outcome' {
        ref item request : 'Definition Inspection Request';
        attribute evaluatedRevision [0..1] : 'Revision Number';
        item anchorDetails [*] : 'Anchor Definition Detail';
        doc /*
         * An accepted result contains one complete detail for every requested
         * anchor type active at the request's evaluated current or historical
         * state and no unrelated definitions. An unknown or
         * duplicate key or inability to answer completely produces findings,
         * no evaluated revision, and no details. The operation changes no
         * canonical state but may produce observational activity.
         */
    }

    item def 'Definition Delta Result' :> 'Revisioned Outcome' {
        attribute evaluatedRevision [0..1] : 'Revision Number';
        ref item definitionDelta [0..1] : 'Definition Delta';
        item assessment [0..1] : 'Validation Report';
        doc /*
         * An accepted result always identifies its evaluated revision. Absence
         * of a delta is a normal accepted result. When a delta is present, the
         * result exposes the complete authoritative proposal and one current
         * definitionDelta-scoped assessment without computing a server-side diff.
         * Assessment is present exactly when a delta is returned and has the same
         * evaluated revision as this result. A resulting revision, when present,
         * is also this evaluated revision. A rejected or failed staging operation
         * returns no proposal, assessment, evaluated revision, or resulting
         * revision; the caller may retrieve the unchanged current proposal
         * separately.
         */
    }

    item def 'Graph Change' {
        item anchorUpserts [*] : Anchor;
        item associatedDataUpserts [*] : 'Associated Data Object';
        item linkUpserts [*] : Link;
        attribute anchorRemovals [*] : 'Graph UUID';
        attribute associatedDataRemovals [*] : 'Graph UUID';
        attribute linkRemovals [*] : 'Graph UUID';
        doc /*
         * Explicit complete-object upserts and UUID removals. Direct
         * associations change only through complete associated-data anchor
         * references. Duplicate commands, upsert/removal conflicts, unknown
         * removals, object-kind changes, invalid final references, and any
         * change that depends on an implicit cascade are rejected. The complete
         * resulting graph is validated before one atomic commit.
         */
    }

    /* Canonical state, snapshots, and history. */

    item def Provenance {
        attribute initiator : ScalarValues::String;
        attribute source [0..1] : ScalarValues::String;
        doc /* Identifies who initiated a record and, when applicable, its bounded source provenance. */
    }

    item def 'Canonical State' {
        item graph : Graph;
        item activeDefinitions : 'Graph Definition Set';
        item definitionDelta [0..1] : 'Definition Delta';
        attribute revision : 'Revision Number';
        doc /*
         * Two canonical states are semantically equal exactly when their
         * revisions, graphs, active definitions, and delta presence agree and,
         * when present, their proposed definition sets are semantically equal.
         */
    }

    item def 'Canonical Change' {
        doc /*
         * Replay-sufficient meaning for one transition. A graph mutation carries
         * the accepted graph change, while historical restoration may carry a
         * complete replacement graph. The two graph forms are never
         * both present. An absent graph form or active-definition value means
         * unchanged. Delta disposition distinguishes unchanged, present, and
         * absent. Present requires a delta value; unchanged and absent forbid one.
         */
        item graphChange [0..1] : 'Graph Change';
        item replacementGraph [0..1] : Graph;
        item activeDefinitions [0..1] : 'Graph Definition Set';
        attribute deltaDisposition : 'Definition Delta Disposition';
        item definitionDelta [0..1] : 'Definition Delta';
    }

    abstract item def 'History Record' {
        attribute recordedAt : 'Recorded Time';
        item provenance : Provenance;
    }

    abstract item def 'Canonical Record' :> 'History Record' {
        attribute establishedRevision : 'Revision Number';
        doc /*
         * Establishes exactly one canonical revision: the contained revision
         * for an initial record and the resulting revision for a transition.
         */
    }

    item def 'Initial State Record' :> 'Canonical Record' {
        item canonicalState : 'Canonical State';
        attribute initializationSummary : ScalarValues::String;
        bind establishedRevision = canonicalState.revision;
        doc /*
         * Establishes the owned history base. Its revision may be greater than
         * zero when a fresh RTG is seeded from reconstructed snapshot state;
         * the record makes no claim about transitions before that base. Its
         * bounded summary describes how the base was established without copying
         * complete source, candidate, report, or canonical payloads.
         */
    }

    item def 'Canonical Transition Record' :> 'Canonical Record' {
        attribute priorRevision : 'Revision Number';
        attribute resultingRevision : 'Revision Number';
        attribute kind : 'Transition Kind';
        item change : 'Canonical Change';
        bind establishedRevision = resultingRevision;
        doc /*
         * Establishes one contiguous canonical transition. The record carries
         * enough semantic change to replay without activity history but does
         * not prescribe event, snapshot, checkpoint, or hybrid storage.
         *
         * A graph mutation supplies only graphChange and leaves the delta unchanged.
         * A definition-delta change supplies only a present or absent delta. An
         * activation supplies active definitions and an absent delta. Historical
         * restoration supplies replacementGraph, active definitions, and an
         * absent delta. Other combinations are invalid and cannot be replayed.
         */
    }

    item def 'State Change Ledger' {
        item initial : 'Initial State Record';
        item transitions [*] ordered : 'Canonical Transition Record';
        doc /*
         * The complete, durable, ordered authority from its owned initial base
         * forward. Replay through its final canonical record establishes the
         * current canonical state.
         */
    }

    item def 'Activity Record' :> 'History Record' {
        attribute capability : ScalarValues::String;
        attribute outcomeCategory : 'Operation Status';
        attribute evaluatedRevision [0..1] : 'Revision Number';
        attribute semanticScope : ScalarValues::String;
        attribute summary : ScalarValues::String;
        doc /*
         * The bounded owner-facing summary identifies capability, outcome,
         * provenance, evaluated revision when applicable, and semantic scope.
         * It copies no result rows, canonical payloads, or inferred intent.
         */
    }

    item def 'Activity Ledger' {
        item records [*] ordered : 'Activity Record';
        doc /*
         * Observational history that is never replayed and cannot establish
         * canonical state. A history read is evaluated against the activity
         * ledger before the record of that read is appended, so its result never
         * includes its own observation.
         */
    }

    item def 'Canonical Snapshot' {
        item canonicalState : 'Canonical State';
        ref item capturedThrough : 'Canonical Record';
        doc /*
         * A self-contained, lossless capture of complete canonical state at its
         * revision, bound to the exact authoritative record that establishes
         * that revision. Physical artifact and serialization format remain open.
         */
    }

    item def 'Ledger Tail' {
        ref item precedingRecord : 'Canonical Record';
        ref item transitions [1..*] ordered : 'Canonical Transition Record';
        doc /*
         * References a contiguous sequence from the same authoritative ledger.
         * Its first transition immediately follows the exact preceding record;
         * revision-number equality alone cannot establish compatibility.
         */
    }

    item def 'Replay Request' {
        ref item initial [0..1] : 'Initial State Record';
        ref item capturedSnapshot [0..1] : 'Canonical Snapshot';
        ref item tail [0..1] : 'Ledger Tail';
        doc /*
         * Uses exactly one base: an initial record or a snapshot. When a tail is
         * present, its preceding record is exactly that initial record or the
         * selected snapshot's captured-through record. The tail may then advance
         * that base through later canonical revisions from the same ledger.
         */
    }

    item def 'Historical State' :> 'Canonical State' {
        doc /* Read-only canonical state reconstructed at one committed revision. */
    }

    item def 'Replay Outcome' :> 'Operation Outcome' {
        item reconstructedState [0..1] : 'Historical State';
        doc /* Reconstructed state is present exactly when status is accepted. */
    }

    item def 'Snapshot Outcome' :> 'Operation Outcome' {
        item capturedSnapshot [0..1] : 'Canonical Snapshot';
        doc /* A snapshot is present exactly when capture is accepted. */
    }

    item def 'History Query' {
        attribute kind : 'History Kind';
        attribute startTime [0..1] : 'Recorded Time';
        attribute endTime [0..1] : 'Recorded Time';
        attribute maximumRecords : ScalarValues::Positive;
        doc /*
         * Selects one record family and an optional chronological interval. The
         * start and end bounds are inclusive. The
         * positive maximum bounds one complete result rather than requesting a
         * page. Query notation and evaluation representation remain open.
         */
    }

    abstract item def 'History Entry' {
        attribute recordedAt : 'Recorded Time';
        item provenance : Provenance;
        attribute summary : ScalarValues::String;
        doc /*
         * An owner-facing projection of one authoritative record. It carries
         * enough meaning for review without becoming replay authority or copying
         * canonical state and replay payloads into an agent response.
         */
    }

    item def 'Canonical History Entry' :> 'History Entry' {
        attribute revision : 'Revision Number';
        attribute priorRevision [0..1] : 'Revision Number';
        attribute transitionKind [0..1] : 'Transition Kind';
        doc /*
         * Projects an initial record when priorRevision and transitionKind are
         * both absent. A transition entry has both present, and revision is its
         * resulting revision. The replay-sufficient canonical change is not an
         * inline history-query result.
         */
    }

    item def 'Activity History Entry' :> 'History Entry' {
        attribute capability : ScalarValues::String;
        attribute outcomeCategory : 'Operation Status';
        attribute evaluatedRevision [0..1] : 'Revision Number';
        attribute semanticScope : ScalarValues::String;
    }

    item def 'History Result' :> 'Operation Outcome' {
        ref item query : 'History Query';
        attribute evaluatedRevision [0..1] : 'Revision Number';
        item canonicalEntries [*] ordered : 'Canonical History Entry';
        item activityEntries [*] ordered : 'Activity History Entry';
        doc /*
         * An accepted result identifies its evaluated revision. An accepted
         * canonical query contains one canonical entry for every
         * selected canonical record and no activity entries. An accepted
         * activity query contains one activity entry for every selected activity
         * record and no canonical entries. Entries preserve the complete
         * requested inclusive interval and selected ledger order without
         * exposing canonical replay payloads. An over-broad request or one that
         * cannot be returned completely is rejected with no entries or evaluated
         * revision. A failed operation likewise returns no success payload;
         * activity entries are never replayed.
         */
    }

    abstract item def 'Historical State Selection';

    item def 'Revision Selection' :> 'Historical State Selection' {
        attribute revision : 'Revision Number';
    }

    item def 'Time Selection' :> 'Historical State Selection' {
        attribute time : 'Recorded Time';
    }

    item def 'Recovery Candidate' {
        doc /*
         * Transient normalized v1 graph meaning and complete target active
         * definitions. While forming this candidate, a v1
         * anchor without a display name is assigned the clearly synthetic value
         * "[recovered] {typeKey} {uuid}" using that anchor's exact type-key and
         * UUID strings. The candidate is validated before first-use initialization
         * and never becomes an existing-system mutation.
         */
        item graph : Graph;
        item activeDefinitions : 'Graph Definition Set';
    }

    item def 'Recovery Finding' {
        attribute disposition : 'Recovery Finding Disposition';
        attribute summary : ScalarValues::String;
    }

    item def 'Recovery Report' {
        ref item candidate : 'Recovery Candidate';
        item findings [*] : 'Recovery Finding';
        doc /*
         * A transient, complete preview of preserved graph meaning and every
         * simplified, omitted, or blocking definition condition for the exact
         * candidate. It is not canonical or activity state.
         */
    }
}
