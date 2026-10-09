"""UserPromptSubmit: the operator's words, and the intent ack (design R24, R22, decision 13.2).

Words, matched only on a HUMAN message whose whole first line is the word:
  hold                  pushes refuse until `release`
  release               lifts hold
  used #<milestone> <task>   records that the operator used it for a real task
  approve <rulebook> <hash>  pins a rule table's examples

The intent ack: when this worktree has an intent that was SHOWN and not yet
acked, the human message is classified. A correction clears the ack and asks
for a rewrite; anything else acks that intent's hash, and the notice names the
message so the operator can see what was taken as a yes.

Every human message also appends ``{ts, len, class}`` to the ceremony log — the
length and a class, never the text.
"""

from __future__ import annotations

import re
import time

from rails import intent, store
from rails.hookio import Event, Notice

NAME = "prompt_words"

#: `used #<number> <task>` - the `#` and the digits are required: "Used 3 hours on this, still
#: broken" recorded `used` for milestone 3, which `rails close 3` then honoured (review of 1.3.0).
_USED = re.compile(r"^\s*used\s+(#\d+)\b\s*(.*)$", re.IGNORECASE)
_APPROVE = re.compile(r"^\s*approve\s+(\S+)\s+([0-9a-f]{6,64})\s*$", re.IGNORECASE)
_CEREMONY = {
    "push": re.compile(r"\b(push|pushed|pushing)\b", re.I),
    "merge": re.compile(r"\b(merge|merged|squash)\b", re.I),
    "approve": re.compile(
        r"^\s*(yes|yep|ok|okay|go|go ahead|proceed|approved?|lgtm|sure|do it)\b[.!]*\s*$",
        re.I,
    ),
}


def _classify_ceremony(prompt: str) -> str:
    for name, rx in _CEREMONY.items():
        if rx.search(prompt):
            return name
    return "other"


def check(evt: Event):
    store.touch_heartbeat()
    repo = store.find_repo(evt.cwd)
    prompt = evt.prompt
    if repo is None or not intent.is_human(evt.payload, prompt):
        return None
    first = prompt.strip().splitlines()[0].strip() if prompt.strip() else ""
    word = first.lower().rstrip(".!")
    now = int(time.time())
    notices = []
    cls = _classify_ceremony(prompt)
    if word == "hold":
        with store.updating(repo.dir / "state.json", {}) as state:
            state["hold"] = {
                "on": True,
                "since": time.strftime("%Y-%m-%d %H:%M"),
                "by": "prompt",
            }
        notices.append(
            "rails: HOLD recorded. Every push refuses until the operator says `release`."
        )
        cls = "hold"
    elif word == "release":
        with store.updating(repo.dir / "state.json", {}) as state:
            state["hold"] = {"on": False, "since": "", "lifted": now}
        notices.append(
            "rails: hold lifted; pushes are allowed again when the check marker exists."
        )
        cls = "release"
    elif m := _USED.match(first):
        with store.updating(repo.dir / "state.json", {}) as state:
            state.setdefault("used", []).append(
                {"milestone": m.group(1), "task": m.group(2)[:200], "at": now}
            )
        notices.append(
            f"rails: recorded `used {m.group(1)}` - the operator used it for a real task."
        )
        cls = "used"
    elif m := _APPROVE.match(first):
        with store.updating(repo.dir / "state.json", {}) as state:
            state.setdefault("approved", {})[m.group(1)] = {
                "hash": m.group(2),
                "at": now,
            }
        notices.append(f"rails: rule table {m.group(1)} approved at {m.group(2)}.")
        cls = "approve-rules"
    else:
        h = intent.current_hash(repo.top)
        st = intent.get(repo)
        if (
            h
            and st.get("hash") == h
            and st.get("shown_at")
            and st.get("acked_hash") != h
        ):
            if now - int(st.get("shown_at", 0)) < 5:
                pass  # <5 s after showing: a relay or an automation, not a read
            elif intent.classify(prompt) == "changes":
                intent.update(repo, acked_hash="", acked_at=0, rewrite_requested=now)
                notices.append(
                    "rails: that message changes what is built. Rewrite .rails/intent.md before any edit, "
                    "and end the turn showing it with its new marker."
                )
                cls = "correction"
            else:
                n = int(st.get("messages", 0)) + 1
                intent.update(
                    repo,
                    acked_hash=h,
                    acked_at=now,
                    acked_by=f"message {n}",
                    messages=n,
                )
                notices.append(
                    f"rails: intent {h} acked by message {n} at {time.strftime('%H:%M')}."
                )
    try:
        store.append_jsonl(
            repo.dir / "ceremony.jsonl",
            {"ts": now, "len": len(prompt), "class": cls, "leaf": repo.leaf},
        )
    except OSError:
        pass
    return [Notice(n) for n in notices] or None
