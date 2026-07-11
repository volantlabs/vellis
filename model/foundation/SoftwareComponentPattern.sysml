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
        @FailureContract {
            errorIds = ("foundation.error.request_invalid");
            obligation = "Invalid requests fail without a partial response.";
        }
    }

    action def DispatchMessage {
        in message : WorkMessage;
        out accepted : Boolean;
    }

    part def Provider {
        attribute cachedResponse : ResponseValue {
            @StateAuthority {
                authority = StateAuthorityKind::derived;
                lifetime = StateLifetime::componentCoupled;
                persistence = StatePersistence::ephemeral;
            }
        }
        ref item queue : DurableQueue {
            @StateAuthority {
                authority = StateAuthorityKind::externalReference;
                lifetime = StateLifetime::independent;
                persistence = StatePersistence::durable;
            }
        }
        perform action processRequest[0..*] : ProcessRequest;
        perform action dispatch[0..*] : DispatchMessage;
        dependency processCache from processRequest to cachedResponse {
            @StateAccess { kind = StateAccessKind::write; effect = "cache the most recent successful response"; }
        }
        dependency dispatchQueue from dispatch to queue {
            @StateAccess { kind = StateAccessKind::write; effect = "submit one message to the external queue"; }
        }
    }

    action def OpenProvider {
        in queue : DurableQueue;
        out part provider : Provider;
    }

    part def Consumer {
        ref action requiredProcessRequest[0..*] : ProcessRequest {
            @RequiredCapability {
                providerLowerBound = 1;
                providerUpperBound = 1;
            }
        }
    }

    part def ExampleApplication {
        part consumer : Consumer;
        part provider : Provider;

        dependency processRequestSatisfaction
            from consumer.requiredProcessRequest
            to provider.processRequest {
            @ContractSatisfaction;
        }
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

    requirement processRequestRequirement {
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
