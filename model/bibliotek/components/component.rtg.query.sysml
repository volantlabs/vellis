library package BibliotekRtgQuery {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;
    private import BibliotekRtgGraph::*;

    doc /* Declarative, read-only matching over one coherent RTG graph read view. */

    enum def RtgQueryOperator {
        enum exists; enum equals;
        enum not_equals;
        enum lt;
        enum lte;
        enum gt;
        enum gte;
        enum contains;
        enum 'in';
        enum substring; enum regex;
    }
    enum def RtgQueryLiveFilter { enum 'all'; enum live; enum non_live; }
    enum def RtgQueryOrderDirection { enum ascending; enum descending; }
    enum def RtgQueryUnknownTermGuidance { enum none; enum suggest_discovery; }
    enum def RtgQueryDiagnosticSeverity { enum warning; enum info; }

    attribute def RtgQueryAnchorBucket {
        attribute name : String;
        attribute anchorTypeKeys[1..*] : String;
    }
    attribute def RtgQueryLinkRequirement {
        attribute name : String;
        attribute sourceBucket : String;
        attribute targetBucket : String;
        attribute linkTypeKeys[1..*] : String;
    }
    attribute def RtgQueryPropertyPredicate {
        attribute path[1..*] : String;
        attribute operator : RtgQueryOperator;
        attribute value[0..1] : JsonValue;
        attribute values[0..*] : JsonScalar;
        attribute caseSensitive : Boolean = false;
        attribute regexFlags[0..*] : String;
    }
    attribute def RtgQueryDataRequirement {
        attribute name : String;
        attribute anchorBucket : String;
        attribute dataTypeKey : String;
        attribute required : Boolean = true;
        attribute predicates[0..*] : RtgQueryPropertyPredicate;
    }
    attribute def RtgQueryReturnProperty {
        attribute dataRequirement : String;
        attribute path[1..*] : String;
    }
    attribute def RtgQueryReturnSpec {
        attribute anchorBuckets[0..*] : String;
        attribute linkRequirements[0..*] : String;
        attribute dataRequirements[0..*] : String;
        attribute properties[0..*] : RtgQueryReturnProperty;
    }
    attribute def RtgQueryDiagnosticOptions {
        attribute includeNonFatal : Boolean = true;
        attribute unknownTermGuidance : RtgQueryUnknownTermGuidance = RtgQueryUnknownTermGuidance::suggest_discovery;
    }
    attribute def RtgQuerySpec {
        attribute anchorBuckets[1..*] : RtgQueryAnchorBucket;
        attribute linkRequirements[0..*] : RtgQueryLinkRequirement;
        attribute dataRequirements[0..*] : RtgQueryDataRequirement;
        attribute returnSpec[0..1] : RtgQueryReturnSpec;
        attribute diagnosticOptions[0..1] : RtgQueryDiagnosticOptions;
    }
    attribute def RtgQueryOrderBy {
        attribute dataRequirement : String;
        attribute path[1..*] : String;
        attribute direction : RtgQueryOrderDirection = RtgQueryOrderDirection::ascending;
    }
    attribute def RtgQueryOptions {
        attribute liveFilter : RtgQueryLiveFilter = RtgQueryLiveFilter::'all';
        attribute liveStatusOverlay[0..*] : RtgQueryLiveStatusOverride;
        attribute orderBy[0..*] : RtgQueryOrderBy;
    }
    attribute def RtgQueryLiveStatusOverride {
        attribute objectUuid : Uuid;
        attribute live : Boolean;
        doc /* One entry in a unique object-UUID-to-effective-live-status map used only for selection. */
    }
    attribute def RtgQueryNamedObjectBinding {
        attribute name : String;
        attribute objectUuid : Uuid;
        doc /* One unique query name to matched graph-object identity binding. */
    }
    attribute def RtgQueryBindingRow {
        attribute rowIndex : Integer;
        attribute anchors[1..*] : RtgQueryNamedObjectBinding;
        attribute links[0..*] : RtgQueryNamedObjectBinding;
        attribute dataObjects[0..*] : RtgQueryNamedObjectBinding;
    }
    attribute def RtgQueryReturnRow {
        attribute rowIndex : Integer;
        attribute anchors[0..*] : RtgQueryNamedObjectBinding;
        attribute links[0..*] : RtgQueryNamedObjectBinding;
        attribute dataObjects[0..*] : RtgQueryNamedObjectBinding;
        attribute properties : JsonObject;
        doc /* Binding entry collections have unique names and realization codecs encode them as JSON objects from name to UUID. */
    }
    attribute def RtgQueryDiagnostic {
        attribute severity : RtgQueryDiagnosticSeverity;
        attribute code : String;
        attribute 'message' : String;
        attribute suggestion[0..1] : String;
        attribute affectedTerms[0..*] : String;
        attribute diagnostic[0..1] : JsonObject;
    }
    attribute def RtgQueryResult {
        attribute bindings[0..*] : RtgQueryBindingRow;
        attribute returns[0..*] : RtgQueryReturnRow;
        attribute diagnostics[0..*] : RtgQueryDiagnostic;
    }
    attribute def RtgQuerySpecInvalid { attribute 'message' : String; attribute diagnostic : JsonObject; }
    attribute def RtgQueryUnsupported { attribute 'message' : String; attribute diagnostic : JsonObject; }

    action def ExecuteRtgQuery {
        in graph : RtgGraphReadView;
        in querySpec : RtgQuerySpec;
        in queryOptions[0..1] : RtgQueryOptions;
        out result : RtgQueryResult;
        doc /* Validate and evaluate the declarative specification over one coherent graph read view, then shape deterministic bindings, returns, and diagnostics without mutation. */
        @FailureContract {
            errorIds = ("RtgQuerySpecInvalid", "RtgQueryUnsupported");
        }
    }

    calc def RtgQueryJsonEqual {
        in left : JsonValue;
        in right : JsonValue;
        doc /* The equality rule used by equals, not_equals, contains, and in predicate evaluation. */
        return equal : Boolean = JsonValueEqual(left, right);
    }

    calc def RtgQueryJsonContains {
        in values[0..*] ordered : JsonValue;
        in candidate : JsonValue;
        doc /* The sequence-membership rule used by contains and in predicate evaluation. */
        return contained : Boolean = JsonSequenceContains(values, candidate);
    }

    part def <'component.rtg.query'> RtgQueryEngine {
        doc /* Evaluate declarative RTG queries against one coherent graph read view without mutation. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }

        perform action execute[0..*] : ExecuteRtgQuery {
            doc /* read only; the supplied graph view is unchanged. */
        }
        dependency executeReadsGraph from execute to execute::graph {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Every read in the invocation observes the supplied coherent view. */
        }
    }


    requirement <'contract.rtg.query.valid_spec'> validQuerySpec {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Names are unique, references resolve, predicate operands fit their operators, and order_by refers only to returned properties. */
        }
    }

    requirement <'contract.rtg.query.defaults'> defaultSemantics {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Data requirements default required=true; predicate case sensitivity defaults false; diagnostic inclusion defaults true with suggest-discovery guidance; absent query options mean all live states, empty overlay, and no order_by; absent order direction means ascending. */
        }
    }

    requirement <'contract.rtg.query.coherent_read_view'> coherentReadView {
        subject operation : ExecuteRtgQuery;
        assume constraint {
            doc /* The supplied graph capability presents one coherent logical view for the invocation. */
        }
        require constraint { doc /* All graph reads in one execution observe one coherent logical graph view supplied by the composition. */ }
    }

    requirement <'contract.rtg.query.matching'> matchingSemantics {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Anchor buckets select matching anchor types; link requirements match directed typed links between bound buckets; data requirements match directly associated typed data objects. Predicates on one data requirement must hold on the same object. */
        }
    }

    requirement <'contract.rtg.query.binding_expansion'> bindingExpansion {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Independent required matches expand to their Cartesian product. A missing required match removes the candidate row; a missing optional match preserves it without that binding. */
        }
    }

    requirement <'contract.rtg.query.predicates'> predicateSemantics {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* exists treats missing paths as false. Equality/not-equality invoke RtgQueryJsonEqual; contains/in membership invoke RtgQueryJsonContains. Relational operators match only two numbers or two strings. Substring defaults case-insensitive. Regex performs an unanchored search using the RE2 2025-11-05 syntax in UTF-8 mode; only case_insensitive and multiline may be supplied as flags. Invalid RE2 syntax and unsupported constructs such as backreferences and lookaround are rejected. Unresolved paths are non-matches, not errors. */
        }
    }

    requirement <'contract.rtg.query.lifecycle_filtering'> lifecycleFiltering {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* The default includes live and non-live objects. Explicit filtering may consult a caller overlay, which changes selection only and never canonical graph state. */
        }
    }

    requirement <'contract.rtg.query.deterministic_result'> deterministicResult {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Base order compares anchor UUIDs in bucket declaration order, then link UUIDs in requirement order, then data UUIDs in requirement order; absent optional data sorts before present UUIDs. order_by applies returned-property keys in caller order and keeps base order as stable tie-breaker; missing/Boolean/object/array keys sort last. rowIndex is zero-based final order. */
        }
    }

    requirement <'contract.rtg.query.return_shaping'> returnShaping {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Return selection never changes matching. Bindings contain names to matched UUIDs; independent matches form a Cartesian product. Returns align one-for-one by rowIndex, include only selected records, and reconstruct selected property paths as nested JSON without delimiter ambiguity. Missing optional bindings or paths are omitted and may produce non-fatal diagnostics. */
        }
    }

    requirement <'contract.rtg.query.diagnostics'> diagnosticSemantics {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Valid queries may return warning/info diagnostics without changing results. Malformed structure, unsupported operators, flags, or ordering references raise declared errors. Stable diagnostic codes distinguish unbound return requirements and unresolved returned property paths and carry generic repair guidance only. */
        }
    }

    requirement <'contract.rtg.query.intentional_boundary'> intentionalBoundary {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Query is a read-only declarative evaluator. It owns no graph, schema, constraint, authorization, visibility, publication, persistence, transport, or UI state; validates no proposed change; infers no facts; and exposes only the modeled RTG query language rather than a general graph-database language. */
        }
    }

    requirement <'invariant.rtg.query.no_mutation'> queryNoMutation {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Query has no owned state and never mutates the supplied graph read view. */
        }
    }

    requirement <'invariant.rtg.query.diagnostics_non_mutating'> diagnosticsAreNonMutating {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Diagnostics explain validation or resolution outcomes without changing query matching or graph state. */
        }
    }

    requirement <'invariant.rtg.query.deterministic_results'> deterministicResults {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Identical coherent graph views, specifications, and options produce identical ordered bindings, returns, and diagnostics. */
        }
    }

    requirement <'invariant.rtg.query.deterministic_string_matching'> deterministicStringMatching {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Substring and regex behavior uses the declared case and dialect rules rather than implementation-language-specific extensions. */
        }
    }

    requirement <'invariant.rtg.query.public_graph_reads_only'> publicGraphReadsOnly {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Query consumes only the public coherent graph read-view capability. */
        }
    }

    requirement <'invariant.rtg.query.operates_over_read_view'> operatesOverReadView {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Live, projected, or alternative providers are substitutable when they satisfy RtgGraphReadView coherently. */
        }
    }

    requirement <'invariant.rtg.query.no_hidden_lifecycle_filter'> noHiddenLifecycleFilter {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Lifecycle filtering occurs only through explicit options and never through hidden live-only defaults. */
        }
    }

    requirement <'invariant.rtg.query.overlay_filters_only'> overlayFiltersOnly {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* A live-status overlay affects selection only and never mutates or rewrites returned graph records. */
        }
    }

    requirement <'invariant.rtg.query.default_includes_non_live'> defaultIncludesNonLive {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Absent options include live and non-live objects. */
        }
    }

    requirement <'invariant.rtg.query.discovery_independent'> discoveryIndependent {
        subject query : RtgQueryEngine;
        require constraint {
            doc /* Query returns its own generic diagnostics and never invokes discovery or embeds application-specific schema answers. */
        }
    }

    requirement <'contract.rtg.query.execute_rtg_query.failures'> executeRtgQueryFailureSemantics {
        subject operation : ExecuteRtgQuery;
        require constraint {
            doc /* Rejected queries leave graph state unchanged and return a structured diagnostic. */
        }
    }

    part contractContext {
        part query : RtgQueryEngine;
        satisfy validQuerySpec by query.execute;
        satisfy defaultSemantics by query.execute;
        satisfy coherentReadView by query.execute;
        satisfy matchingSemantics by query.execute;
        satisfy bindingExpansion by query.execute;
        satisfy predicateSemantics by query.execute;
        satisfy lifecycleFiltering by query.execute;
        satisfy deterministicResult by query.execute;
        satisfy returnShaping by query.execute;
        satisfy diagnosticSemantics by query.execute;
        satisfy intentionalBoundary by query;
        satisfy queryNoMutation by query;
        satisfy diagnosticsAreNonMutating by query;
        satisfy deterministicResults by query;
        satisfy deterministicStringMatching by query;
        satisfy publicGraphReadsOnly by query;
        satisfy operatesOverReadView by query;
        satisfy noHiddenLifecycleFilter by query;
        satisfy overlayFiltersOnly by query;
        satisfy defaultIncludesNonLive by query;
        satisfy discoveryIndependent by query;

        satisfy executeRtgQueryFailureSemantics by query.execute;
    }

    verification def ExecuteRtgQueryContractVerification {
        subject operation : ExecuteRtgQuery;
        objective {
            verify validQuerySpec;
            verify defaultSemantics;
            verify coherentReadView;
            verify matchingSemantics;
            verify bindingExpansion;
            verify predicateSemantics;
            verify lifecycleFiltering;
            verify deterministicResult;
            verify returnShaping;
            verify diagnosticSemantics;

            verify executeRtgQueryFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "components/rtg/query/tests/test_rtg_query_contract.py#ExecuteRtgQueryContractVerification";
            implementationScope = "SimpleRtgQueryEngine";
        }
    }


    verification def RtgQueryBoundaryVerification {
        subject query : RtgQueryEngine;
        objective {
verify queryNoMutation;
            verify diagnosticsAreNonMutating;
            verify deterministicResults;
            verify deterministicStringMatching;
            verify publicGraphReadsOnly;
            verify operatesOverReadView;
            verify noHiddenLifecycleFilter;
            verify overlayFiltersOnly;
            verify defaultIncludesNonLive;
            verify discoveryIndependent;
            verify intentionalBoundary;
        }
        @EvidenceBinding {
                        evidenceId = "components/rtg/query/tests/test_rtg_query_contract.py#RtgQueryBoundaryVerification";
            implementationScope = "SimpleRtgQueryEngine";
        }
    }
}
