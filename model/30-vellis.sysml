package Vellis {
    private import RTG::*;
    private import RTGSystem::*;
    private import EverydayLifeStarter::*;

    item def 'V1 Import Preview' {
        ref item source : 'V1 Snapshot';
        item candidate : 'Recovery Candidate';
        item report : 'Recovery Report';
        bind report.source = source;
        bind report.candidate = candidate;
        doc /* One transient source/candidate/report meaning bound by exact digests. */
    }

    part def Owner {
        doc /* The single authoritative human owner of one Vellis system and its memory. */
    }
    part def 'External AI Agent' {
        doc /* An AI agent outside Vellis acting within owner-authorized workflow scope. */
    }
    part def 'MCP Agent' :> 'External AI Agent', 'MCP Client';
    part def 'Vellis System' :> 'RTG Client' {
        doc /* The individually owned application boundary. */
        part memory : 'RTG System';
    }

    use case def 'Begin using personal Vellis' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            require constraint {
            doc /*
             * In an empty destination, initialize from an explicitly confirmed
             * blank or recommended Everyday Life definition choice, an audited
             * complete backup, or an exact confirmed v1 preview. Fresh choices
             * create revision zero, an empty graph, no draft, one canonical
             * initial record, and empty activity. Backup preserves its complete
             * lineage. V1 establishes a new revision-zero lineage with the
             * translated graph and definitions. Failure publishes no partial
             * destination. After initialization, offer an explicit STDIO or HTTP
             * agent connection; connection failure never rolls back initialization.
             */
            }
        }
    }

    use case def 'Connect trusted MCP agent' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            require constraint {
            doc /*
             * Probe the intended installed Vellis target before registering it
             * through a supported public client interface. STDIO uses the exact
             * foreground server command. Guided HTTP uses a secret bearer token;
             * non-loopback HTTP always requires it. Replacement requires explicit
             * owner confirmation after a successful target probe. External client
             * mutation failure is reported truthfully with recovery action and
             * never described as rolled back. Vellis edits no client configuration file.
             */
            }
        }
    }

    use case def 'Use AI with persistent personal context' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            require constraint {
            doc /*
             * A cold trusted agent discovers relevant definitions and uses one
             * bounded identity or connected-pattern query to obtain only requested
             * context. It submits active personal-context change only after owner
             * approval in the surrounding workflow. Later sessions and restarts
             * retrieve accepted context; declined, malformed, rejected, or failed
             * changes do not enter canonical memory. Vellis implements neither
             * prompting, approval policy, roles, nor authorization scope.
             */
            }
        }
    }

    use case def 'Correct or forget personal context' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            require constraint {
            doc /*
             * Apply explicit field patches and removals as one conforming
             * owner-directed active batch. No dependent context is cascaded.
             * Rejection preserves canonical state; accepted history remains
             * available even after current content is removed.
             */
            }
        }
    }

    use case def 'Govern definitions and coordinated context' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            require constraint {
            doc /*
             * Build one durable bucket of complete definition replacements and
             * field-level graph deltas while live context may continue to change.
             * Inspect raw operations, query effective draft meaning, and validate
             * current findings. Then leave it staged, activate after fresh complete
             * validation, or discard it. No public version, status, assessment
             * identity, or activation token mediates this owner workflow.
             */
            }
        }
    }

    use case def 'Review personal memory and activity' {
        subject system : 'Vellis System';
        actor owner : Owner;
        actor agent : 'MCP Agent';
        objective {
            require constraint {
            doc /*
             * Explore current or historical graph and definitions at an exact
             * evaluated revision and inspect complete bounded canonical or
             * activity intervals. Canonical history is corruption-evident and
             * activity is observational. Activity detail supports later external
             * owner-visible analysis without implementing analysis agents,
             * conversation capture, or automatic pruning.
             */
            }
        }
    }

    use case def 'Restore prior personal memory' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            require constraint {
            doc /*
             * With no draft, select revision or time and restore its graph and
             * definitions as one new validated revision without rewriting
             * intervening history. Equality is an accepted activity-only no-op.
             */
            }
        }
    }

    use case def 'Back up personal Vellis' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            require constraint {
            doc /*
             * While serving, create and audit one owner-private complete backup
             * suitable for empty-destination initialization. Include ledgers,
             * settings, draft, and useful validation state; exclude token, v1
             * source, and v1 report sidecars. Reading the source adds no activity.
             */
            }
        }
    }

    use case def 'Audit personal Vellis' {
        subject system : 'Vellis System';
        actor owner : Owner;
        objective {
            require constraint {
            doc /*
             * Verify complete stored integrity and graph conformance without
             * modifying the source. Report corruption or inconsistency rather
             * than repairing, replaying, or silently replacing state.
             */
            }
        }
    }

    use case def 'Begin from Vellis v1 snapshot' {
        subject system : 'Vellis System';
        actor owner : Owner;
        in ref item source : 'V1 Snapshot';
        in ref item confirmedPreview [0..1] : 'V1 Import Preview';
        objective {
            require constraint {
            doc /*
             * Stream one complete v1 snapshot into transient staging with bounded
             * memory. Missing system.live means true; omit and report non-live
             * content. Preserve live identity, kind, type, names, associations,
             * links, endpoints, and nonempty legacy metadata. Infer one scalar
             * property kind across declaration and live values; null plus one kind
             * becomes nullable, while nested, unsafe, or incompatible values make
             * the entire property canonical JSON text. Do not infer date or
             * timestamp from strings. Map a relationship rule only when exactly
             * reducible to one type's local bound; otherwise omit and report it.
             * Block unresolved live references, identity conflicts, or loss.
             * Confirmation is bound to unchanged source and deterministic report
             * digests. Success publishes exactly revision zero with its one
             * initialization record, no imported predecessor transitions, no
             * draft or activity, plus the owner-private report sidecar;
             * any refusal or failure publishes nothing.
             */
            }
        }
    }

    dependency freshInitialization
        from 'Begin using personal Vellis' to RTGSystem::'Initialize fresh RTG';
    dependency contextualQuery
        from 'Use AI with persistent personal context' to RTGSystem::'Discover evaluated definitions',
            RTGSystem::'Query evaluated graph', RTGSystem::'Apply active graph change';
    dependency definitionGovernance
        from 'Govern definitions and coordinated context' to RTGSystem::'Edit durable draft',
            RTGSystem::'Inspect durable draft', RTGSystem::'Validate current or draft state',
            RTGSystem::'Activate durable draft', RTGSystem::'Discard durable draft';
    dependency reviewHistory
        from 'Review personal memory and activity' to RTGSystem::'Inspect bounded history';
    dependency restoreMemory
        from 'Restore prior personal memory' to RTGSystem::'Restore historical state';
    dependency backupMemory from 'Back up personal Vellis' to RTGSystem::'Back up complete RTG';
    dependency auditMemory from 'Audit personal Vellis' to RTGSystem::'Audit complete RTG';

    part def Context {
        part system : 'Vellis System';
        ref part owner : Owner;
        ref part agent : 'MCP Agent';
        use case begin : 'Begin using personal Vellis' {
            subject redefines system = Context::system; actor redefines owner = Context::owner;
        }
        use case 'connect' : 'Connect trusted MCP agent' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner; actor redefines agent = Context::agent;
        }
        use case persistentContext : 'Use AI with persistent personal context' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner; actor redefines agent = Context::agent;
        }
        use case correct : 'Correct or forget personal context' {
            subject redefines system = Context::system; actor redefines owner = Context::owner;
        }
        use case govern : 'Govern definitions and coordinated context' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner; actor redefines agent = Context::agent;
        }
        use case review : 'Review personal memory and activity' {
            subject redefines system = Context::system;
            actor redefines owner = Context::owner; actor redefines agent = Context::agent;
        }
        use case restore : 'Restore prior personal memory' {
            subject redefines system = Context::system; actor redefines owner = Context::owner;
        }
        use case backup : 'Back up personal Vellis' {
            subject redefines system = Context::system; actor redefines owner = Context::owner;
        }
        use case audit : 'Audit personal Vellis' {
            subject redefines system = Context::system; actor redefines owner = Context::owner;
        }
        use case importV1 : 'Begin from Vellis v1 snapshot' {
            subject redefines system = Context::system; actor redefines owner = Context::owner;
        }
    }
}
