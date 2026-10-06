"""Refuse ANY tool call that references a live secrets file by path — not just
one that would print its values.

Ported from jarvis ``.claude/hooks/secret_file_touch_gate.py`` (26 denials, 21
of them inside subagents). ``secret_env`` stops a command from EMITTING values
into the transcript, but that is not the only way a secrets file leaks. On
2026-09-15, ``deploy/fleet/.env.dev``'s full contents — every database
password, the GitHub App private key, three API keys, an OAuth client secret —
appeared in a session's context AS A SYSTEM NOTE, unprompted, after commands
that were exactly the safe, names-only idiom ``secret_env`` recommends::

    cut -d= -f1 deploy/fleet/.env.dev
    grep "^OUTLOOK_" deploy/fleet/.env.dev

The leak came from the harness's own file-state tracking: a tool that
references a path registers that file as "seen", and when a tracked file
changes on disk later (exactly what ``--sync`` does to ``.env.dev`` on every
run), the harness surfaces an unredacted diff of it as an automatic note.

**The touch is the hazard, not the shape of the command that touches it.** So
this refuses the path outright, for every tool that can register a file:

- Bash and PowerShell, matched on COMMAND TEXT (raw — paths are often quoted)
  and requiring a reading/copying verb earlier in the same pipeline clause, so
  prose that merely mentions ``.env`` passes;
- Read, Grep and Glob on their ``file_path`` / ``path`` parameters, as the
  original registered; and, new in the port, Edit / Write / MultiEdit, which
  register the file just the same and can overwrite rendered credentials.

**Residual risk, stated rather than hidden.** A Grep/Glob with no explicit path
(or a directory containing one of these files) is not covered — only an
EXPLICIT reference to the protected file is.

Protected: any ``.env`` variant (never ``.env.example`` / ``.env.*.example``),
``.op-token.*``, and ``.delivery.(dev|prod)``. Override, Bash/PowerShell only::

    JARVIS_SECRET_FILE_TOUCH_OK=1 <your command>          # RAILS_SECRET_FILE_TOUCH_OK is an alias
    $env:JARVIS_SECRET_FILE_TOUCH_OK=1; <your command>    # PowerShell

There is no override for the path tools — route through a shell with the
override instead, so the escape hatch is visible in one place.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell.override import overridden

NAME = "secret_file_touch"

OVERRIDES = ("JARVIS_SECRET_FILE_TOUCH_OK", "RAILS_SECRET_FILE_TOUCH_OK")

#: Tools whose path parameter registers a file with the harness.
PATH_TOOLS = frozenset({"Read", "Grep", "Glob", "Edit", "Write", "MultiEdit"})

#: A path SEGMENT, not a bare substring — `.env` must not fire on
#: `something.environment.json`. Bounded by lookaround, so a bare relative name
#: (`cut -d= -f1 .env.dev`, half the 2026-09-15 leak) still matches.
_BOUNDARY = r"[A-Za-z0-9_.-]"
_FILENAME = (
    r"\.env(?:\.[A-Za-z0-9_-]+)?"  # .env, .env.dev, .env.prod, .env.local, ...
    r"|\.op-token\.[A-Za-z0-9_-]+"  # .op-token.dev, .op-token.prod
    r"|\.delivery\.(?:dev|prod)"  # .delivery.dev, .delivery.prod
)
#: For a path parameter, which is ALWAYS a path, never prose.
_PROTECTED = re.compile(rf"(?<!{_BOUNDARY})(?:{_FILENAME})(?!{_BOUNDARY})")
#: The one family `_PROTECTED` would otherwise catch that holds no real
#: secret. Checked FIRST: `.env.example` contains `.env`.
_TEMPLATE = re.compile(
    rf"(?<!{_BOUNDARY})\.env(?:\.[A-Za-z0-9_-]+)?\.example(?!{_BOUNDARY})"
)

#: For COMMAND TEXT, which can legitimately CONTAIN prose: a recognized
#: reading/copying verb must come earlier in the same pipeline clause
#: (`[^|;&\n]*` cannot cross a `|`/`;`/`&`/newline).
_READ_VERBS = (
    r"cat|bat|head|tail|less|more|type|Get-Content|gc|Select-String|findstr"
    r"|cut|wc|grep|sed|awk|sort|uniq|diff|xxd|od|base64"
    r"|sha256sum|md5sum|notepad|code|vim|vi|nano|emacs"
    r"|cp|copy|Copy-Item|mv|move|Move-Item|scp|rsync"
)
_VERBED = re.compile(
    rf"\b(?:{_READ_VERBS})\b[^|;&\n]*?"
    rf"(?<!{_BOUNDARY})(?P<path>{_FILENAME})(?!{_BOUNDARY})",
    re.IGNORECASE,
)


def _reason(offending_path: str) -> str:
    return (
        f"This references {offending_path!r} — a file the fleet "
        "renders real credentials into.\n\n"
        "Even a names-only touch (`cut -d= -f1`, `grep '^KEY='`, "
        "the Read tool) registers this file as one the harness "
        "has seen. The harness diffs a tracked file when it "
        "changes on disk later — which `--sync` does on every "
        "run — and that diff is NOT redacted: it surfaces every "
        "value in plaintext, unprompted, as a system note. That "
        "is what leaked this file's contents on 2026-09-15, "
        "despite every touch along the way being a safe, "
        "names-only command by secret_env_gate's own "
        "definition.\n\n"
        "You almost certainly do not need to touch this path at "
        "all: fleet.py / run.ps1 / sync-dev.ps1 / "
        "Preview-Purser.ps1 all read and write it from inside "
        "their own script, which never spells out the path and "
        "so never trips this gate. If you need to know "
        "something ABOUT its contents, ask the operator to "
        "check it directly, or query the running "
        "container/app instead of the host file.\n\n"
        "To proceed anyway (Bash/PowerShell only):\n"
        "    JARVIS_SECRET_FILE_TOUCH_OK=1 <your command>\n"
        "    $env:JARVIS_SECRET_FILE_TOUCH_OK=1; <your command>   # PowerShell\n"
        "(RAILS_SECRET_FILE_TOUCH_OK works in place of either name.)"
    )


def _offending_path(text: str) -> str | None:
    """For a PATH parameter — never prose, no verb needed."""
    if _TEMPLATE.search(text):
        return None
    match = _PROTECTED.search(text)
    if match is None:
        return None
    return match.group(0)


def _offending_path_in_command(command: str) -> str | None:
    """For COMMAND TEXT — requires a reading verb first."""
    if _TEMPLATE.search(command):
        return None
    match = _VERBED.search(command)
    if match is None:
        return None
    return match.group("path")


def check(evt: Event) -> Deny | None:
    if evt.shell is not None:
        command = evt.command
        if not command:
            return None
        if overridden(command, *OVERRIDES):
            return None
        offender = _offending_path_in_command(command)
        return Deny(_reason(offender)) if offender else None
    if evt.tool_name in PATH_TOOLS:
        # Grep/Glob with no `path` search the cwd, which names no specific file.
        for candidate in evt.paths():
            offender = _offending_path(candidate)
            if offender:
                return Deny(_reason(offender))
    return None
