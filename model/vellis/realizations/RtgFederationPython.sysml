package VellisRtgFederationPythonRealization {
    private import SoftwareComponentModeling::*;
    private import Bibliotek::*;
    private import BibliotekLocalPythonRealization::*;
    private import VellisRtgFederation::*;

    part def PythonFederationCitationProjectionCatalog :> RtgCitationProjectionCatalog {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_federation"; symbol = "apps.rtg_federation.registry_io._RegistryCitationProjectionCatalog"; realization = "descriptor-declared bounded projection catalog"; }
    }

    part def PythonFederationCitationProjectionReader :> RtgCitationProjectionReader {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_federation"; symbol = "apps.rtg_federation.registry_io._RegistryCitationProjectionReader"; realization = "graph-local snapshot projection reader"; }
    }

    part def PythonFederationCitationResolver :> FederationCitationResolver {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/citation_resolution"; symbol = "components.rtg.citation_resolution.DeterministicRtgCitationResolver"; realization = "BibliotekLocalPython with federation projection adapters"; }
    }

    part def PythonFederationSemanticDraftGenerator :> RtgSemanticDraftGenerator {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_federation"; symbol = "apps.rtg_federation.semantic_openai.OpenAiResponsesSemanticDraftGenerator"; realization = "explicit opt-in OpenAI Responses adapter without graph tools or response storage"; }
    }

    part def PythonRtgFederationSemanticPipeline :> RtgFederationSemanticPipeline {
        part :>> generator : PythonFederationSemanticDraftGenerator;
        part :>> synthesizer : EvidenceBoundedRtgSynthesizer;
    }

    part def RtgFederationPython :> RtgFederationApplication {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/rtg_federation"; symbol = "apps.rtg_federation.toolset.RtgFederationToolset"; realization = "in-process control plane with CLI and FastMCP adapters"; }
        part :>> registry : InMemoryRtgGraphRegistry;
        part :>> routePack : DeterministicRtgRoutePack;
        part :>> bridgeStore : InMemoryRtgGraphBridge;
        part :>> projectionCatalog : PythonFederationCitationProjectionCatalog;
        part :>> projectionReader : PythonFederationCitationProjectionReader;
        part :>> citationResolver : PythonFederationCitationResolver;
        part :>> bridgeTraverser : DeterministicRtgBridgeTraverser;
        part :>> federatedSynthesizer : DeterministicRtgFederatedSynthesizer;
        part :>> semanticPipeline[0..1] : PythonRtgFederationSemanticPipeline;
    }

    part logicalFederation : RtgFederationApplication;
    part pythonFederation : RtgFederationPython;
    allocate logicalFederation to pythonFederation {
        allocate logicalFederation.registry to pythonFederation.registry;
        allocate logicalFederation.routePack to pythonFederation.routePack;
        allocate logicalFederation.bridgeStore to pythonFederation.bridgeStore;
        allocate logicalFederation.projectionCatalog to pythonFederation.projectionCatalog;
        allocate logicalFederation.projectionReader to pythonFederation.projectionReader;
        allocate logicalFederation.citationResolver to pythonFederation.citationResolver;
        allocate logicalFederation.bridgeTraverser to pythonFederation.bridgeTraverser;
        allocate logicalFederation.federatedSynthesizer to pythonFederation.federatedSynthesizer;
        allocate logicalFederation.semanticPipeline to pythonFederation.semanticPipeline;
    }
}
