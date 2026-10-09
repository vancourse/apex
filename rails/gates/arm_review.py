"""Arming auto-merge outside `rails ship` needs the same review receipt (design R26; review of 1.3.0).

`rails ship` will not arm a code diff whose tree has no review receipt (``ship_review``). But
``gh pr merge <n> --auto --squash`` is the arm the merge gate allows - and recommends - so an
agent told "not arming" could arm by hand. This refuses that arm, and the GraphQL
``enablePullRequestAutoMerge`` mutation (inline, in a variable set earlier in the command, in an
``@file`` or ``--input`` file, or piped into ``--input -``; a body it cannot read counts), when:

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

import re
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


_STDIN_SOURCE = re.compile(
    r"(?:\b(?:cat|type|Get-Content|gc)\s+['\"]?([^\s'\"|;]+)['\"]?[^|;\n]*\||<\s*['\"]?([^\s'\"|;<]+))",
    re.IGNORECASE,
)


def _read(name: str, cwd: Path | None) -> str | None:
    path = Path(name)
    if not path.is_absolute() and cwd is not None:
        path = cwd / path
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _graphql_arms(rest: list[str], command: str, cwd: Path | None) -> bool:
    """A GraphQL call arms when the mutation is anywhere it could come from: the command
    text (inline, or a variable set earlier in it), an ``--input`` file, or what is piped into
    ``--input -``. A body it cannot read is treated as an arm (fail closed)."""
    if _MUTATION in command or any(_file_names_mutation(tok, cwd) for tok in rest):
        return True
    for i, tok in enumerate(rest):
        if tok == "--input" and i + 1 < len(rest) or tok.startswith("--input="):
            name = rest[i + 1] if tok == "--input" else tok.split("=", 1)[1]
            if name == "-":
                sources = [a or b for a, b in _STDIN_SOURCE.findall(command)]
                texts = [_read(s, cwd) for s in sources]
                if not sources or any(t is None or _MUTATION in t for t in texts):
                    return True
            else:
                text = _read(name, cwd)
                if text is None or _MUTATION in text:
                    return True
    return False


def _arms(tokens: list[str], cwd: Path | None, command: str) -> bool:
    name = command_name(tokens[0])
    rest = tokens[1:]
    if name == "gh":
        for i in range(len(rest) - 1):
            if rest[i] == "pr" and rest[i + 1] == "merge":
                return "--auto" in rest[i + 2 :]
        if "api" in rest and "graphql" in rest:
            return _graphql_arms(rest, command, cwd)
    if name in _HTTP:
        if any(tok.rstrip("/").endswith("/graphql") for tok in rest) and _graphql_arms(rest, command, cwd):
            return True
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
    if shell is None or not any(w in command for w in ("merge", _MUTATION, "@", "graphql")):
        return None
    try:
        arming = any(_arms(tokens, evt.cwd, command) for _, tokens in commands(command, shell))
    except Exception:  # noqa: BLE001 - an unparsable command is judged by text
        arming = ("--auto" in command and "merge" in command) or "automerge" in command.lower()
    if not arming:
        return None
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    from rails import review, ship
    from rails.gitutil import GitError, git, head, tree

    try:
        local = head(repo.top)
        br = git(repo.top, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
        if br in ("", "HEAD"):
            return Deny("rails: not arming auto-merge from a detached HEAD: check out the PR's branch first.")
        # The PR's head is origin/<branch>; a branch cut from origin/master tracks that as
        # @{u}, so either one holding HEAD counts as pushed.
        pr_head = git(repo.top, "rev-parse", "--verify", "-q", f"origin/{br}", check=False).strip()
        # origin/<branch> is the PR's head when it exists; @{u} only stands in when it does not
        # (a HEAD reset to origin/master must not count as the PR's head, review of 1.3.0)
        remotes = {pr_head} if pr_head else {git(repo.top, "rev-parse", "--verify", "-q", "@{u}", check=False).strip()}
        if local not in remotes:
            return Deny(
                "rails: not arming auto-merge: HEAD is not what the branch's remote holds, and auto-merge merges "
                "the pushed head. Push first (the pre-push hook checks this tree's review), then arm."
            )
        if ship.needs_review(repo.top, None):
            problem = review.arming_problem(review.covering(repo, repo.top, "HEAD"))
            if problem:
                return Deny(f"rails: not arming auto-merge: {problem}")
    except Exception as exc:  # noqa: BLE001 - an arm it cannot check is refused, like pre-push
        return Deny(f"rails: not arming auto-merge: the review could not be checked ({type(exc).__name__})")
    _stamp_armed(repo)
    return None
