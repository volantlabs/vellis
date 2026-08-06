# Model and Implementation Handoff

## Contents

- [Purpose](#purpose)
- [Produce an implementation-ready handoff](#produce-an-implementation-ready-handoff)
- [Expose implementation leverage without prescribing code](#expose-implementation-leverage-without-prescribing-code)
- [Judge readiness](#judge-readiness)
- [Receive implementation feedback](#receive-implementation-feedback)
- [Preserve the authority boundary](#preserve-the-authority-boundary)

## Purpose

Use the handoff to preserve reasoning across model and implementation work. It is a task-local
navigation and evidence aid, not another product contract. Keep the current textual SysML model as
system authority and make every handoff claim reproducible from qualified elements, the active
baseline and change set, and decisive examples.

Produce this handoff when the user asks for implementation readiness, an accepted semantic slice will
move into code, or a model change has implementation impact. Do not force it into unrelated modeling
answers.

## Produce an implementation-ready handoff

Report only the affected semantic closure. Include:

1. **Baseline and scope:** active model baseline, current change set, stakeholder outcome, scope read,
   and the bounded semantic slice prepared for implementation.
2. **Authority:** qualified contextual use cases, domain elements, behaviors, logical
   responsibilities, requirements, satisfiers, analysis or verification cases, and selected
   external boundaries that jointly carry consequential meaning. Cite source locations; do not copy
   their complete prose.
3. **Coverage and remaining authority:** for every cited element, state whether the slice covers all
   of its obligations (`full`) or only a bounded subset (`partial`). When coverage is partial, name
   the obligations that remain outside the slice. Coverage describes the slice's claim against model
   authority; it does not describe implementation progress.
4. **Implementation obligations:** observable distinctions code must preserve, including only the
   applicable identity, ownership, multiplicity, equality, state, mode, ordering, timing, units,
   precision, concurrency, interaction, safety, security, resource, failure, and compatibility
   semantics.
5. **Decisive cases:** smallest nominal, alternate or failed, and plausible-invalid cases for each
   important distinction, including promised non-effects.
6. **Conformance-evidence intent:** tests, analyses, simulations, inspections, demonstrations,
   numerical references, timing measurements, hardware evidence, or other observations that
   discriminate a conforming implementation. Reuse modeled analysis or verification across several
   obligations where appropriate; do not prescribe one test per model element.
7. **Selected boundaries and explicit deferrals:** fixed external names or interaction meaning,
   stakeholder decisions already made, and realization decisions deliberately left to implementation.
8. **Readiness and impact:** whether the slice is ready, what existing implementation it affects,
   compatibility consequences, and the exact unresolved model issue if it is not ready.

Use a compact task-local matrix when several obligations repeat:

| Qualified authority | In-scope obligation | Authority coverage | Remaining obligation | Decisive case and conformance-evidence intent | Required non-effect, open realization, or non-goal |
| --- | --- | --- | --- | --- | --- |

Rows represent independently reviewable claims, not declarations. One row may cite several model
elements, and one element may support several rows. Keep `Authority coverage` and `Remaining
obligation` as distinct fields rather than folding the remainder into evidence, deferrals, or
non-goals. Coverage is evaluated against the complete meaning of each cited accepted authority
element, never only the task prompt or the obligation summarized in the row. `full` requires
`Remaining obligation` to be `none`; if any obligation carried by a cited element remains outside the
slice, use `partial` and name it. Do not assign coverage to a merely prospective element or unresolved
model gap; report that readiness blocker separately. A bounded slice may close with partial coverage,
but it must not claim that the whole cited requirement is satisfied or the whole cited verification
case has passed.

## Expose implementation leverage without prescribing code

The systems model need not decompose every semantic concern into a part. Help implementation agents
see useful cohesion by naming, when applicable:

- semantic neighborhoods whose invariants, calculations, transformations, or transitions change
  together;
- pure computation that can be isolated from state mutation, interaction, or platform code;
- public or environmental interactions versus internal behavior;
- dependencies among identity, values, units, validation, state, time, resources, interaction, and
  evidence;
- coordination rules that several software components must preserve together;
- the single modeled lifecycle, state, timing, safety, failure, physical, or external boundary those
  neighborhoods remain inside.

Call these **implementation cohesion cues**, not logical parts, allocations, services, or prescribed
classes. They may justify a many-to-many software realization projection: one modeled responsibility
can use several code components, and one code mechanism can realize several model elements. Do not
invent system structure merely to make that mapping one-to-one.

State the boundary that finer code must not fracture. For example, isolating conformance calculations
in a class must not create an independent source of authoritative state. Splitting an embedded
control responsibility among sensing, estimation, and actuation modules must not weaken a modeled
deadline, interlock, or safe-state obligation.

## Judge readiness

Declare a slice implementation-ready when the current model can distinguish conforming from
nonconforming system behavior and supplies decisive evidence intent. Confirm, as applicable:

- system boundary, relevant actors, subjects, conditions, stimuli, inputs, outputs, effects, and
  nominal or alternate outcomes are unambiguous;
- identity, occurrence ownership or sharing, multiplicity, equality, collection, and absence
  semantics are strong enough for the slice;
- every relevant state, mode, transition, and promised non-effect has a governing authority;
- calculations have adequate inputs, units, ranges, precision, tolerance, or uncertainty where
  those affect the outcome;
- interactions have adequate direction, carried content, ordering, timing, reliability, or physical
  meaning where those affect the outcome;
- safety, security, privacy, resource, durability, recovery, and compatibility obligations are
  explicit only where required;
- consequential requirements have compatible subjects, selected satisfiers where applicable, and
  analysis or verification paths;
- nominal, alternate or failed, and invalid examples do not require an unmodeled stakeholder
  decision;
- intentionally open realization decisions are explicit.

Do not block readiness merely because the model omits a class hierarchy, module boundary, algorithm,
storage design, serialization, framework, deployment, user-interface structure, or generated-source
shape. Those are implementation decisions unless their observable consequences or realization
boundaries are intentionally selected.

Do not demand persistence, transactions, networking, authorization, concurrency, real-time behavior,
physical interaction, or failure recovery from every project. Do not declare readiness when one of
those dimensions is consequential and code would have to guess its system meaning.

## Receive implementation feedback

Require current, reproducible evidence rather than architecture preference. First ask whether the
affected behavior or boundary is represented or intentionally selected in current model authority,
and whether the evidence shows a consequential stakeholder-visible distinction that the model cannot
decide. Unselected storage, acknowledgement, process, transport, framework, and deployment mechanics
remain realization decisions unless a demonstrated consequence crosses that gate.

For example, a crash between durable commit and delivery of a success response is not by itself a
model gap. It becomes model work only when accepted authority promises response delivery, retry
reconciliation, idempotent result semantics, or another observable distinction that the current model
cannot decide. A durability or restart-continuity obligation alone governs committed state, not an
unselected acknowledgement channel.

Classify feedback before editing the model:

| Feedback | Model response |
| --- | --- |
| The model form is unfamiliar or ambiguous to the reader | Resolve a language question through the reference skill before changing model or code |
| Existing code contradicts sufficient authority | Preserve the model; return an implementation defect |
| Several implementations preserve the same meaning | Leave the model open; record a realization decision in implementation work |
| The model cannot distinguish required system outcomes | Reopen the affected semantic slice |
| A demonstrated feasibility constraint changes an observable outcome or selected boundary | Present the changed consequence for stakeholder and model review |
| Source structure merely differs from model vocabulary | Do not transcribe it into the model; it is a realization decision when a decision is needed |
| Model and feedback use different baselines | Classify a stale baseline and refresh both before deciding |
| Requested behavior is outside the accepted model and task scope | Record an out-of-scope disposition, not a divergence |

For a genuine model gap, begin again with the stakeholder or engineering question and carry the
change through the minimum affected context, behavior, domain meaning, responsibility, requirement,
satisfaction, analysis, and verification path. Not every layer needs a new element. For an
implementation defect, return qualified authority and the failing case; do not weaken the model to
fit the defect.

Translate implementation vocabulary upward before editing. Replace statements such as “this class
needs another field,” “this callback can race,” or “the framework cannot return this type” with the
unresolved system-level distinction, smallest failing instance, and differing observable
consequences. Then choose the strongest appropriate authority: native domain, behavior, interaction,
state, calculation, or relationship semantics; requirement and evidence; or an intentionally
selected external boundary. The software fix may still use a new class, lock, buffer, field, adapter,
or process. That alone never requires a modeled subsystem or feature.

Treat numerical limits, timing, resources, dependencies, platforms, and physical constraints as
engineering evidence. Promote them to model meaning only when the system must promise or expose their
consequence, or when the stakeholder intentionally selects the realization boundary.

## Preserve the authority boundary

- Do not map packages to modules, parts to services or classes, items to records or tables, actions
  to methods, ports to private interfaces, or verification cases to individual tests by name alone.
- Do not make the handoff a permanent parallel requirements document, schema, architecture, or
  implementation inventory. Refresh it from the current model and discard stale versions.
- Do not infer that implementation completeness requires one artifact for every model layer. Trace
  claims through existing authority without mechanical symmetry.
- Do not let tests, framework schemas, generated types, source layout, or runtime limitations
  silently select the living model's vocabulary or topology.
- Do let implementation evidence expose real ambiguity, contradiction, unrealizability, or a newly
  consequential stakeholder choice. Record the prior decision, new evidence, and changed consequence
  when reopening model meaning.

End the handoff by distinguishing modeled, selected, implemented, verified, and runnable. Model
completion alone never claims that source exists.
