package BibliotekLocalPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppCatalog::*;
    private import BibliotekAppLauncher::*;
    private import BibliotekAppShell::*;
    private import BibliotekRtgDiscovery::*;
    private import BibliotekRtgGraphRegistry::*;
    private import BibliotekRtgGraphBridge::*;

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

    part def InMemoryRtgGraphRegistry :> RtgGraphRegistry {
        @ImplementationCodec { logicalType = "SysML lowerCamelCase public feature names"; implementationType = "Python snake_case dataclass and argument names"; normalization = "The realization maps names mechanically without changing values, multiplicities, ordering, or operation meaning."; }
        @ImplementationCodec { logicalType = "RtgGraphOperation and RtgGraphMcpTransport"; implementationType = "str"; normalization = "Python accepts and emits exactly the modeled lower-case enumeration literal names."; }
        @ImplementationCodec { logicalType = "ordered multiplicities"; implementationType = "tuple"; normalization = "Python tuples preserve the modeled caller order and immutable result ordering."; }
        @ImplementationCodec { logicalType = "optional values"; implementationType = "T | None"; normalization = "None represents modeled absence and a present Python value represents the single optional modeled occurrence."; }
        @ImplementationCodec { logicalType = "RtgGraphDescriptor::metadata"; implementationType = "field(default_factory=dict)"; normalization = "An omitted Python constructor argument creates the required present empty logical JsonObject and encodes equivalently."; }
        @ImplementationCodec { logicalType = "JsonObject"; implementationType = "dict[str, JsonValue]"; normalization = "Python preserves finite JSON-compatible values losslessly and deep-copies caller-owned mutable containers at the component boundary."; }
        @ImplementationCodec { logicalType = "Real"; implementationType = "float"; normalization = "Python finite floating-point scores encode the modeled real routing score in the closed interval from zero through one."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/graph_registry"; symbol = "components.rtg.graph_registry.InMemoryRtgGraphRegistry"; realization = "BibliotekLocalPython"; }
    }

    part def InMemoryRtgGraphBridge :> RtgGraphBridge {
        @ImplementationCodec { logicalType = "SysML lowerCamelCase public feature names"; implementationType = "Python snake_case dataclass and argument names"; normalization = "The realization maps names mechanically without changing values, multiplicities, ordering, or operation meaning."; }
        @ImplementationCodec { logicalType = "Uuid"; implementationType = "uuid.UUID"; normalization = "Python UUID values encode as canonical lowercase textual UUID values and decode without changing identity."; }
        @ImplementationCodec { logicalType = "RtgGraphBridgeStatus and RtgGraphBridgeCandidateStatus"; implementationType = "str"; normalization = "Python accepts and emits exactly the modeled lower-case enumeration literal names."; }
        @ImplementationCodec { logicalType = "RtgGraphBridgeStatusFilter and RtgGraphBridgeCandidateStatusFilter"; implementationType = "str | None"; normalization = "Python None encodes the modeled all filter; other values use exactly the modeled lower-case status literals."; }
        @ImplementationCodec { logicalType = "ordered multiplicities"; implementationType = "tuple"; normalization = "Python tuples preserve modeled order and immutable result ordering."; }
        @ImplementationCodec { logicalType = "optional values"; implementationType = "T | None"; normalization = "None represents modeled absence and a present Python value represents the single optional modeled occurrence."; }
        @ImplementationCodec { logicalType = "RtgGraphBridgeDraft::metadata and RtgGraphBridgeCandidateDraft::metadata"; implementationType = "field(default_factory=dict)"; normalization = "An omitted Python constructor argument creates the required present empty logical JsonObject and encodes equivalently."; }
        @ImplementationCodec { logicalType = "JsonObject"; implementationType = "dict[str, JsonValue]"; normalization = "Python preserves finite JSON-compatible values losslessly and deep-copies caller-owned mutable containers at the component boundary."; }
        @ImplementationCodec { logicalType = "Real"; implementationType = "float"; normalization = "Python finite floating-point confidence values encode the modeled real value in the closed interval from zero through one."; }
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "components/rtg/graph_bridge"; symbol = "components.rtg.graph_bridge.InMemoryRtgGraphBridge"; realization = "BibliotekLocalPython"; }
    }
}
