package VellisViews {
    private import Views::*;
    private import Vellis::*;
    private import VellisUseCases::*;

    viewpoint def VellisCompositionViewpoint {
        require constraint {
            doc /* Show the Vellis application roles and the identity bindings that compose its Bibliotek components. */
        }
    }

    viewpoint def VellisUseCaseViewpoint {
        require constraint {
            doc /* Show actor-visible Vellis outcomes and their application subject. */
        }
    }

    view def VellisCompositionView {
        viewpoint composition : VellisCompositionViewpoint;
        filter @SysML::PartUsage;
    }

    view def VellisUseCaseView {
        viewpoint outcomes : VellisUseCaseViewpoint;
        filter @SysML::UseCaseUsage;
    }

    view vellisComposition : VellisCompositionView {
        expose Vellis::**;
        render asTreeDiagram;
    }

    view vellisUseCases : VellisUseCaseView {
        expose VellisUseCases::**;
        render asElementTable;
    }
}
