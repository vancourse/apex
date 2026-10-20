"""UserPromptSubmit: the operator's words, and the intent ack (design R24, R22, decision 13.2).

A HUMAN message is read as the operator wrote it: the harness `<system-reminder>` blocks in front
of it (re-read instructions, a side session reporting in, "Linked sessions now") are removed
first (`intent.operator_text`). A prompt with a reminder tag left anywhere after that is not
human (`intent.is_human`). It acks nothing, but `hold` in it is still honoured, its other words
are reported as not recorded, and a shown intent stops being shown (`_untrusted`).

Words, matched on a HUMAN message whose whole first line is the word (`hold` also on an
untrusted one):
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
    their words may be in it, before the first tag left or after the last one. Nothing is acked
    from it, and nothing is dropped without a word:

    - `hold` on the first line of either part is honoured. A brake set from agent text costs one
      `release`; a brake the operator set and the hook dropped lets pushes through unseen.
    - `release`, `used` or `approve` there is not recorded, and the session is told to have the
      operator say it again on its own.
    - A shown, unacked intent stops being shown, and the Stop hook asks for it again
      (`blocked_hash` cleared, as for a correction). When either part reads as a correction, it is
      voided as corrected, so showing it unchanged cannot get it acked. Otherwise it is only
      un-shown: the next reply cannot ack an intent the dropped message may have corrected.
      Either way the session is told, instead of learning it at push (the 2026-10-20 incident
      was a silent drop).
    """
    if payload.get("agent_id") or not intent.stray_reminder(prompt):
        return None
    parts = intent.around_reminders(prompt)
    firsts = [_first_word(part) for part in parts]
    notices = []
    if any(word == "hold" for _, word in firsts):
        notices.append(_record_hold(repo))
    elif any(
        word == "release" or _USED.match(first) or _APPROVE.match(first) for first, word in firsts
    ):
        notices.append(
            "rails: a message carrying a stray `<system-reminder>` tag was not read as the "
            "operator's, so its `release` / `used` / `approve` was not recorded. Ask the operator "
            "to say it again on its own."
        )
    h = intent.current_hash(repo.top)
    st = intent.get(repo)
    if h and st.get("hash") == h and st.get("shown_at") and st.get("acked_hash") != h:
        dropped = (
            f"rails: a message carrying a stray `<system-reminder>` tag did not ack intent {h}"
        )
        if any(intent.classify(part) == "changes" for part in parts):
            intent.update(
                repo, acked_hash="", acked_at=0, shown_at=0, corrected_hash=h, blocked_hash="",
                rewrite_requested=int(time.time()),
            )
            notices.append(
                f"{dropped}, and the words around the tag read as a correction: rewrite "
                ".rails/intent.md and show it again."
            )
        else:
            intent.update(repo, shown_at=0, blocked_hash="")
            notices.append(
                f"{dropped}, and may have corrected it, so it is no longer marked shown: show it "
                "again and ask for a plain reply."
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
