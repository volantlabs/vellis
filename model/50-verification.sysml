package VellisVerification {
    private import RTGSystem::*;
    private import Vellis::*;
    private import VellisRequirements::*;

    verification def 'Graph Invariants Hold' {
        subject system : 'RTG System';
        objective {
            require constraint {
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
             * Show composed é (U+00E9) has string size 1, e followed by U+0301
             * COMBINING ACUTE ACCENT has string size 2, and neither value is
             * normalized.
             * Reject duplicate natural identities or participating members in
             * multiplicity rules, and show distinct overlapping rules all apply.
             * Every accepted graph conforms and every invalid proposal changes
             * no canonical state or revision.
             */
            }
            verify VellisRequirements::graphInvariants;
        }
    }

    verification def 'Semantic Query Selects And Shapes' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Query one anchor type broadly, narrow it by known anchor UUIDs,
             * and narrow associated data by known associated-data UUIDs,
             * select associated data once by type and direct association alone
             * and once with structured value comparisons, constrain anchor and
             * associated-data endpoint groups by directed link type and optional
             * link UUIDs, and show each result row contains only the requested
             * named anchor, link, data, and property projections at the evaluated
             * revision. Reject a comparison incompatible with its active property
             * definition, and distinguish an omitted property from a present null
             * when applying equality and inequality.
             * Select one anchor group naming several active anchor types and show
             * it returns the anchors of each, identically to the union of the
             * per-type queries it replaces, and reject a group naming a type that
             * is not active.
             * Count, sum, minimise, and maximise one aggregate output target and
             * show each answers over its distinct matching object identities.
             * Show a count of zero where nothing matches
             * and an absent sum, minimum, and maximum where no match carries the
             * property. Hold an aggregating query's maximum below its matching
             * population and show it is refused whole exactly as a projected
             * result is. Reject an aggregation whose property its condition does
             * not define, whose operator cannot sum or order that property's
             * kind, or which omits a property its operator requires.
             * Compare aggregation with an independent semantic oracle and show
             * the same count, sum, minimum, and maximum over the same identities.
             * Order a number-valued property by exact mathematical value and a
             * string-valued property by exact Unicode code-point sequence,
             * including a value whose code-point order differs from its order
             * under case folding or locale collation. Reject an ordered
             * comparison of a null-, Boolean-, array-, or object-valued property,
             * and one whose expected value is of a different JSON kind from the
             * property.
             * Show each row is one jointly satisfying assignment with exactly one
             * binding per requested projection, including an absent-valued binding
             * only for a projected missing optional property, present-valued
             * bindings for both non-null and JSON-null properties, and that identical
             * projected tuples occur once. Show equal values from distinct source
             * data objects remain distinct rows. Every binding identifies its projection
             * and the result identifies its query. Repeat against current state,
             * the sole prospective overlay, a selected revision, and a selected
             * time; all use the same meaning. Alternative evaluation
             * orders produce equivalent rows. After a definition change, repeat
             * a query after cold discovery of the historical vocabulary at an
             * earlier revision and show that evaluation uses the definitions
             * active there.
             * Add a proposal-only type and changed proposed property rule and show
             * prospective selection accepts and applies them while current rejects
             * the proposal-only type and retains the active rule.
             * Exercise paths, stars, and branching selector trees. Independently
             * increase satisfying hidden witnesses on a connected branch and
             * show they govern existence without multiplying returned rows or
             * aggregate targets. Bind two compatible aliases to the same object
             * and use two endpoint aliases to discover a self-link, showing no
             * implicit alias-inequality constraint.
             * Hold a broad query's maximum fixed while increasing unrelated
             * matching rows and show identity selection stops at maximum plus one
             * and hydrates no more than that bounded candidate result.
             */
            }
            verify VellisRequirements::semanticQueryMeaning;
        }
    }

    verification def 'Invalid Query Is Read Only' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Exercise empty or duplicate query-local names, unknown and incompatible
             * type keys, out-of-query references, endpoint directions, anchor,
             * associated-data, and link UUIDs, duplicate UUID restrictions,
             * disconnected selectors, self-edges, parallel edges, longer cycles,
             * property names, incompatible comparisons, missing, empty, or mixed
             * output, malformed projections, and an
             * unrequested result binding, zero maximum, and a result exceeding
             * its positive maximum, plus a result the system cannot return
             * completely. Show findings, no partial result rows, and unchanged
             * graph, definitions, delta, revision, and canonical history, while
             * one rejection observation may be appended to activity history.
             * For query and definition discovery alike, accept current,
             * prospective, revision, and time selections. Reject prospective
             * without a delta, an unresolved revision or time, and a naive time,
             * preserving no partial payload and every canonical non-effect.
             * Reject count with a supplied property as well as sum, minimum, or
             * maximum without a required property.
             */
            }
            verify VellisRequirements::querySafety;
        }
    }

    verification def 'Every Canonical Transition Is Atomic' {
        subject system : 'RTG System';
        objective {
            require constraint {
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
             * Show graph mutation, activation, and historical restoration records
             * carry their semantic upserts and removals rather than a complete
             * replacement graph. Activation applies the exact assessed proposal
             * overlay and definitions together. An effective no-op
             * creates neither revision nor record.
             */
            }
            verify VellisRequirements::atomicCanonicalRevision;
            verify VellisRequirements::explicitGraphChangeSet;
        }
    }

    verification def 'Cold Agent Discovers Evaluated Definitions' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Starting with no graph knowledge, retrieve every current anchor
             * type and description, evaluated revision, and delta presence.
             * Simulate inability to return the complete summary and show no
             * summaries or current-state metadata are returned.
             * Select several anchors and show their complete associated-data,
             * property, endpoint, link-role, and multiplicity neighborhoods with
             * descriptions and no unrelated definitions. Unknown and duplicate
             * selections return findings and no partial details. Retrieve the
             * sole proposal through its identity, bounded definition discovery,
             * overlay counts, and current assessment, or normal absence, without
             * returning a whole proposal aggregate.
             * Add a proposal-only anchor and remove one active anchor; show the
             * prospective summary and detail include only the former while current
             * discovery retains only the latter.
             * With no intervening definition change, show summary and inspection
             * revisions agree. Change active definitions between the two calls,
             * show the differing revisions expose the stale summary, then repeat
             * discovery successfully without a session or lock.
             * Select a revision and a time where definitions later retired were
             * active. Show summary and inspection return those definitions and
             * delta presence at one consistent evaluated revision; reuse a time
             * summary's resolved revision for inspection and graph query. Reject
             * unresolved selections with no partial summary, detail, or evaluated
             * revision. Confirm proposal discovery remains current-only. All
             * reads leave canonical state and revision unchanged while recording
             * their observational outcomes after result selection.
             */
            }
            verify VellisRequirements::agentDefinitionDiscoverability;
        }
    }

    verification def 'Definition Work Is Singular And Non Disruptive' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Through create, repeated definition edit, graph upsert staging,
             * tombstone staging, explicit unstaging, prospective query,
             * assessment, invalid activation,
             * valid activation, discard, and replay, show exactly one active set,
             * at most one delta, unchanged active graph and definitions during
             * delta work, canonical preservation on failure, and singular activation.
             * Build a proposal larger than one request through several bounded
             * natural-keyed definition upserts and removals, including an
             * intermediate invalid reference, without any complete definition-set
             * request or resident definition-set document. On the first edit,
             * change one active definition and show an untouched active definition
             * remains in the proposal; later edits use that proposed meaning.
             * Stage a proposal with an empty description and show its automatic
             * finding and inspectability. Separately record owner review of
             * readability in the owner-facing governance scenario, while
             * automatic activation checks only non-emptiness. Show activation
             * remains blocked while any description is empty. With no delta,
             * staging the active set is an accepted no-op; with a delta,
             * re-staging the same proposal is an accepted no-op and staging the
             * active set cannot implicitly discard the proposal. Create a graph-
             * only delta, then reject unstaging its final entry with the delta and
             * revision unchanged. With an empty overlay, reject a definition edit
             * that would remove the final difference and show rejected status,
             * unchanged proposal identity and content, and unchanged revision;
             * accept the same definition edit while a non-empty graph overlay still
             * distinguishes the proposal. Explicit discard removes it. Activation that
             * clears a delta remains a canonical transition. Show a valid proposal
             * can remain staged across later interactions without requiring
             * activation or discard. Change an active UUID that is also staged,
             * show the assessment becomes stale while both values remain, then
             * reassess the exact effective proposal before activation.
             */
            }
            verify VellisRequirements::definitionCardinality;
            verify VellisRequirements::nonDisruptiveDefinitionWork;
        }
    }

    verification def 'Validation Covers Every Scope' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Produce governing-outcome findings for a well-formed but invalid
             * graph query, graph change, replay, and v1 recovery candidate. Show
             * malformed typed input is rejected before a domain outcome exists.
             * Request complete current and prospective assessments and show each
             * is bound to its exact revision and, for prospective work, exact
             * proposal identity. Deliberately produce more findings than one
             * response bound; show every finding is stored once, multiple ordered
             * pages retrieve the complete set without reassessment. Exercise zero
             * findings, exact-bound, first, middle, last, and out-of-range one-
             * based intervals. Replacing an assessment expires the prior retrieval
             * identity; a failed replacement preserves it; active or proposal
             * change leaves it readable but stale for activation. Reports identify
             * implicated modeled definitions and graph objects when available and
             * create no canonical validation state. Show an unexpected check
             * failure publishes no partial or successful assessment.
             * For the same small old and proposed states, compare active and
             * prospective validation with complete assessment and show identical
             * exact applicable rule, subject, and constrained-end work. Change
             * only display or property content and show no multiplicity work;
             * change an opposite endpoint's membership and show unchanged far
             * endpoints remain lookup-only unless their own count can change.
             * Change only a multiplicity-rule description and show zero
             * multiplicity work.
             */
            }
            verify VellisRequirements::validationCoverage;
        }
    }

    verification def 'Canonical History Is Durable And Contiguous' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Starting from the initial record, commit representative canonical
             * transitions, restart the ordinary process boundary, and show the
             * same complete ordered records with one uninterrupted prior-to-
             * resulting revision chain, stable earlier records, and no activity
             * record in canonical history. Show the initial record establishes
             * its contained revision, every transition establishes its resulting
             * revision, and the one current canonical-state tuple equals replay
             * through the final record before and after restart. Construct two
             * successive states that differ in graph, definitions, or delta and
             * show that no permitted current-state tuple can mix their components
             * or revision.
             */
            }
            verify VellisRequirements::durableCanonicalHistory;
        }
    }

    verification def 'Canonical Snapshot Is Complete And Read Only' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Capture snapshots with and without an in-flight delta. Show each
             * contains equivalent graph, active definitions, optional delta,
             * and revision, identifies the exact canonical record establishing
             * that revision, and changes no canonical state, revision, or
             * canonical history. Export and verify it incrementally with fixed-
             * size buffers while instrumentation shows no Graph, Canonical State,
             * definition-set document, or snapshot document is constructed.
             */
            }
            verify VellisRequirements::canonicalSnapshotCompleteness;
        }
    }

    verification def 'Snapshot And Tail Replay Is Equivalent' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Initialize a fresh RTG from a semantically complete streamed
             * snapshot, then apply every
             * later contiguous same-ledger canonical transition from the exact
             * captured source record. Show equivalent graph,
             * active definitions, optional delta, and final revision without
             * inventing a revision or reading activity history. Show the fresh
             * RTG owns one initial record containing the reconstructed final
             * state and does not claim transitions before that history base.
             * Compare rebuilt and active projections in both directions using
             * set differences and show peak materialization remains bounded.
             */
            }
            verify VellisRequirements::replayEquivalence;
        }
    }

    verification def 'Invalid Ledger Tail Fails Safely' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Replay tails with a gap, duplicate, reorder, mismatched base,
             * invalid or kind-incompatible semantic change, and incompatible
             * result. Supply a tail from another ledger whose preceding record
             * has the same revision number and show it is rejected because record
             * identity and ledger lineage do not match. Show observable findings
             * and no partially accepted state.
             */
            }
            verify VellisRequirements::replayEquivalence;
        }
    }

    verification def 'Historical Selection Is Correct' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Select a revision directly and query before, at, and between
             * committed instants using the same bounded graph-query semantics as
             * current evaluation. Exactly one selector kind is accepted, each
             * resolvable time selects the greatest revision at or before it, and
             * every returned result changes no canonical state. Starting cold,
             * discover definitions later retired, then use a time summary's exact
             * resolved revision for inspection and graph query with consistent results.
             */
            }
            verify VellisRequirements::historicalStateCorrectness;
        }
    }

    verification def 'Restore Appends Without Rewriting' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * With no delta, restore prior graph and active definitions and show
             * one new revision and explicit-difference record with no delta while
             * all earlier records remain unchanged. Instrument the selected/current
             * comparison and show set-based bounded-memory work without either
             * graph aggregate. With a delta, show refusal and no state change.
             */
            }
            verify VellisRequirements::historicalRestoreSemantics;
        }
    }

    verification def 'Activity History Cannot Affect Replay' {
        subject system : 'RTG System';
        objective {
            require constraint {
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
             * Make the activity append fail for an otherwise permitted read,
             * safely reported failure, snapshot, and validation. Show each returns
             * no completed domain result. For validation, show the prior current
             * assessment and all of its findings remain exactly retrievable. Show
             * an accepted canonical mutation still completes from its canonical
             * record without requiring a duplicate activity record.
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
             * For intervals larger than the positive maximum, instrument record
             * retrieval and decoding and show the read stops after enough entries
             * to decide whole-result rejection rather than processing the remaining
             * selected interval.
             */
            }
            verify VellisRequirements::dualLedgerSeparation;
            verify VellisRequirements::boundedHistoryRead;
        }
    }

    verification def 'MCP Tool Surface Is Typed And Portable' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Discover exactly rtg_definition_summary,
             * rtg_definition_inspect, rtg_definition_delta, rtg_query,
             * rtg_change, rtg_set_definition_delta,
             * rtg_activate_definition_delta, rtg_discard_definition_delta,
             * rtg_check, and rtg_history with typed object outputs and typed
             * object inputs only where the operation has semantic input. Show
             * definition summary, graph change, activation, and conformance carry
             * typed state-selection, target, exact-assessment, or page-request
             * inputs, and genuinely parameterless tools introduce no empty domain
             * request type.
             * Invoke every tool through core MCP discovery and invocation alone,
             * without any additional MCP capability.
             */
            }
            verify VellisRequirements::mcpAgentToolContract;
        }
    }

    verification def 'MCP Outcomes Preserve RTG Meaning' {
        subject system : 'RTG System';
        objective {
            require constraint {
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
            }
            verify VellisRequirements::mcpOutcomeIntegrity;
        }
    }

    verification def 'Owner Governs Personal Memory' {
        subject system : 'Vellis System';
        objective {
            require constraint {
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
            }
            verify VellisRequirements::ownerControlledMemory;
        }
    }

    verification def 'Failures Are Observable And Safe' {
        subject system : 'Vellis System';
        objective {
            require constraint {
            doc /*
             * Exercise semantic rejection and execution failure. The affected
             * participant receives a distinct outcome,
             * and every promised graph, definition, canonical-history, activity-
             * history, and revision non-effect holds.
             */
            }
            verify VellisRequirements::observableFailure;
        }
    }

    verification def 'V1 Snapshot Initializes Compatible Memory' {
        subject system : 'Vellis System';
        objective {
            require constraint {
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
            }
            verify VellisRequirements::v1SnapshotCompatibility;
        }
    }

    verification def 'One Owner Begins Using One Cohesive System' {
        subject system : 'Vellis System';
        objective {
            require constraint {
            doc /*
             * From a clean supported local environment, follow the supplied setup
             * guidance, connect one trusted owner-configured MCP agent, and
             * discover exactly the selected ten tools. Confirm the recommended
             * Everyday Life start, then have a cold agent discover current
             * definitions, issue a bounded query, and retain one owner-approved
             * context change. Restart Vellis, begin a distinct later agent session,
             * and show the same approved context is available at the identically
             * recovered canonical state. Decline a second proposal and show it
             * causes no mutation and is not retained. Exercise setup failure before
             * initialization and show an actionable observation with no partial
             * canonical or activity state. After memory is established, exercise a
             * failing subsequent setup attempt and a connection failure; show each
             * identifies the failed stage, states that established memory remains
             * unchanged, and supplies an available corrective action. Show the
             * graph, active definitions, current revision, canonical ledger, and
             * current definition proposal are identical before and after each
             * failure. A generic failure lacking the failed stage, state-effect
             * result, or available corrective action does not pass.
             * Separately start once blank, once from a complete v2 snapshot plus
             * later records, and once from a confirmed compatible v1 snapshot.
             * Show one owner can query, preserve, and govern the resulting system
             * and sole definition delta without tenant, organization, role,
             * cluster, server-fleet, database, or enterprise-infrastructure
             * administration and without internal RTG subsystems. Show agent
             * prompting, permissions, scheduling, inference, and decisions about
             * tool invocation remain external to Vellis.
             */
            }
            verify VellisRequirements::simpleIndividualOperation;
        }
    }

    verification def 'Canonical Equality Decides No Ops' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Compare Boolean, number, string, array, object, and null JSON
             * values. Show JSON kinds remain distinct, 1 and 1.0 have equal exact
             * mathematical value, composed é (U+00E9) and e followed by U+0301
             * COMBINING ACUTE ACCENT are unequal code-point sequences, array
             * order matters, object-member order does not, and a missing property
             * differs from null. Reorder graph-object,
             * definition, association, and participating-type sets and show an
             * accepted effective no-op with no revision, transition, or delta.
             * Change a description, pattern expression text, graph-object value,
             * endpoint, or association and show a semantic difference. Show type,
             * property, endpoint-rule, and multiplicity natural identities decide
             * whether content is an edit, addition, removal, or invalid duplicate.
             * Compare canonical states and show revision, delta presence,
             * proposed-definition content, and keyed graph-overlay content also
             * participate without requiring either state as a resident aggregate.
             * Validate permitted-value collections at successively doubled sizes
             * through at least eight thousand members. Instrument semantic
             * equality work and show each supplied value contributes once to the
             * uniqueness decision rather than being compared with every earlier
             * value, while preserving duplicate decisions for equivalent numbers,
             * object-member order, and nested values.
             */
            }
            verify VellisRequirements::canonicalSemanticEquality;
        }
    }

    verification def 'String Patterns Validate Stored Values' {
        subject system : 'RTG System';
        objective {
            require constraint {
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
             * closed set, and that changing or removing a pattern moves no
             * ordered string comparison result, so ordering follows the stored
             * values rather than the pattern describing them.
             */
            }
            verify VellisRequirements::stringPatternValidation;
        }
    }

    verification def 'Fresh RTG Begins At Revision Zero' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Initialize one state-free RTG with an empty valid definition set
             * and another with a non-empty valid set. Show each has revision 0,
             * an empty graph, exactly the supplied active definitions, no delta,
             * one equivalent initial-state record, no transitions, and an empty
             * activity ledger. Reject an invalid initial set and a request against
             * an already initialized RTG without establishing partial state.
             * Initialize separately from a streamed snapshot and show its
             * definitions and revision are reconstructed without any fresh-start
             * overlay or resident whole state. Initialize
             * separately from a confirmed v1 candidate and show its graph and
             * translated definitions form revision 0 with no transitions or activity.
             */
            }
            verify VellisRequirements::freshInitialization;
        }
    }

    verification def 'Everyday Life Is An Optional Confirmed Start' {
        subject system : 'Vellis System';
        objective {
            require constraint {
            doc /*
             * With no prior state, show blank and Everyday Life are the complete
             * choice set, Everyday Life is recommended and preselected, and
             * neither choice initializes before explicit owner confirmation.
             * Confirm blank and show empty definitions. Confirm Everyday Life and
             * show exactly twelve anchor types, twelve optional profile types,
             * nine links, and twenty-four profile multiplicity rules with no
             * graph objects or example data. Show every named catalog member,
             * profile property, permitted source, permitted target, and
             * relationship rule is a singleton within its explicitly sized
             * aggregate. Inspect every profile and endpoint neighborhood and show
             * it matches the modeled starter. For each
             * date-like property, accept 2024-02-29; reject 2024-2-9, 2024-13-01,
             * 2024-01-00, and arbitrary text; accept absent dates and show
             * 2023-02-31 is lexically accepted without claiming calendar validity.
             * Initialize from a v2 snapshot and a v1 snapshot and show no starter
             * overlay. Show an
             * existing system has no separate starter-install operation and may
             * use only ordinary owner-controlled definition governance.
             */
            }
            verify VellisRequirements::recommendedEverydayLifeStart;
            verify VellisRequirements::freshInitialization {
                subject redefines system =
                    'Everyday Life Is An Optional Confirmed Start'::system.memory;
            }
            verify VellisRequirements::graphInvariants {
                subject redefines system =
                    'Everyday Life Is An Optional Confirmed Start'::system.memory;
            }
        }
    }

    verification def 'Current Operations Ignore History Length' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Construct equivalent current canonical-state tuples backed by short
             * and long logical histories. Instrument semantic record accesses
             * while performing current definition summary and inspection, current
             * graph query, current conformance assessment, proposal discovery, and
             * ordinary change validation. Show each performs constant
             * historical-record work while scaling only with the state facets and
             * candidate relationships its meaning requires, proposal, and requested
             * return bounds. Repeat definition summary and focused inspection across
             * process restart and show they decode only requested definitions and
             * no graph objects. Hold one small query answer fixed while increasing unrelated
             * graph populations; instrument candidate retrieval and object decoding
             * and show answer identities are bounded before hydration, hidden
             * witnesses do not multiply work, and no complete graph is materialized.
             * Hold one-object mutation meaning fixed while increasing unrelated
             * rules and populations and show exact applicable rule, subject, and
             * constrained-end work is unchanged. Separately increase only an
             * applicable degree and show work scales with that degree while far
             * endpoints remain lookup-only.
             * For state-wide conformance and cutover, show semantic-entry visits and
             * finding counts may grow while peak materialization remains bounded.
             * Instrument every production operation and show none constructs a
             * Graph, Canonical State, definition-set document, or canonical-change
             * document. Commit one effective
             * canonical mutation and show the current projection update and one
             * appended transition are recoverably atomic without traversing or
             * rewriting the earlier logical prefix.
             * Append activity and show it neither visits the canonical prefix nor
             * reconstructs canonical state.
             */
            }
            verify VellisRequirements::historyIndependentCurrentWork;
            verify VellisRequirements::atomicCanonicalRevision;
        }
    }

    verification def 'Historical Selection Avoids Irrelevant Records' {
        subject system : 'RTG System';
        objective {
            require constraint {
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
             * unavailable. Include the selection or filtering plan when a returned-
             * record counter would hide excluded records visited underneath it; do
             * not use unstable wall-clock assertions.
             */
            }
            verify VellisRequirements::boundedHistoricalSelectionWork;
            verify VellisRequirements::historicalStateCorrectness;
            verify VellisRequirements::boundedHistoryRead;
        }
    }

    verification def 'Replay Work Is Characterized By Required Tail' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Reconstruct and ordinarily restart equivalent states across
             * increasing required replay-tail lengths. Record semantic record
             * visits, bounded buffer occupancy, peak materialization, and startup
             * or replay duration with their measurement units, demonstrate replay
             * equivalence, and characterize the dependency on required tail length
             * without asserting a numerical performance target. Show no Graph or
             * Canonical State aggregate is constructed.
             */
            }
            verify VellisRequirements::replayEquivalence;
            verify VellisRequirements::durableCanonicalHistory;
        }
    }

    verification def 'Cold Agent Prepares Incremental Improvement' {
        subject system : 'Vellis System';
        objective {
            require constraint {
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
            }
            verify VellisRequirements::ownerVisibleImprovementAnalysis;
            verify VellisRequirements::ownerControlledMemory;
        }
    }

    analysis def 'History Growth Performance Characterization' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Independently vary current graph size, canonical-ledger length,
             * definition-change density, activity-history length, selected
             * interval size, projected and unprojected query candidate populations,
             * distinct result cardinality, and required replay-tail length. Measure
             * semantic and physically filtered record visits, per-object encoding
             * and decoding, retained and transient memory, streaming buffer bounds,
             * allocation or copy work, identity/type/association/relationship
             * candidate joins, value comparisons, returned-identity and hidden-witness work, replay and
             * startup duration with explicit units, and storage growth. Include a
             * representative scale fixture with about one thousand definitions and
             * at least one hundred thousand graph objects, plus fixed one-object,
             * high-degree, narrow-cutover, state-wide-cutover, and broad-query
             * cases. Treat any complete-state materialization as a failure, not a
             * quantity to optimize.
             * Use the resulting evidence to select later numerical latency,
             * startup, and storage budgets only after a runtime, hardware profile,
             * and representative owner dataset exist. This analysis does not
             * claim satisfaction of any numerical performance target.
             */
            }
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
