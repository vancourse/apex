"""Refuse a heredoc whose delimiter is unquoted (bash), or an expanding
here-string whose body PowerShell would rewrite.

Ported from jarvis ``.claude/hooks/heredoc_write_gate.py`` (23 denials). The
command it stops looks like this, and it recurs across sessions rather than
being learned once::

    cat > parser.py <<EOF
    PATTERN = re.compile(r"\\\\d+\\\\s*USD")
    EOF

**The delimiter is the whole bug.** ``<<EOF`` expands the body; ``<<'EOF'`` does
not. In the unquoted form the shell rewrites ``\\\\`` -> ``\\``, ``\\$`` -> ``$``,
``\\``` -> ````` and eats ``\\`` + newline before the text reaches the file.
``\\d``, ``\\s`` and ``\\n`` pass through untouched, which is what makes the
symptom so consistently misread: what breaks is content that was already
escaped correctly, silently, in a file that still parses.

**Keyed on the delimiter, never on the redirect.** Commit ``1ac6639f`` (*"a
heredoc'd gh --body quote truncated the section check"*) had no file redirect
at all — the heredoc fed a command's stdin. The destination only picks which
remedy the message names.

**A real heredoc is identified by its terminator line**, not by the ``<<``
token, which keeps ``python -c "print(1 << 3)"`` out of scope. Heredoc BODIES
are skipped, not scanned, or the gate denies its own commit message. All three
literal forms pass: ``<<'EOF'``, ``<<"EOF"``, ``<<\\EOF``.

**PowerShell** (new in the port). The same mistake has a different spelling:
``@"`` ... ``"@`` expands ``$name``, ``$(...)`` and backtick escapes; ``@'`` ...
``'@`` is literal. Backslashes pass through, so the casualty is a body holding
``$`` or a backtick (a regex's ``$1``, a script's ``$env:X``). A double-quoted
here-string whose body holds neither arrives byte-for-byte and is allowed; one
inside a literal here-string's body is text, not a here-string. Like the bash
rule, an unterminated one is not a here-string at all (fail-open).

The override, as TEXT or in the hook's own environment::

    JARVIS_HEREDOC_OK=1 <your command>          # RAILS_HEREDOC_OK is an alias
    $env:JARVIS_HEREDOC_OK=1; <your command>    # PowerShell
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell import words
from rails.shell.override import overridden

NAME = "heredoc_write"

OVERRIDES = ("JARVIS_HEREDOC_OK", "RAILS_HEREDOC_OK")

#: The heredoc operator and its delimiter token. `(?!<)` keeps `<<<` (a
#: herestring) out; `-?` covers `<<-`. Alternation order is load-bearing: the
#: quoted forms must be tried before the bare one.
_HEREDOC = re.compile(
    r"<<(?!<)-?[ \t]*(?P<delim>'[^']*'|\"[^\"]*\"|\\[A-Za-z_]\w*|[A-Za-z_]\w*)"
)

#: A redirect that lands in a file. Only used to pick which remedy to name.
_FILE_REDIRECT = re.compile(r">>?[ \t]*(?![&|])(?P<path>[^\s|&;<>]+)")

#: `| tee out.txt` — the other way a heredoc body becomes a file.
_TEE = re.compile(r"\|[ \t]*tee\b(?:[ \t]+-\S+)*[ \t]+(?P<path>[^\s|&;<>]+)")

#: A PowerShell here-string opener: `@'` or `@"` ending its line.
_PS_OPEN = re.compile(r"@(?P<q>['\"])[ \t]*\r?$")

#: What a double-quoted here-string rewrites: a variable / subexpression, or
#: any backtick escape.
_PS_EXPANDS = re.compile(r"\$[\w{(?^$:]|`")

#: Cmdlets that author a file from their input, and their parameters that take
#: a value which is not the path.
_PS_SINKS = frozenset(
    {
        "set-content",
        "sc",
        "add-content",
        "ac",
        "out-file",
        "tee-object",
        "tee",
    }
)
_PS_VALUED = frozenset({"-encoding", "-value", "-delimiter", "-width", "-variable"})
_PS_PATH_PARAMS = frozenset({"-path", "-filepath", "-literalpath"})
_PS_REDIRECT = re.compile(r"\*?\d?>>?[ \t]*(?P<path>[^\s|&;<>]+)")


def _bare(delim: str) -> str:
    """`'EOF'` / `"EOF"` / `\\EOF` / `EOF` -> `EOF`."""
    if delim[0] in "'\"":
        return delim[1:-1]
    if delim[0] == "\\":
        return delim[1:]
    return delim


def _is_literal(delim: str) -> bool:
    """True when the delimiter is quoted, i.e. the body is passed through as-is."""
    return delim[0] in "'\"\\"


def _terminator(lines: list[str], start: int, bare: str) -> int | None:
    """Index of the line that closes a heredoc opened before `start`, or None."""
    for index in range(start, len(lines)):
        if lines[index].strip() == bare:
            return index
    return None


def _unquoted_heredocs(command: str) -> list[tuple[str, str]]:
    """Every unquoted heredoc, as `(delimiter, the line that opened it)`.

    Heredoc BODIES are skipped, not scanned: a correctly-quoted commit message
    whose body explains the bug contains the text `<<EOF`.
    """
    lines = command.splitlines()
    offenders: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        cursor = index + 1
        for match in _HEREDOC.finditer(line):
            delim = match.group("delim")
            bare = _bare(delim)
            end = _terminator(lines, cursor, bare)
            if end is None:
                # Unterminated: not a heredoc. Fail-open is the bias.
                return offenders
            if not _is_literal(delim):
                offenders.append((bare, line))
            cursor = end + 1
        index = cursor
    return offenders


def _target_file(opening_line: str) -> str | None:
    """The file the offending heredoc's own line would author, or None."""
    for pattern in (_FILE_REDIRECT, _TEE):
        for match in pattern.finditer(opening_line):
            path = match.group("path")
            if path.startswith("/dev/"):
                continue
            return path
    return None


def _expanding_herestrings(command: str) -> list[tuple[str, str]]:
    """Every `@"` here-string whose body PowerShell would rewrite, as
    `(opening line, closing line)`. Literal bodies are skipped, not scanned."""
    lines = command.split("\n")
    found: list[tuple[str, str]] = []
    index = 0
    while index < len(lines):
        match = _PS_OPEN.search(lines[index])
        if not match:
            index += 1
            continue
        quote = match.group("q")
        close = None
        for j in range(index + 1, len(lines)):
            if lines[j].startswith(quote + "@"):
                close = j
                break
        if close is None:
            return found  # unterminated: not a here-string
        body = "\n".join(lines[index + 1 : close])
        if quote == '"' and _PS_EXPANDS.search(body):
            # The markers themselves are cut off, so the lines tokenise cleanly:
            # `Set-Content f.py -Value ` and ` | Set-Content f.py`.
            found.append((lines[index][: match.start()], lines[close][2:]))
        index = close + 1
    return found


def _ps_target(line: str) -> str | None:
    """The file a here-string's opening or closing line writes, or None."""
    tokens = words(line, "powershell")
    for k, token in enumerate(tokens):
        if token.lower() not in _PS_SINKS:
            continue
        skip = False
        for j in range(k + 1, len(tokens)):
            arg = tokens[j]
            if skip:
                skip = False
                continue
            if arg in ("|", ";"):
                break
            low = arg.lower()
            if low in _PS_PATH_PARAMS and j + 1 < len(tokens):
                return tokens[j + 1]
            if low in _PS_VALUED:
                skip = True
                continue
            if arg.startswith("-") or arg.startswith("@"):
                continue
            return arg
    for match in _PS_REDIRECT.finditer(line):
        path = match.group("path")
        if path.lower() not in ("$null", "nul"):
            return path
    return None


def _bash_reason(command: str) -> str | None:
    offenders = _unquoted_heredocs(command)
    if not offenders:
        return None
    delim, opening_line = offenders[0]
    target = _target_file(opening_line)
    if target:
        destination = f"the file is written: {target}"
        remedy = (
            "Author the file with the Write tool instead. It writes the bytes you\n"
            "give it, and on this box a shell `>>` additionally writes LF endings\n"
            "into a CRLF file, which no amount of quoting fixes.\n\n"
            f"If it really must be the shell here, quote the delimiter: <<'{delim}'"
        )
    else:
        destination = "the command sees it"
        remedy = (
            "Quote the delimiter — that is the entire fix:\n\n"
            f"    <<'{delim}'      instead of      <<{delim}\n\n"
            "Quoting turns expansion off, so the body arrives byte-for-byte."
        )
    return (
        f"This heredoc's delimiter is unquoted (`<<{delim}`), so the shell rewrites\n"
        f"the body before {destination}.\n\n"
        f"Four things get rewritten, and only these four:\n"
        f"    \\\\  ->  \\        <- doubled backslashes COLLAPSE\n"
        f"    \\$  ->  $\n"
        f"    \\`  ->  `\n"
        f"    \\ + newline  ->  both eaten (line continuation)\n\n"
        f"`\\d`, `\\s` and `\\n` pass through untouched, which is why this reads as\n"
        f"random damage. It is not: what breaks is content that was already escaped\n"
        f'correctly. A regex written `"\\\\d+"` lands as `"\\d+"` and still parses, so\n'
        f"nothing fails until the pattern quietly stops matching.\n\n"
        f"{remedy}\n\n"
        f"If you genuinely want the shell to interpolate `$vars` into this body:\n"
        f"    JARVIS_HEREDOC_OK=1 <your command>   (RAILS_HEREDOC_OK=1 also works)"
    )


def _powershell_reason(command: str) -> str | None:
    offenders = _expanding_herestrings(command)
    if not offenders:
        return None
    opening, closing = offenders[0]
    target = _ps_target(opening) or _ps_target(closing)
    if target:
        destination = f"the file is written: {target}"
        remedy = (
            "Author the file with the Write tool instead. It writes the bytes you\n"
            "give it.\n\n"
            "If it really must be the shell here, use a literal here-string:\n"
            "    @'\n    ...\n'@"
        )
    else:
        destination = "the command sees it"
        remedy = (
            "Use a literal here-string — that is the entire fix:\n\n"
            "    @' ... '@      instead of      @\" ... \"@\n\n"
            "Single quotes turn expansion off, so the body arrives byte-for-byte."
        )
    return (
        f'This here-string is double-quoted (`@"`), so PowerShell rewrites the\n'
        f"body before {destination}.\n\n"
        f"What gets rewritten:\n"
        f"    $name, ${{name}}, $(...)  ->  their values (an unset name becomes empty)\n"
        f'    `n `t `$ `" ``           ->  newline, tab, $, ", `   <- backticks are consumed\n\n'
        f"Backslashes pass through, which is why this reads as random damage: a\n"
        f"regex's `$1` or a script's `$env:X` lands with a value spliced in (or\n"
        f"nothing), and the file still parses.\n\n"
        f"{remedy}\n\n"
        f"If you genuinely want PowerShell to interpolate into this body:\n"
        f"    $env:JARVIS_HEREDOC_OK=1; <your command>   (RAILS_HEREDOC_OK also works)"
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
    reason = (
        _powershell_reason(command) if shell == "powershell" else _bash_reason(command)
    )
    return Deny(reason) if reason else None
