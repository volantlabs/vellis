library package BibliotekRtgGraphRegistry {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /* Draft graph-directory component for deterministic, advisory routing across independently owned RTG graph monographs. */

    enum def RtgGraphOperation {
        enum read;
        enum write;
        enum admin;
    }

    enum def RtgGraphMcpTransport {
        enum http;
        enum stdio;
    }

    attribute def RtgGraphMcpEndpoint {
        attribute transport : RtgGraphMcpTransport;
        attribute host[0..1] : String;
        attribute 'port'[0..1] : Integer;
        attribute path : String default = "/mcp";
        attribute serverName[0..1] : String;
        doc /* Local MCP launch or client-configuration hint; it is not a live transport handle. */
    }

    item def RtgGraphDescriptor {
        attribute graphId : String;
        attribute title : String;
        attribute storageRoot : String;
        attribute sqlDatabasePath : String;
        attribute authority : String;
        attribute writePolicy : String;
        attribute domains[1..*] ordered : String;
        attribute tags[0..*] ordered : String;
        attribute mcpEndpoint[0..1] : RtgGraphMcpEndpoint;
        attribute 'metadata' : JsonObject;
        doc /* Declarative identity, routing vocabulary, authority guidance, local storage pointers, and optional endpoint metadata for one independently owned graph monograph. */
    }

    attribute def RtgGraphIntent {
        attribute operation : RtgGraphOperation;
        attribute text : String;
        attribute targetGraphId[0..1] : String;
        attribute domainHints[0..*] ordered : String;
        attribute tagHints[0..*] ordered : String;
    }

    attribute def RtgGraphRouteCandidate {
        attribute graphId : String;
        attribute score : Real;
        attribute reasons[0..*] ordered : String;
    }

    attribute def RtgGraphRouteRecord {
        attribute intent : RtgGraphIntent;
        attribute candidates[0..*] ordered : RtgGraphRouteCandidate;
        attribute selectedGraphId[0..1] : String;
        attribute requiresConfirmation : Boolean;
        attribute reason : String;
    }

    attribute def RtgGraphFederatedIntent {
        attribute operation : RtgGraphOperation;
        attribute text : String;
        attribute targetGraphIds[0..*] ordered : String;
        attribute domainHints[0..*] ordered : String;
        attribute tagHints[0..*] ordered : String;
    }

    attribute def RtgGraphFederatedPlanStep {
        attribute graphId : String;
        attribute operation : RtgGraphOperation;
        attribute intentText : String;
        attribute score : Real;
        attribute reasons[0..*] ordered : String;
    }

    attribute def RtgGraphFederatedPlan {
        attribute intent : RtgGraphFederatedIntent;
        attribute steps[0..*] ordered : RtgGraphFederatedPlanStep;
        attribute requiresConfirmation : Boolean;
        attribute executable : Boolean;
        attribute reason : String;
    }

    attribute def RtgGraphList {
        item graphs[0..*] ordered : RtgGraphDescriptor;
    }

    attribute def RtgGraphRegistryInvalid { attribute 'message' : String; }
    attribute def RtgGraphNotFound { attribute 'message' : String; }

    action def PutGraph {
        in graph : RtgGraphDescriptor;
        out stored : RtgGraphDescriptor;
        doc /* Normalize, validate, and create or fully replace one descriptor by graphId without probing storage or endpoints. */
        @FailureContract { errorIds = ("RtgGraphRegistryInvalid"); }
    }

    action def ListGraphs {
        out result : RtgGraphList;
        doc /* Return canonical descriptor copies in ascending graphId order. */
        @FailureContract { errorIds = (); }
    }

    action def GetGraph {
        in graphId : String;
        out graph : RtgGraphDescriptor;
        doc /* Return a canonical copy of the descriptor named by normalized graphId. */
        @FailureContract { errorIds = ("RtgGraphRegistryInvalid", "RtgGraphNotFound"); }
    }

    action def CompileIntent {
        in intent : RtgGraphIntent;
        out route : RtgGraphRouteRecord;
        doc /* Rank deterministic candidate descriptors; explicit targets win, unambiguous high-confidence reads may auto-select, and writes without explicit targets never select. */
        @FailureContract { errorIds = ("RtgGraphRegistryInvalid", "RtgGraphNotFound"); }
    }

    action def CompileFederatedIntent {
        in intent : RtgGraphFederatedIntent;
        out plan : RtgGraphFederatedPlan;
        doc /* Produce ordered graph-local advisory steps without executing queries, joining results, resolving identity, or authorizing writes. */
        @FailureContract { errorIds = ("RtgGraphRegistryInvalid", "RtgGraphNotFound"); }
    }

    part def <'component.rtg.graph_registry'> RtgGraphRegistry {
        doc /* Own graph descriptors and deterministic routing decisions while remaining independent of graph contents, execution, transport lifecycle, authorization, and bridge state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        item descriptors[0..*] : RtgGraphDescriptor {
            doc /* Canonical in-memory descriptors keyed by normalized graphId; repository file formats remain adapter concerns. */
        }

        perform action putGraph[0..*] : PutGraph;
        perform action listGraphs[0..*] : ListGraphs;
        perform action getGraph[0..*] : GetGraph;
        perform action compileIntent[0..*] : CompileIntent;
        perform action compileFederatedIntent[0..*] : CompileFederatedIntent;

        dependency putDescriptorState from putGraph to descriptors {
            @StateAccess { kind = StateAccessKind::write; }
            doc /* Atomically create or fully replace one valid descriptor. */
        }
        dependency listDescriptorState from listGraphs to descriptors {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Return ordered descriptor copies without exposing mutable owned state. */
        }
        dependency getDescriptorState from getGraph to descriptors {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Resolve one normalized graph identity without mutation. */
        }
        dependency routeDescriptorState from compileIntent to descriptors {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Rank candidates from descriptor vocabulary without graph-local calls. */
        }
        dependency federatedRouteDescriptorState from compileFederatedIntent to descriptors {
            @StateAccess { kind = StateAccessKind::read; }
            doc /* Compile independent graph-local steps without executing or joining them. */
        }
    }

    action def CreateEmptyRtgGraphRegistry {
        out part registry : RtgGraphRegistry;
        doc /* Return an in-memory registry with no graph descriptors. */
        @FailureContract { errorIds = (); }
    }

    requirement <'contract.rtg.graph_registry.descriptor_validity'> descriptorValidity {
        subject operation : PutGraph;
        require constraint {
            doc /* Descriptor identity and required text are non-empty; graphId and optional serverName are identifiers; domains are non-empty and sequences contain no duplicate normalized values; metadata is finite JSON; HTTP endpoint hints include a host and valid TCP port while paths start with slash. */
        }
    }

    requirement <'contract.rtg.graph_registry.put_effect'> putEffect {
        subject operation : PutGraph;
        require constraint {
            doc /* Success stores exactly one normalized descriptor under graphId, fully replaces any prior descriptor with that identity, returns an independent copy, and leaves other descriptors unchanged; rejection leaves registry state unchanged. */
        }
    }

    requirement <'contract.rtg.graph_registry.read_effects'> readEffects {
        subject registry : RtgGraphRegistry;
        require constraint {
            doc /* Listing is ascending by graphId and get resolves one normalized identity; both return independent copies and never mutate descriptors. */
        }
    }

    requirement <'contract.rtg.graph_registry.route_compilation'> routeCompilation {
        subject operation : CompileIntent;
        require constraint {
            doc /* Explicit existing targetGraphId selects exactly that graph. Otherwise deterministic scoring uses request text, domain hints, and tag hints; only one non-tied read candidate at or above the fixed confidence threshold may auto-select. */
        }
    }

    requirement <'contract.rtg.graph_registry.federated_planning'> federatedPlanning {
        subject operation : CompileFederatedIntent;
        require constraint {
            doc /* Explicit targetGraphIds preserve caller order. Inferred reads include every positive-scoring candidate in deterministic rank order. Write and admin plans remain non-executable and all steps retain graph-local identity. */
        }
    }

    requirement <'invariant.rtg.graph_registry.unique_graph_ids'> uniqueGraphIds {
        subject registry : RtgGraphRegistry;
        require constraint { doc /* At most one canonical descriptor exists for each normalized graphId. */ }
    }

    requirement <'invariant.rtg.graph_registry.deterministic_listing'> deterministicListing {
        subject registry : RtgGraphRegistry;
        require constraint { doc /* List and route outputs are deterministic for the same registry state and normalized intent. */ }
    }

    requirement <'invariant.rtg.graph_registry.no_implicit_write_target'> noImplicitWriteTarget {
        subject registry : RtgGraphRegistry;
        require constraint { doc /* A write or admin intent without an explicit target never selects a graph or yields an executable federated plan. */ }
    }

    requirement <'invariant.rtg.graph_registry.route_records_are_advisory'> routeRecordsAreAdvisory {
        subject registry : RtgGraphRegistry;
        require constraint { doc /* Routing mutates no graph, starts no MCP server, grants no authorization, proves no freshness, and executes no graph-local query. */ }
    }

    requirement <'invariant.rtg.graph_registry.cross_graph_identity_is_explicit'> crossGraphIdentityIsExplicit {
        subject registry : RtgGraphRegistry;
        require constraint { doc /* Graph-local identifiers are meaningful only with graphId; registry behavior never treats raw UUIDs, labels, or domain keys as global identity and never merges graph results. */ }
    }

    requirement <'contract.rtg.graph_registry.intentional_boundary'> intentionalBoundary {
        subject registry : RtgGraphRegistry;
        require constraint { doc /* The component does not open storage, inspect graph contents or validation state, run transports, execute federation capabilities, authorize access, resolve bridges, or own a durable registry file. */ }
    }

    requirement <'contract.rtg.graph_registry.put_graph.failures'> putGraphFailureSemantics {
        subject operation : PutGraph;
        require constraint { doc /* Invalid descriptors expose no partial replacement and leave all descriptors unchanged. */ }
    }
    requirement <'contract.rtg.graph_registry.list_graphs.failures'> listGraphsFailureSemantics {
        subject operation : ListGraphs;
        require constraint { doc /* Listing has no state effect and returns no mutable alias to owned descriptors. */ }
    }
    requirement <'contract.rtg.graph_registry.get_graph.failures'> getGraphFailureSemantics {
        subject operation : GetGraph;
        require constraint { doc /* Invalid or unknown graph identities do not mutate registry state or select a fallback graph. */ }
    }
    requirement <'contract.rtg.graph_registry.compile_intent.failures'> compileIntentFailureSemantics {
        subject operation : CompileIntent;
        require constraint { doc /* Malformed intents and unknown explicit targets do not mutate descriptors or invoke any graph-local capability. */ }
    }
    requirement <'contract.rtg.graph_registry.compile_federated_intent.failures'> compileFederatedIntentFailureSemantics {
        subject operation : CompileFederatedIntent;
        require constraint { doc /* Malformed intents or any unknown explicit target produce no partial plan, state mutation, graph-local call, or joined result. */ }
    }
    requirement <'contract.rtg.graph_registry.create_empty.failures'> createEmptyRtgGraphRegistryFailureSemantics {
        subject operation : CreateEmptyRtgGraphRegistry;
        require constraint { doc /* Construction creates no storage, process, network, graph, or registry-file side effect. */ }
    }

    part contractContext {
        part registry : RtgGraphRegistry;
        satisfy descriptorValidity by registry.putGraph;
        satisfy putEffect by registry.putGraph;
        satisfy readEffects by registry;
        satisfy routeCompilation by registry.compileIntent;
        satisfy federatedPlanning by registry.compileFederatedIntent;
        satisfy uniqueGraphIds by registry;
        satisfy deterministicListing by registry;
        satisfy noImplicitWriteTarget by registry;
        satisfy routeRecordsAreAdvisory by registry;
        satisfy crossGraphIdentityIsExplicit by registry;
        satisfy intentionalBoundary by registry;
        satisfy putGraphFailureSemantics by registry.putGraph;
        satisfy listGraphsFailureSemantics by registry.listGraphs;
        satisfy getGraphFailureSemantics by registry.getGraph;
        satisfy compileIntentFailureSemantics by registry.compileIntent;
        satisfy compileFederatedIntentFailureSemantics by registry.compileFederatedIntent;
        action createEmptySubject : CreateEmptyRtgGraphRegistry;
        satisfy createEmptyRtgGraphRegistryFailureSemantics by createEmptySubject;
    }

    verification def PutGraphContractVerification {
        subject operation : PutGraph;
        objective { verify descriptorValidity; verify putEffect; verify putGraphFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#PutGraphContractVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
    verification def ListGraphsContractVerification {
        subject operation : ListGraphs;
        objective { verify listGraphsFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#ListGraphsContractVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
    verification def GetGraphContractVerification {
        subject operation : GetGraph;
        objective { verify getGraphFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#GetGraphContractVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
    verification def CompileIntentContractVerification {
        subject operation : CompileIntent;
        objective { verify routeCompilation; verify compileIntentFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#CompileIntentContractVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
    verification def CompileFederatedIntentContractVerification {
        subject operation : CompileFederatedIntent;
        objective { verify federatedPlanning; verify compileFederatedIntentFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#CompileFederatedIntentContractVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
    verification def CreateEmptyRtgGraphRegistryContractVerification {
        subject operation : CreateEmptyRtgGraphRegistry;
        objective { verify createEmptyRtgGraphRegistryFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#CreateEmptyRtgGraphRegistryContractVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
    verification def RtgGraphRegistryBoundaryVerification {
        subject registry : RtgGraphRegistry;
        objective { verify readEffects; verify uniqueGraphIds; verify deterministicListing; verify noImplicitWriteTarget; verify routeRecordsAreAdvisory; verify crossGraphIdentityIsExplicit; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/graph_registry/tests/test_rtg_graph_registry_contract.py#RtgGraphRegistryBoundaryVerification"; implementationScope = "InMemoryRtgGraphRegistry"; }
    }
}
