package VellisRtgFederation {
    private import SoftwareComponentModeling::*;
    private import Bibliotek::*;

    part def FederationCitationResolver :> RtgCitationResolver, RtgBridgeEndpointResolver;

    part def RtgFederationSemanticPipeline {
        part generator : RtgSemanticDraftGenerator;
        part synthesizer : RtgEvidenceBoundedSynthesizer;

        bind synthesizer.generator = generator;
    }

    part def <'application.vellis.rtg_federation'> RtgFederationApplication {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        part registry : RtgGraphRegistry;
        part routePack : RtgRoutePack;
        part bridgeStore : RtgGraphBridge;
        part projectionCatalog : RtgCitationProjectionCatalog;
        part projectionReader : RtgCitationProjectionReader;
        part citationResolver : FederationCitationResolver;
        part bridgeTraverser : RtgBridgeTraverser;
        part federatedSynthesizer : RtgFederatedSynthesizer;
        part semanticPipeline[0..1] : RtgFederationSemanticPipeline;

        bind citationResolver.catalog = projectionCatalog;
        bind citationResolver.reader = projectionReader;
        bind bridgeTraverser.bridgeStore = bridgeStore;
        bind bridgeTraverser.citationResolver = citationResolver;
    }

    requirement <'invariant.vellis.rtg_federation.graph_local_reads'> graphLocalReads {
        subject application : RtgFederationApplication;
        require constraint {
            doc /* Every executable graph read is descriptor-declared and runs against one owning graph at a time; the federation application performs no arbitrary cross-graph join and proxies no monograph write. */
        }
    }

    requirement <'invariant.vellis.rtg_federation.explicit_write_targets'> explicitWriteTargets {
        subject application : RtgFederationApplication;
        require constraint {
            doc /* Route compilation never authorizes a write from confidence alone. Any write-oriented route requires one explicitly named graph and hands execution to that graph's governed application boundary. */
        }
    }

    requirement <'invariant.vellis.rtg_federation.qualified_identity'> qualifiedIdentity {
        subject application : RtgFederationApplication;
        require constraint {
            doc /* Federated citations and bridge endpoints retain graph-qualified identity. Citation resolution is bounded by the owning descriptor, and confirmed bridge traversal keeps source and target projections separate. */
        }
    }

    requirement <'invariant.vellis.rtg_federation.semantic_opt_in'> semanticOptIn {
        subject application : RtgFederationApplication;
        require constraint {
            doc /* Deterministic synthesis is always available without a model. The optional semantic pipeline receives only the deterministic evidence envelope, receives no graph tools, stores no response, and cannot claim verified entailment. */
        }
    }

    requirement <'invariant.vellis.rtg_federation.adapters_outside_components'> adaptersOutsideComponents {
        subject application : RtgFederationApplication;
        require constraint {
            doc /* Registry JSON loading, snapshot access, canned-query dispatch, CLI encoding, and MCP transport remain application adapters and do not redefine reusable Bibliotek contracts. */
        }
    }

    requirement <'invariant.vellis.rtg_federation.read_compatible_snapshots'> readCompatibleSnapshots {
        subject application : RtgFederationApplication;
        require constraint {
            doc /* A predecessor snapshot may be projected in memory for bounded reads only when every unsupported schema field or legacy value kind is recognized and reported. The projection never rewrites the stored snapshot and never authorizes a graph write or claims schema-domain runtime readiness. */
        }
    }

    part contractContext {
        part application : RtgFederationApplication;
        satisfy graphLocalReads by application;
        satisfy explicitWriteTargets by application;
        satisfy qualifiedIdentity by application;
        satisfy semanticOptIn by application;
        satisfy adaptersOutsideComponents by application;
        satisfy readCompatibleSnapshots by application;
    }

    verification def RtgFederationCompositionVerification {
        subject application : RtgFederationApplication;
        objective {
            verify graphLocalReads;
            verify explicitWriteTargets;
            verify qualifiedIdentity;
            verify semanticOptIn;
            verify adaptersOutsideComponents;
            verify readCompatibleSnapshots;
        }
        @EvidenceBinding { evidenceId = "apps/rtg_federation/tests/test_rtg_federation_app.py#RtgFederationCompositionVerification"; implementationScope = "RtgFederationPython"; }
    }
}
