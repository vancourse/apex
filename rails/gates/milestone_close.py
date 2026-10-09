"""A milestone closes through `rails close`, never a raw API call (design R18).

`rails close N` closes milestone N only when the operator recorded ``used #N`` and no issue
is open: done is the operator using it, not the issue count reaching zero. An agent command
that PATCHes a milestone to ``state=closed`` skips both and is refused (both shells), however
it is spelled: ``gh api`` or ``curl``, a number or a variable (``milestones/$N``), ``-X PATCH``
or ``'-X','PATCH'`` inside a script one-liner, the state inline or in an ``--input`` file.

Still allowed: reading a milestone, and PATCHing its title or description (an operator
correction is written into the milestone description, and that goes through this API).
What it cannot see: a request built in a script file, or a closed state assembled at run
time. Shadow-first, like every new deny.
"""

from __future__ import annotations

import re
from pathlib import Path

from rails.hookio import Deny, Event

NAME = "milestone_close"

_MILESTONE = re.compile(r"milestones/(\d+|\$\{?\w+\}?|%\w+%)")
_PATCH = re.compile(r"PATCH", re.IGNORECASE)
_CLOSED = re.compile(r"state\W{0,6}closed\b", re.IGNORECASE)
_INPUT = re.compile(r"--input[=\s]+['\"]?([^\s'\"]+)")


def _input_closes(evt: Event, command: str) -> bool:
    for name in _INPUT.findall(command):
        if name == "-":
            continue
        path = Path(name) if Path(name).is_absolute() else evt.cwd / name
        try:
            if _CLOSED.search(path.read_text(encoding="utf-8", errors="replace")):
                return True
        except OSError:
            continue
    return False


def check(evt: Event):
    command = evt.command or ""
    m = _MILESTONE.search(command)
    if not m or not _PATCH.search(command):
        return None
    if _CLOSED.search(command) or _input_closes(evt, command):
        n = m.group(1)
        return Deny(
            f"rails: close milestone {n} with `rails close {n}` - it closes only when the operator said "
            f"`used #<n> <task>` and no issue is open. A raw PATCH to state=closed skips both."
        )
    return None
