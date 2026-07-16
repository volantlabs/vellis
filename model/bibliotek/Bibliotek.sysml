library package Bibliotek {
    private import SoftwareComponentModeling::*;
    public import BibliotekSoftwareValues::*;
    public import BibliotekRtgChangeValues::*;
    public import BibliotekStorageJsonFile::*;
    public import BibliotekStorageSql::*;
    public import BibliotekRtgDiagnostics::*;
    public import BibliotekRtgGraph::*;
    public import BibliotekRtgSchema::*;
    public import BibliotekRtgConstraints::*;
    public import BibliotekRtgMigration::*;
    public import BibliotekRtgQuery::*;
    public import BibliotekRtgChangeValidation::*;
    public import BibliotekRtgDiscovery::*;
    public import BibliotekRtgController::*;
    public import BibliotekRuntimeMessaging::*;
    public import BibliotekRuntimeMessageRuntime::*;
    public import BibliotekRuntimeComponentAdapter::*;
    public import BibliotekRuntimePythonRealization::*;
    public import BibliotekInterfaceMcpGateway::*;

    doc /*
     * Bibliotek is the supported reusable-library facade. Public imports form its
     * consumer API; the modeling foundation remains a private authoring dependency.
     * Bibliotek has no dependency on Vellis, Vellis-specific transport behavior,
     * deployment topology, or a Vellis application behavior. Reusable runtime and
     * interface components, including the generic MCP gateway, are exported as separate
     * contracts; logical domain components remain topology-neutral.
     */
}
