"""Identifiers declared once: event names, schedule names, screen states, tool names.

tests/test_identifier_registry.py ties each to its producer and its consumer:
every emitted event is declared and has a subscriber, every subscriber listens
to an emitted event, every schedule has a handler, and no handler is a no-op.
SCREEN_STATES generates frontend/src/gen/registry.ts (scripts/gen.py registry),
so the frontend's state union cannot drift from this list.
"""

from __future__ import annotations

EVENTS: tuple[str, ...] = ("entry.recorded",)

SCHEDULES: tuple[str, ...] = ("prune_activity",)

SCREEN_STATES: tuple[str, ...] = (
    "loading",
    "loaded",
    "empty",
    "failed",
    "write_failed",
    "unauthenticated",
    "disabled_503",
    "not_composed",
    "partial",
)

TOOLS: tuple[str, ...] = ()  # model-callable tool names, once a model is in the loop
