"""Refuse a ``git push`` onto a branch whose pull request has already MERGED.

Ported from jarvis ``.claude/hooks/merged_pr_push_gate.py``.

**The failure, measured twice in one hour on 2026-09-20.** A session opens a
PR and arms auto squash-merge. CI goes green, the arm fires, the PR merges with
the commits it had at that moment. The session, still working the same line,
pushes its next commit "onto the PR" — and the push succeeds, because the
branch still exists. The commit is now on a branch no PR watches: not on
master, not in any review, not deployed, and nothing says so. #2185 merged with
one of its four commits; #2187 was cut to carry the other three and merged
before the fourth arrived. A memory note written after the first did not
prevent the second, forty minutes later.

**What is refused.** A push whose target branch has a MERGED pull request and
no OPEN one. **What is not.** A branch with an open PR, a branch with no PR, a
branch whose PR was closed unmerged, and any push when ``gh`` cannot answer —
a gate that blocks pushes while the network is down is a worse gate than none.

The lookup is one ``gh pr list --head <branch>`` per pushed branch, bounded by
a timeout; any error, timeout or non-zero exit allows. Tests supply the table
from a JSON file instead (``RAILS_PR_LOOKUP_FIXTURE``, or the original
``JARVIS_PR_LOOKUP_FIXTURE``). Same git command in both shells; matched per
statement on the scrubbed text.

Overrides: ``JARVIS_MERGED_PUSH_OK`` / ``RAILS_MERGED_PUSH_OK`` in the hook's
own environment, or ``# merged-ok`` in the command.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from rails.hookio import Deny, Event
from rails.shell import scrubbed_segments
from rails.shell.override import in_environment

NAME = "merged_pr_push"

OVERRIDES = ("JARVIS_MERGED_PUSH_OK", "RAILS_MERGED_PUSH_OK")
FIXTURE_ENVS = ("RAILS_PR_LOOKUP_FIXTURE", "JARVIS_PR_LOOKUP_FIXTURE")

#: Seconds. The whole PreToolUse hook has 30; a slow `gh` must never eat it.
GH_TIMEOUT = 8.0
GIT_TIMEOUT = 5.0

#: An in-command opt-out, written where a reviewer sees it.
_OVERRIDE = re.compile(r"#\s*merged-ok\b")

#: `git push [flags] [remote] [refspec...]`, after any `-C <path>` on git.
_GIT_FLAG = (
    r"(?:-[cC]\s+\S+|--(?:git-dir|work-tree|namespace)(?:=\S+|\s+\S+)|-[^\s]+)\s+"
)
#: `VAR=1 git push ...` is how a push consent is spelled in bash, so an
#: env-assignment prefix is part of the shape.
_PUSH = re.compile(
    r"(?:^|[;&|]|\b(?:and|then)\s+)\s*(?:\w+=\S*\s+)*git\s+(?:"
    + _GIT_FLAG
    + r")*push\b([^;&|]*)"
)

#: Push flags that take a value, so the value is not mistaken for a refspec.
_VALUED_FLAGS = frozenset({"-o", "--push-option", "--receive-pack", "--exec", "--repo"})


def target_branches(push_args: str) -> list[str | None]:
    """The branch names a push lands on; ``None`` for "the current branch"."""
    tokens = push_args.split()
    if "--delete" in tokens or "-d" in tokens or "--tags" in tokens:
        return []
    positional: list[str] = []
    skip = False
    for tok in tokens:
        if skip:
            skip = False
            continue
        if tok in _VALUED_FLAGS:
            skip = True
            continue
        if tok.startswith("-"):
            continue
        positional.append(tok)
    refspecs = positional[1:]  # the first positional is the remote
    if not refspecs:
        return [None]
    out: list[str | None] = []
    for spec in refspecs:
        spec = spec.lstrip("+")
        if spec.startswith(":"):
            continue  # `git push origin :branch` deletes the remote branch
        if spec.startswith("refs/tags/") or ":refs/tags/" in spec:
            continue
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/") :]
        if dst:
            out.append(dst)
    return out


def current_branch(cwd: Path | None) -> str | None:
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            cwd=str(cwd) if cwd and cwd.is_dir() else None,
        )
    except Exception:  # noqa: BLE001 — fail open on anything
        return None
    name = result.stdout.strip() if result.returncode == 0 else ""
    return name or None


def pull_requests(branch: str, cwd: Path | None = None) -> list[dict] | None:
    """Every PR whose head is ``branch``, or ``None`` when nothing can answer."""
    fixture = next((os.environ[k] for k in FIXTURE_ENVS if os.environ.get(k)), None)
    if fixture:
        try:
            table = json.loads(Path(fixture).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        rows = table.get(branch) if isinstance(table, dict) else None
        return list(rows) if isinstance(rows, list) else []
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "number,state",
                "--limit",
                "20",
            ],
            capture_output=True,
            text=True,
            timeout=GH_TIMEOUT,
            cwd=str(cwd) if cwd and cwd.is_dir() else None,
        )
        if result.returncode != 0:
            return None
        rows = json.loads(result.stdout or "[]")
    except Exception:  # noqa: BLE001 — no gh, a timeout, bad JSON: allow
        return None
    return rows if isinstance(rows, list) else None


def merged_and_unwatched(rows: list[dict]) -> list[int]:
    """The merged PR numbers, when no open PR watches the branch any more."""
    states = {str(r.get("state", "")).upper(): True for r in rows}
    if "OPEN" in states:
        return []
    return [
        int(r["number"])
        for r in rows
        if str(r.get("state", "")).upper() == "MERGED" and "number" in r
    ]


def _reason(branch: str, merged: list[int]) -> str:
    numbers = ", ".join(f"#{n}" for n in merged)
    return (
        f"Branch `{branch}` belongs to a pull request that has already MERGED\n"
        f"({numbers}), and no open PR watches it. This push would succeed and\n"
        f"land on nothing: not on master, not in any review, not deployed --\n"
        f"measured twice on 2026-09-20 (#2185, #2187), each found only by\n"
        f"reading the PR after the push.\n\n"
        f"Re-cut instead:\n"
        f"    git fetch origin master\n"
        f"    git checkout -b <new-branch> origin/master\n"
        f"    git cherry-pick <the commits since the merge>\n"
        f"    git push -u origin <new-branch>   # then gh pr create\n\n"
        f"If pushing to the merged branch is the point, append `# merged-ok`."
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
    branches: list[str] = []
    for _raw, scrubbed in scrubbed_segments(command, shell):
        for match in _PUSH.finditer(scrubbed):
            for target in target_branches(match.group(1)):
                name = target if target is not None else current_branch(evt.cwd)
                if name and name not in branches:
                    branches.append(name)
    for branch in branches:
        rows = pull_requests(branch, evt.cwd)
        if rows is None:
            continue  # could not look: a gate that blocks pushes offline is worse than none
        merged = merged_and_unwatched(rows)
        if merged:
            return Deny(_reason(branch, merged))
    return None
