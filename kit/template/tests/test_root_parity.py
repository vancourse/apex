"""R5: every composition root composes every seam, schedule and server setting.

Introspects each root in roots/registry.py ROOTS by BUILDING it: a root that
omits something roots/exclusions.toml does not excuse fails, a seam left None
refuses to boot, and every schedule handler runs once as the app role.
"""

from __future__ import annotations

import importlib
import tomllib
from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from fastapi import FastAPI

from scripts.gen import setting_rows
from __app__.clock import WallClock
from __app__.db import Database
from __app__.roots import Composition, NullSeam
from __app__.roots.registry import ROOTS, SEAMS
from __app__.schedules import SCHEDULES
from __app__.settings import Settings
from tests.astscan import ROOT

EXCLUSIONS = ROOT / "src" / "__app__" / "roots" / "exclusions.toml"
KINDS = ("seam", "schedule", "config")


def _resolve(target: str) -> Callable[[Settings], Composition]:
    module, _, name = target.partition(":")
    return getattr(importlib.import_module(module), name)


def exclusions() -> list[dict[str, Any]]:
    return tomllib.loads(EXCLUSIONS.read_text(encoding="utf-8")).get("exclude", [])


def test_exclusions_are_reasoned_and_current() -> None:
    today = WallClock().now().date()
    problems = []
    for row in exclusions():
        label = f"{row.get('root')}/{row.get('kind')}/{row.get('name')}"
        if row.get("root") not in ROOTS:
            problems.append(f"{label}: unknown root")
        if row.get("kind") not in KINDS:
            problems.append(f"{label}: kind must be one of {KINDS}")
        if not str(row.get("reason", "")).strip():
            problems.append(f"{label}: no reason")
        try:
            if date.fromisoformat(str(row.get("expires"))) < today:
                problems.append(
                    f"{label}: expired {row['expires']} -- compose it or renew with a reason"
                )
        except ValueError:
            problems.append(f"{label}: expires must be YYYY-MM-DD")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize("root_name", sorted(ROOTS))
def test_every_root_composes_its_seams_schedules_and_settings(
    root_name: str, offline_settings: Settings
) -> None:
    comp = _resolve(ROOTS[root_name])(
        offline_settings
    )  # a None seam raises NullSeam here
    excused = {(r["kind"], r["name"]) for r in exclusions() if r["root"] == root_name}
    server = {r["name"] for r in setting_rows(ROOT) if "server" in r["consumers"]}
    wanted = {
        "seam": set(SEAMS),
        "schedule": set(SCHEDULES),
        "config": server,
    }
    have = {
        "seam": set(comp.seams),
        "schedule": set(comp.schedules),
        "config": set(comp.config_fields),
    }
    problems = [
        f"{root_name} omits {kind} {name!r} (compose it, or add a dated row to roots/exclusions.toml)"
        for kind in KINDS
        for name in sorted(
            wanted[kind] - have[kind] - {n for k, n in excused if k == kind}
        )
    ]
    problems += [
        f"{root_name}: schedule {n!r} has no handler"
        for n, h in comp.schedules.items()
        if not callable(h)
    ]
    assert not problems, "\n".join(problems)
    assert comp.routes, f"{root_name} serves no routes"


def test_a_null_seam_refuses_boot() -> None:
    comp = Composition(
        app=FastAPI(), config_fields=frozenset(), seams={"db": None}, schedules={}
    )
    with pytest.raises(NullSeam, match="db"):
        comp.assert_no_null_seams()
    comp = Composition(
        app=FastAPI(), config_fields=frozenset(), seams={}, schedules={"tick": None}
    )
    with pytest.raises(NullSeam, match="tick"):
        comp.assert_no_null_seams()


def test_the_root_refuses_to_boot_without_an_auth_seam(
    offline_settings: Settings,
) -> None:
    from __app__.roots.app import build

    with pytest.raises(NullSeam, match="auth"):
        build(offline_settings.model_copy(update={"allow_dev_auth": False}))


def test_every_schedule_runs_as_the_app_role(composition: Composition) -> None:
    db = composition.seams["db"]
    assert isinstance(db, Database)
    who = db.identity()
    assert "rolsuper=False" in who and "rolbypassrls=False" in who, who
    for name, handler in composition.schedules.items():
        assert handler is not None
        result = handler()
        assert isinstance(result, int) and result >= 0, (
            f"schedule {name} returned {result!r} {who}"
        )
