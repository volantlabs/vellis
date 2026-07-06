from __future__ import annotations

from dataclasses import dataclass

from components.rtg.graph.protocol import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class RtgDiagnostic:
    """Generic, machine-readable corrective guidance for RTG consumers."""

    code: str
    category: str
    problem: str
    remedy: str
    path: str | None = None
    accepted_fields: tuple[str, ...] = ()
    minimal_example: JsonObject | None = None
    guide_topics: tuple[str, ...] = ()
    safe_to_retry: bool = True
    mutation_state: str = "not_mutated"


def rtg_diagnostic(
    *,
    code: str,
    category: str,
    problem: str,
    remedy: str,
    path: str | None = None,
    accepted_fields: tuple[str, ...] = (),
    minimal_example: JsonObject | None = None,
    guide_topics: tuple[str, ...] = (),
    safe_to_retry: bool = True,
    mutation_state: str = "not_mutated",
) -> JsonObject:
    payload: JsonObject = {
        "code": code,
        "category": category,
        "problem": problem,
        "remedy": remedy,
        "safe_to_retry": safe_to_retry,
        "mutation_state": mutation_state,
    }
    if path is not None:
        payload["path"] = path
    if accepted_fields:
        payload["accepted_fields"] = list(accepted_fields)
    if minimal_example is not None:
        payload["minimal_example"] = minimal_example
    if guide_topics:
        payload["guide_topics"] = list(guide_topics)
    return payload


def diagnostic_as_json(value: object) -> JsonObject | None:
    if isinstance(value, RtgDiagnostic):
        return rtg_diagnostic(
            code=value.code,
            category=value.category,
            problem=value.problem,
            remedy=value.remedy,
            path=value.path,
            accepted_fields=value.accepted_fields,
            minimal_example=value.minimal_example,
            guide_topics=value.guide_topics,
            safe_to_retry=value.safe_to_retry,
            mutation_state=value.mutation_state,
        )
    if isinstance(value, dict):
        normalized: JsonObject = {}
        for key, item in value.items():
            is_json, json_value = _normalize_json_value(item)
            if is_json:
                normalized[str(key)] = json_value
        return normalized
    return None


def _normalize_json_value(value: object) -> tuple[bool, JsonValue]:
    if value is None or isinstance(value, str | int | float | bool):
        return True, value
    if isinstance(value, tuple | list):
        normalized_items: list[JsonValue] = []
        for item in value:
            is_json, json_value = _normalize_json_value(item)
            if not is_json:
                return False, None
            normalized_items.append(json_value)
        return True, normalized_items
    if isinstance(value, dict):
        normalized_object: JsonObject = {}
        for key, item in value.items():
            if not isinstance(key, str):
                return False, None
            is_json, json_value = _normalize_json_value(item)
            if not is_json:
                return False, None
            normalized_object[key] = json_value
        return True, normalized_object
    return False, None


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, str | int | float | bool):
        return True
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False
