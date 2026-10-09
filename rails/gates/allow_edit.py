"""A subagent may not edit an allowlist file (design R2: ``*_allow.toml`` with ``agent_id``).

An allowlist row is how a gate's finding is accepted instead of fixed. Measured: 17 of 20
overrides in the evidence were self-granted, and a delegated agent told to "make the gate
pass" reaches for the allowlist first. The main session may still edit one - the operator
can see that diff and the leak/rule gates review it - but a subagent's edit to an
allowlist is refused: it should report the finding and let the session decide.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event

NAME = "allow_edit"

_ALLOWLIST = re.compile(r"(?:^|[/\\])[\w.-]*(?:_allow|allowlist)[\w.-]*\.toml$", re.IGNORECASE)


def check(evt: Event):
    if not evt.agent_id:
        return None
    hits = [p for p in evt.paths() if _ALLOWLIST.search(p)]
    if hits:
        return Deny(
            f"rails: {hits[0]} is an allowlist - a finding accepted instead of fixed. A delegated agent does not "
            "grow one: report the finding (file, line, why it is a false positive) and let the session decide."
        )
    return None
