library package BibliotekRtgRoutePack {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    doc /* Draft stateless assembly and hazard gating of adapter-supplied advisory context for routed RTG work. */

    enum def RtgRoutePackStatus { enum ready; enum needs_attention; }
    enum def RtgRoutePackDecision { enum invoke; enum clarify; enum blocked; }

    attribute def RtgRoutePackAssemblyRequest {
        attribute intent : JsonObject;
        attribute selectedSkill : JsonObject;
        attribute scopedTools : JsonObject;
        attribute requiredDocs[0..*] ordered : String;
        attribute verificationCommands[0..*] ordered : JsonObject;
        attribute freshnessAndEvidence : JsonObject;
        attribute identityAndCitationRules : JsonObject;
        attribute singleGraphRoute : JsonObject;
        attribute federatedPlan : JsonObject;
        attribute graphContexts[0..*] ordered : JsonObject;
        attribute hazards[0..*] ordered : JsonObject;
        doc /* Adapter-prepared intent, skill, route, plan, graph context, evidence, verification, and hazard records; route correctness remains advisory and caller-owned. */
    }

    attribute def RtgRoutePackRecord {
        attribute status : RtgRoutePackStatus;
        attribute intent : JsonObject;
        attribute selectedSkill : JsonObject;
        attribute scopedTools : JsonObject;
        attribute requiredDocs[0..*] ordered : String;
        attribute verificationCommands[0..*] ordered : JsonObject;
        attribute freshnessAndEvidence : JsonObject;
        attribute identityAndCitationRules : JsonObject;
        attribute singleGraphRoute : JsonObject;
        attribute federatedPlan : JsonObject;
        attribute graphContexts[0..*] ordered : JsonObject;
        attribute hazards[0..*] ordered : JsonObject;
        doc /* Canonical isolated copy of one advisory route context; ready has no hazards and needs_attention has one or more hazards. */
    }

    attribute def RtgRoutePackGateRecord {
        attribute decision : RtgRoutePackDecision;
        attribute reason : String;
        attribute intent : JsonObject;
        attribute routePackStatus : RtgRoutePackStatus;
        attribute selectedSkill : JsonObject;
        attribute graphTargets : JsonObject;
        attribute allowedTools : JsonObject;
        attribute requiredDocs[0..*] ordered : String;
        attribute requiredVerificationCommands[0..*] ordered : JsonObject;
        attribute freshnessAndEvidence : JsonObject;
        attribute hazards[0..*] ordered : JsonObject;
        attribute blockingHazardCodes[0..*] ordered : String;
        attribute clarificationHazardCodes[0..*] ordered : String;
        attribute nextActions[0..*] ordered : JsonObject;
        doc /* Normalized execution decision and advisory next actions; the record describes but never performs those actions. */
    }

    attribute def RtgRoutePackInvalid { attribute 'message' : String; }

    action def AssembleRoutePack {
        in request : RtgRoutePackAssemblyRequest;
        out result : RtgRoutePackRecord;
        doc /* Validate finite JSON and hazard shape, copy every input, and derive ready for no hazards or needs_attention for any hazards without executing work. */
        @FailureContract { errorIds = ("RtgRoutePackInvalid"); }
    }

    action def EvaluateRoutePack {
        in routePack : RtgRoutePackRecord;
        out result : RtgRoutePackGateRecord;
        doc /* Validate status consistency, classify blocker, non-blocker, or hazard-free context as blocked, clarify, or invoke, and return normalized copied context and advisory next actions. */
        @FailureContract { errorIds = ("RtgRoutePackInvalid"); }
    }

    part def <'component.rtg.route_pack'> RtgRoutePack {
        doc /* Assemble and gate advisory RTG execution context while owning no route, plan, graph, bridge, command, snapshot, transport, or persistence state. */
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        perform action assemble[0..*] : AssembleRoutePack { doc /* Pure route-pack assembly with no state or execution effect. */ }
        perform action evaluate[0..*] : EvaluateRoutePack { doc /* Pure gate evaluation with no state or execution effect. */ }
    }

    requirement <'contract.rtg.route_pack.assembly'> assemblySemantics {
        subject operation : AssembleRoutePack;
        require constraint { doc /* Assembly preserves every supplied context value and order in independent finite-JSON copies; status is ready exactly when hazards is empty and needs_attention otherwise. Each hazard has non-empty code, severity, and message fields. */ }
    }
    requirement <'contract.rtg.route_pack.gate_decision'> gateDecision {
        subject operation : EvaluateRoutePack;
        require constraint { doc /* Any severity=blocker hazard yields blocked; otherwise any hazard yields clarify; only a hazard-free ready pack yields invoke. Hazard codes preserve caller order in blocker and clarification groups. */ }
    }
    requirement <'contract.rtg.route_pack.tool_exposure'> toolExposure {
        subject operation : EvaluateRoutePack;
        require constraint { doc /* Federation tools and recipes remain advisory context, while graph-local MCP tools are copied into allowedTools only for invoke and are empty for clarify or blocked. */ }
    }
    requirement <'contract.rtg.route_pack.next_action_precedence'> nextActionPrecedence {
        subject operation : EvaluateRoutePack;
        require constraint { doc /* Invoke first reports required verification commands, then selects one sole-context matching descriptor read when supplied, otherwise federated-plan execution for several graph contexts, otherwise graph-local MCP hand-off for a selected graph, with a planned federated read as the final fallback. Clarify requests confirmation; blocked stops for each blocker. */ }
    }
    requirement <'invariant.rtg.route_pack.advisory_context_only'> advisoryContextOnly {
        subject routePack : RtgRoutePack;
        require constraint { doc /* Assembly and gating compile no route or plan, inspect no descriptor or graph state, and execute no read, write, bridge change, MCP tool, network call, or verification command. */ }
    }
    requirement <'invariant.rtg.route_pack.no_input_mutation'> noInputMutation {
        subject routePack : RtgRoutePack;
        require constraint { doc /* Both actions return isolated JSON-safe records and mutate no request, route pack, graph, bridge, snapshot, dependency, command, or external storage. */ }
    }
    requirement <'contract.rtg.route_pack.intentional_boundary'> intentionalBoundary {
        subject routePack : RtgRoutePack;
        require constraint { doc /* The component infers no hazards, authorizes no user or write target, selects no bridge permission, opens no filesystem path carried as inert text, and consumes no graph, registry, controller, query, schema, storage, transport, or network private internals. */ }
    }
    requirement <'contract.rtg.route_pack.assemble.failures'> assembleRoutePackFailureSemantics {
        subject operation : AssembleRoutePack;
        require constraint { doc /* Malformed or non-finite JSON and malformed hazard records return no partial pack and leave all caller values unchanged. */ }
    }
    requirement <'contract.rtg.route_pack.evaluate.failures'> evaluateRoutePackFailureSemantics {
        subject operation : EvaluateRoutePack;
        require constraint { doc /* Malformed required fields, inconsistent status and hazards, or an invalid direct-read graph identity return no partial gate record and leave the supplied pack unchanged. */ }
    }

    part contractContext {
        part routePack : RtgRoutePack;
        satisfy assemblySemantics by routePack.assemble;
        satisfy gateDecision by routePack.evaluate;
        satisfy toolExposure by routePack.evaluate;
        satisfy nextActionPrecedence by routePack.evaluate;
        satisfy advisoryContextOnly by routePack;
        satisfy noInputMutation by routePack;
        satisfy intentionalBoundary by routePack;
        satisfy assembleRoutePackFailureSemantics by routePack.assemble;
        satisfy evaluateRoutePackFailureSemantics by routePack.evaluate;
    }

    verification def AssembleRoutePackContractVerification {
        subject operation : AssembleRoutePack;
        objective { verify assemblySemantics; verify assembleRoutePackFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/route_pack/tests/test_rtg_route_pack_contract.py#AssembleRoutePackContractVerification"; implementationScope = "DeterministicRtgRoutePackBuilder"; }
    }
    verification def EvaluateRoutePackContractVerification {
        subject operation : EvaluateRoutePack;
        objective { verify gateDecision; verify toolExposure; verify nextActionPrecedence; verify evaluateRoutePackFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/rtg/route_pack/tests/test_rtg_route_pack_contract.py#EvaluateRoutePackContractVerification"; implementationScope = "DeterministicRtgRoutePackGate"; }
    }
    verification def RtgRoutePackBoundaryVerification {
        subject routePack : RtgRoutePack;
        objective { verify advisoryContextOnly; verify noInputMutation; verify intentionalBoundary; }
        @EvidenceBinding { evidenceId = "components/rtg/route_pack/tests/test_rtg_route_pack_contract.py#RtgRoutePackBoundaryVerification"; implementationScope = "components.rtg.route_pack"; }
    }
}
