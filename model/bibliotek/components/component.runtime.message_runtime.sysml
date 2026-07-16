library package BibliotekRuntimeMessageRuntime {
    private import SoftwareComponentModeling::*;
    private import BibliotekSoftwareValues::*;
    public import BibliotekRuntimeMessaging::*;
    private import ScalarValues::*;

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
        attribute includePayload : Boolean default = false;
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
    attribute def RuntimeTraceSummary {
        attribute traceId : Uuid;
        attribute rootMessageId : Uuid;
        attribute rootActionId : String;
        attribute terminalPosition : Integer;
        attribute disposition : RuntimeTraceDisposition;
    }
    attribute def RuntimeTraceSummaryPage {
        attribute summaries[0..*] : RuntimeTraceSummary;
        attribute nextPosition[0..1] : Integer;
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
        attribute checkpointReferences[0..1] : JsonObject;
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
    }

    action def PrepareStaticRuntimeTopology {
        in manifest : RuntimeTopologyManifest;
        doc /* Durably fix the complete static occurrence plan before inserting an occurrence. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def RegisterComponentOccurrence {
        in declaration : ComponentOccurrenceDeclaration;
        out resolvedRegistration : ComponentOccurrenceRegistration;
        doc /* Allocate the first durable incarnation or reuse its exact matching identity after restart. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def AttachRuntimeParticipant {
        in registration : ComponentOccurrenceRegistration;
        in part participant : RuntimeParticipant;
        in actions[0..*] : RuntimeActionBindingDescriptor;
        doc /* Attach one conforming participant and its explicit action inventory to one registered occurrence. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeFailStopped"); }
    }
    action def ConfirmStaticRuntimeTopology {
        in manifest : RuntimeTopologyManifest;
        out confirmation : RuntimeTopologyConfirmation;
        doc /* Open ingress only after every declared occurrence has a participant and every curated operation resolves exactly. */
        @FailureContract { errorIds = ("RuntimeRegistrationInvalid", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def SendRuntimeMessage {
        in 'message' : RuntimeMessageEnvelope;
        out receipt : RuntimeMessageReceipt;
        doc /* Durably accept and schedule one envelope. Requests, responses, faults, and signals use this same path. */
        @FailureContract { errorIds = ("RuntimeAddressUnknown", "RuntimeActionUnknown", "RuntimeSchemaUnsupported", "RuntimeMessageConflict", "RuntimeQueueFull", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def CompleteRuntimeDelivery {
        in requestMessageId : Uuid;
        in result : RuntimePayload;
        in canonicalEffect[0..1] : JsonObject;
        out receipt : RuntimeMessageReceipt;
        doc /* Exactly once, close one delivering request and atomically record and create its correlated response envelope. */
        @FailureContract { errorIds = ("RuntimeDeliveryUnknown", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def FaultRuntimeDelivery {
        in requestMessageId : Uuid;
        in error : RuntimePayload;
        in traceDisposition : RuntimeTraceDisposition;
        in canonicalEffect[0..1] : JsonObject;
        out receipt : RuntimeMessageReceipt;
        doc /* Exactly once, close one delivering request and atomically record and create its correlated fault envelope. */
        @FailureContract { errorIds = ("RuntimeDeliveryUnknown", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def AcknowledgeRuntimeDelivery {
        in messageId : Uuid;
        in canonicalEffect[0..1] : JsonObject;
        out receipt : RuntimeMessageReceipt;
        doc /* Exactly once, close a delivered signal, response, or fault. */
        @FailureContract { errorIds = ("RuntimeDeliveryUnknown", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def QueryRuntimeHistory {
        in query : RuntimeHistoryQuery;
        out page : RuntimeHistoryPage;
        doc /* Return deterministic cursor-paginated immutable facts without creating business traffic. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def CountRuntimeHistory {
        in query : RuntimeHistoryQuery;
        out count : Integer;
        doc /* Count matching immutable facts through database aggregation without hydrating facts or payloads. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def QueryRuntimeTraceSummaries {
        in afterPosition[0..1] : Integer;
        in limit : Integer default = 100;
        in newestFirst : Boolean default = false;
        in rootActionIds[0..*] : String;
        out page : RuntimeTraceSummaryPage;
        doc /* Return bounded terminal root-trace metadata without hydrating causal facts or payloads. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def GetRuntimeCausalTrace {
        in traceId : Uuid;
        in includePayload : Boolean default = false;
        out trace : RuntimeCausalTrace;
        doc /* Return the ordered facts and terminal disposition of one causal trace. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def GetRuntimeMessageEnvelope {
        in messageId : Uuid;
        out envelope[0..1] : RuntimeMessageEnvelope;
        doc /* Explicitly hydrate one durable envelope by identity without creating traffic. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def LookupRuntimeMessageOutcome {
        in messageId : Uuid;
        out outcome[0..1] : RuntimeMessageOutcome;
        doc /* Read the durable request and correlated terminal state for one message without creating traffic or retaining an in-memory result cache. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def ReconstructRuntimeState {
        in request : RuntimeReconstructionRequest;
        out report : RuntimeReconstructionReport;
        doc /* Apply only committed canonical effects without creating new business traffic or repeating external exchanges. */
        @FailureContract { errorIds = ("RuntimeReplayIncompatible", "RuntimeReplayTargetNotPrepared", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def RecordRuntimeBranchProvenance {
        in sourceRuntimeId : Uuid;
        in sourceCursor : Integer;
        in verifiedDigest : String;
        out runtimePosition : Integer;
        doc /* Recheck and record source identity, selected cursor, and verified digest before opening a historical branch. */
        @FailureContract { errorIds = ("RuntimeReplayIncompatible", "RuntimeReplayTargetNotPrepared", "RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def GetRuntimeHealth {
        out health : RuntimeHealth;
        doc /* Return runtime readiness without creating message traffic. */
        @FailureContract { errorIds = (); }
    }
    action def AddressForRuntimeOccurrence {
        in instanceKey : String;
        out address : RuntimeAddress;
        doc /* Resolve one declared readable occurrence key to its durable exact address. */
        @FailureContract { errorIds = ("RuntimeAddressUnknown"); }
    }
    action def GetCurrentRuntimePosition {
        out runtimePosition : Integer;
        doc /* Return the latest confirmed runtime ledger position. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable", "RuntimeFailStopped"); }
    }
    action def AcloseMessageRuntime {
        doc /* Quiesce deliveries, record orderly shutdown when possible, and close the local execution host. */
        @FailureContract { errorIds = ("RuntimeLedgerUnavailable"); }
    }

    part def <'component.runtime.message_runtime'> MessageRuntime {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::accepted; owner = "humans"; }
        doc /* Durable local message boundary. It knows participant addresses, binding metadata, lanes, envelopes, and chronology, but no component purpose or business role. Its participant surface is message send/delivery/completion; trusted history and reconstruction actions form a separate operator surface. */
        attribute runtimeId : Uuid;
        attribute runtimeKey : String;
        attribute occurrenceRegistry : JsonObject;
        attribute staticTopologyPlan : JsonObject;
        attribute openDeliveries : JsonObject;
        attribute health : RuntimeHealth;
        derived attribute currentPosition : Integer;
        port messages : RuntimeMessagePort;
        perform action prepareStaticTopology[0..*] : PrepareStaticRuntimeTopology { doc /* Persist the static plan. */ }
        perform action registerOccurrence[0..*] : RegisterComponentOccurrence { doc /* Persist one occurrence identity. */ }
        perform action attachParticipant[0..*] : AttachRuntimeParticipant { doc /* Attach one participant and action inventory. */ }
        perform action confirmStaticTopology[0..*] : ConfirmStaticRuntimeTopology { doc /* Confirm and expose the complete topology. */ }
        perform action 'send'[0..*] : SendRuntimeMessage { doc /* Record and schedule an envelope. */ }
        perform action completeDelivery[0..*] : CompleteRuntimeDelivery { doc /* Record completion and emit its response. */ }
        perform action faultDelivery[0..*] : FaultRuntimeDelivery { doc /* Record fault and emit its fault envelope. */ }
        perform action acknowledgeDelivery[0..*] : AcknowledgeRuntimeDelivery { doc /* Record terminal acknowledgement. */ }
        perform action queryHistory[0..*] : QueryRuntimeHistory { doc /* Read immutable chronology. */ }
        perform action countHistory[0..*] : CountRuntimeHistory { doc /* Aggregate immutable chronology. */ }
        perform action queryTraceSummaries[0..*] : QueryRuntimeTraceSummaries { doc /* Read bounded terminal trace metadata. */ }
        perform action getTrace[0..*] : GetRuntimeCausalTrace { doc /* Read one causal trace. */ }
        perform action getEnvelope[0..*] : GetRuntimeMessageEnvelope { doc /* Explicitly hydrate one durable envelope. */ }
        perform action lookupOutcome[0..*] : LookupRuntimeMessageOutcome { doc /* Read one durable message outcome. */ }
        perform action reconstruct[0..*] : ReconstructRuntimeState { doc /* Apply selected canonical effects. */ }
        perform action recordBranchProvenance[0..*] : RecordRuntimeBranchProvenance { doc /* Record verified branch provenance. */ }
        perform action getHealth[0..*] : GetRuntimeHealth { doc /* Read runtime health. */ }
        perform action resolveAddress[0..*] : AddressForRuntimeOccurrence { doc /* Read one durable address resolution. */ }
        perform action getCurrentPosition[0..*] : GetCurrentRuntimePosition { doc /* Read chronology position. */ }
        perform action close[0..*] : AcloseMessageRuntime { doc /* Close the execution host. */ }
        dependency preparedTopology from prepareStaticTopology to staticTopologyPlan { @StateAccess { kind = StateAccessKind::write; } }
        dependency registeredOccurrence from registerOccurrence to occurrenceRegistry { @StateAccess { kind = StateAccessKind::write; } }
        dependency attachedOccurrence from attachParticipant to occurrenceRegistry { @StateAccess { kind = StateAccessKind::write; } }
        dependency confirmedTopology from confirmStaticTopology to staticTopologyPlan { @StateAccess { kind = StateAccessKind::read; } }
        dependency acceptedHistory from 'send' to currentPosition { @StateAccess { kind = StateAccessKind::write; } }
        dependency openedDelivery from 'send' to openDeliveries { @StateAccess { kind = StateAccessKind::write; } }
        dependency completedHistory from completeDelivery to currentPosition { @StateAccess { kind = StateAccessKind::write; } }
        dependency faultedHistory from faultDelivery to currentPosition { @StateAccess { kind = StateAccessKind::write; } }
        dependency acknowledgedHistory from acknowledgeDelivery to currentPosition { @StateAccess { kind = StateAccessKind::write; } }
        dependency completedDelivery from completeDelivery to openDeliveries { @StateAccess { kind = StateAccessKind::write; } }
        dependency faultedDelivery from faultDelivery to openDeliveries { @StateAccess { kind = StateAccessKind::write; } }
        dependency acknowledgedDelivery from acknowledgeDelivery to openDeliveries { @StateAccess { kind = StateAccessKind::write; } }
        dependency queriedHistory from queryHistory to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency countedHistory from countHistory to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency summarizedHistory from queryTraceSummaries to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency tracedHistory from getTrace to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency envelopeHistory from getEnvelope to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency outcomeHistory from lookupOutcome to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency replayedHistory from reconstruct to currentPosition { @StateAccess { kind = StateAccessKind::read; } }
        dependency branchedHistory from recordBranchProvenance to currentPosition { @StateAccess { kind = StateAccessKind::write; } }
        dependency healthState from getHealth to health { @StateAccess { kind = StateAccessKind::read; } doc /* Read readiness without mutation. */ }
        dependency addressRegistry from resolveAddress to occurrenceRegistry { @StateAccess { kind = StateAccessKind::read; } doc /* Resolve only an existing durable identity. */ }
        dependency positionState from getCurrentPosition to currentPosition { @StateAccess { kind = StateAccessKind::read; } doc /* Read the latest ledger cursor. */ }
        dependency closeState from close to health { @StateAccess { kind = StateAccessKind::write; } doc /* Transition the local host to closed. */ }
    }

    requirement <'contract.runtime.message_runtime.uniform_delivery'> uniformDurableDelivery {
        subject runtime : MessageRuntime;
        require constraint { doc /* Every envelope kind is durably accepted before delivery. Responses and faults are scheduled to the requester's independently available response lane; there is no runtime request future or special response return path. */ }
    }
    requirement <'contract.runtime.message_runtime.completion'> singleCompletionPath {
        subject runtime : MessageRuntime;
        require constraint { doc /* A request remains open until exactly one complete or fault operation records its terminal fact and correlated envelope. Signals, responses, and faults remain open until exactly one acknowledgement. Unknown, wrong-kind, or duplicate closure is rejected. */ }
    }
    requirement <'contract.runtime.message_runtime.causality'> terminalCausality {
        subject runtime : MessageRuntime;
        require constraint { doc /* A trace becomes terminal only after its root and every accepted causal descendant are terminal. Correlation and causation reference accepted messages in that same trace. */ }
    }
    requirement <'contract.runtime.message_runtime.lanes'> laneScheduling {
        subject runtime : MessageRuntime;
        require constraint { doc /* Each declared action lane is bounded FIFO with its own worker limit. No cross-lane or global execution order is promised. The response lane is capacity-exempt and remains deliverable while request workers await collaborators. */ }
    }
    requirement <'contract.runtime.message_runtime.consistency'> declarativeConsistency {
        subject runtime : MessageRuntime;
        require constraint { doc /* Independent actions are ungated. Shared actions in a consistency group may overlap. Exclusive actions use writer-preferring admission, wait for active shared actions, block new shared actions, and remain exclusive through request completion. Admission never reorders a lane. */ }
    }
    requirement <'contract.runtime.message_runtime.identity'> durableIdentity {
        subject runtime : MessageRuntime;
        require constraint { doc /* Runtime and occurrence identities survive restart. Duplicate live keys or UUIDs fail composition. Addresses always include runtime and occurrence UUIDs. */ }
    }
    requirement <'contract.runtime.message_runtime.topology'> staticTopologyAtomicity {
        subject runtime : MessageRuntime;
        require constraint { doc /* The complete manifest is prepared before occurrence insertion. Traffic opens only when every occurrence has exactly one attached participant and curated operations resolve to declared actions. Changed topology requires an explicit migration. */ }
    }
    requirement <'contract.runtime.message_runtime.deduplication'> messageDeduplication {
        subject runtime : MessageRuntime;
        require constraint { doc /* Identical reuse of a message ID observes current or recorded state without re-execution. Reuse with different immutable content is rejected. Delivery attempt identity remains distinct from message identity. */ }
    }
    requirement <'contract.runtime.message_runtime.payload_boundary'> explicitStateTransferBoundary {
        subject runtime : MessageRuntime;
        require constraint { doc /* Complete component state crosses a message boundary only through an explicitly modeled state-transfer or external-document action. Ordinary requests, results, faults, and canonical effects contain commands, targeted reads, deltas, summaries, bounded diagnostics, digests, or opaque durable references. Credentials, live handles, connections, and filesystem capabilities are never durable payload values. */ }
    }
    requirement <'contract.runtime.message_runtime.timeout'> nonCancellingWaitTimeout {
        subject runtime : MessageRuntime;
        require constraint { doc /* A caller or adapter wait timeout does not cancel a handler or imply delivery failure. Late terminal envelopes are still delivered and acknowledged. */ }
    }
    requirement <'contract.runtime.message_runtime.lifecycle'> explicitRuntimeLifecycle {
        subject runtime : MessageRuntime;
        require constraint { doc /* Runtime health is a typed lifecycle. Ready accepts ordinary roots; quiescing accepts only descendants of already-open traces; recovery-required admits one recovery-authorized root and its descendants; reconstructing, branch-pending, fail-stopped, closing, and closed reject ordinary ingress. Every persisted transition is recorded in runtime chronology. */ }
    }
    requirement <'contract.runtime.message_runtime.fail_stop'> persistenceFailStop {
        subject runtime : MessageRuntime;
        require constraint { doc /* Initial append failure prevents dispatch. Terminal persistence failure after possible component effect enters fail-stop, quiesces lanes, marks open deliveries indeterminate where durable recording remains possible, and rejects new traffic. */ }
    }
    requirement <'contract.runtime.message_runtime.recovery'> recoveryAndReplay {
        subject runtime : MessageRuntime;
        require constraint { doc /* Restart marks open deliveries indeterminate. Reconstruction applies only canonical effects whose effect and committed trace-terminal facts are both at or before the selected cursor. A superseding aggregate contains ordered immutable references only; every reference resolves to a same-trace causal descendant with the recorded effect digest, and embedded child payloads are rejected. A checkpoint set names every state owner and represents one common cursor. External exchanges are reported but never invoked. Failed reset, import, replay, digest, or verification leaves recovery required; replay evaluation is not appended as business traffic. */ }
    }
    requirement <'contract.runtime.message_runtime.operator_separation'> operatorSurfaceSeparation {
        subject runtime : MessageRuntime;
        require constraint { doc /* History, trace, health, reconstruction, and branch operations are trusted runtime boundary operations and are never used as component-to-component integration calls or exposed as universal production tools. */ }
    }
    requirement <'contract.runtime.message_runtime.failures'> runtimeFailureSemantics {
        subject runtime : MessageRuntime;
        require constraint { doc /* Invalid topology, address, action, schema, lane capacity, causality, completion, or envelope content causes no component effect. Runtime failures remain distinct from modeled component faults. */ }
    }
    requirement <'contract.runtime.message_runtime.prepare.failures'> prepareTopologyFailureSemantics { subject operation : PrepareStaticRuntimeTopology; require constraint { doc /* Rejection changes neither the prepared plan nor durable occurrences. */ } }
    requirement <'contract.runtime.message_runtime.register.failures'> registerOccurrenceFailureSemantics { subject operation : RegisterComponentOccurrence; require constraint { doc /* Rejection allocates no occurrence identity and changes no registration. */ } }
    requirement <'contract.runtime.message_runtime.attach.failures'> attachParticipantFailureSemantics { subject operation : AttachRuntimeParticipant; require constraint { doc /* Rejection leaves the occurrence unattached and unroutable. */ } }
    requirement <'contract.runtime.message_runtime.confirm.failures'> confirmTopologyFailureSemantics { subject operation : ConfirmStaticRuntimeTopology; require constraint { doc /* Incomplete or inconsistent topology remains closed to traffic. */ } }
    requirement <'contract.runtime.message_runtime.send.failures'> sendMessageFailureSemantics { subject operation : SendRuntimeMessage; require constraint { doc /* Rejection occurs before participant delivery and component effect. */ } }
    requirement <'contract.runtime.message_runtime.complete.failures'> completeDeliveryFailureSemantics { subject operation : CompleteRuntimeDelivery; require constraint { doc /* Unknown or duplicate completion creates no response and does not alter the prior terminal fact. */ } }
    requirement <'contract.runtime.message_runtime.fault.failures'> faultDeliveryFailureSemantics { subject operation : FaultRuntimeDelivery; require constraint { doc /* Unknown or duplicate fault creates no fault envelope and does not alter the prior terminal fact. */ } }
    requirement <'contract.runtime.message_runtime.ack.failures'> acknowledgeDeliveryFailureSemantics { subject operation : AcknowledgeRuntimeDelivery; require constraint { doc /* Unknown or duplicate acknowledgement does not alter the prior terminal fact. */ } }
    requirement <'contract.runtime.message_runtime.history.failures'> queryHistoryFailureSemantics { subject operation : QueryRuntimeHistory; require constraint { doc /* Query failure changes neither ledger nor component state. */ } }
    requirement <'contract.runtime.message_runtime.count_history.failures'> countHistoryFailureSemantics { subject operation : CountRuntimeHistory; require constraint { doc /* Count failure changes neither ledger nor component state. */ } }
    requirement <'contract.runtime.message_runtime.trace_summaries.failures'> traceSummaryFailureSemantics { subject operation : QueryRuntimeTraceSummaries; require constraint { doc /* Summary-query failure changes neither ledger nor component state. */ } }
    requirement <'contract.runtime.message_runtime.trace.failures'> getTraceFailureSemantics { subject operation : GetRuntimeCausalTrace; require constraint { doc /* Trace-read failure changes neither ledger nor component state. */ } }
    requirement <'contract.runtime.message_runtime.envelope.failures'> getEnvelopeFailureSemantics { subject operation : GetRuntimeMessageEnvelope; require constraint { doc /* Unknown identity returns absence; hydration changes neither ledger nor component state. */ } }
    requirement <'contract.runtime.message_runtime.outcome.failures'> lookupOutcomeFailureSemantics { subject operation : LookupRuntimeMessageOutcome; require constraint { doc /* Unknown identity returns absence. Outcome inspection changes neither ledger nor component state. */ } }
    requirement <'contract.runtime.message_runtime.reconstruct.failures'> reconstructStateFailureSemantics { subject operation : ReconstructRuntimeState; require constraint { doc /* Incompatibility is reported and the runtime does not expose an unverified target as ready. */ } }
    requirement <'contract.runtime.message_runtime.branch.failures'> branchProvenanceFailureSemantics { subject operation : RecordRuntimeBranchProvenance; require constraint { doc /* Mismatched or unsolicited provenance never opens ordinary ingress. */ } }
    requirement <'contract.runtime.message_runtime.health.failures'> getHealthFailureSemantics { subject operation : GetRuntimeHealth; require constraint { doc /* Health inspection has no state effect. */ } }
    requirement <'contract.runtime.message_runtime.address.failures'> addressForFailureSemantics { subject operation : AddressForRuntimeOccurrence; require constraint { doc /* Unknown key resolution allocates no identity and changes no routing. */ } }
    requirement <'contract.runtime.message_runtime.position.failures'> currentPositionFailureSemantics { subject operation : GetCurrentRuntimePosition; require constraint { doc /* Position inspection has no state effect. */ } }
    requirement <'contract.runtime.message_runtime.close.failures'> closeRuntimeFailureSemantics { subject operation : AcloseMessageRuntime; require constraint { doc /* Close failure never reports a partially active runtime as ready. */ } }

    part runtimeContractContext {
        part runtime : MessageRuntime;
        satisfy uniformDurableDelivery by runtime;
        satisfy singleCompletionPath by runtime;
        satisfy terminalCausality by runtime;
        satisfy laneScheduling by runtime;
        satisfy declarativeConsistency by runtime;
        satisfy durableIdentity by runtime;
        satisfy staticTopologyAtomicity by runtime;
        satisfy messageDeduplication by runtime;
        satisfy explicitStateTransferBoundary by runtime;
        satisfy nonCancellingWaitTimeout by runtime;
        satisfy explicitRuntimeLifecycle by runtime;
        satisfy persistenceFailStop by runtime;
        satisfy recoveryAndReplay by runtime;
        satisfy operatorSurfaceSeparation by runtime;
        satisfy runtimeFailureSemantics by runtime;
        satisfy prepareTopologyFailureSemantics by runtime.prepareStaticTopology;
        satisfy registerOccurrenceFailureSemantics by runtime.registerOccurrence;
        satisfy attachParticipantFailureSemantics by runtime.attachParticipant;
        satisfy confirmTopologyFailureSemantics by runtime.confirmStaticTopology;
        satisfy sendMessageFailureSemantics by runtime.'send';
        satisfy completeDeliveryFailureSemantics by runtime.completeDelivery;
        satisfy faultDeliveryFailureSemantics by runtime.faultDelivery;
        satisfy acknowledgeDeliveryFailureSemantics by runtime.acknowledgeDelivery;
        satisfy queryHistoryFailureSemantics by runtime.queryHistory;
        satisfy countHistoryFailureSemantics by runtime.countHistory;
        satisfy traceSummaryFailureSemantics by runtime.queryTraceSummaries;
        satisfy getTraceFailureSemantics by runtime.getTrace;
        satisfy getEnvelopeFailureSemantics by runtime.getEnvelope;
        satisfy lookupOutcomeFailureSemantics by runtime.lookupOutcome;
        satisfy reconstructStateFailureSemantics by runtime.reconstruct;
        satisfy branchProvenanceFailureSemantics by runtime.recordBranchProvenance;
        satisfy getHealthFailureSemantics by runtime.getHealth;
        satisfy addressForFailureSemantics by runtime.resolveAddress;
        satisfy currentPositionFailureSemantics by runtime.getCurrentPosition;
        satisfy closeRuntimeFailureSemantics by runtime.close;
    }
    verification def MessageRuntimeBoundaryVerification {
        subject runtime : MessageRuntime;
        objective { verify uniformDurableDelivery; verify singleCompletionPath; verify terminalCausality; verify laneScheduling; verify declarativeConsistency; verify durableIdentity; verify staticTopologyAtomicity; verify messageDeduplication; verify explicitStateTransferBoundary; verify nonCancellingWaitTimeout; verify explicitRuntimeLifecycle; verify persistenceFailStop; verify recoveryAndReplay; verify operatorSurfaceSeparation; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#MessageRuntimeBoundaryVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RuntimeParticipantClosureVerification {
        subject runtime : MessageRuntime;
        objective { verify singleCompletionPath; verify runtimeFailureSemantics; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RuntimeParticipantClosureVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RuntimeTopologyVerification {
        subject runtime : MessageRuntime;
        objective { verify durableIdentity; verify staticTopologyAtomicity; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RuntimeTopologyVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def RuntimeReconstructionVerification {
        subject runtime : MessageRuntime;
        objective { verify recoveryAndReplay; }
        @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RuntimeReconstructionVerification"; implementationScope = "BibliotekRuntimePython"; }
    }
    verification def PrepareStaticRuntimeTopologyContractVerification { subject operation : PrepareStaticRuntimeTopology; objective { verify prepareTopologyFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#PrepareStaticRuntimeTopologyContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def RegisterComponentOccurrenceContractVerification { subject operation : RegisterComponentOccurrence; objective { verify registerOccurrenceFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RegisterComponentOccurrenceContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def AttachRuntimeParticipantContractVerification { subject operation : AttachRuntimeParticipant; objective { verify attachParticipantFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#AttachRuntimeParticipantContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ConfirmStaticRuntimeTopologyContractVerification { subject operation : ConfirmStaticRuntimeTopology; objective { verify confirmTopologyFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#ConfirmStaticRuntimeTopologyContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def SendRuntimeMessageContractVerification { subject operation : SendRuntimeMessage; objective { verify sendMessageFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#SendRuntimeMessageContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def CompleteRuntimeDeliveryContractVerification { subject operation : CompleteRuntimeDelivery; objective { verify completeDeliveryFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#CompleteRuntimeDeliveryContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def FaultRuntimeDeliveryContractVerification { subject operation : FaultRuntimeDelivery; objective { verify faultDeliveryFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#FaultRuntimeDeliveryContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def AcknowledgeRuntimeDeliveryContractVerification { subject operation : AcknowledgeRuntimeDelivery; objective { verify acknowledgeDeliveryFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#AcknowledgeRuntimeDeliveryContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def QueryRuntimeHistoryContractVerification { subject operation : QueryRuntimeHistory; objective { verify queryHistoryFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#QueryRuntimeHistoryContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def CountRuntimeHistoryContractVerification { subject operation : CountRuntimeHistory; objective { verify countHistoryFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#CountRuntimeHistoryContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def QueryRuntimeTraceSummariesContractVerification { subject operation : QueryRuntimeTraceSummaries; objective { verify traceSummaryFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#QueryRuntimeTraceSummariesContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def GetRuntimeCausalTraceContractVerification { subject operation : GetRuntimeCausalTrace; objective { verify getTraceFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeCausalTraceContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def GetRuntimeMessageEnvelopeContractVerification { subject operation : GetRuntimeMessageEnvelope; objective { verify getEnvelopeFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeMessageEnvelopeContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def LookupRuntimeMessageOutcomeContractVerification { subject operation : LookupRuntimeMessageOutcome; objective { verify lookupOutcomeFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#LookupRuntimeMessageOutcomeContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def ReconstructRuntimeStateContractVerification { subject operation : ReconstructRuntimeState; objective { verify reconstructStateFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#ReconstructRuntimeStateContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def RecordRuntimeBranchProvenanceContractVerification { subject operation : RecordRuntimeBranchProvenance; objective { verify branchProvenanceFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#RecordRuntimeBranchProvenanceContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def GetRuntimeHealthContractVerification { subject operation : GetRuntimeHealth; objective { verify getHealthFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetRuntimeHealthContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def AddressForRuntimeOccurrenceContractVerification { subject operation : AddressForRuntimeOccurrence; objective { verify addressForFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#AddressForRuntimeOccurrenceContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def GetCurrentRuntimePositionContractVerification { subject operation : GetCurrentRuntimePosition; objective { verify currentPositionFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#GetCurrentRuntimePositionContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
    verification def AcloseMessageRuntimeContractVerification { subject operation : AcloseMessageRuntime; objective { verify closeRuntimeFailureSemantics; } @EvidenceBinding { evidenceId = "components/runtime/message_runtime/tests/test_message_runtime_contract.py#AcloseMessageRuntimeContractVerification"; implementationScope = "BibliotekRuntimePython"; } }
}
