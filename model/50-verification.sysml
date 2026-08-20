package VellisVerification {
    private import RTGSystem::*;
    private import Vellis::*;
    private import VellisRequirements::*;

    verification def 'Scalars Definitions And Lineage Are Closed' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Exercise safe-integer edges and rejection outside them; integer
             * versus number, finite binary64, negative zero, shortest round-trip
             * number output; leap dates and invalid dates; timestamp offsets,
             * UTC normalization, fractional precision, invalid/naive/leap-second
             * forms; exact composed/decomposed Unicode; absence versus null; and
             * required nullable meaning. Exercise every compatible constraint
             * combination and reject duplicate canonical allowed values, null in
             * allowed values, unsafe/non-finite values, inverted or incompatible
             * rules, malformed RE2, undeclared properties, and missing required
             * properties. Reserve UUID and type key kinds across removal and
             * same-kind reactivation. Show system envelopes preserve original
             * creation and legacy metadata and only changed subjects update
             * lastChangedRevision. Show draft deltas contain no system metadata,
             * live-backed draft results retain unchanged canonical metadata,
             * draft-only additions/reactivations omit it, and activation applies
             * ordinary canonical envelope rules. Reject dangling associations/endpoints,
             * wrong-kind types, duplicate set members, and links as endpoints;
             * accept a conforming self-link.
             */
            }
            verify VellisRequirements::scalarDefinitions;
            verify VellisRequirements::graphLineage;
        }
    }

    verification def 'Local Bounds Replace Relationship Rules' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * For one associated-data type, exercise anchors-per-object and
             * objects-per-anchor minimum, maximum, exact-bound, and unbounded
             * cases over all permitted anchor types. For one link type, do the
             * same at source and target across its complete permitted populations.
             * Reject an inverted bound, data minimum below one, subset-specific
             * or independently identified rule, and a graph or definition change
             * that violates one local count. Show a second type can express
             * deliberately different count meaning without overlap.
             */
            }
            verify VellisRequirements::localCardinality;
        }
    }

    verification def 'Cold Discovery And Unified Query Compose' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Starting cold, retrieve every shallow anchor definition, inspect
             * several complete neighborhoods, and formulate one query. Resolve a
             * mixed ordered list of known anchor/data/link and missing UUIDs
             * directly, requesting no properties, selected properties, and all
             * properties; show structural/system fields, explicit missing UUIDs,
             * absent versus null properties, and optional legacy disclosure.
             * Query single-node, path, branch, cycle, parallel-link, direct-
             * association, and real self-link patterns. Show type and UUID filters
             * intersect, distinct names bind distinct identities, every node/link
             * selector is returned, objects are hydrated once, rows are
             * deterministic, and no separate retrieval operation is needed.
             * Reject duplicate names/UUIDs/property names, disconnected patterns,
             * wrong endpoints, unknown types/properties, property requests on
             * anchor/link, incompatible predicates, and any hidden projection,
             * aggregation, traversal, disconnected product, or general OR form.
             * Show accepted empty payloads remain distinguishable from rejected
             * outcomes with no query payload.
             */
            }
            verify VellisRequirements::unifiedQuery;
        }
    }

    verification def 'Predicates Search And Bounds Are Exact' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Exercise present, missing, null, not-null, same-kind equality and
             * ordering for integer, number, exact text, date, and timestamp;
             * anyOf typing; case-sensitive and folded contains/prefix; RE2
             * substring regex; and structured all-term, any-term, and phrase
             * full-text search over display names and text properties. Distinguish
             * exact case/diacritics from folded contains and diacritic-insensitive
             * full text. Reject raw FTS, malformed RE2, multi-token term operands,
             * property predicates without typed data candidates, and cross-kind
             * comparisons. Accept no match as empty. At exact maximum return all;
             * at maximum plus one reject with no rows or hydration. Instrument
             * unrelated populations, hidden witnesses, historical intervals, and
             * selected-field hydration. Compare every small pattern against an
             * independent brute-force oracle and mutate the compiler so the oracle
             * catches the nearest wrong join or distinctness behavior.
             */
            }
            verify VellisRequirements::queryPredicates;
            verify VellisRequirements::querySafety;
            verify VellisRequirements::locality;
        }
    }

    verification def 'Field Changes Preserve Unseen Context' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Create each object kind, then patch one field after reading only a
             * subset and show every unmentioned display field, property,
             * association, and endpoint survives. Distinguish setting null from
             * removal. Reject a property set with both/neither value and null,
             * same-property set/remove, same-anchor add/remove, and update with a
             * supplied complete anchor set, showing no state effect. Accept
             * removal of absent property, association, or object
             * and addition of an existing association. Reject incomplete create,
             * kind reuse, conflicts, and stale expected revision including a
             * redundant batch. Change type and endpoint conformingly. Apply the
             * same multi-object batch in every command permutation and show equal
             * state, findings, and revision effect. Remove an anchor while
             * removing/repointing all dependents successfully; leave dependents
             * and show every one is named with no implicit cascade. Instrument
             * exact changed neighborhood/cardinality subjects and prove unrelated
             * populations are not scanned. Show active no-op appends activity but
             * no canonical revision, and inject failure before response
             * serialization, activity, commit, and after the commit boundary.
             */
            }
            verify VellisRequirements::atomicChange;
            verify VellisRequirements::locality;
            verify VellisRequirements::mcpBoundary;
        }
    }

    verification def 'Draft Tracks Fields Not Fictional Versions' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Stage definition replacement, field patches, association/property
             * add/remove, and tombstones through repeated edits. Show one raw entry
             * per key, later same-field win, tombstone win, later upsert restarting
             * from then-live state, whole-entry unstage, raw redundant entries,
             * and draft removal after final unstage. While staged, perform live
             * changes to the same and unrelated fields: staged fields win and
             * unrelated live fields survive. Exercise live deletion beneath
             * partial and complete upserts, compatible and incompatible live
             * creation, and draft queries over nonconforming mechanically
             * representable state. Reject only a query requiring an
             * unmaterializable staged object. Confirm no public version, digest,
             * status, stale flag, assessment identity, or activation token exists.
             */
            }
            verify VellisRequirements::durableDraft;
        }
    }

    verification def 'Inspect Validate Activate And Discard Draft' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Inspect filtered definitions, anchors, data, and links by operation
             * and identity; verify deterministic ordering, raw/effective counts,
             * precise graph operations, effect flags, page limits, and expiration
             * after live/draft/new-inspection changes. Show empty fresh filters
             * select all; reject a fresh call without a
             * limit, a continuation with filters or limit, and validation
             * continuation whose scope differs from its cursor. Show draft
             * absence inspects as empty but rejects draft validation. Repeatedly
             * validate and page
             * every deterministic finding without reassessment, repair, and
             * validate again; show current/draft continuations expire on their
             * exact relevant changes and clean=false remains accepted. Invalid
             * activation preserves live and draft, publishes latest findings, and
             * records rejection. Valid effective activation revalidates latest
             * state and makes exactly one revision. Valid redundant activation
             * clears without revision. Discard changes no canonical state and
             * absence is a no-op. Show inspection activity and atomic validation-
             * backing/activity publication without canonical or draft mutation.
             * No earlier validation authorizes activation.
             */
            }
            verify VellisRequirements::draftWorkflow;
        }
    }

    verification def 'History Is Indexed And Activity Is Separate' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Commit and restart across representative revisions. Show contiguous
             * corruption-evident canonical records, nondecreasing times under a
             * backward clock, direct current/historical graph, definitions,
             * query, and search without replay, correct greatest revision at tied
             * time, and rejection before revision zero. Query canonical and
             * activity ranges by inclusive time and by sequence with exclusive
             * after and inclusive through; return complete
             * ledger order and kind-specific head or reject whole. Exercise
             * omitted/both-absent ranges, reversed-time rejection, accepted empty
             * sequence ranges, selected-family-only payload, and rejected
             * no-payload results. Select activity before
             * recording the history read. Show semantic is the initial activity
             * mode, accepted owner mode change appends configuration activity
             * without a canonical revision, and rejected/failed mode change
             * preserves the prior mode. Compare semantic and verbose detail;
             * verify complete rejection findings/request, truthful bounded binding
             * counts, no recursive history payload, and no token/secret capture.
             * Change activity detail and show canonical state and history are
             * unchanged. Ordinary restart performs no ledger traversal.
             */
            }
            verify VellisRequirements::historicalState;
            verify VellisRequirements::activitySeparation;
        }
    }

    verification def 'Restore Audit And Backup Preserve Lineage' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Restore by revision and time as one new revision while preserving
             * all prior records, original identity creation/legacy metadata, and
             * new last-change revision; show current-equal restore is activity-
             * only and a present draft refuses. Corrupt every version family,
             * interval, reservation, canonical hash/time/sequence, projection,
             * search, validation, and activity structure in copied fixtures and
             * show read-only audit detects it. Back up while concurrent HTTP reads
             * and writes use the source; audit the backup and show it contains
             * history, ledgers, settings, draft, and validation but no token or
             * v1 sidecar and adds no source activity. Refuse an existing output.
             * Initialize an empty destination from backup and show identical
             * lineage/revisions with no copied or generated token.
             */
            }
            verify VellisRequirements::lifecycle;
        }
    }

    verification def 'V1 Import Is Streamed Explicit And Lossless' {
        subject system : 'Vellis System';
        objective {
            require constraint {
            doc /*
             * Preview representative and large v1 snapshots while bounding peak
             * materialization and proving no whole graph/definition set is held.
             * Exercise absent/false live, UUID spelling normalization, Boolean,
             * safe integer, finite number, text, null-plus-kind nullable, unsafe
             * integer, nested array/object, mixed kind, and large decimal lexemes.
             * Verify whole-property canonical JSON-text conversion including JSON
             * strings and null, with no date/timestamp inference. Preserve object
             * and definition legacy metadata. Map only exactly reducible local
             * bounds and report subset/overlap omission. Block dangling reference,
             * unresolved type, duplicate/kind conflict, or preservation failure.
             * Show deterministic human/machine reports, exact digest confirmation,
             * changed-input/report refusal, owner-private sidecar, revision zero
             * with one initialization record and no imported predecessor
             * transitions, draft, or activity, and no destination from preview or
             * failure. Discover/query imported meaning and inspect converted text
             * and legacy metadata before generic owner-approved remodeling advice.
             */
            }
            verify VellisRequirements::initialization;
        }
    }

    verification def 'Starter Is Small Typed And Optional' {
        subject system : 'Vellis System';
        objective {
            require constraint {
            doc /*
             * Require confirmation for blank and recommended preselected starter.
             * Blank yields no definitions. Starter yields exactly its modeled
             * twelve anchor keys, corresponding twelve details types with unchanged
             * property names/descriptions, nine link keys/descriptions/endpoints,
             * no graph objects, no separate multiplicity objects, details bounds
             * 1..1 and 0..1, and link bounds 0..unbounded. Show all properties are
             * optional non-nullable, Boolean properties remain Boolean, and the
             * eight selected date properties accept valid leap dates while rejecting
             * invalid calendar dates or lexical forms. Backup and v1 starts add no
             * starter and an existing system has no starter-install operation.
             */
            }
            verify VellisRequirements::starter;
        }
    }

    verification def 'MCP And Owner Lifecycle Are Truthful' {
        subject system : 'Vellis System';
        objective {
            require constraint {
            doc /*
             * From installed wheel and source distribution, initialize blank,
             * starter, backup, and v1 modes; run real STDIO and HTTP initialize,
             * list, and calls; inspect ordinary self-contained schemas and unknown-
             * member rejection. Verify the selected tool names and cold-agent
             * guidance without treating their count as internal architecture.
             * Distinguish malformed input, semantic rejection, execution failure,
             * and post-commit response loss followed by revision/history
             * reconciliation. Exercise loopback development without token,
             * guided loopback token generation, non-loopback refusal without
             * token, missing/invalid/valid bearer, complete application protection,
             * exact /mcp, constant-time comparison, concurrent request isolation,
             * and plaintext-network warning. Show no token leakage. Through public
             * Codex and Claude CLIs, probe before add/replace, require confirmation,
             * pass only environment references, avoid configuration files, and
             * truthfully report remove-then-add failure with recovery command.
             * Initialization survives later connection failure. Audit, backup,
             * restore, configure, and token rotation retain one-owner simplicity
             * without daemon, TLS, OAuth, roles, users, tenants, or containers.
             */
            }
            verify VellisRequirements::mcpBoundary {
                subject redefines system = 'MCP And Owner Lifecycle Are Truthful'::system.memory;
            }
            verify VellisRequirements::simpleOperation;
        }
    }

    verification def 'Current Work Is Local And Broad Work Is Bounded' {
        subject system : 'RTG System';
        objective {
            require constraint {
            doc /*
             * Hold one current discovery/query/change result fixed while growing
             * excluded history and unrelated current objects/types; instrument
             * semantic accesses and show no dependency. Increase only applicable
             * degree and show proportional affected-neighborhood work. Resolve
             * narrow historical ranges behind growing excluded prefixes without
             * linear visits. For validation, activation, restore, audit, import,
             * and backup, grow complete relevant state and show scans may grow
             * while retained/transient working memory stays bounded and no resident
             * complete graph or definition-set document survives an operation.
             * Characterize, but do not invent, numerical performance targets.
             */
            }
            verify VellisRequirements::locality;
        }
    }

    part vellis : 'Vellis System';
    verification scalarClosure : 'Scalars Definitions And Lineage Are Closed' {
        subject redefines system = vellis.memory;
    }
    verification cardinality : 'Local Bounds Replace Relationship Rules' {
        subject redefines system = vellis.memory;
    }
    verification queryComposition : 'Cold Discovery And Unified Query Compose' {
        subject redefines system = vellis.memory;
    }
    verification queryPredicates : 'Predicates Search And Bounds Are Exact' {
        subject redefines system = vellis.memory;
    }
    verification activeChange : 'Field Changes Preserve Unseen Context' {
        subject redefines system = vellis.memory;
    }
    verification draftMerge : 'Draft Tracks Fields Not Fictional Versions' {
        subject redefines system = vellis.memory;
    }
    verification draftWorkflow : 'Inspect Validate Activate And Discard Draft' {
        subject redefines system = vellis.memory;
    }
    verification history : 'History Is Indexed And Activity Is Separate' {
        subject redefines system = vellis.memory;
    }
    verification lifecycle : 'Restore Audit And Backup Preserve Lineage' {
        subject redefines system = vellis.memory;
    }
    verification v1 : 'V1 Import Is Streamed Explicit And Lossless' {
        subject redefines system = vellis;
    }
    verification starter : 'Starter Is Small Typed And Optional' {
        subject redefines system = vellis;
    }
    verification mcpLifecycle : 'MCP And Owner Lifecycle Are Truthful' {
        subject redefines system = vellis;
    }
    verification locality : 'Current Work Is Local And Broad Work Is Bounded' {
        subject redefines system = vellis.memory;
    }
}
