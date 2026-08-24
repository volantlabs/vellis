# Porting the SysML v2 MBSwE core to a fresh repository

This describes everything needed to reproduce the model-as-authority experience — pinned SysML v2
reference, formal validation, the modeling and implementation method, and the durable evolution
record — in a repository that is not Vellis.

The core is portable by construction: the four core skills contain no Vellis paths, commands, RTG or
MCP vocabulary, programming language, or architecture, and a test enforces that. What binds them to a
project is one small file, two lock files, and a set of `just` recipes. Everything else is either
copied verbatim or is Vellis-specific and left behind.

Read this top to bottom once. The layers build on each other, and each is usable without the next.

---

## What you get, in layers

| Layer | Gives you | Copy cost |
| --- | --- | --- |
| 1. Reference | Pinned SysML v2/KerML spec, standard library, examples, searchable corpus | 3 tools + 2 locks + 1 skill |
| 2. Validation | Formal parse against the official pilot implementation | already present after layer 1 |
| 3. Method | Modeling, implementation, and altitude guidance for humans and agents | 3 skills |
| 4. Record | Durable findings, decisions, acceptance sets, review log | 1 skill + 3 tools |
| 5. Hygiene | Skill validation, doc sync, repository policy | 3 tools + 1 skill |

You can stop after any layer. Layer 1 alone already prevents the single most common failure: an agent
answering SysML questions from training data, which is dominated by SysML v1 and UML.

---

## Prerequisites

- **Python 3.14+** and [`uv`](https://docs.astral.sh/uv/). The tooling uses PEP 695 `type` statements
  and PEP 758 unparenthesized `except` tuples, so an older interpreter will report syntax errors on
  valid code.
- **[`just`](https://github.com/casey/just)** for the recipes. Optional — every recipe is a one-line
  `uv run python …` you can invoke directly.
- **`git`** on `PATH`. Setup performs a blobless sparse clone of the upstream release repository;
  this is not an archive download.
- **No Java install needed.** Setup downloads a checksum-pinned Temurin JRE into the ignored cache.
- **Network access on first run only**, to reach `github.com`. Everything afterwards is local.

Python dependencies actually required by the core tooling, verified by walking its imports:

| Package | Needed by |
| --- | --- |
| `jupyter-client` | `sysml_validator.py` — the official pilot implementation runs as a Jupyter kernel |
| `pypdf` | `sysml_reference.py` — extracting the specification PDFs into the search corpus |
| `pyyaml` | the evolution record and skill frontmatter |
| `jsonschema` | validating the evolution record against its schema |

Vellis's other dependencies (`fastmcp`, `pydantic`, `uvicorn`, `google-re2`, `ijson`) belong to the
product, not the core.

---

## Layer 1 — Pinned reference

**Copy:**

- `tools/sysml_reference.py`
- `tools/sysml_validator.py` — its `setup` drives the clone that supplies the corpus
- `tools/model_layout.py` (shared by every layer; see [Binding](#binding-the-core-to-your-project))
- `model/config/language.lock.json` and `model/config/validator.lock.json`
- `.agents/skills/sysml-reference/` (whole directory)

**Recipes:**

```
model-setup:              uv run python tools/sysml_validator.py setup
                          uv run python tools/sysml_reference.py render
model-reference-find:     uv run python tools/sysml_reference.py find
model-reference-concepts: uv run python tools/sysml_reference.py concepts
model-reference-render:   uv run python tools/sysml_reference.py render
model-reference-check:    uv run python tools/sysml_reference.py check
```

### What setup actually fetches

`just model-setup` is two steps and needs no manual intervention:

1. **`sysml_validator.py setup`** performs a **blobless sparse clone** of
   `github.com/Systems-Modeling/SysML-v2-Release.git`, pinned to an exact commit, restricted to four
   paths — the two specification PDFs, plus `sysml/src/**` and `kerml/src/**` for the standard
   library, examples, and training models. Blobless keeps it small; sparse keeps it to what the
   reference layer reads; the single pinned commit is what makes the specifications and the library
   agree with each other rather than being assembled from separate downloads. It then fetches the
   pilot-implementation kernel jar and a platform-matched Temurin JRE from
   `SysML-v2-Pilot-Implementation` releases, verifying every artifact against its recorded checksum.
   Re-running is cheap: if the checkout is already at the pinned commit, it is left alone.
2. **`sysml_reference.py render`** extracts the PDFs and source trees into the searchable corpus the
   skill queries.

Everything lands in the **ignored** `.cache/sysml/` and is never committed — no upstream licence is
redistributed, and the corpus cannot drift from its pin. `just model-reference-check` verifies the
generated corpus still matches.

Note that both locks are needed even for layer 1 alone, because the clone that supplies the
reference corpus is driven by `sysml_validator.py setup`.

To move to a newer SysML release, update the commit, checksums, and versions in the two locks and
re-run setup. Do not hand-edit generated corpora.

**What the skill contributes** beyond the corpus: an intent→construct routing table covering the
whole SysML v2 surface, the distinctions that actually decide a modeling choice, a v1-displacement
reference for forms that *parse cleanly and mean something else*, and worked examples at process,
system, and software altitude.

---

## Layer 2 — Formal validation

**Copy:** nothing further — `sysml_validator.py` and both locks arrived with layer 1. Optionally add
`tools/model_policy.py` (see below).

**Recipes:**

```
model-check:  uv run python tools/sysml_validator.py validate
              uv run python tools/model_policy.py          # optional
model-probe:  uv run python tools/sysml_validator.py probe
```

`validator.lock.json` pins the official pilot implementation, its kernel jar, and a JRE per platform,
all by checksum. `probe` validates a snippet without touching your model — the right tool when an
agent is unsure of syntax and would otherwise guess.

Model files are concatenated in **sorted filename order** before validation, so a numeric prefix
convention (`10-`, `20-`, `30-`…) is load-bearing for dependency order. Keep it.

`model_policy.py` is a small repo-local lint asserting that every `requirement` and `objective` owns
a substantive `require constraint` rather than carrying normative prose in a bare `doc`. It encodes a
house rule, not a language rule. Adopt it or drop it.

---

## Layer 3 — The method

**Copy whole directories:**

- `.agents/skills/sysml-modeling/`
- `.agents/skills/sysml-implementation/`
- `.agents/skills/sysml-evolution/`

These are prose plus one schema and one template. They contain no code and no project bindings.

The governing rules they carry, so you can judge whether you want them:

- **Model at any depth the project means to govern**, including software structure and internal
  interfaces. What is modeled binds implementation; what is unmodeled is the implementer's to choose.
- **Conformance depth follows model depth.** Subdivision inside a modeled boundary is free; a code
  unit spanning two modeled parts is an implementation defect, not a realization decision.
- **Selected structure versus transcribed structure.** Before subtracting, ask what an element
  forbids — name one implementation a competent engineer would otherwise plausibly choose.
  Transcription fails that by construction, because an element derived from existing code forbids
  nothing that code already does.
- **Acceptance sets close at dispatch.** A work item names the specific wrong behaviors it must make
  impossible, each bound to evidence that fails if the behavior is present. A reviewer extends a
  closed set only by reporting a defect the artifact actually exhibits, with a reproduction.
- **Two review pairs per work item**, then escalate rather than iterate.
- **Copilot and autonomous modes differ deliberately.** Copilot spends the human and saves agents —
  ask rather than assume, one reviewer with the human as second lens. Autonomous spends agents to
  cover the human's absence — everything closed before dispatch, two fresh context-isolated
  reviewers, mechanical stop conditions.

---

## Layer 4 — The durable record

**Copy:**

- `tools/system_evolution.py`, `tools/system_evolution_record.py`,
  `tools/system_evolution_repository.py`, `tools/record_common.py`
- `.agents/skills/sysml-evolution/assets/system-evolution.schema.json`
- `.agents/skills/sysml-evolution/assets/system-evolution.template.yaml`

**Recipes:**

```
system-evolution-check:  uv run python tools/system_evolution.py check
system-evolution-status: uv run python tools/system_evolution.py status
```

Start from the template. The record indexes findings, decisions, work items with acceptance sets, an
append-only review log, and closure — it is an execution and evidence index, **never product
authority**.

`system_evolution_repository.py` is the only part with Git assumptions (checkpoints are commits,
evidence resolves against the working tree). If your project is not Git-backed, that file is what you
replace; the schema and record semantics are unaffected.

Two rules learned the hard way, both already fixed here — check they survived your copy:

- The record must not store a copy of what the tool can compute from the repository. An `observed`
  baseline goes stale on every ordinary commit and buys a re-stamp rather than a fact.
- A **complete** record must not require the repository to stay at its checkpoint. That freezes the
  project: once an evolution closes, no later commit passes the gate.

---

## Layer 5 — Hygiene

**Copy:**

- `tools/validate_skills.py` — frontmatter, naming, link resolution, UI metadata
- `tools/sync_agent_skills.py` — generates `.claude/skills/` links from `.agents/skills/`
- `.agents/skills/documentation-sync/` — **adapt, do not copy verbatim.** Its authority map names
  Vellis paths.

**Recipes:**

```
skills-check: uv run python tools/validate_skills.py
              uv run python tools/sync_agent_skills.py --check
skills-sync:  uv run python tools/sync_agent_skills.py
```

---

## Binding the core to your project

`tools/model_layout.py` (34 lines) is the **only** file that must change. Everything project-specific
lives here:

```python
ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "model"                       # where your .sysml files live
LANGUAGE_LOCK_PATH  = MODEL_ROOT / "config" / "language.lock.json"
VALIDATOR_LOCK_PATH = MODEL_ROOT / "config" / "validator.lock.json"
SYSTEM_EVOLUTION_PATH = ROOT / "system-evolution.yaml"
SYSTEM_EVOLUTION_SCHEMA_PATH = ROOT / ".agents" / "skills" / ... # schema asset
AUTHORED_MODEL_PACKAGES = {                       # root package -> owning file
    "YourDomain": "model/10-your-domain.sysml",
    ...
}
SYSML_CACHE_ROOT = ROOT / ".cache" / "sysml"      # ignored; never committed
```

`AUTHORED_MODEL_PACKAGES` is an exhaustive map of root package to owning file. **Adding a model file
requires adding a line here**, and the numeric prefix must sort after its dependencies.

Then write two project-binding documents. Keep them thin — the normative method lives in the skills,
and restating it is how five copies of a rule drift apart:

- **`AGENTS.md`** — safety rules, where authority lives, skill routing, reading scope, what a
  checkpoint is in your VCS, which gates to run, and the evidence-reference format. Bind the portable
  rules; do not repeat them.
- **`CONTRIBUTING.md`** — the human-facing workflow, pointing at both.

Also copy `.gitignore` entries for `.cache/`, and add a `just check` aggregate.

---

## What to leave behind

Vellis-specific, no value in a fresh repo:

- `vellis/` — the product
- `model/*.sysml` — Vellis's own model; write your own
- `.agents/skills/rtg-schema-design/` — an optional domain extension for Reified Type Graph meaning.
  Useful only if your domain is RTG. It is the worked example of what a *domain* skill looks like
  alongside the portable core, so read it before writing your own.
- `tools/package_smoke.py` — Python packaging checks for a `uv tool install` distribution
- `docs/v2-*.md` — historical evidence documents

---

## Tests worth copying

These guard the machinery rather than the product, and each fails for a real defect:

| Test | Guards |
| --- | --- |
| `tests/test_sysml_validator.py` | validator setup, pinning, probe behavior |
| `tests/test_sysml_reference.py`, `tests/test_reference_routing.py` | corpus generation and intent routing |
| `tests/test_skills.py` | skill structure, link resolution, **portable-core purity** |
| `tests/test_system_evolution.py` | every record invariant |
| `tests/test_model_policy.py` | the requirement-constraint house rule |

Two guards in `tests/test_skills.py` are worth understanding before you adapt them, because both
existed to catch a check that had stopped checking:

- The portability test asserts each skill **contributed files** before scanning them. Without it, a
  renamed or deleted skill makes the scan vacuous and it passes having read nothing.
- The inventory test asserts a minimum skill count. Two empty inventories compare equal.

---

## Bring-up order

1. `uv init`, add `jupyter-client`, `pypdf`, `pyyaml`, `jsonschema` as dev dependencies.
2. Copy `tools/model_layout.py` and edit it for your layout.
3. Copy layer 1 and 2 tooling and both lock files. Run `model-setup`, then `model-check` on a
   one-package model. **You now have pinned reference and formal validation.**
4. Copy the four portable skills and `sync_agent_skills.py`. Run `skills-sync`, then `skills-check`.
5. Write `AGENTS.md` with routing and your project bindings.
6. Copy layer 4 when you have something built worth recording changes against. A greenfield project
   does not need an evolution record on day one.
7. Add `just check` aggregating lint, typecheck, `model-check`, `skills-check`, tests, and
   `system-evolution-check` once that exists.

## Verifying the port

The port is good when a **fresh agent**, given only the new repository, can:

- answer a SysML construct question by citation from the pinned corpus rather than from recall;
- validate a snippet before editing the model;
- state what the model requires, what it leaves open, and how it knows which is which;
- refuse to invent subsystems for a model that deliberately does not decompose;
- classify a code unit spanning two modeled parts as an implementation defect.

Those five are the actual deliverable. Everything above is what it takes to get them.
