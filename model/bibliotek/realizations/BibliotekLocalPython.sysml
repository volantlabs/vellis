package BibliotekLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppCatalog::*;
    private import BibliotekAppLauncher::*;
    private import BibliotekAppShell::*;
    private import BibliotekRtgDiscovery::*;

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

    part def InMemoryRtgDiscovery :> RtgDiscovery {
        @ImplementationCodec { logicalType = "SysML lowerCamelCase public feature names"; implementationType = "Python snake_case dataclass and argument names"; normalization = "The realization maps names mechanically without changing values, multiplicities, ordering, or operation meaning."; }
        @ImplementationCodec { logicalType = "RtgDiscoveryView::rowLabels and columnLabels"; implementationType = "dict[str, str]"; normalization = "Each modeled JSON object member key and string value maps losslessly to one Python dictionary entry; member order has no semantic meaning."; }
        @ImplementationCodec { logicalType = "RtgDiscoverySelection::cellDescriptions"; implementationType = "dict[RtgDiscoveryCoordinates, str]"; normalization = "Each modeled JSON member key is the canonical JSON string encoding of the ordered rowKey and columnKey pair; Python decodes that pair to one immutable coordinate key without ambiguity."; }
        @ImplementationCodec { logicalType = "RtgDiscoveryView::metadata"; implementationType = "field(default_factory=dict)"; normalization = "An omitted Python constructor argument creates the required present empty logical JsonObject and encodes equivalently."; }
        @ImplementationCodec { logicalType = "JsonObject"; implementationType = "dict[str, JsonValue]"; normalization = "Python preserves finite JSON-compatible values losslessly and copies caller-owned mutable containers at the component boundary."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/discovery"; symbol = "components.rtg.discovery.InMemoryRtgDiscovery"; realization = "BibliotekLocalPython"; }
    }
}
