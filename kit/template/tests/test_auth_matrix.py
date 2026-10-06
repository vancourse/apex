"""R8: the auth and negative-input matrix, enumerated from the COMPOSED app.

Every route the root serves needs a row in auth_matrix.toml (and every row a
route); each actor gets exactly its declared status; every `str` path or query
parameter fed ../, %2e%2e, empty, 4 KB or NUL gets a 4xx, never a 2xx or 5xx.
Removing a member leaves no row carrying their member_id in ANY table that has
a member_id column -- the tables are read from the catalog, so a new one joins.
"""

from __future__ import annotations

import tomllib
import typing
from typing import Any

import psycopg
import pytest
from psycopg import sql
from fastapi.testclient import TestClient

from scripts.gen import flat_params
from __app__ import ledger
from __app__.clock import PinnedClock, parse_instant
from __app__.db import Database, describe, one
from __app__.events import SUBSCRIBERS, EventBus
from __app__.roots import Composition, api_routes as _all_routes
from tests.astscan import ROOT

MATRIX = tomllib.loads((ROOT / "auth_matrix.toml").read_text(encoding="utf-8"))
ACTORS = ("anonymous", "member", "other_member")
HOSTILE = {
    "dot-dot-slash": "../",
    "encoded-dot-dot": "%2e%2e",
    "empty": "",
    "4kb": "a" * 4096,
    "nul": "%00",
}


def api_routes(comp: Composition) -> list[Any]:
    return [r for r in _all_routes(comp.app) if r.path.startswith("/api")]


def _row(method: str, path: str) -> dict[str, Any] | None:
    return next(
        (r for r in MATRIX["route"] if r["method"] == method and r["path"] == path),
        None,
    )


def _url(path: str, household: str, override: dict[str, str] | None = None) -> str:
    values = {"household_id": household, **(override or {})}
    for name, value in values.items():
        path = path.replace("{" + name + "}", value)
    return path


def _headers(actor: str, tokens: dict[str, str]) -> dict[str, str]:
    if actor == "anonymous":
        return {}
    return {"X-Member": tokens[MATRIX["actors"][actor]]}


def _is_str(annotation: Any) -> bool:
    return annotation is str or str in typing.get_args(annotation)


def test_every_route_has_a_row_and_every_row_a_route(composition: Composition) -> None:
    served = {(m, r.path) for r in api_routes(composition) for m in r.methods}
    declared = {(r["method"], r["path"]) for r in MATRIX["route"]}
    assert served, "the composed app serves no /api routes"
    problems = [
        f"no auth_matrix.toml row for {m} {p}" for m, p in sorted(served - declared)
    ]
    problems += [
        f"auth_matrix.toml row for a route the app does not serve: {m} {p}"
        for m, p in sorted(declared - served)
    ]
    assert not problems, "\n".join(problems)


def test_route_actor_matrix(
    composition: Composition, client: TestClient, tokens: dict[str, str], db: Database
) -> None:
    household = MATRIX["actors"]["household"]
    problems = []
    for route in api_routes(composition):
        for method in sorted(route.methods):
            row = _row(method, route.path)
            if row is None:
                continue  # reported by the test above
            for actor in ACTORS:
                response = client.request(
                    method,
                    _url(route.path, household),
                    headers=_headers(actor, tokens),
                    json=row.get("body"),
                )
                if response.status_code != row[actor]:
                    problems.append(
                        f"{method} {route.path} as {actor}: got {response.status_code}, "
                        f"declared {row[actor]} -- {response.text[:120]}"
                    )
    assert not problems, "\n".join(problems) + f"\n{db.identity(household)}"


def test_hostile_string_parameters_get_a_4xx(
    composition: Composition, client: TestClient, tokens: dict[str, str]
) -> None:
    household = MATRIX["actors"]["household"]
    headers = _headers("member", tokens)
    checked, problems = 0, []
    for route in api_routes(composition):
        flat = flat_params(route.dependant)
        for method in sorted(route.methods):
            row = _row(method, route.path) or {}
            for param in flat["path"]:
                if not _is_str(param.field_info.annotation):
                    continue
                for label, value in HOSTILE.items():
                    url = _url(route.path, household, {param.name: value})
                    status = client.request(
                        method, url, headers=headers, json=row.get("body")
                    ).status_code
                    checked += 1
                    if not 400 <= status < 500:
                        problems.append(
                            f"{method} {route.path} path {param.name}={label}: {status}"
                        )
            for param in flat["query"]:
                if not _is_str(param.field_info.annotation):
                    continue
                for label, value in HOSTILE.items():
                    raw = "\x00" if label == "nul" else value
                    url = _url(route.path, household)
                    status = client.request(
                        method,
                        url,
                        params={param.name: raw},
                        headers=headers,
                        json=row.get("body"),
                    ).status_code
                    checked += 1
                    if not 400 <= status < 500:
                        problems.append(
                            f"{method} {route.path} query {param.name}={label}: {status}"
                        )
    assert checked, "no str path or query parameter found -- the enumeration is broken"
    assert not problems, "hostile input must be refused with a 4xx:\n" + "\n".join(
        problems
    )


@pytest.mark.superuser(
    reason="reads every member_id column across tenants after a removal"
)
def test_member_removal_leaves_no_rows(
    admin_conn: psycopg.Connection, db: Database
) -> None:
    household = MATRIX["actors"]["household"]
    probe = ledger.add_member(
        db,
        household_id=household,
        member_id="m_removal_probe",
        display_name="Probe",
        tz="UTC",
        token="planted-removal",
    )
    ledger.add_entry(
        db,
        clock=PinnedClock(parse_instant("2031-02-01T12:00:00Z")),
        events=EventBus(SUBSCRIBERS),
        member=probe,
        amount_cents=1,
        note="removal probe",
        race_window_s=0.0,
    )
    tables = [
        name
        for (name,) in admin_conn.execute(
            "SELECT table_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND column_name = 'member_id' ORDER BY table_name"
        )
    ]
    assert tables, f"no member_id columns in the catalog {describe(admin_conn)}"

    def count(table: str) -> int:
        query = sql.SQL("SELECT count(*) FROM {} WHERE member_id = %s").format(
            sql.Identifier("public", table)
        )
        (n,) = one(admin_conn.execute(query, (probe.id,)).fetchone())
        return int(n)

    before = {t: count(t) for t in tables}
    assert sum(before.values()) >= 2, (
        f"the probe planted too little to prove a removal: {before}"
    )
    ledger.remove_member(db, probe)
    left = {t: n for t in tables if (n := count(t))}
    (member_rows,) = one(
        admin_conn.execute(
            "SELECT count(*) FROM members WHERE id = %s", (probe.id,)
        ).fetchone()
    )
    assert not left and member_rows == 0, (
        f"rows left after removing {probe.id}: {left} {describe(admin_conn)}"
    )
