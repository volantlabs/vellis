"""Minimal RFC 6901 pointer construction shared by domain and adapters."""

from __future__ import annotations


def append_pointer(base: str, *segments: object) -> str:
    return base + "".join(f"/{pointer_segment(segment)}" for segment in segments)


def pointer_segment(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")
