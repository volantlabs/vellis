from __future__ import annotations

from components.rtg.graph_registry import (
    InMemoryRtgGraphRegistry,
    RtgGraphDescriptor,
    RtgGraphFederatedIntent,
    RtgGraphIntent,
    RtgGraphMcpEndpoint,
    RtgGraphNotFound,
    RtgGraphRegistryInvalid,
)
from components.rtg.graph_registry.reference import create_reference_component

MODEL_EVIDENCE = {
    "PutGraphContractVerification": (
        "test_registry_stores_lists_replaces_and_returns_copies",
        "test_registry_validates_descriptor_shape",
        "test_registry_rejects_non_finite_metadata_without_replacing",
    ),
    "ListGraphsContractVerification": (
        "test_empty_registry_has_no_graphs",
        "test_registry_stores_lists_replaces_and_returns_copies",
        "test_registry_lists_graphs_deterministically",
    ),
    "GetGraphContractVerification": (
        "test_registry_stores_lists_replaces_and_returns_copies",
        "test_get_graph_reports_missing_graphs",
    ),
    "CompileIntentContractVerification": (
        "test_compile_intent_auto_selects_unambiguous_read_route",
        "test_compile_intent_requires_confirmation_for_ambiguous_or_write_routes",
        "test_compile_intent_rejects_unknown_explicit_target",
        "test_compile_intent_rejects_malformed_intent_without_mutation",
    ),
    "CompileFederatedIntentContractVerification": (
        "test_compile_federated_intent_plans_read_steps_across_matching_graphs",
        "test_compile_federated_intent_preserves_explicit_graph_set",
        "test_compile_federated_intent_does_not_auto_execute_writes",
        "test_compile_federated_intent_rejects_unknown_target_without_partial_plan",
    ),
    "CreateEmptyRtgGraphRegistryContractVerification": ("test_empty_registry_has_no_graphs",),
    "RtgGraphRegistryBoundaryVerification": (
        "test_empty_registry_has_no_graphs",
        "test_registry_stores_lists_replaces_and_returns_copies",
        "test_registry_lists_graphs_deterministically",
        "test_compile_intent_auto_selects_unambiguous_read_route",
        "test_compile_intent_requires_confirmation_for_ambiguous_or_write_routes",
        "test_compile_federated_intent_plans_read_steps_across_matching_graphs",
        "test_compile_federated_intent_does_not_auto_execute_writes",
        "test_registry_surface_does_not_expose_adjacent_component_operations",
    ),
}


def repo_graph() -> RtgGraphDescriptor:
    return RtgGraphDescriptor(
        graph_id="repo_twin",
        title="Repo Digital Twin",
        storage_root=".data/repo-twin",
        sql_database_path=".data/repo-twin/controller.sqlite",
        authority="derived_from_repo",
        write_policy="sync_only",
        domains=("components", "specs", "tests", "evidence", "repo-structure"),
        tags=("repo", "engineering", "derived", "evidence"),
        mcp_endpoint=RtgGraphMcpEndpoint(
            transport="http",
            host="127.0.0.1",
            port=8765,
            path="/mcp",
            server_name="vellis_repo_twin",
        ),
        metadata={"disposable": True},
    )


def personal_graph() -> RtgGraphDescriptor:
    return RtgGraphDescriptor(
        graph_id="personal_ops",
        title="Personal Operating Graph",
        storage_root=".data/monographs/personal-ops-v1",
        sql_database_path=".data/monographs/personal-ops-v1/controller.sqlite",
        authority="user_authored",
        write_policy="explicit_target_required",
        domains=("commitments", "decisions", "routines", "attention", "evidence"),
        tags=("personal", "operating", "memory"),
    )


def test_empty_registry_has_no_graphs() -> None:
    assert create_reference_component().list_graphs().graphs == ()


def test_registry_stores_lists_replaces_and_returns_copies() -> None:
    registry = create_reference_component()
    repo = registry.put_graph(repo_graph())
    replacement = registry.put_graph(
        RtgGraphDescriptor(
            graph_id=repo.graph_id,
            title="Repo Twin Replacement",
            storage_root=".data/repo-twin",
            sql_database_path=".data/repo-twin/controller.sqlite",
            authority="derived_from_repo",
            write_policy="sync_only",
            domains=("components",),
        )
    )
    replacement.metadata["mutated"] = True

    listed = registry.list_graphs().graphs
    listed[0].metadata["mutated"] = True

    assert listed[0].title == "Repo Twin Replacement"
    assert registry.get_graph("repo_twin") == RtgGraphDescriptor(
        graph_id="repo_twin",
        title="Repo Twin Replacement",
        storage_root=".data/repo-twin",
        sql_database_path=".data/repo-twin/controller.sqlite",
        authority="derived_from_repo",
        write_policy="sync_only",
        domains=("components",),
    )


def test_registry_lists_graphs_deterministically() -> None:
    registry = InMemoryRtgGraphRegistry.empty()
    registry.put_graph(personal_graph())
    registry.put_graph(repo_graph())

    assert [graph.graph_id for graph in registry.list_graphs().graphs] == [
        "personal_ops",
        "repo_twin",
    ]


def test_get_graph_reports_missing_graphs() -> None:
    registry = create_reference_component()

    try:
        registry.get_graph("missing_graph")
    except RtgGraphNotFound:
        pass
    else:
        raise AssertionError("missing graph should fail")


def test_registry_validates_descriptor_shape() -> None:
    registry = create_reference_component()
    invalid_descriptors = (
        RtgGraphDescriptor(
            graph_id="bad-id",
            title="Bad id.",
            storage_root=".data/bad",
            sql_database_path=".data/bad/controller.sqlite",
            authority="test",
            write_policy="test",
            domains=("test",),
        ),
        RtgGraphDescriptor(
            graph_id="empty_domains",
            title="Empty domains.",
            storage_root=".data/bad",
            sql_database_path=".data/bad/controller.sqlite",
            authority="test",
            write_policy="test",
            domains=(),
        ),
        RtgGraphDescriptor(
            graph_id="bad_endpoint",
            title="Bad endpoint.",
            storage_root=".data/bad",
            sql_database_path=".data/bad/controller.sqlite",
            authority="test",
            write_policy="test",
            domains=("test",),
            mcp_endpoint=RtgGraphMcpEndpoint(transport="http", host="127.0.0.1"),
        ),
        RtgGraphDescriptor(
            graph_id="bad_metadata",
            title="Bad metadata.",
            storage_root=".data/bad",
            sql_database_path=".data/bad/controller.sqlite",
            authority="test",
            write_policy="test",
            domains=("test",),
            metadata={"bad": object()},  # type: ignore[dict-item]
        ),
    )

    for descriptor in invalid_descriptors:
        try:
            registry.put_graph(descriptor)
        except RtgGraphRegistryInvalid:
            pass
        else:
            raise AssertionError(f"invalid descriptor should fail: {descriptor.graph_id}")


def test_registry_rejects_non_finite_metadata_without_replacing() -> None:
    registry = create_reference_component()
    original = registry.put_graph(repo_graph())

    for number in (float("nan"), float("inf"), float("-inf")):
        invalid = RtgGraphDescriptor(
            graph_id=original.graph_id,
            title="Invalid replacement",
            storage_root=original.storage_root,
            sql_database_path=original.sql_database_path,
            authority=original.authority,
            write_policy=original.write_policy,
            domains=original.domains,
            metadata={"number": number},
        )
        try:
            registry.put_graph(invalid)
        except RtgGraphRegistryInvalid:
            pass
        else:
            raise AssertionError("non-finite metadata should fail")

    assert registry.get_graph(original.graph_id) == original


def test_compile_intent_auto_selects_unambiguous_read_route() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    registry.put_graph(personal_graph())

    route = registry.compile_intent(
        RtgGraphIntent(
            operation="read",
            text="Which component specs lack verification evidence?",
        )
    )

    assert route.selected_graph_id == "repo_twin"
    assert route.requires_confirmation is False
    assert route.candidates[0].graph_id == "repo_twin"
    assert "domain:components" in route.candidates[0].reasons
    assert "domain:evidence" in route.candidates[0].reasons


def test_compile_intent_requires_confirmation_for_ambiguous_or_write_routes() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    registry.put_graph(personal_graph())

    ambiguous = registry.compile_intent(
        RtgGraphIntent(operation="read", text="Find evidence.", domain_hints=("evidence",))
    )
    write = registry.compile_intent(
        RtgGraphIntent(operation="write", text="Record evidence for today's decision.")
    )
    explicit_write = registry.compile_intent(
        RtgGraphIntent(
            operation="write",
            text="Record evidence for today's decision.",
            target_graph_id="personal_ops",
        )
    )

    assert ambiguous.selected_graph_id is None
    assert ambiguous.requires_confirmation is True
    assert ambiguous.reason == "multiple graphs tied for the strongest match"
    assert write.selected_graph_id is None
    assert write.requires_confirmation is True
    assert write.reason == "write intents require an explicit target_graph_id"
    assert explicit_write.selected_graph_id == "personal_ops"
    assert explicit_write.requires_confirmation is False


def test_compile_intent_rejects_unknown_explicit_target() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())

    try:
        registry.compile_intent(
            RtgGraphIntent(
                operation="read",
                text="Read something.",
                target_graph_id="missing_graph",
            )
        )
    except RtgGraphNotFound:
        pass
    else:
        raise AssertionError("unknown explicit target should fail")


def test_compile_intent_rejects_malformed_intent_without_mutation() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    before = registry.list_graphs()

    for intent in (
        RtgGraphIntent(operation="delete", text="Do something."),
        RtgGraphIntent(operation="read", text=" "),
        RtgGraphIntent(operation="read", text="Read.", domain_hints=("repo", "repo")),
    ):
        try:
            registry.compile_intent(intent)
        except RtgGraphRegistryInvalid:
            pass
        else:
            raise AssertionError("malformed intent should fail")

    assert registry.list_graphs() == before


def test_compile_federated_intent_plans_read_steps_across_matching_graphs() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    registry.put_graph(personal_graph())

    plan = registry.compile_federated_intent(
        RtgGraphFederatedIntent(
            operation="read",
            text="Compare component evidence with personal decisions.",
        )
    )

    assert plan.executable is True
    assert plan.requires_confirmation is False
    assert plan.reason == "read plan includes all matching graph candidates"
    assert [step.graph_id for step in plan.steps] == ["personal_ops", "repo_twin"]
    assert all(step.operation == "read" for step in plan.steps)
    assert "domain:decisions" in plan.steps[0].reasons
    assert "domain:components" in plan.steps[1].reasons


def test_compile_federated_intent_preserves_explicit_graph_set() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    registry.put_graph(personal_graph())

    plan = registry.compile_federated_intent(
        RtgGraphFederatedIntent(
            operation="read",
            text="Read these graphs.",
            target_graph_ids=("repo_twin", "personal_ops"),
        )
    )

    assert plan.executable is True
    assert [step.graph_id for step in plan.steps] == ["repo_twin", "personal_ops"]
    assert plan.steps[0].reasons == ("explicit target_graph_ids",)


def test_compile_federated_intent_does_not_auto_execute_writes() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    registry.put_graph(personal_graph())

    inferred_write = registry.compile_federated_intent(
        RtgGraphFederatedIntent(
            operation="write",
            text="Record evidence for a decision.",
        )
    )
    explicit_write = registry.compile_federated_intent(
        RtgGraphFederatedIntent(
            operation="write",
            text="Record evidence for a decision.",
            target_graph_ids=("personal_ops",),
        )
    )

    assert inferred_write.executable is False
    assert inferred_write.requires_confirmation is True
    assert (
        inferred_write.reason == "federated write and admin plans require explicit target_graph_ids"
    )
    assert explicit_write.executable is False
    assert explicit_write.requires_confirmation is True
    assert [step.graph_id for step in explicit_write.steps] == ["personal_ops"]


def test_compile_federated_intent_rejects_unknown_target_without_partial_plan() -> None:
    registry = create_reference_component()
    registry.put_graph(repo_graph())
    before = registry.list_graphs()

    try:
        registry.compile_federated_intent(
            RtgGraphFederatedIntent(
                operation="read",
                text="Read these graphs.",
                target_graph_ids=("repo_twin", "missing_graph"),
            )
        )
    except RtgGraphNotFound:
        pass
    else:
        raise AssertionError("unknown explicit target should fail the whole plan")

    assert registry.list_graphs() == before


def test_registry_surface_does_not_expose_adjacent_component_operations() -> None:
    registry = create_reference_component()

    for forbidden_name in (
        "execute",
        "put_anchor",
        "validate_live_graph_changes",
        "stage_schema_migration",
        "run_mcp_server",
        "query",
    ):
        assert not hasattr(registry, forbidden_name)
