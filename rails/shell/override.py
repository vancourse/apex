"""The escape hatches the ported gates document, matched where they can arrive.

Two forms, both kept from the jarvis originals:

* **the hook's own environment** (``os.environ``) — reachable only by whoever
  launched Claude Code, never by the agent writing the command;
* **an assignment written in front of the command**, matched as TEXT. A
  PreToolUse hook runs before the proposed command's shell exists, so
  ``JARVIS_PIPE_OK=1 pytest | tail`` never becomes a variable ``os.environ``
  can see. Checking only the environment shipped an escape hatch that could
  not fire (``detached_server_gate``, ``session_pickup_gate``).

PowerShell has no ``VAR=1 cmd`` prefix, so its form is ``$env:VAR=1; cmd`` (or
``$env:VAR = '1'``). Truthiness mirrors ``os.environ.get``: an empty value
does not open anything.

Every gate accepts its original ``JARVIS_*_OK`` name and a ``RAILS_*_OK``
alias; callers pass both.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache


@lru_cache(maxsize=64)
def _patterns(name: str) -> tuple[re.Pattern[str], re.Pattern[str]]:
    escaped = re.escape(name)
    # The originals' `\bNAME=(?:"[^"]+"|'[^']+'|\S+)`, with one fix: their bare
    # `\S+` also matched an empty quoted value (`NAME=''`), which `os.environ.get`
    # reads as falsy. A bare value may not start with a quote.
    prefix = re.compile(rf"\b{escaped}=(?:\"[^\"]+\"|'[^']+'|[^\s'\"]\S*)")
    powershell = re.compile(
        rf"\$env:{escaped}\s*=\s*(?:\"[^\"]+\"|'[^']+'|[^\s;'\"]+)", re.IGNORECASE
    )
    return prefix, powershell


def in_environment(*names: str) -> bool:
    return any(os.environ.get(name) for name in names)


def in_text(command: str, *names: str) -> bool:
    for name in names:
        prefix, powershell = _patterns(name)
        if prefix.search(command) or powershell.search(command):
            return True
    return False


def overridden(command: str, *names: str) -> bool:
    """Either form, for any of `names`."""
    return in_environment(*names) or in_text(command, *names)
