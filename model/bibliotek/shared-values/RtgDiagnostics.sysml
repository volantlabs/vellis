library package BibliotekRtgDiagnostics {
    private import BibliotekSoftwareValues::*;
    private import ScalarValues::*;

    attribute def RtgDiagnostic {
        attribute code : String;
        attribute category : String;
        attribute problem : String;
        attribute remedy : String;
        attribute path[0..1] : String;
        attribute acceptedFields[0..*] : String;
        attribute minimalExample[0..1] : JsonObject;
        attribute guideTopics[0..*] : String;
        attribute safeToRetry : Boolean = true;
        attribute mutationState : String = "not_mutated";
        doc /* Generic JSON-safe corrective guidance. code is stable within its owning contract; category groups the problem; optional fields refine location, accepted shape, examples, workflow guidance, retry safety, and the observable mutation outcome. */
    }
}
