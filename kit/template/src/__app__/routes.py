"""The HTTP surface. Every route has a response_model (tests/test_contracts.py) and a
row in auth_matrix.toml (tests/test_auth_matrix.py enumerates routes from the
composed app, so a new route without a row fails).

Household routes check the member belongs to the path's household AND bind the
database tenant to the member's own household: either alone would stop a
cross-household read; both are here so one regression is not a leak.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Query, Request

from contracts.wire import (
    ID_PATTERN,
    MONTH_PATTERN,
    Entry,
    EntryList,
    Health,
    Me,
    NewEntry,
    Summary,
)
from __app__ import ledger
from __app__.auth import DevTokenAuth
from __app__.clock import Clock, PinnedClock, member_month
from __app__.db import Database
from __app__.events import EventBus
from __app__.ledger import CapExceeded, Member


@dataclass(frozen=True)
class Wiring:
    """The composed seams, typed, as the routes see them (built by the root)."""

    auth: DevTokenAuth
    clock: Clock
    db: Database
    events: EventBus
    race_window_s: float


def wiring(request: Request) -> Wiring:
    return request.app.state.wiring


HouseholdId = Annotated[str, Path(pattern=ID_PATTERN)]
MonthParam = Annotated[str | None, Query(pattern=MONTH_PATTERN)]


def current_member(
    w: Annotated[Wiring, Depends(wiring)],
    x_member: Annotated[str | None, Header()] = None,
) -> Member:
    member = w.auth.resolve(x_member)
    if member is None:
        raise HTTPException(status_code=401, detail="unknown or missing X-Member")
    return member


def require_household(member: Member, household_id: str) -> None:
    if member.household_id != household_id:
        raise HTTPException(status_code=403, detail="not a member of this household")


PREFIX = "/api"
ROUTES: list[dict[str, Any]] = []
F = TypeVar("F", bound=Callable[..., Any])


def route(method: str, path: str, *, response_model: type, status_code: int = 200) -> Callable[[F], F]:
    """Declare a route. The root mounts ROUTES with add_api_route, so the composed
    app's own route list -- not an included sub-router -- is what tests enumerate."""

    def register(endpoint: F) -> F:
        ROUTES.append(
            {
                "path": PREFIX + path,
                "endpoint": endpoint,
                "methods": [method],
                "response_model": response_model,
                "status_code": status_code,
                "name": endpoint.__name__,
            }
        )
        return endpoint

    return register


def mount(app: FastAPI) -> None:
    for spec in ROUTES:
        app.add_api_route(**spec)


@route("GET", "/health", response_model=Health)
def health(w: Annotated[Wiring, Depends(wiring)]) -> Health:
    return Health(
        status="ok", clock="pinned" if isinstance(w.clock, PinnedClock) else "wall"
    )


@route("GET", "/me", response_model=Me)
def me(member: Annotated[Member, Depends(current_member)]) -> Me:
    return Me(
        member_id=member.id,
        household_id=member.household_id,
        display_name=member.display_name,
    )


@route("GET", "/households/{household_id}/summary", response_model=Summary)
def get_summary(
    household_id: HouseholdId,
    member: Annotated[Member, Depends(current_member)],
    w: Annotated[Wiring, Depends(wiring)],
    month: MonthParam = None,
) -> Summary:
    require_household(member, household_id)
    month = month or member_month(w.clock, member.tz)
    total = ledger.month_total(w.db, member.household_id, month)
    return Summary(
        household_id=member.household_id, month=month, month_total_cents=total
    )


@route("GET", "/households/{household_id}/entries", response_model=EntryList)
def list_entries(
    household_id: HouseholdId,
    member: Annotated[Member, Depends(current_member)],
    w: Annotated[Wiring, Depends(wiring)],
    month: MonthParam = None,
) -> EntryList:
    require_household(member, household_id)
    month = month or member_month(w.clock, member.tz)
    entries = ledger.list_entries(w.db, member.household_id, month)
    return EntryList(household_id=member.household_id, month=month, entries=entries)


@route("POST", "/households/{household_id}/entries", response_model=Entry, status_code=201)
def post_entry(
    household_id: HouseholdId,
    body: NewEntry,
    member: Annotated[Member, Depends(current_member)],
    w: Annotated[Wiring, Depends(wiring)],
) -> Entry:
    require_household(member, household_id)
    try:
        return ledger.add_entry(
            w.db,
            clock=w.clock,
            events=w.events,
            member=member,
            amount_cents=body.amount_cents,
            note=body.note,
            race_window_s=w.race_window_s,
        )
    except CapExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
