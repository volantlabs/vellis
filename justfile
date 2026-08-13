set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# List available recipes.
default:
    @just --list

# Install Python tooling for this repository.
setup:
    @uv sync --dev

# Check formatting and lint rules.
lint:
    @uv run ruff check .
    @uv run ruff format --check .

# Apply formatting.
format:
    @uv run ruff format .

# Type-check tools and tests.
typecheck:
    @uv run basedpyright

# Run the test suite.
test:
    @uv run pytest

# Validate repo-local skills and their managed links.
skills-check:
    @uv run python tools/validate_skills.py
    @uv run python tools/sync_agent_skills.py --check

# Validate the model-derived implementation campaign and its current baseline.
implementation-campaign-check:
    @uv run python tools/implementation_campaign.py check

# Validate the active model-and-implementation evolution record.
system-evolution-check:
    @uv run python tools/system_evolution.py check

# Show the active evolution lifecycle, approval, and next work.
system-evolution-status:
    @uv run python tools/system_evolution.py status

# Show the current implementation campaign lifecycle and next work.
implementation-campaign-status:
    @uv run python tools/implementation_campaign.py status

# Emit one machine-readable manager disposition without changing campaign state.
implementation-campaign-dispatch identical_failures="0" expected_state_token="":
    @expected={{quote(expected_state_token)}}; if test -n "$expected"; then uv run python tools/implementation_campaign.py dispatch --identical-failures {{quote(identical_failures)}} --expect-state-token "$expected"; else uv run python tools/implementation_campaign.py dispatch --identical-failures {{quote(identical_failures)}}; fi

# Generate one finding-free, project-bound review prompt for an active slice or for closure.
implementation-campaign-review-frame work_item lens:
    @uv run python tools/implementation_campaign.py review-frame --slice {{quote(work_item)}} --lens {{quote(lens)}}

# Validate a compact campaign worker result before a manager consumes it.
implementation-campaign-worker-result-check result:
    @uv run python tools/implementation_campaign.py worker-result-check --result {{quote(result)}}

# Print current model, language, and validator baseline digests without changing the campaign.
implementation-campaign-baseline:
    @uv run python tools/implementation_campaign.py baseline

# Validate clean committed HEAD, approved plan projection, current checkpoint, and current evidence.
implementation-campaign-checkpoint-check:
    @uv run python tools/implementation_campaign.py checkpoint-check

# Regenerate managed skill links.
skills-sync:
    @uv run python tools/sync_agent_skills.py

# Fetch pinned specifications, libraries, examples, and validator, then generate the search corpus.
model-setup:
    @uv run python tools/sysml_validator.py setup
    @uv run python tools/sysml_reference.py render

# Validate every authored SysML file with the pinned official validator.
model-check:
    @uv run python tools/sysml_validator.py validate --self-test

# Regenerate the searchable specification corpus from the pinned PDFs.
model-reference-render:
    @uv run python tools/sysml_reference.py render

# Prove the generated corpus still matches its pin.
model-reference-check:
    @uv run python tools/sysml_reference.py check

# Search specifications, model libraries, and examples; optional specification and limit are positional.
model-reference-find query specification="" limit="8":
    @specification={{quote(specification)}}; if test -n "$specification"; then uv run python tools/sysml_reference.py find {{quote(query)}} --specification "$specification" --limit {{quote(limit)}}; else uv run python tools/sysml_reference.py find {{quote(query)}} --limit {{quote(limit)}}; fi

# Run the complete repository gate.
check: lint typecheck skills-check implementation-campaign-check system-evolution-check model-check model-reference-check test

# List every SysML v2 construct name, for turning a question into a searchable term.
model-reference-concepts:
    @uv run python tools/sysml_reference.py concepts

# Check one SysML snippet against the pinned parser (about six seconds).
model-probe source:
    @uv run python tools/sysml_validator.py probe {{quote(source)}}
