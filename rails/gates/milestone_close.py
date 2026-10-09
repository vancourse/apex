"""A milestone closes through `rails close`, never a raw API call (design R18).

`rails close N` closes milestone N only when the operator recorded ``used #N`` and no issue
is open: done is the operator using it, not the issue count reaching zero. A direct
``gh api repos/<o>/<r>/milestones/N -X PATCH -f state=closed`` skips both, so an agent
command shaped like that is refused (both shells). Reading a milestone stays allowed.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event

NAME = "milestone_close"

_MILESTONE = re.compile(r"milestones/(\d+)")
_PATCH = re.compile(r"(?:-X|--method)\s*=?\s*['\"]?PATCH\b", re.IGNORECASE)
_CLOSED = re.compile(r"state['\"]?\s*[=:]\s*['\"]?closed\b", re.IGNORECASE)


def check(evt: Event):
    command = evt.command or ""
    m = _MILESTONE.search(command)
    if not m or "gh" not in command:
        return None
    if _PATCH.search(command) and _CLOSED.search(command):
        return Deny(
            f"rails: close milestone {m.group(1)} with `rails close {m.group(1)}` - it closes only when the "
            f"operator said `used #{m.group(1)} <task>` and no issue is open. A raw PATCH skips both."
        )
    return None
