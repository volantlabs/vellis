from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from uuid import uuid4

from components.runtime.message_runtime import SqliteMessageRuntime
from components.runtime.messaging import (
    ComponentOccurrenceDeclaration,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeMessageEnvelope,
    RuntimeMessageKind,
    RuntimeParticipantContext,
    RuntimePayload,
    RuntimeReplayMode,
    RuntimeTopologyManifest,
    topology_manifest_hash,
)


class _EchoParticipant:
    async def deliver(
        self,
        envelope: RuntimeMessageEnvelope,
        context: RuntimeParticipantContext,
    ) -> None:
        if envelope.kind is RuntimeMessageKind.REQUEST:
            await context.complete(
                envelope.message_id,
                RuntimePayload(
                    "codec.reference.echo.result.json",
                    1,
                    {"result": envelope.payload.value},
                ),
            )
            return
        await context.ack(envelope.message_id)

    async def apply_replay_effect(self, _effect: dict[str, object]) -> None:
        return

    async def replay_state_status(self) -> object:
        return object()

    async def reset_replay_state(self) -> None:
        return

    async def import_replay_checkpoint(self, _reference: str) -> int:
        return 0

    async def replay_state_digest(self) -> str:
        return "0" * 64

    async def verify_replay_state(self) -> tuple[str, ...]:
        return ()


async def _run() -> int:
    descriptor = RuntimeActionBindingDescriptor(
        "component.reference.echo",
        "component.reference.echo.echo",
        "binding.reference.echo.v1",
        1,
        1,
        "codec.reference.echo.request.json",
        "codec.reference.echo.result.json",
        "codec.reference.echo.failure.json",
        RuntimeActionIdempotency.IDEMPOTENT,
        RuntimeReplayMode.NO_STATE_EFFECT,
    )
    declaration = ComponentOccurrenceDeclaration(
        "reference.echo.primary",
        descriptor.component_contract_id,
        descriptor.binding_id,
        descriptor.binding_version,
    )
    manifest = RuntimeTopologyManifest("runtime.reference", 4, (declaration,), (), "")
    manifest = replace(manifest, manifest_hash=topology_manifest_hash(manifest))
    with TemporaryDirectory() as directory:
        runtime = SqliteMessageRuntime(
            f"{directory}/runtime.sqlite", runtime_key=manifest.runtime_key
        )
        await runtime.prepare_static_topology(manifest)
        registration = await runtime.register_occurrence(declaration)
        await runtime.attach_participant(registration, _EchoParticipant(), (descriptor,))
        await runtime.confirm_static_topology(manifest)
        address = runtime.address_for(declaration.instance_key)
        message_id = uuid4()
        trace_id = uuid4()
        await runtime.send(
            RuntimeMessageEnvelope(
                message_id=message_id,
                kind=RuntimeMessageKind.REQUEST,
                source=address,
                target=address,
                component_contract_id=descriptor.component_contract_id,
                action_id=descriptor.action_id,
                schema_version=descriptor.schema_version,
                trace_id=trace_id,
                created_at=datetime.now(UTC).isoformat(),
                payload=RuntimePayload(
                    descriptor.request_codec_id,
                    descriptor.request_codec_version,
                    {"value": "hello"},
                ),
            )
        )
        for _ in range(100):
            trace = await runtime.get_trace(trace_id)
            if trace.disposition is not None:
                break
            await asyncio.sleep(0.01)
        position = await runtime.current_position()
        await runtime.aclose()
        return position


def run_reference() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    print(run_reference())
