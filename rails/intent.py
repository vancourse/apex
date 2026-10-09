"""Intent read-back (design R24): the agent shows what it will build; the operator's next words ack it.

``.rails/intent.md`` in the worktree (gitignored) holds the intent. Its marker is
``intent:<first 8 hex of sha256(text)>``. The Stop hook stamps ``shown_at`` for a
hash only when that marker appears in the LAST assistant message of the turn —
so "shown" means the operator could actually see it. The next HUMAN message is
classified: a correction clears the ack and asks for a rewrite; anything else
acks that hash. ``rails: autonomous <scope>`` in a dispatch prompt acks for an
unattended session, and is counted separately.

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

MACHINE_PREFIXES = ("<", "[", "{", "Caveat:", "This session is being continued")


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
    stripped = prompt.lstrip()
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
