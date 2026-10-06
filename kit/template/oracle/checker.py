"""The oracle: every concept in concepts.toml, recomputed from the planted ledger.

Pure Python over the corpus rows. It imports nothing from the app -- not its
SQL, not its clock helpers, not its month arithmetic (tests/test_concepts.py
asserts that) -- so a truncation the app applies everywhere still disagrees
with this, and tests/test_surface_parity.py fails.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "planted" / "corpus.toml"


@dataclass(frozen=True)
class Row:
    household: str
    member: str
    tz: str
    recorded_at: datetime
    amount_cents: int
    note: str

    @property
    def local_month(self) -> str:
        return self.recorded_at.astimezone(ZoneInfo(self.tz)).strftime("%Y-%m")


def load_corpus(path: Path = CORPUS) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def rows(corpus: dict[str, Any]) -> list[Row]:
    members = {m["id"]: m for m in corpus["member"]}
    out = []
    for e in corpus["entry"]:
        member = members[e["member"]]
        out.append(
            Row(
                household=member["household"],
                member=member["id"],
                tz=member["tz"],
                recorded_at=datetime.fromisoformat(
                    e["recorded_at"].replace("Z", "+00:00")
                ),
                amount_cents=int(e["amount_cents"]),
                note=e["note"],
            )
        )
    return out


def corpus_months(corpus: dict[str, Any]) -> list[tuple[str, str]]:
    """Every (household, month) the planted ledger has an entry in."""
    return sorted({(r.household, r.local_month) for r in rows(corpus)})


def month_total(corpus: dict[str, Any], household: str, month: str) -> int:
    return sum(
        r.amount_cents
        for r in rows(corpus)
        if r.household == household and r.local_month == month
    )


def entry_amount(corpus: dict[str, Any], household: str, month: str, note: str) -> int:
    matches = [
        r.amount_cents
        for r in rows(corpus)
        if r.household == household and r.local_month == month and r.note == note
    ]
    if len(matches) != 1:
        raise LookupError(
            f"{household} {month} {note!r}: {len(matches)} planted rows, need exactly one"
        )
    return matches[0]
