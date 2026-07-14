# Personal Launcher App

Local reference app that composes `component.app.catalog`, `component.app.launcher`, and
`component.app.shell` into a desktop-openable launcher.

Run it during development:

```bash
just launcher-dev
```

Install or refresh the macOS app wrapper:

```bash
just launcher-app
```

The wrapper installs `Vellis Launcher.app` with the bundled Vellis app icon.

The default catalog is created at `~/.vellis/app-catalog.json` the first time the launcher runs.
It includes Codex, the Vellis workspace, and RTG MCP info. Additional applications can be added to
the catalog as their implementations are installed or harmonized into this repository.

The Activity rail separates managed sessions from recent launches. Long-running command surfaces
remain switchable and stoppable while the launcher owns their process; files, URLs, desktop apps,
and completed commands are recorded as recent handoffs without claiming runtime ownership.
