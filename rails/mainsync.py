"""Keep the main checkout on trunk without pulling files from under a live session.

Nothing moves a main checkout's branch by itself: PRs merge on GitHub, worktrees are cut
from ``origin/<trunk>``, and the main folder moved only when a session pulled it by hand.
jarvis's stopped on 2026-09-25, the day before a history rewrite made a fast-forward
impossible, and sat 97 commits behind (and on the old history) until 2026-10-06 - while
sessions started there read that stale CLAUDE.md and ran its hooks.

Moving it is not free either. A session started in the main folder keeps the hook list it
loaded, and ``$CLAUDE_PROJECT_DIR`` points at the main folder: when the 2026-10-06 update
deleted seven retired hook scripts, ``python3 <missing file>`` exited 2 and Claude Code
blocked that session's next prompt.

So SessionStart fast-forwards the main checkout only when every one of these holds, and
otherwise prints one line saying which did not:

* this session is not running in the main checkout itself;
* the main checkout is on trunk's branch, with no tracked changes, and trunk is strictly
  ahead of it (a diverged branch is never moved: it may hold work, or retired history);
* the update deletes or renames nothing under ``.claude/`` (a live session may call it);
* no other session started in the main folder wrote its transcript in the last
  ``ACTIVE_HOURS`` (file mtimes only; the transcript format is never read);
* it is at most ``MAX_AUTO`` commits (a SessionStart hook has 30 seconds).

``rails sync`` fetches first and does the same by hand; ``--now`` drops the last three
conditions and names the hook files the update removes, so the operator can restart.
"""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from rails import history, store

ACTIVE_HOURS = 2
MAX_AUTO = 300
MERGE_TIMEOUT = 20


@dataclass
class Plan:
    act: bool
    line: str | None
    behind: int = 0


def _git(top: Path, *args: str, timeout: float = 60) -> tuple[int, str]:
    return history._git(top, *args, timeout=timeout)


def _transcripts(main: Path) -> Path:
    root = os.environ.get("CLAUDE_CONFIG_DIR") or str(Path.home() / ".claude")
    return Path(root) / "projects" / store._key_for(main)


def other_sessions(main: Path, session_id: str, hours: float = ACTIVE_HOURS) -> int:
    """Sessions rooted in the main folder that wrote their transcript recently (not this one)."""
    folder = _transcripts(main)
    since = time.time() - hours * 3600
    count = 0
    try:
        for path in folder.glob("*.jsonl"):
            if session_id and path.stem.startswith(session_id):
                continue
            try:
                if path.stat().st_mtime >= since:
                    count += 1
            except OSError:
                continue
    except OSError:
        return 0
    return count


def removed_under_claude(main: Path, old: str, new: str) -> list[str]:
    code, out = _git(main, "diff", "--name-only", "--diff-filter=DR", old, new, "--", ".claude")
    return out.splitlines() if code == 0 else []


def plan(
    repo: store.RepoId, session_id: str = "", *, manual: bool = False, now: bool = False
) -> Plan:
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
    if not manual and repo.top.resolve() == main.resolve():
        return Plan(
            False,
            f"{where} is {behind} behind {base}; this session runs in it, so it is not moved under you "
            "(`rails sync` from a worktree, or from your shell)",
            behind,
        )
    if now:
        return Plan(True, None, behind)
    removed = removed_under_claude(main, head, trunk_sha)
    if removed:
        return Plan(
            False,
            f"{where} is {behind} behind {base}; the update removes {len(removed)} file(s) under .claude/ "
            "that open sessions may still call - close sessions started there, then `rails sync --now`",
            behind,
        )
    others = other_sessions(main, session_id)
    if others:
        return Plan(
            False,
            f"{where} is {behind} behind {base}; {others} other session(s) started there were active in "
            f"the last {ACTIVE_HOURS} h - `rails sync` once they are idle",
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


def at_session_start(repo: store.RepoId, session_id: str) -> str | None:
    """The one line SessionStart prints about the main folder, after acting if it is safe."""
    try:
        p = plan(repo, session_id)
        return apply(repo, p) if p.act else p.line
    except (OSError, subprocess.SubprocessError) as exc:
        return f"main folder: not checked ({type(exc).__name__})"


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="rails sync")
    ap.add_argument(
        "--now",
        action="store_true",
        help="also when other sessions are active there or hook files go away (restart them after)",
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
    p = plan(repo, "", manual=True, now=args.now)
    if not p.act:
        print(p.line or f"rails sync: main folder already at {base}")
        return 0 if p.line is None else 1
    removed = removed_under_claude(
        repo.main, history.resolve(repo.main, "HEAD") or "HEAD", history.resolve(repo.main, base) or base
    )
    print(apply(repo, p))
    if removed:
        print(
            f"  removed under .claude/: {', '.join(removed[:8])} - restart sessions started in {repo.main.name}"
        )
    return 0
