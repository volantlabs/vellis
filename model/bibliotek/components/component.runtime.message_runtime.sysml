library package BibliotekRuntimeMessageRuntime {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    enum def RuntimeMessageKind {
        enum request;
        enum response;
        enum fault;
        enum signal;
    }
    enum def RuntimeTraceDisposition {
        enum committed;
        enum aborted;
        enum indeterminate;
    }
    enum def RuntimeDeliveryStatus {
        enum accepted;
        enum rejected;
        enum delivering;
        enum completed;
        enum faulted;
        enum timed_out;
    }
    enum def RuntimeReplayMode {
        enum no_state_effect;
        enum canonical_effect;
        enum coordinator_trace;
        enum external_exchange;
    }
    enum def RuntimeExternalBoundaryMode {
        enum playback_only;
        enum live;
        enum simulated;
        enum unavailable;
    }

    attribute def RuntimeAddress {
        attribute runtimeId : Uuid;
        attribute instanceId : Uuid;
        doc /* Durable exact address. Human-readable keys are resolved before an envelope is accepted. */
    }
    attribute def RuntimePayload {
        attribute contentType : String default = "application/json";
        attribute codecId : String;
        attribute codecVersion : Integer;
        attribute value : JsonValue;
        doc /* Canonical versioned, serializable payload; live handles and credentials are never embedded. */
    }
    item def RuntimeMessageEnvelope {
        attribute messageId : Uuid;
        attribute kind : RuntimeMessageKind;
        attribute source : RuntimeAddress;
        attribute target : RuntimeAddress;
        attribute componentContractId : String;
        attribute actionId : String;
        attribute schemaVersion : Integer;
        attribute traceId : Uuid;
        attribute correlationId[0..1] : Uuid;
        attribute causationId[0..1] : Uuid;
        attribute idempotencyKey[0..1] : String;
        attribute createdAt : String;
        attribute payload : RuntimePayload;
        doc /* Immutable request, response, fault, or signal identity and canonical payload. */
    }
    attribute def ComponentOccurrenceDeclaration {
        attribute instanceKey : String;
        attribute componentContractId : String;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute queueCapacity : Integer default = 128;
        attribute maxInFlight : Integer default = 1;
        attribute replayAuthority : RuntimeReplayMode default = RuntimeReplayMode::no_state_effect;
        attribute configurationReferences[0..*] : String;
    }
    attribute def ComponentOccurrenceRegistration {
        attribute instanceKey : String;
        attribute instanceId : Uuid;
        attribute componentContractId : String;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute queueCapacity : Integer;
        attribute maxInFlight : Integer;
        attribute replayAuthority : RuntimeReplayMode;
        attribute configurationReferences[0..*] : String;
        doc /* Durable runtime resolution of one declared occurrence; the runtime allocates the first incarnation UUID. */
    }
    attribute def RuntimeCuratedOperationDeclaration {
        attribute operationId : String;
        attribute targetInstanceKey : String;
        attribute componentContractId : String;
        attribute actionId : String;
        attribute schemaVersion : Integer;
    }
    attribute def RuntimeTopologyManifest {
        attribute manifestSchemaVersion : Integer;
        attribute runtimeKey : String;
        attribute occurrences[1..*] : ComponentOccurrenceDeclaration;
        attribute curatedOperations[0..*] : RuntimeCuratedOperationDeclaration;
        attribute manifestHash : String;
        doc /* Complete static occurrence, binding, configuration-reference, replay-authority, and curated-operation inventory. */
    }
    attribute def RuntimeTopologyConfirmation {
        attribute manifestHash : String;
        attribute topologyHash : String;
        attribute occurrenceCount : Integer;
    }
    attribute def RuntimeMessageReceipt {
        attribute messageId : Uuid;
        attribute traceId : Uuid;
        attribute acceptedPosition : Integer;
        attribute status : RuntimeDeliveryStatus;
    }
    attribute def RuntimeRequestOutcome {
        attribute request : RuntimeMessageReceipt;
        ref item response : RuntimeMessageEnvelope;
        attribute terminalPosition : Integer;
        attribute traceDisposition : RuntimeTraceDisposition;
    }
    attribute def RuntimeHistoryQuery {
        attribute afterPosition[0..1] : Integer;
        attribute throughPosition[0..1] : Integer;
        attribute afterTime[0..1] : String;
        attribute throughTime[0..1] : String;
        attribute runtimeId[0..1] : Uuid;
        attribute instanceKey[0..1] : String;
        attribute instanceId[0..1] : Uuid;
        attribute componentContractId[0..1] : String;
        attribute messageId[0..1] : Uuid;
        attribute traceId[0..1] : Uuid;
        attribute correlationId[0..1] : Uuid;
        attribute causationId[0..1] : Uuid;
        attribute actionId[0..1] : String;
        attribute messageKind[0..1] : RuntimeMessageKind;
        attribute schemaVersion[0..1] : Integer;
        attribute deliveryStatus[0..1] : RuntimeDeliveryStatus;
        attribute traceDisposition[0..1] : RuntimeTraceDisposition;
        attribute factType[0..1] : String;
        attribute limit : Integer default = 100;
    }
    attribute def RuntimeLedgerFact {
        attribute runtimePosition : Integer;
        attribute factType : String;
        attribute recordedAt : String;
        attribute runtimeId : Uuid;
        attribute instanceKey[0..1] : String;
        attribute instanceId[0..1] : Uuid;
        attribute componentContractId[0..1] : String;
        attribute messageId[0..1] : Uuid;
        attribute traceId[0..1] : Uuid;
        attribute correlationId[0..1] : Uuid;
        attribute causationId[0..1] : Uuid;
        attribute actionId[0..1] : String;
        attribute schemaVersion[0..1] : Integer;
        ref item envelope[0..1] : RuntimeMessageEnvelope;
        attribute details : JsonObject;
    }
    attribute def RuntimeHistoryPage {
        attribute facts[0..*] : RuntimeLedgerFact;
        attribute nextPosition[0..1] : Integer;
    }
    attribute def RuntimeCausalTrace {
        attribute traceId : Uuid;
        attribute facts[0..*] : RuntimeLedgerFact;
        attribute disposition[0..1] : RuntimeTraceDisposition;
    }
    attribute def RuntimeExternalBoundaryDisposition {
        attribute boundaryId : String;
        attribute mode : RuntimeExternalBoundaryMode;
        attribute limitation[0..1] : String;
    }
    attribute def RuntimeReconstructionRequest {
        attribute throughPosition[0..1] : Integer;
        attribute sourceRuntimeId[0..1] : Uuid;
        attribute checkpointReference[0..1] : String;
        attribute checkpointReferences : JsonObject;
        attribute resetTargets : Boolean default = false;
        attribute externalBoundaries[0..*] : RuntimeExternalBoundaryDisposition;
    }
    attribute def RuntimeReconstructionReport {
        attribute startPosition : Integer;
        attribute throughPosition : Integer;
        attribute appliedEffects : Integer;
        attribute skippedEffects : Integer;
        attribute incompatibleEffects : Integer;
        attribute stateDigests : JsonObject;
        attribute verified : Boolean;
        attribute externalEffectsSkipped : Integer;
        attribute externalBoundaries[0..*] : RuntimeExternalBoundaryDisposition;
        attribute limitations[0..*] : String;
        attribute verifiedDigest[0..1] : String;
        doc /* verifiedDigest is the canonical digest of the complete per-occurrence state-digest map and is present only after verified reconstruction. */
    }

    attribute def RuntimeRegistrationInvalid { attribute 'message' : String; }
    attribute def RuntimeAddressUnknown { attribute 'message' : String; }
    attribute def RuntimeActionUnknown { attribute 'message' : String; }
    attribute def RuntimeSchemaUnsupported { attribute 'message' : String; }
    attribute def RuntimeMessageConflict { attribute 'message' : String; }
    attribute def RuntimeQueueFull { attribute 'message' : String; }
    attribute def RuntimeLedgerUnavailable { attribute 'message' : String; }
    attribute def RuntimeFailStopped { attribute 'message' : String; }
    attribute def RuntimeRequestTimedOut { attribute 'message' : String; }
    attribute def RuntimeReplayIncompatible { attribute 'message' : String; }
    attribute def RuntimeReplayTargetNotPrepared { attribute 'message' : String; }

    action def RegisterComponentOccurrence {
        in declaration : ComponentOccurrenceDeclaration;
        out resolvedRegistration : ComponentOccurrenceRegistration;
        doc /* Resolve exactly one declaration before traffic; allocate its first incarnation UUID or reuse its durable matching resolution after restart. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def PrepareStaticRuntimeTopology {
        in manifest : RuntimeTopologyManifest;
        doc /* Durably fix the complete normalized static occurrence plan before inserting any occurrence; an interrupted first start may resume only that exact plan. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def ConfirmStaticRuntimeTopology {
        in manifest : RuntimeTopologyManifest;
        out confirmation : RuntimeTopologyConfirmation;
        doc /* Confirm every prepared occurrence, attached binding/action, configuration reference, replay authority, and curated operation in the complete manifest before traffic is exposed. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def SendRuntimeMessage {
        in 'message' : RuntimeMessageEnvelope;
        out receipt : RuntimeMessageReceipt;
        doc /* Durably accept one signal or request before dispatching it to the exact target occurrence. */
        @FailureContract { errorIds = ("RuntimeAddressUnknown", "RuntimeActionUnknown", "RuntimeSchemaUnsupported", "RuntimeMessageConflict", "RuntimeQueueFull", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def RequestRuntimeMessage {
        in 'message' : RuntimeMessageEnvelope;
        in timeoutSeconds[0..1] : Real;
        out outcome : RuntimeRequestOutcome;
        doc /* Accept and await one request; a wait timeout does not cancel handler execution. */
        @FailureContract { errorIds = ("RuntimeAddressUnknown", "RuntimeActionUnknown", "RuntimeSchemaUnsupported", "RuntimeMessageConflict", "RuntimeQueueFull", "RuntimeLedgerUnavailable", "RuntimeFailStopped", "RuntimeRequestTimedOut"); }
    }
    action def QueryRuntimeHistory {
        in query : RuntimeHistoryQuery;
        out page : RuntimeHistoryPage;
        doc /* Return deterministic cursor-paginated immutable facts without recursively creating business traffic. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def GetRuntimeCausalTrace {
        in traceId : Uuid;
        out trace : RuntimeCausalTrace;
        doc /* Return every recorded fact in one causal trace and its confirmed terminal disposition. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def ReconstructRuntimeState {
        in request : RuntimeReconstructionRequest;
        out report : RuntimeReconstructionReport;
        doc /* Prepare the target, select committed canonical effects in position order, honor an explicitly marked final aggregate effect over derived effects from the same trace, verify final component digests and invariants, and never repeat recorded external effects. All prior deliveries must be terminal; the sole explicitly recovery-authorized root request that invokes reconstruction is the only permitted pending delivery. Verified reconstruction through an explicit cursor earlier than the source head enters branch-pending state rather than reopening ingress. */
        @FailureContract { errorIds = ("RuntimeReplayIncompatible", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def RecordRuntimeBranchProvenance {
        in sourceRuntimeId : Uuid;
        in sourceCursor : Integer;
        in verifiedDigest : String;
        out runtimePosition : Integer;
        doc /* Recheck the pending reconstructed state, durably record its exact source runtime, selected cursor, and verified digest, and only then open the new branch to ordinary traffic. */
        @FailureContract { errorIds = ("RuntimeReplayIncompatible", "RuntimeReplayTargetNotPrepared", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }

    port def RuntimeMessagePort {
        in item inbound[0..*] : RuntimeMessageEnvelope;
        out item outbound[0..*] : RuntimeMessageEnvelope;
    }
    interface def RuntimeMessageExchange {
        end caller : ~RuntimeMessagePort;
        end runtime : RuntimeMessagePort;
        flow caller.outbound to runtime.inbound;
        flow runtime.outbound to caller.inbound;
    }

    part def <'component.runtime.message_runtime'> MessageRuntime {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        doc /* Own exact-address routing, durable traffic chronology, occurrence identity, trace disposition, and safe system reconstruction. */
        attribute runtimeId : Uuid;
        attribute runtimeKey : String;
        attribute occurrenceRegistry : JsonObject;
        attribute staticTopologyPlan : JsonObject;
        attribute health : String;
        derived attribute currentPosition : Integer;
        port messages : RuntimeMessagePort;
        perform action registerOccurrence[0..*] : RegisterComponentOccurrence;
        perform action prepareStaticTopology[0..*] : PrepareStaticRuntimeTopology;
        perform action confirmStaticTopology[0..*] : ConfirmStaticRuntimeTopology;
        perform action 'send'[0..*] : SendRuntimeMessage;
        perform action request[0..*] : RequestRuntimeMessage;
        perform action queryHistory[0..*] : QueryRuntimeHistory;
        perform action getTrace[0..*] : GetRuntimeCausalTrace;
        perform action reconstruct[0..*] : ReconstructRuntimeState;
        perform action recordBranchProvenance[0..*] : RecordRuntimeBranchProvenance;
        dependency registerRegistry from registerOccurrence to occurrenceRegistry { @StateAccess { kind = StateAccessKind::write; } doc /* Persist one unique key-to-incarnation mapping and binding identity. */ }
        dependency prepareTopologyPlan from prepareStaticTopology to staticTopologyPlan { @StateAccess { kind = StateAccessKind::write; } doc /* Atomically persist the full declaration plan before individual occurrence insertion. */ }
        dependency confirmTopologyPlan from confirmStaticTopology to staticTopologyPlan { @StateAccess { kind = StateAccessKind::read; } doc /* Require the exact prepared plan. */ }
        dependency confirmRegistry from confirmStaticTopology to occurrenceRegistry { @StateAccess { kind = StateAccessKind::read; } doc /* Compare the complete manifest inventory to durable occurrence identities, attached actions, and binding versions. */ }
        dependency sendHistory from 'send' to currentPosition { @StateAccess { kind = StateAccessKind::write; } doc /* Append acceptance before target dispatch and preserve duplicate-message identity. */ }
        dependency requestHistory from request to currentPosition { @StateAccess { kind = StateAccessKind::write; } doc /* Append acceptance, delivery, response or fault, and terminal trace disposition. */ }
        dependency queryHistoryState from queryHistory to currentPosition { @StateAccess { kind = StateAccessKind::read; } doc /* Read immutable ledger facts without changing canonical business history. */ }
        dependency traceHistoryState from getTrace to currentPosition { @StateAccess { kind = StateAccessKind::read; } doc /* Read the complete ordered causal trace without changing canonical history. */ }
        dependency reconstructHistory from reconstruct to currentPosition { @StateAccess { kind = StateAccessKind::read; } doc /* Select committed canonical effects and verify reconstruction without re-delivering coordinator commands. */ }
        dependency branchHistory from recordBranchProvenance to currentPosition { @StateAccess { kind = StateAccessKind::write; } doc /* Append exactly one matching provenance fact before reopening a verified historical branch. */ }
    }

    requirement <'contract.runtime.message_runtime.delivery'> durableBeforeDispatch {
        subject runtime : MessageRuntime;
        require constraint { doc /* A message is never dispatched before durable acceptance; initial append failure has no component effect. */ }
    }
    requirement <'contract.runtime.message_runtime.identity'> durableIdentity {
        subject runtime : MessageRuntime;
        require constraint { doc /* The runtime allocates the first incarnation UUID for each manifest key, reuses that resolution across restart, and rejects duplicate live keys or UUIDs; callers never assign first-incarnation identity. */ }
    }
    requirement <'contract.runtime.message_runtime.static_topology_atomicity'> staticTopologyAtomicity {
        subject runtime : MessageRuntime;
        require constraint { doc /* Static application composition durably prepares the complete normalized occurrence plan before inserting any occurrence. Once prepared or confirmed, registration accepts only exact declared keys and contracts; a rejected changed manifest inserts nothing, and interruption may resume only the same plan. */ }
    }
    requirement <'contract.runtime.message_runtime.ordering'> boundedOccurrenceOrdering {
        subject runtime : MessageRuntime;
        require constraint { doc /* Each occurrence has a bounded FIFO queue and one in-flight delivery unless its accepted binding declares safe higher concurrency; no global execution order is promised. A root trace receives a terminal disposition only after its root and every accepted causal descendant has a recorded response or fault. */ }
    }
    requirement <'contract.runtime.message_runtime.deduplication'> messageDeduplication {
        subject runtime : MessageRuntime;
        require constraint { doc /* Identical reuse of a message ID observes its current or prior outcome without re-execution; changed content under the same ID is rejected. */ }
    }
    requirement <'contract.runtime.message_runtime.fail_stop'> terminalPersistenceFailStop {
        subject runtime : MessageRuntime;
        require constraint { doc /* Failure to encode or persist a terminal result after an effect places the runtime in fail-stop state, quiesces accepted traffic, and rejects further traffic. */ }
    }
    requirement <'contract.runtime.message_runtime.causality'> terminalCausality {
        subject runtime : MessageRuntime;
        require constraint { doc /* Every accepted causal message identifies an accepted parent in the same open trace. New causal messages are rejected after the trace terminal fact, while exact duplicate observation remains available without re-execution. */ }
    }
    requirement <'contract.runtime.message_runtime.recovery_ingress'> recoveryIngress {
        subject runtime : MessageRuntime;
        require constraint { doc /* Confirmed canonical history awaiting reconstruction, an indeterminate trace, or an indeterminate reconstruction places the runtime in recovery-required state across restart. Ordinary traffic is rejected; only a sole root request whose accepted descriptor explicitly authorizes recovery may enter, and successful verified reconstruction durably reopens traffic. */ }
    }
    requirement <'contract.runtime.message_runtime.replay'> canonicalEffectReplay {
        subject runtime : MessageRuntime;
        require constraint { doc /* Reconstruction starts only from proven-empty occurrences or one compatible imported checkpoint after every prior delivery is terminal; a sole explicitly recovery-authorized root request may remain pending only while it invokes reconstruction. Reconstruction applies only committed canonical effects, lets the latest explicitly marked final aggregate effect supersede derived effects in the same trace, excludes aborted and indeterminate traces, never repeats external effects, and reports incompatible history or unavailable external boundaries. Final digest and invariant verification, including nested public component reads, executes as derived playback and appends no canonical business traffic. */ }
    }
    requirement <'contract.runtime.message_runtime.branching'> verifiedHistoricalBranching {
        subject runtime : MessageRuntime;
        require constraint { doc /* Verified reconstruction through an explicit position earlier than the source head durably records that provenance is required and remains branch-pending across restart. Ordinary traffic is rejected until the runtime rechecks every represented occurrence digest and records the exact source runtime, source cursor, and combined verified digest; mismatched or unsolicited provenance never opens ingress. */ }
    }
    requirement <'contract.runtime.message_runtime.register.failures'> registerFailureSemantics {
        subject operation : RegisterComponentOccurrence;
        require constraint { doc /* Rejected registration changes neither durable identity nor the routable occurrence set. */ }
    }
    requirement <'contract.runtime.message_runtime.topology.failures'> topologyFailureSemantics {
        subject operation : ConfirmStaticRuntimeTopology;
        require constraint { doc /* A missing, extra, or changed occurrence, binding/version, configuration reference, replay authority, curated operation, or manifest schema version rejects application exposure and does not reinterpret durable identity. Every curated operation must resolve to an exact action and schema on an attached target adapter. The full application manifest hash may advance when this topology hash is unchanged, and the newly confirmed manifest hash is recorded. */ }
    }
    requirement <'contract.runtime.message_runtime.topology_prepare.failures'> topologyPreparationFailureSemantics {
        subject operation : PrepareStaticRuntimeTopology;
        require constraint { doc /* An invalid or changed plan is rejected before occurrence insertion; append failure leaves no partially prepared replacement plan. */ }
    }
    requirement <'contract.runtime.message_runtime.send.failures'> sendFailureSemantics {
        subject operation : SendRuntimeMessage;
        require constraint { doc /* Messages with an unresolved or non-local source or target, other invalid envelopes, and messages whose durable append fails are rejected before component dispatch. */ }
    }
    requirement <'contract.runtime.message_runtime.request.failures'> requestFailureSemantics {
        subject operation : RequestRuntimeMessage;
        require constraint { doc /* A caller timeout does not cancel accepted delivery; validation and append failures have no component effect. */ }
    }
    requirement <'contract.runtime.message_runtime.history.failures'> historyFailureSemantics {
        subject operation : QueryRuntimeHistory;
        require constraint { doc /* History query success and failure never change canonical business history. */ }
    }
    requirement <'contract.runtime.message_runtime.trace.failures'> traceFailureSemantics {
        subject operation : GetRuntimeCausalTrace;
        require constraint { doc /* Causal trace reads return immutable facts and never change canonical business history. */ }
    }
    requirement <'contract.runtime.message_runtime.reconstruct.failures'> reconstructFailureSemantics {
        subject operation : ReconstructRuntimeState;
        require constraint { doc /* Non-empty targets without explicit reset authority, incompatible checkpoints or effects, failed initial digest checks, and unresolved external modes are rejected before an unsafe effect; effects are never applied through an unverified codec or binding. */ }
    }
    requirement <'contract.runtime.message_runtime.branch.failures'> branchFailureSemantics {
        subject operation : RecordRuntimeBranchProvenance;
        require constraint { doc /* Provenance without a pending verified historical reconstruction, mismatched identity/cursor/digest, changed or unavailable state, and persistence failure never open ordinary ingress. */ }
    }

    part runtimeContractContext {
        part runtime : MessageRuntime;
        satisfy durableBeforeDispatch by runtime;
        satisfy durableIdentity by runtime;
        satisfy staticTopologyAtomicity by runtime;
        satisfy boundedOccurrenceOrdering by runtime;
        satisfy messageDeduplication by runtime;
        satisfy terminalPersistenceFailStop by runtime;
        satisfy terminalCausality by runtime;
        satisfy recoveryIngress by runtime;
        satisfy canonicalEffectReplay by runtime;
        satisfy verifiedHistoricalBranching by runtime;
        satisfy registerFailureSemantics by runtime.registerOccurrence;
        satisfy topologyPreparationFailureSemantics by runtime.prepareStaticTopology;
        satisfy topologyFailureSemantics by runtime.confirmStaticTopology;
        satisfy sendFailureSemantics by runtime.'send';
        satisfy requestFailureSemantics by runtime.request;
        satisfy historyFailureSemantics by runtime.queryHistory;
        satisfy traceFailureSemantics by runtime.getTrace;
        satisfy reconstructFailureSemantics by runtime.reconstruct;
        satisfy branchFailureSemantics by runtime.recordBranchProvenance;
    }

    verification def MessageRuntimeBoundaryVerification {
        subject runtime : MessageRuntime;
        objective { verify durableBeforeDispatch; verify durableIdentity; verify staticTopologyAtomicity; verify boundedOccurrenceOrdering; verify messageDeduplication; verify terminalPersistenceFailStop; verify terminalCausality; verify recoveryIngress; verify canonicalEffectReplay; verify verifiedHistoricalBranching; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#MessageRuntimeBoundaryVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RegisterComponentOccurrenceContractVerification {
        subject operation : RegisterComponentOccurrence;
        objective { verify registerFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RegisterComponentOccurrenceContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def PrepareStaticRuntimeTopologyContractVerification {
        subject operation : PrepareStaticRuntimeTopology;
        objective { verify topologyPreparationFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#PrepareStaticRuntimeTopologyContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ConfirmStaticRuntimeTopologyContractVerification {
        subject operation : ConfirmStaticRuntimeTopology;
        objective { verify topologyFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#ConfirmStaticRuntimeTopologyContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def SendRuntimeMessageContractVerification {
        subject operation : SendRuntimeMessage;
        objective { verify sendFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#SendRuntimeMessageContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RequestRuntimeMessageContractVerification {
        subject operation : RequestRuntimeMessage;
        objective { verify requestFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RequestRuntimeMessageContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def QueryRuntimeHistoryContractVerification {
        subject operation : QueryRuntimeHistory;
        objective { verify historyFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#QueryRuntimeHistoryContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def GetRuntimeCausalTraceContractVerification {
        subject operation : GetRuntimeCausalTrace;
        objective { verify traceFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeCausalTraceContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def ReconstructRuntimeStateContractVerification {
        subject operation : ReconstructRuntimeState;
        objective { verify reconstructFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#ReconstructRuntimeStateContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RecordRuntimeBranchProvenanceContractVerification {
        subject operation : RecordRuntimeBranchProvenance;
        objective { verify branchFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RecordRuntimeBranchProvenanceContractVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
}
