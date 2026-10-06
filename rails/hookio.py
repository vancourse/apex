"""The hook protocol: what arrives on stdin, what a gate may answer, what goes out.

A gate never writes to stdout and never exits. It receives an `Event` and
returns a verdict (or None). The dispatcher owns the wire format, so a gate
cannot get the JSON shape wrong, print a non-ASCII byte into a cp1252 console,
or block a tool call by crashing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Tools whose `tool_input.command` is a shell command line.
SHELL_TOOLS = {"Bash": "bash", "PowerShell": "powershell"}

#: Tools whose input names a filesystem path.
PATH_KEYS = ("file_path", "path", "notebook_path")


@dataclass
class Event:
    name: str
    payload: dict[str, Any]

    @property
    def tool_name(self) -> str:
        return str(self.payload.get("tool_name") or "")

    @property
    def tool_input(self) -> dict[str, Any]:
        value = self.payload.get("tool_input")
        return value if isinstance(value, dict) else {}

    @property
    def session_id(self) -> str:
        return str(self.payload.get("session_id") or "")

    @property
    def cwd(self) -> Path:
        return Path(str(self.payload.get("cwd") or "."))

    @property
    def agent_id(self) -> str:
        """Set when the call comes from a subagent rather than the main session."""
        return str(self.payload.get("agent_id") or "")

    @property
    def transcript_path(self) -> str:
        return str(self.payload.get("transcript_path") or "")

    @property
    def shell(self) -> str | None:
        """'bash' or 'powershell' for a shell tool call, else None."""
        return SHELL_TOOLS.get(self.tool_name)

    @property
    def command(self) -> str:
        if self.shell is None:
            return ""
        value = self.tool_input.get("command")
        return value if isinstance(value, str) else ""

    @property
    def prompt(self) -> str:
        """UserPromptSubmit text, or an Agent/Task dispatch prompt."""
        if self.name == "UserPromptSubmit":
            return str(self.payload.get("prompt") or "")
        value = self.tool_input.get("prompt")
        return value if isinstance(value, str) else ""

    def paths(self) -> list[str]:
        """Every path the tool input names, with backslashes normalised to '/'.

        apex's original path guards compared against forward-slash globs and
        were inert on this Windows box for months, because the harness hands
        hooks `C:\\Users\\...`. Normalising here, once, is the fix for all of
        them.
        """
        found = []
        for key in PATH_KEYS:
            value = self.tool_input.get(key)
            if isinstance(value, str) and value:
                found.append(normalise_path(value))
        return found


def normalise_path(value: str) -> str:
    return value.replace("\\", "/")


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


# --- verdicts -----------------------------------------------------------------


@dataclass
class Deny:
    """PreToolUse refusal. `reason` must name the alternative."""

    reason: str


@dataclass
class Block:
    """Stop / UserPromptSubmit refusal: the turn may not end (or the prompt is held)."""

    reason: str


@dataclass
class Notice:
    """Context the model sees; never refuses anything."""

    text: str


Verdict = Deny | Block | Notice


@dataclass
class Outcome:
    """What the dispatcher collected for one event, ready to serialise."""

    event: str
    denies: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

    def render(self) -> str:
        """The JSON the harness expects for this event, or '' for silence.

        ensure_ascii is deliberate: Windows defaults stdout to cp1252 and a
        non-ASCII reason would raise inside the hook and lose the message.
        """
        context = "\n\n".join(self.notices)
        if self.event == "PreToolUse":
            if self.denies:
                reason = "\n\n".join(self.denies)
                if context:
                    reason = f"{reason}\n\n{context}"
                body = {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                }
                return json.dumps(body)
            if context:
                return json.dumps(
                    {
                        "hookSpecificOutput": {
                            "hookEventName": "PreToolUse",
                            "additionalContext": context,
                        }
                    }
                )
            return ""
        if self.event in ("Stop", "SubagentStop"):
            if self.blocks:
                return json.dumps(
                    {"decision": "block", "reason": "\n\n".join(self.blocks)}
                )
            if context:
                return json.dumps({"systemMessage": context})
            return ""
        if self.event == "UserPromptSubmit":
            if self.blocks:
                return json.dumps(
                    {"decision": "block", "reason": "\n\n".join(self.blocks)}
                )
        if context and self.event in (
            "SessionStart",
            "UserPromptSubmit",
            "PostToolUse",
        ):
            return json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": self.event,
                        "additionalContext": context,
                    }
                }
            )
        return ""
