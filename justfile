set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

default:
    @just --list

setup:
    @uv sync --dev

lint:
    @uv run ruff check .
    @uv run ruff format --check .

format:
    @uv run ruff format .

typecheck:
    @uv run basedpyright

test:
    @uv run pytest

skills-check:
    @uv run python tools/validate_skills.py
    @uv run python tools/sync_agent_skills.py --check

skills-sync:
    @uv run python tools/sync_agent_skills.py

model-setup:
    @uv run python tools/sysml_validator.py setup
    @uv run python tools/sysml_reference.py render

model-check:
    @uv run python tools/sysml_validator.py validate --self-test

model-reference-render:
    @uv run python tools/sysml_reference.py render

model-reference-check:
    @uv run python tools/sysml_reference.py check

model-reference-find query specification="" limit="8":
    @specification={{quote(specification)}}; if test -n "$specification"; then uv run python tools/sysml_reference.py find {{quote(query)}} --specification "$specification" --limit {{quote(limit)}}; else uv run python tools/sysml_reference.py find {{quote(query)}} --limit {{quote(limit)}}; fi

check: lint typecheck skills-check model-check model-reference-check test

model-reference-concepts:
    @uv run python tools/sysml_reference.py concepts

model-probe source:
    @uv run python tools/sysml_validator.py probe {{quote(source)}}
