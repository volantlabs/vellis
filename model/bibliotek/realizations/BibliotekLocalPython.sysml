package BibliotekLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppCatalog::*;
    private import BibliotekAppLauncher::*;

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
}
