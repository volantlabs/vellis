"""Evidence for ``VellisVerification::stringPatterns``.

The whole-string obligation is the one a familiar regular-expression API gets wrong by
default: ``search`` and ``match`` both accept a prefix. Each rejection case below states
the permissive behavior it rules out.
"""

from __future__ import annotations

import pytest

from vellis.definitions import (
    AnchorTypeDefinition,
    AssociatedDataTypeDefinition,
    GraphDefinitionSet,
    PropertyConstraint,
    StringPattern,
    ValueRange,
    ValueShape,
    validate_definition_set,
)
from vellis.json_value import JsonKind, normalize
from vellis.patterns import PatternError, compile_pattern
from vellis.validation import validate_property_value

YEAR = "[0-9]{4}"


def test_whole_string_match_rejects_prefix_and_suffix() -> None:
    """Excludes ``search`` and ``match`` semantics, which accept a longer string."""
    compiled = compile_pattern(YEAR)
    assert compiled.matches("2026")
    assert not compiled.matches("2026-08")
    assert not compiled.matches("in 2026")
    assert not compiled.matches("202")


def test_perl_classes_carry_re2_ascii_meaning() -> None:
    """RE2 defines these over ASCII; this engine widens them to Unicode unless expanded.

    Excludes accepting values the modeled language forbids, and keeps the two spellings
    of one RE2 class from disagreeing with each other.
    """
    word = compile_pattern(r"\w+")
    assert word.matches("cafe_1")
    assert not word.matches("caf\u00e9")
    assert compile_pattern("[[:word:]]+").matches("cafe_1")
    assert not compile_pattern("[[:word:]]+").matches("caf\u00e9")

    digits = compile_pattern(r"\d+")
    assert digits.matches("2026")
    assert not digits.matches("\u0663\u0664")

    spaces = compile_pattern(r"\s+")
    assert spaces.matches(" \t\n")
    assert not spaces.matches("\u00a0")

    assert compile_pattern(r"\D+").matches("abc")
    assert not compile_pattern(r"\D+").matches("a1")


def test_anchors_mean_end_of_text_not_end_of_line() -> None:
    """Excludes this engine's ``$``, which also matches before a trailing newline."""
    assert compile_pattern("^a$").matches("a")
    assert not compile_pattern("a$").matches("a\n")


def test_re2_reads_an_open_lower_repetition_as_literal_text() -> None:
    """Excludes the standard library's reading of ``{,5}`` as the repetition ``{0,5}``."""
    pattern = compile_pattern("a{,5}")
    assert pattern.matches("a{,5}")
    assert not pattern.matches("aaa")


@pytest.mark.parametrize(
    "expression",
    [
        "(?=abc)abc",
        "(?!abc)def",
        "(?<=a)b",
        "(?<!a)b",
        r"(a)\1",
        "(?>abc)",
        "(?#comment)a",
    ],
)
def test_re2_unsupported_constructs_are_rejected(expression: str) -> None:
    """Excludes accepting a backtracking-only expression that RE2 itself would refuse."""
    with pytest.raises(PatternError):
        compile_pattern(expression)


@pytest.mark.parametrize("expression", ["[unclosed", "a{2,1}", "a**", "\\"])
def test_malformed_expressions_are_rejected(expression: str) -> None:
    with pytest.raises(PatternError):
        compile_pattern(expression)


def _constraint(**overrides: object) -> PropertyConstraint:
    base: dict[str, object] = {
        "property_name": "year",
        "required": False,
        "json_kind": JsonKind.STRING,
        "description": "The four-digit year.",
        "pattern": StringPattern(expression=YEAR),
    }
    base.update(overrides)
    return PropertyConstraint(**base)  # pyright: ignore[reportArgumentType]


def test_present_value_must_match_and_absent_optional_is_accepted() -> None:
    constraint = _constraint()
    assert validate_property_value(constraint, normalize("2026")) == ()
    assert validate_property_value(constraint, normalize("2026-08")) != ()


def test_pattern_size_and_permitted_values_all_apply() -> None:
    """Excludes short-circuiting after the first satisfied condition."""
    constraint = _constraint(
        value_shape=ValueShape(minimum_size=4, maximum_size=4),
        value_range=ValueRange(permitted_values=(normalize("2025"), normalize("2026"))),
    )
    assert validate_property_value(constraint, normalize("2026")) == ()
    assert validate_property_value(constraint, normalize("2027")) != ()


def test_a_permitted_value_its_own_pattern_rejects_is_an_invalid_definition() -> None:
    """Excludes validating stored values only and never the rules against each other."""
    findings = validate_definition_set(
        _definition_set(
            _constraint(
                value_range=ValueRange(permitted_values=(normalize("2026"), normalize("later")))
            )
        )
    )
    assert any("its own pattern does not match" in finding.summary for finding in findings)


@pytest.mark.parametrize(
    "kind",
    [JsonKind.NUMBER, JsonKind.BOOLEAN, JsonKind.NULL, JsonKind.ARRAY, JsonKind.OBJECT],
)
def test_pattern_on_a_non_string_property_is_invalid(kind: JsonKind) -> None:
    findings = validate_definition_set(_definition_set(_constraint(json_kind=kind)))
    assert any("carries a string pattern" in finding.summary for finding in findings)


def test_malformed_pattern_makes_the_definition_set_invalid() -> None:
    findings = validate_definition_set(
        _definition_set(_constraint(pattern=StringPattern(expression="(?<=a)b")))
    )
    assert any("invalid pattern" in finding.summary for finding in findings)


def test_active_expression_text_is_discoverable_exactly() -> None:
    """Excludes storing a compiled or rewritten form in place of the authored text."""
    definitions = _definition_set(_constraint(pattern=StringPattern(expression=YEAR)))
    stored = definitions.associated_data_types[0].property_constraints[0].pattern
    assert stored is not None
    assert stored.expression == YEAR


def _definition_set(constraint: PropertyConstraint) -> GraphDefinitionSet:
    return GraphDefinitionSet(
        anchor_types=(AnchorTypeDefinition(type_key="person", description="A person."),),
        associated_data_types=(
            AssociatedDataTypeDefinition(
                type_key="note",
                permitted_anchor_type_keys=("person",),
                property_constraints=(constraint,),
                description="A note about a person.",
            ),
        ),
    )


@pytest.mark.parametrize(
    ("expression", "value", "expected"),
    [
        ("[[:digit:]]{4}", "2026", True),
        ("[[:digit:]]{4}", "d]]]]", False),
        ("[[:alpha:]]+", "abc", True),
        ("[[:alpha:]]+", "ab1", False),
        ("[[:alnum:]_]+", "a_1", True),
        ("[[:space:]]+", " \t", True),
        ("[[:upper:]][[:lower:]]+", "Ada", True),
        ("[[:xdigit:]]+", "beef", True),
        ("[[:xdigit:]]+", "ghij", False),
    ],
)
def test_posix_classes_mean_what_re2_says_they_mean(
    expression: str, value: str, expected: bool
) -> None:
    """Excludes passing POSIX classes to an engine that reads them as a set of punctuation."""
    assert compile_pattern(expression).matches(value) is expected


@pytest.mark.parametrize("expression", ["a*+", "a++", "a{2,3}+", "(ab)*+"])
def test_possessive_quantifiers_are_refused(expression: str) -> None:
    """RE2 has no possessive quantifier; this engine does, and would match differently."""
    with pytest.raises(PatternError, match="bad repetition operator"):
        compile_pattern(expression)


def test_lazy_quantifiers_remain_available() -> None:
    """The possessive check must not catch RE2's ordinary non-greedy forms."""
    assert compile_pattern("a+?").matches("aaa")
    assert compile_pattern("a??").matches("")


def test_the_re2_end_of_text_anchor_is_the_accepted_spelling() -> None:
    """``\\Z`` is not RE2 syntax; ``\\z`` is."""
    with pytest.raises(PatternError, match="invalid escape sequence"):
        compile_pattern(r"abc\Z")
    assert compile_pattern(r"abc\z").matches("abc")


def test_the_full_re2_language_is_available_to_the_owner() -> None:
    """The model selects RE2 syntax, so these must be usable in a property constraint.

    Every one of these is rejected by the standard library engine, so this case is what
    keeps the realization from quietly narrowing the owner's vocabulary.
    """
    greek = compile_pattern(r"\p{Greek}+")
    assert greek.matches("αβ")
    assert not greek.matches("ab")

    assert compile_pattern(r"\b\w+\b").matches("abc")
    assert compile_pattern("[[:^digit:]]+").matches("abc")
    assert not compile_pattern("[[:^digit:]]+").matches("a1")
    assert compile_pattern("a((?i)b)c").matches("aBc")
    assert compile_pattern("(?<year>[0-9]{4})").matches("2026")


def test_the_stored_expression_is_the_authored_text() -> None:
    """Excludes storing a compiled or rewritten form in place of what the owner wrote."""
    expression = r"(?<year>\p{Nd}{4})"
    assert compile_pattern(expression).expression == expression


def test_unencodable_expression_text_becomes_a_finding_not_an_exception() -> None:
    """The engine encodes to UTF-8; its failure must reach the caller as a PatternError."""
    with pytest.raises(PatternError, match="not encodable text"):
        compile_pattern("a" + chr(0xD800))
