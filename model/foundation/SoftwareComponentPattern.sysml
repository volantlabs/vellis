package SoftwareComponentPattern {
    private import SoftwareComponentModeling::*;
    private import ScalarValues::*;

    attribute def RequestValue {
        attribute value : String;
    }

    abstract attribute def OperationOutcome;

    attribute def ResponseValue :> OperationOutcome {
        attribute value : String;
    }

    attribute def RejectedOutcome :> OperationOutcome {
        attribute reason : String;
    }

    item def WorkMessage {
        attribute correlationId : String;
        attribute payload : RequestValue;
    }

    item def DurableQueue {
        doc /* An independently durable external resource used only by the fixture. */
    }

    constraint def MatchingResponse {
        in request : RequestValue;
        in response : ResponseValue;
        request.value == response.value
    }

    calc def RequestIsValid {
        in request : RequestValue;
        return valid : Boolean = request.value != "";
    }

    action def ProcessRequest {
        in request : RequestValue;
        out response : ResponseValue;
        doc /* Produce a response for one valid request. */
        @FailureContract {
            errorIds = ("foundation.error.request_invalid");
        }
    }

    action def DispatchMessage {
        in 'message' : WorkMessage;
        out accepted : Boolean;
        doc /* Submit one message to the configured durable queue and report acceptance. */
    }

    part def Provider {
        attribute successfulRequestCount : Integer := 0;
        derived attribute cachedResponse : ResponseValue {
            doc /* Ephemeral response cache derived from the most recent successful processing. */
        }
        ref item queue : DurableQueue {
            doc /* Independently durable queue referenced, but not lifecycle-owned, by the provider. */
        }

        perform action processRequest[0..*] : ProcessRequest {
            assign successfulRequestCount := successfulRequestCount + 1;
        }
        perform action dispatch[0..*] : DispatchMessage;

        dependency processDerivesCache from processRequest to cachedResponse {
            @StateAccess { kind = StateAccessKind::write; }
            doc /* A successful response determines the derived most-recent response view. */
        }
        dependency processWritesCount from processRequest to successfulRequestCount {
            @StateAccess { kind = StateAccessKind::write; }
        }
        dependency dispatchReadsQueue from dispatch to queue {
            @StateAccess { kind = StateAccessKind::read; }
        }
        dependency dispatchPreservesCount from dispatch to successfulRequestCount {
            @StateAccess { kind = StateAccessKind::noStateEffect; }
            doc /* Dispatch does not change request-processing state. */
        }
    }

    action def OpenProvider {
        in ref item queue : DurableQueue;
        out part provider : Provider;
        doc /* Construct a provider that refers to the supplied independently existing queue. */
        bind provider.queue = queue;
    }

    part def Consumer {
        ref part provider[1] : Provider;
    }

    action def ServeRequest {
        in request : RequestValue;
        out response : ResponseValue;
    }

    part def ExampleApplication {
        part consumer : Consumer;
        part provider : Provider {
            perform serve.invokeProvider;
        }

        bind consumer.provider = provider;

        action serve : ServeRequest {
            action invokeProvider : ProcessRequest {
                in request redefines ProcessRequest::request = serve.request;
                out response redefines ProcessRequest::response = serve.response;
            }
        }

    }

    part def ExternalActor {
        doc /* A system-external participant in the fixture use case. */
    }

    use case def ProcessRequestUseCase {
        subject application : ExampleApplication;
        actor requester : ExternalActor;
        objective {
            doc /* The requester receives a response for a valid request. */
        }
    }

    use case processRequestUseCase : ProcessRequestUseCase {
        subject application;
        actor requester;
        action process : ServeRequest;
    }


    requirement <'contract.foundation.process_request'> processRequestRequirement {
        subject operation : ProcessRequest;
        assume constraint {
            RequestIsValid(operation.request)
        }
        require constraint matchingResponse : MatchingResponse {
            in request = operation.request;
            in response = operation.response;
        }
    }


    requirement <'contract.foundation.process_request_failure'> processRequestFailureSemantics {
        subject operation : ProcessRequest;
        require constraint {
            doc /* An invalid request reports foundation.error.request_invalid and produces no partial response. */
        }
    }

    requirement <'invariant.foundation.provider_count'> providerCountRequirement {
        subject provider : Provider;
        require constraint {
            doc /* The successful request count changes only after successful processing and never decreases. */
        }
    }

    part contractContext {
        part provider : Provider;
        satisfy processRequestRequirement by provider.processRequest;
        satisfy processRequestFailureSemantics by provider.processRequest;
        satisfy providerCountRequirement by provider;
    }

    verification def ProcessRequestVerification {
        subject operation : ProcessRequest;
        objective {
            verify processRequestRequirement;
            verify processRequestFailureSemantics;
        }
        @EvidenceBinding {
            evidenceId = "tests/test_sysml_model.py::test_foundation_native_semantics#ProcessRequestVerification";
            implementationScope = "model-profile";
        }
    }

    verification def ProviderVerification {
        subject provider : Provider;
        objective {
            verify providerCountRequirement;
        }
        @EvidenceBinding {
            evidenceId = "tests/test_sysml_model.py::test_foundation_native_semantics#ProviderVerification";
            implementationScope = "model-profile";
        }
    }

    part def PythonProvider :> Provider {
        @ImplementationBinding {
            implementationLanguage = ImplementationLanguage::python;
            codeRoot = "tools";
            symbol = "model_tool.main";
            realization = "modeling-fixture-only";
        }
    }

    part logicalProvider : Provider;
    part pythonProvider : PythonProvider;
    allocate logicalProvider to pythonProvider;
}
