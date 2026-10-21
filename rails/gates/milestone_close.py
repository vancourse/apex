"""A milestone closes through `rails close`, never a raw API call (design R18).

`rails close N` closes milestone N only when the operator recorded ``used #N`` and no issue
is open: done is the operator using it, not the issue count reaching zero. An agent command
that writes ``state=closed`` to a milestone skips both and is refused (both shells), however
it is spelled: ``gh api`` or ``curl``; a number or any variable (``milestones/$N``,
``milestones/"$N"``, ``milestones/$($m.number)``); ``PATCH``, or the ``POST`` GitHub accepts
for it (``gh api`` sends POST when given fields); the state inline, in an ``--input`` file,
or piped into ``--input -`` (``cat f |``, ``Get-Content f |``, ``< f``). Piping from a
source it cannot read is refused too: write the body to a file and name it.

Only a statement that writes is judged (a write method, or a body: gh's field flags and
``--input``, curl's data flags), so reads are allowed: ``-X GET``, a plain ``gh api`` with a
``--jq`` that mentions "closed", listing closed ones (``milestones?state=closed``), and a
``--state closed`` in another statement. Changing a title or description is allowed too (an operator correction is
written into the milestone description, and that goes through this API). A statement that
runs a script file (``python x.py``, ``uv run python x.py``, ``bash x.sh``, ``pwsh -File x.ps1``,
``./x.sh``, ``& ./x.ps1``) is judged by the script's text: one that names a milestone, writes
and sets ``state`` to closed is refused like the command would be (p3j). What it cannot see: a
closed state assembled at run time, or a script it cannot read. Shadow-first, like every new
deny.
"""

from __future__ import annotations

import re
from pathlib import Path

from rails.hookio import Deny, Event

NAME = "milestone_close"

_MILESTONE = re.compile(r"milestones/(\S+)")
_GET = re.compile(r"(?:-X|--method)[=\s]+['\"]?GET\b", re.IGNORECASE)
#: A statement that writes: an explicit write method, or a body (gh's field flags and --input,
#: curl's data flags). Without one, `gh api` and curl send GET - a `--jq` that mentions
#: "closed" is a read (review of 1.3.0).
_WRITES = re.compile(
    r"(?:-X|--method|--request)[=\s]*['\"]?(?:PATCH|POST|PUT)\b|['\"](?:PATCH|POST|PUT)['\"]|"
    r"\s(?:-f|-F|--field|--raw-field|--input|-d|--data(?:-raw|-binary|-urlencode)?|--json)(?=[\s=])|"
    r"\s-[fFd]\S|-Method\s+['\"]?(?:Patch|Post|Put)\b|\s-Body\b|\.(?:patch|post|put)\s*\(|\b(?:json|data)\s*=",
    re.IGNORECASE,
)
_CLOSED = re.compile(r"state\W{0,6}closed\b", re.IGNORECASE)
_INPUT = re.compile(r"--input[=\s]+['\"]?([^\s'\"]+)")
_STDIN_SOURCE = re.compile(
    r"(?:\b(?:cat|type|Get-Content|gc)\s+['\"]?([^\s'\"|;]+)['\"]?[^|;\n]*\||<\s*['\"]?([^\s'\"|;]+))",
    re.IGNORECASE,
)


def _reads_closed(evt: Event, name: str) -> bool | None:
    path = Path(name)
    if not path.is_absolute() and evt.cwd is not None:
        path = evt.cwd / path
    try:
        return bool(_CLOSED.search(path.read_text(encoding="utf-8", errors="replace")))
    except OSError:
        return None


def _input_closes(evt: Event, command: str) -> bool:
    for name in _INPUT.findall(command):
        if name == "-":
            sources = [a or b for a, b in _STDIN_SOURCE.findall(command)]
            if not sources:
                return True  # a body from somewhere it cannot read: fail closed
            if any(_reads_closed(evt, s) is not False for s in sources):
                return True
            continue
        if _reads_closed(evt, name) is not False:  # unreadable (`$env:TEMP\\c.json`): fail closed
            return True
    return False


_SCRIPT = re.compile(r"\.(?:py|sh|bash|ps1|psm1)$", re.IGNORECASE)
_TEST_FILE = re.compile(r"(?:^|[/\\])(?:tests?[/\\]|test_[^/\\]*$|conftest\.py$)")
#: An HTTP write in a script's text: a write method named, a write call, or gh's
#: body flags as tokens. (`data =` is any assignment in Python, not a write.)
_SCRIPT_WRITES = re.compile(
    r"\b(?:PATCH|POST|PUT)\b|\.(?:patch|post|put)\s*\(|['\"](?:-f|-F|--field|--raw-field|--input)['\"]"
    r"|\s(?:-f|-F|--field|--raw-field|--input)\s"
)
_RUNNERS = {"python", "python3", "py", "uv", "bash", "sh", "zsh", "pwsh", "powershell", "&", "."}
#: `uv run` options that take a value.
_UV_VALUED = frozenset(
    {"--with", "--with-requirements", "--with-editable", "--python", "-p", "--project", "--directory",
     "--package", "--env-file", "--extra", "--group", "--index", "--only-group"}
)


def _scripts(evt: Event, command: str) -> list[Path]:
    """The script files a command runs: the first argument naming one after a runner
    (``python``, ``uv run python``, ``bash``, ``pwsh -File``, ``&``), or a statement that is
    itself a script path (``./x.sh``)."""
    from rails.gates.destructive import command_name, commands

    found: list[Path] = []
    try:
        parsed = commands(command, evt.shell or "bash")
    except Exception:  # noqa: BLE001
        return found
    for _, tokens in parsed:
        if not tokens:
            continue
        head = command_name(tokens[0])
        candidates = tokens[1:] if head in _RUNNERS else tokens[:1]
        # `python -m pytest tests/x.py`: -m names the program, and what follows are its
        # arguments; a test file is never the script that runs.
        stop = next((i for i, tok in enumerate(candidates) if tok in ("-m", "-c", "run")), None)
        if stop is not None and head != "uv":
            candidates = candidates[:stop]
        if head == "uv":
            # `uv run [opts] x.py`, or `uv run [opts] python[3] x.py`; anything else uv runs
            # (`uv run pytest ...`) names a program, not a script.
            after = candidates[candidates.index("run") + 1 :] if "run" in candidates else []
            i = 0
            while i < len(after) and after[i].startswith("-"):
                i += 2 if after[i] in _UV_VALUED else 1
            after = after[i:]
            if after and command_name(after[0]) in ("python", "python3", "py"):
                after = after[1:]
                candidates = after[: next((j for j, tok in enumerate(after) if tok in ("-m", "-c")), len(after))]
            else:
                candidates = after[:1]
        for tok in candidates:
            if _SCRIPT.search(tok.strip("'\"")) and not _TEST_FILE.search(tok):
                path = Path(tok.strip("'\""))
                if not path.is_absolute() and evt.cwd is not None:
                    path = evt.cwd / path
                found.append(path)
                break
    return found


def _script_closes(evt: Event, command: str) -> str | None:
    """The first script the command runs that writes a closed state to a milestone."""
    for path in _scripts(evt, command):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "milestones" in text and _CLOSED.search(text) and _SCRIPT_WRITES.search(text):
            return path.name
    return None


def _statements(evt: Event, command: str) -> list[str]:
    from rails.shell import segments

    try:
        return segments(command, evt.shell or "bash") or [command]
    except Exception:  # noqa: BLE001
        return [command]


def check(evt: Event):
    command = evt.command or ""
    lowered = command.lower()
    script = (
        _script_closes(evt, command)
        if any(ext in lowered for ext in (".py", ".sh", ".ps1", ".bash", ".psm1"))
        else None
    )
    if script:
        return Deny(
            f"rails: {script} writes state=closed to a milestone. Close it with `rails close <n>` - "
            "it closes only when the operator said `used #<n> <task>` and no issue is open."
        )
    if "milestones/" not in command:
        return None
    named = _MILESTONE.search(command)
    for statement in _statements(evt, command):
        # the endpoint may be a variable set in an earlier statement (`U=.../milestones/75; gh api $U`)
        m = _MILESTONE.search(statement) or named
        if not m or _GET.search(statement) or not _WRITES.search(statement):
            continue
        # a pipe feeding `--input -` lives in the same statement, so the source is found
        if not (_CLOSED.search(statement) or _input_closes(evt, statement)):
            continue
        n = m.group(1).strip("'\")")
        n = n if n.isdigit() else "<n>"
        return Deny(
            f"rails: close milestone {n} with `rails close {n}` - it closes only when the operator said "
            "`used #<n> <task>` and no issue is open. A raw API write of state=closed skips both."
        )
    return None
