from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "model"
MODEL_CONFIG_ROOT = MODEL_ROOT / "config"
LANGUAGE_LOCK_PATH = MODEL_CONFIG_ROOT / "language.lock.json"
VALIDATOR_LOCK_PATH = MODEL_CONFIG_ROOT / "validator.lock.json"
IMPLEMENTATION_CAMPAIGN_PATH = ROOT / "implementation-campaign.yaml"
IMPLEMENTATION_CAMPAIGN_SCHEMA_PATH = (
    ROOT
    / ".agents"
    / "skills"
    / "sysml-implementation-campaign"
    / "assets"
    / "implementation-campaign.schema.json"
)
SYSTEM_EVOLUTION_PATH = ROOT / "system-evolution.yaml"
SYSTEM_EVOLUTION_SCHEMA_PATH = (
    ROOT / ".agents" / "skills" / "sysml-evolution" / "assets" / "system-evolution.schema.json"
)
AUTHORED_MODEL_PACKAGES = {
    "RTG": "model/10-rtg-domain.sysml",
    "EverydayLifeStarter": "model/15-everyday-life-starter.sysml",
    "RTGSystem": "model/20-rtg-system.sysml",
    "Vellis": "model/30-vellis.sysml",
    "VellisRequirements": "model/40-requirements.sysml",
    "VellisVerification": "model/50-verification.sysml",
}
SYSML_CACHE_ROOT = ROOT / ".cache" / "sysml"
VALIDATOR_CACHE_ROOT = SYSML_CACHE_ROOT / "validator"

# A blobless sparse checkout of the pinned upstream release: specifications,
# example models, and training models arrive together at one commit, so they
# cannot disagree with each other.
RELEASE_CACHE_ROOT = SYSML_CACHE_ROOT / "release"

# Reference corpora are generated from checksum-pinned upstream sources into the
# ignored cache, never committed. Nothing derived from upstream lives in Git, so
# the corpus cannot drift from its pin and no upstream licence is redistributed.
REFERENCE_CACHE_ROOT = SYSML_CACHE_ROOT / "reference"
SPECIFICATION_REFERENCE_ROOT = REFERENCE_CACHE_ROOT / "specifications"
