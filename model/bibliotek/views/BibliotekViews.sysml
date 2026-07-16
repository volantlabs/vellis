package BibliotekViews {
    private import Views::*;
    private import Bibliotek::*;

    view def BibliotekComponentStructureView {
        doc /* Reusable definitions, usages, composition, equality bindings, and allocations. */
        filter @SysML::PartDefinition or @SysML::PartUsage or
            @SysML::BindingConnectorAsUsage or @SysML::AllocationUsage;
    }

    view def BibliotekBehaviorContractView {
        doc /* Public operations, performances, state/capability dependencies, and sequencing. */
        filter @SysML::ActionDefinition or @SysML::ActionUsage or
            @SysML::Dependency or @SysML::SuccessionAsUsage;
    }

    view def BibliotekRequirementVerificationView {
        doc /* Requirements, asserted satisfiers, verification definitions, and their objectives. */
        filter @SysML::RequirementUsage or @SysML::SatisfyRequirementUsage or
            @SysML::VerificationCaseDefinition;
    }

    view def BibliotekComponentContractDiagramView {
        doc /* Compact component boundary: root, public state/value members, and provided operations. */
        filter @SysML::PartDefinition or @SysML::AttributeUsage or
            @SysML::ItemUsage or @SysML::PerformActionUsage;
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

    view <'diagram.bibliotek.component.rtg.constraints.contract'> rtgConstraintsContractDiagram : BibliotekComponentContractDiagramView {
        expose BibliotekRtgConstraints::RtgConstraints::applyBatch;
        expose BibliotekRtgConstraints::RtgConstraints::countSummary;
        expose BibliotekRtgConstraints::RtgConstraints::listConstraintsByTarget;
        render asTreeDiagram;
    }

    view <'diagram.bibliotek.component.rtg.discovery.contract'> rtgDiscoveryContractDiagram : BibliotekComponentContractDiagramView {
        expose BibliotekRtgDiscovery::RtgDiscovery;
        render asTreeDiagram;
    }

    view <'diagram.bibliotek.component.rtg.migration.contract'> rtgMigrationContractDiagram : BibliotekComponentContractDiagramView {
        expose BibliotekRtgMigration::RtgMigration::applyBatch;
        expose BibliotekRtgMigration::RtgMigration::countSummary;
        expose BibliotekRtgMigration::RtgMigration::findCandidateOwners;
        render asTreeDiagram;
    }

    view <'diagram.bibliotek.component.rtg.schema.contract'> rtgSchemaContractDiagram : BibliotekComponentContractDiagramView {
        expose BibliotekRtgSchema::RtgSchema::applyBatch;
        expose BibliotekRtgSchema::RtgSchema::countSummary;
        expose BibliotekRtgSchema::RtgSchema::listDefinitionsByTypeKey;
        render asTreeDiagram;
    }

    view <'diagram.bibliotek.component.storage.json_file.contract'> jsonFileStorageContractDiagram : BibliotekComponentContractDiagramView {
        expose BibliotekStorageJsonFile::JsonFileStorage;
        render asTreeDiagram;
    }

    view <'diagram.bibliotek.component.storage.sql.contract'> sqlStorageContractDiagram : BibliotekComponentContractDiagramView {
        expose BibliotekStorageSql::SqlStorage;
        render asTreeDiagram;
    }
}
