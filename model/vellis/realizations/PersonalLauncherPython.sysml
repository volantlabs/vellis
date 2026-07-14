package VellisPersonalLauncherPythonRealization {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppLauncher::*;
    private import BibliotekLocalPythonRealization::*;
    private import VellisPersonalLauncher::*;

    part def PythonDesktopRuntimeAdapter :> RuntimeAdapter {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/personal_launcher"; symbol = "apps.personal_launcher.runtime.DesktopRuntimeAdapter"; realization = "PersonalLauncherPython"; }
    }

    part def PersonalLauncherPython :> PersonalLauncherApplication {
        @ImplementationBinding { implementationLanguage = ImplementationLanguage::python; codeRoot = "apps/personal_launcher"; symbol = "apps.personal_launcher.service.build_service"; realization = "in-process composition with HTTP and macOS desktop adapters"; }
        part :>> catalog : InMemoryAppCatalog;
        part :>> runtimeAdapter : PythonDesktopRuntimeAdapter;
        part :>> launcher : InMemoryAppLauncher;
        part :>> shell : InMemoryAppShell;
    }

    part logicalLauncher : PersonalLauncherApplication;
    part pythonLauncher : PersonalLauncherPython;
    allocate logicalLauncher to pythonLauncher {
        allocate logicalLauncher.catalog to pythonLauncher.catalog;
        allocate logicalLauncher.runtimeAdapter to pythonLauncher.runtimeAdapter;
        allocate logicalLauncher.launcher to pythonLauncher.launcher;
        allocate logicalLauncher.shell to pythonLauncher.shell;
    }
}
