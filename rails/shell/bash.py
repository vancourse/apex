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

A heredoc inside ``$(...)`` is a heredoc there too: the default commit form,
``git commit -m "$(cat <<'EOF' ... EOF)"``, has apostrophes in its body, and
reading one as an opening quote hid every command after the commit.

``scrub(command, comments=True)`` blanks comments as well. ``spans`` is fed
that copy, so a ``;`` or ``&&`` inside a comment cuts nothing.

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
    r"-?[ \t]*(?P<delim>'[^'\n]*'|\"[^\"\n]*\"|\\[A-Za-z_]\w*|[A-Za-z_][^\s;&|<>()'\"`\\]*)"
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


def _skip_double(text: str, i: int, out: list[str] | None = None) -> int:
    """`i` is just after an opening `"`; nested `$(...)` may hold its own quotes. With
    ``out``, a heredoc body inside a nested substitution is blanked there."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == '"':
            return i + 1
        if c == "$" and text.startswith("$(", i):
            i = _skip_subst(text, i + 2, out)
            continue
        if c == "`":
            i = _skip_backtick(text, i + 1)
            continue
        i += 1
    return n


def _skip_subst(text: str, i: int, out: list[str] | None = None) -> int:
    """`i` is just after `$(`; return the index after the matching `)`.

    A heredoc opened in here has its body skipped at the next newline, so an
    apostrophe in it (``gate's``) is text, not a quote that never closes.
    """
    n = len(text)
    depth = 1
    pending: list[str] = []
    while i < n:
        c = text[i]
        if c == "\n" and pending:
            end = _past_bodies(text, i + 1, pending, out)
            pending = []
            # A body whose terminator never comes is not read as one: the scan goes on, so
            # the `)` that closes the substitution still closes it.
            i = end if end is not None else i + 1
            continue
        if c == "\\":
            i += 2
            continue
        if text.startswith("$((", i) or text.startswith("((", i):
            i = _skip_arith(text, i)  # `<<` in here is a shift
            continue
        if text.startswith("<<<", i):
            i += 3
            continue
        if text.startswith("<<", i):
            match = _DELIM.match(text, i + 2)
            if match:
                pending.append(_bare(match.group("delim")))
            i += 2
            continue
        if c == "'":
            i = _skip_single(text, i + 1)
            continue
        if c == '"':
            i = _skip_double(text, i + 1, out)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _past_bodies(text: str, i: int, pending: list[str], out: list[str] | None = None) -> int | None:
    """Inside `$(...)`: where the last of `pending`'s bodies ends, from line `i`. That is the
    newline after its terminator line, or a `)` right after the terminator (`EOF)`), which
    closes the substitution. None when a terminator never comes."""
    n = len(text)
    first = i

    def blank(stop: int) -> None:
        if out is not None:
            for k in range(first, stop):
                out[k] = " "

    for index, bare in enumerate(pending):
        while True:
            j = text.find("\n", i)
            end = n if j < 0 else j
            line = text[i:end].strip()
            if line == bare:
                i = end
                break
            if line.startswith(bare) and line[len(bare) :].lstrip().startswith(")"):
                close = text.index(")", text.index(bare, i) + len(bare))
                blank(close)
                return close
            if j < 0:
                return None
            i = end + 1
        if index < len(pending) - 1:
            i += 1
    blank(i)
    return i


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


def _skip_heredoc_bodies(
    text: str, i: int, pending: list[tuple[str, bool]], out: list[str] | None
) -> int:
    """Blank the bodies (and terminator lines) of `pending`, starting at line `i`;
    with ``out`` None, only find where they end.

    Returns the index of the newline ending the last terminator line, so the
    caller treats it as an ordinary statement separator; or ``len(text)`` when
    a heredoc never terminates — bash reads it to end of input.
    """
    n = len(text)
    first = i
    for index, (bare, in_subst) in enumerate(pending):
        start = i
        found = False
        while i < n:
            j = text.find("\n", i)
            end = n if j < 0 else j
            line = text[i:end].strip()
            if line == bare:
                found = True
                if out is not None:
                    for k in range(start, end):
                        out[k] = " "
                i = end
                break
            if in_subst and line.startswith(bare) and line[len(bare) :].lstrip().startswith(")"):
                # `msg=$(cat <<EOF ... EOF)`: the heredoc of a substitution ends at its `)`,
                # which stays visible to close it
                close = text.index(")", text.index(bare, i) + len(bare))
                if out is not None:
                    # and the newline before the first body: `msg=$(cat <<EOF ... EOF)` is one
                    # statement, so the body is never read as one of its own
                    for k in range(max(first - 1, 0), close):
                        out[k] = " "
                return close
            i = end + 1
        if not found:
            if out is not None:
                for k in range(start, n):
                    out[k] = " "
            return n
        if index < len(pending) - 1 and i < n:
            if out is not None:
                out[i] = " "  # the newline between two bodies separates nothing
            i += 1
    return i


def scrub(command: str, comments: bool = False, quotes: bool = True) -> str:
    """With ``quotes`` False, quoted spans and escapes are kept as written and only heredoc
    bodies (and, with ``comments``, comments) are blanked: what ``words`` tokenizes."""
    out = list(command)
    n = len(command)
    i = 0
    pending: list[tuple[str, bool]] = []
    # Open parens at the top level: `$` for a substitution (`$(`, `<(`, `>(`), `(` for a
    # subshell. Only a heredoc opened inside a substitution may end at `EOF)`.
    opened: list[str] = []

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
                if quotes:
                    blank(i, end)
                i = end
                continue
            i += 2
            continue
        if c == "#" and (i == 0 or command[i - 1] in _WORD_BREAK):
            j = command.find("\n", i)
            end = n if j < 0 else j
            if comments:
                blank(i, end)
            i = end
            continue
        if c == "'":
            end = _skip_single(command, i + 1)
            if quotes:
                blank(i, end)
            i = end
            continue
        if c == "$" and command.startswith("$'", i):
            end = _skip_ansi_c(command, i + 2)
            if quotes:
                blank(i, end)
            i = end
            continue
        if c == '"':
            # kept as written for words, except a heredoc body inside a substitution there
            end = _skip_double(command, i + 1, None if quotes else out)
            if quotes:
                blank(i, end)
            i = end
            continue
        if command.startswith("$((", i) or command.startswith("((", i):
            i = _skip_arith(command, i)
            continue
        if command.startswith(("$(", "<(", ">("), i):
            opened.append("$")
            i += 2
            continue
        if c == "(":
            opened.append("(")
        elif c == ")" and opened:
            opened.pop()
        if command.startswith("<<<", i):
            i += 3
            continue
        if command.startswith("<<", i):
            match = _DELIM.match(command, i + 2)
            if match:
                pending.append((_bare(match.group("delim")), "$" in opened))
            # The delimiter itself is scanned normally: its quotes are blanked
            # like any other quoted span.
            i += 2
            continue
        i += 1
    return "".join(out)


def expanding(command: str) -> str:
    """``command`` with only the text bash expands left: single-quoted and `$'...'` spans,
    heredoc bodies and comments blanked; double-quoted text kept, since bash runs a `$(...)`
    and expands a `$name` inside it (`out="$(gh pr merge 12)"`). Escapes are kept as written
    (`\\$(` is text), so a reader skips the character after a backslash."""
    kept = scrub(command, comments=True, quotes=False)
    out = list(kept)
    n = len(kept)
    i = 0
    while i < n:
        c = kept[i]
        if c == "\\":
            i += 2
            continue
        if c == "'":
            end = _skip_single(kept, i + 1)
            out[i:end] = " " * (end - i)
            i = end
            continue
        if kept.startswith("$'", i):
            end = _skip_ansi_c(kept, i + 2)
            out[i:end] = " " * (end - i)
            i = end
            continue
        if c == '"':
            i += 1  # its inside is scanned like the rest: `'` there is a plain character
            while i < n and kept[i] != '"':
                if kept[i] == "\\":
                    i += 1
                elif kept.startswith("$(", i):
                    i = _skip_subst(kept, i + 2) - 1
                elif kept[i] == "`":
                    i = _skip_backtick(kept, i + 1) - 1
                i += 1
            i += 1
            continue
        i += 1
    return "".join(out)


def heredoc_spans(command: str) -> list[tuple[int, int]]:
    """(start, end) of every heredoc body in ``command``, at the top level or inside a
    substitution (quoted or not)."""
    kept = scrub(command, quotes=False)
    # b: blanked (a body), w: whitespace the body kept, x: anything else
    marks = "".join(
        "b" if c != k else ("w" if c.isspace() else "x") for c, k in zip(command, kept)
    )
    return [(m.start(), m.end()) for m in re.finditer(r"b(?:[bw]*b)?", marks)]


def heredoc_bodies(command: str) -> list[str]:
    """The text of every heredoc body in ``command``. ``words`` never reads a body; the gates
    that judge the text a command sends (a household value in a PR body, a GraphQL mutation)
    read these."""
    return [command[a:b] for a, b in heredoc_spans(command)]


def statement_bodies(command: str, statement: str) -> list[str]:
    """The heredoc bodies ``statement`` owns: those inside its own text (`-f q="$(cat <<'EOF'
    ...)"`), and those it feeds on stdin, which follow it (`--input - <<'EOF'`)."""
    start = command.find(statement)
    if start < 0:
        return heredoc_bodies(statement)
    end = start + len(statement)
    owned: list[str] = []
    reach = end
    for a, b in heredoc_spans(command):
        if start <= a < end:
            owned.append(command[a:b])
        elif a >= reach and not command[reach:a].strip():
            owned.append(command[a:b])
            reach = b
        elif a >= end:
            break
    return owned


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
        if c == "\n" and re.search(r"(?<!\|)\|[ \t\r]*$", scrubbed[start:i]):
            i += 1  # `a |` then `b` on the next line: the pipeline goes on
            continue
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
    """Tokens with quotes removed and comments dropped; str.split if shlex refuses.

    A comment is what ``scrub`` reads as one, so a `#` inside a word is the word's
    (`.../pull/12#issuecomment-1`), as bash reads it. A heredoc body is not words. A line
    continuation joins the lines.
    """
    text = scrub(segment, comments=True, quotes=False)
    text = re.sub(r"\\\r?\n", "", text)
    try:
        return shlex.split(text, comments=False, posix=True)
    except ValueError:
        return text.split()
