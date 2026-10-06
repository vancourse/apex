"""The ONE place this app reads the wall clock.

Engines take a ``clock`` argument with no default, so a caller cannot forget to
pass the pinned one (tests/test_clock_lint.py fails a ``clock=`` default and any
``datetime.now``/``date.today``/``time.time`` outside this file). "Today" is
always a member's today, in the member's own timezone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from zoneinfo import ZoneInfo


class Clock(Protocol):
    def now(self) -> datetime:
        """An aware UTC instant."""
        ...


class WallClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class PinnedClock:
    as_of: datetime

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("PinnedClock needs an aware instant (add Z or an offset)")

    def now(self) -> datetime:
        return self.as_of.astimezone(UTC)


def parse_instant(text: str) -> datetime:
    instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if instant.tzinfo is None:
        raise ValueError(f"instant {text!r} has no timezone")
    return instant


def from_as_of(as_of: str) -> Clock:
    """The AS_OF setting: empty is the wall clock, anything else pins it."""
    return PinnedClock(parse_instant(as_of)) if as_of else WallClock()


def member_today(clock: Clock, tz: str) -> date:
    return clock.now().astimezone(ZoneInfo(tz)).date()


def member_month(clock: Clock, tz: str) -> str:
    return member_today(clock, tz).strftime("%Y-%m")
