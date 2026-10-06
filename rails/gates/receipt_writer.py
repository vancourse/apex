"""PostToolUse: the witness log that makes receipts tamper-EVIDENT (design R25).

When a shell command ran a rails command that writes receipts (check, post,
ship, walk, oracle, review, snapshot), log a ``rails-cmd`` firing. When a
command wrote under the rails store or ``.rails/`` by hand (redirect, tee,
Set-Content, Out-File, cp/mv), log ``store-write``. A receipt written from an
agent's tool call with no ``rails-cmd`` firing around it is reported ``forged``.

Never refuses anything and never shows the model anything.
"""

from __future__ import annotations

import re
import time

from rails import store
from rails.hookio import Event, sha256

NAME = "receipt_writer"

_RAILS_CMD = re.compile(
    r"(?:^|[\s;&|/\\\"'])rails(?:\.cmd)?[\"']?\s+(check|post|ship|walk|oracle|review|snapshot|work)\b"
)
_STORE_WRITE = re.compile(
    r"(?:>|>>|\btee\b|\bSet-Content\b|\bAdd-Content\b|\bOut-File\b|\bcp\b|\bmv\b|\bCopy-Item\b|\bMove-Item\b)"
    r"[^;&|\n]*(?:\.claude[/\\]rails[/\\]|\.rails[/\\])",
    re.IGNORECASE,
)


def check(evt: Event):
    command = evt.command
    if not command:
        return None
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    kinds = []
    m = _RAILS_CMD.search(command)
    if m:
        kinds.append(("rails-cmd", m.group(1)))
    if _STORE_WRITE.search(command):
        kinds.append(("store-write", ""))
    for verdict, sub in kinds:
        try:
            store.append_jsonl(
                repo.dir / "firings.jsonl",
                {
                    "ts": int(time.time()),
                    "session": evt.session_id[:12],
                    "leaf": repo.leaf,
                    "event": "PostToolUse",
                    "tool": evt.tool_name,
                    "gate": NAME,
                    "verdict": verdict,
                    "sub": sub,
                    "cmd_sha256": sha256(command)[:16],
                },
            )
        except OSError:
            pass
    return None
