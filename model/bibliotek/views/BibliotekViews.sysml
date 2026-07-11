package BibliotekViews {
    private import Views::*;
    private import Bibliotek::*;

    view def BibliotekComponentStructureView {
        doc /* Reusable definitions, usages, composition, equality bindings, and allocations. */
        filter @SysML::PartDefinition;
        filter @SysML::PartUsage;
        filter @SysML::BindingConnectorAsUsage;
        filter @SysML::AllocationUsage;
    }

    view def BibliotekBehaviorContractView {
        doc /* Public operations, performances, state/capability dependencies, and sequencing. */
        filter @SysML::ActionDefinition;
        filter @SysML::ActionUsage;
        filter @SysML::Dependency;
        filter @SysML::SuccessionAsUsage;
    }

    view def BibliotekRequirementVerificationView {
        doc /* Requirements, asserted satisfiers, verification definitions, and their objectives. */
        filter @SysML::RequirementUsage;
        filter @SysML::SatisfyRequirementUsage;
        filter @SysML::VerificationCaseDefinition;
    }

    view bibliotekComponentStructure : BibliotekComponentStructureView {
        expose Bibliotek::**;
        render asTreeDiagram;
    }

    view bibliotekBehaviorContracts : BibliotekBehaviorContractView {
        expose Bibliotek::**;
        render asElementTable;
    }

    view bibliotekRequirementVerification : BibliotekRequirementVerificationView {
        expose Bibliotek::**;
        render asElementTable;
    }
}
