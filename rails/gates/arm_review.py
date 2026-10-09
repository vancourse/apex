"""Arming auto-merge outside `rails ship` needs the same review receipt (design R26; review of 1.3.0).

`rails ship` will not arm a code diff whose tree has no review receipt (``ship_review``). But
``gh pr merge <n> --auto --squash`` is the arm the merge gate allows - and recommends - so an
agent told "not arming" could arm by hand. This refuses that arm, and the GraphQL
``enablePullRequestAutoMerge`` mutation (inline, or in an ``@file`` it names), when:

* the worktree's HEAD tree is a code diff with no review, or a review with open must-fix
  items; or
* HEAD is not what the branch's remote holds: auto-merge merges the pushed head, so a
  review of an unpushed local fix approves nothing GitHub will merge.

It reads the command's words, as ``merge_by_effect`` does (``gh.exe``, ``gh -R o/r pr merge``),
so a commit message or a grep that mentions the command is not an arm. When it allows an arm
it stamps the worktree's ``pr.json`` armed, so ``turn_end`` holds the turn to the PR's steps
as it does after `rails ship`.

Scope: it judges the worktree the command runs in (one PR per line of work). A PR number from
another worktree is judged by this one's tree, and a `gh alias` hides the words - known gaps.
"""

from __future__ import annotations

from pathlib import Path

from rails import store
from rails.gates.destructive import command_name, commands
from rails.hookio import Deny, Event

NAME = "arm_review"

_MUTATION = "enablePullRequestAutoMerge"
_HTTP = ("gh", "curl", "invoke-restmethod", "invoke-webrequest", "irm", "iwr")


def _file_names_mutation(token: str, cwd: Path | None) -> bool:
    name = token.split("=", 1)[1] if "=" in token else token
    if not name.startswith("@") or len(name) < 2:
        return False
    path = Path(name[1:])
    if not path.is_absolute() and cwd is not None:
        path = cwd / path
    try:
        return _MUTATION in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _arms(tokens: list[str], cwd: Path | None) -> bool:
    name = command_name(tokens[0])
    rest = tokens[1:]
    if name == "gh":
        for i in range(len(rest) - 1):
            if rest[i] == "pr" and rest[i + 1] == "merge":
                return "--auto" in rest[i + 2 :]
    if name in _HTTP:
        return any(_MUTATION in tok or _file_names_mutation(tok, cwd) for tok in rest)
    return False


def _stamp_armed(repo: store.RepoId) -> None:
    path = repo.leaf_dir / "pr.json"
    pr = store.read_json(path, None)
    if isinstance(pr, dict):
        pr["armed"] = True
        store.write_json(path, pr)


def check(evt: Event):
    shell = evt.shell
    command = evt.command or ""
    if shell is None or ("merge" not in command and _MUTATION not in command and "@" not in command):
        return None
    try:
        arming = any(_arms(tokens, evt.cwd) for _, tokens in commands(command, shell))
    except Exception:  # noqa: BLE001 - an unparsable command is judged by text
        arming = "--auto" in command and "merge" in command
    if not arming:
        return None
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    from rails import review, ship
    from rails.gitutil import GitError, git, head, tree

    try:
        local = head(repo.top)
        remote = git(repo.top, "rev-parse", "--verify", "-q", "@{u}", check=False).strip()
        if not remote:
            br = git(repo.top, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
            remote = git(repo.top, "rev-parse", "--verify", "-q", f"origin/{br}", check=False).strip()
        if remote != local:
            return Deny(
                "rails: not arming auto-merge: HEAD is not what the branch's remote holds, and auto-merge merges "
                "the pushed head. Push first (the pre-push hook checks this tree's review), then arm."
            )
        if ship.needs_review(repo.top, None):
            problem = review.arming_problem(review.latest_for_tree(repo, tree(repo.top)))
            if problem:
                return Deny(f"rails: not arming auto-merge: {problem}")
    except (GitError, OSError):
        return None
    _stamp_armed(repo)
    return None
