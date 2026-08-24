from pathlib import Path

from tools.model_policy import model_policy_findings, policy_findings


def test_current_normative_model_blocks_own_required_constraints() -> None:
    assert model_policy_findings() == ()


def test_policy_is_independent_of_declaration_names_and_counts() -> None:
    source = """
package Example {
    requirement def AnyName {
        subject system : Anything;
        require constraint { doc /* The subject shall behave. */ }
    }
    use case def AnyCase {
        objective { require constraint { doc /* Demonstrate it. */ } }
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()


def test_named_objectives_and_requirement_usages_own_required_constraints() -> None:
    source = """
package Example {
    requirement namedUsage : SomeRequirement {
        subject system : Anything;
        require constraint governingRule {
            doc policyText locale "en" /* The subject shall behave. */
        }
    }
    verification def NamedCase {
        objective demonstrateBehavior {
            require constraint governingRule {
                doc <'OBJ'> 'policy text' /* Demonstrate the required behavior. */
            }
        }
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()


def test_named_objectives_and_requirement_usages_cannot_bypass_policy() -> None:
    source = """
package Example {
    requirement bareUsage : SomeRequirement {
        doc /* The subject shall behave. */
    }
    verification def NamedCase {
        objective bareObjective {
            doc /* Demonstrate the required behavior. */
        }
    }
}
"""
    findings = policy_findings(Path("example.sysml"), source)
    assert len(findings) == 4
    assert sum("no directly owned required constraint" in finding for finding in findings) == 2
    assert sum("outside a required constraint" in finding for finding in findings) == 2
    assert any("requirement usage" in finding for finding in findings)
    assert any("objective" in finding for finding in findings)


def test_unrestricted_names_cannot_hide_normative_declarations() -> None:
    source = """
package Example {
    requirement def 'Bare; Requirement' {
        subject system : Anything;
        doc /* The subject shall behave. */
    }
    verification def NamedCase {
        objective 'Bare; Objective' {
            doc /* Demonstrate the required behavior. */
        }
    }
}
"""
    findings = policy_findings(Path("example.sysml"), source)
    assert len(findings) == 4
    assert sum("no directly owned required constraint" in finding for finding in findings) == 2
    assert sum("outside a required constraint" in finding for finding in findings) == 2


def test_identified_bare_docs_are_rejected_even_beside_empty_required_constraints() -> None:
    source = """
package Example {
    requirement def IdentifiedRequirement {
        doc policyText locale "en" /* The subject shall behave. */
        require constraint emptyRule { }
    }
    verification def IdentifiedCase {
        objective namedObjective {
            doc <'OBJ'> 'policy text' /* Demonstrate the required behavior. */
            require constraint emptyRule { }
        }
    }
}
"""
    findings = policy_findings(Path("example.sysml"), source)
    assert len(findings) == 4
    assert sum("substantive content" in finding for finding in findings) == 2
    assert sum("outside a required constraint" in finding for finding in findings) == 2


def test_empty_required_constraints_cannot_make_definitions_or_objectives_nonvacuous() -> None:
    source = """
package Example {
    requirement def EmptyFormalMeaning {
        subject system : Anything;
        require constraint emptyRule { }
    }
    verification def VacuousCase {
        objective { require constraint { } }
    }
}
"""
    findings = policy_findings(Path("example.sysml"), source)
    assert len(findings) == 2
    assert all("substantive content" in finding for finding in findings)


def test_empty_documentation_does_not_make_a_required_constraint_substantive() -> None:
    source = """
package Example {
    requirement def EmptyDocumentation {
        require constraint namedRule {
            doc policyText locale "en" /**/
        }
    }
    use case def EmptyObjective {
        objective { require constraint { doc /*   */ } }
    }
}
"""
    findings = policy_findings(Path("example.sysml"), source)
    assert len(findings) == 2
    assert all("substantive content" in finding for finding in findings)


def test_shorthand_required_constraint_references_preserve_inherited_formal_meaning() -> None:
    source = """
package Example {
    constraint 'governing rule' { true }
    requirement def ShorthandRequirement {
        require 'governing rule';
    }
    use case def ShorthandCase {
        objective { require 'governing rule'; }
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()


def test_typed_required_constraint_usages_preserve_referenced_formal_meaning() -> None:
    source = """
package Example {
    constraint def Rule { true }
    requirement def TypedRequirement {
        require constraint namedRule : Rule;
    }
    use case def TypedCase {
        objective { require constraint : Rule; }
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()


def test_inherited_requirement_usage_needs_no_redundant_local_constraint() -> None:
    source = """
package Example {
    requirement inheritedRequirement : SomeRequirement {
        subject system : Anything;
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()


def test_notes_and_strings_cannot_inject_phantom_normative_syntax() -> None:
    source = """
package Example {
    //*
      requirement def Phantom { doc phantom braces }
    */
    requirement def RealRequirement {
        require constraint governingRule {
            "doc /* not documentation */";
            doc actualDocumentation /* The subject shall behave. */
        }
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()


def test_bare_normative_docs_are_rejected_even_when_verify_is_present() -> None:
    source = """
package Example {
    requirement def EmptyFormalMeaning {
        subject system : Anything;
        doc /* The subject shall behave. */
    }
    verification def VacuousCase {
        objective {
            doc /* Demonstrate it. */
            verify someRequirement;
        }
    }
}
"""
    findings = policy_findings(Path("example.sysml"), source)
    assert len(findings) == 4
    assert sum("no directly owned required constraint" in finding for finding in findings) == 2
    assert sum("outside a required constraint" in finding for finding in findings) == 2


def test_braces_inside_documentation_do_not_change_ownership_depth() -> None:
    source = """
package Example {
    requirement def BracedWords {
        subject system : Anything;
        require constraint { doc /* The value { shall } remain meaningful. */ }
    }
}
"""
    assert policy_findings(Path("example.sysml"), source) == ()
