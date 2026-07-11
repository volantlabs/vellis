# SysML migration evidence

This directory contains temporary, non-authoring evidence retained while the repository's SysML
models complete human acceptance.

`component-spec-baseline/` is the frozen predecessor Markdown baseline. It exists only to support
cutover review and lossless knowledge disposition. Do not update it for new design or implementation
changes; author contracts in textual SysML under `model/` and regenerate `docs/reference/`.

The baseline will be removed only after the Bibliotek and Vellis acceptance gates in
`model/migration/cutover-status.json` are explicitly approved. Git preserves its earlier history.
