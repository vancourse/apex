"""A milestone closes through `rails close`, never a raw API call (design R18).

`rails close N` closes milestone N only when the operator recorded ``used #N`` and no issue
is open: done is the operator using it, not the issue count reaching zero. An agent command
that writes ``state=closed`` to a milestone skips both and is refused (both shells), however
it is spelled: ``gh api`` or ``curl``; a number or any variable (``milestones/$N``,
``milestones/"$N"``, ``milestones/$($m.number)``); ``PATCH``, or the ``POST`` GitHub accepts
for it (``gh api`` sends POST when given fields); the state inline, in an ``--input`` file,
or piped into ``--input -`` (``cat f |``, ``Get-Content f |``, ``< f``). Piping from a
source it cannot read is refused too: write the body to a file and name it.

Only a statement that writes is judged (a write method, or a body: gh's field flags and
``--input``, curl's data flags), so reads are allowed: ``-X GET``, a plain ``gh api`` with a
``--jq`` that mentions "closed", listing closed ones (``milestones?state=closed``), and a
``--state closed`` in another statement. Changing a title or description is allowed too (an operator correction is
written into the milestone description, and that goes through this API). What it cannot see:
a request built in a script file, or a closed state assembled at run time. Shadow-first, like
every new deny.
"""

from __future__ import annotations

import re
from pathlib import Path

from rails.hookio import Deny, Event

NAME = "milestone_close"

_MILESTONE = re.compile(r"milestones/(\S+)")
_GET = re.compile(r"(?:-X|--method)[=\s]+['\"]?GET\b", re.IGNORECASE)
#: A statement that writes: an explicit write method, or a body (gh's field flags and --input,
#: curl's data flags). Without one, `gh api` and curl send GET - a `--jq` that mentions
#: "closed" is a read (review of 1.3.0).
_WRITES = re.compile(
    r"(?:-X|--method|--request)[=\s]*['\"]?(?:PATCH|POST|PUT)\b|['\"](?:PATCH|POST|PUT)['\"]|"
    r"\s(?:-f|-F|--field|--raw-field|--input|-d|--data(?:-raw|-binary|-urlencode)?|--json)(?=[\s=])|"
    r"\s-[fFd]\S|-Method\s+['\"]?(?:Patch|Post|Put)\b|\s-Body\b|\.(?:patch|post|put)\s*\(|\b(?:json|data)\s*=",
    re.IGNORECASE,
)
_CLOSED = re.compile(r"state\W{0,6}closed\b", re.IGNORECASE)
_INPUT = re.compile(r"--input[=\s]+['\"]?([^\s'\"]+)")
_STDIN_SOURCE = re.compile(
    r"(?:\b(?:cat|type|Get-Content|gc)\s+['\"]?([^\s'\"|;]+)['\"]?[^|;\n]*\||<\s*['\"]?([^\s'\"|;]+))",
    re.IGNORECASE,
)


def _reads_closed(evt: Event, name: str) -> bool | None:
    path = Path(name)
    if not path.is_absolute() and evt.cwd is not None:
        path = evt.cwd / path
    try:
        return bool(_CLOSED.search(path.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return None


def _input_closes(evt: Event, command: str) -> bool:
    for name in _INPUT.findall(command):
        if name == "-":
            sources = [a or b for a, b in _STDIN_SOURCE.findall(command)]
            if not sources:
                return True  # a body from somewhere it cannot read: fail closed
            if any(_reads_closed(evt, s) is not False for s in sources):
                return True
            continue
        if _reads_closed(evt, name) is not False:  # unreadable (`$env:TEMP\\c.json`): fail closed
            return True
    return False


def _statements(evt: Event, command: str) -> list[str]:
    from rails.shell import segments

    try:
        return segments(command, evt.shell or "bash") or [command]
    except Exception:  # noqa: BLE001
        return [command]


def check(evt: Event):
    command = evt.command or ""
    if "milestones/" not in command:
        return None
    named = _MILESTONE.search(command)
    for statement in _statements(evt, command):
        # the endpoint may be a variable set in an earlier statement (`U=.../milestones/75; gh api $U`)
        m = _MILESTONE.search(statement) or named
        if not m or _GET.search(statement) or not _WRITES.search(statement):
            continue
        # a pipe feeding `--input -` lives in the same statement, so the source is found
        if not (_CLOSED.search(statement) or _input_closes(evt, statement)):
            continue
        n = m.group(1).strip("'\")")
        n = n if n.isdigit() else "<n>"
        return Deny(
            f"rails: close milestone {n} with `rails close {n}` - it closes only when the operator said "
            "`used #<n> <task>` and no issue is open. A raw API write of state=closed skips both."
        )
    return None
