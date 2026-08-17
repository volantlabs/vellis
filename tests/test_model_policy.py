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
        require constraint { doc /* The subject shall behave. */ }
    }
    verification def NamedCase {
        objective demonstrateBehavior {
            require constraint { doc /* Demonstrate the required behavior. */ }
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
