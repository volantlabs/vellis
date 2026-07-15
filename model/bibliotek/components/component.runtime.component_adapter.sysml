library package BibliotekRuntimeComponentAdapter {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRuntimeMessageRuntime::*;
    private import ScalarValues::*;

    enum def RuntimeActionIdempotency {
        enum idempotent;
        enum non_idempotent;
        enum unspecified;
    }
    attribute def RuntimeArgumentDescriptor {
        attribute name : String;
        attribute required : Boolean;
        attribute 'default'[0..1] : JsonValue;
    }
    attribute def RuntimeFailureBindingDescriptor {
        attribute failureName : String;
        attribute codecId : String;
        attribute codecVersion : Integer;
        attribute contentType : String default = "application/json";
        attribute traceDisposition : RuntimeTraceDisposition;
        attribute replayMode : RuntimeReplayMode default = RuntimeReplayMode::no_state_effect;
    }
    attribute def RuntimeActionBindingDescriptor {
        attribute componentContractId : String;
        attribute actionId : String;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute schemaVersion : Integer;
        attribute requestContentType : String default = "application/json";
        attribute requestCodecId : String;
        attribute requestCodecVersion : Integer;
        attribute resultContentType : String default = "application/json";
        attribute resultCodecId : String;
        attribute resultCodecVersion : Integer;
        attribute failureContentType : String default = "application/json";
        attribute failureCodecId : String;
        attribute failureCodecVersion : Integer;
        attribute requestArguments[0..*] : RuntimeArgumentDescriptor;
        attribute supportedFailureNames[0..*] : String;
        attribute failureBindings[0..*] : RuntimeFailureBindingDescriptor;
        attribute idempotency : RuntimeActionIdempotency;
        attribute concurrencyLane : String default = "serialized";
        attribute replayMode : RuntimeReplayMode;
        attribute canonicalEffectSchemaVersion[0..1] : Integer;
        attribute canonicalEffectCodecId[0..1] : String;
        attribute canonicalEffectCodecVersion[0..1] : Integer;
        attribute modeledFaultTraceDisposition : RuntimeTraceDisposition default = RuntimeTraceDisposition::aborted;
        attribute maxInFlight : Integer default = 1;
        attribute externallyEffectful : Boolean default = false;
        attribute recoveryAuthorized : Boolean default = false;
    }
    attribute def RuntimeDispatchResult {
        ref item response : RuntimeMessageEnvelope;
        attribute canonicalEffect[0..1] : JsonObject;
        attribute effectDigest[0..1] : String;
        attribute traceDisposition : RuntimeTraceDisposition;
    }
    attribute def RuntimeBindingDescription {
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute actions[1..*] : RuntimeActionBindingDescriptor;
    }
    attribute def RuntimeReplayStateStatus {
        attribute available : Boolean;
        attribute empty : Boolean;
        attribute prepared : Boolean;
        attribute checkpointCursor : Integer;
        attribute stateDigest[0..1] : String;
        attribute limitations[0..*] : String;
    }
    attribute def RuntimeBindingInvalid { attribute 'message' : String; }
    attribute def RuntimePayloadInvalid { attribute 'message' : String; }
    attribute def RuntimeComponentFault { attribute 'message' : String; attribute faultType : String; attribute evidence : JsonObject; }

    action def DescribeRuntimeBinding {
        out description : RuntimeBindingDescription;
        doc /* Return the explicit routable action inventory; arbitrary object methods are absent. */
        @FailureContract { errorIds = (); }
    }
    action def DispatchRuntimeMessage {
        in request : RuntimeMessageEnvelope;
        out result : RuntimeDispatchResult;
        doc /* Decode one registered request, invoke the corresponding black-box action exactly once, and encode its public result or modeled failure. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimePayloadInvalid", "RuntimeComponentFault"); }
    }
    action def ApplyCanonicalReplayEffect {
        in effect : JsonObject;
        doc /* Apply one compatible committed effect without recording new business traffic or repeating external effects. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimePayloadInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ReplayStateStatus {
        out status : RuntimeReplayStateStatus;
        doc /* Report whether the adapted occurrence is empty, checkpoint-prepared, or unavailable for safe reconstruction. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ResetReplayState {
        doc /* Replace the adapted occurrence state with its contract-defined empty state before reconstruction. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ImportReplayCheckpoint {
        in reference : String;
        out throughPosition : Integer;
        doc /* Atomically import one binding-compatible checkpoint and return the represented runtime position; the runtime verifies its digest before later effects. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimePayloadInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ReplayStateDigest {
        out digest : String;
        doc /* Compute one deterministic canonical digest without changing adapted component state. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }
    action def VerifyReplayState {
        out limitations[0..*] : String;
        doc /* Verify the adapted component's public invariants without changing its state; an empty limitation list means verified. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }

    part def <'component.runtime.component_adapter'> ComponentRuntimeAdapter {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        doc /* Explicitly maps one reusable black-box component occurrence to runtime messages while preserving its direct protocol. */
        ref part runtime[1] : MessageRuntime;
        port messages : ~RuntimeMessagePort;
        interface runtimeExchange : RuntimeMessageExchange
            connect messages to runtime.messages;
        attribute occurrenceAddress : RuntimeAddress;
        attribute bindingDescription : RuntimeBindingDescription;
        perform action describe[0..*] : DescribeRuntimeBinding;
        perform action dispatch[0..*] : DispatchRuntimeMessage;
        perform action applyReplayEffect[0..*] : ApplyCanonicalReplayEffect;
        perform action replayStateStatus[0..*] : ReplayStateStatus;
        perform action resetReplayState[0..*] : ResetReplayState;
        perform action importReplayCheckpoint[0..*] : ImportReplayCheckpoint;
        perform action replayStateDigest[0..*] : ReplayStateDigest;
        perform action verifyReplayState[0..*] : VerifyReplayState;
        dependency describeBinding from describe to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Expose the immutable explicit binding inventory without component effects. */ }
        dependency dispatchBinding from dispatch to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Route only registered actions and preserve modeled defaults, results, failures, and effects. */ }
        dependency replayBinding from applyReplayEffect to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Validate effect compatibility before delegating replay to the state owner. */ }
        dependency statusBinding from replayStateStatus to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Inspect only the explicitly supported reconstruction status surface without mutation. */ }
        dependency resetBinding from resetReplayState to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Require explicit reset support before replacing adapted state with empty state. */ }
        dependency checkpointBinding from importReplayCheckpoint to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Require exact checkpoint and binding compatibility before state replacement. */ }
        dependency digestBinding from replayStateDigest to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Select the binding's deterministic canonical digest codec without mutation. */ }
        dependency invariantBinding from verifyReplayState to bindingDescription { @StateAccess { kind = StateAccessKind::read; } doc /* Invoke only the binding-declared invariant verification surface without mutation. */ }
    }

    requirement <'contract.runtime.component_adapter.explicit_mapping'> explicitMapping {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Every routable action declares request/result/failure schema and codec versions, request arguments and defaults, concrete supported failures and modeled-fault disposition, canonical-effect codec, idempotency, concurrency, replay mode, external-effect status, and whether the action alone is authorized while reconstruction is required; reflection never exposes private methods. */ }
    }
    requirement <'contract.runtime.component_adapter.equivalence'> directMessageEquivalence {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Direct and message-mediated invocation preserve logical inputs, defaults, public results, concrete failures, ordering, and state effects. */ }
    }
    requirement <'contract.runtime.component_adapter.replay'> resolvedReplayEffects {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* State-owning actions capture nondeterministic resolved values in canonical effects; reads and coordinators do not duplicate derived effects, while a coordinator that owns a confirmed aggregate state may emit an explicit final effect that supersedes its same-trace derived effects. */ }
    }
    requirement <'contract.runtime.component_adapter.reconstruction'> reconstructionStateControl {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Reconstruction uses only explicitly supported reset, checkpoint import, deterministic digest, and invariant verification operations; checkpoint import is atomic and must match its expected digest. */ }
    }
    requirement <'contract.runtime.component_adapter.recovery_authorization'> recoveryAuthorization {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Recovery authorization defaults false and may be declared only for a non-effectful coordinator action that is intentionally safe as the sole recovery ingress; it never grants arbitrary routing or replay authority. */ }
    }
    requirement <'contract.runtime.component_adapter.describe.failures'> describeFailureSemantics {
        subject operation : DescribeRuntimeBinding;
        require constraint { doc /* Description has no declared domain failure and changes neither component nor adapter state. */ }
    }
    requirement <'contract.runtime.component_adapter.dispatch.failures'> dispatchFailureSemantics {
        subject operation : DispatchRuntimeMessage;
        require constraint { doc /* Invalid bindings or payloads are rejected before component invocation; modeled component failures preserve their declared no-effect or documented effect semantics. */ }
    }
    requirement <'contract.runtime.component_adapter.replay.failures'> replayFailureSemantics {
        subject operation : ApplyCanonicalReplayEffect;
        require constraint { doc /* An incompatible effect is rejected before invoking the state owner. */ }
    }
    requirement <'contract.runtime.component_adapter.replay_state_status.failures'> replayStateStatusFailureSemantics {
        subject operation : ReplayStateStatus;
        require constraint { doc /* Status inspection success or failure has no adapted component state effect and never reports an unsafe target as prepared. */ }
    }
    requirement <'contract.runtime.component_adapter.reset.failures'> resetFailureSemantics {
        subject operation : ResetReplayState;
        require constraint { doc /* Unsupported or failed reset does not expose a partially reset occurrence as reconstruction-ready. */ }
    }
    requirement <'contract.runtime.component_adapter.checkpoint.failures'> checkpointFailureSemantics {
        subject operation : ImportReplayCheckpoint;
        require constraint { doc /* Incompatible, invalid, or digest-mismatched checkpoints do not expose partially imported state. */ }
    }
    requirement <'contract.runtime.component_adapter.digest.failures'> digestFailureSemantics {
        subject operation : ReplayStateDigest;
        require constraint { doc /* Digest success or failure has no adapted component state effect. */ }
    }
    requirement <'contract.runtime.component_adapter.invariants.failures'> invariantVerificationFailureSemantics {
        subject operation : VerifyReplayState;
        require constraint { doc /* Invariant verification success or failure has no adapted component state effect. */ }
    }

    part adapterContractContext {
        part adapter : ComponentRuntimeAdapter;
        satisfy explicitMapping by adapter;
        satisfy directMessageEquivalence by adapter;
        satisfy resolvedReplayEffects by adapter;
        satisfy reconstructionStateControl by adapter;
        satisfy recoveryAuthorization by adapter;
        satisfy describeFailureSemantics by adapter.describe;
        satisfy dispatchFailureSemantics by adapter.dispatch;
        satisfy replayFailureSemantics by adapter.applyReplayEffect;
        satisfy replayStateStatusFailureSemantics by adapter.replayStateStatus;
        satisfy resetFailureSemantics by adapter.resetReplayState;
        satisfy checkpointFailureSemantics by adapter.importReplayCheckpoint;
        satisfy digestFailureSemantics by adapter.replayStateDigest;
        satisfy invariantVerificationFailureSemantics by adapter.verifyReplayState;
    }
    verification def ComponentRuntimeAdapterBoundaryVerification {
        subject adapter : ComponentRuntimeAdapter;
        objective { verify explicitMapping; verify directMessageEquivalence; verify resolvedReplayEffects; verify reconstructionStateControl; verify recoveryAuthorization; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ComponentRuntimeAdapterBoundaryVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def DescribeRuntimeBindingContractVerification {
        subject operation : DescribeRuntimeBinding;
        objective { verify describeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#DescribeRuntimeBindingContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def DispatchRuntimeMessageContractVerification {
        subject operation : DispatchRuntimeMessage;
        objective { verify dispatchFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#DispatchRuntimeMessageContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ApplyCanonicalReplayEffectContractVerification {
        subject operation : ApplyCanonicalReplayEffect;
        objective { verify replayFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ApplyCanonicalReplayEffectContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ReplayStateStatusContractVerification {
        subject operation : ReplayStateStatus;
        objective { verify replayStateStatusFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateStatusContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ResetReplayStateContractVerification {
        subject operation : ResetReplayState;
        objective { verify resetFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ResetReplayStateContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ImportReplayCheckpointContractVerification {
        subject operation : ImportReplayCheckpoint;
        objective { verify checkpointFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ImportReplayCheckpointContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ReplayStateDigestContractVerification {
        subject operation : ReplayStateDigest;
        objective { verify digestFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateDigestContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def VerifyReplayStateContractVerification {
        subject operation : VerifyReplayState;
        objective { verify invariantVerificationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#VerifyReplayStateContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
}
