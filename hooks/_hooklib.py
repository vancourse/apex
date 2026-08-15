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

import hashlib
import json
import os
import shlex
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


def command_key(command: str) -> str:
    """A stable `warn_once` key for one shell command.

    `hash()` is the obvious thing to reach for and it is wrong here. Python salts
    string hashing per interpreter process, and every hook invocation IS a new
    process — so a key built from `hash(command)` differs on every call, the marker
    file is never found again, and the once-per-command muting silently does nothing.
    It looks like it works because the observable symptom is a hook that speaks, which
    is also what a hook with something new to say looks like.
    """
    return hashlib.sha256(command.encode("utf-8", "replace")).hexdigest()[:16]


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


def plugin_root() -> Path:
    """apex's own directory. `hooks/` sits directly under it.

    `CLAUDE_PLUGIN_ROOT` is what the harness sets, so it wins; deriving from
    `__file__` is the fallback that keeps the hooks working when they are run
    directly, which is how the tests drive them.
    """
    override = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent


def invocation_index(tokens: list[str], invocation: tuple[str, ...]) -> int | None:
    """Where `gh <sub> <verb>` is actually *invoked*, as consecutive exact tokens.

    A substring match over the raw command is not good enough. The first version of
    this used one, and fired on a `git commit` whose message merely *mentioned*
    `gh issue create` — then read that commit's `-F -` as a body flag and reported
    every section missing. Tokenising and requiring exact, consecutive tokens keeps
    quoted prose (``"`gh issue create`,"`` tokenises with the backticks attached)
    from being mistaken for a command.
    """
    span = len(invocation)
    for index in range(len(tokens) - span + 1):
        if tuple(tokens[index : index + span]) == invocation:
            return index
    return None


def flag_values(tokens: list[str], start: int, names: tuple[str, ...]) -> list[str]:
    """Every value given for `names`, honouring `--flag v`, `--flag=v` and repeats."""
    values = []
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token in names and index + 1 < len(tokens):
            values.append(tokens[index + 1])
        else:
            for name in names:
                if name.startswith("--") and token.startswith(f"{name}="):
                    values.append(token.split("=", 1)[1])
    return values


def submitted_body(command: str, root: Path, start: int = 0) -> tuple[str, str] | None:
    """What is being submitted as the body: `(kind, value)`, or None if no body flag.

    `kind` is one of:

    * ``"text"``       — the body itself, read inline or from a file we could open.
    * ``"unreadable"`` — a `--body-file` we could not open; `value` is the path.

    That distinction is load-bearing. A hook sees the command *before* the shell
    expands it, so `--body-file "$SP/body.md"` arrives with `$SP` unexpanded and
    cannot be read. Collapsing that into an empty body made every section look
    absent and produced a confident, totally wrong "you are missing all 7 sections"
    — a false positive that trains the reader to ignore the check, which is worse
    than not checking at all.
    """
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None
    for index, token in enumerate(tokens):
        value = None
        if index < start:
            # A body flag before the gh invocation belongs to some other command —
            # `git commit -F -` is not submitting a PR body.
            continue
        if token in ("--body", "-b", "--body-file", "-F") and index + 1 < len(tokens):
            value = tokens[index + 1]
        elif token.startswith(("--body=", "--body-file=")):
            value = token.split("=", 1)[1]
        else:
            continue
        if token in ("--body", "-b") or token.startswith("--body="):
            return ("text", value)
        candidate = Path(value)
        for probe in (candidate, root / candidate):
            try:
                return ("text", probe.read_text(encoding="utf-8"))
            except OSError:
                continue
        return ("unreadable", value)
    return None


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
