"""A subagent may not edit an allowlist (design R2: ``*_allow.toml`` with ``agent_id``).

An allowlist row is how a gate's finding is accepted instead of fixed. Measured: 17 of 20
overrides in the evidence were self-granted, and a delegated agent told to "make the gate
pass" reaches for the allowlist first. The main session may still edit one - the operator
can see that diff - but a subagent's edit is refused: it should report the finding and let
the session decide. Covers Edit/Write/MultiEdit, and a shell command that names an
allowlist (or ``rails/leak.toml``, which holds the allowlist and the store guard's names)
and writes: a ``>``/``>>`` redirect (not ``2>``), ``tee``, ``Set-Content``/``Add-Content``/
``Out-File``, ``sed -i``/``perl -i``, ``cp``/``mv``/``Copy-Item``/``Move-Item``, ``git apply``,
or an interpreter one-liner that opens it for writing (``python -c``, ``node -e``,
``[IO.File]::Write*``). Reading one (``cat``, ``python -c "...read()"``) is not refused.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event

NAME = "allow_edit"

_ALLOWLIST = re.compile(
    r"(?:^|[/\\])(?:[\w.-]*(?:_allow|allowlist)[\w.-]*\.toml|leak\.toml)$", re.IGNORECASE
)
_IN_COMMAND = re.compile(r"[\w./\\-]*(?:_allow|allowlist)[\w.-]*\.toml|[\w./\\-]*leak\.toml", re.IGNORECASE)
_SHELL_WRITE = re.compile(
    r"(?<![0-9&>])>>?(?![&>])|\btee\b|Set-Content|Add-Content|Out-File|\bsed\b[^\n;|&]*\s-\w*i|"
    r"\bperl\b[^\n;|&]*\s-\w*i|\bmv\b|\bcp\b|Copy-Item|Move-Item|\bgit\s+apply\b",
    re.IGNORECASE,
)
_INTERPRETER_WRITE = re.compile(
    r"(?:\bpython\w*(?:\.exe)?\s+-c|\bnode\s+-e|\bruby\s+-e|\[IO\.File\]::)[^\n]*"
    r"(?:['\"][wax]\+?['\"]|\bwrite|WriteAll|AppendAll)",
    re.IGNORECASE,
)


def check(evt: Event):
    if not evt.agent_id:
        return None
    hits = [p for p in evt.paths() if _ALLOWLIST.search(p)]
    command = evt.command or ""
    if not hits and command:
        named = _IN_COMMAND.search(command)
        if named and (_SHELL_WRITE.search(command) or _INTERPRETER_WRITE.search(command)):
            hits = [named.group(0)]
    if hits:
        return Deny(
            f"rails: {hits[0]} is an allowlist (or the leak guard's config) - a finding accepted instead of fixed. "
            "A delegated agent does not change it: report the finding (file, line, why it is a false positive) and "
            "let the session decide."
        )
    return None
