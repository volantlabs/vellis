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

    enum def StateAuthorityKind {
        enum canonicalOwner;
        enum derived;
        enum externalReference;
    }

    enum def StateLifetime {
        enum componentCoupled;
        enum independent;
    }

    enum def StatePersistence {
        enum ephemeral;
        enum durable;
        enum unspecified;
    }

    enum def StateAccessKind {
        enum read;
        enum create;
        enum write;
        enum delete;
        enum none;
    }

    enum def ImplementationLanguage {
        enum python;
        enum external;
        enum unimplemented;
    }

    enum def ExternalNamingConvention {
        enum exact;
        enum lowerSnakeCase;
    }

    metadata def SpecIdentity {
        attribute id : String;
        attribute lifecycleStatus : SpecLifecycle;
        attribute owner : String;
    }

    metadata def RequiredCapability {
        attribute providerLowerBound[0..1] : Integer;
        attribute providerUpperBound[0..1] : Integer;
        doc /* Marks a referential feature as a required capability and declares provider cardinality. Provided capability semantics come directly from perform action. */
    }

    metadata def ContractSatisfaction;

    metadata def CapabilityUse {
        attribute effect : String;
        doc /* Describes how one action uses a required capability. This is distinct from access to component-owned state. */
    }

    metadata def StateAuthority {
        attribute authority : StateAuthorityKind;
        attribute lifetime : StateLifetime;
        attribute persistence : StatePersistence;
    }

    metadata def StateAccess {
        attribute kind : StateAccessKind;
        attribute effect : String;
    }

    metadata def FailureContract {
        attribute errorIds[0..*] : String;
        attribute obligation : String;
    }

    metadata def DependencyPolicy {
        attribute allowedComponentIds[0..*] : String;
        attribute forbiddenComponentIds[0..*] : String;
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

    metadata def StableId {
        attribute id : String;
    }

    metadata def ExternalEncodingProfile {
        attribute memberNames : ExternalNamingConvention;
        attribute enumLiterals : ExternalNamingConvention;
        doc /* Declares the default externally observable member and enum spelling for a model namespace. */
    }

    metadata def ExternalName {
        attribute name : String;
        doc /* Overrides the default external spelling of the annotated public model element. */
    }

}
