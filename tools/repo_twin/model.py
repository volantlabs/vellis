from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid5

from components.rtg.graph.protocol import JsonObject

TWIN_NAMESPACE = UUID("90879669-4a48-5f34-a67c-e7f5124e8fd8")
SCHEMA_VERSION = "1"
IMPORTER_VERSION = "sysml-authority-1"
SNAPSHOT_PATH = "snapshots/current.json"


@dataclass(frozen=True, slots=True)
class AnchorRecord:
    natural_key: str
    type_key: str
    display_name: str

    @property
    def uuid(self) -> UUID:
        return twin_uuid(self.natural_key)


@dataclass(frozen=True, slots=True)
class DataRecord:
    natural_key: str
    type_key: str
    properties: JsonObject
    anchor_keys: tuple[str, ...]

    @property
    def uuid(self) -> UUID:
        return twin_uuid(self.natural_key)


@dataclass(frozen=True, slots=True)
class LinkRecord:
    type_key: str
    source_key: str
    target_key: str

    @property
    def natural_key(self) -> str:
        return f"{self.type_key}:{self.source_key}:{self.target_key}"

    @property
    def uuid(self) -> UUID:
        return twin_uuid(self.natural_key)


@dataclass(frozen=True, slots=True)
class RepoMetadata:
    repo_commit: str
    branch: str
    dirty: bool
    indexed_at: str


@dataclass(frozen=True, slots=True)
class ParseIssue:
    source_path: str
    message: str


@dataclass(frozen=True, slots=True)
class ComponentScan:
    component_id: str
    status: str
    spec_path: str
    declared_code_roots: tuple[str, ...]
    section_hashes: dict[str, str]
    related_component_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImplementationScan:
    path: str
    source_hash: str
    has_protocol: bool
    has_implementation: bool
    has_reference: bool
    has_tests: bool
    protocol_hash: str | None
    file_count: int
    test_file_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScanResult:
    anchors: tuple[AnchorRecord, ...]
    data_objects: tuple[DataRecord, ...]
    links: tuple[LinkRecord, ...]
    components: dict[str, ComponentScan]
    implementation_roots: dict[str, ImplementationScan]
    parse_issues: tuple[ParseIssue, ...] = ()
    duplicate_component_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    severity: str
    subject: str
    detail: str
    suggested_action: str

    def to_json(self) -> JsonObject:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity,
            "subject": self.subject,
            "detail": self.detail,
            "suggested_action": self.suggested_action,
        }


@dataclass(frozen=True, slots=True)
class SyncSummary:
    created: int
    updated: int
    pruned: int
    anchors: int
    data_objects: int
    links: int

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.pruned)


_EARLIEST_TIMESTAMP = datetime.min.replace(tzinfo=UTC)


def produced_at_timestamp(properties: JsonObject) -> datetime:
    """Parse an evidence record's produced_at into a comparable UTC datetime.

    Accepts both legacy second-granularity values (``...T04:52:08Z``) and
    microsecond-precision values; unparsable or missing values sort earliest.
    """
    raw = properties.get("produced_at")
    if not isinstance(raw, str) or not raw:
        return _EARLIEST_TIMESTAMP
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return _EARLIEST_TIMESTAMP
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def twin_uuid(natural_key: str) -> UUID:
    return uuid5(TWIN_NAMESPACE, natural_key)


def managed_system(natural_key: str, *, authority: str = "repo") -> JsonObject:
    return {
        "live": True,
        "twin_managed": "repo_twin",
        "natural_key": natural_key,
        "authority": authority,
        "schema_version": SCHEMA_VERSION,
        "importer_version": IMPORTER_VERSION,
    }
