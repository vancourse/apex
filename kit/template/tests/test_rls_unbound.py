"""R9: generated from the catalog -- every public table is tenant-scoped.

The table list comes from pg_class at run time, so a new table joins this test
the moment a migration creates it. Each must have row-level security, must hold
planted rows (so "0 rows" means something), and must read as EMPTY to the app
role with the tenant unset and with it set to ''.
"""

from __future__ import annotations

from types import SimpleNamespace

import psycopg
import pytest
from psycopg import sql

from __app__.db import Database, describe, one
from tests.conftest import superuser_reason

CATALOG = """
SELECT c.relname, c.relrowsecurity
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
ORDER BY c.relname
"""


@pytest.mark.superuser(
    reason="reads the catalog and counts planted rows across every tenant"
)
def test_every_public_table_is_rls_scoped_and_reads_empty_unbound(
    admin_conn: psycopg.Connection, db: Database
) -> None:
    tables = admin_conn.execute(CATALOG).fetchall()
    assert len(tables) >= 4, (
        f"catalog returned {tables!r}; the migration did not run? {describe(admin_conn)}"
    )
    problems = []
    for name, has_rls in tables:
        count = sql.SQL("SELECT count(*) FROM {}").format(
            sql.Identifier("public", name)
        )
        if not has_rls:
            problems.append(f"{name}: row-level security is not enabled")
        (planted,) = one(admin_conn.execute(count).fetchone())
        if planted == 0:
            problems.append(
                f"{name}: holds no planted rows, so an empty read proves nothing {describe(admin_conn)}"
            )
        with db.unbound() as conn:
            for tenant in (None, ""):
                if tenant is not None:
                    conn.execute(
                        "SELECT set_config('app.tenant_id', %s, true)", (tenant,)
                    )
                (seen,) = one(conn.execute(count).fetchone())
                if seen:
                    problems.append(f"{name}: {seen} rows visible {describe(conn)}")
    assert not problems, "\n".join(problems)


def test_an_admin_connection_needs_a_reasoned_marker() -> None:
    def node(marker: object) -> SimpleNamespace:
        return SimpleNamespace(
            get_closest_marker=lambda name: marker if name == "superuser" else None
        )

    assert superuser_reason(node(None)) is None
    assert superuser_reason(node(pytest.mark.superuser.mark)) is None
    assert superuser_reason(node(pytest.mark.superuser(reason="  ").mark)) is None
    assert (
        superuser_reason(node(pytest.mark.superuser(reason="counts rows").mark))
        == "counts rows"
    )
