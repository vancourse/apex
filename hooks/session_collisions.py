"""SessionStart hook: name the other sessions working this repo right now.

This is the one fact a session cannot learn for itself. Everything else these
hooks inject — what packages exist, which template a doc needs — is readable
from the tree. *What the other seven Claude Code windows are doing* is not: each
session sees its own cwd, its own branch, and nothing else, so two sessions can
claim the same issue, cut two branches for it, and neither notices until a human
spots it in chat.

That is not hypothetical. In one measured day, eight sessions ran against a single
repo at once, seven of them started within 22 minutes. Two independently claimed
the same work item and cut two branches for it: one branch held the finished,
fully-tested component, the other held nothing. Several more sessions edited the
same feature-doc folder from different worktrees, and the operator was
deconflicting them by hand, in prose, mid-task. The prerequisite slices those
sessions merged — all landing in *other* packages — are what moved a dependency
underneath the long-lived branch holding the real work and put it into conflict.

A convention that says "claim a work item by assigning yourself before starting"
is correct, and it is prose: it tells you to check, it cannot tell you *what the
check would have found*. This puts the answer on the table at the one moment it
changes behaviour — before the first edit.

**Advisory, never blocking**, like its two siblings. It injects context and exits
0 whatever happens; a hook that stalls session start would be far worse than one
that occasionally misses a collision.

Liveness is inferred from transcript mtime, because it is the only signal
available without the harness's cooperation: a session whose `.jsonl` was
touched inside the window is one somebody is plausibly still driving. That is a
heuristic, and it is stated as one in the output — the hook says "active
recently", never "running now".
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hooklib import emit, fail_open, find_repo_root, read_payload, run  # noqa: E402

# A transcript touched inside this window belongs to a session somebody may still
# be driving. Too short and a session that paused for a coffee vanishes; too long
# and every finished session from this morning is reported as a rival. Two hours
# is about one working block.
ACTIVE_WINDOW_SECONDS = 2 * 60 * 60

# Never report more than this many, newest first. The point is "who else is in
# here", not a census -- and on a heavy day the census is the noise.
MAX_REPORTED = 8

# Tokens that identify a claimed unit of work, harvested from branch names and
# session titles: a bare issue reference (#325) or a slice id (RS11, CO9, W8).
_ISSUE_RE = re.compile(r"(?:#|\bissue[-_ ]?)(\d{2,5})\b", re.IGNORECASE)
_SLICE_RE = re.compile(r"\b([A-Z]{1,3}\d{1,2}[a-z]?)\b")


def _config_home() -> Path:
    """Where the harness keeps `projects/`.

    `CLAUDE_CONFIG_DIR` is the harness's own override, so honouring it is both
    more correct than hardcoding `~/.claude` and what makes this hook testable
    against a synthetic transcript tree."""
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override)
    return Path.home() / ".claude"


def _slug(path: Path) -> str:
    """The harness's project-directory name for *path*: non-alphanumerics to '-'."""
    return "".join(c if c.isalnum() else "-" for c in str(path))


def _main_checkout(repo_root: Path) -> Path:
    """The primary checkout, even when called from inside a linked worktree.

    A worktree's `.git` is a file pointing at `<main>/.git/worktrees/<name>`, and
    that directory holds `commondir` pointing back at `<main>/.git`. Following
    both lands on the main checkout; anything unexpected falls back to the root
    we were given, which is correct for a normal clone."""
    marker = repo_root / ".git"
    try:
        if not marker.is_file():
            return repo_root
        pointer = marker.read_text(encoding="utf-8").strip()
        if not pointer.startswith("gitdir:"):
            return repo_root
        git_dir = Path(pointer.split(":", 1)[1].strip())
        if not git_dir.is_absolute():
            git_dir = (repo_root / git_dir).resolve()
        commondir = git_dir / "commondir"
        if not commondir.is_file():
            return repo_root
        common = Path(commondir.read_text(encoding="utf-8").strip())
        if not common.is_absolute():
            common = (git_dir / common).resolve()
        return common.parent
    except (OSError, ValueError, UnicodeDecodeError):
        return repo_root


def _project_dirs(repo_root: Path) -> list[Path]:
    """The `~/.claude/projects/<slug>` holding this repo's transcripts.

    The harness keys a project directory on the path `claude` was launched from,
    NOT on the repository -- so a session started inside
    `.claude/worktrees/<name>` gets its own directory, slugified from the
    worktree path. Scanning one directory would therefore find only the current
    session and report nothing, which is precisely the collision case this hook
    exists for: the sessions worth warning about are the ones in OTHER worktrees.

    Every one of those slugs begins with the main checkout's slug, because every
    worktree path begins with the main checkout path. So the family is found by
    prefix, from the primary checkout resolved via git's `commondir`.
    """
    home = _config_home() / "projects"
    if not home.is_dir():
        return []
    prefix = _slug(_main_checkout(repo_root))
    try:
        return sorted(
            d for d in home.iterdir() if d.is_dir() and d.name.startswith(prefix)
        )
    except OSError:
        return []


def _session_facts(transcript: Path) -> dict[str, str]:
    """Title, branch and cwd for one transcript, read from its tail.

    Only the last few KB are parsed: these files reach 10 MB, this runs on every
    session start, and the fields wanted are re-stamped on every record, so the
    tail is as authoritative as the whole and thousands of times cheaper.
    """
    facts: dict[str, str] = {}
    try:
        size = transcript.stat().st_size
        with transcript.open("rb") as handle:
            handle.seek(max(0, size - 64_000))
            blob = handle.read().decode("utf-8", errors="ignore")
    except OSError:
        return facts
    for line in reversed(blob.splitlines()):
        if not line.startswith("{"):
            continue
        try:
            record = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        for key, field in (
            ("customTitle", "title"),
            ("gitBranch", "branch"),
            ("cwd", "cwd"),
        ):
            value = record.get(key)
            if value and field not in facts:
                facts[field] = str(value)
        if len(facts) == 3:
            break
    return facts


def _current_branch(cwd: Path) -> str:
    """This session's branch, read from git's own files rather than a subprocess.

    A worktree's `.git` is a *file* holding `gitdir: <path>`, not a directory, so
    the pointer is followed before reading HEAD -- which is the whole reason this
    matters here: every session in this repo runs in a worktree, and a version
    that only handled the directory case would report no branch for all of them
    and silently never fire the branch collision.
    """
    try:
        marker = cwd / ".git"
        if marker.is_file():
            pointer = marker.read_text(encoding="utf-8").strip()
            if not pointer.startswith("gitdir:"):
                return ""
            git_dir = Path(pointer.split(":", 1)[1].strip())
            if not git_dir.is_absolute():
                git_dir = (cwd / git_dir).resolve()
        elif marker.is_dir():
            git_dir = marker
        else:
            return ""
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except (OSError, ValueError, UnicodeDecodeError):
        return ""
    if head.startswith("ref:"):
        return head.split("refs/heads/", 1)[-1].strip()
    return ""  # detached HEAD claims no branch


def _claims(*texts: str) -> set[str]:
    """Work-unit tokens mentioned in a branch name or title."""
    found: set[str] = set()
    for text in texts:
        if not text:
            continue
        found |= {f"#{n}" for n in _ISSUE_RE.findall(text)}
        found |= set(_SLICE_RE.findall(text.upper().replace("-", " ")))
    return found


def main() -> None:
    payload = read_payload()
    session_id = str(payload.get("session_id") or "")
    cwd = payload.get("cwd") or os.getcwd()

    repo_root = find_repo_root(Path(str(cwd)))
    if repo_root is None:
        fail_open()

    project_dirs = _project_dirs(repo_root)
    if not project_dirs:
        fail_open()

    transcripts: list[Path] = []
    for project_dir in project_dirs:
        try:
            transcripts += list(project_dir.glob("*.jsonl"))
        except OSError:
            continue
    if not transcripts:
        fail_open()

    # "Now" is the newest transcript rather than wall-clock: the window should
    # measure activity relative to this burst of work, so a session resumed after
    # a two-day gap still sees the siblings it was started alongside.
    try:
        now = max(p.stat().st_mtime for p in transcripts)
    except OSError:
        fail_open()

    others: list[tuple[float, dict[str, str]]] = []
    for transcript in transcripts:
        if transcript.stem == session_id:
            continue
        try:
            mtime = transcript.stat().st_mtime
        except OSError:
            continue
        if now - mtime > ACTIVE_WINDOW_SECONDS:
            continue
        facts = _session_facts(transcript)
        if facts.get("branch") or facts.get("cwd"):
            others.append((mtime, facts))

    if not others:
        fail_open()

    others.sort(key=lambda item: item[0], reverse=True)
    others = others[:MAX_REPORTED]

    my_cwd = str(cwd)
    my_branch = _current_branch(Path(my_cwd))

    lines = [
        f"Other Claude Code sessions active in this repo within the last "
        f"{ACTIVE_WINDOW_SECONDS // 3600}h ({len(others)}). Inferred from transcript "
        "activity, so treat it as 'recently active', not 'running now':",
        "",
    ]
    collisions: list[str] = []
    my_claims = _claims(my_branch, Path(my_cwd).name)
    for _mtime, facts in others:
        title = facts.get("title", "(untitled)")[:58]
        branch = facts.get("branch", "?")
        where = facts.get("cwd", "?")
        leaf = Path(where).name if where != "?" else "?"
        lines.append(f"  - {title}")
        lines.append(f"      branch {branch}   worktree {leaf}")
        if branch and branch == my_branch:
            collisions.append(f"another session is on YOUR branch ({branch})")
        if where and os.path.normcase(where) == os.path.normcase(my_cwd):
            collisions.append(f"another session is in YOUR worktree ({leaf})")
        shared = _claims(branch, facts.get("title", "")) & my_claims
        if shared:
            collisions.append(
                f"'{title}' names {', '.join(sorted(shared))}, which your worktree also names"
            )

    lines += [
        "",
        "Before you start: claim the work item you are about to pick up, however this "
        "repo records a claim (assigning yourself the issue is the usual form). If one "
        "of the sessions above is already on it, join that session rather than cutting "
        "a second branch -- two branches for one slice is how a finished component "
        "ends up stranded behind a merge conflict.",
    ]
    if collisions:
        lines.insert(0, "COLLISION: " + "; ".join(dict.fromkeys(collisions)) + "\n")

    emit("\n".join(lines), event="SessionStart")


run(main)
