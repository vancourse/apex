"""Reading a shell command line the way the shell will, closely enough for a gate.

Three questions every command-matching gate asks, answered once for both shells
the harness runs (``Bash`` and ``PowerShell`` tool calls):

``scrub(command, shell)``
    The command with quoted spans and heredoc / here-string bodies blanked to
    spaces, SAME LENGTH as the input, so a regex cannot match inside a quoted
    commit message and an offset in the result is an offset in the original.
``segments(command, shell)``
    The top-level statements, as slices of the ORIGINAL text. Splitting is
    decided on the scrubbed text, so a ``;`` inside quotes splits nothing.
    Pipelines stay inside one statement; a backgrounding ``&`` stays at the end
    of the statement it backgrounds.
``words(segment, shell)``
    Tokens with quoting removed.

Stdlib only: this runs inside a hook process that starts on every tool call.
An unknown or missing ``shell`` is read as bash.
"""

from __future__ import annotations

from rails.shell import bash as _bash
from rails.shell import powershell as _powershell

__all__ = ["scrub", "segments", "spans", "scrubbed_segments", "words"]


def _module(shell: str | None):
    return _powershell if shell == "powershell" else _bash


def scrub(command: str, shell: str | None = "bash") -> str:
    return _module(shell).scrub(command)


def spans(command: str, shell: str | None = "bash") -> list[tuple[int, int]]:
    """Trimmed (start, end) offsets of each statement that holds any code."""
    scrubbed = _module(shell).scrub(command)
    found: list[tuple[int, int]] = []
    for start, end in _module(shell).spans(command, scrubbed):
        if not scrubbed[start:end].strip():
            continue  # only quoted text or a heredoc body: nothing runs here
        while start < end and command[start].isspace():
            start += 1
        while end > start and command[end - 1].isspace():
            end -= 1
        found.append((start, end))
    return found


def segments(command: str, shell: str | None = "bash") -> list[str]:
    return [command[a:b] for a, b in spans(command, shell)]


def scrubbed_segments(
    command: str, shell: str | None = "bash"
) -> list[tuple[str, str]]:
    """``(original, scrubbed)`` for each statement, aligned character for character."""
    scrubbed = scrub(command, shell)
    return [(command[a:b], scrubbed[a:b]) for a, b in spans(command, shell)]


def words(segment: str, shell: str | None = "bash") -> list[str]:
    return _module(shell).words(segment)
