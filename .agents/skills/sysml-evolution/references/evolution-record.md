# Evolution Record

## Contents

- [Authority boundary](#authority-boundary)
- [Baselines and lifecycle](#baselines-and-lifecycle)
- [Findings and decisions](#findings-and-decisions)
- [Work items and evidence](#work-items-and-evidence)
- [Record consistency](#record-consistency)

## Authority boundary

The accepted textual SysML model remains product and system authority. An evolution record is a
baseline-bound index of evidence, classification, decisions, execution, and closure. It does not
restate requirements, define architecture, or make implementation source authoritative.

Keep only stable navigation and decision information in the record:

- source and target baseline identities;
- the evolution objective and observable distinction;
- reproducible findings with qualified authority references;
- classification, disposition, and affected work owner;
- consequential realization decisions;
- dependency-ordered work state, acceptance sets, evidence references, blockers, and checkpoints;
- final synchronization and compatibility status;
- independently attributable review results bound to the exact state reviewed.

Keep transcripts, detailed designs, estimates, assignees, copied model prose, code inventories,
temporary measurements, and reviewer dialogue elsewhere. Evidence references point to reproducible
artifacts or commands using the project's convention.

## Baselines and lifecycle

Bind the record to an accepted source model checkpoint, implementation checkpoint, language baseline
when language meaning is consequential, and selected execution environment when runtime, platform,
toolchain, hardware, or physical setup can change the result. Record the proposed target model and
implementation checkpoints only after they exist.

Record only the baseline the evolution is bound to. Do not store a second copy of what the project
can derive from its current system of record: a stored observation goes stale on every ordinary
change and buys a restamp rather than a fact.

Use these lifecycle meanings:

- `discovery`: evidence and scope are still being collected;
- `planning`: findings are classified and work is being derived;
- `awaiting-approval`: changed model meaning or a project-selected consequential decision awaits its
  required human gate;
- `ready`: approval is satisfied and one or more dependency-ready work items may start;
- `active`: exactly one work item owns mutation;
- `blocked`: a genuine blocker prevents safe progress;
- `stale`: a bound source, target, language, or implementation baseline changed unexpectedly;
- `complete`: findings, authority, implementation, evidence, documentation, and baseline closure all
  reconcile.

Approval is not always required. Record it on the work item whose consequence needs the gate. A code
defect under sufficient accepted authority can proceed under the project's normal change
authorization while an independent model change waits. Changed system meaning, a selected external
boundary, or a project-designated material realization decision uses explicit approval. The
evolution-level approval is a roll-up, not permission for every item. Record `not-required` rather
than manufacturing approval evidence.

## Findings and decisions

Each finding has one stable ID, raw evidence, consequence, qualified authority references,
classification, disposition, and its work-item owner. The wrong behavior a finding is closed against
belongs to the owning work item's acceptance set, not to a second prose field beside it. Classify by the needed response:

| Classification | Meaning and route |
| --- | --- |
| `language question` | Resolve model-language meaning before changing authority or code. |
| `model gap` | Current accepted authority cannot distinguish consequential conforming behavior. |
| `plan gap` | Accepted meaning is sufficient, but planned work, ownership, dependency, or evidence is incomplete. |
| `feasibility consequence` | Demonstrated realization limits change stakeholder-visible behavior or a selected boundary. |
| `implementation defect` | Current implementation or evidence contradicts sufficient accepted authority. |
| `realization decision` | Several implementations preserve accepted meaning; select the smallest sufficient choice. |
| `stale baseline` | Evidence or work was derived from superseded authority or implementation. |
| `external dependency` | Required progress depends on state outside project authority. |
| `out of scope` | The request is neither an active obligation nor part of this evolution objective. |

One observation may yield several findings. For example, slow behavior may expose both an existing
complexity-obligation violation and a separate missing resource promise. Conversely, several raw
measurements may support one root-cause finding. Keep classification at the independently actionable
consequence.

Record a consequential realization decision only when later work or review must preserve it. Include
the authority it preserves, selected choice, smallest plausible alternatives, reversibility,
and completion owner. The wrong realization it is closed against belongs to the owning work item's
acceptance set. Status and evidence advance during execution; the selected meaning and owner are
planning state.

## Work items and evidence

Cut work by end-to-end semantic effect:

- `modeling` closes changed system meaning and produces accepted target authority;
- `implementation` realizes one bounded accepted semantic slice;
- `integration` proves several changed slices preserve their shared boundaries;
- `closure` reconciles the complete evolution set, external behavior, documentation truth, and new
  baseline.

Do not create setup, layer, table, service, or refactoring work items without an independently
verifiable semantic or engineering outcome. A work item may own several compatible findings, but
every finding and selected decision has exactly one completion owner.

Fix an acceptance set before dispatch: numbered entries naming the specific wrong behaviors the work
must make impossible, each bound to one piece of evidence the item carries. The set closes at
dispatch and the working agent does not extend it. A complete item carries no evidence that no entry
claims. Use implementation status `not evaluated`, `absent`, `partial`, `conforming`, or
`conflicting`.
Use `not applicable` only for a dimension the affected system or change genuinely does not have.

Evidence must discriminate the nearest plausible wrong system. Parsing, type checking, test counts,
coverage percentages, elapsed time without conditions, or a nominal example alone do not close a
semantic finding. Include resource, timing, concurrency, safety, security, durability, recovery,
simulation, hardware, or compatibility evidence only where the affected obligation requires it.

## Record consistency

A project validator should reject at least:

- duplicate IDs or unknown references;
- a ready or active record with stale baselines or unsatisfied required approval;
- more than one active work item or a work item active before its dependencies complete;
- resolved findings or conforming decisions without an owner and attributable evidence;
- completed work with open owned findings or decisions, blockers, or no checkpoint;
- complete evolution with open findings, nonconforming authority or integration, required external
  behavior unevaluated, stale target baselines, or no final checkpoint.

For every completed review, retain its declared lens, independent reviewer identity, reviewed-state
checkpoint, reviewed scope, disposition, and reproducible evidence references. Reviews are an
append-only log, so a lens may appear more than once and the latest entry per lens decides; closure
requires a clean latest entry for every declared lens. A clean status label without those bindings is
not review evidence. Every finding, including an accepted or out-of-scope disposition, retains exactly one work
item that owns its disposition and closure.

The bundled schema checks shape, not project history or semantic truth. Bind stronger baseline,
checkpoint, authority-reference, evidence-reference, and approval validation in the project.
