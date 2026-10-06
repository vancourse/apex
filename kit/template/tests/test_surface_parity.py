"""R15: what the API serves equals the oracle, for every (household, month) in the corpus.

Each surface is compared with oracle/checker.py's value computed from the planted
ledger -- never surface-to-surface -- so a truncation applied everywhere still
fails. The examples tables in concepts.toml pin the oracle itself to hand-checked
numbers. These are the concepts' pinning tests.
"""

from __future__ import annotations

import tomllib
from typing import Any

from fastapi.testclient import TestClient

from oracle import checker
from __app__.db import Database
from tests.astscan import ROOT

CONCEPTS = {
    c["name"]: c
    for c in tomllib.loads((ROOT / "concepts.toml").read_text(encoding="utf-8"))[
        "concept"
    ]
}


def _token(corpus: dict[str, Any], household: str) -> str:
    return next(m["token"] for m in corpus["member"] if m["household"] == household)


def _summary(
    client: TestClient, corpus: dict[str, Any], household: str, month: str
) -> int:
    response = client.get(
        f"/api/households/{household}/summary",
        params={"month": month},
        headers={"X-Member": _token(corpus, household)},
    )
    assert response.status_code == 200, response.text
    return response.json()["month_total_cents"]


def _entries(
    client: TestClient, corpus: dict[str, Any], household: str, month: str
) -> list[dict[str, Any]]:
    response = client.get(
        f"/api/households/{household}/entries",
        params={"month": month},
        headers={"X-Member": _token(corpus, household)},
    )
    assert response.status_code == 200, response.text
    return response.json()["entries"]


def test_month_total_matches_checker(
    client: TestClient, corpus: dict[str, Any], db: Database
) -> None:
    pairs = checker.corpus_months(corpus)
    assert len(pairs) >= 4, f"the corpus covers too little to compare: {pairs}"
    straddles = [
        r
        for r in checker.rows(corpus)
        if r.local_month != r.recorded_at.strftime("%Y-%m")
    ]
    assert straddles, (
        "the corpus must hold an entry whose local month differs from its UTC month"
    )
    mismatches = []
    for household, month in pairs:
        served, expected = (
            _summary(client, corpus, household, month),
            checker.month_total(corpus, household, month),
        )
        if served != expected:
            mismatches.append(
                f"{household} {month}: served {served}, oracle {expected}"
            )
    assert not mismatches, "\n".join(mismatches) + f"\n{db.identity()}"


def test_every_planted_entry_landed(client: TestClient, corpus: dict[str, Any]) -> None:
    served = sum(
        len(_entries(client, corpus, h, m)) for h, m in checker.corpus_months(corpus)
    )
    assert served == len(corpus["entry"]), (
        f"{served} entries served, {len(corpus['entry'])} planted"
    )


def test_month_total_examples(client: TestClient, corpus: dict[str, Any]) -> None:
    examples = CONCEPTS["month_total"]["example"]
    assert examples
    for ex in examples:
        oracle = checker.month_total(corpus, ex["household"], ex["month"])
        served = _summary(client, corpus, ex["household"], ex["month"])
        assert oracle == ex["expected"], (
            f"oracle disagrees with the example: {ex} -> {oracle}"
        )
        assert served == ex["expected"], (
            f"the API disagrees with the example: {ex} -> {served}"
        )


def test_entry_amount_examples(client: TestClient, corpus: dict[str, Any]) -> None:
    examples = CONCEPTS["entry_amount"]["example"]
    assert examples
    for ex in examples:
        oracle = checker.entry_amount(corpus, ex["household"], ex["month"], ex["note"])
        served = [
            e["amount_cents"]
            for e in _entries(client, corpus, ex["household"], ex["month"])
            if e["note"] == ex["note"]
        ]
        assert oracle == ex["expected"], (
            f"oracle disagrees with the example: {ex} -> {oracle}"
        )
        assert served == [ex["expected"]], (
            f"the API disagrees with the example: {ex} -> {served}"
        )
