# Local Vellis data

`uv run vellis setup` stores the local RTG graph and controller ledger under
`.data/rtg_knowledge_graph/`. Everything in this directory except this README is ignored by Git.

Ordinary pulls and checkouts do not touch this data. Commands such as `git clean -x` can delete
ignored files, including the graph. Back up the directory before intentionally cleaning ignored
state. See [Getting started](../docs/guides/vellis/getting-started.md) for backup and reset guidance.
