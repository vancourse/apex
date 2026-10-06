"""R7: one wire definition; frozen schema and frontend client generated from it.

Fails when wire/frozen.json, frontend/src/gen/types.ts or client.ts is stale, when
a route has no response_model, and when a field in wire/baseline.json is removed,
retyped or made required. Adding an OPTIONAL field is the only admitted change.
"""

from __future__ import annotations

import copy
import json
from typing import Any

from scripts.gen import render_contracts, stale
from __app__.roots import api_routes
from __app__.roots.app import build
from __app__.settings import Settings
from tests.astscan import ROOT, rel

COSMETIC = ("title", "description", "examples", "default")


def _shape(schema: Any) -> Any:
    if isinstance(schema, dict):
        return {k: _shape(v) for k, v in schema.items() if k not in COSMETIC}
    if isinstance(schema, list):
        return [_shape(v) for v in schema]
    return schema


def additive_problems(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    problems = []
    for model, old in baseline["models"].items():
        new = current["models"].get(model)
        if new is None:
            problems.append(f"{model}: removed")
            continue
        old_props, new_props = old.get("properties", {}), new.get("properties", {})
        for field, old_schema in old_props.items():
            if field not in new_props:
                problems.append(f"{model}.{field}: removed")
            elif _shape(new_props[field]) != _shape(old_schema):
                problems.append(f"{model}.{field}: retyped")
        for field in sorted(
            set(new.get("required", [])) - set(old.get("required", []))
        ):
            why = (
                "became required"
                if field in old_props
                else "added as required (a new field must be optional)"
            )
            problems.append(f"{model}.{field}: {why}")
    return problems


def test_generated_wire_is_current() -> None:
    drift = stale(render_contracts(ROOT))
    assert not drift, (
        f"stale: {[rel(p) for p in drift]} -- run `uv run python scripts/gen.py contracts`"
    )


def test_every_route_has_a_response_model(offline_settings: Settings) -> None:
    comp = build(offline_settings)
    routes = api_routes(comp.app)
    assert routes, "the composed app serves no API routes"
    untyped = [
        f"{sorted(r.methods or ())} {r.path}"
        for r in routes
        if r.response_model is None
    ]
    assert not untyped, f"routes without response_model: {untyped}"


def test_frozen_wire_is_additive_over_baseline() -> None:
    baseline = json.loads((ROOT / "wire" / "baseline.json").read_text(encoding="utf-8"))
    frozen = json.loads((ROOT / "wire" / "frozen.json").read_text(encoding="utf-8"))
    problems = additive_problems(baseline, frozen)
    assert not problems, "wire/frozen.json breaks wire/baseline.json:\n" + "\n".join(
        problems
    )


def test_additive_check_refuses_removal_retype_and_new_required() -> None:
    baseline = json.loads((ROOT / "wire" / "baseline.json").read_text(encoding="utf-8"))
    some_model = sorted(baseline["models"])[0]
    some_field = sorted(baseline["models"][some_model]["properties"])[0]

    removed = copy.deepcopy(baseline)
    del removed["models"][some_model]["properties"][some_field]
    retyped = copy.deepcopy(baseline)
    retyped["models"][some_model]["properties"][some_field] = {"type": "boolean"}
    required = copy.deepcopy(baseline)
    required["models"][some_model]["properties"]["planted"] = {"type": "string"}
    required["models"][some_model].setdefault("required", []).append("planted")
    optional = copy.deepcopy(baseline)
    optional["models"][some_model]["properties"]["planted"] = {"type": "string"}

    assert additive_problems(baseline, removed) == [
        f"{some_model}.{some_field}: removed"
    ]
    assert additive_problems(baseline, retyped) == [
        f"{some_model}.{some_field}: retyped"
    ]
    assert additive_problems(baseline, required) == [
        f"{some_model}.planted: added as required (a new field must be optional)"
    ]
    assert additive_problems(baseline, optional) == []
