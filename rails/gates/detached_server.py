"""Refuse to spawn a detached ad-hoc HTTP server inside a worktree.

Ported from jarvis ``.claude/hooks/detached_server_gate.py``. The command it
stops looks like this, and six different sessions wrote some version of it::

    cd docs/status && nohup python -m http.server 8791 --bind 127.0.0.1 >/dev/null 2>&1 &
    sleep 2 && curl -s http://127.0.0.1:8791/board.html

An agent wants to look at a generated page, so it backgrounds a one-line
server, curls it once, and moves on. Nothing ever kills it.

**The cost lands on a different session, days later.** A detached server's
working directory is whichever worktree launched it, and an open CWD pins that
directory on Windows. ``git worktree remove`` then fails *non-atomically* —
deregistering the worktree and deleting files before it hits the locked one —
leaving a half-deleted orphan ``git worktree list`` cannot see. Measured
2026-08-07: one had held a directory for nine hours.

**Keyed on the shape, never the port.** The observed leak used four ports
(8791 sixteen times, plus 8911, 8792, 8772). A denial needs BOTH halves in one
statement: something that serves HTTP, and something that detaches it. A
foreground server blocks the tool call, dies with it, and is allowed.

**PowerShell** (new in the port): the detachments are ``Start-Process`` (and
``start``/``saps``) without ``-Wait``, ``Start-Job`` / ``Start-ThreadJob``, a
trailing ``&``, ``cmd /c start``, and ``Win32_Process`` ``Create`` — the one
form jarvis found survives its parent. jarvis also measured the reverse
failure: a server started with ``Start-Process``, ``&`` or ``nohup`` was reaped
part-way through a later run, so the page vanished mid-check. Either way the
server is the wrong tool. The bash path keeps the original's raw-text
statement split, so ``sh -c 'python -m http.server &'`` is still seen.

The override, as TEXT or in the hook's own environment::

    JARVIS_DETACHED_SERVER_OK=1 <your command>          # RAILS_DETACHED_SERVER_OK is an alias
    $env:JARVIS_DETACHED_SERVER_OK=1; <your command>    # PowerShell
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell import segments
from rails.shell.override import overridden

NAME = "detached_server"

OVERRIDES = ("JARVIS_DETACHED_SERVER_OK", "RAILS_DETACHED_SERVER_OK")

#: `python -m http.server` / `python3 -m http.server` / `py -m http.server`.
_HTTP_SERVER = re.compile(r"\b(?:python3?|py)\s+-m\s+http\.server\b")

#: `nohup …` — an explicit request to outlive the shell.
_NOHUP = re.compile(r"\bnohup\b")

#: A trailing `&` that backgrounds the segment; `&&` is a conjunction.
_TRAILING_AMP = re.compile(r"(?<!&)&\s*$")

#: PowerShell: the module may be split from `python` by `-ArgumentList` and
#: quotes, so only the two words are required, in order.
_PS_HTTP_SERVER = re.compile(
    r"\b(?:python3?|py)(?:\.exe)?\b.*?\bhttp\.server\b", re.IGNORECASE | re.DOTALL
)
_PS_DETACH = re.compile(
    r"^\s*(?:&\s*)?(?:Start-Process|saps|start|Start-Job|sajb|Start-ThreadJob)\b"
    r"|\bcmd(?:\.exe)?\s+/c\s+['\"]?start\b"
    r"|\bWin32_Process\b"
    r"|(?<!&)&\s*$",
    re.IGNORECASE,
)
_PS_WAIT = re.compile(r"\s-Wait\b", re.IGNORECASE)


def _segments(command: str) -> list[str]:
    """The original's split, kept for bash: on `&` (lookbehind, so the `&` stays
    with the segment it backgrounds), `;` and newlines, with `&&` protected.
    Deliberately quote-blind, so a server inside `sh -c '... &'` is seen."""
    guarded = command.replace("&&", "\x00AND\x00")
    parts = re.split(r"[\n;]|(?<=&)", guarded)
    return [p.replace("\x00AND\x00", "&&") for p in parts]


def _detached_server(command: str) -> str | None:
    for raw in _segments(command):
        segment = raw.strip()
        if not segment or not _HTTP_SERVER.search(segment):
            continue
        if _NOHUP.search(segment) or _TRAILING_AMP.search(segment):
            return " ".join(segment.split())[:160]
    return None


def _ps_detached_server(command: str) -> str | None:
    for segment in segments(command, "powershell"):
        if not _PS_HTTP_SERVER.search(segment):
            continue
        if not _PS_DETACH.search(segment):
            continue
        if re.match(r"\s*(?:&\s*)?(?:Start-Process|saps|start)\b", segment, re.I) and (
            _PS_WAIT.search(segment)
        ):
            continue  # -Wait blocks the call: nothing outlives it
        return " ".join(segment.split())[:160]
    return None


def _reason(offender: str, shell: str) -> str:
    if shell == "powershell":
        proceed = "    $env:JARVIS_DETACHED_SERVER_OK=1; <your command>   (RAILS_DETACHED_SERVER_OK also works)"
        extra = (
            "jarvis also measured the reverse on this box: a server started with "
            "Start-Process, `&` or nohup was reaped part-way through a later run, "
            "so it does not even serve reliably.\n\n"
        )
    else:
        proceed = "    JARVIS_DETACHED_SERVER_OK=1 <your command>   (RAILS_DETACHED_SERVER_OK=1 also works)"
        extra = ""
    return (
        f"This backgrounds an HTTP server that nothing will ever stop:\n"
        f"    {offender}\n\n"
        f"Its working directory becomes this worktree, and an open CWD pins the "
        f"directory. A later `git worktree remove` then fails half-way through — "
        f"deregistering the worktree and deleting files before it hits the lock — "
        f"which leaves an orphan `git worktree list` cannot see. One of these held "
        f"a directory for nine hours on 2026-08-07.\n\n"
        f"{extra}"
        f"Use a server that gets cleaned up:\n"
        f'  * preview_start with name "docs"  — serves docs/ on 5180, torn down '
        f"by the harness\n"
        f"  * bash scripts/board.sh            — the delivery board on 8765\n\n"
        f"To read one generated file you usually need no server at all: open it "
        f"with the Read tool, or send it with SendUserFile.\n\n"
        f"If a detached server really is right here:\n"
        f"{proceed}"
    )


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command:
        return None
    if overridden(command, *OVERRIDES):
        return None
    offender = (
        _ps_detached_server(command)
        if shell == "powershell"
        else _detached_server(command)
    )
    if offender is None:
        return None
    return Deny(_reason(offender, shell))
