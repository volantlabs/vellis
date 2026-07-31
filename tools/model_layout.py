from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = ROOT / "model"
MODEL_CONFIG_ROOT = MODEL_ROOT / "config"
LANGUAGE_LOCK_PATH = MODEL_CONFIG_ROOT / "language.lock.json"
VALIDATOR_LOCK_PATH = MODEL_CONFIG_ROOT / "validator.lock.json"
SPECIFICATION_REFERENCE_ROOT = ROOT / "reference" / "specifications"

SYSML_CACHE_ROOT = ROOT / ".cache" / "sysml"
FORMAL_CACHE_ROOT = SYSML_CACHE_ROOT / "formal"
VALIDATOR_CACHE_ROOT = SYSML_CACHE_ROOT / "validator"
