package RTGSystem {
    private import RTG::*;

    part def 'RTG Client' {
        doc /* A person or system acting within scope already established by the owner. */
    }
    part def 'MCP Client' :> 'RTG Client' {
        doc /* One trusted owner-configured agent client. */
    }
    part def 'RTG System' {
        doc /*
         * One cohesive semantic and transactional boundary. Current and
         * historical state are directly indexed meanings, not replay products.
         * Query, draft, validation, history, search, backup, and audit are
         * capabilities rather than independent subsystems.
         */
        item currentState : 'Canonical State';
        item canonicalHistory : 'Canonical Ledger';
        item activities : 'Activity Ledger';
        attribute activityMode : 'Activity Mode' default = 'Activity Mode'::semantic;
        item draft [0..1] : Draft;
        item latestValidation [0..2] : 'Validation Report';

        perform action typeSummary : rtg_type_summary;
        perform action typeInspect : rtg_type_inspect;
        perform action query : rtg_query;
        perform action change : rtg_change;
        perform action draftInspect : rtg_draft_inspect;
        perform action draftChange : rtg_draft_change;
        perform action validate : rtg_validate;
        perform action draftActivate : rtg_draft_activate;
        perform action draftDiscard : rtg_draft_discard;
        perform action history : rtg_history;
    }

    use case def 'Discover evaluated definitions' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Return a complete shallow anchor summary, then complete focused
             * neighborhoods for selected anchor keys at current, draft, revision,
             * or time state. Every success identifies the evaluated revision.
             * Draft requires a present draft. Unknown, duplicate, unresolved, or
             * incompletely answerable selections reject whole. The canonical
             * state and draft do not change; activity records the attempt.
             */
            }
        }
    }

    use case def 'Query evaluated graph' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Accept exactly one known-identity or connected-pattern selection.
             * Identity selection reports found and missing UUIDs and hydrates
             * only requested properties. Pattern selection first establishes at
             * most maximumMatches complete distinct bindings, rejects whole on
             * maximum plus one, and only then hydrates requested object fields.
             * No match is an accepted empty result. Evaluation has identical
             * meaning for current, draft, revision, and time state and changes no
             * canonical or draft state while recording activity.
             */
            }
        }
    }

    use case def 'Apply active graph change' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Require expectedRevision to equal the current revision, including
             * for a no-op. Apply one bounded final-state batch of field upserts
             * and explicit removals independent of command order. Creation needs
             * complete required content; updates preserve every unnamed field.
             * Validate exact affected references and cardinality subjects with
             * no cascade or whole-state assessment. Rejection changes no
             * canonical state. An effective success creates one revision; a
             * redundant success creates none. Both append activity atomically
             * with their observable effect. A draft, when present, is untouched.
             */
            }
        }
    }

    use case def 'Edit durable draft' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Stage complete definition replacements or tombstones and graph
             * field patches or tombstones by natural key. Repeated edits merge
             * into one normalized entry; whole-entry unstage removes it. Draft
             * editing validates request structure and lineage kind reservation
             * but may leave effective meaning nonconforming. It never advances
             * canonical revision or changes live state. The final removed entry
             * removes draft presence. An empty request is an accepted no-op and
             * does not create a draft. Activity records the attempt.
             */
            }
        }
    }

    use case def 'Configure activity detail' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Let the owner select semantic or verbose activity detail. Semantic
             * is the initial mode. An accepted change appends configuration
             * activity without a canonical revision. Rejection or failure
             * preserves the prior mode and canonical state.
             */
            }
        }
    }

    use case def 'Inspect durable draft' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Return filtered raw normalized entries with current content, exact
             * staged operations, mechanically composed proposal, effect flag,
             * whole-draft raw/effective counts, evaluated revision, and a bounded
             * continuation. A continuation expires after current or draft change
             * or a newer fresh inspection. No draft digest or version is public.
             * Draft absence is an accepted empty inspection with presence false.
             * The read changes neither live nor draft content and appends activity.
             */
            }
        }
    }

    use case def 'Validate current or draft state' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * A fresh call computes every current or effective-draft finding once,
             * publishes only the latest backing for that scope, and returns its
             * complete count, cleanliness, and first bounded page. Continuations
             * page that backing without reassessment and expire after relevant
             * content or newer validation changes. Non-clean is an accepted
             * assessment result. Draft scope rejects when no draft is present.
             * Validation changes no canonical or draft content; publication of
             * its latest backing and activity is one atomic observational effect.
             */
            }
        }
    }

    use case def 'Activate durable draft' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Recompose the present draft over latest live state and validate the
             * complete effective system in one atomic operation. Invalidity
             * preserves live state and draft, publishes pageable findings, and
             * records rejected activity. A valid effective proposal creates one
             * canonical revision, clears the draft, and records activity. A valid
             * redundant proposal clears the draft without a revision. No prior
             * assessment authorizes activation; the latest state is always
             * revalidated. Draft operations carry no system metadata; publication
             * applies the same canonical create, update, or reactivation envelope
             * rules as active change. Absence rejects.
             */
            }
        }
    }

    use case def 'Discard durable draft' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Clear a present draft and append activity without changing live
             * graph, definitions, revision, or canonical history. Absence is an
             * accepted no-op.
             */
            }
        }
    }

    use case def 'Inspect bounded history' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Select one complete bounded canonical or activity interval by
             * inclusive time or by sequence range with an exclusive after and
             * inclusive through boundary, and report the observed head.
             * Exceeding the caller maximum rejects whole. Canonical entries are
             * owner-readable records without replay payloads. Activity selection
             * occurs before recording this history read, so a response never
             * includes itself. History reads change no canonical or draft state.
             */
            }
        }
    }

    use case def 'Initialize fresh RTG' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        in item definitions : 'Graph Definition Set';
        objective {
            require constraint {
            doc /*
             * For an empty destination, atomically establish revision zero with
             * an empty graph, exactly the validated definitions, no draft, one
             * initial canonical record, and empty activity. Failure publishes
             * nothing. Initial system envelopes use revision zero.
             */
            }
        }
    }

    use case def 'Restore historical state' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Refuse while a draft exists. Resolve a revision or time, compute
             * its difference from current state, validate complete resulting
             * meaning, and append one new canonical revision when effective.
             * Equality appends activity without revision. Preserve all intervening
             * history and original identity creation metadata.
             */
            }
        }
    }

    use case def 'Audit complete RTG' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Read-only verification covers lineage and schema identity,
             * contiguous nondecreasing canonical history and integrity evidence,
             * version intervals, identity reservations, definitions, graph
             * conformance, indexed projection equivalence, search equivalence,
             * and activity/validation structural integrity. Audit appends no activity.
             */
            }
        }
    }

    use case def 'Back up complete RTG' {
        subject system : 'RTG System';
        actor client : 'RTG Client';
        objective {
            require constraint {
            doc /*
             * Produce an audited owner-private complete database backup while
             * serving. Include current and historical state, both ledgers,
             * settings, draft, and useful validation backing. Exclude HTTP tokens
             * and v1 report/source sidecars. Backup reads append no source activity.
             */
            }
        }
    }

    /* Selected external MCP behavior. Names are boundary decisions, not architecture. */

    action def rtg_type_summary {
        in item request : 'Definition Summary Request';
        out item result : 'Definition Summary Result';
    }
    action def rtg_type_inspect {
        in item request : 'Definition Inspection Request';
        out item result : 'Definition Inspection Result';
    }
    action def rtg_query {
        in item request : 'Graph Query';
        out item result : 'Graph Query Result';
    }
    action def rtg_change {
        in item request : 'Active Change Request';
        out item result : 'Operation Outcome';
    }
    action def rtg_draft_inspect {
        in item request : 'Draft Inspection Request';
        out item result : 'Draft Inspection Result';
    }
    action def rtg_draft_change {
        in item request : 'Draft Change';
        out item result : 'Draft Change Result';
    }
    action def rtg_validate {
        in item request : 'Validation Request';
        out item result : 'Validation Report';
    }
    action def rtg_draft_activate { out item result : 'Validation Report'; }
    action def rtg_draft_discard { out item result : 'Operation Outcome'; }
    action def rtg_history {
        in item request : 'History Query';
        out item result : 'History Result';
    }

    dependency typeSummaryBehavior from rtg_type_summary to 'Discover evaluated definitions';
    dependency typeInspectBehavior from rtg_type_inspect to 'Discover evaluated definitions';
    dependency queryBehavior from rtg_query to 'Query evaluated graph';
    dependency changeBehavior from rtg_change to 'Apply active graph change';
    dependency draftInspectBehavior from rtg_draft_inspect to 'Inspect durable draft';
    dependency draftChangeBehavior from rtg_draft_change to 'Edit durable draft';
    dependency validateBehavior from rtg_validate to 'Validate current or draft state';
    dependency activateBehavior from rtg_draft_activate to 'Activate durable draft';
    dependency discardBehavior from rtg_draft_discard to 'Discard durable draft';
    dependency historyBehavior from rtg_history to 'Inspect bounded history';
}
