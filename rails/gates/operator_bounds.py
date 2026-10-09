"""What the operator holds and an agent does not reach for (design R2 reference deny; review of 1.3.0).

Two refusals, both on an agent's own tool calls:

* **The agent marker.** ``CLAUDECODE=1`` is how the plugin tells an agent's shell from the
  operator's: the pre-push intent check asks only agents, and `rails used|approve|release`
  refuse inside one (they also need the operator's terminal, which an agent does not have).
  A command - or a file an agent writes, to run next - that sets, clears or unsets the
  marker is refused: ``CLAUDECODE=0 ...``, ``env -u CLAUDECODE``, ``env -i``,
  ``unset ${!CLAUDE@}``, ``$env:CLAUDECODE=''``, ``Remove-Item Env:CLAUDE*``,
  ``os.environ.pop('CLAUDECODE')``. Naming or reading it (``git grep CLAUDECODE``,
  ``os.environ.get("CLAUDECODE")``) is not refused, and neither is a test file (``tests/``,
  ``test_*``), where these spellings are the planted inputs.
* **The household store by name.** leak.toml ``[guard] names`` lists the real store's
  container and database. A command that names one, or a file an agent writes that names one
  (a script it would then run), is refused: real values never enter an agent's context.
  There is no exemption: the operator's `rails snapshot` runs in their own shell, which this
  hook never sees, and `rails receipt -- <cmd>` runs whatever follows it.

What it cannot see: a name assembled at run time, or a script written before this gate.
Tamper-evident, not tamper-proof - the receipts say the same of themselves.
"""

from __future__ import annotations

import re
import tomllib

from rails import store
from rails.hookio import Deny, Event

NAME = "operator_bounds"

#: Setting, clearing or unsetting the marker, in bash, PowerShell, cmd or a script.
_MARKER_TOUCH = re.compile(
    r"\bCLAUDECODE\s*=(?!=)|"
    r"(?:\bunset\b|\benv\s+-u\b|\b(?:Remove|Clear|Set)-Item\b|SetEnvironmentVariable|"
    r"\$env:|\bEnv:|\bputenv\b|\bunsetenv\b|\bdelete\s+process\.env)[^\n;|&]*\bCLAUDE|"
    r"\benviron\s*\.\s*(?:pop|clear|update)\b|\bdel\s+os\.environ\b|"
    r"\benviron\s*\[\s*['\"]CLAUDE\w*['\"]\s*\]\s*=(?!=)|"
    r"\$\{!CLAUDE|\benv\s+(?:-\w*i\b|--ignore-environment)|-UseNewEnvironment\b",
    re.IGNORECASE,
)
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_TEST_FILE = re.compile(r"(?:^|[/\\])(?:tests?[/\\]|test_[^/\\]*$|[^/\\]*_test\.py$)")


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


def _written(evt: Event) -> str:
    ti = evt.tool_input
    parts = [str(ti.get(k, "")) for k in ("content", "new_string", "new_source")]
    parts += [str(e.get("new_string", "")) for e in ti.get("edits", []) if isinstance(e, dict)]
    return "\n".join(parts)


def check(evt: Event):
    command = evt.command or ""
    written = _written(evt) if evt.tool_name in _WRITE_TOOLS else ""
    target = str(evt.tool_input.get("file_path") or evt.tool_input.get("notebook_path") or "")
    marker_texts = [(command, "command")]
    if written and not _TEST_FILE.search(target):
        marker_texts.append((written, "file"))
    for text, where in marker_texts:
        if text and _MARKER_TOUCH.search(text):
            return Deny(
                f"rails: this {where} sets, clears or unsets CLAUDECODE - how the plugin tells an agent's shell "
                "from the operator's. An agent never changes it; the operator's words (`used`, `approve`, "
                "`release`) come from them, in a prompt or their own terminal."
            )
    if not command and not written:
        return None
    names = store_names(evt)
    if not names:
        return None
    hit = _names_in(command, names)
    if hit:
        return Deny(
            f"rails: `{hit}` is the household store (leak.toml [guard] names). Port the question to the "
            "planted database, or ask the operator to run it; real values never enter an agent's context."
        )
    hit = _names_in(written, names)
    if hit:
        return Deny(
            f"rails: this writes `{hit}` (the household store, leak.toml [guard] names) into a file an agent "
            "would then run or commit. Point it at the planted database instead."
        )
    return None
