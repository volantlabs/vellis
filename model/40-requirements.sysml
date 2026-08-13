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
         * inclusive numeric-bound, permitted-value, and string-pattern meaning;
         * endpoint constraints; directed link multiplicity; and direct-association
         * multiplicity. Every anchor shall have a non-empty display name.
         * Every graph object's type key shall resolve to exactly one active type
         * definition of the same object kind, and active type keys shall be
         * unique across the shared namespace.
         * A size condition shall apply only to string, array, or object values,
         * contain at least one bound, and never invert its bounds. String size
         * shall be its number of Unicode code points without normalization;
         * array and object size shall be their number of elements and members.
         * A value range shall contain at least one inclusive numeric bound or
         * permitted value;
         * numeric bounds shall be ordered, permitted values shall be unique and
         * match the property's JSON kind, and coexisting forms shall both hold.
         * A string pattern shall occur only on a stringValue property and every
         * listed permitted string shall match it. Duplicate multiplicity-rule
         * natural identities and duplicate participating types shall be invalid;
         * distinct overlapping multiplicity rules shall all hold conjunctively.
         * Property names shall be non-empty and unique within each associated-
         * data type definition. Each associated-data object's properties shall
         * use only names declared by its active type definition, include every
         * required property, and validate every present required or optional
         * property against its declared JSON kind, shape, range, and pattern.
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
         * revision shall govern property kind, shape, range, pattern validation,
         * and endpoint validity.
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
         * Evaluation shall not multiply work across selector components
         * disconnected from every projected selector. Such a component shall
         * affect the result only through whether it has at least one satisfying
         * assignment. Query work may scale with candidates and conditions inside
         * a component that can change a projected tuple, with combinations of
         * projected components, and with distinct rows needed to decide the
         * caller's maximum.
         */
    }

    requirement def 'Atomic Canonical Revision' {
        subject system : 'RTG System';
        doc /*
         * Every accepted canonical state change shall advance the one total
         * revision exactly once and commit its semantic change and contiguous
         * transition record recoverably atomically. The updated current graph,
         * active definitions, optional delta, and revision projection and the
         * appended transition shall become recoverable as one effect. Rejected
         * or failed operations shall change no canonical state or revision. An accepted
         * effective no-op shall create neither a revision nor a transition.
         */
    }

    requirement def 'Definition Cardinality' {
        subject system : 'RTG System';
        doc /*
         * At every established revision, the current canonical-state projection
         * shall contain exactly one active definition set and zero or one
         * definition delta.
         */
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
         * replayed state, and v1 recovery candidates. Validation reports shall
         * identify only the assessment scopes that currently return reports: complete
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
         * for deterministic replay without activity history. Every initial record
         * shall establish its contained-state revision and every transition shall
         * establish its resulting revision. Current graph, active definitions,
         * optional delta, and revision shall form one current canonical-state
         * projection of replay through the final canonical record and shall not
         * form parallel authority. No permitted current-state tuple shall mix
         * values established by different canonical records. An initial base
         * seeded from reconstructed snapshot state shall not claim
         * omitted earlier transitions. Each transition's semantic change shall be
         * valid for its kind. An ordinary graph mutation record shall carry its
         * accepted graph change rather than a complete replacement graph. Only
         * historical restoration may carry a complete replacement graph.
         */
    }

    requirement def 'Canonical Snapshot Completeness' {
        subject system : 'RTG System';
        doc /*
         * A canonical snapshot shall be a self-contained, lossless capture of
         * graph, active definitions, optional in-flight delta, and total
         * revision and shall identify the exact canonical record it captures.
         * Creating it shall not change canonical state or revision.
         */
    }

    requirement def 'Replay Equivalence' {
        subject system : 'RTG System';
        doc /*
         * Replay from an initial record or complete snapshot plus an optional
         * contiguous later same-ledger tail shall reconstruct equivalent graph,
         * active definitions, optional delta, and revision without activity
         * history. A snapshot shall identify the exact record it captures and a
         * tail shall identify the exact record it follows. A tail from another
         * ledger shall be rejected even when its preceding revision number is
         * equal. Initializing a fresh RTG shall seed its owned history with the
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
         * committed revision at or before it. Definition summary and focused
         * inspection shall accept the same optional selector, return definitions
         * active at the exact evaluated revision and delta presence at that state,
         * and reject unresolved selections without partial content or evaluated
         * revision. A caller may reuse a time-based summary's resolved revision
         * for inspection and graph query. Definition-delta retrieval remains
         * current-only.
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
         * never establish canonical state or trigger canonical reconstruction.
         * Each activity summary shall identify capability, outcome category,
         * provenance, evaluated revision when applicable, and bounded semantic
         * scope without copying result rows, canonical payloads, or inferred
         * intent. Owner-directed retention may change
         * only activity history and shall not affect reconstruction.
         */
    }

    requirement def 'Agent Definition Discoverability' {
        subject system : 'RTG System';
        doc /*
         * Every active type and rule definition shall have a non-empty,
         * owner-readable description. Automatic assessment shall establish only
         * presence and non-emptiness; owner review shall establish readability.
         * A complete shallow read shall return every anchor type active at the
         * current or selected historical state, its description, the evaluated
         * revision, and delta presence at that state, or no summaries when it
         * cannot return the complete vocabulary. A focused read shall return the
         * complete relevant definition neighborhood at its own identified
         * evaluated revision
         * for each selected anchor and no unrelated definitions. A caller shall
         * be able to detect an intervening definition change by comparing the
         * summary and inspection revisions. Unknown, duplicate, or
         * incompletely answerable selections shall return findings and no partial
         * details or evaluated revision. The sole current proposed set shall
         * remain separately retrievable whole with its current assessment;
         * historical discovery shall not change delta retrieval. All discovery
         * shall change no canonical state or revision, while its operation attempt may be recorded
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
         * Activity entries shall expose time, provenance, capability, outcome
         * category, optional evaluated revision, bounded
         * semantic scope, and summary. A start after its end shall be invalid.
         * A result shall never mix entry families, paginate silently, mutate
         * canonical state, or treat activity as replay authority.
         */
    }

    requirement def 'History Independent Current Work' {
        subject system : 'RTG System';
        doc /*
         * Current definition summary and inspection, current graph query,
         * current conformance assessment, delta retrieval, and ordinary change
         * validation shall use the current canonical-state projection and shall
         * not traverse canonical or activity history to rediscover current state.
         * Their work may scale with the current state facets and candidate
         * relationships their meaning requires, active or proposed definitions,
         * requested return bounds, and proposed change size. Routine current work
         * shall not require retaining the complete canonical-state tuple or complete
         * graph in process memory between invocations. Definition-only summary and
         * inspection shall not materialize graph objects. Current graph query shall
         * narrow candidates by the requested identities, types, direct associations,
         * and directed relationships before applying property comparisons and shall
         * not materialize unrelated graph objects merely because they are current.
         * Complete-state inspection, snapshot capture, replay, restoration, whole-
         * graph conformance, and change validation whose invariants require the whole
         * graph may materialize complete state explicitly. A value returned to a
         * caller shall not share mutable canonical state retained by the system.
         * No cache, database, serialization, indexing technology, or storage layout
         * is selected.
         * Canonical mutation and activity observation may perform constant
         * terminal-position and append work but shall neither traverse nor
         * rewrite the existing logical ledger prefix. Activity recording shall
         * remain observational and shall not trigger canonical reconstruction.
         */
    }

    requirement def 'Bounded Historical Selection Work' {
        subject system : 'RTG System';
        doc /*
         * Resolving a revision or time selector shall not linearly scan the
         * complete ledger. Selecting a bounded canonical or activity interval
         * shall perform no linear scan of records preceding that interval; its
         * expected semantic record-processing work shall be logarithmic selection
         * plus the returned interval. Historical definition summary and focused
         * inspection shall locate the revision and applicable definition-changing
         * records without replaying unrelated graph-only transitions. Historical
         * graph reconstruction, explicit replay, restoration, and startup recovery
         * may depend on their required replay tail and shall be characterized
         * separately. These constraints govern semantic record processing, not
         * physical database pages or a selected indexing technology.
         */
    }

    requirement def 'MCP Agent Tool Contract' {
        subject system : 'RTG System';
        doc /*
         * The system shall expose exactly the selected ten stable, discoverable
         * MCP tool names. Every completed invocation shall return typed object
         * meaning; tools with semantic input shall accept typed object meaning.
         * Optional selection on definition summary shall be carried directly and
         * shall not introduce an empty request type. Other parameterless tools
         * shall introduce no empty domain request.
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

    requirement def 'V1 Snapshot Compatibility' {
        subject system : 'Vellis System';
        doc /*
         * Only before any v2 canonical state exists, Vellis shall analyze one
         * complete v1.0.0 JSON system snapshot into a transient complete target
         * graph, active definition set, and report bound to that exact source.
         * Missing v1 system.live shall mean true. The candidate shall contain
         * every live graph object and its closed live relationships, report every
         * omitted non-live candidate, and preserve UUID, object kind, type key,
         * display name, nested JSON, metadata, direct associations, link direction,
         * and endpoints exactly. Only an absent anchor display name shall use
         * "[recovered] {typeKey} {uuid}" from its exact stored values. After live
         * filtering, the graph shall already be closed and valid; Vellis shall
         * neither repair dangling relationships nor rewrite stored values.
         *
         * Active definitions shall translate by natural type and property
         * identity, discarding v1 definition UUID and lifecycle metadata while
         * exactly preserving representable type, property, endpoint, requiredness,
         * range, permitted-value, multiplicity, and active-cardinality meaning.
         * Unsupported refinements shall be removed, never replaced by invented
         * meaning. A property shall be retained only when one v2 JSON kind follows
         * from its v1 rule or all imported values. The report shall summarize
         * preserved graph content and identify every narrowing, removed refinement,
         * synthesized description, omitted unused
         * property or type, omitted query-pattern or migration-oriented constraint,
         * and untranslatable constraint. A definition may be omitted only when no
         * imported object, relationship, or retained definition depends on it.
         *
         * Initialization shall refuse atomically when unchanged graph data cannot
         * conform to translated definitions, including duplicate or kind-conflicting
         * natural identities, dangling endpoints, unresolved used types, or mixed
         * JSON kinds for one used v2 property. It shall omit v1 migrations, inactive
         * candidates, definition lifecycle state, ledger history, transaction and
         * storage/runtime metadata. V1 Everyday Life vocabulary shall retain its
         * original keys and shall never be reinterpreted as or overlaid with the v2
         * starter. The owner shall preview and confirm the exact candidate/report
         * pair. Acceptance shall establish the unchanged graph, translated active
         * definitions, no delta, revision 0, one initial record with import
         * provenance and a bounded recovery summary, no transitions, and an empty
         * activity ledger as a new v2 lineage. Decline, changed input, rejection,
         * failure, or an existing v2 state shall establish no canonical or activity
         * state; no merge or replacement behavior exists.
         */
    }

    requirement def 'Simple Individual Operation' {
        subject system : 'Vellis System';
        doc /*
         * From a clean supported local environment, one owner shall be able to
         * follow supplied setup guidance to prepare one local Vellis system and
         * connect one trusted owner-configured MCP agent. The owner shall be able
         * to initialize blank, with the recommended Everyday Life starter, from a
         * compatible v2 snapshot and tail, or from a confirmed compatible v1 JSON
         * snapshot; use, query, preserve, restart, and govern the one cohesive
         * system; and recover identical canonical memory for a later agent
         * interaction. Setup and connection failures shall identify the failed
         * stage, state whether initialization or established memory changed, and
         * supply an available corrective action. A generic failure without that
         * minimum guidance shall not be actionable. Such failures shall not corrupt
         * any already established canonical state; initialization failure shall
         * establish no partial canonical or activity state.
         * None of this shall require tenant, organization, role, cluster,
         * server-fleet, database, concurrent definition-delta, or enterprise-
         * infrastructure administration.
         */
    }

    requirement def 'Canonical Semantic Equality' {
        subject system : 'RTG System';
        doc /*
         * Every no-op, definition-delta comparison, graph comparison, replay
         * comparison, and permitted-value uniqueness decision shall use one
         * canonical semantic equality. JSON equality shall be kind-sensitive;
         * numbers shall compare by exact mathematical value, strings by exact
         * Unicode code-point sequence without normalization, arrays recursively
         * in order, and objects recursively without member-order significance,
         * with missing distinct from null. Graph equality shall include every
         * canonical object value, association, and directed
         * endpoint while ignoring order in unordered collections. Definition
         * equality shall use the modeled natural identities and include kind,
         * descriptions, and every structured rule. Reordering unordered content
         * shall be an effective no-op; changing canonical meaning shall not. Two
         * canonical states shall additionally require equal revision and equal
         * definition-delta presence and content.
         */
    }

    requirement def 'Fresh Initialization' {
        subject system : 'RTG System';
        doc /*
         * A fresh RTG initialized without prior state shall accept one internally
         * valid initial definition set and establish revision 0 with an empty
         * graph, exactly that active set, no definition delta, one matching
         * initial-state record, no transitions, and an empty activity ledger.
         * Refusal or failure shall establish no partial state. Snapshot-based
         * initialization shall use only reconstructed snapshot state and shall
         * not overlay fresh-start definitions. Confirmed v1 initialization shall
         * establish its complete recovery candidate at revision 0 as a new owned
         * history base with no transitions or activity records.
         */
    }

    requirement def 'String Pattern Validation' {
        subject system : 'RTG System';
        doc /*
         * An optional property pattern shall use Google RE2 syntax and Unicode
         * semantics with whole-string FullMatch behavior. The system shall reject
         * malformed or unsupported expressions and patterns on non-string
         * properties. Requiredness, shape, range, and pattern shall apply
         * conjunctively to present values, without requiring general
         * satisfiability analysis. Pattern expression text shall be discoverable
         * exactly and shall participate exactly in definition equality. Pattern
         * validation shall add no regex query comparison or ordered string
         * comparison.
         */
    }

    requirement def 'Recommended Everyday Life Start' {
        subject system : 'Vellis System';
        doc /*
         * When no prior state exists, Vellis shall offer blank and Everyday Life
         * fresh vocabulary choices, present Everyday Life as recommended and
         * preselected, and require explicit owner confirmation before either
         * initialization. Blank shall use an empty definition set; Everyday Life
         * shall use exactly the modeled Everyday Life starter definition set.
         * Neither choice shall create graph objects. Snapshot initialization
         * and v1 initialization shall not offer or overlay the starter, and
         * existing systems shall gain no separate starter-install behavior.
         */
    }

    requirement def 'Owner Visible Improvement Analysis' {
        subject system : 'Vellis System';
        doc /*
         * Vellis shall support an external owner-configured agent in using
         * explicit bounded canonical and activity intervals, evaluated historical
         * definitions, and bounded historical or current graph queries to prepare
         * traceable owner-visible findings about stale data, repeated failures,
         * unused vocabulary, and cleanup opportunities. Scheduled analysis shall
         * continue incrementally from its previously processed interval rather
         * than repeatedly requesting all history. Before proposing a current
         * graph change or definition delta, the agent shall rediscover current
         * definitions. Vellis shall add no scheduler, job registry, worker, or
         * inference authority. Automated analysis shall not bypass owner approval;
         * declined proposals shall create no canonical mutation.
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
    requirement <RTG019> canonicalSemanticEquality : 'Canonical Semantic Equality';
    requirement <RTG020> freshInitialization : 'Fresh Initialization';
    requirement <RTG021> stringPatternValidation : 'String Pattern Validation';
    requirement <RTG022> historyIndependentCurrentWork : 'History Independent Current Work';
    requirement <RTG023> boundedHistoricalSelectionWork : 'Bounded Historical Selection Work';
    requirement <VEL001> ownerControlledMemory : 'Owner Controlled Memory';
    requirement <VEL002> observableFailure : 'Observable Failure';
    requirement <VEL003> v1SnapshotCompatibility : 'V1 Snapshot Compatibility';
    requirement <VEL004> simpleIndividualOperation : 'Simple Individual Operation';
    requirement <VEL005> recommendedEverydayLifeStart : 'Recommended Everyday Life Start';
    requirement <VEL006> ownerVisibleImprovementAnalysis : 'Owner Visible Improvement Analysis';

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
    satisfy canonicalSemanticEquality by vellis.memory;
    satisfy freshInitialization by vellis.memory;
    satisfy stringPatternValidation by vellis.memory;
    satisfy historyIndependentCurrentWork by vellis.memory;
    satisfy boundedHistoricalSelectionWork by vellis.memory;
    satisfy ownerControlledMemory by vellis;
    satisfy observableFailure by vellis;
    satisfy v1SnapshotCompatibility by vellis;
    satisfy simpleIndividualOperation by vellis;
    satisfy recommendedEverydayLifeStart by vellis;
    satisfy ownerVisibleImprovementAnalysis by vellis;
}
