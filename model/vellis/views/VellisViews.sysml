package VellisViews {
    private import Views::*;
    private import Vellis::*;
    private import VellisUseCases::*;
    private import VellisLocalPythonRealization::*;
    private import VellisMcpPythonRealization::*;
    private import VellisRuntimePythonRealization::*;

    view def VellisCompositionView {
        doc /* Vellis roles, runtime ports and interfaces, message/send/accept behavior, equality bindings, and logical-to-realization allocations. */
        filter @SysML::PartDefinition or @SysML::PartUsage or
            @SysML::PortDefinition or @SysML::PortUsage or
            @SysML::InterfaceDefinition or @SysML::InterfaceUsage or
            @SysML::FlowUsage or @SysML::ActionUsage or
            @SysML::BindingConnectorAsUsage or @SysML::AllocationUsage;
    }

    view def VellisUseCaseView {
        doc /* Actor-visible outcomes, internal actions, and externally meaningful succession. */
        filter @SysML::UseCaseDefinition or @SysML::UseCaseUsage or
            @SysML::ActionUsage or @SysML::SuccessionAsUsage;
    }

    view def VellisRequirementVerificationView {
        doc /* Application requirements, satisfiers, verification cases, and objectives. */
        filter @SysML::RequirementUsage or @SysML::SatisfyRequirementUsage or
            @SysML::VerificationCaseDefinition;
    }

    view vellisComposition : VellisCompositionView {
        expose Vellis::**;
        expose VellisLocalPythonRealization::**;
        expose VellisMcpPythonRealization::**;
        expose VellisRuntimePythonRealization::**;
        render asTreeDiagram;
    }

    view vellisUseCases : VellisUseCaseView {
        expose VellisUseCases::**;
        render asElementTable;
    }

    view vellisRequirementVerification : VellisRequirementVerificationView {
        expose Vellis::**;
        render asElementTable;
    }
}
