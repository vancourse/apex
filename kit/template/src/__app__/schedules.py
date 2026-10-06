"""Recurring work. Every schedule named in contracts/registry.py has a real handler
here; the root composes each one and tests/test_root_parity.py runs it once
against the planted database as the app role.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

from __app__ import limits
from __app__.clock import Clock
from __app__.db import Database, one


@dataclass(frozen=True)
class ScheduleContext:
    db: Database
    clock: Clock


@dataclass(frozen=True)
class Schedule:
    name: str
    every_s: int
    handler: Callable[[ScheduleContext], int]


def prune_activity(ctx: ScheduleContext) -> int:
    """Delete activity older than ACTIVITY_RETENTION_DAYS; returns the rows removed."""
    cutoff = ctx.clock.now() - timedelta(days=limits.ACTIVITY_RETENTION_DAYS)
    with ctx.db.unbound() as conn:
        (removed,) = one(
            conn.execute("SELECT prune_activity(%s)", (cutoff,)).fetchone()
        )
    return int(removed)


SCHEDULES: dict[str, Schedule] = {
    "prune_activity": Schedule(
        "prune_activity", limits.PRUNE_ACTIVITY_EVERY_S, prune_activity
    ),
}
