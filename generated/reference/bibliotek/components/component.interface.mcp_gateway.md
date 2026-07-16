# component.interface.mcp_gateway

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `McpGateway`
- Lifecycle: `accepted`
- Purpose: Own MCP tool registration and request/response transport mapping without importing application controllers or domain implementations.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `registerTools` | `RegisterMcpGatewayTools` | in `registrations: McpGatewayToolRegistration[1..*]` | `McpGatewayRegistrationInvalid` | Replace the curated tool inventory with schema-valid unique registrations. |
| `getRegistrations` | `GetMcpGatewayRegistrations` | out `registrations: McpGatewayToolRegistration[0..*]` | None | Return a defensive ordered snapshot of the current curated tool inventory. |
| `invokeTool` | `InvokeMcpGatewayTool` | in `invocation: McpGatewayInvocation`; out `outcome: McpGatewayOutcome` | `McpGatewayToolUnknown`, `McpGatewayInvocationInvalid`, `RuntimeRegistrationInvalid`, `RuntimeAddressUnknown`, `RuntimeActionUnknown`, `RuntimeSchemaUnsupported`, `RuntimeMessageConflict`, `RuntimeQueueFull`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped`, `RuntimeRequestTimedOut` | Validate one curated tool call, dispatch one runtime request, and return the registered encoded result. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| — | — | — | No package-level construction action. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| `runtime` | `part` | `MessageRuntime` | `[1]` |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| `registrations` | `McpGatewayToolRegistration` | `owned` | Typed component state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `registerTools` | `registrations` | `write` | Atomically replace a unique curated tool inventory. |
| `getRegistrations` | `registrations` | `read` | Return an ordered defensive snapshot without exposing mutable owned registration state. |
| `invokeTool` | `registrations` | `read` | Resolve only a registered tool and delegate its application behavior through the runtime. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.interface.mcp_gateway.curated` | `McpGateway` | `gateway` | Production exposes only registered application operations and never a universal arbitrary-component invocation tool. |
| `contract.interface.mcp_gateway.transport_only` | `McpGateway` | `gateway` | The gateway owns MCP schemas and transport outcomes but no application compilation, validation policy, usage guidance, response shaping, or domain coordination. |
| `contract.interface.mcp_gateway.register.failures` | `RegisterMcpGatewayTools` | `gateway.registerTools` | An invalid registration set leaves the prior curated inventory unchanged. |
| `contract.interface.mcp_gateway.registrations.failures` | `GetMcpGatewayRegistrations` | `gateway.getRegistrations` | Registration reads preserve insertion order, return defensive values, and never change the curated inventory. |
| `contract.interface.mcp_gateway.invoke.failures` | `InvokeMcpGatewayTool` | `gateway.invokeTool` | Unknown tools and invalid arguments are rejected before runtime dispatch; registration, addressing, action, schema, message-conflict, queue, ledger, health, and timeout failures reported by the runtime propagate without retyping and preserve their recorded message evidence. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `McpGatewayToolRegistration` | `attribute` | `toolName: String`, `description: String`, `parameterSchema: JsonObject`, `annotations: JsonObject`, `targetInstanceKey: String`, `componentContractId: String`, `actionId: String`, `schemaVersion: Integer`, `bindingId: String`, `bindingVersion: Integer`, `requestCodecId: String`, `requestCodecVersion: Integer`, `requestPayloadDisposition: RuntimePayloadDisposition`, `resultPayloadDisposition: RuntimePayloadDisposition`, `faultPayloadDisposition: RuntimePayloadDisposition`, `effectPayloadDisposition[0..1]: RuntimePayloadDisposition` | Defined by its typed fields and action requirements. |
| `McpGatewayInvocation` | `attribute` | `toolName: String`, `arguments: JsonObject` | Defined by its typed fields and action requirements. |
| `McpGatewayOutcome` | `attribute` | `toolName: String`, `result: JsonObject`, `messageId: Uuid`, `traceId: Uuid`, `terminalPosition: Integer`, `traceDisposition: RuntimeTraceDisposition` | Defined by its typed fields and action requirements. |
| `McpGatewayRegistrationInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `McpGatewayToolUnknown` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `McpGatewayInvocationInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `McpGatewayBoundaryVerification` | `McpGateway` | `curatedSurface`, `transportOnly` | `components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#McpGatewayBoundaryVerification` |
| `RegisterMcpGatewayToolsContractVerification` | `RegisterMcpGatewayTools` | `registerFailureSemantics` | `components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#RegisterMcpGatewayToolsContractVerification` |
| `GetMcpGatewayRegistrationsContractVerification` | `GetMcpGatewayRegistrations` | `registrationReadFailureSemantics` | `components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#GetMcpGatewayRegistrationsContractVerification` |
| `InvokeMcpGatewayToolContractVerification` | `InvokeMcpGatewayTool` | `invokeFailureSemantics` | `components/interface/mcp_gateway/tests/test_mcp_gateway_contract.py#InvokeMcpGatewayToolContractVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
