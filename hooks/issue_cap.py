"""PreToolUse hook: from the second `gh issue create` of a session, say the count.

Measured on a real repo's first 33 days: **78% of the open backlog was agent-filed,
and the largest single lane was issues about triaging issues.** None of them were
wrong. Each was a real observation, filed the moment it was made, by an actor for
whom filing costs nothing — which is precisely the problem. A tracker is a queue of
work somebody intends to do, and an actor that can add to it faster than anyone can
drain it converts the tracker from a plan into a record of everything ever noticed.

So this hook does not judge whether an issue is worth filing. It reports the rate,
which is the thing the filer cannot see: each `gh issue create` looks locally
reasonable, and the twelfth one of an afternoon still looks locally reasonable.

**Silent on the first issue of a session.** One issue is a session doing its job, and
a hook that fires on correct work teaches the reader to skip past it — after which it
is not there for the twelfth either. The count is what carries the signal, so there is
nothing to say until there is a count.

**The counter lives in a temp directory, never in the repo.** A hook that writes into
the working tree makes every subsequent `git status` lie, and a `git add -A` then
commits the hook's bookkeeping into somebody's PR. `APEX_ISSUE_CAP_DIR` overrides the
location, which is how the tests drive it without touching a real session's state.

Advisory, always. It never blocks a tool call, never exits non-zero, and survives
malformed stdin — a `gh issue create` that a broken hook prevents is a strictly worse
outcome than every issue this hook was written about.
"""

from __future__ import annotations

import os
import shlex
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hooklib import (  # noqa: E402
    emit,
    fail_open,
    invocation_index,
    read_payload,
    run,
)

INVOCATION = ("gh", "issue", "create")

#: The share of one measured repo's open backlog that was agent-filed, over 33 days.
AGENT_FILED_SHARE = "78%"


def counter_dir() -> Path:
    override = os.environ.get("APEX_ISSUE_CAP_DIR")
    return Path(override) if override else Path(tempfile.gettempdir()) / "apex-hooks"


def bump(session_id: str) -> int:
    """This session's issue count including the one about to be filed.

    On any filesystem trouble this reports 1 — the count a first issue would have,
    which is the silent case. A hook that cannot read its own bookkeeping should say
    nothing rather than assert a number it did not measure.
    """
    slug = "".join(c if c.isalnum() else "-" for c in session_id)[:150]
    marker = counter_dir() / f"issue-cap-{slug}"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        try:
            count = int(marker.read_text(encoding="utf-8").strip()) + 1
        except (OSError, ValueError):
            count = 1
        marker.write_text(str(count), encoding="utf-8")
        return count
    except OSError:
        return 1


def message(count: int) -> str:
    return "\n".join(
        [
            f"ISSUE RATE — this is issue #{count} filed in this session.",
            "",
            f"Measured on a real repo's first 33 days: {AGENT_FILED_SHARE} of the open "
            "backlog was agent-filed, and the",
            "largest lane was issues about triaging issues. Every one of them was a real "
            "observation.",
            "That is what makes the rate the problem rather than any single issue — filing "
            "costs the",
            "filer nothing, and draining costs somebody else everything.",
            "",
            "The alternative, when the observation belongs to work already in flight:",
            "**put it in the PR body.** It reaches the same reader, attached to the "
            "change that",
            "produced it, and it does not outlive the moment it was true.",
            "",
            "File it as an issue if it is a demo step of a release (apex:release-loop step "
            "4) or genuine",
            "standalone work somebody will pick up. This is a count, not a refusal.",
        ]
    )


def main() -> None:
    payload = read_payload()
    if payload.get("tool_name") != "Bash":
        fail_open()

    command = str(payload.get("tool_input", {}).get("command", ""))
    if not command:
        fail_open()
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        fail_open()
    if invocation_index(tokens, INVOCATION) is None:
        fail_open()

    count = bump(str(payload.get("session_id", "nosession")))
    if count < 2:
        fail_open()
    emit(message(count))


if __name__ == "__main__":
    run(main)
