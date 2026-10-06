"""In-transaction events: ``bus.emit(conn, "<name>", payload)`` runs every subscriber
inside the emitter's transaction, so an event and its effects commit together.

Names come from contracts/registry.py EVENTS. tests/test_identifier_registry.py
fails an emitted name with no subscriber, a subscriber to a name nothing emits,
and a handler that does nothing (``pass``, ``...``, a lambda, a constant return).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import psycopg

from contracts.registry import EVENTS

Handler = Callable[[psycopg.Connection, Mapping[str, Any]], None]

SUBSCRIBERS: dict[str, list[Handler]] = {}


def subscribe(name: str) -> Callable[[Handler], Handler]:
    if name not in EVENTS:
        raise ValueError(f"event {name!r} is not declared in contracts/registry.py")

    def register(handler: Handler) -> Handler:
        SUBSCRIBERS.setdefault(name, []).append(handler)
        return handler

    return register


class EventBus:
    def __init__(self, subscribers: Mapping[str, Sequence[Handler]]) -> None:
        self._subscribers = subscribers

    def emit(
        self, conn: psycopg.Connection, name: str, payload: Mapping[str, Any]
    ) -> None:
        if name not in EVENTS:
            raise ValueError(f"event {name!r} is not declared in contracts/registry.py")
        for handler in self._subscribers.get(name, ()):
            handler(conn, payload)


@subscribe("entry.recorded")
def record_activity(conn: psycopg.Connection, payload: Mapping[str, Any]) -> None:
    conn.execute(
        "INSERT INTO activity (household_id, member_id, kind, at) VALUES (%s, %s, %s, %s)",
        (
            payload["household_id"],
            payload["member_id"],
            "entry.recorded",
            payload["recorded_at"],
        ),
    )
