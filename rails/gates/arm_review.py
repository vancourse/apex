"""Arming auto-merge outside `rails ship` needs the same review receipt (design R26; review of 1.3.0).

`rails ship` will not arm a code diff whose tree has no review receipt (``ship_review``). But
``gh pr merge <n> --auto --squash`` is the arm the merge gate allows - and recommends - so an
agent told "not arming" could arm by hand. This refuses that command, and the GraphQL
``enablePullRequestAutoMerge`` mutation, when the worktree's HEAD tree is a code diff with no
review, or a review with open must-fix items.

Scope: it judges the worktree the command runs in (the PR is this worktree's, one PR per line
of work). A PR number from another worktree is judged by this one's tree - a known gap the
`second_pr` gate narrows.
"""

from __future__ import annotations

import re

from rails import store
from rails.hookio import Deny, Event

NAME = "arm_review"

_ARM = re.compile(r"\bgh\s+pr\s+merge\b[^\n;|&]*--auto\b|enablePullRequestAutoMerge", re.IGNORECASE)


def check(evt: Event):
    command = evt.command or ""
    if not _ARM.search(command):
        return None
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    from rails import review, ship
    from rails.gitutil import GitError, tree

    try:
        if not ship.needs_review(repo.top, None):
            return None
        problem = review.arming_problem(review.latest_for_tree(repo, tree(repo.top)))
    except (GitError, OSError):
        return None
    if problem:
        return Deny(f"rails: not arming auto-merge: {problem}")
    return None
