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
             * closed size bounds, inclusive numeric bounds, permitted values, and
             * live-value cases. Reject unknown object type keys, kind-mismatched
             * type keys, duplicate active type keys across kinds, and empty,
             * inverted, duplicate, and JSON-kind-
             * incompatible property rules, including empty or duplicate property
             * names within one associated-data type. Accept an absent optional
             * property, and reject a missing required property, an undeclared
             * property, or a present value that violates its declared rule.
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
             * a query whose historical vocabulary the caller already knows at an
             * earlier revision and show that evaluation uses the definitions active
             * at that revision. Show current-only discovery makes no claim to
             * discover retired vocabulary.
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
             * discard, definition activation, historical restoration, and
             * predecessor recovery. Each advances exactly one revision with one
             * contiguous replay-sufficient, kind-compatible record. Show each
             * kind changes only its permitted state facets. A rejection and
             * failure in every family change no canonical state or revision.
             * For graph mutation, use mixed complete-object upserts and UUID
             * removals, then reject duplicate commands, conflicts, unknown
             * removals, kind changes, invalid references, and an assumed cascade.
             * Show the accepted graph-change record carries those semantic upserts
             * and removals rather than a complete replacement graph; restoration
             * and recovery alone carry replacement graphs. An effective no-op
             * creates neither revision nor record.
             */
            verify VellisRequirements::atomicCanonicalRevision;
            verify VellisRequirements::explicitGraphChangeSet;
        }
    }

    verification def 'Cold Agent Discovers Active Definitions' {
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
             * Confirm that neither discovery operation accepts a historical
             * selector. All reads leave canonical state and revision unchanged
             * while recording their observational outcomes after result selection.
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
             * graph query, graph change, replay, and predecessor recovery. Show
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
             * record in canonical history.
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
             * and revision and that capture changes no canonical state, revision,
             * or canonical history.
             */
            verify VellisRequirements::canonicalSnapshotCompleteness;
        }
    }

    verification def 'Snapshot And Tail Replay Is Equivalent' {
        subject system : 'RTG System';
        objective {
            doc /*
             * Initialize a fresh RTG from a complete snapshot, then apply every
             * later contiguous canonical transition. Show equivalent graph,
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
             * result. Show observable findings and no partially accepted state.
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
             * every returned result changes no canonical state. Use caller-known
             * vocabulary valid at each selected historical revision.
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
             * activity with provenance and summaries after each outcome is
             * determined. Query activity history and show the result is selected
             * before its own observation is appended and therefore never includes
             * itself. Vary owner-directed activity retention and disclosure, then
             * show identical reconstructed state from the unchanged canonical source.
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
             * parameterless tools introduce no empty domain request type.
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

    verification def 'Predecessor RTG Meaning Is Preserved' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Recover representative predecessor examples and show stable UUIDs
             * and kinds, direct associations distinct from links, directed
             * anchor or associated-data endpoints, lossless nested JSON, and
             * missing system.live normalized to true. Accepted recovery is one
             * replayable transition; invalid recovery changes no canonical state.
             */
            verify VellisRequirements::rtgCompatibility;
        }
    }

    verification def 'One Owner Begins Using One Cohesive System' {
        subject system : 'Vellis System';
        objective {
            doc /*
             * Start once with an empty valid RTG and once from a complete
             * snapshot plus later records. Show one owner can query, preserve,
             * and govern the resulting system and sole definition delta without
             * tenant, organization, role, cluster, server-fleet, or enterprise-
             * infrastructure administration and without internal RTG subsystems.
             */
            verify VellisRequirements::simpleIndividualOperation;
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
    verification definitionDiscovery : 'Cold Agent Discovers Active Definitions' {
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
    verification predecessorCompatibility : 'Predecessor RTG Meaning Is Preserved' {
        subject redefines system = VellisRequirements::vellis;
    }
    verification simpleOperation : 'One Owner Begins Using One Cohesive System' {
        subject redefines system = VellisRequirements::vellis;
    }
}
