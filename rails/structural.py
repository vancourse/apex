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
from dataclasses import dataclass
from pathlib import Path

from rails import mainsync

PLACEHOLDER_DAYS = 30


@dataclass
class Finding:
    check: str
    message: str


def hook_removals(top: Path, base_sha: str) -> list[str]:
    """Files the change deletes that a hook command on the base branch still runs.

    Narrower than the main-folder sync's guard (which waits on any .claude/ deletion):
    a retired rule or skill file does not block a prompt, only a missing hook script does.
    """
    code, out = mainsync._git(top, "diff", "--name-only", "--diff-filter=D", "--no-renames", base_sha, "HEAD")
    if code != 0:
        return []
    named = mainsync.hook_paths(top, base_sha)
    return [p for p in out.splitlines() if p in named or p.startswith(".claude/hooks/")]


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
    path = top / rel
    template = _PLACEHOLDERS.get(path.suffix)
    if template is None:
        return 2, f"rails retire-hook: no placeholder for {path.suffix or 'an extensionless'} script; write one that exits 0"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(template.format(today=today.isoformat(), until=until.isoformat()), encoding="utf-8", newline="\n")
    return 0, (
        f"rails retire-hook: {rel} is now a do-nothing placeholder until {until}. Remove its line from "
        ".claude/settings.json in this change; delete the placeholder after that date."
    )
