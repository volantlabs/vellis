# component.runtime.component_adapter

Generated from textual SysML v2 by `just model-render` as a non-normative reading projection; do not edit by hand.

- Model definition: `ComponentRuntimeAdapter`
- Lifecycle: `accepted`
- Purpose: Explicitly maps one reusable black-box component occurrence to runtime messages while preserving its direct protocol.

## Provided actions

| Feature | Contract | Signature | Principal failures | Meaning |
|---|---|---|---|---|
| `describe` | `DescribeRuntimeBinding` | out `description: RuntimeBindingDescription` | None | Return the explicit routable action inventory; arbitrary object methods are absent. |
| `dispatch` | `DispatchRuntimeMessage` | in `request: RuntimeMessageEnvelope`; out `result: RuntimeDispatchResult` | `RuntimeBindingInvalid`, `RuntimePayloadInvalid`, `RuntimeComponentFault` | Decode one registered request, invoke the corresponding black-box action exactly once, and encode its public result or modeled failure. |
| `applyReplayEffect` | `ApplyCanonicalReplayEffect` | in `effect: JsonObject` | `RuntimeBindingInvalid`, `RuntimePayloadInvalid`, `RuntimeReplayIncompatible` | Apply one compatible committed effect without recording new business traffic or repeating external effects. |
| `replayStateStatus` | `ReplayStateStatus` | out `status: RuntimeReplayStateStatus` | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Report whether the adapted occurrence is empty, checkpoint-prepared, or unavailable for safe reconstruction. |
| `resetReplayState` | `ResetReplayState` | — | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Replace the adapted occurrence state with its contract-defined empty state before reconstruction. |
| `importReplayCheckpoint` | `ImportReplayCheckpoint` | in `reference: String`; out `throughPosition: Integer` | `RuntimeBindingInvalid`, `RuntimePayloadInvalid`, `RuntimeReplayIncompatible` | Atomically import one binding-compatible checkpoint and return the represented runtime position; the runtime verifies its digest before later effects. |
| `replayStateDigest` | `ReplayStateDigest` | out `digest: String` | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Compute one deterministic canonical digest without changing adapted component state. |
| `verifyReplayState` | `VerifyReplayState` | out `limitations: String[0..*]` | `RuntimeBindingInvalid`, `RuntimeReplayIncompatible` | Verify the adapted component's public invariants without changing its state; an empty limitation list means verified. |

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

## Action and state effects

| Action | State / collaborator | Access | Modeled effect |
|---|---|---|---|
| `describe` | `bindingDescription` | `read` | Expose the immutable explicit binding inventory without component effects. |
| `dispatch` | `bindingDescription` | `read` | Route only registered actions and preserve modeled defaults, results, failures, and effects. |
| `applyReplayEffect` | `bindingDescription` | `read` | Validate effect compatibility before delegating replay to the state owner. |
| `replayStateStatus` | `bindingDescription` | `read` | Inspect only the explicitly supported reconstruction status surface without mutation. |
| `resetReplayState` | `bindingDescription` | `read` | Require explicit reset support before replacing adapted state with empty state. |
| `importReplayCheckpoint` | `bindingDescription` | `read` | Require exact checkpoint and binding compatibility before state replacement. |
| `replayStateDigest` | `bindingDescription` | `read` | Select the binding's deterministic canonical digest codec without mutation. |
| `verifyReplayState` | `bindingDescription` | `read` | Invoke only the binding-declared invariant verification surface without mutation. |

## Native action behavior

| Public action | Nested semantic actions | Observable successions |
|---|---|---|
| — | — | No action decomposition required at this boundary. |

## Invariants and behavioral obligations

| Stable ID | Subject | Satisfier | Required constraint |
|---|---|---|---|
| `contract.runtime.component_adapter.explicit_mapping` | `ComponentRuntimeAdapter` | `adapter` | Every routable action declares request/result/failure schema and codec versions, request arguments and defaults, concrete supported failures and modeled-fault disposition, canonical-effect codec, idempotency, concurrency, replay mode, external-effect status, and whether the action alone is authorized while reconstruction is required; reflection never exposes private methods. |
| `contract.runtime.component_adapter.equivalence` | `ComponentRuntimeAdapter` | `adapter` | Direct and message-mediated invocation preserve logical inputs, defaults, public results, concrete failures, ordering, and state effects. |
| `contract.runtime.component_adapter.replay` | `ComponentRuntimeAdapter` | `adapter` | State-owning actions capture nondeterministic resolved values in canonical effects; reads and coordinators do not duplicate derived effects, while a coordinator that owns a confirmed aggregate state may emit an explicit final effect that supersedes its same-trace derived effects. |
| `contract.runtime.component_adapter.reconstruction` | `ComponentRuntimeAdapter` | `adapter` | Reconstruction uses only explicitly supported reset, checkpoint import, deterministic digest, and invariant verification operations; checkpoint import is atomic and must match its expected digest. |
| `contract.runtime.component_adapter.recovery_authorization` | `ComponentRuntimeAdapter` | `adapter` | Recovery authorization defaults false and may be declared only for a non-effectful coordinator action that is intentionally safe as the sole recovery ingress; it never grants arbitrary routing or replay authority. |
| `contract.runtime.component_adapter.describe.failures` | `DescribeRuntimeBinding` | `adapter.describe` | Description has no declared domain failure and changes neither component nor adapter state. |
| `contract.runtime.component_adapter.dispatch.failures` | `DispatchRuntimeMessage` | `adapter.dispatch` | Invalid bindings or payloads are rejected before component invocation; modeled component failures preserve their declared no-effect or documented effect semantics. |
| `contract.runtime.component_adapter.replay.failures` | `ApplyCanonicalReplayEffect` | `adapter.applyReplayEffect` | An incompatible effect is rejected before invoking the state owner. |
| `contract.runtime.component_adapter.replay_state_status.failures` | `ReplayStateStatus` | `adapter.replayStateStatus` | Status inspection success or failure has no adapted component state effect and never reports an unsafe target as prepared. |
| `contract.runtime.component_adapter.reset.failures` | `ResetReplayState` | `adapter.resetReplayState` | Unsupported or failed reset does not expose a partially reset occurrence as reconstruction-ready. |
| `contract.runtime.component_adapter.checkpoint.failures` | `ImportReplayCheckpoint` | `adapter.importReplayCheckpoint` | Incompatible, invalid, or digest-mismatched checkpoints do not expose partially imported state. |
| `contract.runtime.component_adapter.digest.failures` | `ReplayStateDigest` | `adapter.replayStateDigest` | Digest success or failure has no adapted component state effect. |
| `contract.runtime.component_adapter.invariants.failures` | `VerifyReplayState` | `adapter.verifyReplayState` | Invariant verification success or failure has no adapted component state effect. |

## Public values and items

| Public definition | Kind | Fields | Meaning |
|---|---|---|---|
| `RuntimeArgumentDescriptor` | `attribute` | `name: String`, `required: Boolean`, `default[0..1]: JsonValue` | Defined by its typed fields and action requirements. |
| `RuntimeFailureBindingDescriptor` | `attribute` | `failureName: String`, `codecId: String`, `codecVersion: Integer`, `contentType: String` = `"application/json"`, `traceDisposition: RuntimeTraceDisposition`, `replayMode: RuntimeReplayMode` = `RuntimeReplayMode::no_state_effect` | Defined by its typed fields and action requirements. |
| `RuntimeActionBindingDescriptor` | `attribute` | `componentContractId: String`, `actionId: String`, `bindingId: String`, `bindingVersion: Integer`, `schemaVersion: Integer`, `requestContentType: String` = `"application/json"`, `requestCodecId: String`, `requestCodecVersion: Integer`, `resultContentType: String` = `"application/json"`, `resultCodecId: String`, `resultCodecVersion: Integer`, `failureContentType: String` = `"application/json"`, `failureCodecId: String`, `failureCodecVersion: Integer`, `requestArguments[0..*]: RuntimeArgumentDescriptor`, `supportedFailureNames[0..*]: String`, `failureBindings[0..*]: RuntimeFailureBindingDescriptor`, `idempotency: RuntimeActionIdempotency`, `concurrencyLane: String` = `"serialized"`, `replayMode: RuntimeReplayMode`, `canonicalEffectSchemaVersion[0..1]: Integer`, `canonicalEffectCodecId[0..1]: String`, `canonicalEffectCodecVersion[0..1]: Integer`, `modeledFaultTraceDisposition: RuntimeTraceDisposition` = `RuntimeTraceDisposition::aborted`, `maxInFlight: Integer` = `1`, `externallyEffectful: Boolean` = `false`, `recoveryAuthorized: Boolean` = `false` | Defined by its typed fields and action requirements. |
| `RuntimeDispatchResult` | `attribute` | `response: RuntimeMessageEnvelope`, `canonicalEffect[0..1]: JsonObject`, `effectDigest[0..1]: String`, `traceDisposition: RuntimeTraceDisposition` | Defined by its typed fields and action requirements. |
| `RuntimeBindingDescription` | `attribute` | `bindingId: String`, `bindingVersion: Integer`, `actions[1..*]: RuntimeActionBindingDescriptor` | Defined by its typed fields and action requirements. |
| `RuntimeReplayStateStatus` | `attribute` | `available: Boolean`, `empty: Boolean`, `prepared: Boolean`, `checkpointCursor: Integer`, `stateDigest[0..1]: String`, `limitations[0..*]: String` | Defined by its typed fields and action requirements. |
| `RuntimeBindingInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimePayloadInvalid` | `attribute` | `message: String` | Defined by its typed fields and action requirements. |
| `RuntimeComponentFault` | `attribute` | `message: String`, `faultType: String`, `evidence: JsonObject` | Defined by its typed fields and action requirements. |

## Public enumerations

| Enumeration | Logical literals |
|---|---|
| `RuntimeActionIdempotency` | `idempotent`, `non_idempotent`, `unspecified` |

## Verification

| Verification | Subject | Objectives | Evidence |
|---|---|---|---|
| `ComponentRuntimeAdapterBoundaryVerification` | `ComponentRuntimeAdapter` | `explicitMapping`, `directMessageEquivalence`, `resolvedReplayEffects`, `reconstructionStateControl`, `recoveryAuthorization` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ComponentRuntimeAdapterBoundaryVerification` |
| `DescribeRuntimeBindingContractVerification` | `DescribeRuntimeBinding` | `describeFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#DescribeRuntimeBindingContractVerification` |
| `DispatchRuntimeMessageContractVerification` | `DispatchRuntimeMessage` | `dispatchFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#DispatchRuntimeMessageContractVerification` |
| `ApplyCanonicalReplayEffectContractVerification` | `ApplyCanonicalReplayEffect` | `replayFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ApplyCanonicalReplayEffectContractVerification` |
| `ReplayStateStatusContractVerification` | `ReplayStateStatus` | `replayStateStatusFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateStatusContractVerification` |
| `ResetReplayStateContractVerification` | `ResetReplayState` | `resetFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ResetReplayStateContractVerification` |
| `ImportReplayCheckpointContractVerification` | `ImportReplayCheckpoint` | `checkpointFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ImportReplayCheckpointContractVerification` |
| `ReplayStateDigestContractVerification` | `ReplayStateDigest` | `digestFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateDigestContractVerification` |
| `VerifyReplayStateContractVerification` | `VerifyReplayState` | `invariantVerificationFailureSemantics` | `components/runtime/component_adapter/tests/test_component_adapter_contract.py#VerifyReplayStateContractVerification` |

Equivalent private algorithms, helpers, storage layouts, and implementation-language inheritance remain implementation choices.
