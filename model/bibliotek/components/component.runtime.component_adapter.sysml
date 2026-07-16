library package BibliotekRuntimeComponentAdapter {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import BibliotekRuntimeMessaging::*;
    private import BibliotekRuntimeMessageRuntime::*;
    private import ScalarValues::*;

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
    attribute def RuntimeTerminalEncodingFailed { attribute 'message' : String; }

    action def DescribeRuntimeBinding {
        out description : RuntimeBindingDescription;
        doc /* Return the explicit action inventory. Private methods and component-purpose labels are absent. */
        @FailureContract { errorIds = (); }
    }
    action def DeliverRuntimeEnvelope {
        in envelope : RuntimeMessageEnvelope;
        doc /* Accept one runtime delivery. A request handler terminates only through runtime complete or fault; a signal, response, or fault terminates only through acknowledgement. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimePayloadInvalid", "RuntimeTerminalEncodingFailed"); }
    }
    action def ApplyCanonicalReplayEffect {
        in effect : JsonObject;
        doc /* Apply one compatible committed effect without creating new business traffic or repeating an external effect. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimePayloadInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ReplayStateStatus {
        out status : RuntimeReplayStateStatus;
        doc /* Report whether the occurrence owns replay state and whether that state is empty or checkpoint-prepared. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ResetReplayState {
        doc /* Replace supported replay-owned state with the component-defined empty state. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ImportReplayCheckpoint {
        in reference : String;
        out throughPosition : Integer;
        doc /* Atomically import a compatible checkpoint and return the represented runtime position. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimePayloadInvalid", "RuntimeReplayIncompatible"); }
    }
    action def ReplayStateDigest {
        out digest : String;
        doc /* Compute a deterministic digest of the replay-owned state without changing it. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }
    action def VerifyReplayState {
        out limitations[0..*] : String;
        doc /* Verify public state invariants; an empty limitations list means verified. */
        @FailureContract { errorIds = ("RuntimeBindingInvalid", "RuntimeReplayIncompatible"); }
    }

    part def <'component.runtime.component_adapter'> ComponentRuntimeAdapter :> RuntimeParticipant {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        doc /* Standard composable realization of the minimal runtime participant protocol. It adapts any ordinary component occurrence through explicit handlers, codecs, continuations, effects, and replay functions. It is not a framework superclass and alternative conforming participants remain valid. */
        ref part runtime[1] : MessageRuntime;
        port messages : ~RuntimeMessagePort;
        interface runtimeExchange : RuntimeMessageExchange connect messages to runtime.messages;
        attribute occurrenceAddress : RuntimeAddress;
        attribute bindingDescription : RuntimeBindingDescription;
        attribute continuations : JsonObject;
        attribute outstandingExecutionLimit : Integer;
        perform action describe[0..*] : DescribeRuntimeBinding { doc /* Read the immutable binding inventory. */ }
        perform action deliver[0..*] : DeliverRuntimeEnvelope { doc /* Decode, execute, continue, or acknowledge one envelope. */ }
        perform action applyReplayEffect[0..*] : ApplyCanonicalReplayEffect { doc /* Apply one explicitly registered effect. */ }
        perform action replayStateStatus[0..*] : ReplayStateStatus { doc /* Inspect replay readiness. */ }
        perform action resetReplayState[0..*] : ResetReplayState { doc /* Reset replay-owned state. */ }
        perform action importReplayCheckpoint[0..*] : ImportReplayCheckpoint { doc /* Import one compatible checkpoint. */ }
        perform action replayStateDigest[0..*] : ReplayStateDigest { doc /* Read a deterministic state digest. */ }
        perform action verifyReplayState[0..*] : VerifyReplayState { doc /* Verify replay-owned state invariants. */ }
        dependency describedBinding from describe to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency deliveredBinding from deliver to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency deliveredContinuation from deliver to continuations { @StateAccess { kind = StateAccessKind::write; } }
        dependency replayedBinding from applyReplayEffect to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency statusBinding from replayStateStatus to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency resetBinding from resetReplayState to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency checkpointBinding from importReplayCheckpoint to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency digestBinding from replayStateDigest to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
        dependency verificationBinding from verifyReplayState to bindingDescription { @StateAccess { kind = StateAccessKind::read; } }
    }

    requirement <'contract.runtime.component_adapter.one_archetype'> oneComponentArchetype {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* The same participant and adapter contracts host local, coordinating, state-owning, stateless, external-interface, and mixed action behavior. Store, controller, coordinator, façade, gateway, actor, and saga labels create neither adapter subtypes nor runtime registration categories. */ }
    }
    requirement <'contract.runtime.component_adapter.minimal_participant'> minimalParticipantSubstitution {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* The runtime-facing obligation is only asynchronous envelope delivery with its scoped participant context. Bibliotek's adapter is one conforming implementation; an equivalent hand-authored participant can replace it without changing runtime routing. */ }
    }
    requirement <'contract.runtime.component_adapter.uniform_handler'> uniformActionHandler {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Every action handler receives decoded arguments and one execution context. It may perform local work, send or await messages, compensate, and aggregate. It does not return a second runtime result path and must explicitly complete or fault its inbound request. */ }
    }
    requirement <'contract.runtime.component_adapter.explicit_mapping'> explicitMapping {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Every routable action explicitly declares schemas, codecs, arguments and defaults, failures, lane, consistency group and access, idempotency, deadline, replay mode, canonical effect, and external-effect status. The descriptor contains no component-role or handler-kind field and reflection exposes no unregistered method. */ }
    }
    requirement <'contract.runtime.component_adapter.continuations'> messageContinuations {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* A coordinating handler calls collaborators by sending a request with a deterministic step message ID and waiting on a loop-neutral bounded continuation keyed by correlation. Reusing one step key with identical immutable content observes the same continuation; changed content is rejected. Response and fault delivery resolves and removes the continuation and is always acknowledged, including after caller timeout. Durable outcome lookup replaces terminal in-memory caches. */ }
    }
    requirement <'contract.runtime.component_adapter.execution_lifetime'> boundedExecutionLifetime {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* The adapter bounds outstanding outbound continuations and cooperates with runtime-hosted action deadlines. Caller wait timeout never cancels component execution. Cancellation of an off-loop synchronous invocation waits for that invocation to settle. A coordinating handler may compensate before faulting; otherwise deadline expiry renders the execution indeterminate. */ }
    }
    requirement <'contract.runtime.component_adapter.equivalence'> directMessageEquivalence {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Generated local handlers preserve the logical component's defaults, ordering, results, failures, and state effects. Runtime messaging remains visible to coordinating handlers through action references, argument mappings, target addresses, and deterministic step keys rather than proxy objects. */ }
    }
    requirement <'contract.runtime.component_adapter.replay'> replayStateComposition {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Optional canonical-effect application, empty/reset/checkpoint, deterministic digest, and invariant-verification functions compose into the same adapter. Their absence means the occurrence owns no replayed state, not that it belongs to a different participant type. */ }
    }
    requirement <'contract.runtime.component_adapter.failures'> adapterFailureSemantics {
        subject adapter : ComponentRuntimeAdapter;
        require constraint { doc /* Invalid action, payload, codec, effect, or terminal encoding is rejected without unmodeled component mutation. Modeled component faults retain their declared evidence and disposition; unexpected faults remain distinct and indeterminate. */ }
    }
    requirement <'contract.runtime.component_adapter.describe.failures'> describeBindingFailureSemantics { subject operation : DescribeRuntimeBinding; require constraint { doc /* Description changes neither adapted component nor continuation state. */ } }
    requirement <'contract.runtime.component_adapter.deliver.failures'> deliverEnvelopeFailureSemantics { subject operation : DeliverRuntimeEnvelope; require constraint { doc /* Invalid binding or payload is rejected before component invocation; a started request is never silently left complete. */ } }
    requirement <'contract.runtime.component_adapter.effect.failures'> applyReplayEffectFailureSemantics { subject operation : ApplyCanonicalReplayEffect; require constraint { doc /* Incompatible effects are rejected before invoking the state owner. */ } }
    requirement <'contract.runtime.component_adapter.status.failures'> replayStatusFailureSemantics { subject operation : ReplayStateStatus; require constraint { doc /* Status failure never reports an unsafe target as prepared. */ } }
    requirement <'contract.runtime.component_adapter.reset.failures'> resetReplayStateFailureSemantics { subject operation : ResetReplayState; require constraint { doc /* Failed reset never reports partial state as reconstruction-ready. */ } }
    requirement <'contract.runtime.component_adapter.checkpoint.failures'> importCheckpointFailureSemantics { subject operation : ImportReplayCheckpoint; require constraint { doc /* Invalid checkpoint never exposes partially imported state as prepared. */ } }
    requirement <'contract.runtime.component_adapter.digest.failures'> replayDigestFailureSemantics { subject operation : ReplayStateDigest; require constraint { doc /* Digest failure has no state effect. */ } }
    requirement <'contract.runtime.component_adapter.verify.failures'> verifyReplayStateFailureSemantics { subject operation : VerifyReplayState; require constraint { doc /* Invariant verification failure has no state effect. */ } }

    part adapterContractContext {
        part adapter : ComponentRuntimeAdapter;
        satisfy oneComponentArchetype by adapter;
        satisfy minimalParticipantSubstitution by adapter;
        satisfy uniformActionHandler by adapter;
        satisfy explicitMapping by adapter;
        satisfy messageContinuations by adapter;
        satisfy boundedExecutionLifetime by adapter;
        satisfy directMessageEquivalence by adapter;
        satisfy replayStateComposition by adapter;
        satisfy adapterFailureSemantics by adapter;
        satisfy describeBindingFailureSemantics by adapter.describe;
        satisfy deliverEnvelopeFailureSemantics by adapter.deliver;
        satisfy applyReplayEffectFailureSemantics by adapter.applyReplayEffect;
        satisfy replayStatusFailureSemantics by adapter.replayStateStatus;
        satisfy resetReplayStateFailureSemantics by adapter.resetReplayState;
        satisfy importCheckpointFailureSemantics by adapter.importReplayCheckpoint;
        satisfy replayDigestFailureSemantics by adapter.replayStateDigest;
        satisfy verifyReplayStateFailureSemantics by adapter.verifyReplayState;
    }
    verification def ComponentRuntimeAdapterBoundaryVerification {
        subject adapter : ComponentRuntimeAdapter;
        objective { verify oneComponentArchetype; verify minimalParticipantSubstitution; verify uniformActionHandler; verify explicitMapping; verify messageContinuations; verify boundedExecutionLifetime; verify directMessageEquivalence; verify replayStateComposition; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ComponentRuntimeAdapterBoundaryVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def DeliverRuntimeEnvelopeContractVerification { subject operation : DeliverRuntimeEnvelope; objective { verify deliverEnvelopeFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#DeliverRuntimeEnvelopeContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ComponentRuntimeReplayVerification {
        subject adapter : ComponentRuntimeAdapter;
        objective { verify replayStateComposition; verify adapterFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ComponentRuntimeReplayVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def DescribeRuntimeBindingContractVerification { subject operation : DescribeRuntimeBinding; objective { verify describeBindingFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#DescribeRuntimeBindingContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ApplyCanonicalReplayEffectContractVerification { subject operation : ApplyCanonicalReplayEffect; objective { verify applyReplayEffectFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ApplyCanonicalReplayEffectContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ReplayStateStatusContractVerification { subject operation : ReplayStateStatus; objective { verify replayStatusFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateStatusContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ResetReplayStateContractVerification { subject operation : ResetReplayState; objective { verify resetReplayStateFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ResetReplayStateContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ImportReplayCheckpointContractVerification { subject operation : ImportReplayCheckpoint; objective { verify importCheckpointFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ImportReplayCheckpointContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ReplayStateDigestContractVerification { subject operation : ReplayStateDigest; objective { verify replayDigestFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#ReplayStateDigestContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def VerifyReplayStateContractVerification { subject operation : VerifyReplayState; objective { verify verifyReplayStateFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/component_adapter/tests/test_component_adapter_contract.py#VerifyReplayStateContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
}
