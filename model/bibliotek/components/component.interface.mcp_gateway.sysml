library package BibliotekInterfaceMcpGateway {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRuntimeMessageRuntime::*;
    private import ScalarValues::*;

    attribute def McpGatewayToolRegistration {
        attribute toolName : String;
        attribute description : String;
        attribute parameterSchema : JsonObject;
        attribute annotations : JsonObject;
        attribute targetInstanceKey : String;
        attribute componentContractId : String;
        attribute actionId : String;
        attribute schemaVersion : Integer;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute requestCodecId : String;
        attribute requestCodecVersion : Integer;
        attribute requestPayloadDisposition : RuntimePayloadDisposition;
        attribute resultPayloadDisposition : RuntimePayloadDisposition;
        attribute faultPayloadDisposition : RuntimePayloadDisposition;
        attribute effectPayloadDisposition[0..1] : RuntimePayloadDisposition;
    }
    attribute def McpGatewayInvocation {
        attribute toolName : String;
        attribute arguments : JsonObject;
    }
    attribute def McpGatewayOutcome {
        attribute toolName : String;
        attribute result : JsonObject;
        attribute messageId : Uuid;
        attribute traceId : Uuid;
        attribute terminalPosition : Integer;
        attribute traceDisposition : RuntimeTraceDisposition;
    }
    attribute def McpGatewayRegistrationInvalid { attribute 'message' : String; }
    attribute def McpGatewayToolUnknown { attribute 'message' : String; }
    attribute def McpGatewayInvocationInvalid { attribute 'message' : String; }

    action def RegisterMcpGatewayTools {
        in registrations[1..*] : McpGatewayToolRegistration;
        doc /* Replace the curated tool inventory with schema-valid unique registrations. */
        @FailureContract { errorIds = ("McpGatewayRegistrationInvalid"); }
    }
    action def GetMcpGatewayRegistrations {
        out registrations[0..*] : McpGatewayToolRegistration;
        doc /* Return a defensive ordered snapshot of the current curated tool inventory. */
        @FailureContract { errorIds = (); }
    }
    action def InvokeMcpGatewayTool {
        in invocation : McpGatewayInvocation;
        out outcome : McpGatewayOutcome;
        doc /* Validate one curated tool call, dispatch one runtime request, and return the registered encoded result. */
        @FailureContract { errorIds = ("McpGatewayToolUnknown", "McpGatewayInvocationInvalid", "RuntimeRegistrationInvalid", "RuntimeAddressUnknown", "RuntimeActionUnknown", "RuntimeSchemaUnsupported", "RuntimeMessageConflict", "RuntimeQueueFull", "RuntimeLedgerUnavailable", "RuntimeFailStopped", "RuntimeRequestTimedOut"); }
    }

    part def <'component.interface.mcp_gateway'> McpGateway {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        doc /* Own MCP tool registration and request/response transport mapping without importing application controllers or domain implementations. */
        ref part runtime[1] : MessageRuntime;
        port messages : ~RuntimeMessagePort;
        interface runtimeExchange : RuntimeMessageExchange
            connect messages to runtime.messages;
        attribute registrations[0..*] : McpGatewayToolRegistration;
        perform action registerTools[0..*] : RegisterMcpGatewayTools;
        perform action getRegistrations[0..*] : GetMcpGatewayRegistrations;
        perform action invokeTool[0..*] : InvokeMcpGatewayTool;
        dependency registrationState from registerTools to registrations { @StateAccess { kind = StateAccessKind::write; } doc /* Atomically replace a unique curated tool inventory. */ }
        dependency registrationReadState from getRegistrations to registrations { @StateAccess { kind = StateAccessKind::read; } doc /* Return an ordered defensive snapshot without exposing mutable owned registration state. */ }
        dependency invocationState from invokeTool to registrations { @StateAccess { kind = StateAccessKind::read; } doc /* Resolve only a registered tool and delegate its application behavior through the runtime. */ }
    }

    requirement <'contract.interface.mcp_gateway.curated'> curatedSurface {
        subject gateway : McpGateway;
        require constraint { doc /* Production exposes only registered application operations and never a universal arbitrary-component invocation tool. */ }
    }
    requirement <'contract.interface.mcp_gateway.transport_only'> transportOnly {
        subject gateway : McpGateway;
        require constraint { doc /* The gateway owns MCP schemas and transport outcomes but no application compilation, validation policy, usage guidance, response shaping, or domain coordination. */ }
    }
    requirement <'contract.interface.mcp_gateway.register.failures'> registerFailureSemantics {
        subject operation : RegisterMcpGatewayTools;
        require constraint { doc /* An invalid registration set leaves the prior curated inventory unchanged. */ }
    }
    requirement <'contract.interface.mcp_gateway.registrations.failures'> registrationReadFailureSemantics {
        subject operation : GetMcpGatewayRegistrations;
        require constraint { doc /* Registration reads preserve insertion order, return defensive values, and never change the curated inventory. */ }
    }
    requirement <'contract.interface.mcp_gateway.invoke.failures'> invokeFailureSemantics {
        subject operation : InvokeMcpGatewayTool;
        require constraint { doc /* Unknown tools and invalid arguments are rejected before runtime dispatch; registration, addressing, action, schema, message-conflict, queue, ledger, health, and timeout failures reported by the runtime propagate without retyping and preserve their recorded message evidence. */ }
    }

    part gatewayContractContext {
        part gateway : McpGateway;
        satisfy curatedSurface by gateway;
        satisfy transportOnly by gateway;
        satisfy registerFailureSemantics by gateway.registerTools;
        satisfy registrationReadFailureSemantics by gateway.getRegistrations;
        satisfy invokeFailureSemantics by gateway.invokeTool;
    }
    verification def McpGatewayBoundaryVerification {
        subject gateway : McpGateway;
        objective { verify curatedSurface; verify transportOnly; }
        @EvidenceBinding { evidenceId = "components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#McpGatewayBoundaryVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RegisterMcpGatewayToolsContractVerification {
        subject operation : RegisterMcpGatewayTools;
        objective { verify registerFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#RegisterMcpGatewayToolsContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def GetMcpGatewayRegistrationsContractVerification {
        subject operation : GetMcpGatewayRegistrations;
        objective { verify registrationReadFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#GetMcpGatewayRegistrationsContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def InvokeMcpGatewayToolContractVerification {
        subject operation : InvokeMcpGatewayTool;
        objective { verify invokeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#InvokeMcpGatewayToolContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
}
