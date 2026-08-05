from __future__ import annotations

import re

from tools import model_layout, sysml_validator


def _text(name: str) -> str:
    return (model_layout.MODEL_ROOT / name).read_text(encoding="utf-8")


def _all_model_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(model_layout.MODEL_ROOT.glob("*.sysml"))
    )


def _body_from(text: str, marker: str, start: int = 0) -> str:
    model_code = sysml_validator._mask_non_code(text)
    declaration = model_code.index(marker, start)
    opening = model_code.index("{", declaration)
    depth = 0
    for index in range(opening, len(model_code)):
        if model_code[index] == "{":
            depth += 1
        elif model_code[index] == "}":
            depth -= 1
            if depth == 0:
                return model_code[opening + 1 : index]
    raise AssertionError(f"unclosed declaration: {marker}")


def test_body_extraction_ignores_braces_in_comments_and_strings() -> None:
    text = (
        "use case def 'Example' { "
        'doc /* A } does not close the body. */ attribute note = "{"; attribute kept; }'
    )

    assert "attribute kept" in _body_from(text, "use case def 'Example'")


def test_context_and_inclusions_reference_declared_use_cases() -> None:
    text = _text("30-vellis.sysml")
    model_code = sysml_validator._mask_non_code(text)
    rtg_code = sysml_validator._mask_non_code(_text("20-rtg-system.sysml"))
    definitions = set(re.findall(r"use case def '([^']+)'", model_code))
    rtg_definitions = set(re.findall(r"use case def '([^']+)'", rtg_code))
    context = _body_from(text, "part def Context")
    context_usages = set(re.findall(r"(?m)^\s*use case \w+\s*:\s*'([^']+)'", context))
    inclusions = set(re.findall(r"include use case [^{\n]+:\s*'([^']+)'", model_code))

    assert context_usages == definitions
    assert inclusions <= definitions | rtg_definitions


def test_vellis_composition_references_declared_behavior_and_core_memory_routes() -> None:
    rtg_system = _text("20-rtg-system.sysml")
    vellis = _text("30-vellis.sysml")
    rtg_code = sysml_validator._mask_non_code(rtg_system)
    vellis_code = sysml_validator._mask_non_code(vellis)
    rtg_definitions = set(re.findall(r"use case def '([^']+)'", rtg_code))
    vellis_definitions = set(re.findall(r"use case def '([^']+)'", vellis_code))
    included = set(re.findall(r"include use case [^{\n]+:\s*'([^']+)'", vellis_code))

    assert included <= rtg_definitions | vellis_definitions
    discovery_body = _body_from(vellis, "use case def 'Understand personal memory vocabulary'")
    context_body = _body_from(vellis, "use case def 'Obtain authorized relevant context'")
    retention_body = _body_from(vellis, "use case def 'Retain owner-approved context'")
    assert "Discover active graph definitions" in discovery_body
    assert "Query graph" in context_body
    assert "Apply graph change" in retention_body


def test_independent_review_outcomes_do_not_use_optional_includes_as_control() -> None:
    text = _text("30-vellis.sysml")
    model_code = sysml_validator._mask_non_code(text)

    for use_case in (
        "Review personal memory",
        "Review canonical memory history",
        "Review memory activity",
    ):
        assert f"use case def '{use_case}'" in model_code

    assert "Review personal memory and consequential activity" not in model_code


def test_actions_are_used_without_forcing_every_use_case_to_have_one() -> None:
    text = _text("20-rtg-system.sysml")
    model_code = sysml_validator._mask_non_code(text)
    quoted_definitions = set(re.findall(r"action def '([^']+)'", model_code))
    public_definitions = set(re.findall(r"action def (rtg_[a-z_]+)", model_code))
    definitions = quoted_definitions | public_definitions
    performed = set(
        re.findall(
            r"perform action \w+(?:\[[^]]+\])?\s*:\s*(?:'([^']+)'|(rtg_[a-z_]+))",
            model_code,
        )
    )
    performed_names = {quoted or public for quoted, public in performed}
    nested = set(
        re.findall(
            r"(?m)^\s*action (?!def\b)\w+(?:\s*\[[^]]+\])?\s*:\s*'([^']+)'",
            model_code,
        )
    )

    assert definitions == performed_names | nested


def test_selected_mcp_tool_inventory_is_exact_and_performed_by_rtg() -> None:
    text = _text("20-rtg-system.sysml")
    model_code = sysml_validator._mask_non_code(text)
    expected = {
        "rtg_definition_summary",
        "rtg_definition_inspect",
        "rtg_definition_delta",
        "rtg_query",
        "rtg_change",
        "rtg_set_definition_delta",
        "rtg_activate_definition_delta",
        "rtg_discard_definition_delta",
        "rtg_check",
        "rtg_history",
    }
    definitions = set(re.findall(r"action def (rtg_[a-z_]+)", model_code))
    rtg_system = _body_from(text, "part def 'RTG System'")
    performed = set(re.findall(r"perform action \w+\s*:\s*(rtg_[a-z_]+)", rtg_system))

    assert definitions == expected
    assert performed == expected
    tools_with_input = {
        "rtg_definition_inspect",
        "rtg_query",
        "rtg_change",
        "rtg_set_definition_delta",
        "rtg_history",
    }
    for tool in expected:
        body = _body_from(text, f"action def {tool}")
        assert "out item" in body
        assert ("in item" in body) is (tool in tools_with_input)

    assert "Empty Tool Request" not in model_code


def test_each_selected_tool_depends_on_declared_black_box_behavior() -> None:
    """Check the repository trace convention without treating it as product behavior."""
    text = _text("20-rtg-system.sysml")
    model_code = sysml_validator._mask_non_code(text)
    tools = set(re.findall(r"action def (rtg_[a-z_]+)", model_code))
    use_cases = set(re.findall(r"use case def '([^']+)'", model_code))
    dependencies = re.findall(
        r"dependency\s+\w+\s+from\s+(rtg_[a-z_]+)\s+to\s+([^;]+);",
        model_code,
    )
    traced_tools = {tool for tool, _ in dependencies}
    traced_behaviors = {
        target for _, targets in dependencies for target in re.findall(r"'([^']+)'", targets)
    }

    assert traced_tools == tools
    assert traced_behaviors <= use_cases
    assert all(re.findall(r"'([^']+)'", targets) for _, targets in dependencies)


def test_every_selected_tool_behavior_reaches_a_vellis_owner_outcome() -> None:
    rtg_code = sysml_validator._mask_non_code(_text("20-rtg-system.sysml"))
    vellis_code = sysml_validator._mask_non_code(_text("30-vellis.sysml"))
    tool_dependencies = re.findall(
        r"dependency\s+\w+\s+from\s+rtg_[a-z_]+\s+to\s+([^;]+);",
        rtg_code,
    )
    tool_behaviors = {
        target for targets in tool_dependencies for target in re.findall(r"'([^']+)'", targets)
    }
    included_behaviors = set(re.findall(r"include use case [^{\n]+:\s*'([^']+)'", vellis_code))
    app_dependencies = re.findall(
        r"dependency\s+\w+\s+from\s+'[^']+'\s+to\s+([^;]+);",
        vellis_code,
    )
    depended_behaviors = {
        target for targets in app_dependencies for target in re.findall(r"'([^']+)'", targets)
    }

    assert tool_behaviors <= included_behaviors | depended_behaviors


def test_mcp_client_is_an_external_role_without_transport_structure() -> None:
    text = _text("20-rtg-system.sysml")
    vellis = sysml_validator._mask_non_code(_text("30-vellis.sysml"))
    model_code = sysml_validator._mask_non_code(text)

    assert "part def 'MCP Client' :> 'RTG Client'" in model_code
    assert "part def 'External AI Agent'" in vellis
    assert "part def 'MCP Agent' :> 'External AI Agent', 'MCP Client'" in vellis
    discovery = _body_from(
        _text("30-vellis.sysml"),
        "use case def 'Understand personal memory vocabulary'",
    )
    assert "actor redefines client = 'Understand personal memory vocabulary'::agent" in discovery
    assert "port def" not in model_code
    assert "interface def" not in model_code


def test_rtg_is_one_cohesive_boundary_without_internal_system_parts() -> None:
    """Protect the selected cohesive RTG boundary, not a generic part inventory."""
    text = _text("20-rtg-system.sysml")
    model_code = sysml_validator._mask_non_code(text)
    removed_parts = {
        "Graph System",
        "Definition and Constraint System",
        "Validation System",
        "History System",
    }

    assert "part def 'RTG System'" in model_code
    assert not any(f"part def '{name}'" in model_code for name in removed_parts)
    rtg_system = _body_from(text, "part def 'RTG System'")
    for owned_state in (
        "currentGraph",
        "activeDefinitions",
        "definitionDelta",
        "currentRevision",
        "stateChanges",
        "activities",
    ):
        assert owned_state in rtg_system


def test_query_model_has_bounded_named_semantics() -> None:
    """Protect the selected minimal query language and its current cardinalities."""
    text = _text("10-rtg-domain.sysml")
    anchor_group = _body_from(text, "item def 'Anchor Group'")
    required_link = _body_from(text, "item def 'Required Link'")
    data_condition = _body_from(text, "item def 'Associated Data Condition'")
    property_condition = _body_from(text, "item def 'Data Property Condition'")
    query = _body_from(text, "item def 'Graph Query'")
    result = _body_from(text, "item def 'Graph Query Result'")
    anchor_binding = _body_from(text, "item def 'Anchor Binding'")
    link_binding = _body_from(text, "item def 'Link Binding'")
    data_binding = _body_from(text, "item def 'Associated Data Binding'")
    returned_property = _body_from(text, "item def 'Returned Property'")
    row = _body_from(text, "item def 'Graph Query Row'")

    assert "anchorType : 'Type Key'" in anchor_group
    assert "uuidFilter [0..1] : 'Anchor UUID Filter'" in anchor_group
    assert "uuids [1..*] : 'Graph UUID'" in _body_from(text, "item def 'Anchor UUID Filter'")
    assert "item def 'Anchor Group' :> 'Endpoint Group'" in text
    assert "item def 'Associated Data Condition' :> 'Endpoint Group'" in text
    assert "sourceGroup : 'Endpoint Group'" in required_link
    assert "targetGroup : 'Endpoint Group'" in required_link
    assert "linkType : 'Type Key'" in required_link
    assert "uuidFilter [0..1] : 'Link UUID Filter'" in required_link
    assert "anchorGroup : 'Anchor Group'" in data_condition
    assert "associatedDataType : 'Type Key'" in data_condition
    assert "propertyConditions [*]" in data_condition
    assert "comparison : 'Property Comparison'" in property_condition
    assert "expectedValue : 'JSON Value'" in property_condition
    for duplicated_definition_field in ("required", "jsonKind", "valueShape", "range"):
        assert duplicated_definition_field not in property_condition
    assert "anchorGroups [1..*]" in query
    assert "requiredLinks [*]" in query
    assert "dataConditions [*]" in query
    assert "returnShape : 'Return Shape'" in query
    assert "historicalSelection [0..1] : 'Historical State Selection'" in query
    assert "maximumRows : ScalarValues::Positive" in query
    assert "ref item query : 'Graph Query'" in result
    assert "evaluatedRevision [0..1]" in result
    assert "rows [*] : 'Graph Query Row'" in result
    assert "projection : 'Anchor Projection'" in anchor_binding
    assert "projection : 'Link Projection'" in link_binding
    assert "projection : 'Associated Data Projection'" in data_binding
    assert "value [0..1] : 'JSON Value'" in returned_property
    for binding_family in ("anchors", "links", "associatedData", "properties"):
        assert binding_family in row


def test_property_shape_and_range_are_closed_typed_vocabulary() -> None:
    text = _text("10-rtg-domain.sysml")
    shape = _body_from(text, "attribute def 'Value Shape'")
    value_range = _body_from(text, "attribute def 'Value Range'")

    assert "minimumSize [0..1] : ScalarValues::Natural" in shape
    assert "maximumSize [0..1] : ScalarValues::Natural" in shape
    assert "lowerBound [0..1] : 'JSON Value'" in value_range
    assert "upperBound [0..1] : 'JSON Value'" in value_range
    assert "permittedValues [*] : 'JSON Value'" in value_range
    assert "Inclusive" not in value_range


def test_definition_discovery_is_complete_focused_and_active_only() -> None:
    domain = _text("10-rtg-domain.sysml")
    system = _text("20-rtg-system.sysml")
    definition_object = _body_from(domain, "abstract item def 'Definition Object'")
    summary = _body_from(domain, "item def 'Definition Summary Result'")
    inspection_request = _body_from(domain, "item def 'Definition Inspection Request'")
    detail = _body_from(domain, "item def 'Anchor Definition Detail'")
    inspection_result = _body_from(domain, "item def 'Definition Inspection Result'")
    delta = _body_from(domain, "item def 'Definition Delta'")
    set_delta_request = _body_from(domain, "item def 'Set Definition Delta Request'")
    delta_result = _body_from(domain, "item def 'Definition Delta Result'")

    assert "description [0..1] : ScalarValues::String" in definition_object
    for described_family in (
        "abstract item def 'Type Definition' :> 'Definition Object'",
        "item def 'Property Constraint' :> 'Definition Object'",
        "item def 'Endpoint Constraint' :> 'Definition Object'",
        "abstract item def 'Relationship Constraint' :> 'Definition Object'",
    ):
        assert described_family in domain
    assert "item def 'Definition Summary Request'" not in domain
    assert "anchorTypes [*] : 'Anchor Type Summary'" in summary
    assert "evaluatedRevision [0..1] : 'Revision Number'" in summary
    assert "deltaPresent [0..1] : ScalarValues::Boolean" in summary
    assert "anchorTypeKeys [1..*] : 'Type Key'" in inspection_request
    assert "historicalSelection" not in inspection_request
    for feature in ("anchorType", "associatedDataTypes", "linkTypes", "relationshipConstraints"):
        assert feature in detail
    assert "anchorDetails [*] : 'Anchor Definition Detail'" in inspection_result
    assert "evaluatedRevision [0..1] : 'Revision Number'" in inspection_result
    assert "proposedDefinitions : 'Graph Definition Set'" in delta
    assert "proposedDefinitions : 'Graph Definition Set'" in set_delta_request
    assert "definitionDelta [0..1] : 'Definition Delta'" in delta_result
    assert "assessment [0..1] : 'Validation Report'" in delta_result
    assert "Discover active graph definitions" in system
    summary_action = _body_from(system, "action def rtg_definition_summary")
    assert "in item" not in summary_action
    assert "proposedDefinitions" not in summary
    assert "proposedDefinitions" not in inspection_result


def test_graph_change_is_explicit_without_full_graph_or_cascade_authority() -> None:
    text = _text("10-rtg-domain.sysml")
    change = _body_from(text, "item def 'Graph Change'")

    for feature in (
        "anchorUpserts",
        "associatedDataUpserts",
        "linkUpserts",
        "anchorRemovals",
        "associatedDataRemovals",
        "linkRemovals",
    ):
        assert feature in change
    assert "proposedGraph" not in change


def test_history_query_selects_one_bounded_record_family() -> None:
    text = _text("10-rtg-domain.sysml")
    query = _body_from(text, "item def 'History Query'")
    result = _body_from(text, "item def 'History Result'")

    assert "kind : 'History Kind'" in query
    assert "startTime [0..1]" in query
    assert "endTime [0..1]" in query
    assert "maximumRecords : ScalarValues::Positive" in query
    assert "query : 'History Query'" in result
    canonical_entry = _body_from(text, "item def 'Canonical History Entry'")
    activity_entry = _body_from(text, "item def 'Activity History Entry'")
    assert "canonicalEntries [*] ordered : 'Canonical History Entry'" in result
    assert "activityEntries [*] ordered : 'Activity History Entry'" in result
    assert "kind : 'History Kind'" not in result
    assert "abstract item def 'Canonical Record' :> 'History Record'" in text
    assert "item def 'Activity Record' :> 'History Record'" in text
    assert "priorRevision [0..1] : 'Revision Number'" in canonical_entry
    assert "transitionKind [0..1] : 'Transition Kind'" in canonical_entry
    assert "activityKind : 'Activity Kind'" in activity_entry
    assert "Canonical Change" not in canonical_entry
    assert "Canonical State" not in canonical_entry
    assert "History Record" not in result


def test_result_payloads_can_exclude_success_data_after_rejection_or_failure() -> None:
    text = _text("10-rtg-domain.sysml")
    operation = _body_from(text, "item def 'Operation Outcome'")
    query_result = _body_from(text, "item def 'Graph Query Result'")
    delta_result = _body_from(text, "item def 'Definition Delta Result'")
    history_result = _body_from(text, "item def 'History Result'")

    assert "status : 'Operation Status'" in operation
    assert "evaluatedRevision [0..1] : 'Revision Number'" in query_result
    assert "evaluatedRevision [0..1] : 'Revision Number'" in delta_result
    assert "definitionDelta [0..1] : 'Definition Delta'" in delta_result
    assert "assessment [0..1] : 'Validation Report'" in delta_result
    assert "evaluatedRevision [0..1] : 'Revision Number'" in history_result


def test_activity_retention_has_an_rtg_behavior_route_without_an_extra_tool() -> None:
    system = _text("20-rtg-system.sysml")
    vellis = _text("30-vellis.sysml")

    assert "use case def 'Manage activity retention'" in system
    retention = _body_from(vellis, "use case def 'Manage activity history retention'")
    assert "include use case retainActivity[1] : 'Manage activity retention'" in retention
    assert "action def rtg_activity_retention" not in system


def test_initial_mcp_boundary_adds_no_authorization_architecture() -> None:
    model_code = sysml_validator._mask_non_code(_all_model_text()).casefold()

    for declaration in (
        "part def 'authorization",
        "item def 'authorization",
        "action def authorize",
        "port def",
        "interface def",
    ):
        assert declaration not in model_code


def test_public_check_is_the_nonduplicated_current_graph_assessment() -> None:
    domain = _text("10-rtg-domain.sysml")
    system = _text("20-rtg-system.sysml")
    action = _body_from(system, "action def rtg_check")

    assert "Check Request" not in domain
    assert "Check Target" not in domain
    assert "in item" not in action
    assert "out item result : 'Validation Report'" in action


def test_validation_report_scope_has_no_unused_taxonomy() -> None:
    domain = _text("10-rtg-domain.sysml")
    scope = _body_from(domain, "enum def 'Validation Scope'")

    assert set(re.findall(r"enum (\w+);", scope)) == {"graphConformance", "definitionDelta"}
    assert "assessment [0..1] : 'Validation Report'" in _body_from(
        domain, "item def 'Definition Delta Result'"
    )


def test_query_result_is_bound_to_the_query_that_authorizes_it() -> None:
    text = _text("20-rtg-system.sysml")
    query_action = _body_from(text, "action def rtg_query")

    assert "bind result.query = query" in query_action
    assert not re.search(r"(?m)^\s*action\s+\w+\s*:", query_action)


def test_snapshot_and_tail_declare_required_replay_relationships() -> None:
    text = _text("10-rtg-domain.sysml")
    canonical_state = _body_from(text, "item def 'Canonical State'")
    snapshot = _body_from(text, "item def 'Canonical Snapshot'")
    change = _body_from(text, "item def 'Canonical Change'")
    transition = _body_from(text, "item def 'Canonical Transition Record'")
    tail = _body_from(text, "item def 'Ledger Tail'")
    request = _body_from(text, "item def 'Replay Request'")

    for state_feature in ("graph", "activeDefinitions", "definitionDelta", "revision"):
        assert state_feature in canonical_state
    assert "canonicalState : 'Canonical State'" in snapshot
    assert "priorRevision : 'Revision Number'" in transition
    assert "resultingRevision : 'Revision Number'" in transition
    assert "change : 'Canonical Change'" in transition
    assert "resultingState" not in transition
    assert "graphChange [0..1] : 'Graph Change'" in change
    assert "replacementGraph [0..1] : Graph" in change
    complete_graph_payloads = set(
        re.findall(r"item\s+(\w+)(?:\s*\[[^]]+\])?\s*:\s*Graph\s*;", change)
    )
    assert complete_graph_payloads == {"replacementGraph"}
    assert "followsRevision : 'Revision Number'" in tail
    assert "ref item transitions [1..*] ordered" in tail
    assert "ref item initial [0..1]" in request
    assert "ref item capturedSnapshot [0..1]" in request
    assert "ref item tail [0..1]" in request


def test_requirements_name_satisfiers_and_have_verification_paths() -> None:
    requirements = sysml_validator._mask_non_code(_text("40-requirements.sysml"))
    verification = sysml_validator._mask_non_code(_text("50-verification.sysml"))
    definitions = set(re.findall(r"requirement def '([^']+)'", requirements))
    usages = re.findall(
        r"requirement <([^>]+)> (\w+)\s*:\s*'([^']+)'\s*;",
        requirements,
    )
    satisfied = re.findall(
        r"satisfy (\w+)\s+by\s+([^;]+);",
        requirements,
    )
    verified = set(re.findall(r"verify VellisRequirements::(\w+);", verification))
    usage_names = {name for _, name, _ in usages}
    usage_definitions = {definition for _, _, definition in usages}

    assert usage_definitions == definitions
    assert {requirement for requirement, _ in satisfied} == usage_names
    assert verified == usage_names
    assert all(feature.strip() for _, feature in satisfied)


def test_every_verification_definition_has_a_bound_usage() -> None:
    text = sysml_validator._mask_non_code(_text("50-verification.sysml"))
    definitions = set(re.findall(r"verification def '([^']+)'", text))
    usages = set(re.findall(r"(?m)^\s*verification \w+\s*:\s*'([^']+)'", text))

    assert usages == definitions


def test_normative_model_declares_no_unselected_realization_structure() -> None:
    """Guard declarations, not explanatory vocabulary; retire when realization is selected."""
    model_code = sysml_validator._mask_non_code(_all_model_text()).casefold()

    for declaration in (
        "part def 'mcp server'",
        "part def 'database service'",
        "part def 'storage adapter'",
        "part def 'repository'",
        "part def 'runtime'",
        "port def",
        "interface def",
    ):
        assert declaration not in model_code

    assert not re.search(
        r"(?m)^\s*(?:private\s+)?import\s+(?:fastmcp|sqlite|postgres|python|pydantic)(?:::|\b)",
        model_code,
    )


def test_compatibility_critical_rtg_distinctions_remain_explicit() -> None:
    """Protect only predecessor meanings explicitly selected for compatibility."""
    text = sysml_validator._mask_non_code(_text("10-rtg-domain.sysml"))

    assert "item def Anchor :> 'Link Endpoint'" in text
    assert "item def 'Associated Data Object' :> 'Link Endpoint'" in text
    assert "ref item anchors [1..*] : Anchor" in text
    assert "item def Link :> 'Graph Object'" in text
    assert "ref item source : 'Link Endpoint'" in text
    assert "ref item target : 'Link Endpoint'" in text
    assert "attribute live : ScalarValues::Boolean default = true" in text
    assert "item def 'Link Multiplicity Constraint'" in text
    assert "item def 'Direct Association Multiplicity Constraint'" in text
    assert "Multi Object Constraint" not in text
