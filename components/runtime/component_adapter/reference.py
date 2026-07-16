from __future__ import annotations

import asyncio
from dataclasses import replace
from tempfile import TemporaryDirectory
from typing import cast

from components.runtime.component_adapter import ActionBinding, ComponentAdapter, ComponentEndpoint
from components.runtime.message_runtime import SqliteMessageRuntime
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeReplayMode,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)


async def _run() -> int:
    descriptor = RuntimeActionBindingDescriptor(
        "component.reference.accumulator",
        "component.reference.accumulator.add",
        "binding.reference.accumulator.v2",
        1,
        1,
        "codec.reference.accumulator.request.json",
        "codec.reference.accumulator.result.json",
        "codec.reference.accumulator.failure.json",
        RuntimeActionIdempotency.NON_IDEMPOTENT,
        RuntimeReplayMode.NO_STATE_EFFECT,
    )
    adapter = ComponentAdapter(
        (
            ActionBinding(
                descriptor,
                lambda payload: ((cast(int, payload["value"]),), {}),
                lambda result: cast(int, result),
                invoke=lambda value: value + 1,
            ),
        )
    )
    with TemporaryDirectory() as directory:
        runtime = SqliteMessageRuntime(
            f"{directory}/runtime.sqlite", runtime_key="adapter.reference"
        )
        declaration = ComponentOccurrenceDeclaration(
            "reference.accumulator.primary",
            adapter.describe().component_contract_id,
            adapter.describe().binding_id,
            adapter.describe().binding_version,
        )
        manifest = RuntimeTopologyManifest("adapter.reference", 4, (declaration,), (), "")
        manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
        await runtime.prepare_static_topology(manifest)
        registration = await runtime.register_occurrence(declaration)
        await runtime.attach_participant(registration, adapter, adapter.describe().actions)
        await runtime.confirm_static_topology(manifest)
        endpoint = ComponentEndpoint(
            runtime,
            adapter,
            source=runtime.address_for(declaration.instance_key),
        )
        outcome = await endpoint.request(
            descriptor.action_ref(),
            {"value": 1},
            target=runtime.address_for(declaration.instance_key),
        )
        await runtime.aclose()
        payload = outcome.response.payload.value
        if not isinstance(payload, dict):
            raise RuntimeError("reference adapter returned a non-object payload")
        return cast(int, payload["result"])


def run_reference() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    print(run_reference())
