"""Model traceability invariants.

Every assertion here must be universally quantified over the model: it states a
relationship that holds for *all* declarations of a kind, not a snapshot of the
declarations that happen to exist today.

Specifically, a test in this file must not:

- enumerate the current model's elements and assert an exact set;
- forbid a SysML v2 language construct that has simply not been chosen yet;
- match exact model prose, spacing, or feature declarations.

Those forms turn ordinary modeling into a red suite whose only remedy is editing
the test, and they duplicate the model as a parallel contract in Python. The
model is the authority; these tests check that it refers to itself consistently.
"""

from __future__ import annotations

import re

from tools import model_layout, sysml_validator


def _text(name: str) -> str:
    return (model_layout.MODEL_ROOT / name).read_text(encoding="utf-8")


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


def test_every_selected_tool_is_performed_by_the_rtg_boundary() -> None:
    """Every declared public tool action is performed by the system that owns it.

    Universally quantified: no inventory of tool names appears here, so adding or
    removing a tool is an ordinary model change.
    """
    text = _text("20-rtg-system.sysml")
    model_code = sysml_validator._mask_non_code(text)
    definitions = set(re.findall(r"action def (rtg_[a-z_]+)", model_code))
    rtg_system = _body_from(text, "part def 'RTG System'")
    performed = set(re.findall(r"perform action \w+\s*:\s*(rtg_[a-z_]+)", rtg_system))

    assert definitions
    assert performed == definitions


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


def test_link_endpoints_stay_addressable_and_links_are_not() -> None:
    """The one RTG compatibility obligation that is not derivable from the model.

    Links may address anchors or associated data objects, never other links.
    Stated structurally rather than by matching declaration text, so the model
    may be reformatted or extended freely.
    """
    text = sysml_validator._mask_non_code(_text("10-rtg-domain.sysml"))
    endpoint_specializers = {
        quoted or bare
        for quoted, bare in re.findall(
            r"item def (?:'([^']+)'|(\w+))\s*:>\s*'Link Endpoint'",
            text,
        )
    }
    link_endpoint_features = set(re.findall(r"ref item (?:source|target)\s*:\s*'([^']+)'", text))

    assert "Anchor" in endpoint_specializers
    assert "Associated Data Object" in endpoint_specializers
    assert "Link" not in endpoint_specializers
    assert link_endpoint_features == {"Link Endpoint"}
