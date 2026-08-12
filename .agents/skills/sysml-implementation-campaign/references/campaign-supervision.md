# Campaign Supervision

## Separate manager and worker contexts

Use a context-light manager for campaign continuity and a fresh worker for each slice or closure
attempt. The manager may remain long-running, but it must reconstruct every decision from the
validated campaign record and project checkpoint rather than conversation memory.

The manager:

1. validates durable state and obtains the project's machine-readable dispatch disposition;
2. launches exactly one fresh worker for the selected slice or closure work;
3. waits for that worker rather than polling while it is live;
4. accepts only the compact result described by
   [Worker-result schema](../assets/campaign-worker-result.schema.json), never reviewer transcripts;
5. independently revalidates durable state and the resulting checkpoint;
6. launches the next fresh worker only when the project reports another ready work item.

The manager does not implement, remediate, review, edit the campaign record, reinterpret a worker's
findings, or select work outside the validated dispatch disposition. It may use a less expensive
model than workers because its decisions are deliberately narrow. Model and provider selection are
harness configuration, not method authority.

The worker consumes exactly one selected slice or closure contract, uses the project's one-writer
mechanism, performs implementation and review, creates at most that work item's checkpoint, returns
one compact result, and terminates. It never selects or starts the following slice.

## Await child work without polling

Launch each child once. Prefer a harness-native blocking join. Run independent children concurrently
only when one blocking join can await all of them; otherwise run them sequentially in the foreground.
Concurrency is an optimization, not a conformance requirement.

Do not spend model turns preserving parent liveness. Never simulate waiting with shell sleeps,
timers, repeated status checks, background no-ops, monitors, or overlapping wait tasks. If a harness
offers only asynchronous children, yield once to its event-driven completion mechanism without
polling. If it offers no completion event, use one bounded foreground wait at a time and inspect
state once after that wait completes. A timeout is a recovery boundary, not a heartbeat.

## Dispatch and recovery

Require a dispatch result to identify the campaign, durable project state, worktree condition,
current checkpoint, selected work item, reason codes, and one of these actions:

- `launch-slice`: start the named ready slice in a fresh worker;
- `resume-slice`: inspect and resume the named active slice in a fresh worker;
- `launch-closure`: run whole-system closure in a fresh worker;
- `await-human`: stop at a declared authority or approval boundary;
- `stop-dirty`: stop because no active work item explains workspace changes;
- `stop-invalid`: stop because durable state does not validate;
- `complete`: stop successfully because closure is committed.

Bind a dispatch to a deterministic state token. The worker must revalidate that token immediately
before its first mutation. A changed token invalidates the launch and prevents a stale or duplicate
dispatch from claiming the same ready work. This complements rather than replaces the project's
single-writer mechanism.

After a non-successful worker exit, revalidate state before deciding what happened. A valid new
checkpoint wins over the process exit status. Resume explainable active-slice work in a fresh worker;
stop on unexplained changes. For transient launcher or quota failure, wait only when no worker is
live. Stop after three identical failures against the same state token; do not retry unchanged state
indefinitely. Projects may choose the delay and continuation harness.

## Keep handoffs compact

The result reports the work item, outcome, checkpoint, executed checks, review-pair and material-
finding counts, elapsed time, optional usage measurements, and a pause or failure reason. It does
not contain raw findings, review transcripts, implementation narratives, or hidden recovery notes.
Those details belong in reproducible project artifacts or the work item's durable checkpoint.

Store operational telemetry outside authored model authority and the approved plan projection.
Telemetry may compare duration, checks, review convergence, and harness usage, but it cannot establish
conformance or authorize campaign advancement.
