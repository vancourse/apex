"""PowerShell command text: the same two needs as ``bash.py``, a different grammar.

Measured in October 2026, PowerShell carried 26 of 40 ``git push`` / ``gh pr``
commands on the box this plugin was built on, and 11 of the 12 deny hooks it
replaces matched ``Bash`` only — so the documented workaround for one broken
hook (use PowerShell) bypassed every other one. Reading PowerShell is
therefore not optional, and it cannot be done with ``shlex``:

* ``'...'`` is literal, and ``''`` inside it is one quote;
* ``"..."`` expands, a backtick escapes the next character, ``""`` is one
  quote, and ``$( ... )`` inside it may hold quotes of its own;
* here-strings ``@'`` / ``@"`` run to a ``'@`` / ``"@`` at COLUMN 0;
* the backtick is the escape character everywhere, and a backtick before a
  newline continues the line;
* ``&`` at the start of a statement is the call operator, not a separator;
* ``#`` starts a comment only at the start of a token, ``<# ... #>`` is a
  block comment.

``scrub`` blanks quoted spans, here-strings (markers included) and backtick
escapes to spaces, keeping the length. ``words`` returns tokens with quoting
removed, keeping ``$( ... )`` / ``@( ... )`` / ``@{ ... }`` / ``{ ... }`` as one
token each, ``@args`` (splatting) as written, and ``&`` / ``|`` as tokens of
their own.
"""

from __future__ import annotations

#: Characters after which `#` starts a comment.
_TOKEN_BREAK = frozenset(" \t\n\r;|&(){}")

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "a": "\a", "b": "\b"}


def _skip_single(text: str, i: int) -> int:
    """`i` is just after an opening `'`; `''` is an escaped quote."""
    n = len(text)
    while i < n:
        j = text.find("'", i)
        if j < 0:
            return n
        if j + 1 < n and text[j + 1] == "'":
            i = j + 2
            continue
        return j + 1
    return n


def _skip_double(text: str, i: int) -> int:
    """`i` is just after an opening `"`; backtick and `""` escape, `$(` nests."""
    n = len(text)
    while i < n:
        c = text[i]
        if c == "`":
            i += 2
            continue
        if c == '"':
            if i + 1 < n and text[i + 1] == '"':
                i += 2
                continue
            return i + 1
        if c == "$" and text.startswith("$(", i):
            i = _skip_group(text, i + 1)
            continue
        i += 1
    return n


def _skip_group(text: str, i: int) -> int:
    """`text[i]` is `(` or `{`; return the index after its match."""
    opener = text[i]
    closer = ")" if opener == "(" else "}"
    n = len(text)
    depth = 0
    while i < n:
        c = text[i]
        if c == "`":
            i += 2
            continue
        if c == "'":
            i = _skip_single(text, i + 1)
            continue
        if c == '"':
            i = _skip_double(text, i + 1)
            continue
        if c == "@" and _here_opens(text, i):
            i = _here_end(text, i)
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _here_opens(text: str, i: int) -> bool:
    """`@'` / `@"` followed by nothing but whitespace to the end of its line."""
    if i + 1 >= len(text) or text[i] != "@" or text[i + 1] not in "'\"":
        return False
    j = i + 2
    while j < len(text) and text[j] in " \t\r":
        j += 1
    return j < len(text) and text[j] == "\n"


def _here_end(text: str, i: int) -> int:
    """Index after the here-string opened at `i`; its closer sits at column 0."""
    closer = "\n" + text[i + 1] + "@"
    j = text.find(closer, i + 2)
    return len(text) if j < 0 else j + len(closer)


def scrub(command: str, comments: bool = False) -> str:
    """With ``comments``, line and block comments are blanked too (``spans`` reads that)."""
    out = list(command)
    n = len(command)
    i = 0

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            out[k] = " "

    while i < n:
        c = command[i]
        if c == "`":
            end = i + 2
            if command.startswith("`\r\n", i):
                end = i + 3
            blank(i, end)
            i = end
            continue
        if command.startswith("<#", i):
            j = command.find("#>", i + 2)
            end = n if j < 0 else j + 2
            if comments:
                blank(i, end)
            i = end
            continue
        if c == "#" and (i == 0 or command[i - 1] in _TOKEN_BREAK):
            j = command.find("\n", i)
            end = n if j < 0 else j
            if comments:
                blank(i, end)
            i = end
            continue
        if c == "@" and _here_opens(command, i):
            end = _here_end(command, i)
            blank(i, end)
            i = end
            continue
        if c == "'":
            end = _skip_single(command, i + 1)
            blank(i, end)
            i = end
            continue
        if c == '"':
            end = _skip_double(command, i + 1)
            blank(i, end)
            i = end
            continue
        i += 1
    return "".join(out)


def here_string_spans(command: str) -> list[tuple[int, int]]:
    """(start, end) of every here-string body in ``command``: the lines between `@'` / `@"`
    and the closer at column 0. Quoted strings and comments are skipped, as ``scrub`` does."""
    found: list[tuple[int, int]] = []
    n = len(command)
    i = 0
    while i < n:
        c = command[i]
        if c == "`":
            i += 2
            continue
        if command.startswith("<#", i):
            j = command.find("#>", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "#" and (i == 0 or command[i - 1] in _TOKEN_BREAK):
            j = command.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "@" and _here_opens(command, i):
            start = command.find("\n", i) + 1
            closer = command.find("\n" + command[i + 1] + "@", i + 2)
            if closer < 0:
                found.append((start, n))  # never closed: the rest is its body
                break
            found.append((start, max(start, closer)))  # an empty `@'\n'@` has an empty body
            i = closer + 3
            continue
        if c == "'":
            i = _skip_single(command, i + 1)
            continue
        if c == '"':
            i = _skip_double(command, i + 1)
            continue
        i += 1
    return found


def here_string_bodies(command: str) -> list[str]:
    """The text of every here-string body: what the gates that judge the text a command sends
    read when the body reaches gh through a variable or a pipe."""
    return [command[a:b] for a, b in here_string_spans(command) if command[a:b].strip()]


def expanding(command: str) -> str:
    """``command`` with only the text PowerShell expands left: single-quoted strings,
    `@'...'@` here-strings and comments blanked; double-quoted strings and `@"..."@` kept,
    since PowerShell runs a `$(...)` and expands a `$name` inside them. A backtick escapes
    the character after it, so a reader skips that character."""
    out = list(command)
    n = len(command)

    def blank(a: int, b: int) -> None:
        out[a:b] = " " * (b - a)

    i = 0
    while i < n:
        c = command[i]
        if c == "`":
            i += 2
            continue
        if command.startswith("<#", i):
            j = command.find("#>", i + 2)
            end = n if j < 0 else j + 2
            blank(i, end)
            i = end
            continue
        if c == "#" and (i == 0 or command[i - 1] in _TOKEN_BREAK):
            j = command.find("\n", i)
            end = n if j < 0 else j
            blank(i, end)
            i = end
            continue
        if c == "@" and _here_opens(command, i):
            end = _here_end(command, i)
            if command[i + 1] == "'":
                blank(i, end)
            i = end
            continue
        if c == "'":
            end = _skip_single(command, i + 1)
            blank(i, end)
            i = end
            continue
        if c == '"':
            i = _skip_double(command, i + 1)
            continue
        i += 1
    return "".join(out)


def _top_groups(text: str, opener: str) -> list[tuple[int, int, bool]]:
    """(start, end, closed) of each top-level `opener` group in RAW statement text, read the
    way the shell reads it: quoted strings, here-strings, comments and escapes are text, and a
    `$(...)` subexpression is skipped whole (the caller finds those)."""
    found: list[tuple[int, int, bool]] = []
    n = len(text)
    closer = ")" if opener == "(" else "}"
    i = 0
    while i < n:
        c = text[i]
        if c == "`":
            i += 2
            continue
        if text.startswith("<#", i):
            j = text.find("#>", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "#" and (i == 0 or text[i - 1] in _TOKEN_BREAK):
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "@" and _here_opens(text, i):
            i = _here_end(text, i)
            continue
        if c == "'":
            i = _skip_single(text, i + 1)
            continue
        if c == '"':
            i = _skip_double(text, i + 1)
            continue
        if c == "$" and text.startswith("$(", i):
            i = _skip_group(text, i + 1)
            continue
        if c in "({":
            end = _skip_group(text, i)
            # `${var}` and `@{hashtable}` hold no statements; `@(...)` runs its commands.
            wanted = c == opener and not (i > 0 and text[i - 1] == "$") and not (c == "{" and i > 0 and text[i - 1] == "@")
            if wanted:
                found.append((i, end, text[end - 1 : end] == closer))
            i = end
            continue
        i += 1
    return found


def blocks(statement: str) -> list[str]:
    """The text of each script block a RAW statement holds: `{ a; b }`, one glued to its
    condition (`if($?){gh pr merge 12}`), and the unclosed first piece of a block a `;` cut
    (`if ($?) { gh pr merge 12 --auto`). Its statements run. Braces inside quoted text, a
    here-string or a comment are text, and a `${var}` or an `@{hashtable}` is not a block."""
    out = []
    for start, end, closed in _top_groups(statement, "{"):
        inner = statement[start + 1 : end - 1 if closed else end]
        if inner.strip():
            out.append(inner)
    return out


def groups(statement: str) -> list[str]:
    """The text of each top-level `( ... )` group a RAW statement holds (`$u = (gh pr create
    ...)`, `@(...)`): PowerShell runs a command written inside one."""
    out = []
    for start, end, closed in _top_groups(statement, "("):
        inner = statement[start + 1 : end - 1 if closed else end]
        if inner.strip():
            out.append(inner)
    return out


def spans(command: str, scrubbed: str) -> list[tuple[int, int]]:
    """Statement offsets: newline, `;`, `&&`, `||` (PowerShell 7) split, inside a `{ }` block
    too, so every gate reading statements sees each of a block's statements on its own
    (`if ($?) { a; b }` is `if ($?) { a` and `b }`; `blocks` opens the unclosed first piece).

    A lone `&` never splits: at the start of a statement it is the call
    operator, and at the end it backgrounds the statement it ends, which is
    where gates need to see it.
    """
    n = len(scrubbed)
    cuts: list[tuple[int, int]] = []
    start = 0
    i = 0
    while i < n:
        c = scrubbed[i]
        if c == "\n" and scrubbed[start:i].rstrip(" \t\r").endswith("|") and not scrubbed[
            start:i
        ].rstrip(" \t\r").endswith("||"):
            i += 1  # `@'...'@ |` then `gh ...` on the next line: the pipeline goes on
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
        i += 1
    cuts.append((start, n))
    return cuts


def _read_double(text: str, i: int) -> tuple[str, int]:
    """Content of a `"..."` starting just after the quote, and the index after it."""
    n = len(text)
    buf: list[str] = []
    while i < n:
        c = text[i]
        if c == "`" and i + 1 < n:
            nxt = text[i + 1]
            buf.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        if c == '"':
            if i + 1 < n and text[i + 1] == '"':
                buf.append('"')
                i += 2
                continue
            return "".join(buf), i + 1
        if c == "$" and text.startswith("$(", i):
            end = _skip_group(text, i + 1)
            buf.append(text[i:end])
            i = end
            continue
        buf.append(c)
        i += 1
    return "".join(buf), n


def _read_single(text: str, i: int) -> tuple[str, int]:
    n = len(text)
    buf: list[str] = []
    while i < n:
        c = text[i]
        if c == "'":
            if i + 1 < n and text[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            return "".join(buf), i + 1
        buf.append(c)
        i += 1
    return "".join(buf), n


def words(segment: str) -> list[str]:
    tokens: list[str] = []
    buf: list[str] = []
    started = False
    n = len(segment)
    i = 0

    def flush() -> None:
        nonlocal buf, started
        if started:
            tokens.append("".join(buf))
        buf = []
        started = False

    while i < n:
        c = segment[i]
        if c in " \t\r\n":
            flush()
            i += 1
            continue
        if not started and segment.startswith("<#", i):
            j = segment.find("#>", i + 2)
            i = n if j < 0 else j + 2
            continue
        if not started and c == "#":
            j = segment.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "`":
            if segment.startswith("`\r\n", i):
                i += 3
                continue
            if i + 1 < n and segment[i + 1] == "\n":
                i += 2
                continue
            if i + 1 < n:
                buf.append(segment[i + 1])
                started = True
            i += 2
            continue
        if c == "@" and _here_opens(segment, i):
            end = _here_end(segment, i)
            body_start = segment.find("\n", i) + 1
            closed = segment.endswith("@", 0, end) and end - 3 >= body_start
            body_end = end - 3 if closed else end
            buf.append(segment[body_start:body_end].rstrip("\r"))
            started = True
            i = end
            continue
        if c == "'":
            text, i = _read_single(segment, i + 1)
            buf.append(text)
            started = True
            continue
        if c == '"':
            text, i = _read_double(segment, i + 1)
            buf.append(text)
            started = True
            continue
        if (c in "$@" and i + 1 < n and segment[i + 1] in "({") or c == "{":
            start = i
            end = _skip_group(segment, i + 1 if c in "$@" else i)
            buf.append(segment[start:end])
            started = True
            i = end
            continue
        if c == "&" and not started:
            if segment.startswith("&&", i):
                tokens.append("&&")
                i += 2
                continue
            tokens.append("&")
            i += 1
            continue
        if c == "|":
            flush()
            if segment.startswith("||", i):
                tokens.append("||")
                i += 2
                continue
            tokens.append("|")
            i += 1
            continue
        if c == ";":
            flush()
            tokens.append(";")
            i += 1
            continue
        buf.append(c)
        started = True
        i += 1
    flush()
    return tokens
