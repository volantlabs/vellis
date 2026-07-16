from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import Any, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from apps.rtg_knowledge_graph.application_binding import load_application_binding
from apps.rtg_knowledge_graph.mcp_codec import decode_change_batch
from components.rtg.change_validation import RtgValidationReport
from components.rtg.controller import (
    RTG_CONTROLLER_ACTIONS,
    RtgControllerSystemState,
)
from components.rtg.migration import RtgMigrationRecord
from components.rtg.schema import (
    RTG_SCHEMA_ACTIONS,
    RtgSchemaDefinition,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentExecution,
    RuntimeRemoteFault,
    decode_typed,
    encode_json,
)
from components.runtime.message_runtime import JsonObject as RuntimeJsonObject
from components.runtime.message_runtime import RuntimeTraceDisposition

JsonObject = dict[str, Any]
_INSTALLER_CONTRACT = "application.vellis.starter_ontology_installer"
_INSTALLER_DESCRIPTORS = load_application_binding(_INSTALLER_CONTRACT)
STARTER_INSTALLER_ACTIONS = {
    name: descriptor.action_ref() for name, descriptor in _INSTALLER_DESCRIPTORS.items()
}


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


@dataclass(frozen=True, slots=True)
class EverydayLifeOntologyIdentity:
    ontology_id: str
    version: str
    bootstrap_migration_id: str


@dataclass(frozen=True, slots=True)
class EverydayLifeInstallationResult:
    status: str
    ontology: EverydayLifeOntologyIdentity
    schema_definition_count: int


class EverydayLifeOntologyInstaller:
    """Ordinary component that coordinates starter-ontology installation by messages."""

    def __init__(
        self,
        *,
        install_starter_schema: bool = True,
        automatic_recovery: bool = True,
        controller_key: str = "vellis.controller.primary",
        schema_key: str = "vellis.schema.primary",
    ) -> None:
        self._install = install_starter_schema
        self._automatic_recovery = automatic_recovery
        self._controller_key = controller_key
        self._schema_key = schema_key
        self._last_recovery = "not_checked"

    def create_adapter(self) -> ComponentAdapter:
        async def install(
            _args: tuple[object, ...],
            kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            try:
                recovery = str(kwargs.get("recovery", "not_needed"))
                self._last_recovery = recovery
                bundle = load_starter_schema_bundle()
                before, _ = await self._runtime_status(
                    bundle, recovery, execution, phase="install-before"
                )
                status = await self._prepare(recovery, execution)
            except RuntimeRemoteFault as error:
                await execution.forward_fault(
                    error.payload,
                    disposition=RuntimeTraceDisposition.ABORTED,
                )
                return
            if before.status == "installed":
                installation_status = "alreadyInstalled"
            elif status.status == "installed":
                installation_status = "installed"
            else:
                installation_status = "customPreserved"
            writes = bundle["knowledge_changes"]["schema_changes"]["definition_writes"]
            await execution.complete(
                EverydayLifeInstallationResult(
                    status=installation_status,
                    ontology=EverydayLifeOntologyIdentity(
                        ontology_id=str(bundle["ontology_id"]),
                        version=str(bundle["version"]),
                        bootstrap_migration_id=str(bundle["bootstrap_migration_id"]),
                    ),
                    schema_definition_count=(
                        len(writes) if status.status == "installed" else 0
                    ),
                )
            )

        async def get_status(
            _args: tuple[object, ...],
            kwargs: dict[str, object],
            execution: ComponentExecution,
        ) -> None:
            bundle = load_starter_schema_bundle()
            recovery = str(kwargs.get("recovery", "not_checked"))
            if recovery == "not_checked":
                recovery = self._last_recovery
            status, _ = await self._runtime_status(
                bundle,
                recovery,
                execution,
                phase="status",
            )
            await execution.complete(status)

        def binding(
            name: str,
            handler: object,
        ) -> ActionBinding:
            return ActionBinding(
                descriptor=_INSTALLER_DESCRIPTORS[name],
                decode_request=lambda payload: ((), {"recovery": payload.get("recovery")}),
                encode_result=encode_json,
                handler=cast(Any, handler),
                failure_types=(VellisStartupFailed,),
            )

        return ComponentAdapter(
            (
                binding(
                    "install",
                    install,
                ),
                binding(
                    "get_status",
                    get_status,
                ),
            )
        )

    async def _prepare(
        self,
        recovery: str,
        execution: ComponentExecution,
    ) -> StarterSchemaStatus:
        bundle = load_starter_schema_bundle()
        status, interrupted = await self._runtime_status(
            bundle, recovery, execution, phase="before"
        )
        if not self._automatic_recovery and recovery == "manual_recovery_required":
            return status

        if interrupted:
            if self._install:
                await self._call(
                    "apply_migration_cutover",
                    {
                        "migration_id": str(bundle["bootstrap_migration_id"]),
                        "cutover_options": None,
                    },
                    execution,
                    "recover-cutover",
                )
                recovery = "starter_install_completed"
            else:
                await self._call(
                    "abandon_migration",
                    {
                        "migration_id": str(bundle["bootstrap_migration_id"]),
                        "reason": "starter schema installation disabled after interrupted staging",
                    },
                    execution,
                    "recover-abandon",
                )
                recovery = "starter_install_abandoned"
            status, _ = await self._runtime_status(
                bundle, recovery, execution, phase="after-recovery"
            )

        if not self._install or status.status != "empty":
            return status
        await self._call(
            "stage_knowledge_changes",
            {
                "knowledge_changes": decode_change_batch(bundle["knowledge_changes"]),
                "validation_mode": "strict",
            },
            execution,
            "stage-starter",
        )
        await self._call(
            "apply_migration_cutover",
            {"migration_id": str(bundle["bootstrap_migration_id"]), "cutover_options": None},
            execution,
            "cutover-starter",
        )
        validation = decode_typed(
            await self._call(
                "validate_graph",
                {"migration_ids": None, "validation_options": None},
                execution,
                "validate-starter",
            ),
            RtgValidationReport,
        )
        if not validation.accepted:
            raise VellisStartupFailed("starter schema validation was not accepted")
        status, _ = await self._runtime_status(
            bundle, recovery, execution, phase="after-install"
        )
        if status.status != "installed":
            raise VellisStartupFailed(
                f"Everyday Life ontology installation did not become live: {status.status}"
            )
        return status

    async def _runtime_status(
        self,
        bundle: JsonObject,
        recovery: str,
        execution: ComponentExecution,
        *,
        phase: str,
    ) -> tuple[StarterSchemaStatus, bool]:
        state = decode_typed(
            await self._call("get_system_state", {}, execution, f"starter-state-{phase}"),
            RtgControllerSystemState,
        )
        writes = bundle["knowledge_changes"]["schema_changes"]["definition_writes"]
        expected = {str(item["definition"]["uuid"]): item["definition"] for item in writes}
        installed: dict[str, JsonObject] = {}
        for index, definition_id in enumerate(expected):
            try:
                value = await execution.call(
                    f"starter-definition-{phase}-{index}",
                    RTG_SCHEMA_ACTIONS["get_definition"],
                    {"definition_uuid": definition_id},
                    target=execution.address_for(self._schema_key),
                )
            except RuntimeRemoteFault as error:
                if error.payload.get("type") == "RtgSchemaDefinitionNotFound":
                    continue
                raise
            definition = decode_typed(value, RtgSchemaDefinition)
            installed[definition_id] = cast(RuntimeJsonObject, encode_json(definition))

        fully_installed = all(
            definition_id in installed
            and _definition_is_live(installed[definition_id])
            and _definitions_are_compatible(installed[definition_id], expected_definition)
            for definition_id, expected_definition in expected.items()
        )
        candidate_counts = state.non_live_candidate_counts
        has_state = bool(
            state.live_schema_counts.total
            or any(item.count for item in state.live_object_counts.counts)
            or candidate_counts.schema
            or candidate_counts.constraints
            or candidate_counts.graph
            or state.migration_counts_by_status.total
        )
        status_name = "installed" if fully_installed else ("custom" if has_state else "empty")
        anchor_types, link_types = _bundle_type_keys(bundle)
        status = StarterSchemaStatus(
            ontology_id=str(bundle["ontology_id"]),
            version=str(bundle["version"]),
            status=status_name,
            anchor_type_keys=anchor_types,
            link_type_keys=link_types,
            recovery=recovery,
        )

        staged_shape = (
            not fully_installed
            and state.live_schema_counts.total == 0
            and not any(item.count for item in state.live_object_counts.counts)
            and candidate_counts.schema == len(expected)
            and candidate_counts.constraints == 0
            and candidate_counts.graph == 0
            and state.migration_counts_by_status.total == 1
            and state.migration_counts_by_status.ready == 1
            and set(installed) == set(expected)
            and all(
                _definition_is_non_live(definition)
                and _definitions_are_compatible(definition, expected[definition_id])
                for definition_id, definition in installed.items()
            )
        )
        if not staged_shape:
            return status, False
        try:
            migration = decode_typed(
                await self._call(
                    "get_migration",
                    {"migration_id": str(bundle["bootstrap_migration_id"])},
                    execution,
                    f"starter-migration-{phase}",
                ),
                RtgMigrationRecord,
            )
        except RuntimeRemoteFault:
            return status, False
        return status, migration.status == "ready"

    async def _call(
        self,
        action: str,
        arguments: dict[str, object],
        execution: ComponentExecution,
        step: str,
    ) -> RuntimeJsonObject:
        value = await execution.call(
            step,
            RTG_CONTROLLER_ACTIONS[action],
            arguments,
            target=execution.address_for(self._controller_key),
        )
        if not isinstance(value, dict):
            raise VellisStartupFailed(f"controller {action} result was not an object")
        return cast(RuntimeJsonObject, value)


def load_starter_schema_bundle() -> JsonObject:
    resource = files("apps.rtg_knowledge_graph.resources").joinpath("everyday_life_schema.json")
    value = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise VellisStartupFailed("generated Everyday Life ontology bundle is not an object")
    if value.get("graph_objects") != []:
        raise VellisStartupFailed("starter ontology bundle must not contain graph objects")
    bundle = cast(JsonObject, value)
    _validate_bundle_integrity(bundle)
    return bundle


def unreconstructed_starter_schema_status() -> StarterSchemaStatus:
    """Describe the configured ontology without reading unreconstructed component state."""
    bundle = load_starter_schema_bundle()
    anchor_types, link_types = _bundle_type_keys(bundle)
    return StarterSchemaStatus(
        ontology_id=str(bundle["ontology_id"]),
        version=str(bundle["version"]),
        status="empty",
        anchor_type_keys=anchor_types,
        link_type_keys=link_types,
        recovery="manual_recovery_required",
    )


def _bundle_type_keys(bundle: JsonObject) -> tuple[tuple[str, ...], tuple[str, ...]]:
    writes = bundle["knowledge_changes"]["schema_changes"]["definition_writes"]
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
    return anchor_types, link_types


def _definitions_are_compatible(
    installed: JsonObject,
    expected: JsonObject,
) -> bool:
    if not all(
        installed.get(key) == expected.get(key)
        for key in ("uuid", "kind", "type_key", "description")
    ):
        return False
    expected_payload = expected.get("payload")
    if not isinstance(expected_payload, dict):
        return installed.get("payload") == expected_payload
    normalized_payload = dict(expected_payload)
    if expected.get("kind") == "anchor":
        normalized_payload.setdefault("required_data_types", [])
        normalized_payload.setdefault("optional_data_types", [])
    installed_payload = installed.get("payload")
    if expected.get("kind") == "link" and isinstance(installed_payload, dict):
        for key in ("allowed_source_types", "allowed_target_types"):
            normalized_payload[key] = sorted(cast(list[str], normalized_payload.get(key, [])))
        installed_payload = {
            **installed_payload,
            "allowed_source_types": sorted(
                cast(list[str], installed_payload.get("allowed_source_types", []))
            ),
            "allowed_target_types": sorted(
                cast(list[str], installed_payload.get("allowed_target_types", []))
            ),
        }
    return _without_schema_codec_defaults(installed_payload) == _without_schema_codec_defaults(
        normalized_payload
    )


def _without_schema_codec_defaults(value: object) -> object:
    if isinstance(value, list):
        return [_without_schema_codec_defaults(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {
        key: _without_schema_codec_defaults(item)
        for key, item in value.items()
    }
    defaults: dict[str, object] = {
        "properties": {},
        "items": None,
        "allowed_values": [],
        "format": None,
        "minimum": None,
        "maximum": None,
        "pattern": None,
    }
    return {
        key: item
        for key, item in normalized.items()
        if key not in defaults or item != defaults[key]
    }


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
