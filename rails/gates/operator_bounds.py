"""What the operator holds and an agent does not reach for (design R2 reference deny; review of 1.3.0).

Two refusals, both on an agent's own tool calls:

* **The agent marker.** ``CLAUDECODE=1`` is how the plugin tells an agent's shell from the
  operator's: the pre-push intent check asks only agents, and `rails used|approve|release`
  refuse inside one (they also need the operator's terminal, which an agent does not have).
  A statement that sets, clears or unsets the marker is refused, judged by its command
  words: an assignment (``CLAUDECODE=0 ...``, ``export``, ``set``, ``$env:CLAUDECODE=``),
  ``env -u CLAUDECODE`` / ``env -i``, ``unset`` of a CLAUDE name or ``${!CLAUDE@}``,
  ``Remove-Item|Clear-Item|Set-Item Env:CLAUDE*``, ``SetEnvironmentVariable('CLAUDE...``,
  ``os.environ.pop`` / ``del os.environ`` / ``os.environ['CLAUDE..'] =``. So is a script an
  agent writes with one of those lines (a shell script line by line; Python only for code that
  names the marker, outside test files). Naming or reading it is not refused (``git grep CLAUDECODE``, ``Write-Output $env:CLAUDECODE``, a
  docstring, a commit message), and neither is a test file, where the spellings are planted.
* **The household store by name.** leak.toml ``[guard] names`` lists the real store's
  container and database. A statement that reaches a database (``psql``, ``pg_dump``,
  ``docker``/``podman``/``kubectl``, a driver or a DSN) and names one, or a shell script an
  agent writes that does, is refused: real values never enter an agent's context. Naming one
  elsewhere (``rg <name>``, an edit to the fleet config or its tests) is not.
  There is no exemption: the operator's `rails snapshot` runs in their own shell, which this
  hook never sees, and `rails receipt -- <cmd>` runs whatever follows it.

What it cannot see: a name assembled at run time, a script written before this gate, or
``env`` reached through another launcher (``Start-Process env -ArgumentList ...``).
Tamper-evident, not tamper-proof - the receipts say the same of themselves.
"""

from __future__ import annotations

import re
import tomllib

from rails import store
from rails.gates.destructive import command_name, commands
from rails.hookio import Deny, Event

NAME = "operator_bounds"

#: An assignment to a CLAUDE* variable at the start of a statement or a script line.
_ASSIGN = re.compile(
    r"^[\s(]*(?:\w+=\S*\s+)*(?:export\s+|set\s+|setx\s+|env\s+(?:-\S+\s+|\w+=\S*\s+)*)?(?:\$env:)?CLAUDE\w*\s*=(?!=)",
    re.IGNORECASE,
)
#: Code that changes the marker, wherever it appears: each spelling names CLAUDE itself, so
#: `os.environ.update(env)` or a `Remove-Item` of a `.claude` path is not caught (review of 1.3.0).
_ANYWHERE = re.compile(
    r"\$\{!CLAUDE|SetEnvironmentVariable\s*\(\s*['\"]CLAUDE|"
    r"\benviron\s*\.\s*pop\s*\(\s*['\"]CLAUDE|\bdel\s+os\.environ\s*\[\s*['\"]CLAUDE|"
    r"\benviron\s*\[\s*['\"]CLAUDE\w*['\"]\s*\]\s*=(?!=)|\b(?:put|unset)env\s*\(\s*['\"]CLAUDE|"
    r"\benviron\s*\.\s*clear\s*\(\s*\)|-UseNewEnvironment\b|\bdelete\s+process\.env(?:\.|\[\s*['\"])CLAUDE",
    re.IGNORECASE,
)
_SCRIPT_LINE = re.compile(
    r"^\s*(?:unset\b[^\n]*CLAUDE|env\s+(?:-\w*[iu]\b|--ignore-environment|--unset)|"
    r"(?:Remove|Clear|Set)-Item\s+Env:\\?CLAUDE)",
    re.IGNORECASE | re.MULTILINE,
)
_ENV_ITEM = ("remove-item", "clear-item", "set-item", "new-item", "ri", "del", "rm", "erase")
_ENV_PATH = re.compile(r"^env:\\?/?CLAUDE", re.IGNORECASE)
_WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_SHELL_SCRIPT = re.compile(r"\.(?:sh|bash|zsh|ps1|psm1|cmd|bat)$", re.IGNORECASE)
_PY_SCRIPT = re.compile(r"\.py$", re.IGNORECASE)
_TEST_FILE = re.compile(r"(?:^|[/\\])(?:tests?[/\\]|test_[^/\\]*$|[^/\\]*_test\.py$)")
#: A statement that reaches a database: only these are judged for the store's names, so a
#: `rg <name>` or an edit to the fleet config that names the database is not refused.
_DB_ACCESS = re.compile(
    r"\b(?:psql|pg_dump|pg_dumpall|pg_restore|pgcli|sqlcmd|docker|podman|kubectl|psycopg\d?|asyncpg|"
    r"sqlalchemy|create_engine|DATABASE_URL)\b|postgres(?:ql)?://",
    re.IGNORECASE,
)


def _statement_touches(segment: str, tokens: list[str]) -> bool:
    if _ASSIGN.match(segment):
        return True
    name, args = command_name(tokens[0]), tokens[1:]
    if name == "env":
        own = []  # env's own options and assignments, before the command it runs
        for a in args:
            if not a.startswith("-") and "=" not in a and not (own and own[-1] in ("-u", "--unset")):
                break
            own.append(a)
        if any(a == "--ignore-environment" or re.fullmatch(r"-[a-zA-Z]*i[a-zA-Z]*", a) for a in own):
            return True
        unsets = any(a.startswith(("-u", "--unset")) for a in own)
        return unsets and any("CLAUDE" in a.upper() for a in own)
    if name == "unset":
        return any("CLAUDE" in a.upper() for a in args)
    if name in _ENV_ITEM:
        return any(_ENV_PATH.match(a) for a in args)
    return False


_PIPED_ENV_REMOVE = re.compile(
    r"Env:\\?CLAUDE[^|;\n]*\|\s*(?:Remove-Item|Clear-Item|ri|rm|del|erase)\b", re.IGNORECASE
)


def _command_touches(command: str, shell: str | None) -> bool:
    if _ANYWHERE.search(command) or _PIPED_ENV_REMOVE.search(command):
        return True
    if shell is None:
        return False
    try:
        parsed = commands(command, shell)
    except Exception:  # noqa: BLE001 - judged by the anywhere spellings above
        return False
    return any(_statement_touches(segment, tokens) for segment, tokens in parsed)


def _script_touches(text: str, target: str) -> bool:
    """A shell script is read line by line; Python only for code that names the marker."""
    if _SHELL_SCRIPT.search(target):
        return bool(
            _ANYWHERE.search(text)
            or _SCRIPT_LINE.search(text)
            or any(_ASSIGN.match(line) for line in text.splitlines())
        )
    if _PY_SCRIPT.search(target) and not _TEST_FILE.search(target):
        return bool(_ANYWHERE.search(text))
    return False


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
    touched = None
    if command and _command_touches(command, evt.shell):
        touched = "command"
    elif written and _script_touches(written, target):
        touched = "script"
    if touched:
        return Deny(
            f"rails: this {touched} sets, clears or unsets CLAUDECODE - how the plugin tells an agent's shell "
            "from the operator's. An agent never changes it; the operator's words (`used`, `approve`, "
            "`release`) come from them, in a prompt."
        )
    if not command and not written:
        return None
    names = store_names(evt)
    if not names:
        return None
    # Any statement reaching a database makes the whole command judged: the name can sit in the
    # statement before it (`export PGDATABASE=<name>; psql`, `$c='<name>'; docker exec $c`).
    hit = _names_in(command, names) if command and _DB_ACCESS.search(command) else None
    if hit:
        return Deny(
            f"rails: `{hit}` is the household store (leak.toml [guard] names). Port the question to the "
            "planted database, or ask the operator to run it; real values never enter an agent's context."
        )
    judged = _SHELL_SCRIPT.search(target) or (
        _PY_SCRIPT.search(target) and not _TEST_FILE.search(target) and _DB_ACCESS.search(written)
    )
    hit = _names_in(written, names) if judged else None
    if hit:
        return Deny(
            f"rails: this writes `{hit}` (the household store, leak.toml [guard] names) into a file an agent "
            "would then run or commit. Point it at the planted database instead."
        )
    return None
