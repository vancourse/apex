"""Intent read-back (design R24): the agent shows what it will build; the operator's next words ack it.

``.rails/intent.md`` in the worktree (gitignored) holds the intent. Its marker is
``intent:<first 8 hex of sha256(text)>``. The Stop hook stamps ``shown_at`` for a
hash only when that marker appears in the LAST assistant message of the turn —
so "shown" means the operator could actually see it. The next HUMAN message is
classified: a correction clears the ack and asks for a rewrite; anything else
acks that hash (`rails.gates.prompt_words`, the only writer of ``acked_hash``).

State per leaf in ``<store>/<repo>/state.json`` under ``intent[<leaf>]``:
``{hash, shown_at, acked_hash, acked_at, acked_by}``.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

from rails import store

#: A message that changes what is built. Leading negation or an explicit redirect;
#: conservative on purpose — a misread correction costs a rewrite, a misread
#: approval costs building the wrong thing (139 operator corrections).
CORRECTION = re.compile(
    r"^\s*(?:no\b|nope\b|not\b|don'?t\b|do not\b|stop\b|wait\b|hold on\b|actually\b|instead\b|"
    r"wrong\b|that'?s not\b|but\b|hmm\b|rather\b|change\b|scratch that\b)"
    r"|\binstead of\b|\brather than\b|\bnot what i\b|\bthat'?s wrong\b|\bi meant\b|\bi said\b",
    re.IGNORECASE,
)

#: The last one is the header of a session's first prompt when another session started it: the
#: parent agent's brief, which a reminder hides until it is removed (`operator_text`). Seen as
#: the first prompt of four jarvis worktree sessions (review of 1.6.3).
MACHINE_PREFIXES = (
    "<",
    "[",
    "{",
    "Caveat:",
    "This session is being continued",
    "Background (from the session that started this one)",
)

#: Context Claude Code puts in front of an operator's words: re-read instruction files, a side
#: session reporting in. None of the reminders seen in front of a reply carried the operator's
#: words (175 reminder-led non-meta user lines in the local transcripts to 2026-10-20), so a
#: prompt is judged without them. Behind one, "go ahead and merge" started with `<` and was taken
#: for a machine message; the intent was never acked and `rails ship` refused three times (jarvis,
#: 2026-10-20).
#:
#: Only a RUN of closed blocks at the very START is removed, and only when no reminder tag is left
#: after it. The text inside a reminder can be agent-written: a background agent's result, a side
#: session's quoted report. Quoting a closing tag ends the block early and leaves agent text and
#: the real closing tag behind; quoting a closing tag and then an opening one would, if blocks
#: were removed anywhere, pair with the real tags and leave agent text standing as the operator's.
#: So a prompt with a tag left, like one whose reminder never closes (and quotes no closing tag:
#: see the known limit below), is not taken apart at all:
#: it is judged whole, as on 1.6.0, and starts with `<`. Failing open would let agent text ack
#: an intent; failing closed drops that one reply, as 1.6.0 dropped every reply behind a reminder,
#: and `prompt_words` says so (`unread_reply`).
#:
#: Known limit: a reminder that never closes but QUOTES a closing tag cannot be told from a closed
#: one followed by a reply, so what follows the quote is read as the operator's. The text alone
#: cannot show this never happens. What it shows: in the 175 non-meta user lines of the local
#: transcripts to 2026-10-20 that begin with a reminder, every closing tag starts a line, so none
#: was quoted mid-line. (Elsewhere, in tool results and assistant text, closing tags do sit
#: mid-line.)
_LEADING_REMINDER = re.compile(r"\A\s*<system-reminder>.*?</system-reminder>", re.DOTALL)
_REMINDER_TAG = re.compile(r"</?system-reminder>")


def operator_text(prompt: str) -> str:
    """The text after the closed reminders that begin the prompt, stripped, when no reminder tag
    is left after them. Otherwise the prompt itself, unchanged, to be judged as on 1.6.0."""
    text = prompt
    while match := _LEADING_REMINDER.match(text):
        text = text[match.end() :]
    if text == prompt or _REMINDER_TAG.search(text):
        return prompt
    return text.strip()


def unread_reply(payload: dict[str, Any], prompt: str) -> bool:
    """A main-session prompt that begins with a reminder `operator_text` could not take off: one
    that never closes (and quotes no closing tag), or one that leaves a tag after it. The operator
    may have written in it."""
    return (
        not payload.get("agent_id")
        and prompt.lstrip().startswith("<system-reminder>")
        and operator_text(prompt) == prompt
    )


def intent_file(top: Path) -> Path:
    return top / ".rails" / "intent.md"


def read_any(path: Path) -> str | None:
    """A text file in whatever encoding a shell wrote it; None when it cannot be read. Never raises.

    PowerShell 5.1's `>` writes UTF-16 and `Set-Content -Encoding UTF8` a BOM; the intent and
    the reviewers' reports are written by hand on this box. One decoder for every reader
    (`current_hash`, `rails ship`'s title, `rails review record`) so they cannot disagree.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def current_hash(top: Path) -> str | None:
    """The intent's marker hash, from its text in whatever encoding a shell wrote it.

    PowerShell 5.1's `>` writes UTF-16 and `Set-Content` cp1252; reading those as UTF-8
    raised, the pre-push hook's crash handler turned that into "NOT CHECKED, chaining on",
    and the push went through with no marker or leak check (review of 1.3.0). Never raise.
    Line endings are normalised: the same intent saved by an editor (CRLF) and by a tool
    (LF) is the same intent, with the same hash.
    """
    text = read_any(intent_file(top))
    if text is None or not text.strip():
        return None
    return hashlib.sha256(text.replace("\r\n", "\n").strip().encode("utf-8")).hexdigest()[:8]


def marker(h: str) -> str:
    return f"intent:{h}"


def _state(repo: store.RepoId) -> dict[str, Any]:
    state = store.read_json(repo.dir / "state.json", {}) or {}
    return state.get("intent", {}).get(repo.leaf, {}) or {}


def get(repo: store.RepoId) -> dict[str, Any]:
    return _state(repo)


def update(repo: store.RepoId, **fields: Any) -> None:
    with store.updating(repo.dir / "state.json", {}) as state:
        leafs = state.setdefault("intent", {})
        leafs.setdefault(repo.leaf, {}).update(fields)


def is_human(payload: dict[str, Any], prompt: str) -> bool:
    if payload.get("agent_id"):
        return False
    stripped = operator_text(prompt).lstrip()
    return bool(stripped) and not stripped.startswith(MACHINE_PREFIXES)


def classify(prompt: str) -> str:
    return "changes" if CORRECTION.search(prompt) else "approves"


def acked(repo: store.RepoId, top: Path) -> bool:
    h = current_hash(top)
    if h is None:
        return False
    st = _state(repo)
    return st.get("acked_hash") == h


def last_assistant_text(transcript_path: str, max_bytes: int = 400_000) -> str:
    """The text of the last assistant message in a Claude Code transcript (JSONL).

    The transcript format is internal to Claude Code; any surprise yields ''.
    """
    try:
        path = Path(transcript_path)
        size = path.stat().st_size
        with open(path, "rb") as handle:
            handle.seek(max(0, size - max_bytes))
            tail = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""
    for line in reversed(tail.splitlines()):
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or row.get("type") != "assistant":
            continue
        message = row.get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = [
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            if parts:
                return "\n".join(parts)
    return ""


def stamp_if_shown(repo: store.RepoId, top: Path, last_text: str) -> bool:
    h = current_hash(top)
    if h is None or marker(h) not in last_text:
        return False
    st = _state(repo)
    if st.get("corrected_hash") == h:
        return False  # the operator corrected this text: showing it again is not a rewrite
    if st.get("hash") != h or not st.get("shown_at"):
        update(repo, hash=h, shown_at=int(time.time()))
    return True
