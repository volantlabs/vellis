from __future__ import annotations

from tempfile import TemporaryDirectory
from typing import cast

from components.runtime.component_adapter import (
    ActionBinding,
    ExplicitComponentAdapter,
    RuntimeActionBindingDescriptor,
    RuntimeActionIdempotency,
    RuntimeClient,
)
from components.runtime.component_adapter.implementation import encode_json
from components.runtime.message_runtime import RuntimeReplayMode, SqliteMessageRuntime


def run_reference() -> int:
    """Dispatch one explicitly registered action without exposing private methods."""
    descriptor = RuntimeActionBindingDescriptor(
        component_contract_id="component.reference.accumulator",
        action_id="component.reference.accumulator.add",
        binding_id="binding.reference.accumulator.v1",
        binding_version=1,
        schema_version=1,
        request_codec_id="codec.reference.accumulator.request.json",
        result_codec_id="codec.reference.accumulator.result.json",
        failure_codec_id="codec.reference.accumulator.failure.json",
        idempotency=RuntimeActionIdempotency.NON_IDEMPOTENT,
        replay_mode=RuntimeReplayMode.NO_STATE_EFFECT,
    )
    adapter = ExplicitComponentAdapter(
        (
            ActionBinding(
                descriptor=descriptor,
                invoke=lambda value: value + 1,
                decode_request=lambda payload: ((cast(int, payload["value"]),), {}),
                encode_result=encode_json,
            ),
        )
    )
    with TemporaryDirectory() as directory:
        with SqliteMessageRuntime.open(
            f"{directory}/runtime.sqlite", runtime_key="adapter.reference"
        ) as runtime:
            registration = runtime.register_adapter(
                instance_key="reference.accumulator.primary",
                component_contract_id="component.reference.accumulator",
                adapter=adapter,
            )
            address = runtime.address_for(registration.instance_key)
            client = RuntimeClient(
                runtime,
                source=address,
                target=address,
                component_contract_id="component.reference.accumulator",
                request_codec_id="codec.reference.accumulator.request.json",
            )
            outcome = client.request_sync("component.reference.accumulator.add", {"value": 1})
            payload = outcome.response.payload.value
            if not isinstance(payload, dict):
                raise RuntimeError("reference adapter returned a non-object payload")
            return cast(int, payload["result"])


if __name__ == "__main__":
    print(run_reference())
