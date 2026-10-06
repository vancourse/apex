"""Every shape that crosses HTTP, defined once.

    uv run python scripts/gen.py contracts

freezes these models into wire/frozen.json and generates
frontend/src/gen/types.ts and frontend/src/gen/client.ts (one function per route
of the composed root). tests/test_contracts.py fails when a generated file is
stale and when a field in wire/baseline.json was removed or retyped.

Every numeric field is owned by a concept in concepts.toml (or dated in
concepts/unowned.toml) -- tests/test_concepts.py.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from __app__ import limits

ID_PATTERN = r"^[a-z0-9_]{1,64}$"
MONTH_PATTERN = r"^[0-9]{4}-(0[1-9]|1[0-2])$"


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Health(WireModel):
    status: Literal["ok"]
    clock: Literal["wall", "pinned"]


class Me(WireModel):
    member_id: str
    household_id: str
    display_name: str


class Summary(WireModel):
    household_id: str
    month: str
    month_total_cents: int


class Entry(WireModel):
    id: str
    household_id: str
    member_id: str
    amount_cents: int
    occurred_on: date
    note: str


class EntryList(WireModel):
    household_id: str
    month: str
    entries: list[Entry]


class NewEntry(WireModel):
    amount_cents: int
    note: str = Field(default="", max_length=limits.NOTE_MAX_CHARS)


MODELS: tuple[type[WireModel], ...] = (Entry, EntryList, Health, Me, NewEntry, Summary)
