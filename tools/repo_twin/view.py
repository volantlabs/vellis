from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from components.rtg.graph.protocol import JsonObject, RtgGraphSnapshot
from tools.repo_twin.model import produced_at_timestamp


@dataclass(frozen=True, slots=True)
class GraphView:
    snapshot: RtgGraphSnapshot

    @classmethod
    def from_snapshot(cls, snapshot: RtgGraphSnapshot) -> GraphView:
        return cls(snapshot)

    def components(self) -> list[JsonObject]:
        rows: list[JsonObject] = []
        component_facts = self._facts_by_anchor("twin.ComponentFact")
        for anchor in self._anchors_by_type("twin.Component"):
            uuid_text = str(anchor["uuid"])
            fact = component_facts.get(uuid_text, {})
            component_id = str(fact.get("component_id", anchor.get("display_name", "")))
            impls = self._targets(uuid_text, "twin.HasImplementationRoot")
            tests = [
                target
                for impl_uuid in impls
                for target in self._targets(impl_uuid, "twin.HasTestSuite")
            ]
            evidence = self._newest_evidence(uuid_text)
            rows.append(
                {
                    "component_id": component_id,
                    "status": fact.get("lifecycle_status", ""),
                    "spec_path": fact.get("spec_path", ""),
                    "implementation_roots": [
                        self._anchor_display(impl_uuid) for impl_uuid in impls
                    ],
                    "test_suites": [self._anchor_display(test_uuid) for test_uuid in tests],
                    "newest_evidence_at": evidence.get("produced_at") if evidence else None,
                }
            )
        return sorted(rows, key=lambda item: str(item["component_id"]))

    def unimplemented(self) -> list[JsonObject]:
        return [
            component for component in self.components() if not component["implementation_roots"]
        ]

    def untested(self) -> list[JsonObject]:
        return [component for component in self.components() if not component["test_suites"]]

    def evidence_for(self, component_id: str) -> list[JsonObject]:
        component_uuid = self._component_uuid(component_id)
        if component_uuid is None:
            return []
        records = []
        data_objects = self._data_by_uuid()
        for data_uuid in self.snapshot.anchor_data_index.get(component_uuid, ()):
            item = data_objects.get(data_uuid)
            if item is not None and item.get("type") == "twin.EvidenceRecord":
                properties = item.get("properties")
                if isinstance(properties, dict):
                    records.append(properties)
        return sorted(records, key=produced_at_timestamp, reverse=True)

    def orphans(self) -> JsonObject:
        incoming_impl_links = {
            str(link["target_uuid"])
            for link in self.snapshot.links
            if link.get("type") == "twin.HasImplementationRoot"
        }
        orphan_roots = [
            self._anchor_display(str(anchor["uuid"]))
            for anchor in self._anchors_by_type("twin.ImplementationRoot")
            if str(anchor["uuid"]) not in incoming_impl_links
        ]
        missing_declared: list[JsonObject] = []
        for component in self.components():
            fact = self._component_fact(str(component["component_id"]))
            raw_declared = fact.get("declared_code_roots")
            raw_actual = component.get("implementation_roots")
            declared = (
                [str(item) for item in raw_declared] if isinstance(raw_declared, list) else []
            )
            actual = {str(item) for item in raw_actual} if isinstance(raw_actual, list) else set()
            for root in declared:
                if root not in actual:
                    missing_declared.append(
                        {"component_id": component["component_id"], "missing_root": root}
                    )
        return cast(
            JsonObject,
            {"orphan_code_roots": orphan_roots, "missing_declared_roots": missing_declared},
        )

    def blast_radius(self, component_id: str) -> JsonObject:
        component_uuid = self._component_uuid(component_id)
        if component_uuid is None:
            return {"component_id": component_id, "found": False}
        dependents = [
            self._component_id(str(link["source_uuid"]))
            for link in self.snapshot.links
            if link.get("type") == "twin.DependsOn" and str(link["target_uuid"]) == component_uuid
        ]
        dependencies = [
            self._component_id(str(link["target_uuid"]))
            for link in self.snapshot.links
            if link.get("type") == "twin.DependsOn" and str(link["source_uuid"]) == component_uuid
        ]
        impls = self._targets(component_uuid, "twin.HasImplementationRoot")
        tests = [
            self._anchor_display(str(link["source_uuid"]))
            for link in self.snapshot.links
            if link.get("type") == "twin.Verifies" and str(link["target_uuid"]) == component_uuid
        ]
        apps = [
            self._anchor_display(str(link["source_uuid"]))
            for link in self.snapshot.links
            if link.get("type") == "twin.ComposedOf" and str(link["target_uuid"]) == component_uuid
        ]
        return cast(
            JsonObject,
            {
                "component_id": component_id,
                "found": True,
                "dependents": sorted(item for item in dependents if item is not None),
                "dependencies": sorted(item for item in dependencies if item is not None),
                "implementation_roots": [self._anchor_display(impl_uuid) for impl_uuid in impls],
                "test_suites": sorted(tests),
                "apps": sorted(apps),
            },
        )

    def _anchors_by_type(self, type_key: str) -> list[JsonObject]:
        return [item for item in self.snapshot.anchors if item.get("type") == type_key]

    def _facts_by_anchor(self, type_key: str) -> dict[str, JsonObject]:
        data_by_uuid = self._data_by_uuid()
        result: dict[str, JsonObject] = {}
        for anchor_uuid, data_uuids in self.snapshot.anchor_data_index.items():
            for data_uuid in data_uuids:
                data = data_by_uuid.get(data_uuid)
                if data is None or data.get("type") != type_key:
                    continue
                properties = data.get("properties")
                if isinstance(properties, dict):
                    result[anchor_uuid] = properties
        return result

    def _data_by_uuid(self) -> dict[str, JsonObject]:
        return {str(item["uuid"]): item for item in self.snapshot.data_objects}

    def _anchor_by_uuid(self) -> dict[str, JsonObject]:
        return {str(item["uuid"]): item for item in self.snapshot.anchors}

    def _targets(self, source_uuid: str, type_key: str) -> list[str]:
        return [
            str(link["target_uuid"])
            for link in self.snapshot.links
            if link.get("type") == type_key and str(link["source_uuid"]) == source_uuid
        ]

    def _anchor_display(self, anchor_uuid: str) -> str:
        anchor = self._anchor_by_uuid().get(anchor_uuid, {})
        return str(anchor.get("display_name", anchor_uuid))

    def _component_uuid(self, component_id: str) -> str | None:
        for anchor_uuid, fact in self._facts_by_anchor("twin.ComponentFact").items():
            if fact.get("component_id") == component_id:
                return anchor_uuid
        return None

    def _component_id(self, anchor_uuid: str) -> str | None:
        fact = self._facts_by_anchor("twin.ComponentFact").get(anchor_uuid)
        if fact is None:
            return None
        value = fact.get("component_id")
        return str(value) if isinstance(value, str) else None

    def _component_fact(self, component_id: str) -> JsonObject:
        component_uuid = self._component_uuid(component_id)
        if component_uuid is None:
            return {}
        return self._facts_by_anchor("twin.ComponentFact").get(component_uuid, {})

    def _newest_evidence(self, component_uuid: str) -> JsonObject:
        records = []
        data_by_uuid = self._data_by_uuid()
        for data_uuid in self.snapshot.anchor_data_index.get(component_uuid, ()):
            data = data_by_uuid.get(data_uuid)
            if data is None or data.get("type") != "twin.EvidenceRecord":
                continue
            properties = data.get("properties")
            if isinstance(properties, dict):
                records.append(properties)
        if not records:
            return {}
        return max(records, key=produced_at_timestamp)
