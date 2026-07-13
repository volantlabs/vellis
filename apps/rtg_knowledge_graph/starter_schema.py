from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from apps.rtg_knowledge_graph.mcp_codec import decode_change_batch
from components.rtg.controller import InProcessRtgController

JsonObject = dict[str, Any]


class VellisStartupFailed(RuntimeError):
    """Durable state or the modeled starter schema could not be prepared safely."""


@dataclass(frozen=True, slots=True)
class StarterSchemaStatus:
    ontology_id: str
    version: str
    status: str
    anchor_type_keys: tuple[str, ...]
    link_type_keys: tuple[str, ...]
    recovery: str

    def to_json_value(self) -> JsonObject:
        return {
            "ontology_id": self.ontology_id,
            "version": self.version,
            "status": self.status,
            "anchor_type_keys": list(self.anchor_type_keys),
            "link_type_keys": list(self.link_type_keys),
            "recovery": self.recovery,
        }


def load_starter_schema_bundle() -> JsonObject:
    resource = files("apps.rtg_knowledge_graph.resources").joinpath(
        "everyday_life_schema.json"
    )
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VellisStartupFailed("generated Everyday Life ontology bundle is not an object")
    if value.get("graph_objects") != []:
        raise VellisStartupFailed("starter ontology bundle must not contain graph objects")
    bundle = cast(JsonObject, value)
    _validate_bundle_integrity(bundle)
    return bundle


def prepare_controller(
    controller: InProcessRtgController,
    *,
    install_starter_schema: bool = True,
    automatic_recovery: bool = True,
) -> StarterSchemaStatus:
    bundle = load_starter_schema_bundle()
    recovery = "not_needed"
    state = controller.get_system_state()
    if state.state_classification == "needs_replay":
        if not automatic_recovery:
            return starter_schema_status(
                controller,
                bundle=bundle,
                recovery="manual_recovery_required",
            )
        try:
            controller.replay_ledger()
            report = controller.validate_graph()
            if not report.accepted:
                raise VellisStartupFailed(
                    "replayed durable graph state did not pass validation"
                )
        except Exception as error:  # noqa: BLE001 - startup must fail closed
            raise VellisStartupFailed(
                "Vellis could not reconstruct and validate durable graph state from the "
                "controller ledger; no replacement empty MCP server was started. Run "
                "`uv run vellis doctor`. "
                f"Cause: {error}"
            ) from error
        recovery = "ledger_replayed"

    status = starter_schema_status(controller, bundle=bundle, recovery=recovery)
    if status.status == "custom" and _has_starter_schema_collision(controller, bundle):
        raise VellisStartupFailed(
            "existing schema collides with starter ontology identities or type keys; "
            "the existing graph was preserved without changes"
        )
    if install_starter_schema and status.status == "empty":
        snapshot = controller.export_system_snapshot()
        has_staged_or_graph_state = bool(
            snapshot.graph.anchors
            or snapshot.graph.data_objects
            or snapshot.graph.links
            or snapshot.constraints.constraints
            or snapshot.migration.migrations
            or any(
                _definition_is_non_live(definition)
                for definition in snapshot.schema.definitions
            )
        )
        if has_staged_or_graph_state:
            return starter_schema_status(controller, bundle=bundle, recovery=recovery)
        try:
            changes = decode_change_batch(bundle["knowledge_changes"])
            staged = controller.stage_knowledge_changes(changes, "strict")
            if staged.status != "applied":
                raise VellisStartupFailed(
                    f"starter schema staging returned unexpected status {staged.status}"
                )
            controller.apply_migration_cutover(str(bundle["bootstrap_migration_id"]))
            report = controller.validate_graph()
            if not report.accepted:
                raise VellisStartupFailed("starter schema validation was not accepted")
        except Exception as error:  # noqa: BLE001 - convert all setup failures consistently
            try:
                controller.abandon_migration(
                    str(bundle["bootstrap_migration_id"]),
                    "starter ontology installation did not complete",
                )
            except Exception:  # noqa: BLE001 - fall back to coordinated restoration
                try:
                    controller.restore_from_snapshot(snapshot)
                except Exception as cleanup_error:  # noqa: BLE001 - report unsafe cleanup
                    raise VellisStartupFailed(
                        "Everyday Life ontology installation failed and pre-installation state "
                        f"could not be restored: {cleanup_error}"
                    ) from error
            if not _same_domain_state(controller.export_system_snapshot(), snapshot):
                try:
                    controller.restore_from_snapshot(snapshot)
                except Exception as cleanup_error:  # noqa: BLE001 - report unsafe cleanup
                    raise VellisStartupFailed(
                        "Everyday Life ontology installation failed and left unexpected state: "
                        f"{cleanup_error}"
                    ) from error
            if isinstance(error, VellisStartupFailed):
                raise
            raise VellisStartupFailed(
                f"Everyday Life ontology installation failed: {error}"
            ) from error
        status = starter_schema_status(controller, bundle=bundle, recovery=recovery)
        if status.status != "installed":
            raise VellisStartupFailed("Everyday Life ontology installation did not become live")
    return status


def starter_schema_status(
    controller: InProcessRtgController,
    *,
    bundle: JsonObject | None = None,
    recovery: str = "not_checked",
) -> StarterSchemaStatus:
    value = bundle or load_starter_schema_bundle()
    writes = value["knowledge_changes"]["schema_changes"]["definition_writes"]
    expected = {
        (str(item["definition"]["uuid"]), str(item["definition"]["type_key"]))
        for item in writes
    }
    anchor_types = tuple(
        sorted(
            str(item["definition"]["type_key"])
            for item in writes
            if item["definition"]["kind"] == "anchor"
        )
    )
    link_types = tuple(
        sorted(
            str(item["definition"]["type_key"])
            for item in writes
            if item["definition"]["kind"] == "link"
        )
    )
    snapshot = controller.export_system_snapshot()
    live = {
        (str(item.get("uuid")), str(item.get("type_key")))
        for item in snapshot.schema.definitions
        if _definition_is_live(item)
    }
    if expected <= live:
        status = "installed"
    elif (
        snapshot.schema.definitions
        or snapshot.constraints.constraints
        or snapshot.migration.migrations
        or snapshot.graph.anchors
        or snapshot.graph.data_objects
        or snapshot.graph.links
    ):
        status = "custom"
    else:
        status = "empty"
    return StarterSchemaStatus(
        ontology_id=str(value["ontology_id"]),
        version=str(value["version"]),
        status=status,
        anchor_type_keys=anchor_types,
        link_type_keys=link_types,
        recovery=recovery,
    )


def _has_starter_schema_collision(
    controller: InProcessRtgController,
    bundle: JsonObject,
) -> bool:
    writes = bundle["knowledge_changes"]["schema_changes"]["definition_writes"]
    expected_ids = {str(item["definition"]["uuid"]) for item in writes}
    expected_keys = {str(item["definition"]["type_key"]) for item in writes}
    snapshot = controller.export_system_snapshot()
    for definition in snapshot.schema.definitions:
        if not isinstance(definition, dict):
            continue
        if str(definition.get("uuid")) in expected_ids:
            return True
        if str(definition.get("type_key")) in expected_keys:
            return True
    return False


def _definition_is_live(definition: object) -> bool:
    if not isinstance(definition, dict):
        return False
    system = definition.get("system")
    return isinstance(system, dict) and system.get("live", True) is True


def _definition_is_non_live(definition: object) -> bool:
    if not isinstance(definition, dict):
        return False
    system = definition.get("system")
    return isinstance(system, dict) and system.get("live", True) is False


def _validate_bundle_integrity(bundle: JsonObject) -> None:
    ontology_id = bundle.get("ontology_id")
    migration_key = bundle.get("bootstrap_migration_key")
    if not isinstance(ontology_id, str) or not ontology_id:
        raise VellisStartupFailed("starter ontology bundle has no ontology identity")
    if not isinstance(migration_key, str) or not migration_key:
        raise VellisStartupFailed("starter ontology bundle has no migration key")
    try:
        changes = cast(JsonObject, bundle["knowledge_changes"])
        schema_changes = cast(JsonObject, changes["schema_changes"])
        writes = cast(list[JsonObject], schema_changes["definition_writes"])
    except (KeyError, TypeError) as error:
        raise VellisStartupFailed("starter ontology bundle has invalid schema changes") from error
    if len(writes) != 33:
        raise VellisStartupFailed("starter ontology bundle must contain exactly 33 definitions")
    counts = {"anchor": 0, "data_object": 0, "link": 0}
    identities: set[str] = set()
    type_keys: set[str] = set()
    for write in writes:
        definition = write.get("definition")
        if not isinstance(definition, dict):
            raise VellisStartupFailed("starter ontology definition is not an object")
        kind = definition.get("kind")
        type_key = definition.get("type_key")
        identity = definition.get("uuid")
        if kind not in counts or not isinstance(type_key, str) or not isinstance(identity, str):
            raise VellisStartupFailed("starter ontology definition identity is invalid")
        if identity != str(uuid5(NAMESPACE_URL, f"{ontology_id}:schema:{type_key}")):
            raise VellisStartupFailed("starter ontology definition UUID is not deterministic")
        if identity in identities or type_key in type_keys:
            raise VellisStartupFailed("starter ontology definitions contain duplicate identities")
        if definition.get("system") != {"live": False}:
            raise VellisStartupFailed("starter ontology definitions must be staged non-live")
        UUID(identity)
        identities.add(identity)
        type_keys.add(type_key)
        counts[kind] += 1
    if counts != {"anchor": 12, "data_object": 12, "link": 9}:
        raise VellisStartupFailed("starter ontology definition kinds are incomplete")
    expected_migration = str(
        uuid5(NAMESPACE_URL, f"{ontology_id}:migration-record:{migration_key}")
    )
    if bundle.get("bootstrap_migration_id") != expected_migration:
        raise VellisStartupFailed("starter ontology migration UUID is not deterministic")


def _same_domain_state(left: object, right: object) -> bool:
    return all(
        getattr(left, feature, None) == getattr(right, feature, None)
        for feature in ("graph", "schema", "constraints", "migration")
    )
