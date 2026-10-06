"""Apply migrations/*.sql in name order, once each, as the schema OWNER.

    python -m __app__.migrate --app-role <role>      # owner DSN: MIGRATE_DATABASE_URL

Grants go to the app role named on the command line: each migration reads it
as ``current_setting('rails.app_role')``, so one migration serves every
environment's role name. Bookkeeping lives in the ``meta`` schema, which the
app role cannot see.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import psycopg

from __app__.settings import load_settings

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def apply(
    conn: psycopg.Connection, *, app_role: str, directory: Path = MIGRATIONS
) -> list[str]:
    conn.execute("CREATE SCHEMA IF NOT EXISTS meta")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta.migrations (name text PRIMARY KEY, applied_at timestamptz NOT NULL)"
    )
    conn.execute("SELECT set_config('rails.app_role', %s, false)", (app_role,))
    done = {row[0] for row in conn.execute("SELECT name FROM meta.migrations")}
    applied: list[str] = []
    for path in sorted(directory.glob("*.sql")):
        if path.name in done:
            continue
        conn.execute(path.read_text(encoding="utf-8"))  # type: ignore[arg-type]  # trusted repo file
        conn.execute(
            "INSERT INTO meta.migrations (name, applied_at) VALUES (%s, statement_timestamp())",
            (path.name,),
        )
        applied.append(path.name)
    conn.commit()
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m __app__.migrate")
    parser.add_argument("--app-role", required=True, help="role the server connects as")
    args = parser.parse_args(argv)
    dsn = load_settings().migrate_database_url.get_secret_value()
    if not dsn:
        parser.error("MIGRATE_DATABASE_URL is not set")
    with psycopg.connect(dsn) as conn:
        for name in apply(conn, app_role=args.app_role):
            print(f"applied {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
