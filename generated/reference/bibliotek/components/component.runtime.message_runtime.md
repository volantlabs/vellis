# component.runtime.message_runtime

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `MessageRuntime`
- Lifecycle: `accepted`
- Purpose: Durable local message boundary. It knows participant addresses, binding metadata, lanes, envelopes, and chronology, but no component purpose or business role. Its participant surface is message send/delivery/completion; trusted history and reconstruction actions form a separate operator surface.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `prepareStaticTopology` | `PrepareStaticRuntimeTopology` | in `manifest: RuntimeTopologyManifest` | `RuntimeRegistrationInvalid`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Durably fix the complete static occurrence plan before inserting an occurrence. |
| `registerOccurrence` | `RegisterComponentOccurrence` | in `declaration: ComponentOccurrenceDeclaration`; out `resolvedRegistration: ComponentOccurrenceRegistration` | `RuntimeRegistrationInvalid`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Allocate the first durable incarnation or reuse its exact matching identity after restart. |
| `attachParticipant` | `AttachRuntimeParticipant` | in `registration: ComponentOccurrenceRegistration`; in `participant: RuntimeParticipant`; in `actions: RuntimeActionBindingDescriptor[0..*]` | `RuntimeRegistrationInvalid`, `RuntimeFailStopped` | Attach one conforming participant and its explicit action inventory to one registered occurrence. |
| `confirmStaticTopology` | `ConfirmStaticRuntimeTopology` | in `manifest: RuntimeTopologyManifest`; out `confirmation: RuntimeTopologyConfirmation` | `RuntimeRegistrationInvalid`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Open ingress only after every declared occurrence has a participant and every curated operation resolves exactly. |
| `send` | `SendRuntimeMessage` | in `message: RuntimeMessageEnvelope`; out `receipt: RuntimeMessageReceipt` | `RuntimeAddressUnknown`, `RuntimeActionUnknown`, `RuntimeSchemaUnsupported`, `RuntimeMessageConflict`, `RuntimeQueueFull`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Durably accept and schedule one envelope. Requests, responses, faults, and signals use this same path. |
| `completeDelivery` | `CompleteRuntimeDelivery` | in `requestMessageId: Uuid`; in `result: RuntimePayload`; in `canonicalEffect: JsonObject[0..1]`; out `receipt: RuntimeMessageReceipt` | `RuntimeDeliveryUnknown`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Exactly once, close one delivering request and atomically record and create its correlated response envelope. |
| `faultDelivery` | `FaultRuntimeDelivery` | in `requestMessageId: Uuid`; in `error: RuntimePayload`; in `traceDisposition: RuntimeTraceDisposition`; in `canonicalEffect: JsonObject[0..1]`; out `receipt: RuntimeMessageReceipt` | `RuntimeDeliveryUnknown`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Exactly once, close one delivering request and atomically record and create its correlated fault envelope. |
| `acknowledgeDelivery` | `AcknowledgeRuntimeDelivery` | in `messageId: Uuid`; in `canonicalEffect: JsonObject[0..1]`; out `receipt: RuntimeMessageReceipt` | `RuntimeDeliveryUnknown`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Exactly once, close a delivered signal, response, or fault. |
| `queryHistory` | `QueryRuntimeHistory` | in `query: RuntimeHistoryQuery`; out `page: RuntimeHistoryPage` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Return deterministic cursor-paginated immutable facts without creating business traffic. |
| `countHistory` | `CountRuntimeHistory` | in `query: RuntimeHistoryQuery`; out `count: Integer` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Count matching immutable facts through database aggregation without hydrating facts or payloads. |
| `queryTraceSummaries` | `QueryRuntimeTraceSummaries` | in `afterPosition: Integer[0..1]`; in `limit: Integer` = `100`; in `newestFirst: Boolean` = `false`; in `rootActionIds: String[0..*]`; out `page: RuntimeTraceSummaryPage` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Return bounded terminal root-trace metadata without hydrating causal facts or payloads. |
| `getTrace` | `GetRuntimeCausalTrace` | in `traceId: Uuid`; in `includePayload: Boolean` = `false`; out `trace: RuntimeCausalTrace` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Return the ordered facts and terminal disposition of one causal trace. |
| `getEnvelope` | `GetRuntimeMessageEnvelope` | in `messageId: Uuid`; out `envelope: RuntimeMessageEnvelope[0..1]` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Explicitly hydrate one durable envelope by identity without creating traffic. |
| `lookupOutcome` | `LookupRuntimeMessageOutcome` | in `messageId: Uuid`; out `outcome: RuntimeMessageOutcome[0..1]` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Read the durable request and correlated terminal state for one message without creating traffic or retaining an in-memory result cache. |
| `reconstruct` | `ReconstructRuntimeState` | in `request: RuntimeReconstructionRequest`; out `report: RuntimeReconstructionReport` | `RuntimeReplayIncompatible`, `RuntimeReplayTargetNotPrepared`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Apply only committed canonical effects without creating new business traffic or repeating external exchanges. |
| `recordBranchProvenance` | `RecordRuntimeBranchProvenance` | in `sourceRuntimeId: Uuid`; in `sourceCursor: Integer`; in `verifiedDigest: String`; out `runtimePosition: Integer` | `RuntimeReplayIncompatible`, `RuntimeReplayTargetNotPrepared`, `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Recheck and record source identity, selected cursor, and verified digest before opening a historical branch. |
| `getHealth` | `GetRuntimeHealth` | out `health: RuntimeHealth` | None | Return runtime readiness without creating message traffic. |
| `resolveAddress` | `AddressForRuntimeOccurrence` | in `instanceKey: String`; out `address: RuntimeAddress` | `RuntimeAddressUnknown` | Resolve one declared readable occurrence key to its durable exact address. |
| `getCurrentPosition` | `GetCurrentRuntimePosition` | out `runtimePosition: Integer` | `RuntimeLedgerUnavailable`, `RuntimeFailStopped` | Return the latest confirmed runtime ledger position. |
| `close` | `AcloseMessageRuntime` | — | `RuntimeLedgerUnavailable` | Quiesce deliveries, record orderly shutdown when possible, and close the local execution host. |

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
| `openDeliveries` | `JsonObject` | `owned` | Typed component state. |
| `health` | `RuntimeHealth` | `owned` | Typed component state. |
| `currentPosition` | `Integer` | `derived` | Typed component state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `getHealth` | `health` | `read` | Read readiness without mutation. |
| `resolveAddress` | `occurrenceRegistry` | `read` | Resolve only an existing durable identity. |
| `getCurrentPosition` | `currentPosition` | `read` | Read the latest ledger cursor. |
| `close` | `health` | `write` | Transition the local host to closed. |
| `prepareStaticTopology` | — | `declared` | Persist the static plan. |
| `registerOccurrence` | — | `declared` | Persist one occurrence identity. |
| `attachParticipant` | — | `declared` | Attach one participant and action inventory. |
| `confirmStaticTopology` | — | `declared` | Confirm and expose the complete topology. |
| `completeDelivery` | — | `declared` | Record completion and emit its response. |
| `faultDelivery` | — | `declared` | Record fault and emit its fault envelope. |
| `acknowledgeDelivery` | — | `declared` | Record terminal acknowledgement. |
| `queryHistory` | — | `declared` | Read immutable chronology. |
| `countHistory` | — | `declared` | Aggregate immutable chronology. |
| `queryTraceSummaries` | — | `declared` | Read bounded terminal trace metadata. |
| `getTrace` | — | `declared` | Read one causal trace. |
| `getEnvelope` | — | `declared` | Explicitly hydrate one durable envelope. |
| `lookupOutcome` | — | `declared` | Read one durable message outcome. |
| `reconstruct` | — | `declared` | Apply selected canonical effects. |
| `recordBranchProvenance` | — | `declared` | Record verified branch provenance. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.runtime.message_runtime.uniform_delivery` | `MessageRuntime` | `runtime` | Every envelope kind is durably accepted before delivery. Responses and faults are scheduled to the requester's independently available response lane; there is no runtime request future or special response return path. |
| `contract.runtime.message_runtime.completion` | `MessageRuntime` | `runtime` | A request remains open until exactly one complete or fault operation records its terminal fact and correlated envelope. Signals, responses, and faults remain open until exactly one acknowledgement. Unknown, wrong-kind, or duplicate closure is rejected. |
| `contract.runtime.message_runtime.causality` | `MessageRuntime` | `runtime` | A trace becomes terminal only after its root and every accepted causal descendant are terminal. Correlation and causation reference accepted messages in that same trace. |
| `contract.runtime.message_runtime.lanes` | `MessageRuntime` | `runtime` | Each declared action lane is bounded FIFO with its own worker limit. No cross-lane or global execution order is promised. The response lane is capacity-exempt and remains deliverable while request workers await collaborators. |
| `contract.runtime.message_runtime.consistency` | `MessageRuntime` | `runtime` | Independent actions are ungated. Shared actions in a consistency group may overlap. Exclusive actions use writer-preferring admission, wait for active shared actions, block new shared actions, and remain exclusive through request completion. Admission never reorders a lane. |
| `contract.runtime.message_runtime.identity` | `MessageRuntime` | `runtime` | Runtime and occurrence identities survive restart. Duplicate live keys or UUIDs fail composition. Addresses always include runtime and occurrence UUIDs. |
| `contract.runtime.message_runtime.topology` | `MessageRuntime` | `runtime` | The complete manifest is prepared before occurrence insertion. Traffic opens only when every occurrence has exactly one attached participant and curated operations resolve to declared actions. Changed topology requires an explicit migration. |
| `contract.runtime.message_runtime.deduplication` | `MessageRuntime` | `runtime` | Identical reuse of a message ID observes current or recorded state without re-execution. Reuse with different immutable content is rejected. Delivery attempt identity remains distinct from message identity. |
| `contract.runtime.message_runtime.payload_boundary` | `MessageRuntime` | `runtime` | Complete component state crosses a message boundary only through an explicitly modeled state-transfer or external-document action. Ordinary requests, results, faults, and canonical effects contain commands, targeted reads, deltas, summaries, bounded diagnostics, digests, or opaque durable references. Credentials, live handles, connections, and filesystem capabilities are never durable payload values. |
| `contract.runtime.message_runtime.timeout` | `MessageRuntime` | `runtime` | A caller or adapter wait timeout does not cancel a handler or imply delivery failure. Late terminal envelopes are still delivered and acknowledged. |
| `contract.runtime.message_runtime.lifecycle` | `MessageRuntime` | `runtime` | Runtime health is a typed lifecycle. Ready accepts ordinary roots; quiescing accepts only descendants of already-open traces; recovery-required admits one recovery-authorized root and its descendants; reconstructing, branch-pending, fail-stopped, closing, and closed reject ordinary ingress. Every persisted transition is recorded in runtime chronology. |
| `contract.runtime.message_runtime.fail_stop` | `MessageRuntime` | `runtime` | Initial append failure prevents dispatch. Terminal persistence failure after possible component effect enters fail-stop, quiesces lanes, marks open deliveries indeterminate where durable recording remains possible, and rejects new traffic. |
| `contract.runtime.message_runtime.recovery` | `MessageRuntime` | `runtime` | Restart marks open deliveries indeterminate. Reconstruction applies only canonical effects whose effect and committed trace-terminal facts are both at or before the selected cursor. A superseding aggregate contains ordered immutable references only; every reference resolves to a same-trace causal descendant with the recorded effect digest, and embedded child payloads are rejected. A checkpoint set names every state owner and represents one common cursor. External exchanges are reported but never invoked. Failed reset, import, replay, digest, or verification leaves recovery required; replay evaluation is not appended as business traffic. |
| `contract.runtime.message_runtime.operator_separation` | `MessageRuntime` | `runtime` | History, trace, health, reconstruction, and branch operations are trusted runtime boundary operations and are never used as component-to-component integration calls or exposed as universal production tools. |
| `contract.runtime.message_runtime.failures` | `MessageRuntime` | `runtime` | Invalid topology, address, action, schema, lane capacity, causality, completion, or envelope content causes no component effect. Runtime failures remain distinct from modeled component faults. |
| `contract.runtime.message_runtime.prepare.failures` | `PrepareStaticRuntimeTopology` | `runtime.prepareStaticTopology` | Rejection changes neither the prepared plan nor durable occurrences. |
| `contract.runtime.message_runtime.register.failures` | `RegisterComponentOccurrence` | `runtime.registerOccurrence` | Rejection allocates no occurrence identity and changes no registration. |
| `contract.runtime.message_runtime.attach.failures` | `AttachRuntimeParticipant` | `runtime.attachParticipant` | Rejection leaves the occurrence unattached and unroutable. |
| `contract.runtime.message_runtime.confirm.failures` | `ConfirmStaticRuntimeTopology` | `runtime.confirmStaticTopology` | Incomplete or inconsistent topology remains closed to traffic. |
| `contract.runtime.message_runtime.send.failures` | `SendRuntimeMessage` | `runtime.send` | Rejection occurs before participant delivery and component effect. |
| `contract.runtime.message_runtime.complete.failures` | `CompleteRuntimeDelivery` | `runtime.completeDelivery` | Unknown or duplicate completion creates no response and does not alter the prior terminal fact. |
| `contract.runtime.message_runtime.fault.failures` | `FaultRuntimeDelivery` | `runtime.faultDelivery` | Unknown or duplicate fault creates no fault envelope and does not alter the prior terminal fact. |
| `contract.runtime.message_runtime.ack.failures` | `AcknowledgeRuntimeDelivery` | `runtime.acknowledgeDelivery` | Unknown or duplicate acknowledgement does not alter the prior terminal fact. |
| `contract.runtime.message_runtime.history.failures` | `QueryRuntimeHistory` | `runtime.queryHistory` | Query failure changes neither ledger nor component state. |
| `contract.runtime.message_runtime.count_history.failures` | `CountRuntimeHistory` | `runtime.countHistory` | Count failure changes neither ledger nor component state. |
| `contract.runtime.message_runtime.trace_summaries.failures` | `QueryRuntimeTraceSummaries` | `runtime.queryTraceSummaries` | Summary-query failure changes neither ledger nor component state. |
| `contract.runtime.message_runtime.trace.failures` | `GetRuntimeCausalTrace` | `runtime.getTrace` | Trace-read failure changes neither ledger nor component state. |
| `contract.runtime.message_runtime.envelope.failures` | `GetRuntimeMessageEnvelope` | `runtime.getEnvelope` | Unknown identity returns absence; hydration changes neither ledger nor component state. |
| `contract.runtime.message_runtime.outcome.failures` | `LookupRuntimeMessageOutcome` | `runtime.lookupOutcome` | Unknown identity returns absence. Outcome inspection changes neither ledger nor component state. |
| `contract.runtime.message_runtime.reconstruct.failures` | `ReconstructRuntimeState` | `runtime.reconstruct` | Incompatibility is reported and the runtime does not expose an unverified target as ready. |
| `contract.runtime.message_runtime.branch.failures` | `RecordRuntimeBranchProvenance` | `runtime.recordBranchProvenance` | Mismatched or unsolicited provenance never opens ordinary ingress. |
| `contract.runtime.message_runtime.health.failures` | `GetRuntimeHealth` | `runtime.getHealth` | Health inspection has no state effect. |
| `contract.runtime.message_runtime.address.failures` | `AddressForRuntimeOccurrence` | `runtime.resolveAddress` | Unknown key resolution allocates no identity and changes no routing. |
| `contract.runtime.message_runtime.position.failures` | `GetCurrentRuntimePosition` | `runtime.getCurrentPosition` | Position inspection has no state effect. |
| `contract.runtime.message_runtime.close.failures` | `AcloseMessageRuntime` | `runtime.close` | Close failure never reports a partially active runtime as ready. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RuntimeHistoryQuery` | `attribute` | `afterPosition[0..1]: Integer`, `throughPosition[0..1]: Integer`, `afterTime[0..1]: String`, `throughTime[0..1]: String`, `runtimeId[0..1]: Uuid`, `instanceKey[0..1]: String`, `instanceId[0..1]: Uuid`, `componentContractId[0..1]: String`, `messageId[0..1]: Uuid`, `traceId[0..1]: Uuid`, `correlationId[0..1]: Uuid`, `causationId[0..1]: Uuid`, `actionId[0..1]: String`, `messageKind[0..1]: RuntimeMessageKind`, `schemaVersion[0..1]: Integer`, `deliveryStatus[0..1]: RuntimeDeliveryStatus`, `traceDisposition[0..1]: RuntimeTraceDisposition`, `factType[0..1]: String`, `limit: Integer` = `100`, `includePayload: Boolean` = `false` | Defined by its typed fields and action requirements. |
| `RuntimeLedgerFact` | `attribute` | `runtimePosition: Integer`, `factType: String`, `recordedAt: String`, `runtimeId: Uuid`, `instanceKey[0..1]: String`, `instanceId[0..1]: Uuid`, `componentContractId[0..1]: String`, `messageId[0..1]: Uuid`, `traceId[0..1]: Uuid`, `correlationId[0..1]: Uuid`, `causationId[0..1]: Uuid`, `actionId[0..1]: String`, `schemaVersion[0..1]: Integer`, `envelope[0..1]: RuntimeMessageEnvelope`, `details: JsonObject` | Defined by its typed fields and action requirements. |
| `RuntimeHistoryPage` | `attribute` | `facts[0..*]: RuntimeLedgerFact`, `nextPosition[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RuntimeCausalTrace` | `attribute` | `traceId: Uuid`, `facts[0..*]: RuntimeLedgerFact`, `disposition[0..1]: RuntimeTraceDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeTraceSummary` | `attribute` | `traceId: Uuid`, `rootMessageId: Uuid`, `rootActionId: String`, `terminalPosition: Integer`, `disposition: RuntimeTraceDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeTraceSummaryPage` | `attribute` | `summaries[0..*]: RuntimeTraceSummary`, `nextPosition[0..1]: Integer` | Defined by its typed fields and action requirements. |
| `RuntimeExternalBoundaryDisposition` | `attribute` | `boundaryId: String`, `mode: RuntimeExternalBoundaryMode`, `limitation[0..1]: String` | Defined by its typed fields and action requirements. |
| `RuntimeReconstructionRequest` | `attribute` | `throughPosition[0..1]: Integer`, `sourceRuntimeId[0..1]: Uuid`, `checkpointReference[0..1]: String`, `checkpointReferences[0..1]: JsonObject`, `resetTargets: Boolean` = `false`, `externalBoundaries[0..*]: RuntimeExternalBoundaryDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeReconstructionReport` | `attribute` | `startPosition: Integer`, `throughPosition: Integer`, `appliedEffects: Integer`, `skippedEffects: Integer`, `incompatibleEffects: Integer`, `stateDigests: JsonObject`, `verified: Boolean`, `externalEffectsSkipped: Integer`, `externalBoundaries[0..*]: RuntimeExternalBoundaryDisposition`, `limitations[0..*]: String`, `verifiedDigest[0..1]: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `MessageRuntimeBoundaryVerification` | `MessageRuntime` | `uniformDurableDelivery`, `singleCompletionPath`, `terminalCausality`, `laneScheduling`, `declarativeConsistency`, `durableIdentity`, `staticTopologyAtomicity`, `messageDeduplication`, `explicitStateTransferBoundary`, `nonCancellingWaitTimeout`, `explicitRuntimeLifecycle`, `persistenceFailStop`, `recoveryAndReplay`, `operatorSurfaceSeparation` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#MessageRuntimeBoundaryVerification` |
| `RuntimeParticipantClosureVerification` | `MessageRuntime` | `singleCompletionPath`, `runtimeFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RuntimeParticipantClosureVerification` |
| `RuntimeTopologyVerification` | `MessageRuntime` | `durableIdentity`, `staticTopologyAtomicity` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RuntimeTopologyVerification` |
| `RuntimeReconstructionVerification` | `MessageRuntime` | `recoveryAndReplay` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RuntimeReconstructionVerification` |
| `PrepareStaticRuntimeTopologyContractVerification` | `PrepareStaticRuntimeTopology` | `prepareTopologyFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#PrepareStaticRuntimeTopologyContractVerification` |
| `RegisterComponentOccurrenceContractVerification` | `RegisterComponentOccurrence` | `registerOccurrenceFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RegisterComponentOccurrenceContractVerification` |
| `AttachRuntimeParticipantContractVerification` | `AttachRuntimeParticipant` | `attachParticipantFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#AttachRuntimeParticipantContractVerification` |
| `ConfirmStaticRuntimeTopologyContractVerification` | `ConfirmStaticRuntimeTopology` | `confirmTopologyFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#ConfirmStaticRuntimeTopologyContractVerification` |
| `SendRuntimeMessageContractVerification` | `SendRuntimeMessage` | `sendMessageFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#SendRuntimeMessageContractVerification` |
| `CompleteRuntimeDeliveryContractVerification` | `CompleteRuntimeDelivery` | `completeDeliveryFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#CompleteRuntimeDeliveryContractVerification` |
| `FaultRuntimeDeliveryContractVerification` | `FaultRuntimeDelivery` | `faultDeliveryFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#FaultRuntimeDeliveryContractVerification` |
| `AcknowledgeRuntimeDeliveryContractVerification` | `AcknowledgeRuntimeDelivery` | `acknowledgeDeliveryFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#AcknowledgeRuntimeDeliveryContractVerification` |
| `QueryRuntimeHistoryContractVerification` | `QueryRuntimeHistory` | `queryHistoryFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#QueryRuntimeHistoryContractVerification` |
| `CountRuntimeHistoryContractVerification` | `CountRuntimeHistory` | `countHistoryFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#CountRuntimeHistoryContractVerification` |
| `QueryRuntimeTraceSummariesContractVerification` | `QueryRuntimeTraceSummaries` | `traceSummaryFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#QueryRuntimeTraceSummariesContractVerification` |
| `GetRuntimeCausalTraceContractVerification` | `GetRuntimeCausalTrace` | `getTraceFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeCausalTraceContractVerification` |
| `GetRuntimeMessageEnvelopeContractVerification` | `GetRuntimeMessageEnvelope` | `getEnvelopeFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeMessageEnvelopeContractVerification` |
| `LookupRuntimeMessageOutcomeContractVerification` | `LookupRuntimeMessageOutcome` | `lookupOutcomeFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#LookupRuntimeMessageOutcomeContractVerification` |
| `ReconstructRuntimeStateContractVerification` | `ReconstructRuntimeState` | `reconstructStateFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#ReconstructRuntimeStateContractVerification` |
| `RecordRuntimeBranchProvenanceContractVerification` | `RecordRuntimeBranchProvenance` | `branchProvenanceFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#RecordRuntimeBranchProvenanceContractVerification` |
| `GetRuntimeHealthContractVerification` | `GetRuntimeHealth` | `getHealthFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeHealthContractVerification` |
| `AddressForRuntimeOccurrenceContractVerification` | `AddressForRuntimeOccurrence` | `addressForFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#AddressForRuntimeOccurrenceContractVerification` |
| `GetCurrentRuntimePositionContractVerification` | `GetCurrentRuntimePosition` | `currentPositionFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetCurrentRuntimePositionContractVerification` |
| `AcloseMessageRuntimeContractVerification` | `AcloseMessageRuntime` | `closeRuntimeFailureSemantics` | `components/runtime/message_runtime/tests/test_message_runtime_contract.py#AcloseMessageRuntimeContractVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
