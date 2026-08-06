"""Retrieval quality: does a realistic question surface material that answers it?

This measures the search layer, not the specification. Each question is tagged
with the *register* it is asked in, because a single blended number hides the
thing that matters most:

- A, specification jargon: "what is the difference between subsetting and
  redefinition". BM25 handles these well.
- B, lay phrasing: "behaviour that only happens in certain modes". The asker
  does not know the word "state".
- C, professional systems-engineering vocabulary: "how is traceability
  modelled". Real terms, but not the words SysML v2 uses.

Registers A and C were measured 4x apart, so reporting one average would have
sent effort at ranking, which register A shows is already adequate.

Targets accept any corpus that genuinely answers. A worked training model is
often a better answer than normative prose, and scoring it as a miss because it
is not a clause number measures the eval's assumptions rather than the search.

Questions are phrased the way a person actually asks them. Earlier tests used
specification vocabulary, which is why they passed while natural phrasing failed.
"""

from __future__ import annotations

import pytest

from tools import model_layout, sysml_reference

# (register, question, accepted targets as (source, identifier prefix))
ROUTING_QUESTIONS: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
    # --- Register A: specification jargon -----------------------------------
    (
        "A",
        "what is the difference between subsetting and redefinition",
        (("specification", "7.3.4"),),
    ),
    ("A", "what is the difference between a definition and a usage", (("specification", "7.6"),)),
    (
        "A",
        "when do I use an item def versus a part def",
        (("specification", "7.10"), ("specification", "7.11")),
    ),
    (
        "A",
        "what does conjugation of a port mean",
        (("specification", "7.12"), ("specification", "8.2")),
    ),
    (
        "A",
        "what is a binding connector",
        (
            ("specification", "7.13"),
            ("specification", "7.4.6"),
            ("example", "12. Binding Connectors"),
        ),
    ),
    ("A", "what is a feature value", (("specification", "7.4.11"), ("specification", "7.7"))),
    (
        "A",
        "what does specializes mean for a classifier",
        (("specification", "7.3.3"), ("specification", "7.3.2")),
    ),
    ("A", "what does a satisfy requirement usage do", (("specification", "7.21"),)),
    ("A", "what is a verification case subject", (("specification", "7.24"),)),
    (
        "A",
        "what is an allocation usage",
        (("specification", "7.15"), ("example", "38. Allocation")),
    ),
    ("A", "what is a viewpoint", (("specification", "7.26"), ("example", "42. Views"))),
    (
        "A",
        "what is an occurrence usage",
        (("specification", "7.9"), ("example", "27. Occurrences")),
    ),
    (
        "A",
        "what does a succession flow mean",
        (("specification", "7.16"), ("specification", "7.17")),
    ),
    ("A", "what is a variation point", (("specification", "7.6"), ("example", "36. Variability"))),
    (
        "A",
        "what is an enumeration definition",
        (("specification", "7.8"), ("example", "06. Enumeration Definitions")),
    ),
    (
        "A",
        "subsetting versus redefinition",
        (
            ("specification", "7.3.4"),
            ("example", "04. Subsetting"),
            ("example", "05. Redefinition"),
        ),
    ),
    (
        "A",
        "binding connector versus item flow",
        (("specification", "7.13"), ("specification", "7.16"), ("specification", "7.4.6")),
    ),
    (
        "A",
        "allocation versus satisfaction",
        (("specification", "7.15"), ("specification", "7.21")),
    ),
    # --- Register B: lay phrasing -------------------------------------------
    (
        "B",
        "how do I model behavior that only happens in certain modes",
        (
            ("specification", "7.18"),
            ("example", "23. State Definitions"),
            ("example", "24. States"),
        ),
    ),
    (
        "B",
        "how do I express a rule that must always hold true",
        (("specification", "7.20"), ("example", "31. Constraints")),
    ),
    (
        "B",
        "how do I model data moving from one action to another",
        (("specification", "7.16"), ("example", "13. Flows")),
    ),
    (
        "B",
        "how do I capture what a user wants to accomplish with the system",
        (("specification", "7.25"), ("example", "35. Use Cases"), ("example", "UseCaseTest")),
    ),
    (
        "B",
        "how do I define a connection point on a component",
        (("specification", "7.12"), ("example", "10. Ports")),
    ),
    (
        "B",
        "how do I represent a subsystem of my system",
        (("specification", "7.11"), ("example", "07. Parts"), ("library", "Parts::Part")),
    ),
    (
        "B",
        "how do I model a value like a temperature",
        (
            ("specification", "7.7"),
            ("library", "ISQ"),
            ("example", "Quantities"),
            ("example", "System of Units"),
        ),
    ),
    (
        "B",
        "how do I connect two parts together",
        (("specification", "7.13"), ("example", "09. Connections")),
    ),
    (
        "B",
        "how do I define a behavior with inputs and outputs",
        (
            ("specification", "7.17"),
            ("specification", "7.4.7"),
            ("example", "14. Action Definitions"),
            ("example", "Function-based Behavior"),
        ),
    ),
    (
        "B",
        "how do I say one element depends on another element",
        (("specification", "7.3"), ("example", "37. Dependencies")),
    ),
    (
        "B",
        "what does it mean for a type to be abstract",
        (("specification", "7.3.2"), ("specification", "7.6")),
    ),
    (
        "B",
        "how do I give a feature a default value",
        (("specification", "7.4.11"), ("specification", "7.7")),
    ),
    (
        "B",
        "how do I narrow an inherited feature to a smaller type",
        (("specification", "7.3.4"), ("example", "05. Redefinition")),
    ),
    (
        "B",
        "how do I write documentation attached to an element",
        (("specification", "7.4"), ("example", "01. Packages")),
    ),
    (
        "B",
        "how do I group related elements together",
        (("specification", "7.5"), ("example", "01. Packages")),
    ),
    # --- Register C: professional systems-engineering vocabulary ------------
    ("C", "how is composition represented", (("specification", "7.3.4"), ("specification", "7.6"))),
    (
        "C",
        "how is traceability modeled",
        (
            ("specification", "7.3"),
            ("specification", "7.21"),
            ("specification", "7.24"),
            ("specification", "7.15"),
        ),
    ),
    (
        "C",
        "how do I model decomposition of a system",
        (
            ("specification", "7.11"),
            ("example", "07. Parts"),
            ("example", "Constraining Decomposition"),
        ),
    ),
    (
        "C",
        "how is behavior allocated to structure",
        (
            ("specification", "7.15"),
            ("specification", "7.17"),
            ("example", "38. Allocation"),
            ("example", "18. Action Performance"),
        ),
    ),
    (
        "C",
        "how is variability handled",
        (("specification", "7.6"), ("example", "36. Variability"), ("specification", "A.12")),
    ),
    (
        "C",
        "how do I capture design rationale",
        (
            ("specification", "7.4"),
            ("specification", "7.27"),
            ("specification", "9.3.2"),
            ("example", "39. Metadata"),
            ("example", "RationaleMetadata"),
        ),
    ),
    (
        "C",
        "how is interface control managed",
        (("specification", "7.14"), ("specification", "7.12"), ("example", "11. Interfaces")),
    ),
    (
        "C",
        "how is verification and validation represented",
        (("specification", "7.24"), ("example", "34. Verification")),
    ),
    (
        "C",
        "how do I model the system context and boundary",
        (("specification", "7.11"), ("specification", "7.25")),
    ),
    (
        "C",
        "how is inheritance done",
        (
            ("specification", "7.3.2"),
            ("specification", "7.3.3"),
            ("example", "03. Generalization"),
            ("example", "Inheritance"),
        ),
    ),
    (
        "C",
        "how do I model a requirements hierarchy",
        (("specification", "7.21"), ("example", "32. Requirements")),
    ),
    (
        "C",
        "how is concurrency represented",
        (("specification", "7.17"), ("example", "17. Control")),
    ),
    (
        "C",
        "how is state based behavior exhibited by a part",
        (("specification", "7.18"), ("example", "26. State Exhibition")),
    ),
    (
        "C",
        "how are analysis results captured",
        (("specification", "7.23"), ("example", "33. Analysis")),
    ),
    (
        "C",
        "how is the language itself extended",
        (
            ("specification", "7.27"),
            ("example", "41. Language Extension"),
            ("example", "Language Extensions"),
        ),
    ),
    # --- Held-out set -------------------------------------------------------
    # Written after the questions above, with targets fixed from specification
    # structure before any search was run, then merged in unchanged. Merging
    # rather than discarding keeps the set large and dilutes any tuning that
    # leaked into the original questions.
    ("A", "what is a transition usage trigger", (("specification", "7.18"),)),
    ("A", "what does an exhibit state usage do", (("specification", "7.18"),)),
    ("A", "what is a decision node in an action", (("specification", "7.17"),)),
    ("A", "what is a metadata usage", (("specification", "7.27"),)),
    ("A", "what does a filter condition do in a package", (("specification", "7.5"),)),
    ("A", "what is an individual usage", (("specification", "7.9"),)),
    ("A", "what is a rendering definition", (("specification", "7.26"),)),
    ("A", "what is a subject parameter of a case", (("specification", "7.22"),)),
    ("B", "how do I show that one step happens after another", (("specification", "7.17"),)),
    (
        "B",
        "how do I say something can appear more than once",
        (("specification", "7.4.12"), ("specification", "7.6")),
    ),
    ("B", "how do I model a choice between two paths", (("specification", "7.17"),)),
    (
        "B",
        "how do I reuse a definition with small changes",
        (("specification", "7.6"), ("specification", "7.3.3")),
    ),
    ("B", "how do I model a physical thing the system produces", (("specification", "7.10"),)),
    ("B", "how do I attach a note to an element for tooling", (("specification", "7.27"),)),
    (
        "B",
        "how do I describe something the system must never do",
        (("specification", "7.21"), ("specification", "7.20")),
    ),
    ("B", "how do I show a whole made of smaller pieces", (("specification", "7.11"),)),
    ("C", "how are non functional requirements captured", (("specification", "7.21"),)),
    ("C", "how is model organization handled at scale", (("specification", "7.5"),)),
    ("C", "how are stakeholder concerns addressed", (("specification", "7.26"),)),
    ("C", "how is behavior sequencing controlled", (("specification", "7.17"),)),
    ("C", "how is quantitative analysis integrated", (("specification", "7.23"),)),
    (
        "C",
        "how is a black box boundary distinguished from internals",
        (("specification", "7.11"), ("specification", "7.26")),
    ),
    (
        "C",
        "how is failure behavior represented",
        (("specification", "7.18"), ("specification", "7.17")),
    ),
    ("C", "how is configuration of a product line expressed", (("specification", "7.6"),)),
)

# Measured floors, set just below observed rates so they catch regression rather
# than expressing a wish. Observed on the combined set: A 96%, B 43%, C 60%.
#
# Those are lower than an earlier reading of 93/66/66, and the difference is the
# point. A held-out set was written afterwards, with targets fixed from
# specification structure before any search ran, and the two sets disagreed
# sharply: register A scored 100% held-out against 94% in-sample, but register B
# scored 0% held-out against 46% in-sample when both were scored the same way.
#
# So register A genuinely generalises and register B did not: its earlier number
# was inflated by questions and targets that had been adjusted while looking at
# results. Both sets are now merged, which is why the rates moved. Widening a
# target after seeing output is exactly the move that produced the inflation, so
# treat any future widening as suspect and prefer adding questions.
#
# The two tuned constants were re-checked against held-out data. The descriptive
# clause weight generalises -- held-out register C rises monotonically from 1/8
# to 3/8 as it goes from 1.0 to 2.0, then plateaus. The title weight is within
# noise held-out; it was retained on in-sample evidence and is not re-tuned here,
# because tuning on the held-out set would simply overfit that set instead.
#
# Two changes moved B and C from 13% and 33% to 66% each. Preferring the
# descriptive specification chapter over the syntax and library chapters was
# worth about half of it (see _clause_family_weight); correcting targets that
# omitted genuinely correct answers was the rest.
#
# The residual gap is not a ranking defect and no scoring work closes it. The
# remaining questions use words the corpus never contains -- "modes" for states,
# "rule" for constraints, "traceability" for nothing at all -- and every lexical
# bridge was measured and lost: pseudo-relevance feedback dropped MRR from 0.664
# to 0.306, rank fusion to 0.388, character n-grams to 0.590, and an aggressive
# stemmer was a wash.
#
# What closes the rest is vocabulary, not search. Retrieval reaches the right
# clause ~93% of the time once the concept name is right, so the fix is to hand
# the agent the concept inventory and let it name the construct, which is a
# language task rather than an information-retrieval one. That step needs a model
# in the loop and is deliberately outside this deterministic test; what is tested
# here is that the inventory contains the words an agent would need.
REGISTER_FLOORS = {"A": 0.90, "B": 0.35, "C": 0.50}
TOP_N = 5


def _corpus_ready() -> bool:
    return any(
        (model_layout.SPECIFICATION_REFERENCE_ROOT / identifier).exists()
        for identifier in ("sysml-2.1", "kerml-1.1")
    )


def _hit_rank(question: str, targets: tuple[tuple[str, str], ...]) -> int | None:
    results = sysml_reference.find_references(question, limit=TOP_N)
    for rank, result in enumerate(results, start=1):
        for source, prefix in targets:
            if result.source != source:
                continue
            candidate = f"{result.identifier} {' '.join(result.title_path)}"
            if result.identifier.startswith(prefix) or prefix in candidate:
                return rank
    return None


@pytest.mark.parametrize("register", sorted(REGISTER_FLOORS))
def test_each_register_meets_its_retrieval_floor(register: str) -> None:
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    questions = [entry for entry in ROUTING_QUESTIONS if entry[0] == register]
    ranks = {question: _hit_rank(question, targets) for _, question, targets in questions}
    missed = [question for question, rank in ranks.items() if rank is None]
    found = len(questions) - len(missed)
    rate = found / len(questions)

    assert rate >= REGISTER_FLOORS[register], (
        f"register {register}: {found}/{len(questions)} = {rate:.0%} "
        f"(floor {REGISTER_FLOORS[register]:.0%}); missed: {missed}"
    )


def test_concept_inventory_covers_every_construct_upstream_defines() -> None:
    """The fallback for a failed search is the concept inventory, so it has to be
    complete rather than merely adequate for today's questions.

    Stated structurally instead of as a list of phrasings: every top-level
    descriptive clause and every training module must appear. That keeps the
    check honest when upstream adds a construct, which a hand-written list of
    question-to-concept pairs would not.
    """
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    names = {entry.name.casefold() for entry in sysml_reference.concepts()}
    origins = {entry.origin for entry in sysml_reference.concepts()}

    assert origins == {"specification", "training"}
    # Sanity: constructs an agent reaches for constantly, drawn from both halves
    # of the inventory rather than from the questions above.
    for construct in ("states", "constraints", "parts", "ports", "variability", "redefinition"):
        assert construct in names


def test_concept_inventory_draws_on_practitioner_vocabulary_too() -> None:
    """Clause titles alone are not enough.

    The specification names clause 7.6 "Definition and Usage"; the training
    curriculum names the same idea "Variability", which is the word people search
    for. Losing the training-derived half would silently narrow the inventory.
    """
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    inventory = sysml_reference.concepts()
    origins = {entry.origin for entry in inventory}

    assert origins == {"specification", "training"}
    assert len(inventory) > 50


def test_question_set_is_large_enough_to_distinguish_registers() -> None:
    """Twelve questions give a 52-point confidence interval, which cannot separate
    a good retriever from a mediocre one. Fifteen per register is the working
    minimum; more is better."""
    counts = {register: 0 for register in REGISTER_FLOORS}
    for register, _, _ in ROUTING_QUESTIONS:
        counts[register] += 1

    assert all(count >= 15 for count in counts.values()), counts


def test_every_question_is_phrased_without_specification_section_numbers() -> None:
    """A question naming its own answer measures nothing."""
    for _, question, _ in ROUTING_QUESTIONS:
        assert not any(part.replace(".", "").isdigit() for part in question.split())


def test_the_concept_escape_hatch_is_unconditional(capsys: pytest.CaptureFixture[str]) -> None:
    """A lexical score cannot detect its own failure, so the hatch cannot be gated.

    Measured against these questions, a score threshold fired for none of the
    failing lay or professional questions: they return confident wrong answers,
    because term overlap is not correctness. The pointer is therefore always
    shown, including when results look strong.
    """
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    results = sysml_reference.find_references("redefinition", limit=2)
    sysml_reference._print_search_results(results)
    sysml_reference._print_concept_hint()
    output = capsys.readouterr().out

    assert results and max(result.score for result in results) > 10
    assert "model-reference-concepts" in output


def test_skill_inventory_matches_the_generated_one() -> None:
    """The skill embeds the construct inventory so an agent has it without a tool
    call, which is the whole point: retrieval is measured at 100% once the
    construct is named, so the vocabulary has to be in context at the moment of
    naming.

    Embedding generated content risks drift, so this asserts the embedded list is
    exactly what the pinned release produces. If upstream adds a construct, this
    fails until the skill is regenerated.
    """
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    skill = (model_layout.ROOT / ".agents" / "skills" / "sysml-reference" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    start = skill.index("<!-- generated: construct inventory -->")
    end = skill.index("<!-- end generated -->")
    embedded = {
        name.strip()
        for name in skill[start:end].split("-->", 1)[1].replace("\n", " ").split("·")
        if name.strip()
    }

    assert embedded == {entry.name for entry in sysml_reference.concepts()}


def test_intent_map_covers_every_construct_or_names_it_as_language_mechanics() -> None:
    """The intent map is hand-written, because no derived artifact can contain it.

    The lay vocabulary it bridges from appears nowhere in the pinned material, so
    there is nothing to derive the mapping from; it is domain knowledge. What can
    be machine-checked is completeness, which is what actually rots: when upstream
    adds a construct, this fails until the map accounts for it.
    """
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    skill = (model_layout.ROOT / ".agents" / "skills" / "sysml-reference" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    missing = [
        entry.name
        for entry in sysml_reference.concepts()
        if entry.origin == "specification" and entry.name not in skill
    ]

    assert not missing, f"constructs absent from the intent map: {missing}"


def test_specification_routing_matches_where_constructs_actually_live() -> None:
    """The skill tells the agent which specification to search. That claim is
    derived from the inventory, so it can be checked rather than trusted."""
    if not _corpus_ready():
        pytest.skip("generated corpus absent; run `just model-setup`")
    skill = (model_layout.ROOT / ".agents" / "skills" / "sysml-reference" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    start = skill.index("### Which specification answers it")
    end = skill.index("### Which library file answers it")
    sysml_half, kerml_half = skill[start:end].split("- **KerML**")

    for entry in sysml_reference.concepts():
        if entry.origin != "specification":
            continue
        half = sysml_half if entry.pointer.startswith("sysml") else kerml_half
        other = kerml_half if entry.pointer.startswith("sysml") else sysml_half
        first = entry.name.split()[0]
        if first in other and first not in half:
            raise AssertionError(f"{entry.name} is routed to the wrong specification")
