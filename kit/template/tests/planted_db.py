"""A throwaway planted database: create, migrate, seed, drop.

Used by tests/conftest.py and scripts/walk.py. The admin DSN comes from
DATABASE_URL (default: the local Docker Postgres). Everything created here is
named ``rails_planted_<random>`` -- the database AND its app role -- and nothing
here touches, connects to as a target, or drops any database or role whose name
does not start with that prefix.

Seeding goes through the app's own write path (``ledger.create_household``,
``add_member``, ``add_entry``) as the app role, so the corpus can only hold
shapes production code can produce.
"""

from __future__ import annotations

import os
import secrets
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict

from __app__ import ledger, migrate
from __app__.clock import PinnedClock, parse_instant
from __app__.db import Database
from __app__.events import SUBSCRIBERS, EventBus

PREFIX = "rails_planted_"
DEFAULT_ADMIN_DSN = "postgresql://postgres:postgres@127.0.0.1:5432/postgres"


class PostgresUnavailable(RuntimeError):
    """The admin DSN does not answer. Not a code failure."""


@dataclass(frozen=True)
class Planted:
    name: str
    role: str
    admin_dsn: str  # the cluster admin, connected to the planted database
    app_dsn: str  # the app role: NOSUPERUSER NOBYPASSRLS


def admin_dsn() -> str:
    return os.environ.get("DATABASE_URL") or DEFAULT_ADMIN_DSN


def _url(
    parts: dict[str, Any],
    *,
    dbname: str,
    user: str | None = None,
    password: str | None = None,
) -> str:
    """A postgresql:// URL built from parsed conninfo parts, never by string surgery."""
    user = user if user is not None else str(parts.get("user", "postgres"))
    password = password if password is not None else str(parts.get("password", ""))
    host = parts.get("host", "127.0.0.1")
    port = parts.get("port", "5432")
    auth = quote(user, safe="") + (":" + quote(password, safe="") if password else "")
    return f"postgresql://{auth}@{host}:{port}/{quote(dbname, safe='')}"


def _reachable(parts: dict[str, Any]) -> bool:
    host = parts.get("host", "127.0.0.1")
    port = int(parts.get("port", "5432"))
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _guard(name: str) -> str:
    if not name.startswith(PREFIX):
        raise RuntimeError(f"refusing to touch {name!r}: not a {PREFIX}* object")
    return name


@contextmanager
def planted_database(
    dsn: str | None = None, *, corpus: dict[str, Any] | None = None
) -> Iterator[Planted]:
    from oracle.checker import load_corpus

    dsn = dsn or admin_dsn()
    parts = conninfo_to_dict(dsn)
    if not _reachable(parts):
        raise PostgresUnavailable(
            f"Postgres unavailable at {parts.get('host')}:{parts.get('port', '5432')}: "
            "not a code failure (start Docker Postgres or set DATABASE_URL)"
        )
    suffix = secrets.token_hex(4)
    name = _guard(f"{PREFIX}{suffix}")
    role = _guard(f"{PREFIX}{suffix}_app")
    password = secrets.token_urlsafe(18)
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(
            sql.SQL(
                "CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
            ).format(sql.Identifier(role), sql.Literal(password))
        )
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    planted = Planted(
        name=name,
        role=role,
        admin_dsn=_url(parts, dbname=name),
        app_dsn=_url(parts, dbname=name, user=role, password=password),
    )
    try:
        with psycopg.connect(planted.admin_dsn) as conn:
            migrate.apply(conn, app_role=role)
        seed(Database(planted.app_dsn), corpus or load_corpus())
        yield planted
    finally:
        with psycopg.connect(dsn, autocommit=True) as admin:
            admin.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(_guard(name))
                )
            )
            admin.execute(
                sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(_guard(role)))
            )


def seed(db: Database, corpus: dict[str, Any]) -> None:
    """The planted corpus, through the app's own write path, as the app role."""
    bus = EventBus(SUBSCRIBERS)
    for household in corpus["household"]:
        ledger.create_household(db, household["id"], household["name"])
    members = {}
    for m in corpus["member"]:
        members[m["id"]] = ledger.add_member(
            db,
            household_id=m["household"],
            member_id=m["id"],
            display_name=m["display_name"],
            tz=m["tz"],
            token=m["token"],
        )
    for entry in sorted(corpus["entry"], key=lambda e: e["recorded_at"]):
        ledger.add_entry(
            db,
            clock=PinnedClock(parse_instant(entry["recorded_at"])),
            events=bus,
            member=members[entry["member"]],
            amount_cents=entry["amount_cents"],
            note=entry["note"],
            race_window_s=0.0,
        )
