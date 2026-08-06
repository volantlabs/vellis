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
check: lint typecheck skills-check model-check model-reference-check test

# List every SysML v2 construct name, for turning a question into a searchable term.
model-reference-concepts:
    @uv run python tools/sysml_reference.py concepts

# Check one SysML snippet against the pinned parser (about six seconds).
model-probe source:
    @uv run python tools/sysml_validator.py probe {{quote(source)}}
