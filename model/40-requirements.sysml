package VellisRequirements {
    private import RTGSystem::*;
    private import Vellis::*;

    requirement def 'Scalar And Definition Integrity' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * User properties shall contain only Boolean, safe integer, finite
         * binary64 number, exact text, valid Gregorian date, normalized
         * offset-aware timestamp, and permitted null. Integer and number remain
         * distinct; negative number zero normalizes to positive zero. Absence and
         * null remain distinct. Text is neither trimmed nor normalized. Required
         * nullable properties must be present but may be null. Non-null values
         * shall conform to their one declared kind and compatible allowed values,
         * inclusive range, text code-point length, and RE2 whole-string pattern.
         * Definitions shall reject empty or duplicate names, empty descriptions,
         * duplicate canonical allowed values, incompatible or inverted rules,
         * unsafe or non-finite values, invalid dates or timestamps, and unsupported
         * RE2 constructs, without general pattern satisfiability analysis.
         */
        }
    }

    requirement def 'Graph And Lineage Integrity' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * UUIDs shall be canonical valid hyphenated UUIDs, globally unique across
         * graph kinds for the lineage, and permanently reserved to first-used kind.
         * Type keys shall share one exact namespace and remain reserved to their
         * first definition kind. Same-kind retired identities may reactivate.
         * Every current object shall resolve a correct current type. Associated
         * data shall have a nonempty duplicate-free permitted anchor set and only
         * declared conforming properties. Links shall resolve permitted anchor or
         * data endpoints, never links; self-links are valid. Object kind is
         * immutable while type may change explicitly. No removal cascades.
         * Every canonical current or historical object and definition shall expose
         * read-only created and last-changed revisions and optional v1 legacy text.
         * Patches preserve original creation and legacy metadata; reactivation
         * preserves creation and legacy metadata; lastChangedRevision changes only
         * with that subject's canonical content.
         */
        }
    }

    requirement def 'Local Cardinality Integrity' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Associated-data types shall own permitted anchor types, anchors-per-
         * object bounds with minimum at least one, and objects-per-anchor bounds.
         * Link types shall own complete permitted source and target type sets and
         * links-per-source and links-per-target bounds. Each count applies to the
         * complete permitted population of that exact one type. Distinct
         * cardinality meaning requires a distinct type. No independently named,
         * overlapping, participant-subset, or generalized relationship rule is
         * valid system meaning.
         */
        }
    }

    requirement def 'Unified Query Meaning' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * One query shall accept exactly one identity or pattern selection at
         * current, draft, revision, or time state. Identity selection shall
         * resolve known UUIDs without topology or type requirements, preserve
         * request order, report every missing UUID, always return structural and
         * revision-system fields, and hydrate only requested properties and
         * legacy metadata. A live-backed draft result retains its unchanged
         * canonical envelope; a draft-only addition or reactivation has no system
         * envelope until activation. Pattern selection shall name anchor/data nodes and
         * identity-bearing directed links; direct associations are predicates.
         * One node is valid and every larger pattern is connected. Names are
         * unique across nodes and links; distinct names bind distinct identities;
         * reusing one endpoint node requests a real self-link. Type and UUID
         * filters intersect. Conditions are conjunctive; type/UUID lists and
         * anyOf are the only local alternatives. Every node and link selector is
         * returned. No hidden variable, arbitrary projection, aggregation,
         * disconnected product, traversal, grouping, computed expression,
         * caller ordering, or general OR language exists. Accepted identity and
         * pattern results have exactly their selection-specific payload;
         * semantic rejection has no query payload.
         */
        }
    }

    requirement def 'Query Predicate And Search Integrity' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Property predicates apply only to typed associated-data nodes and
         * display-name predicates only to anchors. Presence, absence, null,
         * equality, inequality, same-kind ordering, anyOf, contains, prefix,
         * RE2 substring regex, and structured all-term, any-term, and phrase
         * full-text matching shall have their selected closed meanings. Exact
         * equality and ordering use code-point exact text. Case-insensitive
         * contains/prefix use Unicode case folding without diacritic removal.
         * Full text is case- and diacritic-insensitive over anchor names and text
         * properties, accepts no raw FTS syntax, and returns Boolean matches only.
         * Unknown or incompatible fields, types, properties, values, endpoints,
         * selectors, or predicates reject the whole request.
         */
        }
    }

    requirement def 'Bounded Query Safety' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * No match is an accepted empty result. Pattern evaluation shall establish
         * distinct complete binding tuples only through maximum plus one. An
         * additional tuple rejects without rows or hydrated values. Hydration
         * occurs only after the bounded row set and each returned object occurs
         * once by UUID. Results and findings are deterministic. Queries alter no
         * canonical or draft content. Ordinary query work may depend on stated
         * candidates, predicates, matching relationships, and bounded answers but
         * not excluded history, unrelated populations, or unrequested value
         * hydration. Server aggregation, fuzzy matching, ranking, embeddings,
         * phonetic matching, and semantic similarity remain absent.
         */
        }
    }

    requirement def 'Atomic Field Change' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Active graph change shall first compare expectedRevision with current
         * revision. A UUID absent from current state is created only with complete
         * required content; an existing UUID changes only supplied fields.
         * Properties independently set, set null, remove, or remain untouched;
         * associations independently add, remove, or remain untouched. Explicit
         * property sets contain exactly one value or null. A property cannot be
         * both set and removed, and an anchor cannot be both added and removed,
         * in one upsert; these contradictions reject without state change.
         * object removal alone retires an object. Removing absent content and
         * adding an existing association are accepted no-ops. One UUID occurs in
         * at most one command. The complete batch is interpreted against its
         * final combined state independent of command ordering. Surviving
         * dangling dependents reject and identify every affected dependent; no
         * cascade is inferred. Validation visits only the changed neighborhood,
         * old/new types, old/new relationships, direct dependents, and exact
         * cardinality subjects whose count can change. A redundant accepted batch
         * appends activity without canonical revision; an effective batch creates
         * exactly one revision and one atomic canonical/activity effect.
         */
        }
    }

    requirement def 'Durable Draft Governance' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * At most one durable noncanonical draft bucket shall contain complete
         * definition replacements/removals and normalized field-level graph
         * patches/removals. Later staged fields replace prior operations for those
         * fields; tombstone replaces the whole entry; later upsert after tombstone
         * starts over the then-current live base; whole-entry unstage removes it.
         * Draft editing never advances canonical revision and may leave effective
         * meaning nonconforming. Live writes never rewrite draft entries. Staged
         * fields win over corresponding latest live fields; unrelated live fields
         * survive; staged add/remove guarantees membership or absence; tombstone
         * hides the whole object. Loss of a partial patch's live base is a finding
         * unless it now has complete create content. Compatible live creation
         * combines with staged fields; kind conflict is invalid. Draft reads may
         * evaluate mechanically representable portions and reject a query that
         * needs an unmaterializable object. No public draft version, status,
         * digest, stale flag, assessment identity, or activation token exists.
         * Empty draft change is an accepted no-op and creates no draft. Selecting
         * draft state or draft validation while no draft exists shall reject.
         * Draft entries never contain system metadata. Effective draft content
         * backed by a live object or definition exposes that unchanged canonical
         * envelope; a staged addition or reactivation exposes none. Activation
         * alone applies ordinary create, update, or reactivation metadata rules.
         */
        }
    }

    requirement def 'Draft Inspection Validation And Activation' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Draft inspection shall expose filtered raw entries, current and
         * proposed content, exact staged graph operations, effect flags, and
         * whole-draft raw/effective counts through a bounded opaque continuation.
         * Empty fresh filter collections select all entries; fresh inspection
         * requires a limit and no cursor, while continuation accepts only its
         * cursor and reuses the bound filters and limit. Fresh validation requires
         * scope and limit; continuation requires the same scope and cursor with no
         * limit. Invalid combinations form no domain request.
         * Draft absence yields an accepted empty inspection with presence false.
         * Validation shall compute all current or effective-draft findings once,
         * report cleanliness and total, and page only the latest backing per
         * scope. Continuations expire on relevant content or newer-call changes.
         * Activation shall in one atomic operation read latest live and draft,
         * compose patches, remove redundant operations, apply tombstones, and
         * validate complete effective state. Invalid activation preserves both
         * and publishes findings. Valid effective activation creates one revision
         * and clears draft. Valid redundant activation clears draft without a
         * revision. Discard clears draft without canonical effect and absence is
         * a no-op. Validation always returns current findings; no separate status
         * operation or prior validation authority is required. Inspection appends
         * activity. Validation backing publication and activity append are one
         * atomic observational effect and change no canonical or draft content.
         * Accepted draft change/inspection and completed validation carry their
         * complete purpose payload. Other rejection omits it, except invalid
         * activation, which returns validation totals, cleanliness, its first
         * finding page, and a continuation when more findings remain.
         */
        }
    }

    requirement def 'Historical State And Canonical Ledger' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Current, draft, established revision, and time reads shall report one
         * evaluated revision. Time selects the greatest revision recorded at or
         * before it, with greatest revision winning tied times; before revision
         * zero is unresolved. Canonical commit times never decrease. Current and
         * historical state shall be directly selectable through indexed version
         * presence, never public replay. One contiguous corruption-evident
         * canonical record per established revision shall expose time,
         * provenance, transition kind, bounded summary, and affected identities,
         * not a replay payload or snapshot. Removed definitions and graph objects
         * remain historically queryable. Ordinary restart shall not traverse a
         * ledger to reconstruct current state.
         */
        }
    }

    requirement def 'Activity Separation And Privacy' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Activity shall remain observational and incapable of establishing
         * canonical state. Semantic is the initial mode. An owner-selected
         * semantic/verbose mode change appends configuration activity without a
         * canonical revision; rejection or failure preserves the prior mode.
         * Semantic mode records normalized requests needed for
         * later owner analysis, truthful bounded result shape, complete findings,
         * accepted mutation effects, and complete rejected mutation requests.
         * Verbose mode additionally records full normalized request/response
         * payloads separately. History reads shall not recursively copy selected
         * entries, and shall select before recording themselves. Tokens,
         * authorization headers, malformed transport content, environment,
         * process arguments, v1 source content, and secrets shall never be
         * captured. Setup/import starts with empty activity; backup, audit, and
         * probing are read-only. Header/payload separation is the only retained
         * seam for future explicitly enabled analysis or conversation events;
         * neither feature nor automatic pruning exists now.
         */
        }
    }

    requirement def 'History Restore Audit And Backup' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * History reads shall return one complete canonical or activity interval
         * by inclusive time or by sequence range with an exclusive after and
         * inclusive through boundary, report observed head, preserve
         * ledger order, and reject whole beyond the caller maximum. Omitted range
         * or a range with both bounds absent selects through the observed head;
         * reversed time bounds reject and sequence after at or beyond through is
         * accepted empty. Accepted history returns only its selected ledger family
         * and kind-specific head; rejected history has no purpose payload. Restore shall
         * refuse with a draft, validate selected historical graph/definitions,
         * preserve intervening history and identity metadata, and append one new
         * revision only when current meaning changes. Audit shall read-only verify
         * lineage/schema identity, revision/time/hash continuity, version
         * intervals, reservations, definitions, references, graph conformance,
         * indexed projections/search, and activity/validation integrity. Backup
         * shall work while serving, audit before publication, include complete
         * database meaning including draft/settings/ledgers, exclude token and v1
         * sidecars, refuse overwrite, and add no source activity. Initialization
         * from backup requires an empty destination and preserves lineage.
         */
        }
    }

    requirement def 'Locality And Bounded Materialization' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * Ordinary current discovery, query, and active change shall not depend
         * on excluded history or unrelated graph populations and shall not retain
         * a complete graph or definition-set aggregate. Full validation,
         * definition activation, restore, audit, import, and backup may scan all
         * relevant state with bounded working memory. Historical selection shall
         * avoid linear scans of excluded ledger prefixes. No numerical latency,
         * throughput, startup, or storage target is selected before representative
         * runtime, hardware, and owner data exist.
         */
        }
    }

    requirement def 'MCP Boundary Integrity' {
        subject system : 'RTG System';
        require constraint {
        doc /*
         * The selected initial MCP boundary shall expose stable type-summary,
         * type-inspection, unified-query, active-change, draft-inspection,
         * draft-change, validation, draft-activation, draft-discard, and history
         * behaviors through ordinary typed JSON values. The inventory count is
         * not RTG domain authority. Unknown wire members and malformed input form
         * no domain request. Accepted reads carry evaluatedRevision and their
         * complete purpose payload even when its collections are empty. Semantic
         * rejection omits purpose payload unless invalid activation explicitly
         * returns its validation page. A well-formed semantic refusal returns accepted or
         * rejected outcome meaning with concise summary and typed findings.
         * Unexpected runtime or transport failure is an MCP error. Complete
         * response construction shall precede commit, and loss after commit shall
         * never claim rollback. Tool descriptions shall guide cold discovery,
         * direct identity use, bounded pattern narrowing, owner-approved active
         * mutation, and inspect/query/validate/activate draft workflow without a
         * mandatory match/get sequence or status call. RTG implements no role or
         * approval engine. Omitted read state means current. One fixed public
         * item limit of 1000 governs every explicitly bounded public collection,
         * query maximum, page, and history maximum; no per-feature configurable
         * limit exists. Set-like input rejects duplicates. Set-like output and
         * findings use deterministic exact-key/UUID ordering, identity results
         * preserve requested UUID order, and pattern rows order lexicographically
         * by selector-order UUID bindings. Long scalar text has no undocumented
         * truncation threshold.
         */
        }
    }

    requirement def 'Fresh And V1 Initialization' {
        subject system : 'Vellis System';
        require constraint {
        doc /*
         * Fresh initialization shall require an empty destination and explicit
         * blank or recommended Everyday Life choice, establish revision zero,
         * and publish atomically. V1 initialization shall stream one exact source
         * with bounded memory. Missing live means true; non-live content is
         * omitted and reported. Compatible scalar kinds and nullable values are
         * retained; nested, unsafe, or incompatible property occurrences become
         * canonical JSON text for that entire property without binary64 loss.
         * Strings do not infer dates or timestamps. Nonempty legacy system
         * metadata minus live is preserved. Only exactly reducible one-type local
         * bounds map; other relationship rules are omitted and reported. Live
         * unresolved references, kind conflicts, or preservation failure block.
         * Deterministic reports and confirmation bind exact source and report
         * digests. Success publishes candidate revision zero with its one
         * initialization record, no imported predecessor transitions, no draft
         * or activity, and one private report sidecar. Refusal,
         * changed input, or failure publishes nothing and no existing-system merge
         * exists.
         */
        }
    }

    requirement def 'Recommended Everyday Life Start' {
        subject system : 'Vellis System';
        require constraint {
        doc /*
         * Fresh setup shall offer blank and the recommended preselected Everyday
         * Life vocabulary and require confirmation. The starter shall contain
         * exactly the modeled twelve anchors, corresponding twelve details types
         * with preserved property vocabulary, nine link types and endpoint sets,
         * no graph data, details bounds 1..1 anchors per object and 0..1 objects
         * per anchor, and link bounds 0..unbounded at both ends. Its selected date
         * properties shall be true dates and all properties optional non-nullable.
         * Backup and v1 initialization never overlay it; existing systems have no
         * starter-install operation.
         */
        }
    }

    requirement def 'Simple Secure Individual Operation' {
        subject system : 'Vellis System';
        require constraint {
        doc /*
         * One local owner shall initialize, serve, connect, configure activity,
         * rotate an HTTP token, audit, back up, and restore one system without
         * tenant, role, organization, cluster, service-manager, or infrastructure
         * administration. STDIO and foreground HTTP are supported. Guided HTTP
         * uses at least 256 random token bits; non-loopback requires an owner-
         * private token and warns that plaintext HTTP needs a trusted network,
         * tunnel, or external TLS. Tokens never appear in arguments, logs,
         * activity, reports, or backups. Public client CLIs alone manage Codex and
         * Claude registration, with probe-before-replace, explicit confirmation,
         * truthful partial-failure reporting, and no configuration-file edits.
         * Data, backups, activity, and reports are plaintext at rest and this is
         * disclosed. Vellis implements no TLS, OAuth, users, roles, daemon,
         * container, or service manager.
         */
        }
    }

    part vellis : 'Vellis System';

    requirement <RTG001> scalarDefinitions : 'Scalar And Definition Integrity';
    requirement <RTG002> graphLineage : 'Graph And Lineage Integrity';
    requirement <RTG003> localCardinality : 'Local Cardinality Integrity';
    requirement <RTG004> unifiedQuery : 'Unified Query Meaning';
    requirement <RTG005> queryPredicates : 'Query Predicate And Search Integrity';
    requirement <RTG006> querySafety : 'Bounded Query Safety';
    requirement <RTG007> atomicChange : 'Atomic Field Change';
    requirement <RTG008> durableDraft : 'Durable Draft Governance';
    requirement <RTG009> draftWorkflow : 'Draft Inspection Validation And Activation';
    requirement <RTG010> historicalState : 'Historical State And Canonical Ledger';
    requirement <RTG011> activitySeparation : 'Activity Separation And Privacy';
    requirement <RTG012> lifecycle : 'History Restore Audit And Backup';
    requirement <RTG013> locality : 'Locality And Bounded Materialization';
    requirement <RTG014> mcpBoundary : 'MCP Boundary Integrity';
    requirement <VEL001> initialization : 'Fresh And V1 Initialization';
    requirement <VEL002> starter : 'Recommended Everyday Life Start';
    requirement <VEL003> simpleOperation : 'Simple Secure Individual Operation';

    satisfy scalarDefinitions by vellis.memory;
    satisfy graphLineage by vellis.memory;
    satisfy localCardinality by vellis.memory;
    satisfy unifiedQuery by vellis.memory;
    satisfy queryPredicates by vellis.memory;
    satisfy querySafety by vellis.memory;
    satisfy atomicChange by vellis.memory;
    satisfy durableDraft by vellis.memory;
    satisfy draftWorkflow by vellis.memory;
    satisfy historicalState by vellis.memory;
    satisfy activitySeparation by vellis.memory;
    satisfy lifecycle by vellis.memory;
    satisfy locality by vellis.memory;
    satisfy mcpBoundary by vellis.memory;
    satisfy initialization by vellis;
    satisfy starter by vellis;
    satisfy simpleOperation by vellis;
}
