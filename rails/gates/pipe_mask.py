"""Refuse a status-bearing command whose trailing pipe masks its exit code.

Ported from jarvis ``.claude/hooks/pipe_mask_gate.py`` (720 denials in 229
sessions). The commands it stops look like these, and both shapes have
produced real incidents::

    uv run pytest -q ci/ 2>&1 | tail -40      # pytest exited 4; tail exited 0
    gh pr edit 123 --body-file b.md | tail -2 # the edit failed; the body was lost

In ``A | B`` the pipeline's status is B's. A filter like ``tail`` exits 0 after
reading anything at all, so the failure of A is not merely hidden — it is
*replaced* with a success. Measured on 2026-08-10: a task notification reported
exit 0 twice while the real codes were 4 (pytest rejected its own arguments and
ran zero tests) and 124 (killed at a timeout); the same session lost a freshly
written PR body to a piped ``gh pr edit`` whose failure nothing reported.

**Keyed on BOTH halves, never one.** Piping to ``tail`` is legitimate constantly
— read-only commands pass untouched however they are piped. A denial needs a
status-bearing command (``git push``/``commit``, ``gh pr``/``issue`` mutations,
``pytest``) AND a trailing filter in the same statement. ``set -o pipefail``
anywhere in the command allows it wholesale: that is the documented remedy, and
a gate that refuses its own remedy teaches people to disable it.

**PowerShell** (new in the port). A native filter (``tail``, ``grep``,
``findstr``) at the end replaces ``$LASTEXITCODE`` exactly as in bash. The
PowerShell cmdlet filters are listed too, for a different reason, measured on
Windows PowerShell 5.1 on 2026-10-06: ``native | Select-Object -First 1``
stopped the native process after its first line — its remaining work never ran
and ``$LASTEXITCODE`` read -1 — while ``Select-String``, ``Measure-Object``,
``Out-String`` and ``-Last`` keep the exit code but discard the output that
would explain a failure.

**Quoted spans and heredoc bodies are invisible on purpose** (``rails.shell.
scrub``). A commit message *about* this trap necessarily contains the text
``pytest | tail``; scanning it would refuse the very commit that documents the
gate. The price is a named limitation: a pipeline nested inside a quoted
``sh -c '...'`` string is not seen. Fail-open is the bias throughout.

The override, matched against the command TEXT (a PreToolUse hook runs before
the proposed command's shell exists) and against the hook's own environment::

    JARVIS_PIPE_OK=1 <your command>          # bash; RAILS_PIPE_OK is an alias
    $env:JARVIS_PIPE_OK=1; <your command>    # PowerShell
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell import scrubbed_segments
from rails.shell.override import overridden

NAME = "pipe_mask"

OVERRIDES = ("JARVIS_PIPE_OK", "RAILS_PIPE_OK")

#: Commands whose EXIT CODE is the payload. Deliberately short: `gh pr view`,
#: `git log`, `grep` and every other read emits its answer on stdout, so piping
#: it filters data, not evidence. These emit evidence.
#:
#: `pytest` must be the COMMAND WORD — first in its statement or pipe stage,
#: optionally behind `VAR=x`, `uv run [flags]` / `poetry run` / `uvx`, a path,
#: or `python -m`. The original's bare `\bpytest\b` refused
#: `cat pytest.ini | tail -3` (measured 2026-10-06, live): the word inside a
#: FILENAME is not a test run.
_STATUS_BEARING = re.compile(
    r"\bgit\s+(?:push|commit)\b"
    r"|\bgh\s+pr\s+(?:create|edit|merge|close)\b"
    r"|\bgh\s+issue\s+(?:create|edit)\b"
    r"|(?:^|[|&(]\s*)(?:\w+=\S*\s+)*"
    r"(?:(?:uv|poetry|pipenv|pdm|hatch)\s+run\s+(?:-{1,2}[\w-]+(?:[= ]\S+)?\s+)*"
    r"|uvx\s+|time\s+)?"
    r"(?:(?:\S*[/\\])?(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?\s+-m\s+)?"
    r"(?:\S*[/\\])?pytest(?:\.exe)?\b(?![.\w-])"
)

#: A pipe into a filter, at or after the status-bearing command in the same
#: segment. `tee` is excluded on purpose: it re-emits everything it reads, so
#: the evidence survives even though the status still lies — refusing it would
#: catch no observed incident and block a legitimate logging idiom.
_TRAILING_FILTER = re.compile(r"\|\s*(?:head|tail|grep|wc|sed|awk)\b")

#: The same in PowerShell: the native filters above (Git for Windows puts them
#: on PATH), `findstr`, and the cmdlets that truncate or swallow the evidence.
#: Case-insensitive, as PowerShell is; aliases included (`select`, `sls`,
#: `measure`, `oss`).
_PS_TRAILING_FILTER = re.compile(
    r"\|\s*(?:head|tail|grep|wc|sed|awk|findstr"
    r"|(?:Select-Object|select)\b[^|]*?\s-(?:fi|la)\w*"
    r"|Select-String|sls|Measure-Object|measure|Out-String|oss)\b",
    re.IGNORECASE,
)


def _masked(command: str, shell: str) -> str | None:
    """The offending statement, or None. Quoted spans are blanked first."""
    trailing = _PS_TRAILING_FILTER if shell == "powershell" else _TRAILING_FILTER
    for raw, scrubbed in scrubbed_segments(command, shell):
        status = _STATUS_BEARING.search(scrubbed)
        if not status:
            continue
        if trailing.search(scrubbed, status.end()):
            return " ".join(raw.split())[:160]
    return None


def _bash_reason(offender: str) -> str:
    return (
        f"This pipes a command whose EXIT CODE is the point into a filter that\n"
        f"replaces it with its own:\n"
        f"    {offender}\n\n"
        f"`tail`/`head`/`grep` exit 0 after reading anything, so a failure here is\n"
        f"not hidden — it is reported as success. Measured: pytest exited 4 (ran\n"
        f"zero tests) and 124 (killed at timeout) while the notification said 0;\n"
        f"a piped `gh pr edit` failure silently deleted a finished PR body.\n\n"
        f"Pick one:\n"
        f"    set -o pipefail; <your command>     # status of the whole pipeline\n"
        f"    <command> > out.txt; tail out.txt   # split: evidence, then filter\n"
        f"    <command>                           # gh/git output is short anyway\n\n"
        f"If the masked status is genuinely irrelevant here:\n"
        f"    JARVIS_PIPE_OK=1 <your command>     (RAILS_PIPE_OK=1 also works)"
    )


def _powershell_reason(offender: str) -> str:
    return (
        f"This pipes a command whose EXIT CODE is the point into a filter:\n"
        f"    {offender}\n\n"
        f"A native filter (`tail`/`grep`/`findstr`) at the end replaces\n"
        f"$LASTEXITCODE with its own 0. `Select-Object -First N` is worse: measured\n"
        f"on Windows PowerShell 5.1, it stopped the native command after N lines —\n"
        f"its remaining work never ran and $LASTEXITCODE read -1. `Select-String`,\n"
        f"`Measure-Object`, `Out-String` and `-Last` keep the code but discard the\n"
        f"output that would explain a failure. Measured in bash: pytest exited 4\n"
        f"while the notification said 0; a piped `gh pr edit` failure silently\n"
        f"deleted a finished PR body.\n\n"
        f"Pick one:\n"
        f'    <command> *> out.txt; $code = $LASTEXITCODE; Get-Content out.txt -Tail 40; "exit=$code"\n'
        f"    <command>                           # gh/git output is short anyway\n\n"
        f"If the masked status is genuinely irrelevant here:\n"
        f"    $env:JARVIS_PIPE_OK=1; <your command>     (RAILS_PIPE_OK also works)"
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
    # The documented remedy. A command that already opted in is correct.
    if "set -o pipefail" in command:
        return None
    offender = _masked(command, shell)
    if offender is None:
        return None
    if shell == "powershell":
        return Deny(_powershell_reason(offender))
    return Deny(_bash_reason(offender))
