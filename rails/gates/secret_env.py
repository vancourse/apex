"""Refuse a command that would print environment VALUES into the transcript.

Ported from jarvis ``.claude/hooks/secret_env_gate.py`` (95 denials in 47
sessions). The command it stops looks like this, and it has leaked a live
Anthropic key twice::

    docker exec dev-jarvis-fleet-1 sh -c 'env | grep -i studio'

An agent wants to know *which* variables a container carries, writes the obvious
command, and the values come with them. The 2026-08-13 instance carried
``STUDIO_MODEL_API_KEY=sk-ant-api03-…`` — a live, billable credential — into the
transcript, where it cannot be recalled. The operator pays to rotate it.

**The agent never wanted the values.** It wanted the NAMES. Every shape refused
here has a name-only form that answers the same question and loses nothing
(``env | cut -d= -f1``, ``docker inspect --format '{{.State.Status}}' X``,
``Get-ChildItem env: | Select-Object -ExpandProperty Name``).

**A redaction filter the agent writes itself is not a control.** The 2026-08-13
leak *had* one — ``sed "s/=.*SECRET.*/=<redacted>/"`` — and it silently failed to
match. Only a small, explicit set of idioms that provably cannot emit a value
(:data:`_NAME_ONLY`) rescues a bulk dump.

**Keyed on the shape, never the variable name.** ``env`` prints every variable,
so the name that leaks is whichever one happens to exist.

**This is a speed bump, not a wall.** An environment can be printed in unbounded
ways; this covers the shapes an agent actually reaches for. Layer 1 is a
spend-capped dev key; layer 3 is not putting a live credential in an
environment at all.

**PowerShell** (new in the port): ``Get-ChildItem env:`` and its aliases
(``gci``/``ls``/``dir``/``Get-Item``), ``[Environment]::GetEnvironmentVariables()``
and ``cmd /c set`` are the same bulk dump; ``gc .env`` / ``Get-Content ".env"``
the same dotenv read. ``$env:NAME`` reads ONE variable and stays allowed, as
``os.environ.get("X")`` does.

Matched on the RAW command text, quotes included — the shapes it stops live
inside ``sh -c '...'`` — so this gate deliberately does not use
``rails.shell.scrub``. The override, as TEXT or in the hook's own environment::

    JARVIS_ENV_DUMP_OK=1 <your command>          # RAILS_ENV_DUMP_OK is an alias
    $env:JARVIS_ENV_DUMP_OK=1; <your command>    # PowerShell
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell.override import overridden

NAME = "secret_env"

OVERRIDES = ("JARVIS_ENV_DUMP_OK", "RAILS_ENV_DUMP_OK")

#: Idioms that provably emit names only — everything from the first `=` onward is
#: discarded. This is an ALLOWLIST on purpose: an arbitrary `sed`/`grep` in the
#: pipeline proves nothing (the leak that motivated this file had one).
_NAME_ONLY = (
    # cut -d= -f1 / cut -d'=' -f1 / cut -d"=" -f 1
    re.compile(
        r"\bcut\s+(?:-d\s*['\"]?=['\"]?\s+-f\s*1|-f\s*1\s+-d\s*['\"]?=['\"]?)\b"
    ),
    # awk -F= '{print $1}'  (and -F'=' / -F"=")
    re.compile(r"\bawk\s+-F\s*['\"]?=['\"]?\s+.*\$1"),
    # sed 's/=.*//'  — drop from the first = to end of line
    re.compile(r"\bsed\s+(?:-E\s+)?['\"]s/=\.\*//"),
    # grep -o with a pattern anchored at ^ that cannot span the `=`. The trailing
    # boundary is a LOOKAHEAD that admits a closing shell quote, so
    # `sh -c 'env | grep -oE "^STUDIO"'` counts, and `grep -oE "^X.*=.*"` does not.
    re.compile(r"\bgrep\s+-[a-zA-Z]*o[a-zA-Z]*\s+['\"]?\^[^='\"\s]*(?=['\"]|\s|$)"),
    # declare -p / compgen -v list names without values
    re.compile(r"\bcompgen\s+-v\b"),
)

#: PowerShell's name-only forms: project the Name (or Keys) and nothing else.
_PS_NAME_ONLY = re.compile(
    r"\b(?:Select-Object|select)\s+(?:-ExpandProperty\s+|-Property\s+|-exp\w*\s+)?"
    r"['\"]?(?:Name|Key)['\"]?(?=$|[\s|;)])"
    r"|\)\.(?:Name|Keys?)\b"
    r"|\b(?:ForEach-Object|foreach|%)\s+(?:-MemberName\s+)?['\"]?(?:Name|Key)['\"]?(?=$|[\s|;)])"
    r"|\s-Name\b",
    re.IGNORECASE,
)

#: `env` / `printenv` invoked so that it dumps EVERYTHING. `env VAR=x cmd` sets a
#: variable and runs a command — it prints nothing — so a following non-flag token
#: means this is not a dump. Bare `env`, or `env | …`, is.
_ENV_DUMP = re.compile(
    r"(?:^|[|;&(]|\bsh\s+-c\s*['\"]|\s)(?:env|printenv)\s*(?:$|[|;&)\n'\"])"
)

#: PowerShell's bulk dumps. `env:` followed by a NAME reads one variable and is
#: not a dump; bare `env:` (or `env:\`, or a wildcard) is.
_PS_ENV_DUMP = re.compile(
    r"\b(?:Get-ChildItem|gci|ls|dir|Get-Item|gi)\s+(?:-(?:Literal)?Path\s+)?['\"]?"
    r"env:[\\/]?(?:\*?['\"]?(?=$|[\s|;)}])|[^\s|;)}]*\*)"
    r"|\[(?:System\.)?Environment\]::GetEnvironmentVariables\s*\("
    r"|\bcmd(?:\.exe)?\s+/c\s+['\"]?set['\"]?(?=$|[\s|;&)])",
    re.IGNORECASE,
)

#: `docker inspect` / `docker container inspect` with no `--format`: the JSON it
#: returns embeds `Config.Env` in full.
_DOCKER_INSPECT = re.compile(r"\bdocker\s+(?:container\s+)?inspect\b")
_DOCKER_FORMAT = re.compile(r"--format\b|-f\s")

#: Explicitly reaching for the env field / file by name. The language-runtime
#: cases require a PRINTING context, not a bare mention: matching a bare
#: `os.environ` refused the original gate's own commit, whose message explains
#: what the gate covers. The known cost: `d = os.environ; print(d)` passes.
_ENV_FIELD = re.compile(
    r"\.Config\.Env\b"  # docker --format '{{.Config.Env}}'
    r"|/proc/\d+/environ|/proc/self/environ"  # the kernel's copy
    r"|(?:print|pprint|console\.log|json\.dumps|repr|str)\s*\(\s*"
    r"(?:os\.environ|process\.env)\s*\)"  # print(os.environ) / console.log(process.env)
    r"|\bdict\s*\(\s*os\.environ\s*\)"  # dict(os.environ) — the usual copy-then-print
)

#: `cat`/`head`/`tail`/`less`/`more`/`type` pointed at a dotenv file.
_DOTENV_READ = re.compile(
    r"\b(?:cat|bat|head|tail|less|more|type|Get-Content)\b[^|;&\n]*"
    r"(?:^|[\s/\\])\.env(?:\.[A-Za-z0-9_.-]+)?\b"
)

#: The same in PowerShell spelling: case-insensitive, the `gc` alias, and a
#: quoted path (`Get-Content ".env"`), which the bash form's boundary misses.
_PS_DOTENV_READ = re.compile(
    r"\b(?:cat|type|more|gc|Get-Content)\b[^|;&\n]*"
    r"(?:^|[\s/\\'\"])\.env(?:\.[A-Za-z0-9_.-]+)?\b",
    re.IGNORECASE,
)


def _strips_values(command: str, shell: str) -> bool:
    """Does the command carry an idiom that provably emits names only?"""
    if any(pattern.search(command) for pattern in _NAME_ONLY):
        return True
    return shell == "powershell" and bool(_PS_NAME_ONLY.search(command))


def _dumping_shape(command: str, shell: str) -> str | None:
    """The offending fragment, or None."""
    if _ENV_FIELD.search(command):
        return "reads the environment block directly"
    if _DOTENV_READ.search(command):
        return "prints a .env file"
    if shell == "powershell" and _PS_DOTENV_READ.search(command):
        return "prints a .env file"
    if _ENV_DUMP.search(command):
        return "dumps every environment variable with its value"
    if shell == "powershell" and _PS_ENV_DUMP.search(command):
        return "dumps every environment variable with its value"
    if _DOCKER_INSPECT.search(command) and not _DOCKER_FORMAT.search(command):
        return "docker inspect returns Config.Env in full"
    return None


def _reason(offender: str, shell: str) -> str:
    if shell == "powershell":
        safe = (
            "    Get-ChildItem env: | Select-Object -ExpandProperty Name\n"
            "    docker exec C sh -c 'env | cut -d= -f1'\n"
            "    docker inspect --format '{{.State.Status}}' C\n\n"
        )
        proceed = "    $env:JARVIS_ENV_DUMP_OK=1; <your command>   (RAILS_ENV_DUMP_OK also works)"
    else:
        safe = (
            "    env | cut -d= -f1                      # which variables exist\n"
            "    docker exec C sh -c 'env | cut -d= -f1'\n"
            "    docker inspect --format '{{.State.Status}}' C\n\n"
        )
        proceed = (
            "    JARVIS_ENV_DUMP_OK=1 <your command>   (RAILS_ENV_DUMP_OK=1 also works)"
        )
    return (
        f"This would print environment VALUES into the transcript — {offender}.\n\n"
        f"That has leaked a live, billable API key twice. A transcript cannot be "
        f"un-read, so the operator pays to rotate the key.\n\n"
        f"You almost certainly want the NAMES, which are safe:\n"
        f"{safe}"
        f"Do NOT write your own redaction filter instead. The last leak had one "
        f'(`sed "s/=.*SECRET.*/=<redacted>/"`); it silently failed to match and '
        f"the key printed anyway. Only name-only idioms are accepted here.\n\n"
        f"If you genuinely need a value, read that ONE variable deliberately and "
        f"say why — or, better, get it from the secrets broker rather than the "
        f"environment.\n\n"
        f"To proceed anyway:\n"
        f"{proceed}"
    )


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command:
        return None
    if overridden(command, *OVERRIDES):
        return None
    offender = _dumping_shape(command, shell)
    if offender is None:
        return None
    # A name-only idiom rescues the BULK shapes, where it is a true substitute.
    # It does not rescue a named reach at the env block itself.
    if _strips_values(command, shell) and not _ENV_FIELD.search(command):
        return None
    return Deny(_reason(offender, shell))
