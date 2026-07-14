library package Bibliotek {
    private import SoftwareComponentModeling::*;
    public import BibliotekSoftwareValues::*;
    public import BibliotekAppCatalog::*;
    public import BibliotekAppLauncher::*;
    public import BibliotekAppShell::*;
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
    public import BibliotekRtgGraphRegistry::*;
    public import BibliotekRtgController::*;

    doc /*
     * Bibliotek is the supported reusable-library facade. Public imports form its
     * consumer API; the modeling foundation remains a private authoring dependency.
     * Bibliotek has no dependency on Vellis, MCP, REST, deployment topology, or a
     * future messaging runtime. Reusable runtime contracts may be added as separate
     * library packages after their observable semantics are intentionally designed.
     */
}
