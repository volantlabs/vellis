SCHEMA_DOMAINS: dict[str, dict[str, object]] = {
    "governance_core": {
        "title": "Governance Core",
        "status": "beta",
        "summary": (
            "Kernel-adjacent governance vocabulary for principles, decisions, conventions, "
            "policies, and their provenance."
        ),
        "catalog_path": "docs/schema-domains/governance-core/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-governance-core-beta-prompt.md",
        "walkthrough_path": (
            "docs/guides/vellis/evals/rtg-governance-core-known-good-walkthrough.md"
        ),
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": ["governance", "provenance", "policy", "beta"],
        "runtime_status": "ready",
        "runtime_requirements": [],
        "runtime_blockers": [],
    },
    "agent_memory_spine": {
        "title": "Agent Memory Spine",
        "status": "beta",
        "summary": (
            "Reference agent-memory vocabulary for actors, traces, facts, assessments, "
            "decisions, skills, taxonomy, media, and domains."
        ),
        "catalog_path": "docs/schema-domains/agent-memory-spine/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-agent-memory-spine-beta-prompt.md",
        "walkthrough_path": (
            "docs/guides/vellis/evals/rtg-agent-memory-spine-known-good-walkthrough.md"
        ),
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": ["agent", "memory", "provenance", "taxonomy", "beta"],
        "runtime_status": "ready",
        "runtime_requirements": [],
        "runtime_blockers": [],
    },
    "individual_life_graph": {
        "title": "Individual Life Graph",
        "status": "beta",
        "summary": "Initial personal and professional planning graph for one operator.",
        "catalog_path": "docs/schema-domains/individual-life-graph/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-individual-life-graph-beta-prompt.md",
        "walkthrough_path": "docs/guides/vellis/evals/rtg-beta-known-good-walkthrough.md",
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": ["personal", "professional", "planning", "beta"],
        "runtime_status": "ready",
        "runtime_requirements": [],
        "runtime_blockers": [],
    },
    "personal_operating_graph": {
        "title": "Personal Operating Graph",
        "status": "beta",
        "summary": (
            "Governed personal operating graph for commitments, decisions, reviews, evidence, "
            "routines, and attention planning."
        ),
        "catalog_path": "docs/schema-domains/personal-operating-graph/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-personal-operating-graph-beta-prompt.md",
        "walkthrough_path": (
            "docs/guides/vellis/evals/rtg-personal-operating-graph-known-good-walkthrough.md"
        ),
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": ["personal", "operating", "evidence", "attention", "beta"],
        "runtime_status": "ready",
        "runtime_requirements": [],
        "runtime_blockers": [],
    },
    "experience_studio": {
        "title": "Experience Studio",
        "status": "alpha",
        "summary": (
            "Governed planning graph for graph-backed public games, visual explorations, and "
            "interactive experiences."
        ),
        "catalog_path": "docs/schema-domains/experience-studio/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-experience-studio-alpha-prompt.md",
        "walkthrough_path": "docs/guides/vellis/evals/rtg-experience-studio-alpha-walkthrough.md",
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": [
            "experience-design",
            "graph-backed-experiences",
            "games",
            "interactive",
            "public-data",
            "publication",
            "publish",
            "alpha",
        ],
        "runtime_status": "blocked",
        "runtime_requirements": [
            "experience-studio schema, seed, and query fixtures",
        ],
        "runtime_blockers": [
            "The referenced prototype fixtures are not yet present in the harmonized tree."
        ],
    },
    "gothic_ambient_archive": {
        "title": "Gothic Ambient Archive",
        "status": "alpha",
        "summary": (
            "Source-grounded public-domain Gothic literature graph for ambient visual "
            "exploration and LLM docent navigation."
        ),
        "catalog_path": "docs/schema-domains/gothic-ambient-archive/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-gothic-ambient-archive-alpha-prompt.md",
        "walkthrough_path": (
            "docs/guides/vellis/evals/rtg-gothic-ambient-archive-alpha-walkthrough.md"
        ),
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": ["literature", "public-domain", "gothic", "ambient", "docent", "alpha"],
        "runtime_status": "blocked",
        "runtime_requirements": [
            "Nocturne Archive schema, seed, and query fixtures",
        ],
        "runtime_blockers": [
            "The referenced prototype fixtures are not yet present in the harmonized tree."
        ],
    },
    "time_room_history": {
        "title": "Time Room History",
        "status": "alpha",
        "summary": (
            "Source-grounded historical claims compiled into deterministic offline runtime "
            "packs for kid-safe historical-figure experiences."
        ),
        "catalog_path": "docs/schema-domains/time-room-history/domain.yaml",
        "prompt_path": "docs/guides/vellis/evals/rtg-time-room-history-alpha-prompt.md",
        "walkthrough_path": "docs/guides/vellis/evals/rtg-time-room-history-alpha-walkthrough.md",
        "recommended_first_call": {"tool": "rtg_get_system_state", "arguments": {}},
        "domain_tags": [
            "history",
            "historical-figures",
            "education",
            "sources",
            "compiled-runtime",
            "time-room",
            "alpha",
        ],
        "runtime_status": "blocked",
        "runtime_requirements": [
            "Time Room History schema, seed, and query fixtures",
        ],
        "runtime_blockers": [
            "The referenced prototype fixtures are not yet present in the harmonized tree."
        ],
    },
}
