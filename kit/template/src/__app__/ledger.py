"""The ledger engine: households, members, entries and the one concept, month_total.

Every function takes the production ``Database`` (the app role) and, where time
matters, a ``clock`` with no default. ``month_total`` is the OWNER of the
concept of that name (concepts.toml); tests/test_surface_parity.py compares what
the API serves with oracle/checker.py, which recomputes it from the planted
ledger without this module's SQL.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import date

from contracts.wire import Entry
from __app__ import limits
from __app__.clock import Clock, member_today
from __app__.db import Database, one
from __app__.events import EventBus


@dataclass(frozen=True)
class Member:
    id: str
    household_id: str
    display_name: str
    tz: str


class CapExceeded(Exception):
    """An admission cap from limits.py refused the write."""


def month_bounds(month: str) -> tuple[date, date]:
    """'2026-02' -> (2026-02-01, 2026-03-01): first day, and first day of the next month."""
    year, mon = (int(part) for part in month.split("-"))
    first = date(year, mon, 1)
    following = date(year + mon // 12, mon % 12 + 1, 1)
    return first, following


def create_household(db: Database, household_id: str, name: str) -> None:
    with db.tenant(household_id) as conn:
        conn.execute(
            "INSERT INTO households (id, name) VALUES (%s, %s)", (household_id, name)
        )


def add_member(
    db: Database,
    *,
    household_id: str,
    member_id: str,
    display_name: str,
    tz: str,
    token: str,
) -> Member:
    with db.tenant(household_id) as conn:
        conn.execute(
            "INSERT INTO members (id, household_id, display_name, tz, token) "
            "VALUES (%s, %s, %s, %s, %s)",
            (member_id, household_id, display_name, tz, token),
        )
    return Member(member_id, household_id, display_name, tz)


def resolve_token(db: Database, token: str) -> Member | None:
    """X-Member token -> member, through a SECURITY DEFINER lookup (no tenant yet)."""
    with db.unbound() as conn:
        row = conn.execute(
            "SELECT id, household_id, display_name, tz FROM member_by_token(%s)",
            (token,),
        ).fetchone()
    return None if row is None else Member(*row)


def remove_member(db: Database, member: Member) -> None:
    """Every row carrying this member_id goes with them (tests/test_auth_matrix.py)."""
    with db.tenant(member.household_id) as conn:
        conn.execute("DELETE FROM members WHERE id = %s", (member.id,))


def month_total(db: Database, household_id: str, month: str) -> int:
    """OWNER of concept `month_total`: the sum of a household's entries in one
    calendar month, each entry dated in its member's timezone when recorded."""
    first, following = month_bounds(month)
    with db.tenant(household_id) as conn:
        (total,) = one(
            conn.execute(
                "SELECT coalesce(sum(amount_cents), 0)::bigint FROM entries "
                "WHERE household_id = %(household)s "
                "AND occurred_on >= %(first)s AND occurred_on < %(next)s",
                {"household": household_id, "first": first, "next": following},
            ).fetchone()
        )
    return int(total)


def list_entries(db: Database, household_id: str, month: str) -> list[Entry]:
    first, following = month_bounds(month)
    with db.tenant(household_id) as conn:
        rows = conn.execute(
            "SELECT id::text, household_id, member_id, amount_cents, occurred_on, note "
            "FROM entries WHERE household_id = %(household)s "
            "AND occurred_on >= %(first)s AND occurred_on < %(next)s "
            "ORDER BY occurred_on, recorded_at, id LIMIT %(limit)s",
            {
                "household": household_id,
                "first": first,
                "next": following,
                "limit": limits.PAGE_SIZE,
            },
        ).fetchall()
    return [
        Entry(
            id=r[0],
            household_id=r[1],
            member_id=r[2],
            amount_cents=r[3],
            occurred_on=r[4],
            note=r[5],
        )
        for r in rows
    ]


def add_entry(
    db: Database,
    *,
    clock: Clock,
    events: EventBus,
    member: Member,
    amount_cents: int,
    note: str,
    race_window_s: float,
) -> Entry:
    """OWNER of concept `entry_amount`. Admits at most ENTRIES_PER_DAY per member-local day.

    The admission is race-free because the member's row is locked FOR UPDATE
    before the count: concurrent admits for one member queue on that lock, and
    each counts after the previous one committed. ``race_window_s`` (the
    ADMIT_RACE_WINDOW_MS setting, 0 in production) widens the gap between the
    count and the insert so a missing lock fails tests/test_caps_parallel.py
    every time instead of now and then.
    """
    recorded_at = clock.now()
    occurred_on = member_today(clock, member.tz)
    with db.tenant(member.household_id) as conn:
        conn.execute("SELECT 1 FROM members WHERE id = %s FOR UPDATE", (member.id,))
        (count,) = one(
            conn.execute(
                "SELECT count(*) FROM entries WHERE member_id = %s AND occurred_on = %s",
                (member.id, occurred_on),
            ).fetchone()
        )
        if count >= limits.ENTRIES_PER_DAY:
            raise CapExceeded(
                f"{member.id} already recorded {count} entries on {occurred_on} "
                f"(ENTRIES_PER_DAY={limits.ENTRIES_PER_DAY})"
            )
        if race_window_s:
            time.sleep(race_window_s)
        row = one(
            conn.execute(
                "INSERT INTO entries (household_id, member_id, amount_cents, occurred_on, "
                "recorded_at, note) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id::text",
                (
                    member.household_id,
                    member.id,
                    amount_cents,
                    occurred_on,
                    recorded_at,
                    note,
                ),
            ).fetchone()
        )
        events.emit(
            conn,
            "entry.recorded",
            {
                "household_id": member.household_id,
                "member_id": member.id,
                "recorded_at": recorded_at,
            },
        )
    return Entry(
        id=row[0],
        household_id=member.household_id,
        member_id=member.id,
        amount_cents=amount_cents,
        occurred_on=occurred_on,
        note=note,
    )
