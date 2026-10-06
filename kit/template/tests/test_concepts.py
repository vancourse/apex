"""R15: one owner per concept, an independent oracle, a pinned examples table.

Fails when an examples table changed without its examples_hash, when a numeric
contract field has neither a concept row nor a dated concepts/unowned.toml row,
when an owner/oracle/pinning test named in a row does not exist, when the oracle
imports the app, and when frontend/src/gen/concepts.ts is stale.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import tomllib
import typing
from datetime import date
from typing import Any

from contracts.wire import MODELS
from scripts.gen import render_concepts, stale
from __app__.clock import WallClock
from tests.astscan import ROOT, rel

DATA = tomllib.loads((ROOT / "concepts.toml").read_text(encoding="utf-8"))
UNOWNED = tomllib.loads(
    (ROOT / "concepts" / "unowned.toml").read_text(encoding="utf-8")
).get("unowned", [])
NUMERIC = (int, float)


def examples_hash(examples: list[dict[str, Any]]) -> str:
    canonical = json.dumps(examples, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def numeric_columns() -> set[str]:
    out = set()
    for model in MODELS:
        for name, field in model.model_fields.items():
            annotation = field.annotation
            kinds = typing.get_args(annotation) or (annotation,)
            if any(k in NUMERIC and k is not bool for k in kinds):
                out.add(f"{model.__name__}.{name}")
    return out


def _resolve(target: str) -> Any:
    module, _, name = target.partition(":")
    return getattr(importlib.import_module(module), name)


def test_examples_hash_matches() -> None:
    problems = []
    for concept in DATA["concept"]:
        actual = examples_hash(concept.get("example", []))
        if concept.get("examples_hash") != actual:
            problems.append(
                f"{concept['name']}: examples_hash is {concept.get('examples_hash')}, table hashes to {actual}"
            )
    assert not problems, "an examples table changed without its hash:\n" + "\n".join(
        problems
    )


def test_every_numeric_contract_field_is_owned() -> None:
    owned = {column for c in DATA["concept"] for column in c["columns"]}
    today = WallClock().now().date()
    problems = []
    for row in UNOWNED:
        if not str(row.get("reason", "")).strip():
            problems.append(f"unowned {row.get('column')}: no reason")
        if date.fromisoformat(str(row["expires"])) < today:
            problems.append(f"unowned {row['column']}: expired {row['expires']}")
    unowned = {row["column"] for row in UNOWNED}
    numeric = numeric_columns()
    assert numeric, "no numeric contract fields found -- the scan is broken"
    problems += [
        f"{col}: numeric, but no concept owns it"
        for col in sorted(numeric - owned - unowned)
    ]
    problems += [
        f"{col}: listed, but not a numeric contract field"
        for col in sorted((owned | unowned) - numeric)
    ]
    assert not problems, "\n".join(problems)


def test_owners_oracles_and_pinning_tests_exist() -> None:
    problems = []
    for concept in DATA["concept"]:
        for key in ("owner", "oracle"):
            try:
                assert callable(_resolve(concept[key]))
            except (ImportError, AttributeError, AssertionError):
                problems.append(
                    f"{concept['name']}: {key} {concept[key]} does not resolve"
                )
        path, _, test = concept["pinning_test"].partition("::")
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
        if not any(
            isinstance(n, ast.FunctionDef) and n.name == test for n in tree.body
        ):
            problems.append(
                f"{concept['name']}: pinning test {concept['pinning_test']} not found"
            )
    assert not problems, "\n".join(problems)


def test_the_oracle_is_independent_of_the_app() -> None:
    path = ROOT / "oracle" / "checker.py"
    imported = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    app_packages = {
        p.name
        for p in (ROOT / "src").iterdir()
        if p.is_dir() and not p.name.startswith((".", "_"))
    }
    app_packages |= {"__app__", "contracts"}
    assert not imported & app_packages, (
        f"{rel(path)} imports the app: {sorted(imported & app_packages)}"
    )


def test_generated_concepts_are_current() -> None:
    drift = stale(render_concepts(ROOT))
    assert not drift, (
        f"stale: {[rel(p) for p in drift]} -- run `uv run python scripts/gen.py concepts`"
    )
