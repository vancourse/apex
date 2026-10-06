"""The one store every worktree of a repo shares.

Layout, under ``~/.claude/rails/`` (``RAILS_DATA`` overrides it, for tests)::

    heartbeat                      touched by every SessionStart / prompt
    receipts.key                   HMAC key, created on first use, 0600 where possible
    <repo-key>/claims.json         claims, one row per worktree leaf
    <repo-key>/state.json          hold, used, approve, intent acks
    <repo-key>/firings.jsonl       one line per gate firing (never the command text)
    <repo-key>/<leaf>/receipts.jsonl
    <repo-key>/<leaf>/markers/check-<sha>.ok
    <repo-key>/<leaf>/evidence/    child output the agent is denied from reading

The path is resolved with ``Path.home()`` from every caller — hooks, git hooks
and the CLI — so the three can never disagree about where state lives. The
plugin data variable the harness exports is not visible to a git hook, which is
why it is not used.

The repo key and leaf are found by walking up for ``.git`` in pure Python: a
``git rev-parse`` costs 30-50 ms on this box, and hooks run on every tool call.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


def data_root() -> Path:
    override = os.environ.get("RAILS_DATA")
    return Path(override) if override else Path.home() / ".claude" / "rails"


@dataclass(frozen=True)
class RepoId:
    """A repository (its main checkout) and the worktree a call came from."""

    main: Path  # the main checkout's top level
    top: Path  # this worktree's top level
    key: str  # filesystem-safe name for `main`
    leaf: str  # the worktree directory name (the main checkout's own name for it)

    @property
    def dir(self) -> Path:
        return data_root() / self.key

    @property
    def leaf_dir(self) -> Path:
        return self.dir / self.leaf


def _key_for(path: Path) -> str:
    """The harness's directory-name encoding (non-alphanumerics to '-').

    The same encoding jarvis's claim store uses, so a repo has one name in both.
    """
    return "".join(c if c.isalnum() else "-" for c in str(path))


def find_repo(start: Path) -> RepoId | None:
    """The repo containing `start`, or None outside any git checkout.

    In a linked worktree `.git` is a file reading ``gitdir: <main>/.git/worktrees/<name>``;
    the main checkout is the parent of that ``.git`` directory.
    """
    try:
        start = start.resolve()
    except OSError:
        return None
    for candidate in [start, *start.parents]:
        dotgit = candidate / ".git"
        if dotgit.is_dir():
            return RepoId(
                main=candidate, top=candidate, key=_key_for(candidate), leaf=candidate.name
            )
        if dotgit.is_file():
            try:
                text = dotgit.read_text(encoding="utf-8", errors="replace").strip()
            except OSError:
                return None
            if not text.startswith("gitdir:"):
                return None
            gitdir = Path(text.split(":", 1)[1].strip())
            if not gitdir.is_absolute():
                gitdir = (candidate / gitdir).resolve()
            # <main>/.git/worktrees/<name>
            if (
                gitdir.parent.name == "worktrees"
                and gitdir.parent.parent.name == ".git"
            ):
                main = gitdir.parent.parent.parent
                return RepoId(
                    main=main, top=candidate, key=_key_for(main), leaf=candidate.name
                )
            return RepoId(
                main=candidate, top=candidate, key=_key_for(candidate), leaf=candidate.name
            )
    return None


# --- locking and atomic files ---------------------------------------------------


@contextlib.contextmanager
def locked(path: Path, timeout: float = 5.0) -> Iterator[None]:
    """An exclusive lock on ``<path>.lock`` shared by every process on the box.

    Uses ``msvcrt.locking`` on Windows and ``fcntl.flock`` elsewhere. On timeout
    it proceeds unlocked rather than blocking a tool call: a lost append is a
    smaller failure than a hung hook.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    handle = open(lock_path, "a+b")
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() > deadline:
                    break
                time.sleep(0.02)
        yield
    finally:
        if acquired:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        handle.close()


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    line = json.dumps(row, ensure_ascii=True, sort_keys=True) + "\n"
    with locked(path):
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(value, dict):
                    rows.append(value)
    except OSError:
        pass
    return rows


def read_json(path: Path, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, value: Any) -> None:
    """Replace `path` atomically: a partial write is a store nobody can parse."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=True, indent=1, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


@contextlib.contextmanager
def updating(path: Path, default: Any) -> Iterator[Any]:
    """Read-modify-write under the lock. Mutate the yielded value in place."""
    with locked(path):
        value = read_json(path, default)
        if value is None:
            value = default
        yield value
        write_json(path, value)


def touch_heartbeat() -> None:
    path = data_root() / "heartbeat"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(int(time.time())), encoding="ascii")
    except OSError:
        pass
