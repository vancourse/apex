"""PreToolUse hook: a session-narrative `.md` heading into `docs/` gets redirected.

Measured on a real repo's first 33 days: of **568 documents, 16 stayed maintained** —
and all 16 were **living registries**, files whose whole job is to be edited again.
**383 were written once and never revisited**, and that genre has a shape: handoffs,
sweeps, readiness reports, triage rounds, completion logs, dated inventories. Each was
true when written and none was ever true again, and together they are most of what a
reader of `docs/` has to wade through to find the 16 that matter.

The redirect, not the refusal: **that content belongs in the PR body.** It reaches the
same reader, it is attached to the change that produced it, and it does not outlive the
moment it was true. A handoff note in a PR body is read by the next person on that
work; the same note in `docs/` is read by nobody and shadows the design doc next to it.

**The exemption list is pinned by name, and that is the load-bearing part.** The 16
maintained documents were living registries — `GAPS.md`, `DECISION_LOG.md`, a standing
`HANDOFF.md` — and a name-shaped rule catches them too, because "handoff" is in the
name of both the genre that fails and the registry that works. **A hook that nags the
3% that work in order to stop the 67% that do not has it backwards**, so the registries
are named — at the top of `docs/`, where a standing register lives — and so are the
directories (`lessons/`, `templates/`) whose whole contents are meant to be re-read.

**Write only, never Edit.** This fires on *creation*. Nagging every touch of a legacy
file teaches a session to skim past the hook, and by the time it fires on something
worth reading it has already been trained away.

Advisory. It injects context and never denies — the author may have a reason, and this
hook does not know it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hooklib import (  # noqa: E402
    emit,
    fail_open,
    find_repo_root,
    read_payload,
    relative_to_root,
    run,
    warn_once,
)

#: Living registries, by name, and **only as an immediate child of `docs/`**. Their
#: whole job is to be edited again.
#:
#: The depth scope is the part worth arguing about. A *standing* handoff register lives
#: at a known place and everyone knows where it is; a `handoff.md` in
#: `docs/ingest/r2/` is a note about one week of one feature, which is precisely the
#: 383. The name alone cannot tell those apart — the location can.
#:
#: Only `handoff.md` currently collides with the patterns below at all. `GAPS.md` and
#: `DECISION_LOG.md` are pinned anyway, so that adding a pattern later cannot quietly
#: start firing on two of the sixteen documents this hook exists to protect.
EXEMPT_NAMES = frozenset({"gaps.md", "decision_log.md", "handoff.md"})

#: Directories whose contents are meant to be re-read, so the genre argument does not
#: apply inside them.
EXEMPT_DIRS = frozenset({"lessons", "templates", "adr"})

#: Basename fragments that name the write-once genre.
NARRATIVE_FRAGMENTS = (
    "handoff",
    "hand-off",
    "sweep",
    "readiness",
    "triage",
    "autonomous-session",
    "session-summary",
    "completion-log",
    "completion_log",
)

#: `2026-08-15`, `20260815`, `2026-08`. A date in the name is the tell that a document
#: is a snapshot of a moment rather than a statement about the system.
DATE = re.compile(r"(?:\d{4}-\d{2}(?:-\d{2})?|\b\d{8}\b)")

#: Dated documents of these kinds. Undated, they are plausibly living registries — an
#: `inventory.md` somebody maintains is a real thing, and `2026-08-15-inventory.md`
#: never is.
DATED_KINDS = ("log", "inventory", "freeze", "audit")


def is_narrative(stem: str) -> bool:
    """True when the basename names the write-once genre.

    Honest limit: this reads *names*, so it catches the genre only when the author
    named it after the genre. `2026-08-15-postmortem.md` is the same kind of document
    and this will not flag it — a name-shaped rule cannot be complete, and widening it
    with guesses is how it starts firing on the registries instead.
    """
    lowered = stem.lower()
    if any(fragment in lowered for fragment in NARRATIVE_FRAGMENTS):
        return True
    return bool(DATE.search(lowered)) and any(kind in lowered for kind in DATED_KINDS)


def verdict(rel: Path) -> bool:
    """True when this path should be redirected to the PR body."""
    parts = rel.parts
    if len(parts) < 2 or parts[0] != "docs":
        return False
    if any(part.lower() in EXEMPT_DIRS for part in parts[1:-1]):
        return False
    if len(parts) == 2 and rel.name.lower() in EXEMPT_NAMES:
        return False
    return is_narrative(Path(rel.name).stem)


def message(rel: Path) -> str:
    return "\n".join(
        [
            f"SESSION NARRATIVE — {rel.as_posix()} reads like a record of a session, not "
            "a statement about",
            "the system.",
            "",
            "Measured on a real repo's first 33 days: of 568 documents, **16 stayed "
            "maintained** — all of",
            "them living registries — and **383 were written once and never revisited**. "
            "Handoffs, sweeps,",
            "readiness reports, triage rounds, completion logs and dated inventories are "
            "that second genre.",
            "",
            "**Put it in the PR body instead.** Same reader, attached to the change that "
            "produced it, and it",
            "stops being read when it stops being true. A handoff in a PR body reaches the "
            "next person on",
            "that work; the same file in `docs/` is read by nobody and shadows the design "
            "doc beside it.",
            "",
            "Write it here anyway if it is a **living registry** — something whose job is "
            "to be edited again",
            f"({', '.join(sorted(EXEMPT_NAMES))} directly under `docs/` are already "
            f"exempt by name, as is anything under "
            f"{', '.join(sorted(d + '/' for d in EXEMPT_DIRS))}). Advisory: nothing is "
            "blocked.",
        ]
    )


def main() -> None:
    payload = read_payload()
    if payload.get("tool_name") != "Write":
        fail_open()

    raw_path = payload.get("tool_input", {}).get("file_path")
    if not raw_path:
        fail_open()

    target = Path(str(raw_path))
    # `.exists()` is what makes this creation-only even though the harness routes both
    # a new file and a full overwrite through `Write`.
    if target.suffix != ".md" or target.exists():
        fail_open()

    root = find_repo_root(target.parent)
    if root is None:
        fail_open()
    rel = relative_to_root(target, root)
    if rel is None or not verdict(rel):
        fail_open()

    if warn_once(
        str(payload.get("session_id", "nosession")), f"narrative-{rel.as_posix()}"
    ):
        fail_open()
    emit(message(rel))


if __name__ == "__main__":
    run(main)
