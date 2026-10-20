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
``arguments(tokens, valued)``
    A command's arguments as it receives them: no redirections, one word per
    substitution or group.

Stdlib only: this runs inside a hook process that starts on every tool call.
An unknown or missing ``shell`` is read as bash.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from rails.shell import bash as _bash
from rails.shell import powershell as _powershell

__all__ = [
    "arguments",
    "expanding",
    "grouped",
    "is_redirect",
    "is_substitution",
    "scrub",
    "segments",
    "spans",
    "scrubbed_segments",
    "words",
]


def _module(shell: str | None):
    return _powershell if shell == "powershell" else _bash


def scrub(command: str, shell: str | None = "bash", comments: bool = False) -> str:
    """With ``comments``, comments are blanked too."""
    return _module(shell).scrub(command, comments)


def expanding(command: str, shell: str | None = "bash") -> str:
    """``command``, SAME LENGTH, with only the text the shell expands left: single-quoted
    text and comments blanked, double-quoted text kept (a `$(...)` runs there). Bodies:
    PowerShell's `@"..."@` is kept and `@'...'@` blanked; bash blanks every heredoc body,
    including an unquoted one bash would expand (a known limit: a `$(...)` written in one is
    not found). Escapes are kept as written: a reader skips the character after one."""
    return _module(shell).expanding(command)


def spans(command: str, shell: str | None = "bash") -> list[tuple[int, int]]:
    """Trimmed (start, end) offsets of each statement that holds any code.

    The cuts are decided with comments blanked too, so a `;` in a comment cuts
    nothing; a statement is kept when it holds code or a comment (overrides).
    """
    scrubbed = _module(shell).scrub(command)
    uncommented = _module(shell).scrub(command, comments=True)
    found: list[tuple[int, int]] = []
    for start, end in _module(shell).spans(command, uncommented):
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
    """``(original, scrubbed)`` for each statement, aligned character for character. The
    scrubbed side has comments blanked too: `git push  # update the PR` pushes no branch
    named `update`. Override tokens (`# merged-ok`) are read from the original."""
    scrubbed = scrub(command, shell, comments=True)
    return [(command[a:b], scrubbed[a:b]) for a, b in spans(command, shell)]


def words(segment: str, shell: str | None = "bash") -> list[str]:
    return _module(shell).words(segment)


#: A redirection operator, longest first, after an optional fd (`2>`), `&` (`&>`) or `*`
#: (PowerShell's `*>`).
_REDIRECT = re.compile(r"(?:\d|\*|&)?(?:<<<|<<-|<<|<>|<&|<|>>|>&|>\||>)")


def is_redirect(tok: str) -> bool:
    """A redirection token (`2>&1`, `>`, `<<EOF`). A token with whitespace in it came from
    quotes, so it is text."""
    return _REDIRECT.match(tok) is not None and not any(ch.isspace() for ch in tok)


def is_substitution(tok: str) -> bool:
    """The whole word is one substitution or group (`$(git branch --show-current)`, a
    backtick pair, PowerShell `(...)`); `HEAD:$(...)-v2` is not."""
    return (
        (tok.startswith("$(") and tok.endswith(")"))
        or (len(tok) > 1 and tok.startswith("`") and tok.endswith("`"))
        or (tok.startswith("(") and tok.endswith(")"))
    )


def takes_target(tok: str) -> bool:
    """A bare redirection operator, whose target is the next word (`> out.txt`, `<< EOF`)."""
    return is_redirect(tok) and _REDIRECT.fullmatch(tok) is not None


def _groups(tokens: list[str]) -> list[str]:
    """Join a substitution or group the tokenizer split (`$(git`, `rev-parse`, `HEAD)`, a
    backtick pair, or PowerShell's `(gh`, ..., `.number)`) back into one word. Only a token
    with no whitespace starts one: a quoted `"a $(b"` is text."""
    out: list[str] = []
    buf: list[str] = []
    depth, tick = 0, False
    for tok in tokens:
        if buf:
            buf.append(tok)
            if tick:
                done = tok.count("`") % 2 == 1
            else:
                depth += tok.count("(") - tok.count(")")
                done = depth <= 0
            if done:
                out.append(" ".join(buf))
                buf, depth, tick = [], 0, False
            continue
        plain = not any(ch.isspace() for ch in tok)
        opens = tok.count("(") - tok.count(")")
        if plain and opens > 0 and ("$(" in tok or tok.startswith("(")):
            buf, depth = [tok], opens
            continue
        if plain and tok.count("`") % 2 == 1:
            buf, tick = [tok], True
            continue
        out.append(tok)
    if buf:
        out.append(" ".join(buf))
    return out


def grouped(tokens: list[str]) -> list[str]:
    """``tokens`` with every substitution or group the tokenizer split joined back into one."""
    return _groups(tokens)


def arguments(tokens: list[str], valued: Iterable[str] = ()) -> list[str]:
    """A command's arguments as it receives them. A substitution or group is one argument
    (`--match-head-commit $(git rev-parse HEAD)`); redirections (`2>&1`, `> out.txt`, `<< EOF`,
    `<<< text`, `*>$null`), their targets and a backgrounding `&` are none. A flag in
    ``valued`` takes the next word as its value, whatever it looks like (`--subject ">"`)."""
    valued = frozenset(valued)
    joined = _groups(tokens)
    out: list[str] = []
    i = 0
    while i < len(joined):
        tok = joined[i]
        if tok in valued:
            out.extend(joined[i : i + 2])
            i += 2
            continue
        if tok == "&":
            i += 1
            continue
        if is_redirect(tok):
            i += 2 if takes_target(tok) else 1
            continue
        out.append(tok)
        i += 1
    return out
