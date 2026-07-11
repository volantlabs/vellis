package BibliotekViews {
    private import Views::*;
    private import Bibliotek::*;

    viewpoint def BibliotekComponentStructureViewpoint {
        require constraint {
            doc /* Show reusable component definitions and their structural decomposition without application or realization elements. */
        }
    }

    viewpoint def BibliotekBehaviorContractViewpoint {
        require constraint {
            doc /* Show public action definitions and usages needed to reason about Bibliotek black-box behavior. */
        }
    }

    view def BibliotekComponentStructureView {
        viewpoint structure : BibliotekComponentStructureViewpoint;
        filter @SysML::PartDefinition;
    }

    view def BibliotekBehaviorContractView {
        viewpoint behavior : BibliotekBehaviorContractViewpoint;
        filter @SysML::ActionDefinition;
    }

    view bibliotekComponentStructure : BibliotekComponentStructureView {
        expose Bibliotek::**;
        render asTreeDiagram;
    }

    view bibliotekBehaviorContracts : BibliotekBehaviorContractView {
        expose Bibliotek::**;
        render asElementTable;
    }
}
