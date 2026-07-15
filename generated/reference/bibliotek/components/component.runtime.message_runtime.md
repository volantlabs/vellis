# component.runtime.message_runtime

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `MessageRuntime`
- Lifecycle: `accepted`
- Purpose: Own exact-address routing, durable traffic chronology, occurrence identity, trace disposition, and safe system reconstruction.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `registerOccurrence` | `RegisterComponentOccurrence` | in `declaration: ComponentOccurrenceDeclaration`; out `resolvedRegistration: ComponentOccurrenceRegistration` | `RuntimeRegistrationInvalid`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Resolve exactly one declaration before traffic; allocate its first incarnation UUID or reuse its durable matching resolution after restart. |
| `prepareStaticTopology` | `PrepareStaticRuntimeTopology` | in `manifest: RuntimeTopologyManifest` | `RuntimeRegistrationInvalid`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Durably fix the complete normalized static occurrence plan before inserting any occurrence; an interrupted first start may resume only that exact plan. |
| `confirmStaticTopology` | `ConfirmStaticRuntimeTopology` | in `manifest: RuntimeTopologyManifest`; out `confirmation: RuntimeTopologyConfirmation` | `RuntimeRegistrationInvalid`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Confirm every prepared occurrence, attached binding/action, configuration reference, replay authority, and curated operation in the complete manifest before traffic is exposed. |
| `send` | `SendRuntimeMessage` | in `message: RuntimeMessageEnvelope`; out `receipt: RuntimeMessageReceipt` | `RuntimeAddressUnknown`, `RuntimeActionUnknown`, `RuntimeSchemaUnsupported`, `RuntimeMessageConflict`, `RuntimeQueueFull`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Durably accept one signal or request before dispatching it to the exact target occurrence. |
| `request` | `RequestRuntimeMessage` | in `message: RuntimeMessageEnvelope`; in `timeoutSeconds: Real[0..1]`; out `outcome: RuntimeRequestOutcome` | `RuntimeAddressUnknown`, `RuntimeActionUnknown`, `RuntimeSchemaUnsupported`, `RuntimeMessageConflict`, `RuntimeQueueFull`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped`, `RuntimeRequestTimedOut` | Accept and await one request; a wait timeout does not cancel handler execution. |
| `queryHistory` | `QueryRuntimeHistory` | in `query: RuntimeHistoryQuery`; out `page: RuntimeHistoryPage` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Return deterministic cursor-paginated immutable facts without recursively creating business traffic. |
| `getTrace` | `GetRuntimeCausalTrace` | in `traceId: Uuid`; out `trace: RuntimeCausalTrace` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Return every recorded fact in one causal trace and its confirmed terminal disposition. |
| `reconstruct` | `ReconstructRuntimeState` | in `request: RuntimeReconstructionRequest`; out `report: RuntimeReconstructionReport` | `RuntimeReplayIncompatible`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Prepare the target, select committed canonical effects in position order, honor an explicitly marked final aggregate effect over derived effects from the same trace, verify final component digests and invariants, and never repeat recorded external effects. All prior deliveries must be terminal; the sole explicitly recovery-authorized root request that invokes reconstruction is the only permitted pending delivery. Verified reconstruction through an explicit cursor earlier than the source head enters branch-pending state rather than reopening ingress. |
| `recordBranchProvenance` | `RecordRuntimeBranchProvenance` | in `sourceRuntimeId: Uuid`; in `sourceCursor: Integer`; in `verifiedDigest: String`; out `runtimePosition: Integer` | `RuntimeReplayIncompatible`, `RuntimeReplayTargetNotPrepared`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Recheck the pending reconstructed state, durably record its exact source runtime, selected cursor, and verified digest, and only then open the new branch to ordinary traffic. |

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
| `runtimeId` | `Uuid` | `owned` | Typed component state. |
| `runtimeKey` | `String` | `owned` | Typed component state. |
| `occurrenceRegistry` | `JsonObject` | `owned` | Typed component state. |
| `staticTopologyPlan` | `JsonObject` | `owned` | Typed component state. |
| `health` | `String` | `owned` | Typed component state. |
| `currentPosition` | `Integer` | `derived` | Typed component state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `registerOccurrence` | `occurrenceRegistry` | `write` | Persist one unique key-to-incarnation mapping and binding identity. |
| `prepareStaticTopology` | `staticTopologyPlan` | `write` | Atomically persist the full declaration plan before individual occurrence insertion. |
| `confirmStaticTopology` | `staticTopologyPlan` | `read` | Require the exact prepared plan. |
| `confirmStaticTopology` | `occurrenceRegistry` | `read` | Compare the complete manifest inventory to durable occurrence identities, attached actions, and binding versions. |
| `send` | `currentPosition` | `write` | Append acceptance before target dispatch and preserve duplicate-message identity. |
| `request` | `currentPosition` | `write` | Append acceptance, delivery, response or fault, and terminal trace disposition. |
| `queryHistory` | `currentPosition` | `read` | Read immutable ledger facts without changing canonical business history. |
| `getTrace` | `currentPosition` | `read` | Read the complete ordered causal trace without changing canonical history. |
| `reconstruct` | `currentPosition` | `read` | Select committed canonical effects and verify reconstruction without re-delivering coordinator commands. |
| `recordBranchProvenance` | `currentPosition` | `write` | Append exactly one matching provenance fact before reopening a verified historical branch. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.runtime.message_runtime.delivery` | `MessageRuntime` | `runtime` | A message is never dispatched before durable acceptance; initial append failure has no component effect. |
| `contract.runtime.message_runtime.identity` | `MessageRuntime` | `runtime` | The runtime allocates the first incarnation UUID for each manifest key, reuses that resolution across restart, and rejects duplicate live keys or UUIDs; callers never assign first-incarnation identity. |
| `contract.runtime.message_runtime.static_topology_atomicity` | `MessageRuntime` | `runtime` | Static application composition durably prepares the complete normalized occurrence plan before inserting any occurrence. Once prepared or confirmed, registration accepts only exact declared keys and contracts; a rejected changed manifest inserts nothing, and interruption may resume only the same plan. |
| `contract.runtime.message_runtime.ordering` | `MessageRuntime` | `runtime` | Each occurrence has a bounded FIFO queue and one in-flight delivery unless its accepted binding declares safe higher concurrency; no global execution order is promised. A root trace receives a terminal disposition only after its root and every accepted causal descendant has a recorded response or fault. |
| `contract.runtime.message_runtime.deduplication` | `MessageRuntime` | `runtime` | Identical reuse of a message ID observes its current or prior outcome without re-execution; changed content under the same ID is rejected. |
| `contract.runtime.message_runtime.fail_stop` | `MessageRuntime` | `runtime` | Failure to encode or persist a terminal result after an effect places the runtime in fail-stop state, quiesces accepted traffic, and rejects further traffic. |
| `contract.runtime.message_runtime.causality` | `MessageRuntime` | `runtime` | Every accepted causal message identifies an accepted parent in the same open trace. New causal messages are rejected after the trace terminal fact, while exact duplicate observation remains available without re-execution. |
| `contract.runtime.message_runtime.recovery_ingress` | `MessageRuntime` | `runtime` | Confirmed canonical history awaiting reconstruction, an indeterminate trace, or an indeterminate reconstruction places the runtime in recovery-required state across restart. Ordinary traffic is rejected; only a sole root request whose accepted descriptor explicitly authorizes recovery may enter, and successful verified reconstruction durably reopens traffic. |
| `contract.runtime.message_runtime.replay` | `MessageRuntime` | `runtime` | Reconstruction starts only from proven-empty occurrences or one compatible imported checkpoint after every prior delivery is terminal; a sole explicitly recovery-authorized root request may remain pending only while it invokes reconstruction. Reconstruction applies only committed canonical effects, lets the latest explicitly marked final aggregate effect supersede derived effects in the same trace, excludes aborted and indeterminate traces, never repeats external effects, and reports incompatible history or unavailable external boundaries. Final digest and invariant verification, including nested public component reads, executes as derived playback and appends no canonical business traffic. |
| `contract.runtime.message_runtime.branching` | `MessageRuntime` | `runtime` | Verified reconstruction through an explicit position earlier than the source head durably records that provenance is required and remains branch-pending across restart. Ordinary traffic is rejected until the runtime rechecks every represented occurrence digest and records the exact source runtime, source cursor, and combined verified digest; mismatched or unsolicited provenance never opens ingress. |
| `contract.runtime.message_runtime.register.failures` | `RegisterComponentOccurrence` | `runtime.registerOccurrence` | Rejected registration changes neither durable identity nor the routable occurrence set. |
| `contract.runtime.message_runtime.topology.failures` | `ConfirmStaticRuntimeTopology` | `runtime.confirmStaticTopology` | A missing, extra, or changed occurrence, binding/version, configuration reference, replay authority, curated operation, or manifest schema version rejects application exposure and does not reinterpret durable identity. Every curated operation must resolve to an exact action and schema on an attached target adapter. The full application manifest hash may advance when this topology hash is unchanged, and the newly confirmed manifest hash is recorded. |
| `contract.runtime.message_runtime.topology_prepare.failures` | `PrepareStaticRuntimeTopology` | `runtime.prepareStaticTopology` | An invalid or changed plan is rejected before occurrence insertion; append failure leaves no partially prepared replacement plan. |
| `contract.runtime.message_runtime.send.failures` | `SendRuntimeMessage` | `runtime.send` | Messages with an unresolved or non-local source or target, other invalid envelopes, and messages whose durable append fails are rejected before component dispatch. |
| `contract.runtime.message_runtime.request.failures` | `RequestRuntimeMessage` | `runtime.request` | A caller timeout does not cancel accepted delivery; validation and append failures have no component effect. |
| `contract.runtime.message_runtime.history.failures` | `QueryRuntimeHistory` | `runtime.queryHistory` | History query success and failure never change canonical business history. |
| `contract.runtime.message_runtime.trace.failures` | `GetRuntimeCausalTrace` | `runtime.getTrace` | Causal trace reads return immutable facts and never change canonical business history. |
| `contract.runtime.message_runtime.reconstruct.failures` | `ReconstructRuntimeState` | `runtime.reconstruct` | Non-empty targets without explicit reset authority, incompatible checkpoints or effects, failed initial digest checks, and unresolved external modes are rejected before an unsafe effect; effects are never applied through an unverified codec or binding. |
| `contract.runtime.message_runtime.branch.failures` | `RecordRuntimeBranchProvenance` | `runtime.recordBranchProvenance` | Provenance without a pending verified historical reconstruction, mismatched identity/cursor/digest, changed or unavailable state, and persistence failure never open ordinary ingress. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RuntimeAddress` | `attribute` | `runtimeId: Uuid`, `instanceId: Uuid` | Durable exact address. Human-readable keys are resolved before an envelope is accepted. |
| `RuntimePayload` | `attribute` | `contentType: String` = `"application/json"`, `codecId: String`, `codecVersion: Integer`, `value: JsonValue` | Canonical versioned, serializable payload; live handles and credentials are never embedded. |
| `RuntimeMessageEnvelope` | `item` | `messageId: Uuid`, `kind: RuntimeMessageKind`, `source: RuntimeAddress`, `target: RuntimeAddress`, `componentContractId: String`, `actionId: String`, `schemaVersion: Integer`, `traceId: Uuid`, `correlationId[0..1]: Uuid`, `causationId[0..1]: Uuid`, `idempotencyKey[0..1]: String`, `createdAt: String`, `payload: RuntimePayload` | Immutable request, response, fault, or signal identity and canonical payload. |
| `ComponentOccurrenceDeclaration` | `attribute` | `instanceKey: String`, `componentContractId: String`, `bindingId: String`, `bindingVersion: Integer`, `queueCapacity: Integer` = `128`, `maxInFlight: Integer` = `1`, `replayAuthority: RuntimeReplayMode` = `RuntimeReplayMode::no_state_effect`, `configurationReferences[0..*]: String` | Defined by its typed fields and action requirements. |
| `ComponentOccurrenceRegistration` | `attribute` | `instanceKey: String`, `instanceId: Uuid`, `componentContractId: String`, `bindingId: String`, `bindingVersion: Integer`, `queueCapacity: Integer`, `maxInFlight: Integer`, `replayAuthority: RuntimeReplayMode`, `configurationReferences[0..*]: String` | Durable runtime resolution of one declared occurrence; the runtime allocates the first incarnation UUID. |
| `RuntimeCuratedOperationDeclaration` | `attribute` | `operationId: String`, `targetInstanceKey: String`, `componentContractId: String`, `actionId: String`, `schemaVersion: Integer` | Defined by its typed fields and action requirements. |
| `RuntimeTopologyManifest` | `attribute` | `manifestSchemaVersion: Integer`, `runtimeKey: String`, `occurrences[1..*]: ComponentOccurrenceDeclaration`, `curatedOperations[0..*]: RuntimeCuratedOperationDeclaration`, `manifestHash: String` | Complete static occurrence, binding, configuration-reference, replay-authority, and curated-operation inventory. |
| `RuntimeTopologyConfirmation` | `attribute` | `manifestHash: String`, `topologyHash: String`, `occurrenceCount: Integer` | Defined by its typed fields and action requirements. |
| `RuntimeMessageReceipt` | `attribute` | `messageId: Uuid`, `traceId: Uuid`, `acceptedPosition: Integer`, `status: RuntimeDeliveryStatus` | Defined by its typed fields and action requirements. |
| `RuntimeRequestOutcome` | `attribute` | `request: RuntimeMessageReceipt`, `response: RuntimeMessageEnvelope`, `terminalPosition: Integer`, `traceDisposition: RuntimeTraceDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeHistoryQuery` | `attribute` | `afterPosition[0..1]: Integer`, `throughPosition[0..1]: Integer`, `afterTime[0..1]: String`, `throughTime[0..1]: String`, `runtimeId[0..1]: Uuid`, `instanceKey[0..1]: String`, `instanceId[0..1]: Uuid`, `componentContractId[0..1]: String`, `messageId[0..1]: Uuid`, `traceId[0..1]: Uuid`, `correlationId[0..1]: Uuid`, `causationId[0..1]: Uuid`, `actionId[0..1]: String`, `messageKind[0..1]: RuntimeMessageKind`, `schemaVersion[0..1]: Integer`, `deliveryStatus[0..1]: RuntimeDeliveryStatus`, `traceDisposition[0..1]: RuntimeTraceDisposition`, `factType[0..1]: String`, `limit: Integer` = `100` | Defined by its typed fields and action requirements. |
| `RuntimeLedgerFact` | `attribute` | `runtimePosition: Integer`, `factType: String`, `recordedAt: String`, `runtimeId: Uuid`, `instanceKey[0..1]: String`, `instanceId[0..1]: Uuid`, `componentContractId[0..1]: String`, `messageId[0..1]: Uuid`, `traceId[0..1]: Uuid`, `correlationId[0..1]: Uuid`, `causationId[0..1]: Uuid`, `actionId[0..1]: String`, `schemaVersion[0..1]: Integer`, `envelope[0..1]: RuntimeMessageEnvelope`, `details: JsonObject` | Defined by its typed fields and action requirements. |
| `RuntimeHistoryPage` | `attribute` | `facts[0..*]: RuntimeLedgerFact`, `nextPosition[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RuntimeCausalTrace` | `attribute` | `traceId: Uuid`, `facts[0..*]: RuntimeLedgerFact`, `disposition[0..1]: RuntimeTraceDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeExternalBoundaryDisposition` | `attribute` | `boundaryId: String`, `mode: RuntimeExternalBoundaryMode`, `limitation[0..1]: String` | Defined by its typed fields and action requirements. |
| `RuntimeReconstructionRequest` | `attribute` | `throughPosition[0..1]: Integer`, `sourceRuntimeId[0..1]: Uuid`, `checkpointReference[0..1]: String`, `checkpointReferences: JsonObject`, `resetTargets: Boolean` = `false`, `externalBoundaries[0..*]: RuntimeExternalBoundaryDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeReconstructionReport` | `attribute` | `startPosition: Integer`, `throughPosition: Integer`, `appliedEffects: Integer`, `skippedEffects: Integer`, `incompatibleEffects: Integer`, `stateDigests: JsonObject`, `verified: Boolean`, `externalEffectsSkipped: Integer`, `externalBoundaries[0..*]: RuntimeExternalBoundaryDisposition`, `limitations[0..*]: String`, `verifiedDigest[0..1]: String` | verifiedDigest is the canonical digest of the complete per-occurrence state-digest map and is present only after verified reconstruction. |
| `RuntimeRegistrationInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeAddressUnknown` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeActionUnknown` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeSchemaUnsupported` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeMessageConflict` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeQueueFull` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeLedgerUnavailable` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeFailStopped` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeRequestTimedOut` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeReplayIncompatible` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeReplayTargetNotPrepared` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RuntimeMessageKind` | `request`, `response`, `fault`, `signal` |
| `RuntimeTraceDisposition` | `committed`, `aborted`, `indeterminate` |
| `RuntimeDeliveryStatus` | `accepted`, `rejected`, `delivering`, `completed`, `faulted`, `timed_out` |
| `RuntimeReplayMode` | `no_state_effect`, `canonical_effect`, `coordinator_trace`, `external_exchange` |
| `RuntimeExternalBoundaryMode` | `playback_only`, `live`, `simulated`, `unavailable` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `MessageRuntimeBoundaryVerification` | `MessageRuntime` | `durableBeforeDispatch`, `durableIdentity`, `staticTopologyAtomicity`, `boundedOccurrenceOrdering`, `messageDeduplication`, `terminalPersistenceFailStop`, `terminalCausality`, `recoveryIngress`, `canonicalEffectReplay`, `verifiedHistoricalBranching` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#MessageRuntimeBoundaryVerification` |
| `RegisterComponentOccurrenceContractVerification` | `RegisterComponentOccurrence` | `registerFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RegisterComponentOccurrenceContractVerification` |
| `PrepareStaticRuntimeTopologyContractVerification` | `PrepareStaticRuntimeTopology` | `topologyPreparationFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#PrepareStaticRuntimeTopologyContractVerification` |
| `ConfirmStaticRuntimeTopologyContractVerification` | `ConfirmStaticRuntimeTopology` | `topologyFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#ConfirmStaticRuntimeTopologyContractVerification` |
| `SendRuntimeMessageContractVerification` | `SendRuntimeMessage` | `sendFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#SendRuntimeMessageContractVerification` |
| `RequestRuntimeMessageContractVerification` | `RequestRuntimeMessage` | `requestFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RequestRuntimeMessageContractVerification` |
| `QueryRuntimeHistoryContractVerification` | `QueryRuntimeHistory` | `historyFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#QueryRuntimeHistoryContractVerification` |
| `GetRuntimeCausalTraceContractVerification` | `GetRuntimeCausalTrace` | `traceFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeCausalTraceContractVerification` |
| `ReconstructRuntimeStateContractVerification` | `ReconstructRuntimeState` | `reconstructFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#ReconstructRuntimeStateContractVerification` |
| `RecordRuntimeBranchProvenanceContractVerification` | `RecordRuntimeBranchProvenance` | `branchFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RecordRuntimeBranchProvenanceContractVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
