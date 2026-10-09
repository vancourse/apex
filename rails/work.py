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


#: A Done-when / Acceptance / Demo / Steps heading - but not "Steps to reproduce", which is
#: a defect's repro, not what the fix must show (review of 1.3.0).
_ACCEPT_HEADING = re.compile(
    r"^\s*(?:#+\s*|\*\*)\s*(?:done when|acceptance(?:\s+criteria)?|demo|exit criteria|steps?(?!\s+to\s+reproduce))\b"
    r"(?:\*\*)?\s*:?\s*(?P<rest>.*)$",
    re.I,
)
_ANY_HEADING = re.compile(r"^\s*(?:#+\s+\S|\*\*[^*]+\*\*\s*:?\s*$)")
#: A ticked box is still owed: the tick is the agent's own claim, and done is a receipt
#: (review of 1.3.0 - ticking `- [x] step: a1` used to drop the item before the PR closed it).
_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s+)?(.+)$")
#: A step id is letters then a digit (a1, s2, b12): "next step: deploy" is prose, not an id.
_STEP = re.compile(r"`?\bstep:\s*`?([A-Za-z]+\d[\w-]{0,13})`?")


def acceptance_lines(body: str) -> list[tuple[str, str]]:
    """(text, step id or '') for each acceptance line of an issue body.

    An acceptance line is a line under a Done-when / Acceptance / Demo / Steps heading (a
    bullet, or a plain line as an issue form renders its box), or any line anywhere that
    names a `step: <id>`. Comments and code fences are not owed; a ticked box still is.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    in_section = False
    in_fence = False
    in_comment = False
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_comment:
            in_comment = "-->" not in stripped
            continue
        if stripped.startswith("<!--"):
            in_comment = "-->" not in stripped[4:]
            continue
        if in_fence:
            continue
        head = _ACCEPT_HEADING.match(line)
        if head:
            in_section = True
            rest = head.group("rest").strip().lstrip("*").strip()
            if not rest:
                continue
            line, stripped = rest, rest  # "**Done when** <criterion>" on one line
        elif _ANY_HEADING.match(line):
            in_section = False
        step_m = _STEP.search(line)
        bullet_m = _BULLET.match(line)
        plain = in_section and stripped and stripped != "_No response_"
        if step_m or (in_section and bullet_m) or plain:
            text = (bullet_m.group(1) if bullet_m else line).strip()
            key = text.lower()
            if text and key not in seen:
                seen.add(key)
                out.append((text[:240], step_m.group(1) if step_m else ""))
    return out


def add_from_issue(repo: store.RepoId, number: str, body: str) -> list[dict[str, Any]]:
    """One work item per acceptance line, each closing `#number`; a named step id is kept.

    The item id is ``<issue>-<step>`` (or ``<issue>-<k>``), so two issues written from the
    same template (`step: s1` in both) keep both sets; the step id stays the walk's key.
    """
    ref = f"#{number.lstrip('#')}"
    n = ref.lstrip("#")
    added = []
    for k, (text, step) in enumerate(acceptance_lines(body), start=1):
        with store.updating(path(repo), {}) as data:
            items = data.setdefault("items", [])
            if any(i.get("text") == text and i.get("closes") == ref for i in items):
                continue
            base = f"{n}-{step}" if step else f"{n}-{k}"
            ident, extra = base, 1
            while any(i["id"] == ident for i in items):  # the issue was edited: a new line, not a lost one
                extra += 1
                ident = f"{base}.{extra}"
            item = {"id": ident, "text": text, "step": step, "status": "open",
                    "added": int(time.time()), "closes": ref, "from_issue": True}
            items.append(item)
            added.append(item)
    return added
