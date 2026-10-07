"""Keep the main checkout on trunk without pulling a hook out from under a live session.

Nothing moves a main checkout's branch by itself: PRs merge on GitHub, worktrees are cut
from ``origin/<trunk>``, and the main folder moved only when a session pulled it by hand.
jarvis's stopped on 2026-09-25, the day before a history rewrite made a fast-forward
impossible, and sat 97 commits behind (and on the old history) until 2026-10-06 - while
sessions started there read that stale CLAUDE.md and ran its hooks.

Moving it is not free either. A session started in the main folder keeps the hook list it
loaded, and ``$CLAUDE_PROJECT_DIR`` points at the main folder: when the 2026-10-06 update
deleted seven retired hook scripts, ``python3 <missing file>`` exited 2 and Claude Code
blocked that session's next prompt. That deletion is the hazard, so it is what this checks.

SessionStart fast-forwards the main checkout when all of these hold, and otherwise prints
one line saying which did not:

* the main checkout is on trunk's branch, with no tracked changes, and trunk is strictly
  ahead of it (a diverged branch is never moved: it may hold work, or retired history);
* the update deletes or renames nothing a running session may call: nothing under
  ``.claude/``, and no file a hook command in ``.claude/settings.json`` names through
  ``$CLAUDE_PROJECT_DIR``;
* it is at most ``MAX_AUTO`` commits (a SessionStart hook has 30 seconds).

rails 1.1.0 also waited while any other session started in the main folder had been active
in the last 2 h, and never moved the folder a session was running in. Measured the same
day, the first wait never cleared: the desktop app starts every session in the main folder
before it moves to a worktree, and 5 such sessions were active at once. Neither condition
guarded the hazard above, so 1.1.1 dropped both.

``rails sync`` fetches first and does the same by hand; ``--now`` also moves past a hook
removal and names the files, so the operator can restart the sessions started there.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from rails import history, store

MAX_AUTO = 300
MERGE_TIMEOUT = 20
_PROJECT_PATH = re.compile(r"\$\{?CLAUDE_PROJECT_DIR\}?[/\\]([^\"'\s]+)")


@dataclass
class Plan:
    act: bool
    line: str | None
    behind: int = 0


def _git(top: Path, *args: str, timeout: float = 60) -> tuple[int, str]:
    return history._git(top, *args, timeout=timeout)


def hook_paths(main: Path, rev: str) -> set[str]:
    """Repo paths the hook commands in `rev`'s .claude/settings.json run."""
    code, out = _git(main, "show", f"{rev}:.claude/settings.json")
    if code != 0:
        return set()
    try:
        hooks = json.loads(out).get("hooks", {})
    except (ValueError, AttributeError):
        return set()
    paths: set[str] = set()
    for groups in hooks.values() if isinstance(hooks, dict) else []:
        for group in groups if isinstance(groups, list) else []:
            for hook in group.get("hooks", []) if isinstance(group, dict) else []:
                for m in _PROJECT_PATH.finditer(str(hook.get("command", ""))):
                    paths.add(m.group(1).replace("\\", "/"))
    return paths


def removed_hooks(main: Path, old: str, new: str) -> list[str]:
    """Files a running session may call that the update deletes or renames away."""
    code, out = _git(main, "diff", "--name-only", "--diff-filter=DR", "--no-renames", old, new)
    if code != 0:
        return []
    named = hook_paths(main, old)
    return [p for p in out.splitlines() if p.startswith(".claude/") or p in named]


def plan(repo: store.RepoId, *, manual: bool = False, now: bool = False) -> Plan:
    main = repo.main
    base = history.trunk(main)
    if base is None:
        return Plan(False, None)
    trunk_sha = history.resolve(main, base)
    if trunk_sha is None:
        return Plan(False, None)
    branch = _git(main, "branch", "--show-current")[1]
    if branch != base.split("/", 1)[-1]:
        return Plan(False, None)  # the operator parked it elsewhere on purpose
    head = history.resolve(main, "HEAD")
    if head is None or head == trunk_sha:
        return Plan(False, None)
    behind = len(_git(main, "rev-list", f"{head}..{trunk_sha}")[1].split())
    ahead = len(_git(main, "rev-list", f"{trunk_sha}..{head}")[1].split())
    where = f"main folder ({main.name}, {branch})"
    if ahead:
        return Plan(
            False,
            f"{where} has diverged from {base}: {ahead} local-only, {behind} behind - not touched; "
            "`rails history status` / `rails doctor`",
            behind,
        )
    if not behind:
        return Plan(False, None)
    dirty = _git(main, "status", "--porcelain", "--untracked-files=no")[1]
    if dirty:
        return Plan(
            False, f"{where} is {behind} behind {base} and has uncommitted changes - not touched", behind
        )
    if not now:
        removed = removed_hooks(main, head, trunk_sha)
        if removed:
            return Plan(
                False,
                f"{where} is {behind} behind {base}; the update removes {len(removed)} hook file(s) "
                f"({', '.join(removed[:3])}) that sessions started there may still call - close them, "
                "then `rails sync --now`",
                behind,
            )
    if not manual and behind > MAX_AUTO:
        return Plan(False, f"{where} is {behind} behind {base}: too large for SessionStart - `rails sync`", behind)
    return Plan(True, None, behind)


def apply(repo: store.RepoId, p: Plan) -> str:
    base = history.trunk(repo.main) or "trunk"
    code, out = _git(
        repo.main, "merge", "--ff-only", "--quiet", base, timeout=MERGE_TIMEOUT
    )
    if code != 0:
        return f"main folder: fast-forward to {base} did not run ({out.strip()[:160] or 'git refused'})"
    return f"main folder fast-forwarded {p.behind} commit(s) to {base}"


def at_session_start(repo: store.RepoId) -> str | None:
    """The one line SessionStart prints about the main folder, after acting if it is safe."""
    try:
        p = plan(repo)
        return apply(repo, p) if p.act else p.line
    except (OSError, subprocess.SubprocessError) as exc:
        return f"main folder: not checked ({type(exc).__name__})"


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="rails sync")
    ap.add_argument(
        "--now",
        action="store_true",
        help="also when the update removes hook files (restart the sessions started there after)",
    )
    args = ap.parse_args(argv)
    repo = store.find_repo(Path.cwd())
    if repo is None:
        print("rails sync: not inside a git checkout")
        return 2
    base = history.trunk(repo.main)
    if base is None:
        print("rails sync: no trunk ref (origin/HEAD); nothing to sync to")
        return 2
    remote, _, branch = base.partition("/")
    code, out = _git(repo.main, "fetch", "-q", remote, branch, timeout=120)
    if code != 0:
        print(f"rails sync: fetch failed ({out[:200]}); local push state unknown, not moving anything")
        return 1
    p = plan(repo, manual=True, now=args.now)
    if not p.act:
        print(p.line or f"rails sync: main folder already at {base}")
        return 0 if p.line is None else 1
    removed = removed_hooks(
        repo.main, history.resolve(repo.main, "HEAD") or "HEAD", history.resolve(repo.main, base) or base
    )
    print(apply(repo, p))
    if removed:
        print(
            f"  removed hook files: {', '.join(removed[:8])} - restart sessions started in {repo.main.name}"
        )
    return 0
