library package BibliotekRuntimeMessaging {
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
        enum indeterminate;
    }
    enum def RuntimeHealth {
        enum starting;
        enum ready;
        enum quiescing;
        enum reconstructing;
        enum recovery_required;
        enum branch_pending;
        enum fail_stopped;
        enum closing;
        enum closed;
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
    enum def RuntimeActionIdempotency {
        enum idempotent;
        enum non_idempotent;
        enum unspecified;
    }
    enum def RuntimeConsistencyAccess {
        enum independent;
        enum shared;
        enum exclusive;
    }
    enum def RuntimePayloadDisposition {
        enum command;
        enum query_result;
        enum diagnostic;
        enum canonical_delta;
        enum state_transfer;
        enum external_document;
    }

    attribute def RuntimeError { attribute 'message' : String; }
    attribute def RuntimeRegistrationInvalid :> RuntimeError;
    attribute def RuntimeAddressUnknown :> RuntimeError;
    attribute def RuntimeActionUnknown :> RuntimeError;
    attribute def RuntimeSchemaUnsupported :> RuntimeError;
    attribute def RuntimeMessageConflict :> RuntimeError;
    attribute def RuntimeQueueFull :> RuntimeError;
    attribute def RuntimeLedgerUnavailable :> RuntimeError;
    attribute def RuntimeFailStopped :> RuntimeError;
    attribute def RuntimeRequestTimedOut :> RuntimeError { attribute messageId : Uuid; }
    attribute def RuntimeRequestIndeterminate :> RuntimeError { attribute messageId : Uuid; }
    attribute def RuntimeDeliveryUnknown :> RuntimeError;
    attribute def RuntimeReplayIncompatible :> RuntimeError;
    attribute def RuntimeReplayTargetNotPrepared :> RuntimeReplayIncompatible;
    attribute def RuntimeStorageVersionUnsupported :> RuntimeError;

    attribute def RuntimeAddress {
        attribute runtimeId : Uuid;
        attribute instanceId : Uuid;
        doc /* Durable exact address. A readable occurrence key is resolved before an envelope is accepted. */
    }
    attribute def RuntimePayload {
        attribute contentType : String default = "application/json";
        attribute codecId : String;
        attribute codecVersion : Integer;
        attribute value : JsonValue;
        doc /* Canonical versioned, serializable payload. Live handles, callables, connections, and credentials are not payload values. */
    }
    attribute def ActionRef {
        attribute componentContractId : String;
        attribute actionId : String;
        attribute schemaVersion : Integer;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute requestCodecId : String;
        attribute requestCodecVersion : Integer;
        attribute requestPayloadDisposition : RuntimePayloadDisposition;
        attribute resultPayloadDisposition : RuntimePayloadDisposition;
        attribute faultPayloadDisposition : RuntimePayloadDisposition;
        attribute effectPayloadDisposition[0..1] : RuntimePayloadDisposition;
        attribute requestCodecId : String;
        attribute requestCodecVersion : Integer default = 1;
        attribute requestContentType : String default = "application/json";
        doc /* Stable message-oriented reference to one registered logical action and its request codec. */
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
    }
    attribute def RuntimeLaneDeclaration {
        attribute name : String;
        attribute queueCapacity : Integer default = 128;
        attribute workerLimit : Integer default = 1;
    }
    attribute def ComponentOccurrenceDeclaration {
        attribute instanceKey : String;
        attribute componentContractId : String;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute lanes[1..*] : RuntimeLaneDeclaration;
        attribute replayAuthority : RuntimeReplayMode default = RuntimeReplayMode::no_state_effect;
        attribute configurationReferences[0..*] : String;
    }
    attribute def ComponentOccurrenceRegistration {
        attribute instanceKey : String;
        attribute instanceId : Uuid;
        attribute componentContractId : String;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute lanes[1..*] : RuntimeLaneDeclaration;
        attribute replayAuthority : RuntimeReplayMode;
        attribute configurationReferences[0..*] : String;
    }
    attribute def RuntimeCuratedOperationDeclaration {
        attribute operationId : String;
        attribute targetInstanceKey : String;
        attribute componentContractId : String;
        attribute actionId : String;
        attribute schemaVersion : Integer;
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute requestCodecId : String;
        attribute requestCodecVersion : Integer;
        attribute requestPayloadDisposition : RuntimePayloadDisposition;
        attribute resultPayloadDisposition : RuntimePayloadDisposition;
        attribute faultPayloadDisposition : RuntimePayloadDisposition;
        attribute effectPayloadDisposition[0..1] : RuntimePayloadDisposition;
    }
    attribute def RuntimeTopologyManifest {
        attribute manifestSchemaVersion : Integer;
        attribute runtimeKey : String;
        attribute occurrences[1..*] : ComponentOccurrenceDeclaration;
        attribute curatedOperations[0..*] : RuntimeCuratedOperationDeclaration;
        attribute manifestHash : String;
        attribute curatedRegistrationDigest[0..1] : String;
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
        attribute terminalPosition[0..1] : Integer;
        attribute traceDisposition[0..1] : RuntimeTraceDisposition;
    }
    attribute def RuntimeRequestOutcome {
        attribute request : RuntimeMessageReceipt;
        ref item response : RuntimeMessageEnvelope;
        attribute terminalPosition : Integer;
        attribute traceDisposition : RuntimeTraceDisposition;
    }
    attribute def RuntimeMessageOutcome {
        ref item requestEnvelope : RuntimeMessageEnvelope;
        attribute requestReceipt : RuntimeMessageReceipt;
        ref item terminalEnvelope[0..1] : RuntimeMessageEnvelope;
        attribute terminalReceipt[0..1] : RuntimeMessageReceipt;
        doc /* Trusted durable observation of one accepted request and its correlated terminal envelope, when available. Reading an outcome creates no runtime traffic. */
    }
    attribute def RuntimeCanonicalEffectReference {
        attribute requestMessageId : Uuid;
        attribute effectDigest : String;
        doc /* Immutable reference to one recorded canonical effect produced by a completed causal descendant. */
    }
    attribute def RuntimeArgumentDescriptor {
        attribute name : String;
        attribute required : Boolean;
        attribute 'default'[0..1] : JsonValue;
        attribute schema : JsonObject;
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
        attribute consistencyGroup[0..1] : String;
        attribute consistencyAccess : RuntimeConsistencyAccess default = RuntimeConsistencyAccess::independent;
        attribute deadlineSeconds[0..1] : Real;
        attribute replayMode : RuntimeReplayMode;
        attribute canonicalEffectSchemaVersion[0..1] : Integer;
        attribute canonicalEffectCodecId[0..1] : String;
        attribute canonicalEffectCodecVersion[0..1] : Integer;
        attribute modeledFaultTraceDisposition : RuntimeTraceDisposition default = RuntimeTraceDisposition::aborted;
        attribute externallyEffectful : Boolean default = false;
        attribute recoveryAuthorized : Boolean default = false;
        attribute requestPayloadDisposition : RuntimePayloadDisposition default = RuntimePayloadDisposition::command;
        attribute resultPayloadDisposition : RuntimePayloadDisposition default = RuntimePayloadDisposition::query_result;
        attribute faultPayloadDisposition : RuntimePayloadDisposition default = RuntimePayloadDisposition::diagnostic;
        attribute effectPayloadDisposition[0..1] : RuntimePayloadDisposition;
        attribute requestSchema : JsonObject;
        attribute resultSchema : JsonObject;
        attribute faultSchema : JsonObject;
        doc /* Generated action metadata contains no component-purpose, handler-kind, saga, controller, store, façade, or gateway discriminator. */
    }
    attribute def RuntimeBindingDescription {
        attribute bindingId : String;
        attribute bindingVersion : Integer;
        attribute componentContractId : String;
        attribute actions[0..*] : RuntimeActionBindingDescriptor;
    }

    port def RuntimeMessagePort {
        in item inbound[0..*] : RuntimeMessageEnvelope;
        out item outbound[0..*] : RuntimeMessageEnvelope;
    }
    interface def RuntimeMessageExchange {
        end participant : ~RuntimeMessagePort;
        end runtime : RuntimeMessagePort;
        flow participant.outbound to runtime.inbound;
        flow runtime.outbound to participant.inbound;
    }
    part def RuntimeParticipant {
        doc /* Minimal runtime-facing participation contract. It classifies neither the adapted component nor its behavior. */
        port messages : ~RuntimeMessagePort;
    }

    doc /*
     * The language-neutral message vocabulary shared by a runtime and every attached
     * participant. It owns no component-purpose taxonomy. Component roles and
     * orchestration styles are expressed by ordinary logical contracts and action
     * behavior, never by fields in this kernel.
     */
}
