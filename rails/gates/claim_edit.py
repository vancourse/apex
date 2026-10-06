"""PreToolUse Edit|Write: claim before the first source edit (design R23).

Advisory for months, this rule moved unclaimed sessions only from 58% to 90%;
two sessions on one slice is how a finished component ends up stranded behind
a merge conflict. Exempt: anything outside a git checkout (the scratchpad,
memory, temp), and paths under ``.rails/``. Records the touched path for the
adhoc census. Ships in shadow (``would-deny``) for 7 days.
"""

from __future__ import annotations

from pathlib import Path

from rails import claims, store
from rails.hookio import Deny, Event

NAME = "claim_edit"


def check(evt: Event):
    paths = evt.paths()
    if not paths:
        return None
    target = Path(paths[0])
    if not target.is_absolute():
        target = evt.cwd / target
    repo = store.find_repo(target.parent if not target.is_dir() else target)
    if repo is None:
        return None
    try:
        rel = target.resolve().relative_to(repo.top.resolve()).as_posix()
    except (ValueError, OSError):
        return None
    if rel.startswith(".rails/") or rel.startswith(".git/"):
        return None
    mine = claims.mine(repo)
    if mine and mine.items:
        try:
            claims.record_paths(repo, [rel])
        except OSError:
            pass
        return None
    return Deny(
        f"rails: {repo.leaf} has no claim, and this is its first source edit ({rel}).\n"
        "Declare what this line of work holds first, so a sibling session is not building the same thing:\n"
        '    rails claim "#<issue>"            # an issue\n'
        '    rails claim --milestone "<title>" # a release\n'
        '    rails claim --adhoc "<one line>"  # an operator-directed one-off\n'
        "(`rails claim --list` shows what the other worktrees hold.)"
    )
