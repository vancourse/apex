"""Small git/gh helpers for the CLI and git hooks (never for per-call hooks: each costs a process)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


class GitError(RuntimeError):
    pass


def run(
    args: list[str],
    cwd: Path,
    *,
    check: bool = True,
    timeout: float = 60,
    input: str | None = None,
) -> str:
    try:
        proc = subprocess.run(
            args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            input=input,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitError(f"{args[0]} failed to run: {exc}") from exc
    if check and proc.returncode != 0:
        raise GitError(
            f"{' '.join(args[:3])} exited {proc.returncode}: {proc.stderr.strip()[:400]}"
        )
    return proc.stdout


def git(cwd: Path, *args: str, check: bool = True) -> str:
    return run(["git", *args], cwd, check=check).strip()


def head(cwd: Path) -> str:
    return git(cwd, "rev-parse", "HEAD")


def tree(cwd: Path, rev: str = "HEAD") -> str:
    return git(cwd, "rev-parse", f"{rev}^{{tree}}")


def toplevel(cwd: Path) -> Path:
    return Path(git(cwd, "rev-parse", "--show-toplevel"))


def branch(cwd: Path) -> str:
    return git(cwd, "branch", "--show-current", check=False)


def dirty_tracked(cwd: Path) -> list[str]:
    out = git(cwd, "status", "--porcelain", "--untracked-files=no", check=False)
    return [line[3:] for line in out.splitlines() if line.strip()]


def untracked(cwd: Path) -> list[str]:
    out = git(cwd, "status", "--porcelain", "--untracked-files=normal", check=False)
    return [line[3:] for line in out.splitlines() if line.startswith("??")]


def merge_base(cwd: Path, base: str) -> str | None:
    out = run(["git", "merge-base", "HEAD", base], cwd, check=False).strip()
    return out or None


def changed_files(cwd: Path, base_sha: str, rev: str = "HEAD") -> list[str]:
    out = git(cwd, "diff", "--name-only", "--no-renames", base_sha, rev)
    return [line for line in out.splitlines() if line.strip()]


def origin_slug(cwd: Path) -> str | None:
    """`owner/repo` from the origin remote URL (https or ssh), or None."""
    url = git(cwd, "config", "--get", "remote.origin.url", check=False)  # raw: insteadOf must not change identity
    m = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def gh_api(
    cwd: Path,
    path: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    timeout: float = 60,
) -> Any:
    """`gh api` with the body as an ASCII JSON file: no code page can touch it."""
    args = ["gh", "api", path, "--method", method]
    if payload is not None:
        args += ["--input", "-"]
    env_input = json.dumps(payload, ensure_ascii=True) if payload is not None else None
    out = run(args, cwd, timeout=timeout, input=env_input)
    return json.loads(out) if out.strip() else None


def gh(cwd: Path, *args: str, check: bool = True, timeout: float = 60) -> str:
    return run(["gh", *args], cwd, check=check, timeout=timeout)


def in_agent() -> bool:
    """True inside a Claude Code tool call (the harness exports CLAUDECODE=1)."""
    return os.environ.get("CLAUDECODE") == "1"
