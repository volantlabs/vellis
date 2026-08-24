package RTG {
    /* Language-neutral meaning for one personally owned reified type graph. */

    attribute def 'Graph UUID' :> ScalarValues::String {
        doc /* A canonical lowercase hyphenated UUID for one graph object. */
    }
    attribute def 'Type Key' :> ScalarValues::String {
        doc /* A non-empty exact Unicode key in the namespace shared by all definition kinds. */
    }
    attribute def 'Property Name' :> ScalarValues::String;
    attribute def 'Query Name' :> ScalarValues::String;
    attribute def 'Revision Number' :> ScalarValues::Natural;
    attribute def 'Activity Number' :> ScalarValues::Positive;
    attribute def 'Recorded Time' {
        doc /* An offset-aware chronological instant normalized to UTC. */
    }
    attribute def 'Date Value' :> ScalarValues::String {
        doc /* A valid proleptic-Gregorian date from year 0001 through 9999 in YYYY-MM-DD form. */
    }
    attribute def 'Timestamp Value' :> ScalarValues::String {
        doc /* A UTC-normalized RFC 3339 instant with seconds and at most nanosecond precision. */
    }

    enum def 'Scalar Kind' {
        enum boolean; enum integer; enum number; enum text; enum date; enum timestamp;
    }
    enum def 'Object Kind' { enum anchor; enum associatedData; enum link; }
    enum def 'Pattern Node Kind' { enum anchor; enum associatedData; }
    enum def 'Definition Kind' { enum anchor; enum associatedData; enum link; }
    enum def 'Operation Status' { enum accepted; enum rejected; }
    enum def 'Activity Outcome' { enum accepted; enum rejected; enum failed; }
    enum def 'History Kind' { enum canonical; enum activity; }
    enum def 'Transition Kind' {
        enum initialization; enum graphChange; enum draftActivation; enum restore;
    }
    enum def 'Activity Mode' { enum semantic; enum verbose; }
    enum def 'Draft Category' {
        enum definitions; enum anchors; enum associatedData; enum links;
    }
    enum def 'Draft Operation' { enum add; enum patch; enum replace; enum remove; }
    enum def 'Finding Code' {
        enum duplicate; enum missing; enum unknown; enum kindMismatch;
        enum invalidValue; enum constraintViolation; enum cardinalityViolation;
        enum conflict; enum staleRevision; enum expiredCursor;
        enum resultLimitExceeded; enum integrityFailure;
    }
    enum def 'Predicate Operator' {
        enum present; enum missing; enum isNull; enum isNotNull;
        enum equal; enum notEqual; enum lessThan; enum lessThanOrEqual;
        enum greaterThan; enum greaterThanOrEqual; enum anyOf;
        enum contains; enum prefix; enum regex;
        enum allTerms; enum anyTerms; enum phrase;
    }
    enum def 'Recovery Finding Disposition' {
        enum preserved; enum converted; enum omitted; enum blocking;
    }

    abstract attribute def 'Scalar Value' {
        doc /* Exactly one non-null scalar value; absence and null are modeled separately. */
    }
    attribute def 'Boolean Value' :> 'Scalar Value' { attribute value : ScalarValues::Boolean; }
    attribute def 'Integer Value' :> 'Scalar Value' {
        attribute value : ScalarValues::Integer;
        doc /* Between -9007199254740991 and 9007199254740991 inclusive. */
    }
    attribute def 'Number Value' :> 'Scalar Value' {
        attribute value : ScalarValues::Real;
        doc /* A finite IEEE-754 binary64 value with negative zero canonicalized to positive zero. */
    }
    attribute def 'Text Value' :> 'Scalar Value' { attribute value : ScalarValues::String; }
    attribute def 'Date Scalar' :> 'Scalar Value' { attribute value : 'Date Value'; }
    attribute def 'Timestamp Scalar' :> 'Scalar Value' { attribute value : 'Timestamp Value'; }

    attribute def 'Property Value' {
        attribute name : 'Property Name';
        attribute value [0..1] : 'Scalar Value';
        attribute isNull : ScalarValues::Boolean default = false;
        doc /*
         * Exactly one of value or isNull=true applies. No occurrence means
         * absence; isNull=true means a present null.
         */
    }
    attribute def 'System Envelope' {
        attribute createdRevision : 'Revision Number';
        attribute lastChangedRevision : 'Revision Number';
        attribute legacyV1 [0..1] : ScalarValues::String;
        doc /* Read-only Vellis-owned lifecycle data. legacyV1 is canonical JSON text. */
    }

    abstract item def 'Graph Object' {
        attribute uuid : 'Graph UUID';
        attribute typeKey : 'Type Key';
        attribute system [0..1] : 'System Envelope';
        doc /*
         * Canonical current/historical objects have one system envelope. A
         * never-live draft proposal has none until activation.
         */
    }
    abstract item def 'Link Endpoint' :> 'Graph Object';
    item def Anchor :> 'Link Endpoint' { attribute displayName : ScalarValues::String; }
    item def 'Associated Data Object' :> 'Link Endpoint' {
        ref item anchors [1..*] : Anchor;
        attribute properties [*] : 'Property Value';
        doc /* Anchor references form one duplicate-free identity-free direct-association set. */
    }
    item def Link :> 'Graph Object' {
        ref item source : 'Link Endpoint';
        ref item target : 'Link Endpoint';
    }
    item def Graph {
        item anchors [*] : Anchor;
        item associatedData [*] : 'Associated Data Object';
        item links [*] : Link;
        doc /*
         * UUIDs are unique across kinds for the full lineage. References resolve
         * within the selected state. Collections are unordered sets; self-links
         * are valid and links are never endpoints.
         */
    }

    item def 'Inclusive Cardinality' {
        attribute minimum : ScalarValues::Natural;
        attribute maximum [0..1] : ScalarValues::Natural;
        doc /* An absent maximum is unbounded; a present maximum is not below minimum. */
    }
    item def 'Property Definition' {
        attribute name : 'Property Name';
        attribute description : ScalarValues::String;
        attribute valueKind : 'Scalar Kind';
        attribute required : ScalarValues::Boolean default = false;
        attribute nullable : ScalarValues::Boolean default = false;
        attribute allowedValues [*] ordered : 'Scalar Value';
        attribute minimum [0..1] : 'Scalar Value';
        attribute maximum [0..1] : 'Scalar Value';
        attribute minimumLength [0..1] : ScalarValues::Natural;
        attribute maximumLength [0..1] : ScalarValues::Natural;
        attribute pattern [0..1] : ScalarValues::String;
        doc /*
         * One closed scalar rule. Allowed values are non-null and same-kind.
         * Numeric, date, and timestamp bounds are inclusive. Text lengths count
         * Unicode code points. A text pattern is a case-sensitive RE2 whole-string rule.
         */
    }
    abstract item def 'Type Definition' {
        attribute typeKey : 'Type Key';
        attribute description : ScalarValues::String;
        attribute system [0..1] : 'System Envelope';
        doc /*
         * Canonical current/historical definitions have one system envelope. A
         * never-live draft replacement has none until activation.
         */
    }
    abstract item def 'Endpoint Type Definition' :> 'Type Definition';
    item def 'Anchor Type Definition' :> 'Endpoint Type Definition';
    item def 'Associated Data Type Definition' :> 'Endpoint Type Definition' {
        ref item permittedAnchorTypes [1..*] ordered : 'Anchor Type Definition';
        item properties [*] ordered : 'Property Definition';
        item anchorsPerObject : 'Inclusive Cardinality';
        item objectsPerAnchor : 'Inclusive Cardinality';
        doc /* anchorsPerObject minimum is at least one. */
    }
    item def 'Link Type Definition' :> 'Type Definition' {
        ref item permittedSourceTypes [1..*] ordered : 'Endpoint Type Definition';
        ref item permittedTargetTypes [1..*] ordered : 'Endpoint Type Definition';
        item linksPerSource : 'Inclusive Cardinality';
        item linksPerTarget : 'Inclusive Cardinality';
    }
    item def 'Graph Definition Set' {
        item anchorTypes [*] ordered : 'Anchor Type Definition';
        item associatedDataTypes [*] ordered : 'Associated Data Type Definition';
        item linkTypes [*] ordered : 'Link Type Definition';
        doc /*
         * Type keys are unique across definition kinds for the full lineage.
         * Every description is non-empty and every reference resolves. Different
         * cardinality meaning requires a distinct data or link type.
         */
    }

    abstract item def 'State Selection';
    item def 'Current Selection' :> 'State Selection';
    item def 'Draft Selection' :> 'State Selection';
    item def 'Revision Selection' :> 'State Selection' {
        attribute revision : 'Revision Number';
    }
    item def 'Time Selection' :> 'State Selection' {
        attribute timestamp : 'Timestamp Value';
    }
    item def 'Anchor Type Summary' { ref item definition : 'Anchor Type Definition'; }
    item def 'Definition Summary Request' {
        item 'state' [0..1] : 'State Selection';
        doc /* Omitted state selects current. */
    }
    item def 'Definition Inspection Request' {
        item 'state' [0..1] : 'State Selection';
        attribute anchorTypeKeys [1..*] ordered : 'Type Key';
        attribute includeLegacySystem : ScalarValues::Boolean default = false;
        doc /* Omitted state selects current. */
    }
    item def 'Anchor Definition Neighborhood' {
        ref item anchorType : 'Anchor Type Definition';
        ref item associatedDataTypes [*] ordered : 'Associated Data Type Definition';
        ref item linkTypes [*] ordered : 'Link Type Definition';
        doc /*
         * Complete focused meaning: data types that permit the anchor and link
         * types involving the anchor or those data types. Unrelated definitions
         * are not recursively copied.
         */
    }

    item def 'Property Selection' {
        attribute 'all' : ScalarValues::Boolean default = false;
        attribute names [*] : 'Property Name';
        doc /* Omission requests no properties; all and names are mutually exclusive. */
    }
    item def 'Identity Object Selection' {
        attribute uuid : 'Graph UUID';
        item properties [0..1] : 'Property Selection';
        attribute includeLegacySystem : ScalarValues::Boolean default = false;
    }
    abstract item def 'Query Selection';
    item def 'Identity Selection' :> 'Query Selection' {
        item objects [1..*] ordered : 'Identity Object Selection';
    }
    abstract item def 'Predicate Field';
    item def 'Display Name Field' :> 'Predicate Field';
    item def 'Property Field' :> 'Predicate Field' { attribute name : 'Property Name'; }
    item def Predicate {
        item field : 'Predicate Field';
        attribute operator : 'Predicate Operator';
        attribute value [0..1] : 'Scalar Value';
        attribute values [*] : 'Scalar Value';
        attribute text [0..1] : ScalarValues::String;
        attribute terms [*] : ScalarValues::String;
        attribute caseSensitive : ScalarValues::Boolean default = false;
        doc /*
         * Payload presence follows exactly the selected operator: presence/null
         * operators carry none; equality/order carries one value; anyOf carries
         * one nonempty values set; contains/prefix/regex carries text; term
         * operators carry a nonempty term set; phrase carries text. Other payload
         * members are absent. Full-text input is structured, never raw FTS syntax.
         */
    }
    item def 'Pattern Node' {
        attribute name : 'Query Name';
        attribute kind : 'Pattern Node Kind';
        attribute typeKeys [*] : 'Type Key';
        attribute uuids [*] : 'Graph UUID';
        item predicates [*] : Predicate;
        item properties [0..1] : 'Property Selection';
        attribute includeLegacySystem : ScalarValues::Boolean default = false;
        doc /* Empty type-key or UUID collections mean that filter is omitted. */
    }
    item def 'Direct Association Predicate' {
        ref item anchorNode : 'Pattern Node';
        ref item associatedDataNode : 'Pattern Node';
    }
    item def 'Pattern Link' {
        attribute name : 'Query Name';
        ref item sourceNode : 'Pattern Node';
        ref item targetNode : 'Pattern Node';
        attribute typeKeys [*] : 'Type Key';
        attribute uuids [*] : 'Graph UUID';
        attribute includeLegacySystem : ScalarValues::Boolean default = false;
        doc /* Empty type-key or UUID collections mean that filter is omitted. */
    }
    item def 'Pattern Selection' :> 'Query Selection' {
        attribute maximumMatches : ScalarValues::Positive;
        item nodes [1..*] ordered : 'Pattern Node';
        item directAssociations [*] : 'Direct Association Predicate';
        item links [*] ordered : 'Pattern Link';
        doc /*
         * A single node is valid; otherwise the undirected pattern is connected.
         * Names are unique across nodes and links. Distinct names bind distinct
         * identities. Conditions are conjunctive. Cycles, parallel links, and a
         * true self-link expressed by reusing one endpoint node are valid.
         */
    }
    item def 'Graph Query' {
        item 'state' [0..1] : 'State Selection';
        item selection : 'Query Selection';
        doc /* Omitted state selects current. */
    }
    item def 'Pattern Binding' {
        attribute name : 'Query Name';
        attribute uuid : 'Graph UUID';
    }
    item def 'Pattern Match' { item bindings [1..*] ordered : 'Pattern Binding'; }
    item def 'Hydrated Object' {
        attribute uuid : 'Graph UUID';
        attribute kind : 'Object Kind';
        attribute typeKey : 'Type Key';
        attribute displayName [0..1] : ScalarValues::String;
        attribute anchorUuids [*] ordered : 'Graph UUID';
        attribute sourceUuid [0..1] : 'Graph UUID';
        attribute targetUuid [0..1] : 'Graph UUID';
        attribute system [0..1] : 'System Envelope';
        attribute selectedProperties [*] ordered : 'Property Value';
        attribute includeLegacySystem : ScalarValues::Boolean default = false;
        doc /*
         * Kind selects the compatible structural fields. Current/historical and
         * live-backed draft objects carry canonical system metadata. A draft-only
         * addition or reactivation carries none until activation.
         */
    }

    abstract item def 'Object Upsert' {
        attribute uuid : 'Graph UUID';
        attribute typeKey [0..1] : 'Type Key';
    }
    item def 'Anchor Upsert' :> 'Object Upsert' {
        attribute displayName [0..1] : ScalarValues::String;
    }
    item def 'Property Set' {
        attribute name : 'Property Name';
        attribute value [0..1] : 'Scalar Value';
        attribute isNull : ScalarValues::Boolean default = false;
        doc /* Exactly one of a value or isNull=true is present. */
    }
    item def 'Complete Anchor UUID Set' {
        attribute values [1..*] : 'Graph UUID';
        doc /* One supplied nonempty duplicate-free complete anchor set. */
    }
    item def 'Associated Data Upsert' :> 'Object Upsert' {
        item anchorUuids [0..1] : 'Complete Anchor UUID Set';
        attribute addAnchorUuids [*] : 'Graph UUID';
        attribute removeAnchorUuids [*] : 'Graph UUID';
        item setProperties [*] : 'Property Set';
        attribute removeProperties [*] : 'Property Name';
        doc /*
         * Creation uses one complete non-empty anchorUuids set and forbids
         * add/remove. Update omits anchorUuids and changes only named operations.
         * The same anchor cannot be added and removed and the same property cannot
         * be set and removed in one upsert; either conflict rejects the request.
         * Supplying anchorUuids, even empty, is distinct from omitting it and is
         * invalid for update; creation requires it to be nonempty.
         */
    }
    item def 'Link Upsert' :> 'Object Upsert' {
        attribute sourceUuid [0..1] : 'Graph UUID';
        attribute targetUuid [0..1] : 'Graph UUID';
    }
    item def 'Graph Change' {
        item upserts [*] : 'Object Upsert';
        attribute removeUuids [*] : 'Graph UUID';
        doc /*
         * One UUID occurs in at most one command. The batch is interpreted
         * atomically against its final combined state, independent of command
         * order. Absence removals and duplicate additions are accepted no-ops.
         * No cascade is inferred.
         */
    }
    item def 'Active Change Request' {
        attribute expectedRevision : 'Revision Number';
        item change : 'Graph Change';
    }

    item def 'Definition Replacement' {
        attribute kind : 'Definition Kind';
        attribute typeKey : 'Type Key';
        attribute description : ScalarValues::String;
        attribute permittedAnchorTypeKeys [*] : 'Type Key';
        attribute permittedSourceTypeKeys [*] : 'Type Key';
        attribute permittedTargetTypeKeys [*] : 'Type Key';
        item properties [*] ordered : 'Property Definition';
        item anchorsPerObject [0..1] : 'Inclusive Cardinality';
        item objectsPerAnchor [0..1] : 'Inclusive Cardinality';
        item linksPerSource [0..1] : 'Inclusive Cardinality';
        item linksPerTarget [0..1] : 'Inclusive Cardinality';
        doc /*
         * Complete owner-supplied content for one definition kind. Valid feature
         * combinations follow kind; no system-envelope member is writable.
         */
    }

    abstract item def 'Draft Entry';
    item def 'Draft Definition Entry' :> 'Draft Entry' {
        attribute typeKey : 'Type Key';
        item replacement [0..1] : 'Definition Replacement';
        attribute remove : ScalarValues::Boolean default = false;
    }
    item def 'Draft Object Entry' :> 'Draft Entry' {
        attribute uuid : 'Graph UUID';
        item patch [0..1] : 'Object Upsert';
        attribute remove : ScalarValues::Boolean default = false;
    }
    item def Draft {
        item definitionEntries [*] : 'Draft Definition Entry';
        item objectEntries [*] : 'Draft Object Entry';
        doc /*
         * The sole durable noncanonical bucket. Repeated edits merge by type key
         * or UUID. Staged fields win over corresponding latest live fields;
         * unstaged live fields follow live state. A tombstone wins over the whole
         * object. Draft presence is derived from nonempty entries.
         */
    }
    item def 'Draft Change' {
        item definitionUpserts [*] : 'Definition Replacement';
        attribute definitionRemovals [*] : 'Type Key';
        attribute unstageDefinitionKeys [*] : 'Type Key';
        item objectUpserts [*] : 'Object Upsert';
        attribute objectRemovals [*] : 'Graph UUID';
        attribute unstageObjectUuids [*] : 'Graph UUID';
        doc /*
         * A type key or UUID occurs in at most one command collection in one
         * request. Duplicate or cross-collection occurrence rejects the whole
         * request; command order has no meaning.
         */
    }
    item def 'Draft Inspection Request' {
        attribute categories [*] : 'Draft Category';
        attribute operations [*] : 'Draft Operation';
        attribute typeKeys [*] : 'Type Key';
        attribute uuids [*] : 'Graph UUID';
        attribute limit [0..1] : ScalarValues::Positive;
        attribute cursor [0..1] : ScalarValues::String;
        doc /*
         * A fresh request omits cursor, requires limit, and treats every empty
         * filter collection as unfiltered. A continuation supplies only cursor;
         * filters and limit are bound by that cursor and must be omitted.
         */
    }
    item def 'Draft Inspection Entry' {
        ref item 'entry' : 'Draft Entry';
        attribute operation : 'Draft Operation';
        ref item currentDefinition [0..1] : 'Type Definition';
        ref item currentObject [0..1] : 'Graph Object';
        ref item proposedDefinition [0..1] : 'Type Definition';
        ref item proposedObject [0..1] : 'Graph Object';
        attribute hasEffect : ScalarValues::Boolean;
        doc /* The referenced raw entry exposes exact staged definition or graph operations. */
    }

    item def 'Validation Finding' {
        attribute code : 'Finding Code';
        attribute path [0..1] : ScalarValues::String;
        attribute summary : ScalarValues::String;
        attribute typeKeys [*] ordered : 'Type Key';
        attribute uuids [*] ordered : 'Graph UUID';
        doc /*
         * When present, path identifies the exact request member or affected-state
         * subject. Public JSON paths are RFC 6901 pointers and the empty string
         * denotes the whole request. A definition-scoped affected-state path uses
         * /definitions/<escaped-type-key>/... . Relevant missing, conflicting,
         * or affected identities remain in typeKeys or uuids.
         */
    }
    item def 'Operation Outcome' {
        attribute status : 'Operation Status';
        attribute summary : ScalarValues::String;
        item findings [*] ordered : 'Validation Finding';
        attribute evaluatedRevision [0..1] : 'Revision Number';
        attribute resultingRevision [0..1] : 'Revision Number';
        doc /*
         * Malformed wire input forms no domain request. Unexpected execution or
         * transport failure forms no fabricated rejection. resultingRevision is
         * present only for an effective accepted canonical change. A semantic
         * rejection carries its decisive findings. Purpose payload presence is
         * fixed by each result subtype rather than inferred from empty lists.
         */
    }
    item def 'Definition Summary Payload' {
        item anchorTypes [*] ordered : 'Anchor Type Summary';
    }
    item def 'Definition Summary Result' :> 'Operation Outcome' {
        item payload [0..1] : 'Definition Summary Payload';
        doc /* Accepted has payload and evaluatedRevision; rejected omits payload. */
    }
    item def 'Definition Inspection Payload' {
        item neighborhoods [*] ordered : 'Anchor Definition Neighborhood';
    }
    item def 'Definition Inspection Result' :> 'Operation Outcome' {
        item payload [0..1] : 'Definition Inspection Payload';
        doc /* Accepted has request-ordered payload and evaluatedRevision; rejected omits payload. */
    }
    abstract item def 'Graph Query Payload' {
        item objects [*] ordered : 'Hydrated Object';
    }
    item def 'Identity Query Payload' :> 'Graph Query Payload' {
        attribute foundUuids [*] ordered : 'Graph UUID';
        attribute missingUuids [*] ordered : 'Graph UUID';
    }
    item def 'Pattern Query Payload' :> 'Graph Query Payload' {
        item matches [*] ordered : 'Pattern Match';
    }
    item def 'Graph Query Result' :> 'Operation Outcome' {
        item payload [0..1] : 'Graph Query Payload';
        doc /*
         * Accepted has evaluatedRevision and exactly the payload subtype matching
         * the request selection. Identity UUIDs preserve request order. Pattern
         * matches are bounded before hydration and ordered by selector-order UUID
         * tuples. Rejection omits payload. Hydrated objects are unique by UUID.
         */
    }
    item def 'Draft Change Payload' {
        attribute draftPresent : ScalarValues::Boolean;
        attribute rawEntryCount : ScalarValues::Natural;
        attribute effectiveChangeCount : ScalarValues::Natural;
    }
    item def 'Draft Change Result' :> 'Operation Outcome' {
        item payload [0..1] : 'Draft Change Payload';
        doc /* Accepted has payload and evaluatedRevision; rejected omits payload. */
    }
    item def 'Draft Inspection Payload' :> 'Draft Change Payload' {
        item entries [*] ordered : 'Draft Inspection Entry';
        attribute returnedCount : ScalarValues::Natural;
        attribute cursor [0..1] : ScalarValues::String;
    }
    item def 'Draft Inspection Result' :> 'Operation Outcome' {
        item payload [0..1] : 'Draft Inspection Payload';
        doc /* Accepted has payload and evaluatedRevision; rejected omits payload. */
    }
    enum def 'Validation Scope' { enum current; enum draft; }
    item def 'Validation Request' {
        attribute scope : 'Validation Scope';
        attribute limit [0..1] : ScalarValues::Positive;
        attribute cursor [0..1] : ScalarValues::String;
        doc /*
         * A fresh request requires limit and omits cursor. A continuation requires
         * cursor and the same scope, omits limit, and pages the stored assessment
         * without reassessment. Any other combination rejects as malformed.
         */
    }
    item def 'Validation Payload' {
        attribute totalFindings : ScalarValues::Natural;
        attribute clean : ScalarValues::Boolean;
        attribute rawDraftEntryCount [0..1] : ScalarValues::Natural;
        attribute effectiveDraftChangeCount [0..1] : ScalarValues::Natural;
        attribute cursor [0..1] : ScalarValues::String;
    }
    item def 'Validation Report' :> 'Operation Outcome' {
        item payload [0..1] : 'Validation Payload';
        doc /*
         * Completed validation is accepted with payload even when non-clean.
         * Invalid draft activation is rejected with payload and its first finding
         * page. Other rejection, including draft absence or cursor expiry, omits
         * payload. Draft counts occur only for draft scope; cursor only when more
         * findings remain.
         */
    }

    item def 'Canonical State' {
        item graph : Graph;
        item definitions : 'Graph Definition Set';
        attribute revision : 'Revision Number';
        doc /* Current and historical state is directly selectable, never reconstructed by public replay. */
    }
    item def Provenance {
        attribute initiator : ScalarValues::String;
        attribute source [0..1] : ScalarValues::String;
    }
    item def 'Canonical Record' {
        attribute revision : 'Revision Number';
        attribute recordedAt : 'Recorded Time';
        item provenance : Provenance;
        attribute transitionKind : 'Transition Kind';
        attribute summary : ScalarValues::String;
        attribute affectedTypeKeys [*] ordered : 'Type Key';
        attribute affectedUuids [*] ordered : 'Graph UUID';
        doc /* One contiguous corruption-evident owner-readable record, not a replay payload. */
    }
    item def 'Canonical Ledger' { item records [1..*] ordered : 'Canonical Record'; }
    item def 'Activity Record' {
        attribute sequence : 'Activity Number';
        attribute recordedAt : 'Recorded Time';
        attribute capability : ScalarValues::String;
        attribute outcome : 'Activity Outcome';
        item provenance : Provenance;
        attribute evaluatedRevision [0..1] : 'Revision Number';
        attribute resultingRevision [0..1] : 'Revision Number';
        attribute summary : ScalarValues::String;
        attribute semanticDetail : ScalarValues::String;
        attribute verboseDetail [0..1] : ScalarValues::String;
        doc /* Observational state that cannot establish canonical state and contains no secrets. */
    }
    item def 'Activity Ledger' { item records [*] ordered : 'Activity Record'; }
    abstract item def 'History Range';
    item def 'History Time Range' :> 'History Range' {
        attribute startTime [0..1] : 'Timestamp Value';
        attribute endTime [0..1] : 'Timestamp Value';
        doc /* Both absent means unbounded through head; start after end rejects. */
    }
    item def 'History Sequence Range' :> 'History Range' {
        attribute afterSequence [0..1] : ScalarValues::Natural;
        attribute throughSequence [0..1] : ScalarValues::Natural;
        doc /*
         * Both absent means unbounded through head. after is exclusive and through
         * inclusive; after greater than or equal to through selects an empty interval.
         */
    }
    item def 'History Query' {
        attribute kind : 'History Kind';
        item range [0..1] : 'History Range';
        attribute maximumRecords : ScalarValues::Positive;
        attribute includeVerbose : ScalarValues::Boolean default = false;
        doc /*
         * Omitted range selects through the observed head. includeVerbose is
         * valid only for activity history.
         */
    }
    abstract item def 'History Payload' {
        attribute headSequence : ScalarValues::Natural;
    }
    item def 'Canonical History Payload' :> 'History Payload' {
        ref item canonicalEntries [*] ordered : 'Canonical Record';
    }
    item def 'Activity History Payload' :> 'History Payload' {
        ref item activityEntries [*] ordered : 'Activity Record';
    }
    item def 'History Result' :> 'Operation Outcome' {
        item payload [0..1] : 'History Payload';
        doc /*
         * Accepted has exactly the payload subtype selected by history kind;
         * canonical headSequence is revision and activity headSequence is activity
         * number. Rejected omits payload.
         */
    }

    item def 'V1 Snapshot' {
        doc /* One complete predecessor JSON snapshot selected only for first-use initialization. */
    }
    item def 'Recovery Candidate' {
        item graph : Graph;
        item definitions : 'Graph Definition Set';
        doc /* Transient complete meaning formed with bounded memory; not canonical state. */
    }
    item def 'Recovery Finding' {
        attribute disposition : 'Recovery Finding Disposition';
        attribute sourcePointer : ScalarValues::String;
        attribute summary : ScalarValues::String;
        attribute targetUuid [0..1] : 'Graph UUID';
        attribute targetTypeKey [0..1] : 'Type Key';
        attribute targetProperty [0..1] : 'Property Name';
    }
    item def 'Recovery Report' {
        ref item source : 'V1 Snapshot';
        ref item candidate : 'Recovery Candidate';
        item findings [*] ordered : 'Recovery Finding';
        doc /* Complete deterministic dispositions bound to the exact source and candidate. */
    }
}
