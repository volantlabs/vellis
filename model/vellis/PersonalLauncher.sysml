package VellisPersonalLauncher {
    private import SoftwareComponentModeling::*;
    private import BibliotekAppCatalog::*;
    private import BibliotekAppLauncher::*;
    private import BibliotekAppShell::*;

    part def <'application.vellis.personal_launcher'> PersonalLauncherApplication {
        @SpecificationStatus { lifecycleStatus = SpecLifecycle::draft; owner = "humans"; }

        part catalog : AppCatalog;
        part runtimeAdapter : RuntimeAdapter;
        part launcher : AppLauncher;
        part shell : AppShell;

        bind launcher.appCatalog = catalog;
        bind launcher.runtimeAdapter = runtimeAdapter;
        bind shell.appCatalog = catalog;
        bind shell.appLauncher = launcher;
    }

    requirement <'invariant.vellis.personal_launcher.public_contracts_only'> publicContractsOnly {
        subject application : PersonalLauncherApplication;
        require constraint {
            doc /* The launcher composes catalog, launcher, shell, and runtime roles only through their modeled public contracts. */
        }
    }

    requirement <'invariant.vellis.personal_launcher.truthful_activity'> truthfulActivity {
        subject application : PersonalLauncherApplication;
        require constraint {
            doc /* Managed runtime surfaces produce launcher-owned sessions; handed-off or already completed surfaces produce bounded recent activity without false runtime ownership. */
        }
    }

    requirement <'invariant.vellis.personal_launcher.current_defaults'> currentDefaults {
        subject application : PersonalLauncherApplication;
        require constraint {
            doc /* Built-in repository-local catalog entries name only surfaces available in the current Vellis distribution; optional applications enter through explicit catalog records when installed. */
        }
    }

    requirement <'invariant.vellis.personal_launcher.transport_outside_components'> transportOutsideComponents {
        subject application : PersonalLauncherApplication;
        require constraint {
            doc /* HTTP serving, browser opening, and desktop-wrapper installation remain application adapters and do not enter reusable component contracts. */
        }
    }

    part contractContext {
        part application : PersonalLauncherApplication;
        satisfy publicContractsOnly by application;
        satisfy truthfulActivity by application;
        satisfy currentDefaults by application;
        satisfy transportOutsideComponents by application;
    }

    verification def PersonalLauncherCompositionVerification {
        subject application : PersonalLauncherApplication;
        objective {
            verify publicContractsOnly;
            verify truthfulActivity;
            verify currentDefaults;
            verify transportOutsideComponents;
        }
        @EvidenceBinding { evidenceId = "apps/personal_launcher/tests/test_personal_launcher_app.py#PersonalLauncherCompositionVerification"; implementationScope = "PersonalLauncherPython"; }
    }
}
