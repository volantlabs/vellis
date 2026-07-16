from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import cast
from uuid import UUID

from components.runtime.messaging.protocol import (
    JsonObject,
    JsonValue,
    RuntimeTopologyManifest,
)


def encode_json(value: object) -> JsonValue:
    """Encode one language-neutral value into the kernel's canonical JSON domain."""
    if value is None or isinstance(value, str | int | float | bool):
        if isinstance(value, float) and (value != value or value in {float("inf"), float("-inf")}):
            raise ValueError("canonical JSON does not admit non-finite numbers")
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return encode_json(value.value)
    if is_dataclass(value) and not isinstance(value, type):
        result: JsonObject = {}
        for field in fields(value):
            item = getattr(value, field.name)
            if (
                field.metadata.get("vellis_codec") == "omit_when_absent"
                and getattr(item, "__vellis_codec_absent__", False) is True
            ):
                continue
            result[field.name] = encode_json(item)
        return result
    if isinstance(value, Mapping):
        return {str(key): encode_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [encode_json(item) for item in value]
    if isinstance(value, set | frozenset):
        encoded = [encode_json(item) for item in value]
        return sorted(encoded, key=canonical_json)
    raise TypeError(f"value is not canonically JSON encodable: {type(value).__name__}")


def canonical_json(value: object) -> str:
    return json.dumps(
        encode_json(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def topology_manifest_hash(manifest: RuntimeTopologyManifest) -> str:
    content: JsonObject = {
        "runtime_key": manifest.runtime_key,
        "manifest_schema_version": manifest.manifest_schema_version,
        "occurrences": cast(JsonValue, encode_json(manifest.occurrences)),
        "curated_operations": cast(JsonValue, encode_json(manifest.curated_operations)),
        "curated_registration_digest": manifest.curated_registration_digest,
    }
    return hashlib.sha256(canonical_json(content).encode()).hexdigest()
