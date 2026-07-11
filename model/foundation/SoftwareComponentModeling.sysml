library package SoftwareComponentModeling {
    private import ScalarValues::*;

    doc /*
     * Native-first conventions for modeling reusable software components and
     * applications. These metadata definitions add governance and traceability;
     * they do not change the semantics of the SysML elements they annotate.
     */

    enum def SpecLifecycle {
        enum draft;
        enum accepted;
        enum deprecated;
        enum retired;
    }

    enum def ImplementationLanguage {
        enum python;
        enum external;
        enum unimplemented;
    }

    metadata def SpecificationStatus {
        attribute lifecycleStatus : SpecLifecycle;
        attribute owner : String;
        doc /* Human governance status only; model identity is carried by the element's SysML short name. */
    }

    metadata def FailureContract {
        attribute errorIds[0..*] : String;
        attribute obligation : String;
    }

    metadata def ImplementationBinding {
        attribute language : ImplementationLanguage;
        attribute codeRoot : String;
        attribute symbol : String;
        attribute realization : String;
    }

    metadata def EvidenceBinding {
        attribute verificationId : String;
        attribute evidenceId : String;
        attribute implementationScope : String;
    }

}
