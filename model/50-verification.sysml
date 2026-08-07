package VellisVerification {
    private import RTGSystem::*;
    private import Vellis::*;
    private import VellisRequirements::*;

    verification def 'Graph Invariants Hold' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Exercise anchors, associated data, direct associations, and links
             * across valid and invalid identity, kind, type, endpoint, property,
             * link-role multiplicity, direct-association multiplicity, JSON,
             * closed size bounds, inclusive numeric bounds, permitted values,
             * string patterns, required non-empty anchor display names, and
             * live-value cases. Reject unknown object type keys, kind-mismatched
             * type keys, duplicate active type keys across kinds, and empty,
             * inverted, duplicate, and JSON-kind-
             * incompatible property rules, including empty or duplicate property
             * names within one associated-data type. Accept an absent optional
             * property, and reject a missing required property, an undeclared
             * property, or a present value that violates its declared rule.
             * Reject duplicate natural identities or participating members in
             * multiplicity rules, and show distinct overlapping rules all apply.
             * Every accepted graph conforms and every invalid proposal changes
             * no canonical state or revision.
             */
            verify VellisRequirements::graphInvariants;
        }
    }

    verification def 'Semantic Query Selects And Shapes' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Query one anchor type broadly, narrow it by known anchor UUIDs,
             * select associated data once by type and direct association alone
             * and once with structured value comparisons, constrain anchor and
             * associated-data endpoint groups by directed link type and optional
             * link UUIDs, and show each result row contains only the requested
             * named anchor, link, data, and property projections at the evaluated
             * revision. Reject a comparison incompatible with its active property
             * definition, and distinguish an omitted property from a present null
             * when applying equality and inequality.
             * Show each row is one jointly satisfying assignment with exactly one
             * binding per requested projection, including an absent-valued binding
             * only for a projected missing optional property, present-valued
             * bindings for both non-null and JSON-null properties, and that identical
             * projected tuples occur once. Every binding identifies its projection
             * and the result identifies its query. Repeat against current state, a selected revision, and
             * a selected time; all use the same meaning. Alternative evaluation
             * orders produce equivalent rows. After a definition change, repeat
             * a query after cold discovery of the historical vocabulary at an
             * earlier revision and show that evaluation uses the definitions
             * active there.
             */
            verify VellisRequirements::semanticQueryMeaning;
        }
    }

    verification def 'Invalid Query Is Read Only' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Exercise empty or duplicate query-local names, unknown and incompatible
             * type keys, out-of-query references, endpoint directions, anchor
             * and link UUIDs, duplicate UUID restrictions, property names, incompatible comparisons,
             * malformed projections, and an
             * unrequested result binding, zero maximum, and a result exceeding
             * its positive maximum, plus a result the system cannot return
             * completely. Show findings, no partial result rows, and unchanged
             * graph, definitions, delta, revision, and canonical history, while
             * one rejection observation may be appended to activity history.
             */
            verify VellisRequirements::querySafety;
        }
    }

    verification def 'Every Canonical Transition Is Atomic' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Exercise accepted graph mutation, delta create or edit, delta
             * discard, definition activation, and historical restoration. Each
             * advances exactly one revision with one
             * contiguous replay-sufficient, kind-compatible record. Show each
             * kind changes only its permitted state facets. A rejection and
             * failure in every family change no canonical state or revision.
             * For graph mutation, use mixed complete-object upserts and UUID
             * removals, then reject duplicate commands, conflicts, unknown
             * removals, kind changes, invalid references, and an assumed cascade.
             * Show the accepted graph-change record carries those semantic upserts
             * and removals rather than a complete replacement graph; historical
             * restoration alone carries a replacement graph. An effective no-op
             * creates neither revision nor record.
             */
            verify VellisRequirements::atomicCanonicalRevision;
            verify VellisRequirements::explicitGraphChangeSet;
        }
    }

    verification def 'Cold Agent Discovers Evaluated Definitions' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Starting with no graph knowledge, retrieve every current anchor
             * type and description, evaluated revision, and delta presence.
             * Simulate inability to return the complete summary and show no
             * summaries or current-state metadata are returned.
             * Select several anchors and show their complete associated-data,
             * property, endpoint, link-role, and multiplicity neighborhoods with
             * descriptions and no unrelated definitions. Unknown and duplicate
             * selections return findings and no partial details. Retrieve the
             * sole proposal whole with its current assessment, or normal absence.
             * With no intervening definition change, show summary and inspection
             * revisions agree. Change active definitions between the two calls,
             * show the differing revisions expose the stale summary, then repeat
             * discovery successfully without a session or lock.
             * Select a revision and a time where definitions later retired were
             * active. Show summary and inspection return those definitions and
             * delta presence at one consistent evaluated revision; reuse a time
             * summary's resolved revision for inspection and graph query. Reject
             * unresolved selections with no partial summary, detail, or evaluated
             * revision. Confirm whole-delta retrieval remains current-only. All
             * reads leave canonical state and revision unchanged while recording
             * their observational outcomes after result selection.
             */
            verify VellisRequirements::agentDefinitionDiscoverability;
        }
    }

    verification def 'Definition Work Is Singular And Non Disruptive' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Through create, repeated edit, assessment, invalid activation,
             * valid activation, discard, and replay, show exactly one active set,
             * at most one delta, unchanged graph and active definitions during
             * delta work, canonical preservation on failure, and singular activation.
             * Stage a proposal with an empty description and show its automatic
             * finding and inspectability. Separately record owner review of
             * readability in the owner-facing governance scenario, while
             * automatic activation checks only non-emptiness. Show activation
             * remains blocked while any description is empty. With no delta,
             * staging the active set is an accepted no-op; with a delta,
             * re-staging the same proposal is an accepted no-op and staging the
             * active set cannot implicitly discard the proposal. Activation that
             * clears a delta remains a canonical transition. Show a valid proposal
             * can remain staged across later interactions without requiring
             * activation or discard.
             */
            verify VellisRequirements::definitionCardinality;
            verify VellisRequirements::nonDisruptiveDefinitionWork;
        }
    }

    verification def 'Validation Covers Every Scope' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Produce governing-outcome findings for a well-formed but invalid
             * graph query, graph change, replay, and v1 recovery candidate. Show
             * malformed typed input is rejected before a domain outcome exists.
             * Show the parameterless public check produces a graphConformance
             * report for current graph state, while whole-delta retrieval and
             * staging produce definitionDelta reports. Reports
             * identify implicated modeled definitions and graph objects when
             * available and create no separate canonical validation state. Show
             * an unexpected check failure produces no successful report.
             */
            verify VellisRequirements::validationCoverage;
        }
    }

    verification def 'Canonical History Is Durable And Contiguous' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Starting from the initial record, commit representative canonical
             * transitions, restart the ordinary process boundary, and show the
             * same complete ordered records with one uninterrupted prior-to-
             * resulting revision chain, stable earlier records, and no activity
             * record in canonical history. Show the initial record establishes
             * its contained revision, every transition establishes its resulting
             * revision, and the current graph, definitions, delta, and revision
             * equal replay through the final record before and after restart.
             */
            verify VellisRequirements::durableCanonicalHistory;
        }
    }

    verification def 'Canonical Snapshot Is Complete And Read Only' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Capture snapshots with and without an in-flight delta. Show each
             * contains equivalent graph, active definitions, optional delta,
             * and revision, identifies the exact canonical record establishing
             * that revision, and changes no canonical state, revision, or history.
             */
            verify VellisRequirements::canonicalSnapshotCompleteness;
        }
    }

    verification def 'Snapshot And Tail Replay Is Equivalent' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Initialize a fresh RTG from a complete snapshot, then apply every
             * later contiguous same-ledger canonical transition from the exact
             * captured source record. Show equivalent graph,
             * active definitions, optional delta, and final revision without
             * inventing a revision or reading activity history. Show the fresh
             * RTG owns one initial record containing the reconstructed final
             * state and does not claim transitions before that history base.
             */
            verify VellisRequirements::replayEquivalence;
        }
    }

    verification def 'Invalid Ledger Tail Fails Safely' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Replay tails with a gap, duplicate, reorder, mismatched base,
             * invalid or kind-incompatible semantic change, and incompatible
             * result. Supply a tail from another ledger whose preceding record
             * has the same revision number and show it is rejected because record
             * identity and ledger lineage do not match. Show observable findings
             * and no partially accepted state.
             */
            verify VellisRequirements::replayEquivalence;
        }
    }

    verification def 'Historical Selection Is Correct' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Select a revision directly and query before, at, and between
             * committed instants using the same bounded graph-query semantics as
             * current evaluation. Exactly one selector kind is accepted, each
             * resolvable time selects the greatest revision at or before it, and
             * every returned result changes no canonical state. Starting cold,
             * discover definitions later retired, then use a time summary's exact
             * resolved revision for inspection and graph query with consistent results.
             */
            verify VellisRequirements::historicalStateCorrectness;
        }
    }

    verification def 'Restore Appends Without Rewriting' {
        subject system : 'RTG System';
        objective {
            doc /*
             * With no delta, restore prior graph and active definitions and show
             * one new revision and record with no delta while all earlier records
             * remain unchanged. With a delta, show refusal and no state change.
             */
            verify VellisRequirements::historicalRestoreSemantics;
        }
    }

    verification def 'Activity History Cannot Affect Replay' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Record reads, validation, rejections, failures, and snapshot
             * activity with capability, outcome category, provenance, evaluated
             * revision when applicable, bounded semantic scope, and summaries
             * after each outcome is
             * determined. Query activity history and show the result is selected
             * before its own observation is appended and therefore never includes
             * itself. Vary owner-directed activity retention and disclosure, then
             * show identical reconstructed state from the unchanged canonical source.
             * Show no activity summary copies result rows, canonical payloads, or
             * inferred intent and no activity append reconstructs canonical state.
             * Reject one retention request and show every preexisting activity
             * record remains while only the failure observation may be appended.
             * Query canonical and activity records separately with chronological
             * bounds and a positive maximum; show one owner-facing entry per
             * selected record, both bounds included, original ledger order preserved,
             * no mixed entry families, and whole rejection when either result
             * exceeds its bound, cannot be returned completely, or its start follows
             * its end. Show canonical entries omit canonical state and replay-
             * sufficient changes while retaining revision, kind, time, provenance,
             * and semantic summary needed for owner review.
             */
            verify VellisRequirements::dualLedgerSeparation;
            verify VellisRequirements::boundedHistoryRead;
        }
    }

    verification def 'MCP Tool Surface Is Typed And Portable' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Discover exactly rtg_definition_summary,
             * rtg_definition_inspect, rtg_definition_delta, rtg_query,
             * rtg_change, rtg_set_definition_delta,
             * rtg_activate_definition_delta, rtg_discard_definition_delta,
             * rtg_check, and rtg_history with typed object outputs and typed
             * object inputs only where the operation has semantic input. Show
             * rtg_definition_summary carries its optional selector directly,
             * without an empty request type, and remaining parameterless tools
             * introduce no empty domain request type.
             * Invoke every tool through core MCP discovery and invocation alone,
             * without any additional MCP capability.
             */
            verify VellisRequirements::mcpAgentToolContract;
        }
    }

    verification def 'MCP Outcomes Preserve RTG Meaning' {
        subject system : 'RTG System';
        objective {
            doc /*
             * For representative reads and mutations within one trusted owner-
             * configured client scope, distinguish a semantic rejection from
             * malformed input and unexpected execution failure, preserving every
             * promised canonical and observational non-effect. Show accepted
             * outcomes contain their complete purpose-specific payload, rejected
             * and safely reported failed outcomes contain no success payload, and
             * malformed input or unexpected tool failure produces no completed
             * domain result. Show the tools do not decide per-call authorization
             * or owner approval, structured and
             * textual representations communicate equivalent typed meaning, and
             * changing or removing advisory annotations cannot change authorization,
             * validation, atomicity, or any failure non-effect.
             */
            verify VellisRequirements::mcpOutcomeIntegrity;
        }
    }

    verification def 'Owner Governs Personal Memory' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Within the pre-established trusted-agent context, show the owner
             * controls memory and activity disclosure and retention. Show an
             * owner-declined context proposal invokes no graph change, while an
             * approved proposal is submitted and retained only if valid. Exercise
             * correction, forgetting, definition changes including review of
             * description readability and leaving a proposal staged, snapshots,
             * and restoration. Show activity-retention changes leave canonical
             * state and replay unchanged.
             */
            verify VellisRequirements::ownerControlledMemory;
        }
    }

    verification def 'Failures Are Observable And Safe' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Exercise semantic rejection and execution failure. The affected
             * participant receives a distinct outcome,
             * and every promised graph, definition, canonical-history, activity-
             * history, and revision non-effect holds.
             */
            verify VellisRequirements::observableFailure;
        }
    }

    verification def 'V1 Snapshot Initializes Compatible Memory' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Analyze representative complete v1 JSON snapshots. Treat absent
             * system.live as true; import live objects and closed live relationships
             * while reporting omitted non-live candidates. Show UUIDs, kinds,
             * type keys, display names, nested JSON, metadata, direct associations,
             * link direction, and endpoints are lossless. Give only an unnamed
             * anchor "[recovered] {typeKey} {uuid}" from its stored values.
             * Translate active definitions by natural identity, discarding UUID
             * and lifecycle metadata while exactly preserving supported property,
             * endpoint, requiredness, range, permitted-value, multiplicity, and
             * cardinality meaning. Preview every narrowing, removed refinement,
             * synthesized description, omission, and untranslatable constraint,
             * then require owner confirmation of that exact candidate/report pair.
             * Show accepted first-use initialization has the unchanged graph and
             * translated definitions at revision 0, no delta, one initial record
             * with import provenance and bounded summary, no transitions, empty
             * activity history, and a new lineage without v1 ledger history,
             * transaction metadata, or storage/runtime metadata.
             * Refuse an existing-system import, changed-input confirmation,
             * mixed-kind used property, duplicate or kind-conflicting identity,
             * dangling live relationship, unresolved used type, and any other
             * preservation failure with no partial canonical or activity state.
             * Show v1 Everyday Life keys remain unchanged with no v2 starter overlay.
             */
            verify VellisRequirements::v1SnapshotCompatibility;
        }
    }

    verification def 'One Owner Begins Using One Cohesive System' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Start once blank, once with the Everyday Life starter, once from a
             * complete v2 snapshot plus later records, and once from a confirmed
             * compatible v1 snapshot. Show one owner can query, preserve,
             * and govern the resulting system and sole definition delta without
             * tenant, organization, role, cluster, server-fleet, or enterprise-
             * infrastructure administration and without internal RTG subsystems.
             */
            verify VellisRequirements::simpleIndividualOperation;
        }
    }

    verification def 'Canonical Equality Decides No Ops' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Compare Boolean, number, string, array, object, and null JSON
             * values. Show JSON kinds remain distinct, 1 and 1.0 have equal exact
             * mathematical value, array order matters, object-member order does
             * not, and a missing property differs from null. Reorder graph-object,
             * definition, association, and participating-type sets and show an
             * accepted effective no-op with no revision, transition, or delta.
             * Change a description, pattern expression text, graph-object value,
             * endpoint, or association and show a semantic difference. Show type,
             * property, endpoint-rule, and multiplicity natural identities decide
             * whether content is an edit, addition, removal, or invalid duplicate.
             * Compare canonical states and show revision, delta presence, and
             * proposed-definition content also participate.
             */
            verify VellisRequirements::canonicalSemanticEquality;
        }
    }

    verification def 'String Patterns Validate Stored Values' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Activate a stringValue property with a valid RE2 expression and
             * show whole-string matching accepts a conforming present value and
             * rejects prefix, suffix, and otherwise nonmatching values. Accept an
             * absent optional property. Combine pattern, size, and permitted
             * values and show every present condition applies, including rejection
             * of a listed permitted string that does not match. Reject a malformed
             * expression, RE2-unsupported lookaround or backreference, and a
             * pattern on every non-string JSON kind. Every rejection preserves
             * graph, definitions, delta, revision, and canonical history. Discover
             * the exact active expression. Change only its text and show a
             * meaningful definition change even when the expressions recognize
             * the same language. Confirm query comparisons remain the existing
             * closed set and ordered comparisons remain number-only.
             */
            verify VellisRequirements::stringPatternValidation;
        }
    }

    verification def 'Fresh RTG Begins At Revision Zero' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Initialize one state-free RTG with an empty valid definition set
             * and another with a non-empty valid set. Show each has revision 0,
             * an empty graph, exactly the supplied active definitions, no delta,
             * one equivalent initial-state record, no transitions, and an empty
             * activity ledger. Reject an invalid initial set and a request against
             * an already initialized RTG without establishing partial state.
             * Initialize separately from a snapshot and show its definitions and
             * revision are reconstructed without any fresh-start overlay. Initialize
             * separately from a confirmed v1 candidate and show its graph and
             * translated definitions form revision 0 with no transitions or activity.
             */
            verify VellisRequirements::freshInitialization;
        }
    }

    verification def 'Everyday Life Is An Optional Confirmed Start' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * With no prior state, show blank and Everyday Life are the complete
             * choice set, Everyday Life is recommended and preselected, and
             * neither choice initializes before explicit owner confirmation.
             * Confirm blank and show empty definitions. Confirm Everyday Life and
             * show exactly twelve anchor types, twelve optional profile types,
             * nine links, and twenty-four profile multiplicity rules with no
             * graph objects or example data. Inspect every profile and endpoint
             * neighborhood and show it matches the modeled starter. For each
             * date-like property, accept 2024-02-29; reject 2024-2-9, 2024-13-01,
             * 2024-01-00, and arbitrary text; accept absent dates and show
             * 2023-02-31 is lexically accepted without claiming calendar validity.
             * Initialize from a v2 snapshot and a v1 snapshot and show no starter
             * overlay. Show an
             * existing system has no separate starter-install operation and may
             * use only ordinary owner-controlled definition governance.
             */
            verify VellisRequirements::recommendedEverydayLifeStart;
            verify VellisRequirements::freshInitialization;
            verify VellisRequirements::graphInvariants;
        }
    }

    verification def 'Current Operations Ignore History Length' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Construct canonically equivalent current graph, active definitions,
             * optional delta, and revision projections backed by short and long
             * logical histories. Instrument semantic record accesses while
             * performing current definition summary and inspection, current graph
             * query, current conformance assessment, delta retrieval, and ordinary
             * change validation. Show each performs constant historical-record
             * work while scaling only with current state, proposal, and requested
             * return bounds. Commit one effective canonical mutation and show the
             * current projection update and one appended transition are recoverably
             * atomic without traversing or rewriting the earlier logical prefix.
             * Append activity and show it neither visits the canonical prefix nor
             * reconstructs canonical state.
             */
            verify VellisRequirements::historyIndependentCurrentWork;
            verify VellisRequirements::atomicCanonicalRevision;
        }
    }

    verification def 'Historical Selection Avoids Irrelevant Records' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Select equally narrow canonical and activity intervals behind
             * differently sized excluded prefixes. Instrument semantic record
             * accesses and show expected work is logarithmic selection plus the
             * returned interval, with no linear visit of preceding records. Hold
             * definition-changing history fixed while increasing unrelated
             * graph-only transitions; retrieve a historical definition summary
             * and focused inspection and show no linear growth from those graph
             * mutations. Resolve revision and time selections without a complete-
             * ledger scan. Use equivalent access traces when direct counters are
             * unavailable; do not use unstable wall-clock assertions.
             */
            verify VellisRequirements::boundedHistoricalSelectionWork;
            verify VellisRequirements::historicalStateCorrectness;
            verify VellisRequirements::boundedHistoryRead;
        }
    }

    verification def 'Replay Work Is Characterized By Required Tail' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Reconstruct and ordinarily restart equivalent states across
             * increasing required replay-tail lengths. Record semantic record
             * visits and startup or replay duration with their measurement units,
             * demonstrate replay equivalence, and characterize the dependency on
             * required tail length without asserting a numerical performance target.
             */
            verify VellisRequirements::replayEquivalence;
            verify VellisRequirements::durableCanonicalHistory;
        }
    }

    verification def 'Cold Agent Prepares Incremental Improvement' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Starting cold, have an externally scheduled owner-configured agent
             * read explicit bounded intervals from both ledgers, discover the
             * definitions active at evaluated revisions, and issue bounded current
             * and historical graph queries. Continue a later run from the prior
             * processed interval instead of rereading all history. Prepare a
             * traceable cleanup proposal for stale data, repeated failure, or
             * unused vocabulary; rediscover current definitions before preparing
             * the current change. Show scheduling and inference remain external,
             * owner approval is required before mutation, and a declined proposal
             * creates no canonical mutation.
             */
            verify VellisRequirements::ownerVisibleImprovementAnalysis;
            verify VellisRequirements::ownerControlledMemory;
        }
    }

    analysis def 'History Growth Performance Characterization' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Independently vary current graph size, canonical-ledger length,
             * definition-change density, activity-history length, selected
             * interval size, and required replay-tail length. Measure semantic
             * record visits, current-operation work, historical-selection work,
             * replay and startup duration with explicit units, and storage growth.
             * Use the resulting evidence to select later numerical latency,
             * startup, and storage budgets only after a runtime, hardware profile,
             * and representative owner dataset exist. This analysis does not
             * claim satisfaction of any numerical performance target.
             */
        }
    }

    verification graphInvariants : 'Graph Invariants Hold' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification semanticQuery : 'Semantic Query Selects And Shapes' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification invalidQuery : 'Invalid Query Is Read Only' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification definitionDiscovery : 'Cold Agent Discovers Evaluated Definitions' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification atomicTransitions : 'Every Canonical Transition Is Atomic' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification definitionWork : 'Definition Work Is Singular And Non Disruptive' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification validationCoverage : 'Validation Covers Every Scope' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification durableHistory : 'Canonical History Is Durable And Contiguous' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification snapshotCompleteness : 'Canonical Snapshot Is Complete And Read Only' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification snapshotReplay : 'Snapshot And Tail Replay Is Equivalent' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification invalidTail : 'Invalid Ledger Tail Fails Safely' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification historicalSelection : 'Historical Selection Is Correct' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification restoreHistory : 'Restore Appends Without Rewriting' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification activitySeparation : 'Activity History Cannot Affect Replay' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification mcpToolSurface : 'MCP Tool Surface Is Typed And Portable' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification mcpOutcomes : 'MCP Outcomes Preserve RTG Meaning' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification ownerControl : 'Owner Governs Personal Memory' {
        subject redefines system = VellisRequirements::vellis;
    }
    verification observableFailure : 'Failures Are Observable And Safe' {
        subject redefines system = VellisRequirements::vellis;
    }
    verification v1Compatibility : 'V1 Snapshot Initializes Compatible Memory' {
        subject redefines system = VellisRequirements::vellis;
    }
    verification simpleOperation : 'One Owner Begins Using One Cohesive System' {
        subject redefines system = VellisRequirements::vellis;
    }
    verification canonicalEquality : 'Canonical Equality Decides No Ops' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification stringPatterns : 'String Patterns Validate Stored Values' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification freshInitialization : 'Fresh RTG Begins At Revision Zero' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification everydayLifeStart : 'Everyday Life Is An Optional Confirmed Start' {
        subject redefines system = VellisRequirements::vellis;
    }
    verification currentWorkScaling : 'Current Operations Ignore History Length' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification historicalSelectionScaling : 'Historical Selection Avoids Irrelevant Records' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification replayCharacterization : 'Replay Work Is Characterized By Required Tail' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
    verification improvementAnalysis : 'Cold Agent Prepares Incremental Improvement' {
        subject redefines system = VellisRequirements::vellis;
    }
    analysis historyGrowth : 'History Growth Performance Characterization' {
        subject redefines system = VellisRequirements::vellis.memory;
    }
}
