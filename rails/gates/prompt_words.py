"""UserPromptSubmit: the operator's words, and the intent ack (design R24, R22, decision 13.2).

A HUMAN message is read as the operator wrote it: the harness `<system-reminder>` blocks in front
of it (re-read instructions, a side session reporting in) are removed first
(`intent.operator_text`). A prompt with a reminder tag left anywhere after that is not human
(`intent.is_human`), except that `hold` is still honoured and a shown, unacked intent is
un-shown with a notice (`_untrusted`).

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


def _record_hold(repo: store.RepoId) -> str:
    with store.updating(repo.dir / "state.json", {}) as state:
        state["hold"] = {
            "on": True,
            "since": time.strftime("%Y-%m-%d %H:%M"),
            "by": "prompt",
        }
    return "rails: HOLD recorded. Every push refuses until the operator says `release`."


def _first_word(text: str) -> tuple[str, str]:
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first, first.lower().rstrip(".!")


def _untrusted(repo: store.RepoId, payload: dict, prompt: str):
    """A prompt with a stray reminder tag is not read as the operator's (`intent.is_human`), but
    their words may be in it, before the first tag left or after the last one. So:

    - `hold` on the first line of either is honoured. A brake set from agent text costs one
      `release`; a brake the operator set and the hook dropped lets pushes through unseen.
    - A shown, unacked intent is un-shown. The message may have corrected it, and dropping a
      correction while the intent stays shown would let the next reply ack what was corrected.
      The session is told, so it shows the intent again and asks for a plain reply instead of
      learning it at push (the 2026-10-20 incident was a silent drop).
    """
    if payload.get("agent_id") or not intent.stray_reminder(prompt):
        return None
    notices = []
    if any(_first_word(part)[1] == "hold" for part in intent.around_reminders(prompt)):
        notices.append(_record_hold(repo))
    h = intent.current_hash(repo.top)
    st = intent.get(repo)
    if h and st.get("hash") == h and st.get("shown_at") and st.get("acked_hash") != h:
        intent.update(repo, shown_at=0)
        notices.append(
            f"rails: a message carrying a stray `<system-reminder>` tag was not read as the "
            f"operator's, so it did not ack intent {h}, and it may have corrected it: the intent "
            "is no longer marked shown. Show it again and ask for a plain reply."
        )
    return [Notice(n) for n in notices] or None


def check(evt: Event):
    store.touch_heartbeat()
    repo = store.find_repo(evt.cwd)
    prompt = evt.prompt
    if repo is None:
        return None
    if not intent.is_human(evt.payload, prompt):
        return _untrusted(repo, evt.payload, prompt)
    # The words, the ack and the ceremony log read what the operator wrote, never the reminder
    # the harness put in front of it (a "rather than" in a side session's report is not theirs).
    prompt = intent.operator_text(prompt)
    first, word = _first_word(prompt)
    now = int(time.time())
    notices = []
    cls = _classify_ceremony(prompt)
    if word == "hold":
        notices.append(_record_hold(repo))
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
                {"milestone": m.group(1), "task": m.group(2)[:200], "at": now, "by": "prompt"}
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
            and st.get("corrected_hash") != h
        ):
            if now - int(st.get("shown_at", 0)) < 5:
                pass  # <5 s after showing: a relay or an automation, not a read
            elif intent.classify(prompt) == "changes":
                # Void the shown state too: otherwise the operator's NEXT message ("how is it
                # going?") acked the very intent they had just corrected (review of 1.3.0).
                intent.update(
                    repo, acked_hash="", acked_at=0, shown_at=0, corrected_hash=h, blocked_hash="",
                    rewrite_requested=now,
                )
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
