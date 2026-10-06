"""The production connection factory.

It connects with DATABASE_URL -- the app role, NOSUPERUSER NOBYPASSRLS -- and
binds the tenant per transaction with ``set_config('app.tenant_id', ..., true)``,
so every row-level-security policy keyed on that setting applies. On its first
connection it refuses to serve as a role that would ignore RLS. Tests use this
same factory; a superuser connection in a test needs @pytest.mark.superuser.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg


def one(row: tuple[Any, ...] | None) -> tuple[Any, ...]:
    """fetchone() of a query that always returns exactly one row."""
    if row is None:
        raise LookupError("expected exactly one row, got none")
    return row


class UnsafeRole(RuntimeError):
    """The DSN's role is a superuser or BYPASSRLS: RLS would silently not apply."""


_POSTURE = (
    "SELECT current_user, r.rolsuper, r.rolbypassrls, "
    "coalesce(current_setting('app.tenant_id', true), '<unset>') "
    "FROM pg_roles r WHERE r.rolname = current_user"
)


class Database:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._checked = False

    def _connect(self) -> psycopg.Connection:
        conn = psycopg.connect(self._dsn)
        if not self._checked:
            user, superuser, bypass, _tenant = one(conn.execute(_POSTURE).fetchone())
            if superuser or bypass:
                conn.close()
                raise UnsafeRole(
                    f"refusing to serve as {user!r}: superuser={superuser} "
                    f"bypassrls={bypass}; row-level security would not apply"
                )
            self._checked = True
        return conn

    @contextmanager
    def tenant(self, household_id: str) -> Iterator[psycopg.Connection]:
        """One transaction bound to one household. Commits on success."""
        with self._connect() as conn:
            conn.execute(
                "SELECT set_config('app.tenant_id', %s, true)", (household_id,)
            )
            yield conn

    @contextmanager
    def unbound(self) -> Iterator[psycopg.Connection]:
        """One transaction with no tenant: RLS tables read as empty.

        Only SECURITY DEFINER functions (token lookup, maintenance) reach data
        from here.
        """
        with self._connect() as conn:
            yield conn

    def identity(self, household_id: str | None = None) -> str:
        """current_user, rolsuper, rolbypassrls, tenant -- print it beside a DB assertion."""
        ctx = self.unbound() if household_id is None else self.tenant(household_id)
        with ctx as conn:
            return describe(conn)


def describe(conn: psycopg.Connection) -> str:
    user, superuser, bypass, tenant = one(conn.execute(_POSTURE).fetchone())
    return f"[as {user} rolsuper={superuser} rolbypassrls={bypass} tenant={tenant}]"
