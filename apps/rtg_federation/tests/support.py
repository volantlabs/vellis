from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from apps.rtg_knowledge_graph.mcp_toolset import RtgMcpToolset
from components.rtg.change_validation import DeterministicRtgChangeValidator
from components.rtg.constraints import InMemoryRtgConstraints
from components.rtg.controller import InProcessRtgController
from components.rtg.graph import InMemoryRtgGraph
from components.rtg.migration import InMemoryRtgMigration
from components.rtg.query import SimpleRtgQueryEngine
from components.rtg.schema import (
    InMemoryRtgSchema,
    RtgAnchorSchemaPayload,
    RtgDataObjectSchemaPayload,
    RtgLinkSchemaPayload,
    RtgSchemaDefinition,
    RtgSchemaField,
)
from components.storage.json_file import LocalJsonFileStorage
from components.storage.sql import SqliteStorage
from tools.repo_twin.schema import build_schema as build_repo_twin_schema


def seed_repo_component_snapshot(graph_root: Path, snapshot_path: str) -> None:
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        build_repo_twin_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(graph_root),
        SqliteStorage.open(graph_root / "controller.sqlite"),
    )
    toolset = RtgMcpToolset(controller)
    applied = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "component-with-evidence"},
                "type": "twin.Component",
                "display_name": "component.with_evidence",
                "facts": [
                    {
                        "type": "twin.ComponentFact",
                        "mode": "merge",
                        "properties": {
                            **_common_repo_properties(
                                source_path=(
                                    "model/bibliotek/components/"
                                    "component.with_evidence.sysml"
                                ),
                                lifecycle_status="draft",
                            ),
                            "component_id": "component.with_evidence",
                            "owner": "humans",
                            "declared_code_roots": ["components/with/evidence"],
                            "spec_section_hashes": "{}",
                            "related_component_ids": [],
                            "spec_path": (
                                "model/bibliotek/components/component.with_evidence.sysml"
                            ),
                        },
                    },
                    {
                        "type": "twin.EvidenceRecord",
                        "mode": "merge",
                        "properties": {
                            **_common_repo_properties(
                                source_path="components/with/evidence/tests/test_contract.py",
                                lifecycle_status="passing",
                            ),
                            "kind": "test_run",
                            "command": "pytest components/with/evidence/tests",
                            "passed": True,
                            "summary": "1 passed",
                            "produced_at": "2026-07-09T00:00:00Z",
                            "subject_hashes": "{}",
                            "artifact_path": None,
                        },
                    },
                ],
            },
            {
                "ref": {"local_ref": "component-without-evidence"},
                "type": "twin.Component",
                "display_name": "component.without_evidence",
                "facts": [
                    {
                        "type": "twin.ComponentFact",
                        "mode": "merge",
                        "properties": {
                            **_common_repo_properties(
                                source_path=(
                                    "model/bibliotek/components/"
                                    "component.without_evidence.sysml"
                                ),
                                lifecycle_status="draft",
                            ),
                            "component_id": "component.without_evidence",
                            "owner": "humans",
                            "declared_code_roots": ["components/without/evidence"],
                            "spec_section_hashes": "{}",
                            "related_component_ids": [],
                            "spec_path": (
                                "model/bibliotek/components/component.without_evidence.sysml"
                            ),
                        },
                    }
                ],
            },
        ]
    )
    persisted = toolset.rtg_persist_system_snapshot(snapshot_path, return_snapshot=False)
    assert applied["ok"] is True, applied
    assert persisted["ok"] is True


def seed_personal_ops_snapshot(graph_root: Path, snapshot_path: str) -> None:
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        _build_personal_ops_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(graph_root),
        SqliteStorage.open(graph_root / "controller.sqlite"),
    )
    toolset = RtgMcpToolset(controller)
    anchor_records = [
        {
            "ref": {"local_ref": "invite-beta-testers"},
            "type": "Commitment",
            "display_name": "Invite first beta testers",
            "facts": [
                {
                    "type": "CommitmentFacts",
                    "mode": "merge",
                    "properties": {
                        "title": "Invite first beta testers",
                        "domain": "professional",
                        "status": "next",
                        "priority": "high",
                        "due": "2026-07-17",
                        "made_to": "Self",
                        "source": "planning session",
                        "confidence": "high",
                    },
                }
            ],
        },
        {
            "ref": {"local_ref": "household-reset"},
            "type": "Routine",
            "display_name": "Sunday household reset",
            "facts": [
                {
                    "type": "RoutineFacts",
                    "mode": "merge",
                    "properties": {
                        "title": "Sunday household reset",
                        "domain": "personal",
                        "cadence": "weekly",
                        "status": "active",
                        "next_due": "2026-07-12",
                        "blocker": "unclear shared list",
                    },
                }
            ],
        },
        {
            "ref": {"local_ref": "friday-review-decision"},
            "type": "Decision",
            "display_name": "Use Friday review as primary cadence",
            "facts": [
                {
                    "type": "DecisionFacts",
                    "mode": "merge",
                    "properties": {
                        "title": "Use Friday review as primary cadence",
                        "domain": "professional",
                        "status": "decided",
                        "decided_at": "2026-07-09",
                        "rationale": "Keeps beta decisions close to evidence.",
                        "reversibility": "reversible",
                        "review_date": "2026-08-07",
                    },
                }
            ],
        },
        {
            "ref": {"local_ref": "doctor-reminder"},
            "type": "Evidence",
            "display_name": "Doctor portal reminder",
            "facts": [
                {
                    "type": "EvidenceFacts",
                    "mode": "merge",
                    "properties": {
                        "title": "Doctor portal reminder",
                        "domain": "personal",
                        "kind": "message",
                        "locator": "placeholder:message/doctor-portal",
                        "observed_at": "2026-07-09",
                        "confidence": "medium",
                    },
                }
            ],
        },
        {
            "ref": {"local_ref": "jordan-context"},
            "type": "RelationshipContext",
            "display_name": "Jordan partner context",
            "facts": [
                {
                    "type": "RelationshipContextFacts",
                    "mode": "merge",
                    "properties": {
                        "person_name": "Jordan",
                        "relationship": "partner",
                        "domain": "personal",
                        "last_contact": "2026-07-09",
                        "preference": "shared household context",
                        "open_loop": "align budget and insurance tasks",
                    },
                }
            ],
        },
    ]
    link_writes = [
        {
            "ref": {"local_ref": "doctor-reminder-justifies-beta-invite"},
            "type": "justifies",
            "source_ref": {"local_ref": "doctor-reminder"},
            "target_ref": {"local_ref": "invite-beta-testers"},
        }
    ]
    applied = toolset.rtg_apply_live_anchor_records(
        anchor_records,
        link_writes=link_writes,
    )
    persisted = toolset.rtg_persist_system_snapshot(snapshot_path, return_snapshot=False)
    assert applied["ok"] is True
    assert persisted["ok"] is True


def seed_gothic_archive_snapshot(graph_root: Path, snapshot_path: str) -> None:
    controller = InProcessRtgController.open(
        InMemoryRtgGraph.empty(),
        _build_gothic_archive_schema(),
        InMemoryRtgConstraints.empty(),
        InMemoryRtgMigration.empty(),
        DeterministicRtgChangeValidator(),
        SimpleRtgQueryEngine(),
        LocalJsonFileStorage.open(graph_root),
        SqliteStorage.open(graph_root / "controller.sqlite"),
    )
    toolset = RtgMcpToolset(controller)
    applied = toolset.rtg_apply_live_anchor_records(
        [
            {
                "ref": {"local_ref": "dracula"},
                "type": "Work",
                "display_name": "Dracula",
                "facts": [
                    {
                        "type": "WorkFacts",
                        "mode": "merge",
                        "properties": {
                            "title": "Dracula",
                            "creator": "Bram Stoker",
                            "publication_year": 1897,
                            "public_domain_basis": "Published in 1897.",
                            "source_language": "English",
                            "notes": "Test source index record.",
                            "verification_status": "planning_seed",
                        },
                    }
                ],
            },
            {
                "ref": {"local_ref": "gutenberg-dracula"},
                "type": "Source",
                "display_name": "Project Gutenberg Dracula",
                "facts": [
                    {
                        "type": "SourceFacts",
                        "mode": "merge",
                        "properties": {
                            "label": "Project Gutenberg Dracula",
                            "edition": "ebook 345",
                            "provider": "Project Gutenberg",
                            "url": "https://www.gutenberg.org/ebooks/345",
                            "license_status": "public_domain",
                            "retrieved_at": "2026-07-10",
                            "notes": "Test source record.",
                            "verification_status": "verified",
                        },
                    }
                ],
            },
            {
                "ref": {"local_ref": "lucy-source-span"},
                "type": "Passage",
                "display_name": "Lucy transformation source span",
                "facts": [
                    {
                        "type": "PassageFacts",
                        "mode": "merge",
                        "properties": {
                            "label": "Lucy transformation source span",
                            "source_marker": "Chapter 16",
                            "summary": "A bounded test passage marker.",
                            "quote_policy": "Verify before quoting.",
                            "verification_status": "unverified",
                        },
                    }
                ],
            },
            {
                "ref": {"local_ref": "blood-trail"},
                "type": "ReadingTrail",
                "display_name": "Blood Trail",
                "facts": [
                    {
                        "type": "ReadingTrailFacts",
                        "mode": "merge",
                        "properties": {
                            "label": "Blood Trail",
                            "summary": "Medical crisis to supernatural explanation.",
                            "curation_status": "planning_seed",
                        },
                    }
                ],
            },
        ]
    )
    persisted = toolset.rtg_persist_system_snapshot(snapshot_path, return_snapshot=False)
    assert applied["ok"] is True
    assert persisted["ok"] is True


def _common_repo_properties(*, source_path: str, lifecycle_status: str) -> dict[str, object]:
    return {
        "source_path": source_path,
        "source_hash": "test-hash",
        "repo_commit": "test-commit",
        "last_indexed_at": "2026-07-09T00:00:00Z",
        "authority": "repo",
        "lifecycle_status": lifecycle_status,
    }


def _build_personal_ops_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    fact_fields = {
        "CommitmentFacts": (
            "title",
            "domain",
            "status",
            "priority",
            "due",
            "made_to",
            "source",
            "confidence",
        ),
        "RoutineFacts": ("title", "domain", "cadence", "status", "next_due", "blocker"),
        "DecisionFacts": (
            "title",
            "domain",
            "status",
            "decided_at",
            "rationale",
            "reversibility",
            "review_date",
        ),
        "EvidenceFacts": ("title", "domain", "kind", "locator", "observed_at", "confidence"),
        "RelationshipContextFacts": (
            "person_name",
            "relationship",
            "domain",
            "last_contact",
            "preference",
            "open_loop",
        ),
    }
    anchor_facts = {
        "Commitment": "CommitmentFacts",
        "Routine": "RoutineFacts",
        "Decision": "DecisionFacts",
        "Evidence": "EvidenceFacts",
        "RelationshipContext": "RelationshipContextFacts",
    }
    for anchor_type, fact_type in anchor_facts.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="anchor",
                type_key=anchor_type,
                description=f"{anchor_type} anchor.",
                payload=RtgAnchorSchemaPayload(required_data_types=(fact_type,)),
                time_shape="state_now",
            )
        )
    schema.put_definition(
        RtgSchemaDefinition(
            uuid=uuid4(),
            kind="link",
            type_key="justifies",
            description="Evidence justifies commitments.",
            payload=RtgLinkSchemaPayload(
                allowed_source_types=("Evidence",),
                allowed_target_types=("Commitment",),
                link_kind="semantic",
            ),
        )
    )
    for fact_type, fields in fact_fields.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="data_object",
                type_key=fact_type,
                description=f"{fact_type} data.",
                payload=RtgDataObjectSchemaPayload(
                    properties={
                        field: RtgSchemaField(required=True, value_kinds=("string",))
                        for field in fields
                    }
                ),
                time_shape="state_now",
            )
        )
    return schema


def _build_gothic_archive_schema() -> InMemoryRtgSchema:
    schema = InMemoryRtgSchema.empty()
    fact_fields: dict[str, dict[str, tuple[bool, str]]] = {
        "WorkFacts": {
            "title": (True, "string"),
            "creator": (True, "string"),
            "publication_year": (True, "integer"),
            "public_domain_basis": (True, "string"),
            "source_language": (False, "string"),
            "notes": (False, "string"),
            "verification_status": (True, "string"),
        },
        "SourceFacts": {
            "label": (True, "string"),
            "edition": (False, "string"),
            "provider": (True, "string"),
            "url": (False, "string"),
            "license_status": (True, "string"),
            "retrieved_at": (False, "string"),
            "notes": (False, "string"),
            "verification_status": (True, "string"),
        },
        "PassageFacts": {
            "label": (True, "string"),
            "source_marker": (True, "string"),
            "summary": (True, "string"),
            "quote_policy": (True, "string"),
            "verification_status": (True, "string"),
        },
        "ReadingTrailFacts": {
            "label": (True, "string"),
            "summary": (True, "string"),
            "curation_status": (True, "string"),
        },
    }
    anchor_facts = {
        "Work": "WorkFacts",
        "Source": "SourceFacts",
        "Passage": "PassageFacts",
        "ReadingTrail": "ReadingTrailFacts",
    }
    for anchor_type, fact_type in anchor_facts.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="anchor",
                type_key=anchor_type,
                description=f"{anchor_type} anchor.",
                payload=RtgAnchorSchemaPayload(required_data_types=(fact_type,)),
                time_shape="state_now",
            )
        )
    for fact_type, fields in fact_fields.items():
        schema.put_definition(
            RtgSchemaDefinition(
                uuid=uuid4(),
                kind="data_object",
                type_key=fact_type,
                description=f"{fact_type} data.",
                payload=RtgDataObjectSchemaPayload(
                    properties={
                        field: RtgSchemaField(required=required, value_kinds=(value_kind,))
                        for field, (required, value_kind) in fields.items()
                    }
                ),
                time_shape="state_now",
            )
        )
    return schema
