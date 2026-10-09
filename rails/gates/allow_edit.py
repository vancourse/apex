"""A subagent may not edit an allowlist (design R2: ``*_allow.toml`` with ``agent_id``).

An allowlist row is how a gate's finding is accepted instead of fixed. Measured: 17 of 20
overrides in the evidence were self-granted, and a delegated agent told to "make the gate
pass" reaches for the allowlist first. The main session may still edit one - the operator
can see that diff - but a subagent's edit is refused: it should report the finding and let
the session decide. Covers Edit/Write/MultiEdit and a shell write (``>``, ``>>``, ``tee``,
``Set-Content``, ``Add-Content``, ``Out-File``, ``sed -i``) to an allowlist, and to
``rails/leak.toml``, which names the allowlist and the store guard's names (review of 1.3.0).
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event

NAME = "allow_edit"

_ALLOWLIST = re.compile(
    r"(?:^|[/\\])(?:[\w.-]*(?:_allow|allowlist)[\w.-]*\.toml|leak\.toml)$", re.IGNORECASE
)
_IN_COMMAND = re.compile(r"[\w./\\-]*(?:_allow|allowlist)[\w.-]*\.toml|[\w./\\-]*leak\.toml", re.IGNORECASE)
_WRITE_OP = re.compile(r">>?|\btee\b|Set-Content|Add-Content|Out-File|\bsed\s+-i|\bmv\b|\bcp\b|Copy-Item|Move-Item", re.IGNORECASE)


def check(evt: Event):
    if not evt.agent_id:
        return None
    hits = [p for p in evt.paths() if _ALLOWLIST.search(p)]
    command = evt.command or ""
    if not hits and command and _IN_COMMAND.search(command) and _WRITE_OP.search(command):
        hits = [_IN_COMMAND.search(command).group(0)]
    if hits:
        return Deny(
            f"rails: {hits[0]} is an allowlist (or the leak guard's config) - a finding accepted instead of fixed. "
            "A delegated agent does not change it: report the finding (file, line, why it is a false positive) and "
            "let the session decide."
        )
    return None
