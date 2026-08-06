package Vellis {
    private import RTGSystem::*;
    private import EverydayLifeStarter::*;

    enum def 'Fresh Vocabulary Choice' {
        enum blank;
        enum everydayLifeStarter;
        doc /*
         * The two owner-confirmed vocabulary choices available only when
         * beginning without prior canonical state. Everyday Life is presented
         * as the recommended preselected choice; blank remains fully supported.
         */
    }

    part def Owner {
        doc /* The single authoritative human owner of one Vellis system and its personal memory. */
    }

    part def 'External AI Agent' {
        doc /* An AI agent outside Vellis that acts within owner-authorized interaction scope. */
    }

    part def 'MCP Agent' :> 'External AI Agent', 'MCP Client' {
        doc /* An external AI agent using the selected MCP access contract for personal memory. */
    }

    part def 'Vellis System' :> 'RTG Client' {
        doc /* The individually owned product boundary. */
        part memory : 'RTG System';
    }

    use case def 'Begin using one personal Vellis system' {
        subject system : 'Vellis System';
        actor owner : Owner;
        in attribute freshVocabularyChoice [0..1] : 'Fresh Vocabulary Choice';
        in attribute freshVocabularyConfirmed [0..1] : ScalarValues::Boolean;
        objective {
            doc /*
             * Input: either no prior memory with one explicitly confirmed fresh
             * vocabulary choice, or a complete canonical snapshot with an
             * optional later ledger tail. For a fresh start, present Everyday
             * Life as recommended and preselected while retaining blank as an
             * alternative; do not initialize until the owner confirms the
             * selected choice. Success: blank establishes revision 0 with empty
             * definitions, while everydayLifeStarter establishes revision 0
             * with exactly EverydayLifeStarter::everydayLifeStarter; both have
             * an empty graph, no delta, one initial record, no transitions, and
             * an empty activity ledger. Snapshot initialization uses only its
             * reconstructed definitions and never overlays a fresh vocabulary.
             * Refusal or failure, including absent or false confirmation,
             * establishes no partial canonical or activity state. Evidence: the
             * owner can use the resulting system without tenant, organization,
             * role, cluster, server-fleet, or infrastructure administration and
             * no starter-created people, examples, or other graph objects exist.
             */
        }
    }

    dependency beginningBehavior
        from 'Begin using one personal Vellis system'
        to RTGSystem::'Initialize fresh RTG',
           RTGSystem::'Initialize fresh RTG from snapshot';

    use case def 'Obtain authorized relevant context' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: a bounded semantic graph query already within the trusted
             * agent's owner-established scope. Success: provide only the requested
             * shaped personal context and its evaluated revision. Invalid,
             * over-broad, or failed requests return no context. The MCP operation
             * does not establish or evaluate authorization. Canonical memory and
             * revision never change; the attempt is recorded observationally.
             * Evidence: returned named bindings satisfy exactly the query.
             */
        }

        include use case queryMemory[1] : 'Query graph' {
            subject redefines system = 'Obtain authorized relevant context'::system.memory;
            actor redefines client = 'Obtain authorized relevant context'::agent;
        }
    }

    use case def 'Understand personal memory vocabulary' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: a trusted owner-configured agent with no prior graph knowledge.
             * Success: discover every currently active anchor concept, then inspect
             * the complete definition neighborhoods needed for a bounded question
             * or current proposed change. Rejected or failed discovery returns no
             * partial definition detail. Canonical memory and revision never
             * change; the attempt is recorded observationally. Evidence: the agent
             * can construct a current query without predecessor knowledge or a
             * full definition dump.
             */
        }

        include use case discoverMemory[1] : 'Discover active graph definitions' {
            subject redefines system = 'Understand personal memory vocabulary'::system.memory;
            actor redefines client = 'Understand personal memory vocabulary'::agent;
        }
    }

    use case def 'Retain owner-approved context' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: a complete graph change that the owner has already approved.
             * Success: the approved context becomes conforming personal memory at
             * one new revision. Invalid or failed changes are not retained. An
             * owner-declined proposal never enters this use case and never invokes
             * the graph-change operation. Evidence: later in-scope queries recover
             * approved context while declined and rejected proposals change no
             * canonical memory.
             */
        }

        include use case retainMemory[1] : 'Apply graph change' {
            subject redefines system = 'Retain owner-approved context'::system.memory;
            actor redefines client = 'Retain owner-approved context'::agent;
        }
    }

    use case def 'Review personal memory' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: an owner-selected bounded memory question within the trusted
             * agent's configured scope. Success: present current shaped facts at
             * their evaluated revision. Rejection or failure returns no partial
             * result. Canonical memory and revision never change; the attempt is
             * recorded observationally. Evidence: the result contains exactly the
             * owner-selected projections.
             */
        }

        include use case queryMemory[1] : 'Query graph' {
            subject redefines system = 'Review personal memory'::system.memory;
            actor redefines client = 'Review personal memory'::agent;
        }
    }

    use case def 'Review canonical memory history' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: an owner-selected chronological range and positive maximum.
             * Success: present one bounded owner-facing entry per canonical
             * record, with provenance, revision, transition kind when applicable,
             * and semantic summary, but no replay payload. Rejection or failure
             * returns no partial entries. Canonical memory and revision never
             * change; the attempt is recorded observationally. Evidence: every
             * entry represents one canonical record in the selected inclusive
             * interval and ledger order.
             */
        }

        include use case inspectChanges[1] : 'Inspect state-change history' {
            subject redefines system = 'Review canonical memory history'::system.memory;
            actor redefines client = 'Review canonical memory history'::agent;
        }
    }

    use case def 'Review memory activity' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: an owner-selected chronological range and positive maximum.
             * Success: present one bounded owner-facing entry per permitted
             * activity record with provenance and summary. The result is selected
             * before this read is recorded and never includes itself. Rejection or
             * failure returns no partial entries. Canonical memory and revision
             * never change; the attempt is recorded observationally. Evidence:
             * every entry represents one activity record in the selected inclusive
             * interval and ledger order.
             */
        }

        include use case inspectActivity[1] : 'Inspect activity history' {
            subject redefines system = 'Review memory activity'::system.memory;
            actor redefines client = 'Review memory activity'::agent;
        }
    }

    use case def 'Manage activity history retention' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            doc /*
             * Input: an owner decision about permitted activity-history
             * retention. Success: apply that decision only to observational
             * activity records. Refusal or failure preserves every preexisting
             * activity record, while the failed attempt may add its own failure
             * observation. Canonical graph, definitions, delta, revision, and
             * state-change history never change. Evidence: replay before and
             * after the retention change reconstructs equivalent canonical state.
             */
        }

        include use case retainActivity[1] : 'Manage activity retention' {
            subject redefines system = 'Manage activity history retention'::system.memory;
            actor redefines client = 'Manage activity history retention'::system;
        }
    }

    use case def 'Correct or forget personal memory' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            doc /*
             * Input: an owner-selected correction or forgetting request.
             * Success: commit one conforming graph change and retain canonical
             * history. Refusal or failure preserves memory. Evidence: current
             * query and replay both show the same accepted change.
             */
        }

        include use case changeMemory[1] : 'Apply graph change' {
            subject redefines system = 'Correct or forget personal memory'::system.memory;
            actor redefines client = 'Correct or forget personal memory'::system;
        }
    }

    use case def 'Manage graph definitions and constraints' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: owner changes to graph meaning. Success: create, edit,
             * retrieve, and assess the sole delta and review its descriptions for
             * owner-readable meaning. According to owner intent, leave the proposal
             * staged for later work, activate it, or discard it. Refusal or failure
             * preserves active definitions and graph; failed activation also
             * preserves the delta. No automatic graph migration occurs. Evidence:
             * whole-delta retrieval preserves staged work, while active discovery
             * reflects exactly one accepted activation or the prior active set
             * after discard or failure.
             */
        }
    }

    /*
     * Definition governance has alternative successful continuations. Abstract
     * dependencies retain change-impact traceability without asserting that
     * review, staging, activation, and discard all occur in one performance.
     */
    dependency definitionGovernanceBehavior
        from 'Manage graph definitions and constraints'
        to RTGSystem::'Review definition delta',
           RTGSystem::'Create or edit definition delta',
           RTGSystem::'Activate definition delta',
           RTGSystem::'Discard definition delta';

    use case def 'Assess personal memory conformance' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: none; assess the owner's current personal memory. Success:
             * present a scoped conformance report at the current revision. Refusal or
             * failure is observable. Canonical memory and revision never change;
             * the validation attempt is recorded observationally. Evidence:
             * findings identify implicated definitions and graph objects when available.
             */
        }

        include use case assessMemory[1] : 'Assess graph conformance' {
            subject redefines system = 'Assess personal memory conformance'::system.memory;
            actor redefines client = 'Assess personal memory conformance'::agent;
        }
    }

    use case def 'Explore prior personal memory' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: an owner-selected bounded graph query whose type and property
             * vocabulary is already known to be valid at one selected revision or
             * time. Success: present the requested personal-memory facts at the
             * resolved revision. Current definition discovery does not discover
             * retired vocabulary. Rejection or failure returns no partial result.
             * Canonical memory and revision never change; the attempt is recorded
             * observationally. Evidence: the result identifies and matches the
             * resolved canonical revision using the supplied historical vocabulary.
             */
        }

        include use case exploreMemory[1] : 'Query graph' {
            subject redefines system = 'Explore prior personal memory'::system.memory;
            actor redefines client = 'Explore prior personal memory'::agent;
        }
    }

    use case def 'Preserve personal memory snapshot' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            doc /*
             * Input: the owner's current personal memory. Success: produce a
             * complete self-contained canonical snapshot suitable for fresh
             * initialization and later ledger catch-up. Refusal or failure is
             * observable. Canonical memory and revision do not change; the snapshot
             * attempt is recorded observationally. Evidence: initialization from
             * the snapshot reconstructs equivalent personal memory.
             */
        }

        include use case snapshotMemory[1] : 'Create canonical snapshot' {
            subject redefines system = 'Preserve personal memory snapshot'::system.memory;
            actor redefines client = 'Preserve personal memory snapshot'::system;
        }
    }

    use case def 'Check personal memory recovery' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            doc /*
             * Input: one initial record or complete snapshot with an optional
             * later ledger tail. Success: reconstruct equivalent personal memory
             * for inspection. Refusal or failure reports findings. Live canonical
             * memory and revision do not change; the validation attempt is recorded
             * observationally, and the reconstruction does not initialize or
             * restore the live system. Evidence: the result is equivalent to direct
             * state at the reconstructed revision.
             */
        }

        include use case reconstructMemory[1] : 'Reconstruct canonical state' {
            subject redefines system = 'Check personal memory recovery'::system.memory;
            actor redefines client = 'Check personal memory recovery'::system;
        }
    }

    use case def 'Restore prior personal memory' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            doc /*
             * Input: an owner-selected historical revision. Success: with no
             * delta in flight, restore its graph and active definitions as one
             * new revision. Refusal or failure preserves current canonical state. Earlier
             * canonical history remains unchanged. Evidence: current memory
             * matches the selected revision and the earlier ledger prefix is intact.
             */
        }

        include use case restoreMemory[1] : 'Restore historical state' {
            subject redefines system = 'Restore prior personal memory'::system.memory;
            actor redefines client = 'Restore prior personal memory'::system;
        }
    }

    use case def 'Recover existing RTG graph' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            doc /*
             * Input: predecessor RTG meaning presented for compatibility
             * recovery into an existing system. Success: preserve canonical
             * identity, kinds, associations, links, endpoints, JSON values, and
             * live defaults in one new revision. Refusal or failure reports
             * findings without partial canonical state. Evidence: current query
             * and replay preserve the representative predecessor meanings.
             */
        }

        include use case recoverMemory[1] : 'Recover predecessor RTG graph' {
            subject redefines system = 'Recover existing RTG graph'::system.memory;
            actor redefines client = 'Recover existing RTG graph'::system;
        }
    }

    use case def 'Use AI with persistent personal context' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            doc /*
             * Input: an owner interaction with an external AI agent. Success:
             * provide relevant personal context within the trusted agent's
             * owner-established scope and submit a memory change only after the
             * owner approves it, so later interactions continue coherently. The
             * MCP tools neither establish that scope nor decide approval. Refusal
             * or failure is observable. Evidence: in a later interaction, approved
             * context from the earlier interaction is available within scope,
             * while declined or rejected context is not.
             */
        }
    }

    part def Context {
        part system : 'Vellis System';
        ref part owner : Owner;
        ref part agent : 'MCP Agent';

        use case beginUse : 'Begin using one personal Vellis system' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
        use case persistentContext : 'Use AI with persistent personal context' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case obtainContext : 'Obtain authorized relevant context' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case retainContext : 'Retain owner-approved context' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case understandVocabulary : 'Understand personal memory vocabulary' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case reviewMemory : 'Review personal memory' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case reviewCanonicalHistory : 'Review canonical memory history' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case reviewActivity : 'Review memory activity' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case manageActivityRetention : 'Manage activity history retention' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
        use case correctOrForgetMemory : 'Correct or forget personal memory' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
        use case manageDefinitions : 'Manage graph definitions and constraints' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case assessConformance : 'Assess personal memory conformance' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case explorePriorMemory : 'Explore prior personal memory' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
            actor redefines agent = Context::agent;
        }
        use case preserveSnapshot : 'Preserve personal memory snapshot' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
        use case checkRecovery : 'Check personal memory recovery' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
        use case restorePriorMemory : 'Restore prior personal memory' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
        use case recoverExistingGraph : 'Recover existing RTG graph' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner;
        }
    }
}
