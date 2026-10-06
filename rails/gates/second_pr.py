"""Deny a second ``gh pr create`` from a worktree that already has an open PR
(design R27).

A line of work is one claim, one worktree, one branch, one PR, many commits.
"One PR per line of work" was restated by the operator 25+ times, and a
duplicate PR is not harmless: it squash-lands an EMPTY commit whose message
claims work it does not carry. ``rails ship`` records the PR it opens at
``<store>/<repo-key>/<leaf>/pr.json`` (``{"number": N, "state": ...}``); while
that record says OPEN, the next commit goes onto that PR's branch.

The escape is written where a reviewer sees it and is logged:
``# second-pr-ok: <reason>`` (a reason is required; a bare token is not
enough). A row whose override appears in more than a quarter of the sessions it
fires in is flagged ``teaches-bypass``. ``RAILS_SECOND_PR_OK`` in the hook's
own environment also allows.

Ships in SHADOW until 2026-10-13.
"""

from __future__ import annotations

import re

from rails import store
from rails.gates.destructive import command_name, commands
from rails.hookio import Deny, Event
from rails.shell.override import in_environment

NAME = "second_pr"

OVERRIDES = ("RAILS_SECOND_PR_OK",)

_OVERRIDE = re.compile(r"#\s*second-pr-ok:\s*\S")


def _creates_pr(tokens: list[str]) -> bool:
    return (
        command_name(tokens[0]) == "gh"
        and len(tokens) > 2
        and tokens[1] == "pr"
        and tokens[2] in ("create", "new")
    )


def open_pr(evt: Event) -> int | None:
    """The open PR recorded for this worktree, or None."""
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    record = store.read_json(repo.leaf_dir / "pr.json", None)
    if not isinstance(record, dict) or not record.get("number"):
        return None
    if str(record.get("state", "OPEN")).upper() != "OPEN":
        return None
    try:
        return int(record["number"])
    except (TypeError, ValueError):
        return None


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command or in_environment(*OVERRIDES) or _OVERRIDE.search(command):
        return None
    if not any(_creates_pr(tokens) for _segment, tokens in commands(command, shell)):
        return None
    number = open_pr(evt)
    if number is None:
        return None
    return Deny(
        f"This worktree already has an open pull request: #{number}.\n\n"
        f"One line of work is one PR with many commits. Commit and push to that\n"
        f"PR's branch instead (`git push`); the commit rides the same review and\n"
        f"the same armed auto-merge. A second PR for the same line squash-lands an\n"
        f"empty commit whose message claims work it does not carry.\n\n"
        f"If a second PR from this worktree is genuinely right, say why where a\n"
        f"reviewer will see it:\n"
        f"    gh pr create ...   # second-pr-ok: <reason>"
    )
