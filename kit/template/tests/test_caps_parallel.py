"""R9: every admission cap in limits.CAPS holds under concurrency, against the real database.

For each cap: cap+3 admits start together (a barrier), each in its own thread on
its own connection through the production factory, and exactly `cap` must
succeed -- then the rows that LANDED are counted too. ADMIT_RACE_WINDOW_MS (the
settings fixture sets 250) holds every admit between its count and its insert,
so an admission without a lock admits all cap+3, every run.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

from __app__ import ledger, limits
from __app__.clock import PinnedClock, parse_instant
from __app__.db import Database, one
from __app__.events import SUBSCRIBERS, EventBus
from __app__.settings import Settings

PROBE_DAY = "2031-01-01T12:00:00Z"  # a day the planted corpus never touches


def _entries_per_day(
    db: Database, settings: Settings, corpus: dict[str, Any], attempt: int
) -> bool:
    kit = next(m for m in corpus["member"] if m["id"] == "m_kit")
    member = ledger.Member(kit["id"], kit["household"], kit["display_name"], kit["tz"])
    try:
        ledger.add_entry(
            db,
            clock=PinnedClock(parse_instant(PROBE_DAY)),
            events=EventBus(SUBSCRIBERS),
            member=member,
            amount_cents=1,
            note=f"cap probe {attempt}",
            race_window_s=settings.admit_race_window_ms / 1000,
        )
    except ledger.CapExceeded:
        return False
    return True


def _entries_per_day_landed(db: Database) -> int:
    with db.tenant("hh_scratch") as conn:
        (count,) = one(
            conn.execute(
                "SELECT count(*) FROM entries WHERE member_id = 'm_kit' AND occurred_on = %s",
                (parse_instant(PROBE_DAY).date(),),
            ).fetchone()
        )
    return int(count)


Probe = Callable[[Database, Settings, dict[str, Any], int], bool]
PROBES: dict[str, tuple[Probe, Callable[[Database], int]]] = {
    "ENTRIES_PER_DAY": (_entries_per_day, _entries_per_day_landed),
}


def test_every_cap_has_a_probe() -> None:
    assert set(PROBES) == set(limits.CAPS), (
        f"caps without a concurrency probe: {sorted(set(limits.CAPS) - set(PROBES))}"
    )


@pytest.mark.parametrize("cap_name", limits.CAPS)
def test_cap_admits_exactly_cap_under_concurrency(
    cap_name: str, db: Database, settings: Settings, corpus: dict[str, Any]
) -> None:
    cap = getattr(limits, cap_name)
    attempts = cap + 3
    probe, landed = PROBES[cap_name]
    assert settings.admit_race_window_ms > 0, (
        "the race window must be open or a missing lock can pass"
    )
    barrier = threading.Barrier(attempts)
    results: list[bool] = []
    errors: list[BaseException] = []

    def worker(i: int) -> None:
        try:
            barrier.wait(timeout=30)
            results.append(probe(db, settings, corpus, i))
        except BaseException as exc:  # noqa: BLE001 -- reported below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(attempts)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    who = db.identity("hh_scratch")
    assert not errors, f"{cap_name}: admits raised {errors!r} {who}"
    admitted = sum(results)
    assert admitted == cap, (
        f"{cap_name}: {admitted} of {attempts} concurrent admits succeeded; cap is {cap} {who}"
    )
    assert landed(db) == cap, (
        f"{cap_name}: {landed(db)} rows landed; cap is {cap} {who}"
    )
