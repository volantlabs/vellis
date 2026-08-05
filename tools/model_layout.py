from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "model"
MODEL_CONFIG_ROOT = MODEL_ROOT / "config"
LANGUAGE_LOCK_PATH = MODEL_CONFIG_ROOT / "language.lock.json"
VALIDATOR_LOCK_PATH = MODEL_CONFIG_ROOT / "validator.lock.json"
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
