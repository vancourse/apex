"""Stop: an intent the operator never saw cannot be acked (design R24).

If ``.rails/intent.md`` exists and its hash is neither shown nor acked, the
turn's LAST assistant message must carry the marker ``intent:<hash>`` — then
``shown_at`` is stamped and the operator's next message is what acks it. If the
marker is missing, block once per hash, asking for the intent to be shown.
"""

from __future__ import annotations

from rails import intent, store
from rails.hookio import Block, Event

NAME = "intent_shown"


def check(evt: Event):
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    h = intent.current_hash(repo.top)
    last = intent.last_assistant_text(evt.transcript_path)
    if h is None or intent.marker(h) not in last:
        # A session started in the main folder shows a worktree's intent (p3i): stamp that
        # worktree, and bind the session so its next human message acks it there. The main
        # folder's own intent, if it has one, is not what this turn showed.
        other = intent.shown_elsewhere(repo, last)
        if other is not None and intent.stamp_if_shown(other, other.top, last):
            intent.bind_session(repo, str(evt.payload.get("session_id", "")), other)
            return None
    if h is None:
        return None
    st = intent.get(repo)
    if st.get("acked_hash") == h:
        return None
    if intent.stamp_if_shown(repo, repo.top, last):
        return None
    if evt.payload.get("stop_hook_active") or st.get("blocked_hash") == h:
        return None
    intent.update(repo, blocked_hash=h)
    if st.get("corrected_hash") == h:
        return Block(
            "rails: the operator corrected this intent and .rails/intent.md has not changed. Rewrite it with "
            "their correction, then end the turn showing the new text and its new marker."
        )
    return Block(
        "rails: .rails/intent.md changed and the operator has not seen it. End this turn by SHOWING it: "
        f"paste the intent block into your final message with the line `{intent.marker(h)}` so they can read it "
        "and their next message acks it (or corrects it)."
    )
