"""Bash command text: blank what the shell will not run, split what it will.

Every gate that matches a command line has the same two needs, and before this
module each one met them with its own private regex:

* **quoted text must be invisible.** A commit message *about* a hazard
  necessarily contains the hazard's spelling — ``git commit -m "never git
  stash"`` — and a gate that reads it refuses the commit that documents it.
  ``heredoc_write_gate`` and ``secret_env_gate`` each shipped that defect and
  had it caught on first live use.
* **a separator inside quotes is not a separator.** ``-m "a; git stash"`` is
  one statement, not two.

``scrub`` blanks quoted spans, ``$'...'`` strings and heredoc bodies to spaces
and returns a string of the SAME LENGTH, so an offset found in the scrubbed
text is an offset into the original. Newlines inside a blanked region become
spaces too: that is what stops a multi-line quoted message from splitting into
statements. Comments stay visible (override tokens such as ``# stash-ok`` live
there) but quotes inside a comment are not quotes.

Named limits, all fail-open (text hidden from a deny gate is text allowed):
``$(...)`` inside double quotes is skipped with the string; an unterminated
quote or heredoc hides the rest of the command, which bash would not have run
as written either; ``case`` patterns with a bare ``)`` inside ``$(...)`` can end
the substitution early.
"""

from __future__ import annotations

import re
import shlex

#: The delimiter after ``<<`` or ``<<-``: quoted, backslash-quoted, or bare.
#: Quoted forms first, or ``'EOF'`` would match as nothing.
_DELIM = re.compile(
    r"-?[ \t]*(?P<delim>'[^'\n]*'|\"[^\"\n]*\"|\\[A-Za-z_]\w*|[A-Za-z_]\w*)"
)

#: A backslash before one of these is blanked with it: an escaped separator or
#: quote must neither split a statement nor open a string. Other escapes stay
#: visible, so a Windows path typed unquoted (``C:\Users\x``) keeps its shape.
_ESCAPE_BLANK = frozenset(";&|'\"\n\r<>`")

#: Characters after which a ``#`` starts a comment.
_WORD_BREAK = frozenset(" \t\n\r;&|()")


def _bare(delim: str) -> str:
    if delim[0] in "'\"":
        return delim[1:-1]
    if delim[0] == "\\":
        return delim[1:]
    return delim


def _skip_single(text: str, i: int) -> int:
    """`i` is just after an opening `'`; return the index after the closing one."""
    j = text.find("'", i)
    return len(text) if j < 0 else j + 1


def _skip_ansi_c(text: str, i: int) -> int:
    """`$'...'`, where a backslash escapes the next character."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            return i + 1
        i += 1
    return n


def _skip_backtick(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        i += 1
    return n


def _skip_double(text: str, i: int) -> int:
    """`i` is just after an opening `"`; nested `$(...)` may hold its own quotes."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        if c == "$" and text.startswith("$(", i):
            i = _skip_subst(text, i + 2)
            continue
        if c == "`":
            i = _skip_backtick(text, i + 1)
            continue
        i += 1
    return n


def _skip_subst(text: str, i: int) -> int:
    """`i` is just after `$(`; return the index after the matching `)`."""
    n = len(text)
    depth = 1
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            i = _skip_single(text, i + 1)
            continue
        if c == '"':
            i = _skip_double(text, i + 1)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _skip_arith(text: str, i: int) -> int:
    """`((...))` / `$((...))`: `<<` in here is a shift, never a heredoc.

    Returns the index after the closing parens, or just past the opener when
    they never balance (then the text is scanned normally).
    """
    start = i + 1 if text[i] == "$" else i
    depth = 0
    j = start
    n = len(text)
    while j < n:
        c = text[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        elif c == "\n":
            break
        j += 1
    return start + 2


def _skip_heredoc_bodies(text: str, i: int, pending: list[str], out: list[str]) -> int:
    """Blank the bodies (and terminator lines) of `pending`, starting at line `i`.

    Returns the index of the newline ending the last terminator line, so the
    caller treats it as an ordinary statement separator; or ``len(text)`` when
    a heredoc never terminates — bash reads it to end of input.
    """
    n = len(text)
    for index, bare in enumerate(pending):
        start = i
        found = False
        while i < n:
            j = text.find("\n", i)
            end = n if j < 0 else j
            if text[i:end].strip() == bare:
                found = True
                for k in range(start, end):
                    out[k] = " "
                i = end
                break
            i = end + 1
        if not found:
            for k in range(start, n):
                out[k] = " "
            return n
        if index < len(pending) - 1 and i < n:
            out[i] = " "  # the newline between two bodies separates nothing
            i += 1
    return i


def scrub(command: str) -> str:
    out = list(command)
    n = len(command)
    i = 0
    pending: list[str] = []

    def blank(a: int, b: int) -> None:
        for k in range(a, b):
            out[k] = " "

    while i < n:
        c = command[i]
        if c == "\n":
            if pending:
                i = _skip_heredoc_bodies(command, i + 1, pending, out)
                pending = []
                if i < n and command[i] == "\n":
                    i += 1
                continue
            i += 1
            continue
        if c == "\\":
            if i + 1 < n and command[i + 1] in _ESCAPE_BLANK:
                end = i + 2
                if command[i + 1] == "\r" and end < n and command[end] == "\n":
                    end += 1
                blank(i, end)
                i = end
                continue
            i += 2
            continue
        if c == "#" and (i == 0 or command[i - 1] in _WORD_BREAK):
            j = command.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "'":
            end = _skip_single(command, i + 1)
            blank(i, end)
            i = end
            continue
        if c == "$" and command.startswith("$'", i):
            end = _skip_ansi_c(command, i + 2)
            blank(i, end)
            i = end
            continue
        if c == '"':
            end = _skip_double(command, i + 1)
            blank(i, end)
            i = end
            continue
        if command.startswith("$((", i) or command.startswith("((", i):
            i = _skip_arith(command, i)
            continue
        if command.startswith("<<<", i):
            i += 3
            continue
        if command.startswith("<<", i):
            match = _DELIM.match(command, i + 2)
            if match:
                pending.append(_bare(match.group("delim")))
            # The delimiter itself is scanned normally: its quotes are blanked
            # like any other quoted span.
            i += 2
            continue
        i += 1
    return "".join(out)


def spans(command: str, scrubbed: str) -> list[tuple[int, int]]:
    """Offsets of each top-level statement, decided on the scrubbed text.

    Splits on newline, ``;``, ``&&``, ``||`` and a backgrounding ``&``; the
    ``&`` stays at the end of the statement it backgrounds, because whether a
    statement is detached is something gates need to see. ``2>&1``, ``&>``,
    ``>&2`` and ``|&`` are redirections, not separators. Pipelines stay whole.
    """
    n = len(scrubbed)
    cuts: list[tuple[int, int]] = []
    start = 0
    i = 0
    while i < n:
        c = scrubbed[i]
        if c in "\n;":
            cuts.append((start, i))
            start = i + 1
            i += 1
            continue
        if scrubbed.startswith("&&", i) or scrubbed.startswith("||", i):
            cuts.append((start, i))
            start = i + 2
            i += 2
            continue
        if c == "&":
            prev = scrubbed[i - 1] if i else ""
            nxt = scrubbed[i + 1] if i + 1 < n else ""
            if prev in ("<", ">", "|") or nxt == ">":
                i += 1
                continue
            cuts.append((start, i + 1))
            start = i + 1
            i += 1
            continue
        i += 1
    cuts.append((start, n))
    return cuts


def words(segment: str) -> list[str]:
    """Tokens with quotes removed and comments dropped; str.split if shlex refuses."""
    try:
        return shlex.split(segment, comments=True, posix=True)
    except ValueError:
        return segment.split()
