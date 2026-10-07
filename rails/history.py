"""Retired history: commits a repository rewrote away never go back out.

A history rewrite (jarvis rewrote master on 2026-09-26 to scrub household values) leaves
the old commits alive in every clone and worktree cut before it. Measured on 2026-10-06:
24 of 60 jarvis worktrees and the main checkout were still on the old history, and
``git push --dry-run origin <old tip>:refs/heads/x`` exited 0. Nothing refused it: the
leak check reads only added lines from the merge base, and an old worktree's tree
predates rails itself.

So the record lives in the repository's SHARED git config, read by the plugin's pre-push
hook in every worktree, whatever that worktree's tree holds::

    rails history retire <tip>      # git config --add rails.retiredHistory <full sha>

A commit is retired when it is reachable from a retired tip and not from trunk. A pushed
commit carries retired history exactly when some merge base of (pushed, tip) is retired:
any retired commit X in the push is a common ancestor of both, so a best common ancestor
M sits on top of X, and M reachable from trunk would make X reachable from trunk too.
Pre-rewrite ancestors that the rewrite kept (reachable from trunk) are not retired, so a
branch that merely shares them passes.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_TIPS = "rails.retiredHistory"
CONFIG_TRUNK = "rails.trunk"


def _git(top: Path, *args: str, timeout: float = 60) -> tuple[int, str]:
    try:
        done = subprocess.run(
            ["git", "-C", str(top), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 128, str(exc)
    return done.returncode, done.stdout.strip()


def tips(top: Path) -> list[str]:
    code, out = _git(top, "config", "--get-all", CONFIG_TIPS)
    return [line.strip() for line in out.splitlines() if line.strip()] if code == 0 else []


def trunk(top: Path) -> str | None:
    """`rails.trunk`, else what origin/HEAD names, else origin/main or origin/master."""
    code, out = _git(top, "config", "--get", CONFIG_TRUNK)
    if code == 0 and out:
        return out
    code, out = _git(top, "symbolic-ref", "-q", "refs/remotes/origin/HEAD")
    if code == 0 and out:
        return out.removeprefix("refs/remotes/")
    for candidate in ("origin/main", "origin/master"):
        if _git(top, "rev-parse", "-q", "--verify", f"refs/remotes/{candidate}")[0] == 0:
            return candidate
    return None


def resolve(top: Path, rev: str) -> str | None:
    code, out = _git(top, "rev-parse", "-q", "--verify", f"{rev}^{{commit}}")
    return out if code == 0 and out else None


def is_ancestor(top: Path, older: str, newer: str) -> bool:
    return _git(top, "merge-base", "--is-ancestor", older, newer)[0] == 0


@dataclass
class Retired:
    """The retired set of one repository: reachable from a tip, not from trunk."""

    top: Path
    tips: list[str]
    trunk: str | None
    problems: list[str] = field(default_factory=list)
    _commits: set[str] | None = None

    @property
    def commits(self) -> set[str]:
        if self._commits is None:
            code, out = _git(self.top, "rev-list", *self.tips, "--not", self.trunk or "")
            if code != 0:
                self.problems.append(f"git rev-list over the retired tips failed: {out[:200]}")
                self._commits = set()
            else:
                self._commits = set(out.split())
        return self._commits

    def carried_by(self, sha: str) -> str | None:
        """The retired commit `sha` is built on (a merge base), or None if it carries none."""
        if sha in self.commits:
            return sha
        for tip in self.tips:
            code, out = _git(self.top, "merge-base", "--all", sha, tip)
            if code not in (0, 1):  # 1 = no common ancestor, which is clean
                self.problems.append(f"git merge-base {sha[:12]} {tip[:12]} failed: {out[:200]}")
                continue
            for base in out.split():
                if base in self.commits:
                    return base
        return None


def load(top: Path) -> Retired | None:
    """The repo's retired set, or None when it has retired nothing (the common case)."""
    found = tips(top)
    if not found:
        return None
    base = trunk(top)
    retired = Retired(top=top, tips=[], trunk=base)
    if base is None or resolve(top, base) is None:
        retired.problems.append(
            f"no trunk to measure retired history against (set `git config {CONFIG_TRUNK} origin/<default>`)"
        )
    for tip in found:
        if resolve(top, tip) is None:
            retired.problems.append(
                f"retired tip {tip[:12]} is not in this clone; keep a ref on it (e.g. a local branch) or remove the row"
            )
        else:
            retired.tips.append(tip)
    return retired


def refusal(retired: Retired, ref_line: str) -> str | None:
    """Why a pre-push ref line must be refused, or None. Fails closed when it cannot tell."""
    parts = ref_line.split()
    if len(parts) != 4 or parts[1] == "0" * 40:
        return None
    local_sha, remote_ref = parts[1], parts[2]
    if retired.problems:
        return (
            f"rails: refused - could not check {remote_ref} for retired history: {retired.problems[0]}"
        )
    base = retired.carried_by(local_sha)
    if retired.problems:
        return (
            f"rails: refused - could not check {remote_ref} for retired history: {retired.problems[0]}"
        )
    if base is None:
        return None
    return (
        f"rails: refused - {remote_ref} carries history this repository rewrote away "
        f"(it is built on {base[:12]}, which {retired.trunk} no longer contains).\n"
        f"  Pushing it would publish what the rewrite removed. Start a fresh worktree from {retired.trunk} "
        f"and cherry-pick only your own commits onto it."
    )


def worktrees(top: Path) -> list[tuple[Path, str, str]]:
    """(path, branch or '(detached)', head sha) for every worktree of the repo."""
    code, out = _git(top, "worktree", "list", "--porcelain")
    if code != 0:
        return []
    rows: list[tuple[Path, str, str]] = []
    path: Path | None = None
    head = ""
    branch = "(detached)"
    for line in [*out.splitlines(), ""]:
        if line.startswith("worktree "):
            path, head, branch = Path(line[9:]), "", "(detached)"
        elif line.startswith("HEAD "):
            head = line[5:]
        elif line.startswith("branch "):
            branch = line[7:].removeprefix("refs/heads/")
        elif not line and path is not None:
            if head:
                rows.append((path, branch, head))
            path = None
    return rows


def carriers(retired: Retired) -> list[tuple[Path, str, str]]:
    """Every worktree whose HEAD carries retired history."""
    return [(p, b, h) for p, b, h in worktrees(retired.top) if retired.carried_by(h)]


def retire(top: Path, rev: str, trunk_ref: str | None = None) -> tuple[int, str]:
    """Record `rev` as a retired tip in the shared config. Refuses a tip trunk contains."""
    sha = resolve(top, rev)
    if sha is None:
        return 2, f"rails history: {rev!r} is not a commit in this clone"
    base = trunk_ref or trunk(top)
    if base is None or resolve(top, base) is None:
        return 2, "rails history: no trunk ref found; pass --trunk origin/<default>"
    if is_ancestor(top, sha, base):
        return 2, (
            f"rails history: {sha[:12]} is on {base}; retiring it would refuse every push. "
            "Retire the tip of the OLD history (e.g. the pre-rewrite branch head)."
        )
    if sha in tips(top):
        return 0, f"rails history: {sha[:12]} is already retired"
    code, out = _git(top, "config", "--add", CONFIG_TIPS, sha)
    if code != 0:
        return 1, f"rails history: git config failed: {out[:200]}"
    if trunk_ref or _git(top, "config", "--get", CONFIG_TRUNK)[0] != 0:
        _git(top, "config", CONFIG_TRUNK, base)
    count = len(_git(top, "rev-list", sha, "--not", base)[1].split())
    return 0, (
        f"rails history: retired {sha[:12]} ({count} commits not on {base}); "
        "every worktree's pre-push now refuses a branch built on them"
    )


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="rails history")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("retire", help="record the tip of rewritten-away history")
    r.add_argument("rev")
    r.add_argument("--trunk", default=None, help="the rewritten trunk (default: origin/HEAD)")
    sub.add_parser("status", help="retired tips and the worktrees that carry them")
    args = ap.parse_args(argv)
    top = Path.cwd()
    if args.cmd == "retire":
        code, text = retire(top, args.rev, args.trunk)
        print(text)
        return code
    retired = load(top)
    if retired is None:
        print("rails history: nothing retired in this repository")
        return 0
    print(f"rails history: {len(retired.tips)} retired tip(s) against {retired.trunk}")
    for problem in retired.problems:
        print(f"  PROBLEM: {problem}")
    if retired.problems:
        return 1
    print(f"  retired commits: {len(retired.commits)}")
    found = carriers(retired)
    print(f"  worktrees carrying retired history: {len(found)}")
    for path, branch, head in found:
        print(f"    {path.name}  {branch}  {head[:12]}")
    return 0
