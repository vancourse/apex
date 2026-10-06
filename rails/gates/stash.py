"""Refuse ``git stash`` in a repo whose stash stack every worktree shares.

Ported from jarvis ``.claude/hooks/stash_gate.py``. ``refs/stash`` resolves to
the **common** git dir, not the worktree's::

    $ git rev-parse --git-path refs/stash
    .git/refs/stash          # the same path from every worktree

So one stack is shared by every concurrent session — nine were live on
2026-08-19 — and a ``pop`` takes whatever is on top, which may be another
session's work. Measured the same day: a ``stash`` -> build -> ``pop`` cycle
returned *"No stash entries found"* with the content still in the tree.

**Why this is a hook and not prose.** jarvis ``CLAUDE.md`` said *"Never `git
stash` here"* in bold from 2026-08-15. On 2026-09-02 a session that had quoted
that rule verbatim into three agent prompts ran ``git stash`` four turns later.

**What is refused, and what is not.** ``list``/``show`` are read-only and pass.
Everything that pushes or consumes is denied: bare ``git stash``, ``push``,
``save``, ``pop``, ``apply``, ``drop``, ``clear``, ``branch``. The remedy is a
commit: per-branch, unreachable by a sibling session, and it survives a crash.

The PowerShell spelling is the same git command; the port matches both shells,
per statement (``rails.shell``), so a ``git stash`` on its own line after
another command is seen — the original's single-string anchor missed it.

Overrides: ``JARVIS_STASH_OK`` / ``RAILS_STASH_OK`` in the hook's own
environment (the operator's shell only), or ``# stash-ok`` in the command,
written where a reviewer sees it.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell import scrubbed_segments
from rails.shell.override import in_environment

NAME = "stash"

OVERRIDES = ("JARVIS_STASH_OK", "RAILS_STASH_OK")

#: An in-command opt-out, for the case where the stash is genuinely the tool.
_OVERRIDE = re.compile(r"#\s*stash-ok\b")

#: Subcommands that only read the stack.
_READ_ONLY = frozenset({"list", "show"})

#: `git -C <path> stash` slipped the first cut of the original pattern: it
#: allowed flags but not a flag's ARGUMENT. Caught by the planted-defect matrix.
_GIT_FLAG = (
    r"(?:-[cC]\s+\S+|--(?:git-dir|work-tree|namespace)(?:=\S+|\s+\S+)|-[^\s]+)\s+"
)
#: Anchors: start of statement, a pipe/`&`/`;`, `and`/`then`, and (new in the
#: port) an opening `(` or `{` — `(git stash)` and PowerShell `& { git stash }` —
#: plus `VAR=x` prefixes, as the sibling push gate's `_PUSH` already allowed:
#: the original let `GIT_X=1 git stash` through unmatched.
_STASH = re.compile(
    r"(?:^|[;&|({]|\b(?:and|then)\s+)\s*(?:\w+=\S*\s+)*git\s+(?:"
    + _GIT_FLAG
    + r")*stash\b([^;&|]*)"
)


def offending_stash(command: str, shell: str = "bash") -> str | None:
    """The first stash invocation that would push or consume, or ``None``.

    Quoted runs are blanked first so an echoed instruction — telling an agent
    never to stash — is not itself refused.
    """
    for _raw, scrubbed in scrubbed_segments(command, shell):
        for match in _STASH.finditer(scrubbed):
            tail = match.group(1).strip()
            first = tail.split()[0] if tail.split() else ""
            if first in _READ_ONLY:
                continue
            return match.group(0).strip()
    return None


def _reason(offender: str, shell: str) -> str:
    commit = (
        "git add -A; git commit -m 'wip'"
        if shell == "powershell"
        else "git add -A && git commit -m 'wip'"
    )
    return (
        f"`refs/stash` is shared by every worktree of this repo, so this stack is\n"
        f"not yours alone:\n"
        f"    {offender}\n\n"
        f"`git rev-parse --git-path refs/stash` resolves to the COMMON git dir, and\n"
        f"concurrent sessions run here constantly. A `pop` takes whatever is on top,\n"
        f"which may be another session's work; a measured stash->build->pop cycle\n"
        f'returned "No stash entries found" with the content still in the tree.\n\n'
        f"Commit instead — per-branch, unreachable by a sibling session, and it\n"
        f"survives a crash:\n"
        f"    {commit}\n\n"
        f"`git stash list` and `git stash show` are read-only and pass. If the stash\n"
        f"is genuinely the right tool here, append `# stash-ok` to say so where a\n"
        f"reviewer will see it."
    )


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command:
        return None
    if in_environment(*OVERRIDES):
        return None
    if _OVERRIDE.search(command):
        return None
    offender = offending_stash(command, shell)
    if offender is None:
        return None
    return Deny(_reason(offender, shell))
