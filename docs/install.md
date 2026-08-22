# Install

Vellis distributes as a git-hosted Python tool, not a registry package. There is no PyPI listing;
`uv` installs directly from the repository.

## Prerequisites

Install [uv](https://docs.astral.sh/uv/). Vellis requires Python 3.14 or newer
(`requires-python` in `pyproject.toml`); `uv` fetches a matching interpreter automatically when one
is not already available, and this is exercised on a runner with no preinstalled Python 3.14 by the
`install` job in `.github/workflows/check.yml`. A `--python 3.14` flag is unnecessary: `uv tool
install` downloads Python by default and only skips that when `--no-python-downloads` or
`UV_PYTHON_DOWNLOADS=never` is set, and passing an incompatible `--python` value does not override
`requires-python` — `uv` still resolves an interpreter that satisfies it. If downloads are disabled
in your environment and no compatible interpreter is present, `uv` reports the version conflict
plainly rather than installing something broken; supply your own Python 3.14 first in that case.

## Install

```sh
uv tool install git+https://github.com/volantlabs/vellis
vellis --help
```

This places a `vellis` shim in `uv tool dir --bin` (usually `~/.local/bin`). That directory must be
on `PATH`: `vellis connect` resolves the running command with `shutil.which("vellis")` and writes
the resulting absolute path into whichever client entry it registers, so an unreachable shim
produces a client entry that cannot be registered correctly.

Try it once without installing:

```sh
uvx --from git+https://github.com/volantlabs/vellis vellis --help
```

## Pin, upgrade, uninstall

```sh
uv tool install git+https://github.com/volantlabs/vellis@<tag-or-commit>   # pin a specific ref
uv tool upgrade vellis                                                    # move to the latest tip
uv tool install --force git+https://github.com/volantlabs/vellis@<ref>    # move to a different ref
uv tool uninstall vellis
```

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| An MCP client reports it cannot connect, and running the configured command by hand shows `vellis: error: the following arguments are required: command` | The client entry invokes `vellis` (or `python -m vellis`) with no subcommand. Vellis v2 always requires one — there is no bare server mode. | Re-register the entry: `vellis connect --client <codex\|claude> --transport stdio --data-dir <dir> --replace`. |
| `vellis` is not found after `uv tool install` | The tool bin directory is not on `PATH`. | Run `uv tool update-shell`, or add `uv tool dir --bin` to `PATH` yourself, then open a new shell. |
| `vellis setup` exits with `noninteractive setup requires an explicit initialization mode` | Fresh `setup` run without a mode flag from a script or agent (no interactive terminal to confirm a preselected choice in). | Pass `--starter` for the recommended Everyday Life vocabulary, or `--blank` for an empty graph. |
| Install fails with a Python version conflict and no download occurred | Python downloads are disabled in your environment (`UV_PYTHON_DOWNLOADS=never` or `--no-python-downloads`) and no Python 3.14+ is present. | Install Python 3.14+ yourself, or re-enable downloads and retry. |

See the [README](../README.md#install) for the canonical commands and
[AGENTS.md](../AGENTS.md#running-vellis) for the agent-facing setup path.
