"""work.json: every item a line of work promised, and what discharged it (design R28).

Lives at ``<store>/<repo>/<leaf>/work.json`` — not in the tree, so it is never
committed and an agent cannot edit it with Write/Edit (the store is denied to
tools). It changes only through ``rails work`` and ``rails ship``::

    {"items": [{"id": "a1", "text": "...", "step": "a1", "status": "open|done|unverified",
                "added": ts}],
     "stop_reason": {"kind": "decision_needed|blocked|hold|wip", "text": "..."} | null,
     "blocks": 0}

An item closes only when its ``step`` id is ``pass`` in a walk receipt. The
agent may add items, never remove them.
"""

from __future__ import annotations

import re
import time
from typing import Any

from rails import receipts, store

STOP_KINDS = ("decision_needed", "blocked", "hold", "wip")


def path(repo: store.RepoId):
    return repo.leaf_dir / "work.json"


def load(repo: store.RepoId) -> dict[str, Any]:
    data = store.read_json(path(repo), None)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("items", [])
    data.setdefault("stop_reason", None)
    data.setdefault("blocks", 0)
    return data


def save(repo: store.RepoId, data: dict[str, Any]) -> None:
    store.write_json(path(repo), data)


def add(repo: store.RepoId, text: str, step: str = "") -> dict[str, Any]:
    with store.updating(path(repo), {}) as data:
        data.setdefault("items", [])
        ident = step or f"w{len(data['items']) + 1}"
        for item in data["items"]:
            if item["id"] == ident:
                return item
        item = {
            "id": ident,
            "text": text.strip(),
            "step": step,
            "status": "open",
            "added": int(time.time()),
        }
        data["items"].append(item)
        return item


def passing_steps(repo: store.RepoId) -> set[str]:
    """Step ids that passed in a sealed walk receipt with an allowed instrument."""
    banned = ("fixture", "mock", "/dev/login", "standalone", "superuser")
    ok: set[str] = set()
    for row in receipts.read(repo, "walk"):
        if not receipts.valid(row):
            continue
        instrument = str(row.get("instrument", ""))
        if any(b in instrument for b in banned):
            continue
        for step in row.get("steps", []):
            if isinstance(step, dict) and step.get("pass"):
                ok.add(str(step.get("step")))
    return ok


def mark_done(repo: store.RepoId, ident: str) -> tuple[bool, str]:
    ok_steps = passing_steps(repo)
    with store.updating(path(repo), {}) as data:
        for item in data.get("items", []):
            if item["id"] != ident:
                continue
            if item.get("step") and item["step"] not in ok_steps:
                return False, (
                    f"{ident} names step {item['step']!r}, which has no passing walk receipt. "
                    "Run `rails walk` (or the target walk) until the step passes."
                )
            item["status"] = "done"
            return True, f"{ident} done"
    return False, f"no item {ident}"


def set_stop_reason(repo: store.RepoId, kind: str, text: str) -> tuple[bool, str]:
    if kind not in STOP_KINDS:
        return False, f"stop reason must be one of {', '.join(STOP_KINDS)}"
    if kind == "decision_needed" and not re.search(r"recommend", text, re.I):
        return (
            False,
            "a decision_needed reason carries a brief: the problem, options with costs, and the one you recommend",
        )
    with store.updating(path(repo), {}) as data:
        data["stop_reason"] = {
            "kind": kind,
            "text": text.strip(),
            "at": int(time.time()),
        }
    return True, f"stop reason recorded: {kind}"


def open_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [i for i in data.get("items", []) if i.get("status") == "open"]
