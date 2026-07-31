package VellisRequirements {
    private import RTGDomain::*;
    private import VellisSystems::*;

    /*
     * Initial requirements discovered from the current use cases and product
     * intent. They are deliberately textual at this stage; formal constraints
     * and verification cases should be added only where they provide value.
     */

    requirement def RTG_Graph_Data_Requirements {
        subject graph : RTG_Graph;

        requirement <GD001> canonicalObjectKindsArePreserved {
            require constraint {
                doc /*
                 * Canonical RTG user-graph state shall distinguish anchors,
                 * associated data objects, and links. A realization shall not
                 * collapse those kinds into a generic or undifferentiated
                 * record model.
                 */
            }
        }

        requirement <GD002> identitiesAndTypesAreStable {
            require constraint {
                doc /*
                 * Every stored graph object shall have a stable UUID and type
                 * key. UUIDs shall be globally unique across all three object
                 * kinds, and one type key shall not denote multiple kinds.
                 */
            }
        }

        requirement <GD003> associatedDataRemainsGrounded {
            require constraint {
                doc /*
                 * Every associated data object shall be directly associated
                 * with at least one existing anchor. Direct anchor-data
                 * association shall remain identity-free and many-to-many;
                 * it shall not be represented as an RTG link or graph object.
                 */
            }
        }

        requirement <GD004> linksPreserveDirectedEndpoints {
            require constraint {
                doc /*
                 * Every link shall preserve its own UUID, type, source UUID,
                 * target UUID, and system metadata. Both endpoints shall
                 * resolve to existing anchors or associated data objects;
                 * links shall not be link endpoints.
                 */
            }
        }

        requirement <GD005> userPayloadsRemainLossless {
            require constraint {
                doc /*
                 * Anchor display names, associated-data properties, and
                 * system metadata shall remain JSON-value-preserving across
                 * storage, backup, restore, and realization boundaries.
                 * Missing system.live shall normalize to true and supplied
                 * system.live shall be Boolean. Display names shall not be
                 * treated as object identity.
                 */
            }
        }

        requirement <GD006> currentUserGraphCanBeRecovered {
            require constraint {
                doc /*
                 * The model shall preserve the logical meaning needed for a
                 * future agent-assisted recovery path from current RTG user
                 * data: object UUIDs and kinds, type keys, anchor display
                 * names, associated-data properties, system metadata, direct
                 * anchor-data associations, and link identity, direction, and
                 * endpoints. A concrete importer, interchange format, and
                 * release commitment are intentionally deferred.
                 */
            }
        }
    }

    requirement def RTG_Ledger_Requirements {
        subject system : RTG_System;

        requirement <LG001> everyCommittedChangeIsRecorded {
            doc /*
             * Every committed RTG state change shall be represented exactly
             * once in the durable state-changing history.
             */
        }

        requirement <LG002> stateAndHistoryAreRecoverablyAtomic {
            doc /*
             * A state change shall become observable as committed only when
             * its durable history and resulting graph revision can be
             * recovered consistently.
             */
        }

        requirement <LG003> committedHistoryIsAppendOnly {
            doc /*
             * Committed state-changing records shall not be modified or
             * removed through normal system operation.
             */
        }

        requirement <LG004> revisionsAreUniquelyOrdered {
            doc /*
             * Every committed state transition shall produce a uniquely
             * ordered graph revision.
             */
        }

        requirement <LG005> historicalStateIsReconstructable {
            doc /*
             * The RTG System shall reconstruct an equivalent graph state for
             * any retained committed revision.
             */
        }

        requirement <LG006> queryResultsIdentifyRevision {
            doc /*
             * Every RTG query result shall identify the graph revision
             * against which it was evaluated.
             */
        }

        requirement <LG007> restorationPreservesHistory {
            doc /*
             * Restoring a prior graph state shall create a new committed
             * revision and shall not rewrite existing history.
             */
        }

        requirement <LG008> activityProvenanceIsRetained {
            doc /*
             * Retained activity shall distinguish activity initiated by the
             * owner, an AI agent, a hosted application, an automation, or the
             * system itself.
             */
        }

        requirement <LG009> auditCoverageIsDeclared {
            doc /*
             * The RTG System shall explicitly define which non-state-changing
             * activities are durably retained and their retention policy.
             */
        }
    }

    requirement def Constraint_Model_Management_Requirements {
        subject system : RTG_System;

        requirement <CM001> exactlyOneActiveModel {
            doc /*
             * The RTG System shall select exactly one constraint model to
             * govern ordinary graph changes.
             */
        }

        requirement <CM002> atMostOneStagedModel {
            doc /*
             * The RTG System shall select no more than one staged successor
             * to the active constraint model.
             */
        }

        requirement <CM003> stagingIsNonDisruptive {
            doc /*
             * Staging or editing a candidate shall not change the model that
             * governs ordinary graph changes.
             */
        }

        requirement <CM004> activationImpactIsAssessed {
            doc /*
             * Before activation, the RTG System shall assess the effects of
             * the staged model against a coherent graph revision.
             */
        }

        requirement <CM005> activationIsAtomic {
            doc /*
             * Activation shall either apply the complete validated effects
             * and select the staged model as active, or leave graph state and
             * active-model selection unchanged.
             */
        }

        requirement <CM006> invalidCandidateIsNotActivated {
            doc /*
             * A candidate that fails model or activation-impact validation
             * shall not become active.
             */
        }
    }

    requirement def Vellis_Ownership_Requirements {
        subject system : Vellis_System;

        requirement <OW001> oneAuthoritativeOwner {
            doc /*
             * One Vellis installation shall operate within the authority and
             * governance domain of one authoritative owner.
             */
        }

        requirement <OW002> agentsActForOwner {
            doc /*
             * External AI agents shall invoke Vellis within the owning
             * experience rather than as independent enterprise tenants.
             */
        }

        requirement <OW003> ownerControlsHostedExecution {
            doc /*
             * The owner shall control which applications and automations are
             * hosted and executed by Vellis.
             */
        }

        requirement <OW004> consequentialActivityIsInspectable {
            doc /*
             * The owner shall be able to inspect consequential activity by
             * the owner, agents, applications, automations, and the system.
             */
        }
    }

    requirement def Vellis_Simplicity_Requirements {
        subject system : Vellis_System;

        requirement <VS001> singleHostOperation {
            doc /*
             * The initial Vellis system shall operate on hardware controlled
             * by the owner without requiring a distributed deployment.
             */
        }

        requirement <VS002> turnkeyOperation {
            doc /*
             * The owner shall be able to install, start, stop, inspect, back
             * up, and restore Vellis without administering multiple
             * independently deployed infrastructure services.
             */
        }

        requirement <VS003> noEnterpriseTenancyRequired {
            doc /*
             * The initial system shall not require enterprise multi-tenancy,
             * organization hierarchy, or complex role management.
             */
        }

        requirement <VS004> commonCapabilitySemantics {
            doc /*
             * Any future external bindings shall preserve the modeled Vellis
             * capability semantics when their protocol details differ.
             */
        }

        requirement <VS005> minimalRequiredInfrastructure {
            doc /*
             * The initial implementation shall not require infrastructure or
             * operational components that are unnecessary for the modeled
             * single-owner use cases.
             */
        }

        requirement <VS006> modelTraceability {
            doc /*
             * Implemented responsibilities, interfaces, and externally
             * observable behavior shall be traceable to the authoritative
             * SysML model.
             */
        }

        requirement <VS007> understandableCodebase {
            doc /*
             * The codebase and operational composition shall remain small
             * enough for an owner or contributor to understand without
             * specialized enterprise infrastructure knowledge.
             */
        }
    }
}
