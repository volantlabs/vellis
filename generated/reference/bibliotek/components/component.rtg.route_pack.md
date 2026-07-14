# component.rtg.route_pack

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `RtgRoutePack`
- Lifecycle: `draft`
- Purpose: Assemble and gate advisory RTG execution context while owning no route, plan, graph, bridge, command, snapshot, transport, or persistence state.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `assemble` | `AssembleRoutePack` | in `request: RtgRoutePackAssemblyRequest`; out `result: RtgRoutePackRecord` | `RtgRoutePackInvalid` | Validate finite JSON and hazard shape, copy every input, and derive ready for no hazards or needs_attention for any hazards without executing work. |
| `evaluate` | `EvaluateRoutePack` | in `routePack: RtgRoutePackRecord`; out `result: RtgRoutePackGateRecord` | `RtgRoutePackInvalid` | Validate status consistency, classify blocker, non-blocker, or hazard-free context as blocked, clarify, or invoke, and return normalized copied context and advisory next actions. |

## Construction actions

| Contract | Signature | Principal failures | Meaning |
|---|---|---|---|
| — | — | — | No package-level construction action. |

## Retained collaborator roles

| Role | Kind | Referenced type | Multiplicity |
|---|---|---|---|
| — | — | — | No retained collaborator roles. |

## Owned state

| State feature | Type | Ownership | Meaning |
|---|---|---|---|
| — | — | — | This component owns no abstract state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `assemble` | — | `declared` | Pure route-pack assembly with no state or execution effect. |
| `evaluate` | — | `declared` | Pure gate evaluation with no state or execution effect. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.rtg.route_pack.assembly` | `AssembleRoutePack` | `routePack.assemble` | Assembly preserves every supplied context value and order in independent finite-JSON copies; status is ready exactly when hazards is empty and needs_attention otherwise. Each hazard has non-empty code, severity, and message fields. |
| `contract.rtg.route_pack.gate_decision` | `EvaluateRoutePack` | `routePack.evaluate` | Any severity=blocker hazard yields blocked; otherwise any hazard yields clarify; only a hazard-free ready pack yields invoke. Hazard codes preserve caller order in blocker and clarification groups. |
| `contract.rtg.route_pack.tool_exposure` | `EvaluateRoutePack` | `routePack.evaluate` | Federation tools and recipes remain advisory context, while graph-local MCP tools are copied into allowedTools only for invoke and are empty for clarify or blocked. |
| `contract.rtg.route_pack.next_action_precedence` | `EvaluateRoutePack` | `routePack.evaluate` | Invoke first reports required verification commands, then selects one sole-context matching descriptor read when supplied, otherwise federated-plan execution for several graph contexts, otherwise graph-local MCP hand-off for a selected graph, with a planned federated read as the final fallback. Clarify requests confirmation; blocked stops for each blocker. |
| `invariant.rtg.route_pack.advisory_context_only` | `RtgRoutePack` | `routePack` | Assembly and gating compile no route or plan, inspect no descriptor or graph state, and execute no read, write, bridge change, MCP tool, network call, or verification command. |
| `invariant.rtg.route_pack.no_input_mutation` | `RtgRoutePack` | `routePack` | Both actions return isolated JSON-safe records and mutate no request, route pack, graph, bridge, snapshot, dependency, command, or external storage. |
| `contract.rtg.route_pack.intentional_boundary` | `RtgRoutePack` | `routePack` | The component infers no hazards, authorizes no user or write target, selects no bridge permission, opens no filesystem path carried as inert text, and consumes no graph, registry, controller, query, schema, storage, transport, or network private internals. |
| `contract.rtg.route_pack.assemble.failures` | `AssembleRoutePack` | `routePack.assemble` | Malformed or non-finite JSON and malformed hazard records return no partial pack and leave all caller values unchanged. |
| `contract.rtg.route_pack.evaluate.failures` | `EvaluateRoutePack` | `routePack.evaluate` | Malformed required fields, inconsistent status and hazards, or an invalid direct-read graph identity return no partial gate record and leave the supplied pack unchanged. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RtgRoutePackAssemblyRequest` | `attribute` | `intent: JsonObject`, `selectedSkill: JsonObject`, `scopedTools: JsonObject`, `requiredDocs[0..*] ordered: String`, `verificationCommands[0..*] ordered: JsonObject`, `freshnessAndEvidence: JsonObject`, `identityAndCitationRules: JsonObject`, `singleGraphRoute: JsonObject`, `federatedPlan: JsonObject`, `graphContexts[0..*] ordered: JsonObject`, `hazards[0..*] ordered: JsonObject` | Adapter-prepared intent, skill, route, plan, graph context, evidence, verification, and hazard records; route correctness remains advisory and caller-owned. |
| `RtgRoutePackRecord` | `attribute` | `status: RtgRoutePackStatus`, `intent: JsonObject`, `selectedSkill: JsonObject`, `scopedTools: JsonObject`, `requiredDocs[0..*] ordered: String`, `verificationCommands[0..*] ordered: JsonObject`, `freshnessAndEvidence: JsonObject`, `identityAndCitationRules: JsonObject`, `singleGraphRoute: JsonObject`, `federatedPlan: JsonObject`, `graphContexts[0..*] ordered: JsonObject`, `hazards[0..*] ordered: JsonObject` | Canonical isolated copy of one advisory route context; ready has no hazards and needs_attention has one or more hazards. |
| `RtgRoutePackGateRecord` | `attribute` | `decision: RtgRoutePackDecision`, `reason: String`, `intent: JsonObject`, `routePackStatus: RtgRoutePackStatus`, `selectedSkill: JsonObject`, `graphTargets: JsonObject`, `allowedTools: JsonObject`, `requiredDocs[0..*] ordered: String`, `requiredVerificationCommands[0..*] ordered: JsonObject`, `freshnessAndEvidence: JsonObject`, `hazards[0..*] ordered: JsonObject`, `blockingHazardCodes[0..*] ordered: String`, `clarificationHazardCodes[0..*] ordered: String`, `nextActions[0..*] ordered: JsonObject` | Normalized execution decision and advisory next actions; the record describes but never performs those actions. |
| `RtgRoutePackInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RtgRoutePackStatus` | `ready`, `needs_attention` |
| `RtgRoutePackDecision` | `invoke`, `clarify`, `blocked` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `AssembleRoutePackContractVerification` | `AssembleRoutePack` | `assemblySemantics`, `assembleRoutePackFailureSemantics` | `components/rtg/route_pack/tests/test_rtg_route_pack_contract.py#AssembleRoutePackContractVerification` |
| `EvaluateRoutePackContractVerification` | `EvaluateRoutePack` | `gateDecision`, `toolExposure`, `nextActionPrecedence`, `evaluateRoutePackFailureSemantics` | `components/rtg/route_pack/tests/test_rtg_route_pack_contract.py#EvaluateRoutePackContractVerification` |
| `RtgRoutePackBoundaryVerification` | `RtgRoutePack` | `advisoryContextOnly`, `noInputMutation`, `intentionalBoundary` | `components/rtg/route_pack/tests/test_rtg_route_pack_contract.py#RtgRoutePackBoundaryVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
