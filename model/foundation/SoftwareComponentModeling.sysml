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

    enum def StateAccessKind {
        enum read;
        enum create;
        enum write;
        enum delete;
        enum noStateEffect;
    }

    metadata def SpecificationStatus {
        :> annotatedElement : SysML::PartDefinition;
        attribute lifecycleStatus : SpecLifecycle;
        attribute owner : String;
        doc /* Human governance status only; model identity is carried by the element's SysML short name. */
    }

    metadata def FailureContract {
        :> annotatedElement : SysML::ActionDefinition;
        :> annotatedElement : SysML::ActionUsage;
        attribute errorIds[0..*] : String;
        doc /* Identifies concrete public failure outcomes. Normative failure effects belong to requirements. */
    }

    metadata def StateAccess {
        :>> annotatedElement : SysML::Dependency;
        attribute kind : StateAccessKind;
    }

    metadata def ImplementationBinding {
        :> annotatedElement : SysML::PartDefinition;
        :> annotatedElement : SysML::AllocationUsage;
        attribute implementationLanguage : ImplementationLanguage;
        attribute codeRoot : String;
        attribute symbol : String;
        attribute realization : String;
    }

    metadata def ImplementationCodec {
        :> annotatedElement : SysML::PartDefinition;
        attribute logicalType : String;
        attribute implementationType : String;
        attribute normalization : String;
        doc /* Realization-only traceability for a non-isomorphic but lossless public encoding. */
    }

    metadata def EvidenceBinding {
        :>> annotatedElement : SysML::VerificationCaseDefinition;
        attribute evidenceId : String;
        attribute implementationScope : String;
    }

}
