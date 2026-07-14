package BibliotekLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppCatalog::*;
    private import BibliotekAppLauncher::*;
    private import BibliotekAppShell::*;

    part def InMemoryAppCatalog :> AppCatalog {
        @ImplementationCodec { logicalType = "LaunchSurfaceMode and RuntimeControl"; implementationType = "str"; normalization = "The Python realization accepts and emits exactly the modeled enumeration literal names."; }
        @ImplementationCodec { logicalType = "JsonObject"; implementationType = "dict[str, JsonValue]"; normalization = "Canonical JSON serialization preserves every member and nested value while removing caller-owned mutable aliases."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/app/catalog"; symbol = "components.app.catalog.InMemoryAppCatalog"; realization = "BibliotekLocalPython"; }
    }

    part def InMemoryAppLauncher :> AppLauncher {
        @ImplementationCodec { logicalType = "Timestamp"; implementationType = "datetime | None"; normalization = "Present timezone-aware datetimes encode as explicit-offset ISO-8601 timestamps; None represents modeled absence."; }
        @ImplementationCodec { logicalType = "JsonObject"; implementationType = "dict[str, JsonValue]"; normalization = "Canonical JSON serialization preserves every member and nested value while removing caller-owned mutable aliases."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/app/launcher"; symbol = "components.app.launcher.InMemoryAppLauncher"; realization = "BibliotekLocalPython"; }
    }

    part def InMemoryAppShell :> AppShell {
        @ImplementationCodec { logicalType = "AppShellState"; implementationType = "private Python fields"; normalization = "The realization preserves active session identity, per-app selected surfaces, most-recent-first app identity order, and a maximum of ten canonical handoff copies."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/app/shell"; symbol = "components.app.shell.InMemoryAppShell"; realization = "BibliotekLocalPython"; }
    }
}
