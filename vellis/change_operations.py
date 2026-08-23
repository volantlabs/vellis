"""Atomic field-level graph changes over the indexed canonical state."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import fields, is_dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from vellis.activity_repository import append_activity, canonical_activity_effect
from vellis.canonical_encoding import CanonicalHeader, canonical_record_hash
from vellis.cardinality_validation import CardinalitySubjects
from vellis.database import connect_database, require_supported_database
from vellis.definition_repository import load_definitions
from vellis.domain import (
    PUBLIC_ITEM_LIMIT,
    Anchor,
    AnchorUpsert,
    AssociatedData,
    AssociatedDataTypeDefinition,
    AssociatedDataUpsert,
    CurrentState,
    Finding,
    FindingCode,
    GraphChangeRequest,
    GraphObject,
    Link,
    LinkTypeDefinition,
    LinkUpsert,
    OperationOutcome,
    OperationStatus,
    ScalarValue,
    SystemEnvelope,
    parse_timestamp,
)
from vellis.domain_validation import graph_cardinality_findings, graph_structure_findings
from vellis.graph_repository import close_graph_versions, insert_graph_versions, load_graph_objects
from vellis.public_wire import public_result
from vellis.search_repository import close_search_versions, insert_search_versions
from vellis.state_repository import resolve_state
from vellis.wire import serialize_wire


def apply_graph_change(
    database_path: Path,
    request: GraphChangeRequest,
    *,
    initiator: str = "agent",
    source: str | None = None,
) -> OperationOutcome:
    connection = connect_database(database_path)
    try:
        require_supported_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        state = resolve_state(connection, CurrentState())
        findings = _request_findings(request)
        if request.expected_revision != state.evaluated_revision:
            findings = (
                *findings,
                Finding(
                    FindingCode.STALE_REVISION,
                    "expected revision does not equal the current revision",
                    "/expectedRevision",
                ),
            )
        commanded_uuids = tuple(
            dict.fromkeys((*request.remove_uuids, *(value.uuid for value in request.upserts)))
        )
        current = load_graph_objects(connection, state, commanded_uuids)
        if not findings:
            proposed_commands, compose_findings = compose_graph_change(
                connection, current, request.upserts, request.remove_uuids
            )
            (
                closure,
                definitions,
                cardinality_definitions,
                cardinality_uuids,
                cardinality_scope,
            ) = _validation_closure(connection, state, commanded_uuids, current, proposed_commands)
            proposed = _replace_commands(closure, proposed_commands, commanded_uuids)
            cardinality_graph = tuple(
                value for value in proposed if value.uuid in cardinality_uuids
            )
            findings = (
                *compose_findings,
                *graph_structure_findings(proposed, definitions, require_system=False),
                *graph_cardinality_findings(
                    cardinality_graph, cardinality_definitions, cardinality_scope
                ),
            )
        else:
            proposed_commands = current
            definitions = ()
        if findings:
            result = OperationOutcome(
                OperationStatus.REJECTED,
                "graph change was rejected",
                tuple(findings),
                state.evaluated_revision,
            )
            serialize_wire(result)
            append_activity(
                connection,
                capability="rtg_change",
                outcome="rejected",
                initiator=initiator,
                source=source,
                evaluated_revision=state.evaluated_revision,
                resulting_revision=None,
                summary=result.summary,
                semantic_payload={"request": _wire(request), "findings": _wire(result.findings)},
                verbose_payload={"request": _wire(request), "response": public_result(result)},
            )
            connection.commit()
            return result
        changed, removed = _semantic_difference(current, proposed_commands)
        if not changed and not removed:
            result = OperationOutcome(
                OperationStatus.ACCEPTED,
                "graph change had no canonical effect",
                (),
                state.evaluated_revision,
            )
            serialize_wire(result)
            append_activity(
                connection,
                capability="rtg_change",
                outcome="accepted",
                initiator=initiator,
                source=source,
                evaluated_revision=state.evaluated_revision,
                resulting_revision=None,
                summary=result.summary,
                semantic_payload=canonical_activity_effect(connection, None),
                verbose_payload={"request": _wire(request), "response": public_result(result)},
            )
            connection.commit()
            return result
        revision = state.evaluated_revision + 1
        canonical_changed = tuple(_canonical_object(value, revision) for value in changed)
        _publish_graph_revision(
            connection,
            revision,
            canonical_changed,
            removed,
            definitions,
            initiator,
            source,
        )
        result = OperationOutcome(
            OperationStatus.ACCEPTED,
            "graph change committed",
            (),
            state.evaluated_revision,
            revision,
        )
        serialize_wire(result)
        append_activity(
            connection,
            capability="rtg_change",
            outcome="accepted",
            initiator=initiator,
            source=source,
            evaluated_revision=state.evaluated_revision,
            resulting_revision=revision,
            summary=result.summary,
            semantic_payload=canonical_activity_effect(connection, revision),
            verbose_payload={"request": _wire(request), "response": public_result(result)},
        )
        connection.commit()
        return result
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def compose_graph_change(
    connection: sqlite3.Connection,
    current: tuple[GraphObject, ...],
    upserts: tuple[AnchorUpsert | AssociatedDataUpsert | LinkUpsert, ...],
    removals: tuple[str, ...],
) -> tuple[tuple[GraphObject, ...], tuple[Finding, ...]]:
    values = {value.uuid: value for value in current}
    findings: list[Finding] = []
    for index, upsert in enumerate(upserts):
        existing = values.get(upsert.uuid)
        reservation = connection.execute(
            "SELECT kind, created_revision, legacy_v1 FROM graph_object_identity WHERE uuid = ?",
            (upsert.uuid,),
        ).fetchone()
        if reservation is not None and str(reservation["kind"]) != upsert.kind.value:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "UUID is permanently reserved to another object kind",
                    f"/upserts/{index}/uuid",
                    uuids=(upsert.uuid,),
                )
            )
            continue
        if existing is not None and existing.kind is not upsert.kind:
            findings.append(
                Finding(
                    FindingCode.KIND_MISMATCH,
                    "object kind cannot change",
                    f"/upserts/{index}/kind",
                    uuids=(upsert.uuid,),
                )
            )
            continue
        try:
            values[upsert.uuid] = _compose_object(existing, upsert, reservation)
        except ValueError as error:
            findings.append(
                Finding(
                    FindingCode.INVALID_VALUE, str(error), f"/upserts/{index}", uuids=(upsert.uuid,)
                )
            )
    for uuid in removals:
        values.pop(uuid, None)
    return tuple(values[key] for key in sorted(values)), _ordered(findings)


def _compose_object(existing, upsert, reservation) -> GraphObject:
    system = _prospective_system(existing, reservation)
    if isinstance(upsert, AnchorUpsert):
        if existing is None:
            if upsert.type_key is None or upsert.display_name is None:
                raise ValueError("anchor creation requires typeKey and displayName")
            return Anchor(upsert.uuid, upsert.type_key, upsert.display_name, system)
        assert isinstance(existing, Anchor)
        return Anchor(
            existing.uuid,
            existing.type_key if upsert.type_key is None else upsert.type_key,
            existing.display_name if upsert.display_name is None else upsert.display_name,
            existing.system,
        )
    if isinstance(upsert, AssociatedDataUpsert):
        return _compose_data(existing, upsert, system)
    assert isinstance(upsert, LinkUpsert)
    if existing is None:
        if upsert.type_key is None or upsert.source_uuid is None or upsert.target_uuid is None:
            raise ValueError("link creation requires typeKey, sourceUuid, and targetUuid")
        return Link(upsert.uuid, upsert.type_key, upsert.source_uuid, upsert.target_uuid, system)
    assert isinstance(existing, Link)
    return Link(
        existing.uuid,
        existing.type_key if upsert.type_key is None else upsert.type_key,
        existing.source_uuid if upsert.source_uuid is None else upsert.source_uuid,
        existing.target_uuid if upsert.target_uuid is None else upsert.target_uuid,
        existing.system,
    )


def _compose_data(existing, upsert: AssociatedDataUpsert, system) -> AssociatedData:
    if existing is None:
        if upsert.type_key is None or upsert.anchor_uuids is None:
            raise ValueError("associated-data creation requires typeKey and anchorUuids")
        if upsert.add_anchor_uuids or upsert.remove_anchor_uuids:
            raise ValueError("associated-data creation cannot add or remove anchors")
        anchors = set(upsert.anchor_uuids)
        properties = dict(upsert.set_properties)
        return AssociatedData(
            upsert.uuid, upsert.type_key, tuple(anchors), tuple(properties.items()), system
        )
    assert isinstance(existing, AssociatedData)
    if upsert.anchor_uuids is not None:
        raise ValueError("associated-data update cannot supply complete anchorUuids")
    anchors = set(existing.anchor_uuids)
    anchors.update(upsert.add_anchor_uuids)
    anchors.difference_update(upsert.remove_anchor_uuids)
    properties = dict(existing.properties)
    properties.update(upsert.set_properties)
    for name in upsert.remove_properties:
        properties.pop(name, None)
    return AssociatedData(
        existing.uuid,
        existing.type_key if upsert.type_key is None else upsert.type_key,
        tuple(anchors),
        tuple(properties.items()),
        existing.system,
    )


def _prospective_system(existing, reservation) -> SystemEnvelope | None:
    if existing is not None:
        return existing.system
    if reservation is None:
        return None
    return SystemEnvelope(
        int(reservation["created_revision"]),
        int(reservation["created_revision"]),
        None if reservation["legacy_v1"] is None else str(reservation["legacy_v1"]),
    )


def _request_findings(
    request: GraphChangeRequest,
    *,
    upserts_path: str = "/upserts",
    removals_path: str = "/removeUuids",
    check_command_duplicates: bool = True,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    commands = [
        (value.uuid, f"{upserts_path}/{index}/uuid") for index, value in enumerate(request.upserts)
    ]
    commands.extend(
        (uuid, f"{removals_path}/{index}") for index, uuid in enumerate(request.remove_uuids)
    )
    if check_command_duplicates:
        _duplicate_command_paths(commands, "UUID occurs in more than one command", findings)
    if len(commands) > PUBLIC_ITEM_LIMIT:
        findings.append(
            Finding(
                FindingCode.INVALID_VALUE,
                f"change exceeds {PUBLIC_ITEM_LIMIT} commands",
                "",
            )
        )
    for index, value in enumerate(request.upserts):
        if isinstance(value, AssociatedDataUpsert):
            _duplicates(
                value.anchor_uuids or (),
                f"{upserts_path}/{index}/anchorUuids",
                "duplicate anchor",
                findings,
            )
            _duplicates(
                value.add_anchor_uuids,
                f"{upserts_path}/{index}/addAnchorUuids",
                "duplicate anchor",
                findings,
            )
            _duplicates(
                value.remove_anchor_uuids,
                f"{upserts_path}/{index}/removeAnchorUuids",
                "duplicate anchor",
                findings,
            )
            _duplicates(
                (name for name, _ in value.set_properties),
                f"{upserts_path}/{index}/setProperties",
                "duplicate property",
                findings,
            )
            _duplicates(
                value.remove_properties,
                f"{upserts_path}/{index}/removeProperties",
                "duplicate property",
                findings,
            )
            if set(value.add_anchor_uuids) & set(value.remove_anchor_uuids):
                findings.append(
                    Finding(
                        FindingCode.CONFLICT,
                        "anchor cannot be both added and removed",
                        f"{upserts_path}/{index}",
                    )
                )
            if {name for name, _ in value.set_properties} & set(value.remove_properties):
                findings.append(
                    Finding(
                        FindingCode.CONFLICT,
                        "property cannot be both set and removed",
                        f"{upserts_path}/{index}",
                    )
                )
    return _ordered(findings)


def _semantic_difference(current, proposed):
    old = {value.uuid: value for value in current}
    new = {value.uuid: value for value in proposed}
    changed = tuple(
        value
        for uuid, value in new.items()
        if uuid not in old or _content(value) != _content(old[uuid])
    )
    removed = tuple(sorted(set(old) - set(new)))
    return changed, removed


def _validation_closure(connection, state, commanded_uuids, current, proposed):
    cardinality_impacts, dependent_endpoints = _semantic_impacts(current, proposed)
    dependent_uuids = _dependent_uuids(connection, dependent_endpoints)
    structural = (*current, *proposed)
    structural_type_keys = {value.type_key for value in structural}
    cardinality_type_keys = {value.type_key for value in cardinality_impacts}
    endpoint_type_keys = {
        value.type_key for value in cardinality_impacts if not isinstance(value, Link)
    }
    cardinality_keys = _affected_definition_keys(
        connection, cardinality_type_keys, endpoint_type_keys
    )
    definition_keys = structural_type_keys | cardinality_keys
    definitions = load_definitions(connection, state, tuple(sorted(definition_keys)))
    cardinality_definitions = tuple(
        value for value in definitions if value.type_key in cardinality_keys
    )
    cardinality_uuids, cardinality_scope = _cardinality_closure_uuids(
        connection, cardinality_definitions, cardinality_impacts
    )
    closure_uuids = dependent_uuids | cardinality_uuids | set(commanded_uuids)
    closure_uuids.update(_dependent_referents(connection, dependent_uuids))
    closure_uuids.update(_referenced_uuids((*current, *proposed)))
    graph = _load_structural_closure(connection, state, closure_uuids)
    header_keys = tuple(sorted({value.type_key for value in graph} - definition_keys))
    if header_keys:
        extra = load_definitions(connection, state, header_keys)
        definitions = tuple({value.type_key: value for value in (*definitions, *extra)}.values())
    return graph, definitions, cardinality_definitions, cardinality_uuids, cardinality_scope


def _load_structural_closure(connection, state, initial_uuids):
    """Load every referent needed to validate the selected local closure."""
    requested = set(initial_uuids)
    objects = {
        value.uuid: value
        for value in load_graph_objects(connection, state, tuple(sorted(requested)))
    }
    while True:
        missing = _referenced_uuids(tuple(objects.values())) - requested
        if not missing:
            return tuple(objects[key] for key in sorted(objects))
        requested.update(missing)
        loaded = load_graph_objects(connection, state, tuple(sorted(missing)))
        objects.update((value.uuid, value) for value in loaded)


def _semantic_impacts(current, proposed):
    old = {value.uuid: value for value in current}
    new = {value.uuid: value for value in proposed}
    cardinality = []
    dependent_endpoints = set()
    for uuid in old.keys() | new.keys():
        before, after = old.get(uuid), new.get(uuid)
        if before is not None and after is not None and _content(before) == _content(after):
            continue
        if _changes_cardinality(before, after):
            if before is not None:
                cardinality.append(before)
            if after is not None:
                cardinality.append(after)
        if (
            before is not None
            and not isinstance(before, Link)
            and (after is None or before.type_key != after.type_key)
        ):
            dependent_endpoints.add(uuid)
    return tuple(cardinality), dependent_endpoints


def _changes_cardinality(before, after):
    if before is None or after is None or before.kind is not after.kind:
        return True
    if before.type_key != after.type_key:
        return True
    if isinstance(before, AssociatedData):
        assert isinstance(after, AssociatedData)
        return before.anchor_uuids != after.anchor_uuids
    if isinstance(before, Link):
        assert isinstance(after, Link)
        return (before.source_uuid, before.target_uuid) != (after.source_uuid, after.target_uuid)
    return False


def _dependent_uuids(connection, endpoint_uuids):
    if not endpoint_uuids:
        return set()
    encoded = json.dumps(sorted(endpoint_uuids), separators=(",", ":"))
    rows = connection.execute(
        """SELECT uuid FROM graph_object_version
           WHERE valid_to_revision IS NULL AND (
               source_uuid IN (SELECT value FROM json_each(?))
               OR target_uuid IN (SELECT value FROM json_each(?))
               OR uuid IN (
                   SELECT object_uuid FROM direct_association_version
                   WHERE valid_to_revision IS NULL
                     AND anchor_uuid IN (SELECT value FROM json_each(?))
               )
           )""",
        (encoded, encoded, encoded),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _dependent_referents(connection, dependent_uuids):
    if not dependent_uuids:
        return set()
    encoded = json.dumps(sorted(dependent_uuids), separators=(",", ":"))
    structural = connection.execute(
        """SELECT source_uuid, target_uuid FROM graph_object_version
           WHERE valid_to_revision IS NULL
             AND uuid IN (SELECT value FROM json_each(?))""",
        (encoded,),
    ).fetchall()
    associations = connection.execute(
        """SELECT anchor_uuid FROM direct_association_version
           WHERE valid_to_revision IS NULL
             AND object_uuid IN (SELECT value FROM json_each(?))""",
        (encoded,),
    ).fetchall()
    return {str(value) for row in structural for value in row if value is not None} | {
        str(row[0]) for row in associations
    }


def _cardinality_closure_uuids(connection, definitions, changed_objects):
    """Select the subjects of each definition whose count this change can alter.

    The subject sets stay separated by definition and by role. A flat uuid set
    would make every closure member a subject of every definition in scope, which
    counts an endpoint under a definition whose population was never loaded.
    """
    uuids = set()
    scope: dict[str, CardinalitySubjects] = {}
    for definition in definitions:
        if isinstance(definition, AssociatedDataTypeDefinition):
            uuids.update(
                value.uuid
                for value in changed_objects
                if isinstance(value, AssociatedData) and value.type_key == definition.type_key
            )
            subjects = {
                anchor_uuid
                for value in changed_objects
                if isinstance(value, AssociatedData) and value.type_key == definition.type_key
                for anchor_uuid in value.anchor_uuids
            }
            subjects.update(
                value.uuid
                for value in changed_objects
                if isinstance(value, Anchor)
                and value.type_key in definition.permitted_anchor_type_keys
            )
            if not _constrains(definition.objects_per_anchor):
                subjects = set()
            uuids.update(subjects)
            uuids.update(_data_count_peers(connection, definition.type_key, subjects))
            scope[definition.type_key] = CardinalitySubjects(data_anchors=frozenset(subjects))
        elif isinstance(definition, LinkTypeDefinition):
            uuids.update(
                value.uuid
                for value in changed_objects
                if isinstance(value, Link) and value.type_key == definition.type_key
            )
            sources, targets = _link_count_subjects(definition, changed_objects)
            if not _constrains(definition.links_per_source):
                sources = set()
            if not _constrains(definition.links_per_target):
                targets = set()
            uuids.update((*sources, *targets))
            uuids.update(_link_count_peers(connection, definition.type_key, sources, targets))
            scope[definition.type_key] = CardinalitySubjects(
                link_sources=frozenset(sources), link_targets=frozenset(targets)
            )
    return uuids, scope


def _constrains(cardinality) -> bool:
    """Whether this bound can ever produce a finding.

    An unbounded role admits every count, so neither its subjects nor its
    population need loading. Materializing them would make an ordinary change
    cost the endpoint's whole degree to satisfy a bound that cannot be violated.
    """
    return cardinality.minimum > 0 or cardinality.maximum is not None


def _data_count_peers(connection, type_key, subjects):
    if not subjects:
        return set()
    encoded = json.dumps(sorted(subjects), separators=(",", ":"))
    rows = connection.execute(
        """SELECT DISTINCT a.object_uuid
           FROM direct_association_version AS a
           JOIN graph_object_version AS o ON o.uuid = a.object_uuid
           WHERE a.valid_to_revision IS NULL AND o.valid_to_revision IS NULL
             AND o.type_key = ?
             AND a.anchor_uuid IN (SELECT value FROM json_each(?))""",
        (type_key, encoded),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _link_count_subjects(definition, changed_objects):
    sources = {
        value.source_uuid
        for value in changed_objects
        if isinstance(value, Link) and value.type_key == definition.type_key
    }
    targets = {
        value.target_uuid
        for value in changed_objects
        if isinstance(value, Link) and value.type_key == definition.type_key
    }
    sources.update(
        value.uuid
        for value in changed_objects
        if not isinstance(value, Link) and value.type_key in definition.permitted_source_type_keys
    )
    targets.update(
        value.uuid
        for value in changed_objects
        if not isinstance(value, Link) and value.type_key in definition.permitted_target_type_keys
    )
    return sources, targets


def _link_count_peers(connection, type_key, sources, targets):
    # Each endpoint is counted only in the role that admitted it, so only that
    # role's population has to be loaded. Loading both roles would materialize an
    # endpoint's whole degree to satisfy a bound the change cannot affect.
    if not sources and not targets:
        return set()
    source_json = json.dumps(sorted(sources), separators=(",", ":"))
    target_json = json.dumps(sorted(targets), separators=(",", ":"))
    rows = connection.execute(
        """SELECT uuid FROM graph_object_version
           WHERE valid_to_revision IS NULL AND type_key = ?
             AND (source_uuid IN (SELECT value FROM json_each(?))
                  OR target_uuid IN (SELECT value FROM json_each(?)))""",
        (type_key, source_json, target_json),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _affected_definition_keys(connection, affected_types, endpoint_types):
    keys = set(affected_types)
    if endpoint_types:
        encoded = json.dumps(sorted(endpoint_types), separators=(",", ":"))
        rows = connection.execute(
            """SELECT DISTINCT p.type_key
               FROM definition_permitted_type AS p
               JOIN definition_version AS d
                 ON d.type_key = p.type_key AND d.valid_from_revision = p.valid_from_revision
               WHERE p.valid_to_revision IS NULL AND d.valid_to_revision IS NULL
                 AND p.permitted_type_key IN (SELECT value FROM json_each(?))""",
            (encoded,),
        ).fetchall()
        keys.update(str(row[0]) for row in rows)
    return keys


def _referenced_uuids(values):
    uuids = set()
    for value in values:
        if isinstance(value, AssociatedData):
            uuids.update(value.anchor_uuids)
        elif isinstance(value, Link):
            uuids.update((value.source_uuid, value.target_uuid))
    return uuids


def _replace_commands(closure, proposed, commanded_uuids):
    values = {value.uuid: value for value in closure if value.uuid not in commanded_uuids}
    values.update((value.uuid, value) for value in proposed)
    return tuple(values[key] for key in sorted(values))


def _content(value: GraphObject) -> tuple:
    if isinstance(value, Anchor):
        return value.kind, value.type_key, value.display_name
    if isinstance(value, AssociatedData):
        return value.kind, value.type_key, value.anchor_uuids, value.properties
    return value.kind, value.type_key, value.source_uuid, value.target_uuid


def _canonical_object(value: GraphObject, revision: int) -> GraphObject:
    created = revision if value.system is None else value.system.created_revision
    legacy = None if value.system is None else value.system.legacy_v1
    return replace(value, system=SystemEnvelope(created, revision, legacy))


def _publish_graph_revision(connection, revision, changed, removed, definitions, initiator, source):
    previous = connection.execute(
        """SELECT c.record_hash, c.recorded_at, m.lineage_uuid
           FROM canonical_record AS c JOIN metadata_setting AS m ON m.head_revision = c.revision
           WHERE m.singleton = 1"""
    ).fetchone()
    if previous is None:
        raise ValueError("canonical head is absent")
    timestamp = _canonical_time(str(previous["recorded_at"]))
    affected = tuple(sorted((*removed, *(value.uuid for value in changed))))
    summary = f"Graph change: objects={len(affected)}"
    previous_hash = bytes(previous["record_hash"])
    connection.execute(
        """INSERT INTO canonical_record(
           revision, recorded_at, recorded_epoch_seconds, recorded_nanosecond,
           initiator, source, transition_kind, summary, affected_type_keys,
           affected_uuids, previous_hash, record_hash)
           VALUES (?, ?, ?, ?, ?, ?, 'graphChange', ?, '[]', ?, ?, ?)""",
        (
            revision,
            timestamp.canonical,
            timestamp.epoch_seconds,
            timestamp.nanosecond,
            initiator,
            source,
            summary,
            json.dumps(affected, separators=(",", ":")),
            previous_hash,
            bytes(32),
        ),
    )
    retired = close_graph_versions(connection, affected, revision)
    close_search_versions(connection, affected, revision)
    introduced = insert_graph_versions(connection, changed, definitions, revision)
    insert_search_versions(connection, changed, revision)
    header = CanonicalHeader(
        str(previous["lineage_uuid"]),
        revision,
        timestamp,
        initiator,
        source,
        "graphChange",
        summary,
    )
    digest = canonical_record_hash(previous_hash, header, introduced, retired)
    connection.execute(
        "UPDATE canonical_record SET record_hash = ? WHERE revision = ?", (digest, revision)
    )
    connection.execute(
        "UPDATE metadata_setting SET head_revision = ? WHERE singleton = 1", (revision,)
    )


def _canonical_time(previous_text: str):
    previous = parse_timestamp(previous_text)
    now = parse_timestamp(datetime.now(UTC).isoformat().replace("+00:00", "Z"))
    if (now.epoch_seconds, now.nanosecond) < (previous.epoch_seconds, previous.nanosecond):
        return previous
    return now


def _duplicates(values, path, summary, findings):
    seen = set()
    for index, value in enumerate(values):
        if value in seen:
            findings.append(Finding(FindingCode.DUPLICATE, summary, f"{path}/{index}"))
        seen.add(value)


def _duplicate_command_paths(commands, summary, findings):
    seen = set()
    for value, path in commands:
        if value in seen:
            findings.append(Finding(FindingCode.DUPLICATE, summary, path))
        seen.add(value)


def _ordered(findings):
    return tuple(
        sorted(
            findings, key=lambda v: (v.code.value, v.path or "", v.type_keys, v.uuids, v.summary)
        )
    )


def _wire(value):
    if isinstance(value, ScalarValue):
        return {"kind": value.kind.value, "value": value.wire_value()}
    if isinstance(value, tuple):
        return [_wire(item) for item in value]
    if is_dataclass(value):
        return {
            field.name: _wire(getattr(value, field.name))
            for field in fields(value)
            if not field.name.startswith("_")
        }
    if hasattr(value, "value") and isinstance(value.value, str):
        return value.value
    return value
