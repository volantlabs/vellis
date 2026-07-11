package SoftwareComponentPattern {
    private import SoftwareComponentModeling::*;
    private import ScalarValues::*;

    attribute def RequestValue {
        attribute value : String;
    }

    attribute def ResponseValue {
        attribute value : String;
    }

    item def WorkMessage {
        attribute correlationId : String;
        attribute payload : RequestValue;
    }

    item def DurableQueue { doc /* An independently durable external resource used only by the fixture. */ }

    constraint def MatchingResponse {
        in request : RequestValue;
        in response : ResponseValue;
        request.value == response.value
    }

    action def ProcessRequest {
        in request : RequestValue;
        out response : ResponseValue;
        doc /* Produce a response with the same value as a valid request. */
        @FailureContract {
            errorIds = ("foundation.error.request_invalid");
            obligation = "Invalid requests fail without a partial response.";
        }
    }

    action def DispatchMessage {
        in message : WorkMessage;
        out accepted : Boolean;
        doc /* Submit one message to the configured durable queue and report acceptance. */
    }

    part def Provider {
        derived attribute cachedResponse : ResponseValue {
            doc /* Ephemeral response cache derived from the most recent successful processing. */
        }
        ref item queue : DurableQueue {
            doc /* Independently durable queue referenced, but not lifecycle-owned, by the provider. */
        }
        perform action processRequest[0..*] : ProcessRequest;
        perform action dispatch[0..*] : DispatchMessage;
        dependency processCache from processRequest to cachedResponse {
            doc /* cache the most recent successful response. */
        }
        dependency dispatchQueue from dispatch to queue {
            doc /* submit one message to the external queue. */
        }
    }

    action def OpenProvider {
        in ref queue : DurableQueue;
        out part provider : Provider;
        doc /* Construct a provider that refers to the supplied independently existing queue. */
        bind provider.queue = queue;
    }

    part def Consumer {
        ref part provider[1] : Provider;
    }

    part def ExampleApplication {
        part consumer : Consumer;
        part provider : Provider;

        bind consumer.provider = provider;
    }

    part def ExternalActor { doc /* A system-external participant in the fixture use case. */ }

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
        action process : ProcessRequest;
    }

    requirement <'contract.foundation.process_request'> processRequestRequirement {
        subject application : ExampleApplication;
        doc /* The application shall use a compatible provider for each requested process. */
    }

    verification def ProcessRequestVerification {
        subject application : ExampleApplication;
        objective {
            verify processRequestRequirement;
        }
        @EvidenceBinding {
            verificationId = "verification.foundation.process_request";
            evidenceId = "tests/test_sysml_model.py";
            implementationScope = "model-profile";
        }
    }

    part def PythonProvider :> Provider {
        @ImplementationBinding {
            language = ImplementationLanguage::python;
            codeRoot = "tools";
            symbol = "model_tool.main";
            realization = "modeling-fixture-only";
        }
    }

    part logicalProvider : Provider;
    part pythonProvider : PythonProvider;
    allocate logicalProvider to pythonProvider;
}
