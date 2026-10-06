"""PreToolUse: household values never ride a gh body, a commit message or a subagent prompt (design R31).

Keyed on DESTINATION, not verb. Checks, against the value snapshot:
  * every `gh` call carrying text that leaves the box: --body/-b, --title/-t,
    --body-file, --input, -f/-F/--field/--raw-field (with @file resolved),
    in `gh pr|issue|release|gist|api`;
  * `git commit -m/-F` messages (they are pushed);
  * Agent/Task dispatch prompts (they leave the machine with the subagent).
Refuses on FOUND (3) and on could-not-look (4): fails closed. Active only in a
repo that declares `rails/leak.toml` — a repo with no household data has
nothing to compare against. Never prints a value.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from rails import leak, store
from rails.hookio import Deny, Event

NAME = "leak_dispatch"

_GH = re.compile(r"\bgh(?:\.exe)?\s+(pr|issue|release|gist|api|repo)\b")
_GIT_COMMIT = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?commit\b")
_TEXT_FLAGS = {"--body", "-b", "--title", "-t", "--message", "-m", "--notes", "-n"}
_FILE_FLAGS = {"--body-file", "--input", "--notes-file", "--file"}
_FIELD_FLAGS = {"-f", "-F", "--field", "--raw-field"}


def _words(command: str, shell: str) -> list[str]:
    try:
        from rails.shell import words  # the dispatcher's shell module, when present

        return words(command, shell)
    except Exception:  # noqa: BLE001
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return command.split()


def _read(path: str, cwd: Path) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = cwd / p
    try:
        return p.read_text(encoding="utf-8", errors="replace")[:2_000_000]
    except OSError:
        return ""


def extract(command: str, shell: str, cwd: Path) -> list[tuple[str, str]]:
    """(label, text) pairs a command would send off the box."""
    if not (_GH.search(command) or _GIT_COMMIT.search(command)):
        return []
    words = _words(command, shell)
    out: list[tuple[str, str]] = []
    is_gh_pr_create = bool(
        re.search(r"\bgh\s+(pr|issue)\s+(create|edit|comment)\b", command)
    )
    i = 0
    while i < len(words):
        w = words[i]
        flag, eq, inline = w.partition("=")
        nxt = words[i + 1] if i + 1 < len(words) else ""
        value = inline if eq else nxt
        step = 1 if eq else 2
        if flag in _TEXT_FLAGS:
            out.append((flag, value))
            i += step
            continue
        if flag in _FILE_FLAGS or (flag == "-F" and is_gh_pr_create):
            out.append((f"{flag} {value}", "" if value == "-" else _read(value, cwd)))
            i += step
            continue
        if flag in _FIELD_FLAGS:
            _, _, field_value = value.partition("=")
            if field_value.startswith("@"):
                out.append((f"{flag} {value}", _read(field_value[1:], cwd)))
            else:
                out.append((flag, field_value))
            i += step
            continue
        i += 1
    return [(label, text) for label, text in out if text]


def check(evt: Event):
    repo = store.find_repo(evt.cwd)
    if repo is None or not (repo.top / "rails" / "leak.toml").is_file():
        return None
    if evt.tool_name in ("Agent", "Task"):
        pieces = [("subagent prompt", evt.prompt)] if evt.prompt else []
    else:
        pieces = extract(evt.command, evt.shell or "bash", evt.cwd)
    if not pieces:
        return None
    lines = []
    for label, text in pieces:
        lines.extend(leak.text_lines(label, text))
    result = leak.check_lines(repo, lines, leak.allowlist_for(repo.top))
    if result.code == leak.EXIT_CLEAN:
        return None
    return Deny(
        "rails: refused - this would send text off the box.\n" + result.report()
    )
