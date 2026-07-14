from __future__ import annotations

from uuid import UUID, uuid5

from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
)
from tools.repo_twin.model import TWIN_NAMESPACE

_COMMON_FIELDS = {
    "source_path": RtgSchemaField(required=True, value_kinds=("string",)),
    "source_hash": RtgSchemaField(required=True, value_kinds=("string",)),
    "repo_commit": RtgSchemaField(required=True, value_kinds=("string",)),
    "last_indexed_at": RtgSchemaField(required=True, value_kinds=("string",)),
    "authority": RtgSchemaField(required=True, value_kinds=("string",)),
    "lifecycle_status": RtgSchemaField(required=True, value_kinds=("string",)),
}


def build_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    for type_key, data_types in {
        "twin.Repo": ("twin.RepoFact", "twin.EvidenceRecord"),
        "twin.Component": (
            "twin.ComponentFact",
            "twin.Invariant",
            "twin.OpenQuestion",
            "twin.EvidenceRecord",
        ),
        "twin.SpecDocument": ("twin.SpecDocumentFact",),
        "twin.ImplementationRoot": ("twin.ImplementationRootFact",),
        "twin.App": ("twin.AppFact",),
        "twin.TestSuite": ("twin.TestSuiteFact", "twin.EvidenceRecord"),
    }.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=_schema_uuid("anchor", type_key),
                kind="anchor",
                type_key=type_key,
                description=f"{type_key} anchor.",
                payload=RtgAnchorSchemaPayload(optional_data_types=data_types),
            )
        )

    data_definitions = {
        "twin.RepoFact": {
            **_COMMON_FIELDS,
            "branch": _field("string"),
            "dirty": _field("boolean"),
            "importer_version": _field("string"),
            "schema_version": _field("string"),
        },
        "twin.ComponentFact": {
            **_COMMON_FIELDS,
            "component_id": _field("string"),
            "owner": _field("string"),
            "declared_code_roots": _field("list"),
            "spec_section_hashes": _field("string"),
            "related_component_ids": _field("list"),
            "spec_path": _field("string"),
        },
        "twin.SpecDocumentFact": {
            **_COMMON_FIELDS,
            "title": _field("string"),
            "frontmatter_id": _field("string"),
            "frontmatter_status": _field("string"),
            "section_titles": _field("list"),
        },
        "twin.ImplementationRootFact": {
            **_COMMON_FIELDS,
            "language": _field("string"),
            "has_protocol": _field("boolean"),
            "has_implementation": _field("boolean"),
            "has_reference": _field("boolean"),
            "has_tests": _field("boolean"),
            "protocol_hash": _field("string", "null"),
            "file_count": _field("integer"),
        },
        "twin.AppFact": {
            **_COMMON_FIELDS,
            "entry_point": _field("string", "null"),
            "module_names": _field("list"),
        },
        "twin.TestSuiteFact": {
            **_COMMON_FIELDS,
            "test_file_names": _field("list"),
            "test_file_count": _field("integer"),
        },
        "twin.Invariant": {
            **_COMMON_FIELDS,
            "invariant_name": _field("string"),
            "component_id": _field("string"),
        },
        "twin.OpenQuestion": {
            **_COMMON_FIELDS,
            "question_text": _field("string"),
            "question_hash": _field("string"),
            "component_id": _field("string"),
            "ordinal": _field("integer"),
        },
        "twin.EvidenceRecord": {
            **_COMMON_FIELDS,
            "kind": _field("string"),
            "command": _field("string"),
            "passed": _field("boolean"),
            "summary": _field("string"),
            "produced_at": _field("string"),
            "subject_hashes": _field("string"),
            "artifact_path": _field("string", "null"),
        },
    }
    for type_key, fields in data_definitions.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=_schema_uuid("data_object", type_key),
                kind="data_object",
                type_key=type_key,
                description=f"{type_key} facts.",
                payload=RtgDataObjectSchemaPayload(properties=fields),
            )
        )

    link_definitions = {
        "twin.HasSpec": (("twin.Component",), ("twin.SpecDocument",)),
        "twin.HasImplementationRoot": (("twin.Component",), ("twin.ImplementationRoot",)),
        "twin.HasTestSuite": (("twin.ImplementationRoot",), ("twin.TestSuite",)),
        "twin.Verifies": (("twin.TestSuite",), ("twin.Component",)),
        "twin.DependsOn": (("twin.Component",), ("twin.Component",)),
        "twin.ComposedOf": (("twin.App",), ("twin.Component",)),
    }
    for type_key, (sources, targets) in link_definitions.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=_schema_uuid("link", type_key),
                kind="link",
                type_key=type_key,
                description=f"{type_key} relationship.",
                payload=RtgLinkSchemaPayload(
                    allowed_source_types=sources,
                    allowed_target_types=targets,
                ),
            )
        )
    return schema


def _field(*kinds: str) -> RtgSchemaField:
    return RtgSchemaField(required=True, value_kinds=kinds)


def _schema_uuid(kind: str, type_key: str) -> UUID:
    return uuid5(TWIN_NAMESPACE, f"schema:{kind}:{type_key}")
