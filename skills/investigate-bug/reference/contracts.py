"""The frozen per-axis adapter contract (design §A, U2 resolved via api-surface-review).

Per-axis small interfaces, NOT one uniform Adapter. Three normalized dataclasses
(NormalizedIssue / LogLine / CommitRef), one AdapterError(code, message), and two
`runtime_checkable` Protocols so S9 conformance is a mechanical `isinstance` check.
There is intentionally NO base class — an adapter is "a thing exposing this axis's
verbs with these return shapes." Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable


# ── Normalized return shapes (producer-side normalization, §A Pass 5) ─────────
@dataclass(frozen=True)
class NormalizedIssue:
    id: str
    title: str  # distinct from body; goes inside the gate's nonce fence
    body: str  # the symptom text; the diagnosis input
    labels: list[str]  # severity/risk hints (raise-only, gate P1)
    comments: list[str]  # bodies only — follow-up repro details
    url: str  # the one field the caller can't compute; the gate's PR back-link
    # Pass-1 deletions (lean by construction): no author, no created_at/updated_at.


@dataclass(frozen=True)
class LogLine:
    ts: datetime  # parsed timestamp; the window-membership oracle (S8)
    text: str  # raw line content — the diagnosis evidence
    source: str  # which file/stream — MVP-real (multi-path grep branches on it)
    # Pass-1 deletions: no severity/level, no request_id (both live in text).


@dataclass(frozen=True)
class CommitRef:
    sha: str
    subject: str  # first commit-message line
    ts: datetime
    paths: list[str]  # files touched within the queried paths — the suspect surface
    # Pass-1 deletions: no author, no full body.


@dataclass(frozen=True)
class TimeWindow:
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValueError(f"TimeWindow start {self.start} is after end {self.end}")

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts <= self.end


# ── Error shape (§A Pass 2 — human + machine, nothing else) ───────────────────
class AdapterErrorCode(str, Enum):
    NOT_FOUND = "NOT_FOUND"
    AUTH = "AUTH"  # → gate fail-closed
    RATE_LIMIT = "RATE_LIMIT"  # → gate P1 HALT (same storm that exhausts spend)
    UNAVAILABLE = "UNAVAILABLE"
    MALFORMED = "MALFORMED"


class AdapterError(Exception):
    def __init__(self, code: AdapterErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code
        self.message = message


# ── Per-axis capability Protocols (no base class; structural typing → S9) ──────
@runtime_checkable
class TrackerAdapter(Protocol):
    def fetch_issue(self, ref: str) -> NormalizedIssue: ...  # READ — P2
    # WRITE — contract verb; in MVP called only by a downstream consumer post-handoff,
    # never by investigate-bug or the gate (§A.1).
    def comment(self, ref: str, body: str) -> None: ...


@runtime_checkable
class ObservabilityAdapter(Protocol):
    # window is a REQUIRED positional (the DoS bound, §A Pass 3 — no default-unbounded).
    def query_logs(
        self, window: TimeWindow, query: str | None = None
    ) -> list[LogLine]: ...
