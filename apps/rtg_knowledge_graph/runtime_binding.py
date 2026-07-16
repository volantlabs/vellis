from __future__ import annotations

from collections.abc import Awaitable, Callable

from apps.rtg_knowledge_graph.application_binding import load_application_binding
from apps.rtg_knowledge_graph.mcp_toolset import (
    TOOL_NAMES,
    VellisRequestInvalid,
)
from components.runtime.component_adapter import (
    ActionBinding,
    ComponentAdapter,
    ComponentExecution,
    encode_json,
)
from components.runtime.message_runtime import (
    JsonObject,
    RuntimeError,
)

FACADE_CONTRACT_ID = "application.vellis.facade"
FACADE_BINDING_ID = "binding.python.vellis.facade.v2"
FACADE_REQUEST_CODEC = f"codec.python.{FACADE_CONTRACT_ID}.request.json"


_FACADE_DESCRIPTORS = load_application_binding(FACADE_CONTRACT_ID)
if set(_FACADE_DESCRIPTORS) != set(TOOL_NAMES):
    raise RuntimeError("generated facade descriptor inventory differs from tool inventory")
FACADE_ACTIONS = {name: descriptor.action_ref() for name, descriptor in _FACADE_DESCRIPTORS.items()}

type FacadeHandler = Callable[[JsonObject, ComponentExecution], Awaitable[None]]


def create_vellis_facade_adapter(
    handlers: dict[str, FacadeHandler],
) -> ComponentAdapter:
    """Create the ordinary adapter used by the Vellis facade occurrence."""
    missing = set(TOOL_NAMES) - set(handlers)
    extra = set(handlers) - set(TOOL_NAMES)
    if missing or extra:
        raise ValueError(
            f"facade handler inventory mismatch; missing={sorted(missing)}, extra={sorted(extra)}"
        )
    bindings: list[ActionBinding] = []
    for name in TOOL_NAMES:

        async def invoke(
            _args: tuple[object, ...],
            kwargs: dict[str, object],
            execution: ComponentExecution,
            *,
            tool_name: str = name,
        ) -> None:
            await handlers[tool_name](kwargs, execution)

        bindings.append(
            ActionBinding(
                descriptor=_FACADE_DESCRIPTORS[name],
                decode_request=lambda payload: ((), dict(payload)),
                encode_result=encode_json,
                handler=invoke,
                failure_types=(VellisRequestInvalid, RuntimeError),
            )
        )
    return ComponentAdapter(tuple(bindings))
__all__ = [
    "FACADE_ACTIONS",
    "FACADE_BINDING_ID",
    "FACADE_CONTRACT_ID",
    "FACADE_REQUEST_CODEC",
    "FacadeHandler",
    "create_vellis_facade_adapter",
]
