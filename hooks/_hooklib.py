"""Shared plumbing for apex's Python hooks.

Two hooks answer the same question at two different moments — "does the thing you
are about to create already have a shape you should be using?" — so the protocol
handling, repo discovery, once-per-session bookkeeping and fail-open contract live
here rather than being copied per hook.

`hooks/` is not a package and must not become one: these files are invoked as
scripts by the harness, never imported by anything that ships. Each hook adds its
own directory to `sys.path` and imports this module by name.

**The fail-open contract is the load-bearing part.** A hook that raises, hangs, or
exits non-zero blocks the agent's tool call. Every unexpected condition here exits
0 with no output instead, because a hook that occasionally misses is vastly better
than one that occasionally blocks work.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, NoReturn


def fail_open() -> NoReturn:
    """Exit silently. Every unexpected condition lands here."""
    sys.exit(0)


def read_payload() -> dict[str, Any]:
    """The harness's hook JSON on stdin, or fail open."""
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError, OSError):
        fail_open()
    if not isinstance(payload, dict):
        fail_open()
    return payload


def emit(context: str, event: str = "PreToolUse") -> None:
    """Return `additionalContext` to the harness.

    `event` must name the hook actually firing — the harness routes on it, so a
    SessionStart hook announcing `PreToolUse` gets its context dropped on the
    floor, silently and with a zero exit code. It defaults to `PreToolUse`
    because the two original callers are both PreToolUse hooks.

    `ensure_ascii` is deliberate, not incidental: Windows still defaults stdout to
    cp1252 and this repo's prose is full of em dashes, so a non-ASCII payload would
    raise `UnicodeEncodeError` inside the hook and lose the message.
    """
    sys.stdout.write(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event,
                    "additionalContext": context,
                }
            }
        )
    )


def find_repo_root(start: Path) -> Path | None:
    """Walk up to the directory holding `.git`.

    Walking up from the *subject* — the target file, or the session cwd — rather
    than trusting a single ambient directory is what makes these hooks correct
    inside a worktree, where the session's cwd and the file's repo differ.

    `.git` is the marker rather than a build manifest because apex ships to repos
    in any language. Keying on `pyproject.toml` (or `package.json`, or any other
    ecosystem's file) would make these hooks fail open — that is, silently do
    nothing — in every repo that does not use it, which is indistinguishable from
    a healthy hook with nothing to say. A worktree's `.git` is a file, not a
    directory, so both are accepted.
    """
    try:
        candidates = [start, *start.parents]
    except (OSError, ValueError):
        return None
    for candidate in candidates:
        marker = candidate / ".git"
        try:
            if marker.is_dir() or marker.is_file():
                return candidate
        except OSError:
            continue
    return None


def relative_to_root(target: Path, root: Path) -> Path | None:
    try:
        return target.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return None


def warn_once(session_id: str, key: str) -> bool:
    """True when this (session, key) has already been warned.

    Enough to inform, not enough to nag. On any filesystem trouble this reports
    "not yet warned" — a duplicate message is a far cheaper failure than a silently
    suppressed one.
    """
    slug = "".join(c if c.isalnum() else "-" for c in f"{session_id}-{key}")[:150]
    marker = Path(tempfile.gettempdir()) / "apex-hooks" / slug
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        if marker.exists():
            return True
        marker.touch()
    except OSError:
        return False
    return False


def headings(markdown: str) -> list[str]:
    """ATX headings, normalised for comparison — '## What This Does' -> 'what this does'."""
    found = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            text = stripped.lstrip("#").strip().rstrip(":").lower()
            if text:
                found.append(text)
    return found


def run(main: "callable[[], None]") -> NoReturn:
    """Entry point wrapper: nothing escapes, nothing exits non-zero."""
    try:
        main()
    except SystemExit:
        raise
    except BaseException:  # noqa: BLE001 — fail-open is the whole contract
        os._exit(0)
    sys.exit(0)
