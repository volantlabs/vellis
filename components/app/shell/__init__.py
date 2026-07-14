"""App Shell component."""

from components.app.shell.implementation import InMemoryAppShell
from components.app.shell.protocol import (
    AppCloseRejected,
    AppOpenRequest,
    AppShell,
    AppShellCommandResult,
    AppShellConfigurationInvalid,
    AppShellError,
    AppShellReadFailed,
    AppShellView,
    CloseRequest,
    ShellActiveApp,
    ShellOptions,
    ShellQuery,
)

__all__ = [
    "AppCloseRejected",
    "AppOpenRequest",
    "AppShell",
    "AppShellCommandResult",
    "AppShellConfigurationInvalid",
    "AppShellError",
    "AppShellReadFailed",
    "AppShellView",
    "CloseRequest",
    "InMemoryAppShell",
    "ShellActiveApp",
    "ShellOptions",
    "ShellQuery",
]
