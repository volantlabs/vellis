# Use-case-first model-as-code development

Vellis treats textual SysML v2 like source code: the model on a branch is the current system
definition, and a pull request is the unit of change and review.

## Breadth before depth

Begin with the owner, external actors, system boundary, and independently valuable outcomes. An
encompassing journey may compose those outcomes but should not erase their different success,
failure, state, or evidence semantics.

## One semantic slice

Start each change with one owner or engineering question. Refine only the affected black-box behavior,
then add the domain meaning and minimal native representation needed to make it precise. Derive actions
when they add ordering, reuse, state, failure, interaction, or verification meaning; group capabilities
before considering structural parts.

Trace the changed claim through applicable requirements, explicitly named satisfiers, and decisive
verification. Reuse current elements when they already carry the meaning; do not create one artifact
per layer merely to make the path look complete.

Treat the path as a reasoning order, not a completeness template. Elaborate query, state, history,
architecture, interfaces, or realization only when the current question changes them. Stop when the
slice is closed; exhaustive representation is not the same as engineering rigor.

An undecided realization is not optional system behavior. Keep it open in the PR or issue rather than
modeling interchangeable parts, variants, or configuration. Likewise, tool and framework operations
are implementation affordances, not an automatic use-case or action inventory.

When an external operation inventory is intentionally selected as product meaning, model those
callable behaviors directly and keep them distinct from internal functional decomposition. A staged
interaction such as shallow discovery followed by focused inspection justifies separate actions only
because the first bounded result supplies information needed to formulate the second.

## Proportionality and continuity

Common enterprise architectures, framework examples, and popular repository patterns are possible
solutions, not neutral starting points. Add a model element only when it expresses a current owner
consequence, compatibility obligation, or implementation-blocking semantic ambiguity in the
selected slice.

Preserve explicit owner decisions and deliberate deferrals across review rounds. An explicit review
may reassess claims in its scope; otherwise reopen a decision only when new evidence creates a
concrete contradiction, and record what consequence changed. Do not mistake incidental tests,
comments, or existing structure for owner decisions. Prefer natural identity, derived facts, one
authoritative relationship rule, and bounded agent interactions before introducing surrogate IDs,
stored flags, parallel schemas, universal envelopes, or operational machinery.

## Semantic closure

Walk changed inputs forward into outputs, state, revision, and history. Walk every returned value,
state effect, responsibility, and requirement backward to the owner outcome and model element that
authorizes it. Confirm shared occurrences have one owner and deliberate references elsewhere. Inspect
nested owned payloads rather than only direct feature names, and define the concrete instance meaning
of each returned row—including projection completeness, duplicates, absence, and null.

## Adequacy and subtraction

Review adequacy before subtraction. Preserve independent outcomes, state authority, failure behavior,
recovery meaning, and verification; then remove elements that express no necessary claim or exclude no
invalid design. The goal is semantic compression: fewer elements with all consequential distinctions
intact.

## Evidence and review

Use the pinned official specifications for consequential language decisions and the official validator
for language conformance. Review the full model diff, requirements closure, verification evidence, and
unsupported commitments separately. Put unresolved work in an issue or PR discussion rather than a
model status system or parallel design document.

For an approved formal plan, map each mandatory claim and non-goal to its authoritative model or
guidance location and decisive evidence. After the last correction, repeat plan conformance, semantic
closure, adequacy, subtraction, and repository-truth review as one full cycle; completion requires a
cycle that finds no new material issue.
