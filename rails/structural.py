"""Checks `rails check` runs before any lane: properties of the change itself, not of its code.

**hook-removal.** A worktree's ``.claude/settings.json`` comes from its own branch, and
its hook commands run ``$CLAUDE_PROJECT_DIR/<path>`` - the MAIN checkout. A change that
deletes a script the base branch's settings still name therefore breaks every session in
every worktree cut before it: python exits 2 on a missing file, and Claude Code reads exit
2 as "block". Measured on jarvis 2026-10-07: #2598 retired seven hook scripts and 57 of 61
worktrees predated it; one session could not send a single prompt, before or after a
restart. The fix that shipped (#2604) put do-nothing placeholders back. This check makes
that the only way to retire a hook: delete it and the check fails, naming
``rails retire-hook <path>``, which writes the placeholder with a delete-by date.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from pathlib import Path

from rails import mainsync

PLACEHOLDER_DAYS = 30


@dataclass
class Finding:
    check: str
    message: str


_SCRIPT_SUFFIXES = (".py", ".sh", ".ps1", ".cmd", ".bat", ".js", ".mjs", ".cjs", ".ts")
_UNTIL = re.compile(r"placeholder until (\d{4}-\d{2}-\d{2})")


def _expired_placeholder(top: Path, base_sha: str, rel: str, today: _dt.date) -> bool:
    """A placeholder whose own date has passed may go: that is what the date is for."""
    code, text = mainsync._git(top, "show", f"{base_sha}:{rel}")
    m = _UNTIL.search(text) if code == 0 else None
    if not m:
        return False
    try:
        return today > _dt.date.fromisoformat(m.group(1))
    except ValueError:
        return False


def hook_removals(top: Path, base_sha: str, today: _dt.date | None = None) -> list[str]:
    """Hook scripts the change deletes that worktrees cut before it may still run.

    A script the base settings name, or any script under ``.claude/hooks/`` (an older
    branch's settings may name it even when the base's no longer do) - except a placeholder
    past its own delete-by date. A README or JSON file there is not a script and not counted.
    Narrower than the main-folder sync's guard, which waits on any .claude/ deletion.
    """
    today = today or _dt.date.today()
    code, out = mainsync._git(top, "diff", "--name-only", "--diff-filter=D", "--no-renames", base_sha, "HEAD")
    if code != 0:
        return []
    named = mainsync.hook_paths(top, base_sha)
    found = []
    for p in out.splitlines():
        is_hook = p in named or (p.startswith(".claude/hooks/") and p.endswith(_SCRIPT_SUFFIXES))
        if is_hook and not _expired_placeholder(top, base_sha, p, today):
            found.append(p)
    return found


def run(top: Path, base_sha: str | None) -> list[Finding]:
    if not base_sha:
        return []
    findings = []
    removed = hook_removals(top, base_sha)
    if removed:
        findings.append(
            Finding(
                "hook-removal",
                "this change deletes hook script(s) that worktrees cut before it still run "
                f"({', '.join(removed[:4])}); a missing script blocks every prompt there. "
                f"Keep a placeholder instead: `rails retire-hook {removed[0]}` (it writes one that "
                f"exits 0, with a delete-by date {PLACEHOLDER_DAYS} days out).",
            )
        )
    return findings


_PLACEHOLDERS = {
    ".py": (
        '"""Retired {today}: kept only as a do-nothing placeholder until {until}.\n\n'
        "Worktrees cut before its retirement still run it from their own .claude/settings.json,\n"
        "through $CLAUDE_PROJECT_DIR (the main checkout); a missing script exits 2, which Claude\n"
        "Code reads as \"block this prompt\". It reads nothing and allows everything. Delete it after\n"
        '{until}.\n"""\n\nimport sys\n\nif __name__ == "__main__":\n    sys.exit(0)\n'
    ),
    ".sh": (
        "#!/bin/sh\n# Retired {today}: a do-nothing placeholder until {until} (see rails retire-hook).\n"
        "# Worktrees cut before its retirement still run it; a missing script blocks their prompts.\nexit 0\n"
    ),
}


def retire_hook(top: Path, rel: str, today: _dt.date | None = None) -> tuple[int, str]:
    """Replace a hook script with a placeholder that exits 0; refuse a type it cannot write."""
    today = today or _dt.date.today()
    until = today + _dt.timedelta(days=PLACEHOLDER_DAYS)
    rel = rel.replace("\\", "/")
    path = (top / rel).resolve()
    try:
        inside = path.relative_to(top.resolve()).as_posix()
    except ValueError:
        return 2, f"rails retire-hook: {rel} is outside this repository"
    named = mainsync.hook_paths(top, "HEAD")
    if not (inside.startswith(".claude/hooks/") or inside in named):
        return 2, (
            f"rails retire-hook: {inside} is not a hook script (not under .claude/hooks/, not named by "
            ".claude/settings.json); refusing to overwrite it with a placeholder"
        )
    template = _PLACEHOLDERS.get(path.suffix)
    if template is None:
        return 2, f"rails retire-hook: no placeholder for {path.suffix or 'an extensionless'} script; write one that exits 0"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.format(today=today.isoformat(), until=until.isoformat()), encoding="utf-8", newline="\n")
    return 0, (
        f"rails retire-hook: {rel} is now a do-nothing placeholder until {until}. Remove its line from "
        ".claude/settings.json in this change; delete the placeholder after that date."
    )
