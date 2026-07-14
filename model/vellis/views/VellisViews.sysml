package VellisViews {
    private import Views::*;
    private import Vellis::*;
    private import VellisUseCases::*;
    private import VellisLocalPythonRealization::*;
    private import VellisMcpPythonRealization::*;
    private import VellisPersonalLauncher::*;
    private import VellisPersonalLauncherPythonRealization::*;

    view def VellisCompositionView {
        doc /* Vellis roles, equality bindings, and logical-to-realization allocations. */
        filter @SysML::PartDefinition;
        filter @SysML::PartUsage;
        filter @SysML::BindingConnectorAsUsage;
        filter @SysML::AllocationUsage;
    }

    view def VellisUseCaseView {
        doc /* Actor-visible outcomes, internal actions, and externally meaningful succession. */
        filter @SysML::UseCaseDefinition;
        filter @SysML::UseCaseUsage;
        filter @SysML::ActionUsage;
        filter @SysML::SuccessionAsUsage;
    }

    view def VellisRequirementVerificationView {
        doc /* Application requirements, satisfiers, verification cases, and objectives. */
        filter @SysML::RequirementUsage;
        filter @SysML::SatisfyRequirementUsage;
        filter @SysML::VerificationCaseDefinition;
    }

    view vellisComposition : VellisCompositionView {
        expose Vellis::**;
        expose VellisLocalPythonRealization::**;
        expose VellisMcpPythonRealization::**;
        expose VellisPersonalLauncher::**;
        expose VellisPersonalLauncherPythonRealization::**;
        render asTreeDiagram;
    }

    view vellisUseCases : VellisUseCaseView {
        expose VellisUseCases::**;
        render asElementTable;
    }

    view vellisRequirementVerification : VellisRequirementVerificationView {
        expose Vellis::**;
        expose VellisPersonalLauncher::**;
        render asElementTable;
    }
}
