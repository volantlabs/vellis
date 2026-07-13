from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

MODEL_ROOT = ROOT / "model"
FOUNDATION_MODEL_ROOT = MODEL_ROOT / "foundation"
BIBLIOTEK_MODEL_ROOT = MODEL_ROOT / "bibliotek"
COMPONENT_MODEL_ROOT = BIBLIOTEK_MODEL_ROOT / "components"
VELLIS_MODEL_ROOT = MODEL_ROOT / "vellis"
MODEL_CONFIG_ROOT = MODEL_ROOT / "config"

ALLOWED_CONSTRUCTS_PATH = MODEL_CONFIG_ROOT / "allowed-constructs.json"
LANGUAGE_LOCK_PATH = MODEL_CONFIG_ROOT / "language.lock.json"
VALIDATOR_LOCK_PATH = MODEL_CONFIG_ROOT / "validator.lock.json"
MODEL_FIXTURE_ROOT = ROOT / "tests" / "model" / "fixtures"
SOFTWARE_COMPONENT_PATTERN_PATH = MODEL_FIXTURE_ROOT / "SoftwareComponentPattern.sysml"

GENERATED_ROOT = ROOT / "generated"
REFERENCE_DOC_ROOT = GENERATED_ROOT / "reference"
BIBLIOTEK_REFERENCE_ROOT = REFERENCE_DOC_ROOT / "bibliotek"
BIBLIOTEK_COMPONENT_REFERENCE_ROOT = BIBLIOTEK_REFERENCE_ROOT / "components"
VELLIS_REFERENCE_ROOT = REFERENCE_DOC_ROOT / "vellis"
GENERATED_MODEL_ROOT = GENERATED_ROOT / "model"
GENERATED_FORMAL_INDEX = GENERATED_MODEL_ROOT / "formal-model-index.json"
GENERATED_CONFORMANCE_OBJECTIVES = GENERATED_MODEL_ROOT / "conformance-objectives.json"
GENERATED_EVIDENCE_INDEX = GENERATED_MODEL_ROOT / "verification-evidence.json"
GENERATED_MANIFEST = ROOT / "apps" / "rtg_knowledge_graph" / "resources" / "model_app_manifest.json"
GENERATED_STARTER_SCHEMA = (
    ROOT / "apps" / "rtg_knowledge_graph" / "resources" / "everyday_life_schema.json"
)

SYSML_CACHE_ROOT = ROOT / ".cache" / "sysml"
FORMAL_CACHE_ROOT = SYSML_CACHE_ROOT / "formal"
VALIDATOR_CACHE_ROOT = SYSML_CACHE_ROOT / "validator"
MODEL_PACKAGE_ROOT = ROOT / "build" / "model" / "packages"
