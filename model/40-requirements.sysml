package VellisRequirements {
    private import RTGSystem::*;
    private import Vellis::*;

    requirement def 'Graph Invariants' {
        subject system : 'RTG System';
        doc /*
         * The graph shall preserve globally unique object identity; distinct
         * anchor, associated-data, and link kinds; same-graph direct
         * associations and link endpoints; permitted type pairings; one type-
         * key namespace; lossless JSON; Boolean live normalization; associated-
         * data property constraints with JSON-kind-compatible closed size,
         * inclusive numeric-bound, and permitted-value meaning; endpoint constraints; directed link
         * multiplicity; and direct-association multiplicity.
         * Every graph object's type key shall resolve to exactly one active type
         * definition of the same object kind, and active type keys shall be
         * unique across the shared namespace.
         * A size condition shall apply only to string, array, or object values,
         * contain at least one bound, and never invert its bounds. A value range
         * shall contain at least one inclusive numeric bound or permitted value;
         * numeric bounds shall be ordered, permitted values shall be unique and
         * match the property's JSON kind, and coexisting forms shall both hold.
         * Property names shall be non-empty and unique within each associated-
         * data type definition. Each associated-data object's properties shall
         * use only names declared by its active type definition, include every
         * required property, and validate every present required or optional
         * property against its declared JSON kind, shape, and range.
         */
    }

    requirement def 'Semantic Query Meaning' {
        subject system : 'RTG System';
        doc /*
         * A graph query shall select named anchor groups of one active type,
         * optionally narrow anchors and links by known UUIDs, select directly
         * associated-data groups by type and optional structured value
         * comparisons, require typed directed links between anchor or
         * associated-data groups, and return only bindings that reference the
         * named projections in its return shape at an identified revision. An
         * associated-data group with no property comparisons shall select by
         * direct association and type alone. Active definitions at the evaluated
         * revision shall govern property kind, shape, range, and endpoint validity.
         * Equality shall compare lossless JSON values; ordered comparisons shall
         * be valid only for number-valued properties. A listed property
         * comparison shall match only when that property is present; omission
         * shall remain distinct from a present null value.
         * Each result row shall be one jointly satisfying assignment and shall
         * contain exactly one binding for each requested projection. Identical
         * projected tuples shall occur once. A selected optional property shall
         * retain its binding when absent so absence remains distinct from JSON null.
         * A returned property value shall be present exactly when the projected
         * property is present, including when that value is JSON null.
         * Query-local names shall be unique and every selector and projection
         * reference shall resolve within that query. Evaluation strategy shall
         * not change this meaning. An absent historical selector shall evaluate
         * current state; exactly one revision or time selector shall evaluate
         * the resolved historical graph and definitions with the same semantics.
         */
    }

    requirement def 'Query Safety' {
        subject system : 'RTG System';
        doc /*
         * Graph queries shall change no canonical state or revision. Their
         * permitted, rejected, or failed attempts may append observational
         * activity. Unknown or
         * incompatible type keys, empty or duplicate names, out-of-query references,
         * endpoint roles, unknown or duplicate UUID restrictions, properties,
         * comparisons, projections, or unresolved
         * historical selections shall produce observable findings and no result
         * rows. Every query shall provide a
         * positive row maximum; a result exceeding it, or one the system cannot
         * return completely, shall be rejected whole, never truncated or paged.
         */
    }

    requirement def 'Atomic Canonical Revision' {
        subject system : 'RTG System';
        doc /*
         * Every accepted canonical state change shall advance the one total
         * revision exactly once and commit its semantic change and contiguous
         * transition record recoverably atomically. Rejected or failed
         * operations shall change no canonical state or revision. An accepted
         * effective no-op shall create neither a revision nor a transition.
         */
    }

    requirement def 'Definition Cardinality' {
        subject system : 'RTG System';
        doc /* The system shall own exactly one active definition set and zero or one delta. */
    }

    requirement def 'Non Disruptive Definition Work' {
        subject system : 'RTG System';
        doc /*
         * Creating, editing, retrieving, or assessing a definition delta shall not change
         * active definitions or graph. Activation shall succeed only when
         * every description is non-empty, the proposed set is internally
         * valid, and the graph already conforms;
         * failure shall preserve graph, active set, delta, revision, and canonical history.
         * A present delta shall differ semantically from the active set. Staging
         * content equal to the sole current proposal, or equal to the active set
         * when no delta exists, shall be an accepted no-op. When a different
         * delta exists, the active set shall not implicitly discard it.
         */
    }

    requirement def 'Validation Coverage' {
        subject system : 'RTG System';
        doc /*
         * The system shall produce typed findings within the governing outcome
         * for semantically invalid graph queries, proposed graph changes,
         * replayed state, and recovered state. Validation reports shall identify
         * only the assessment scopes that currently return reports: complete
         * graph conformance and definition-delta consistency and graph impact.
         * The parameterless public check operation shall produce the former;
         * whole-delta retrieval and staging shall produce the latter. Validation
         * shall own no separate canonical state.
         */
    }

    requirement def 'Durable Canonical History' {
        subject system : 'RTG System';
        doc /*
         * Canonical history shall be complete, ordered, locally durable across
         * ordinary process restarts, and append-only in ordinary operation from
         * its owned initial base. One initial record and one contiguous
         * transition per successive revision after that base shall be sufficient
         * for deterministic replay without activity history. An initial base
         * seeded from reconstructed snapshot state shall not claim omitted
         * earlier transitions. Each transition's semantic change shall be valid
         * for its kind. An ordinary graph mutation record shall carry its accepted
         * graph change rather than a complete replacement graph. Only restoration
         * and predecessor recovery may carry a complete replacement graph.
         */
    }

    requirement def 'Canonical Snapshot Completeness' {
        subject system : 'RTG System';
        doc /*
         * A canonical snapshot shall be a self-contained, lossless capture of
         * graph, active definitions, optional in-flight delta, and total
         * revision. Creating it shall not change canonical state or revision.
         */
    }

    requirement def 'Replay Equivalence' {
        subject system : 'RTG System';
        doc /*
         * Replay from an initial record or complete snapshot plus an optional
         * contiguous later ledger tail shall reconstruct equivalent graph,
         * active definitions, optional delta, and revision without activity
         * history. Initializing a fresh RTG shall seed its owned history with the
         * reconstructed state at the resulting revision, without claiming
         * earlier transitions. A gap, duplicate, reorder, invalid transition,
         * or incompatible base shall fail without partially accepted canonical
         * state.
         */
    }

    requirement def 'Historical State Correctness' {
        subject system : 'RTG System';
        doc /*
         * Historical graph queries shall accept exactly one revision or time
         * selector, change no canonical state, and evaluate the selected committed
         * revision with current-query semantics. A time resolves to the greatest
         * committed revision at or before it. The caller shall supply vocabulary
         * known to be valid at the selected revision; current active-definition
         * discovery shall not claim discovery of retired vocabulary.
         */
    }

    requirement def 'Historical Restore Semantics' {
        subject system : 'RTG System';
        doc /*
         * Restore shall require no in-flight delta and shall commit historical
         * graph and active definitions with no delta as one new revision without
         * rewriting earlier history.
         */
    }

    requirement def 'Dual Ledger Separation' {
        subject system : 'RTG System';
        doc /*
         * Activity history shall record permitted reads, validation, rejections,
         * failures, snapshots, provenance, and summaries after the associated
         * outcome has been determined. An activity-history read shall select its
         * result before its own record is appended and shall never include itself.
         * Activity history shall remain observational, never be replayed, and
         * never establish canonical state. Owner-directed retention may change
         * only activity history and shall not affect reconstruction.
         */
    }

    requirement def 'Agent Definition Discoverability' {
        subject system : 'RTG System';
        doc /*
         * Every active type and rule definition shall have a non-empty,
         * owner-readable description. Automatic assessment shall establish only
         * presence and non-emptiness; owner review shall establish readability.
         * A complete shallow read shall return every
         * currently active anchor type, its description, the evaluated revision,
         * and current delta presence, or no summaries when it cannot return the
         * complete vocabulary. A focused read shall return the complete relevant
         * active-definition neighborhood at its own identified evaluated revision
         * for each selected anchor and no unrelated definitions. A caller shall
         * be able to detect an intervening definition change by comparing the
         * summary and inspection revisions. Unknown, duplicate, or
         * incompletely answerable selections shall return findings and no partial
         * details or evaluated revision. The sole current
         * proposed set shall be separately retrievable
         * whole with its current assessment. All discovery shall change no
         * canonical state or revision, while its operation attempt may be recorded
         * observationally.
         * A returned assessment shall be present exactly with a returned delta;
         * its evaluated revision, and any resulting revision from staging, shall
         * equal the whole-delta result's evaluated revision.
         */
    }

    requirement def 'Explicit Graph Change Set' {
        subject system : 'RTG System';
        doc /*
         * A graph change shall use complete-object upserts and explicit UUID
         * removals for each graph-object kind. Direct associations shall change
         * only through associated-data anchor references. Duplicate commands,
         * upsert/removal conflicts, unknown removals, kind changes, invalid final
         * references, and any assumed implicit cascade shall be rejected without
         * canonical effect. The complete resulting graph shall conform before an
         * atomic commit.
         */
    }

    requirement def 'Bounded History Read' {
        subject system : 'RTG System';
        doc /*
         * A history read shall select exactly one of canonical or activity
         * records, accept an optional chronological interval and a positive
         * maximum, and return one owner-facing entry for every record in the
         * complete inclusive matching interval in the selected ledger's order,
         * or reject it whole when the interval exceeds the caller's maximum or
         * cannot be returned completely. Canonical entries shall expose time,
         * provenance, revision, transition kind when applicable, and semantic
         * summary without exposing canonical state or replay-sufficient changes.
         * Activity entries shall expose time, provenance, activity kind, optional
         * evaluated revision, and summary. A start after its end shall be invalid.
         * A result shall never mix entry families, paginate silently, mutate
         * canonical state, or treat activity as replay authority.
         */
    }

    requirement def 'MCP Agent Tool Contract' {
        subject system : 'RTG System';
        doc /*
         * The system shall expose exactly the selected ten stable, discoverable
         * MCP tool names. Every completed invocation shall return typed object
         * meaning; tools with semantic input shall accept typed object meaning,
         * while parameterless tools shall introduce no empty domain request.
         * Every tool shall preserve canonical RTG semantics and remain usable
         * through core tool discovery and invocation without requiring any
         * additional MCP capability.
         */
    }

    requirement def 'MCP Outcome Integrity' {
        subject system : 'RTG System';
        doc /*
         * Semantic rejection shall be represented as a typed result distinct
         * from malformed input and unexpected execution failure. Read operations
         * shall not mutate canonical state, and every promised rejection or
         * failure non-effect shall hold at the MCP boundary. Accepted results shall
         * carry exactly their purpose-specific success payloads. Rejected and
         * safely reported failed outcomes shall carry no success payload unless a
         * result definition explicitly states otherwise; malformed input shall
         * form no domain request, and an unexpected tool failure shall produce no
         * completed domain result. Tool invocation shall not be represented as
         * establishing per-call authorization or owner approval.
         * Structured and textual representations shall communicate equivalent
         * typed meaning. Advisory tool annotations shall describe behavior only
         * and shall never enforce authorization, validation, atomicity, or failure
         * non-effects.
         */
    }

    requirement def 'Owner Controlled Memory' {
        subject system : 'Vellis System';
        doc /*
         * Vellis shall preserve owner control of personal-memory and activity
         * disclosure and retention, memory correction and
         * forgetting, graph-definition changes, snapshots, and restoration. Vellis
         * shall submit a context proposal for mutation only after owner approval;
         * declined, rejected, or failed context shall not be retained.
         */
    }

    requirement def 'Observable Failure' {
        subject system : 'Vellis System';
        doc /*
         * Semantic refusals and execution failures shall be observable to the
         * affected owner or external agent while preserving promised canonical
         * and observational non-effects.
         */
    }

    requirement def 'RTG Compatibility' {
        subject system : 'Vellis System';
        doc /*
         * Recovery of representative predecessor RTG graphs shall preserve
         * object identity and kind, type meaning, direct associations, directed
         * links, endpoint eligibility, lossless JSON, and system.live meaning
         * without making predecessor storage shape canonical. Accepted recovery
         * is one transition; rejection or failure preserves current canonical state.
         */
    }

    requirement def 'Simple Individual Operation' {
        subject system : 'Vellis System';
        doc /*
         * One owner shall be able to initialize, use, query, preserve, and
         * govern one cohesive Vellis system without tenant, organization, role,
         * cluster, server-fleet, concurrent definition-delta, or required
         * enterprise-infrastructure administration.
         */
    }

    part vellis : 'Vellis System';

    requirement <RTG001> graphInvariants : 'Graph Invariants';
    requirement <RTG002> semanticQueryMeaning : 'Semantic Query Meaning';
    requirement <RTG003> querySafety : 'Query Safety';
    requirement <RTG004> atomicCanonicalRevision : 'Atomic Canonical Revision';
    requirement <RTG005> definitionCardinality : 'Definition Cardinality';
    requirement <RTG006> nonDisruptiveDefinitionWork : 'Non Disruptive Definition Work';
    requirement <RTG007> validationCoverage : 'Validation Coverage';
    requirement <RTG008> durableCanonicalHistory : 'Durable Canonical History';
    requirement <RTG009> canonicalSnapshotCompleteness : 'Canonical Snapshot Completeness';
    requirement <RTG010> replayEquivalence : 'Replay Equivalence';
    requirement <RTG011> historicalStateCorrectness : 'Historical State Correctness';
    requirement <RTG012> historicalRestoreSemantics : 'Historical Restore Semantics';
    requirement <RTG013> dualLedgerSeparation : 'Dual Ledger Separation';
    requirement <RTG014> agentDefinitionDiscoverability : 'Agent Definition Discoverability';
    requirement <RTG015> explicitGraphChangeSet : 'Explicit Graph Change Set';
    requirement <RTG016> boundedHistoryRead : 'Bounded History Read';
    requirement <RTG017> mcpAgentToolContract : 'MCP Agent Tool Contract';
    requirement <RTG018> mcpOutcomeIntegrity : 'MCP Outcome Integrity';
    requirement <VEL001> ownerControlledMemory : 'Owner Controlled Memory';
    requirement <VEL002> observableFailure : 'Observable Failure';
    requirement <VEL003> rtgCompatibility : 'RTG Compatibility';
    requirement <VEL004> simpleIndividualOperation : 'Simple Individual Operation';

    satisfy graphInvariants by vellis.memory;
    satisfy semanticQueryMeaning by vellis.memory;
    satisfy querySafety by vellis.memory;
    satisfy atomicCanonicalRevision by vellis.memory;
    satisfy definitionCardinality by vellis.memory;
    satisfy nonDisruptiveDefinitionWork by vellis.memory;
    satisfy validationCoverage by vellis.memory;
    satisfy durableCanonicalHistory by vellis.memory;
    satisfy canonicalSnapshotCompleteness by vellis.memory;
    satisfy replayEquivalence by vellis.memory;
    satisfy historicalStateCorrectness by vellis.memory;
    satisfy historicalRestoreSemantics by vellis.memory;
    satisfy dualLedgerSeparation by vellis.memory;
    satisfy agentDefinitionDiscoverability by vellis.memory;
    satisfy explicitGraphChangeSet by vellis.memory;
    satisfy boundedHistoryRead by vellis.memory;
    satisfy mcpAgentToolContract by vellis.memory;
    satisfy mcpOutcomeIntegrity by vellis.memory;
    satisfy ownerControlledMemory by vellis;
    satisfy observableFailure by vellis;
    satisfy rtgCompatibility by vellis;
    satisfy simpleIndividualOperation by vellis;
}
