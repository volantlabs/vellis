# component.runtime.component_adapter

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `ComponentRuntimeAdapter`
- Lifecycle: `accepted`
- Purpose: Standard composable realization of the minimal runtime participant protocol. It adapts any ordinary component occurrence through explicit handlers, codecs, continuations, effects, and replay functions. It is not a framework superclass and alternative conforming participants remain valid.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `describe` | `DescribeRuntimeBinding` | out `description: RuntimeBindingDescription` | None | Return the explicit action inventory. Private methods and component-purpose labels are absent. |
| `deliver` | `DeliverRuntimeEnvelope` | in `envelope: RuntimeMessageEnvelope` | `RuntimeBindingInvalid`, `RuntimePayloadInvalid`, `RuntimeTerminalEncodingFailed` | Accept one runtime delivery. A request handler terminates only through runtime complete or fault; a signal, response, or fault terminates only through acknowledgement. |
| `applyReplayEffect` | `ApplyCanonicalReplayEffect` | in `effect: JsonObject` | `RuntimeBindingInvalid`, `RuntimePayloadInvalid`, `RuntimeReplayIncompatible` | Apply one compatible committed effect without creating new business traffic or repeating an external effect. |
| `replayStateStatus` | `ReplayStateStatus` | out `status: RuntimeReplayStateStatus` | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Report whether the occurrence owns replay state and whether that state is empty or checkpoint-prepared. |
| `resetReplayState` | `ResetReplayState` | — | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Replace supported replay-owned state with the component-defined empty state. |
| `importReplayCheckpoint` | `ImportReplayCheckpoint` | in `reference: String`; out `throughPosition: Integer` | `RuntimeBindingInvalid`, `RuntimePayloadInvalid`, `RuntimeReplayIncompatible` | Atomically import a compatible checkpoint and return the represented runtime position. |
| `replayStateDigest` | `ReplayStateDigest` | out `digest: String` | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Compute a deterministic digest of the replay-owned state without changing it. |
| `verifyReplayState` | `VerifyReplayState` | out `limitations: String[0..*]` | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Verify public state invariants; an empty limitations list means verified. |

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
| `occurrenceAddress` | `RuntimeAddress` | `owned` | Typed component state. |
| `bindingDescription` | `RuntimeBindingDescription` | `owned` | Typed component state. |
| `continuations` | `JsonObject` | `owned` | Typed component state. |
| `outstandingExecutionLimit` | `Integer` | `owned` | Typed component state. |

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `describe` | — | `declared` | Read the immutable binding inventory. |
| `deliver` | — | `declared` | Decode, execute, continue, or acknowledge one envelope. |
| `applyReplayEffect` | — | `declared` | Apply one explicitly registered effect. |
| `replayStateStatus` | — | `declared` | Inspect replay readiness. |
| `resetReplayState` | — | `declared` | Reset replay-owned state. |
| `importReplayCheckpoint` | — | `declared` | Import one compatible checkpoint. |
| `replayStateDigest` | — | `declared` | Read a deterministic state digest. |
| `verifyReplayState` | — | `declared` | Verify replay-owned state invariants. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.runtime.component_adapter.one_archetype` | `ComponentRuntimeAdapter` | `adapter` | The same participant and adapter contracts host local, coordinating, state-owning, stateless, external-interface, and mixed action behavior. Store, controller, coordinator, façade, gateway, actor, and saga labels create neither adapter subtypes nor runtime registration categories. |
| `contract.runtime.component_adapter.minimal_participant` | `ComponentRuntimeAdapter` | `adapter` | The runtime-facing obligation is only asynchronous envelope delivery with its scoped participant context. Bibliotek's adapter is one conforming implementation; an equivalent hand-authored participant can replace it without changing runtime routing. |
| `contract.runtime.component_adapter.uniform_handler` | `ComponentRuntimeAdapter` | `adapter` | Every action handler receives decoded arguments and one execution context. It may perform local work, send or await messages, compensate, and aggregate. It does not return a second runtime result path and must explicitly complete or fault its inbound request. |
| `contract.runtime.component_adapter.explicit_mapping` | `ComponentRuntimeAdapter` | `adapter` | Every routable action explicitly declares schemas, codecs, arguments and defaults, failures, lane, consistency group and access, idempotency, deadline, replay mode, canonical effect, and external-effect status. The descriptor contains no component-role or handler-kind field and reflection exposes no unregistered method. |
| `contract.runtime.component_adapter.continuations` | `ComponentRuntimeAdapter` | `adapter` | A coordinating handler calls collaborators by sending a request with a deterministic step message ID and waiting on a loop-neutral bounded continuation keyed by correlation. Reusing one step key with identical immutable content observes the same continuation; changed content is rejected. Response and fault delivery resolves and removes the continuation and is always acknowledged, including after caller timeout. Durable outcome lookup replaces terminal in-memory caches. |
| `contract.runtime.component_adapter.execution_lifetime` | `ComponentRuntimeAdapter` | `adapter` | The adapter bounds outstanding outbound continuations and cooperates with runtime-hosted action deadlines. Caller wait timeout never cancels component execution. Cancellation of an off-loop synchronous invocation waits for that invocation to settle. A coordinating handler may compensate before faulting; otherwise deadline expiry renders the execution indeterminate. |
| `contract.runtime.component_adapter.equivalence` | `ComponentRuntimeAdapter` | `adapter` | Generated local handlers preserve the logical component's defaults, ordering, results, failures, and state effects. Runtime messaging remains visible to coordinating handlers through action references, argument mappings, target addresses, and deterministic step keys rather than proxy objects. |
| `contract.runtime.component_adapter.replay` | `ComponentRuntimeAdapter` | `adapter` | Optional canonical-effect application, empty/reset/checkpoint, deterministic digest, and invariant-verification functions compose into the same adapter. Their absence means the occurrence owns no replayed state, not that it belongs to a different participant type. |
| `contract.runtime.component_adapter.failures` | `ComponentRuntimeAdapter` | `adapter` | Invalid action, payload, codec, effect, or terminal encoding is rejected without unmodeled component mutation. Modeled component faults retain their declared evidence and disposition; unexpected faults remain distinct and indeterminate. |
| `contract.runtime.component_adapter.describe.failures` | `DescribeRuntimeBinding` | `adapter.describe` | Description changes neither adapted component nor continuation state. |
| `contract.runtime.component_adapter.deliver.failures` | `DeliverRuntimeEnvelope` | `adapter.deliver` | Invalid binding or payload is rejected before component invocation; a started request is never silently left complete. |
| `contract.runtime.component_adapter.effect.failures` | `ApplyCanonicalReplayEffect` | `adapter.applyReplayEffect` | Incompatible effects are rejected before invoking the state owner. |
| `contract.runtime.component_adapter.status.failures` | `ReplayStateStatus` | `adapter.replayStateStatus` | Status failure never reports an unsafe target as prepared. |
| `contract.runtime.component_adapter.reset.failures` | `ResetReplayState` | `adapter.resetReplayState` | Failed reset never reports partial state as reconstruction-ready. |
| `contract.runtime.component_adapter.checkpoint.failures` | `ImportReplayCheckpoint` | `adapter.importReplayCheckpoint` | Invalid checkpoint never exposes partially imported state as prepared. |
| `contract.runtime.component_adapter.digest.failures` | `ReplayStateDigest` | `adapter.replayStateDigest` | Digest failure has no state effect. |
| `contract.runtime.component_adapter.verify.failures` | `VerifyReplayState` | `adapter.verifyReplayState` | Invariant verification failure has no state effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RuntimeReplayStateStatus` | `attribute` | `available: Boolean`, `empty: Boolean`, `prepared: Boolean`, `checkpointCursor: Integer`, `stateDigest[0..1]: String`, `limitations[0..*]: String` | Defined by its typed fields and action requirements. |
| `RuntimeBindingInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimePayloadInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeTerminalEncodingFailed` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| — | No component-owned public enumerations. |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `ComponentRuntimeAdapterBoundaryVerification` | `ComponentRuntimeAdapter` | `oneComponentArchetype`, `minimalParticipantSubstitution`, `uniformActionHandler`, `explicitMapping`, `messageContinuations`, `boundedExecutionLifetime`, `directMessageEquivalence`, `replayStateComposition` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ComponentRuntimeAdapterBoundaryVerification` |
| `DeliverRuntimeEnvelopeContractVerification` | `DeliverRuntimeEnvelope` | `deliverEnvelopeFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#DeliverRuntimeEnvelopeContractVerification` |
| `ComponentRuntimeReplayVerification` | `ComponentRuntimeAdapter` | `replayStateComposition`, `adapterFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ComponentRuntimeReplayVerification` |
| `DescribeRuntimeBindingContractVerification` | `DescribeRuntimeBinding` | `describeBindingFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#DescribeRuntimeBindingContractVerification` |
| `ApplyCanonicalReplayEffectContractVerification` | `ApplyCanonicalReplayEffect` | `applyReplayEffectFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ApplyCanonicalReplayEffectContractVerification` |
| `ReplayStateStatusContractVerification` | `ReplayStateStatus` | `replayStatusFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateStatusContractVerification` |
| `ResetReplayStateContractVerification` | `ResetReplayState` | `resetReplayStateFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ResetReplayStateContractVerification` |
| `ImportReplayCheckpointContractVerification` | `ImportReplayCheckpoint` | `importCheckpointFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ImportReplayCheckpointContractVerification` |
| `ReplayStateDigestContractVerification` | `ReplayStateDigest` | `replayDigestFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateDigestContractVerification` |
| `VerifyReplayStateContractVerification` | `VerifyReplayState` | `verifyReplayStateFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#VerifyReplayStateContractVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
