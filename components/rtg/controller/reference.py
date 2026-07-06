from __future__ import annotations

from components.rtg.controller.implementation import InProcessRtgController
from components.rtg.controller.protocol import RtgController


def create_reference_component(
    graph: object,
    schema: object,
    constraints: object,
    migration: object,
    change_validator: object,
    query_engine: object,
    json_storage: object,
    sql_storage: object,
) -> RtgController:
    return InProcessRtgController.open(
        graph,
        schema,
        constraints,
        migration,
        change_validator,
        query_engine,
        json_storage,
        sql_storage,
    )
