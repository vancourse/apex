"""Shared fixtures. The database is a throwaway ``rails_planted_*`` one per session,
reached as the app role through the PRODUCTION factory; only a test marked
``@pytest.mark.superuser(reason=...)`` may hold an admin connection.

The planted database is created lazily, so lint and parity tests that need no
database run (and fail on their own defects) without Postgres.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
import pytest
from fastapi.testclient import TestClient

from oracle.checker import load_corpus
from __app__.db import Database
from __app__.roots import Composition
from __app__.roots.app import build
from __app__.settings import Settings, load_settings
from tests.planted_db import Planted, planted_database

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
# Lets a root build with no database (it connects lazily); used by gen and the
# parity tests that only inspect what a root composes.
OFFLINE_ENV = {
    "DATABASE_URL": "postgresql://offline@127.0.0.1:9/offline",
    "ALLOW_DEV_AUTH": "true",
}


@pytest.fixture(scope="session")
def corpus() -> dict[str, Any]:
    return load_corpus()


@pytest.fixture(scope="session")
def planted(corpus: dict[str, Any]) -> Iterator[Planted]:
    with planted_database(corpus=corpus) as db:
        yield db


@pytest.fixture(scope="session")
def settings(planted: Planted, corpus: dict[str, Any]) -> Settings:
    return load_settings(
        {
            "DATABASE_URL": planted.app_dsn,
            "AS_OF": corpus["as_of"],
            "ALLOW_DEV_AUTH": "true",
            "ADMIT_RACE_WINDOW_MS": "250",  # makes a missing admission lock lose every time
        }
    )


@pytest.fixture(scope="session")
def offline_settings() -> Settings:
    return load_settings(OFFLINE_ENV)


@pytest.fixture(scope="session")
def composition(settings: Settings) -> Composition:
    return build(settings)


@pytest.fixture(scope="session")
def db(composition: Composition) -> Database:
    database = composition.seams["db"]
    assert isinstance(database, Database)
    who = database.identity()
    assert "rolsuper=False" in who and "rolbypassrls=False" in who, (
        f"the app must not bypass RLS {who}"
    )
    return database


@pytest.fixture(scope="session")
def client(composition: Composition) -> TestClient:
    return TestClient(composition.app)


def superuser_reason(node: Any) -> str | None:
    """The reason a test gave for an admin connection, or None if it gave none."""
    marker = node.get_closest_marker("superuser")
    reason = "" if marker is None else str(marker.kwargs.get("reason", "")).strip()
    return reason or None


@pytest.fixture
def admin_conn(
    request: pytest.FixtureRequest, planted: Planted
) -> Iterator[psycopg.Connection]:
    if superuser_reason(request.node) is None:
        pytest.fail("an admin connection needs @pytest.mark.superuser(reason=...)")
    with psycopg.connect(planted.admin_dsn, autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="session")
def tokens(corpus: dict[str, Any]) -> dict[str, str]:
    """member id -> planted X-Member token."""
    return {m["id"]: m["token"] for m in corpus["member"]}
