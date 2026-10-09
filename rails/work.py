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


_ACCEPT_HEADING = re.compile(r"^\s*(?:#+\s*|\*\*)\s*(done when|acceptance|demo|exit criteria|steps?)\b", re.I)
_ANY_HEADING = re.compile(r"^\s*(?:#+\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+)$")
_STEP = re.compile(r"`?step:\s*`?([A-Za-z][\w-]{0,15})`?")


def acceptance_lines(body: str) -> list[tuple[str, str]]:
    """(text, step id or '') for each acceptance line of an issue body.

    An acceptance line is a bullet under a Done-when / Acceptance / Demo / Steps heading,
    or any line anywhere that names a `step: <id>`. Most jarvis issues carry the first
    form; the rails templates write the second.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    in_section = False
    for line in body.splitlines():
        if _ACCEPT_HEADING.match(line):
            in_section = True
            continue
        if _ANY_HEADING.match(line):
            in_section = False
        step_m = _STEP.search(line)
        bullet_m = _BULLET.match(line)
        # an issue form renders its "Done when" box as a heading plus plain lines
        plain = in_section and line.strip() and line.strip() != "_No response_"
        if step_m or (in_section and bullet_m) or plain:
            text = (bullet_m.group(1) if bullet_m else line).strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                out.append((text[:240], step_m.group(1) if step_m else ""))
    return out


def add_from_issue(repo: store.RepoId, number: str, body: str) -> list[dict[str, Any]]:
    """One work item per acceptance line, each closing `#number`; a named step id is kept."""
    ref = f"#{number.lstrip('#')}"
    added = []
    for text, step in acceptance_lines(body):
        with store.updating(path(repo), {}) as data:
            items = data.setdefault("items", [])
            if any(i.get("text") == text and i.get("closes") == ref for i in items):
                continue
            ident = step or f"{ref.lstrip('#')}-{sum(1 for i in items if i.get('closes') == ref) + 1}"
            if any(i["id"] == ident for i in items):
                continue
            item = {"id": ident, "text": text, "step": step, "status": "open",
                    "added": int(time.time()), "closes": ref}
            items.append(item)
            added.append(item)
    return added
