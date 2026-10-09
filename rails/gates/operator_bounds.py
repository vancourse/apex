"""What the operator holds and an agent does not reach for (design R2 reference deny; review of 1.3.0).

Two refusals, both on an agent's own tool calls:

* **The agent marker.** ``CLAUDECODE=1`` is how the plugin tells an agent's shell from the
  operator's: `rails used|approve|release` and `rails snapshot` refuse inside an agent, and
  the pre-push intent check asks only agents. Every one of those reads an environment
  variable the agent's own command can change - ``CLAUDECODE=0 rails used 75 x``,
  ``env -u CLAUDECODE git push``, ``$env:CLAUDECODE=''`` - so a command that names it is
  refused, as ``RAILS_OPERATOR`` already was.
* **The household store by name.** leak.toml ``[guard] names`` lists the real store's
  container and database. A command that names one, or a file an agent writes that names
  one (a script it would then run), is refused: real values never enter an agent's context.
  A statement whose command word is ``rails`` (the operator's `rails snapshot`) is not.

What it cannot see: a name assembled at run time, or a script written before this gate.
Tamper-evident, not tamper-proof - the receipts say the same of themselves.
"""

from __future__ import annotations

import re
import tomllib

from rails import store
from rails.hookio import Deny, Event
from rails.shell import segments, words

NAME = "operator_bounds"

_AGENT_MARKER = re.compile(r"\bCLAUDECODE\b")
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _shell(evt: Event) -> str:
    return "powershell" if evt.tool_name == "PowerShell" else "bash"


def store_names(evt: Event) -> list[str]:
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return []
    try:
        cfg = tomllib.loads((repo.top / "rails" / "leak.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError):
        return []
    return [str(n) for n in cfg.get("guard", {}).get("names", []) if str(n).strip()]


def _names_in(text: str, names: list[str]) -> str | None:
    for name in names:
        if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text):
            return name
    return None


def _is_rails_statement(segment: str, shell: str) -> bool:
    try:
        toks = [t for t in words(segment, shell) if "=" not in t.split("/")[0]]
    except Exception:  # noqa: BLE001 - an unparsable statement is not exempt
        return False
    head = toks[0].replace("\\", "/").rsplit("/", 1)[-1].lower() if toks else ""
    return head in ("rails", "rails.cmd")


def check(evt: Event):
    command = evt.command or ""
    if command and _AGENT_MARKER.search(command):
        return Deny(
            "rails: CLAUDECODE is how the plugin tells an agent's shell from the operator's; an agent's command "
            "never sets, clears or unsets it. The operator's words (`used`, `approve`, `release`) come from them."
        )
    names = store_names(evt) if (command or evt.tool_name in _WRITE_TOOLS) else []
    if not names:
        return None
    if command:
        shell = _shell(evt)
        try:
            parts = segments(command, shell) or [command]
        except Exception:  # noqa: BLE001
            parts = [command]
        for part in parts:
            if _is_rails_statement(part, shell):
                continue
            hit = _names_in(part, names)
            if hit:
                return Deny(
                    f"rails: `{hit}` is the household store (leak.toml [guard] names). Port the question to the "
                    "planted database, or ask the operator to run it; real values never enter an agent's context."
                )
    if evt.tool_name in _WRITE_TOOLS:
        ti = evt.tool_input
        written = "\n".join(
            str(ti.get(k, "")) for k in ("content", "new_string", "new_source")
        ) + "\n".join(str(e.get("new_string", "")) for e in ti.get("edits", []) if isinstance(e, dict))
        hit = _names_in(written, names)
        if hit:
            return Deny(
                f"rails: this writes `{hit}` (the household store, leak.toml [guard] names) into a file an agent "
                "would then run or commit. Point it at the planted database instead."
            )
    return None
