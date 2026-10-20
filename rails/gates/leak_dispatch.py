"""PreToolUse: household values never ride a gh body, a commit message or a subagent prompt (design R31).

Keyed on DESTINATION, not verb. Checks, against the value snapshot:
  * every `gh` call carrying text that leaves the box: --body/-b, --title/-t,
    --body-file, --input, -f/-F/--field/--raw-field (with @file resolved),
    in `gh pr|issue|release|gist|api`;
  * `git commit -m/-F` messages (they are pushed);
  * Agent/Task dispatch prompts (they leave the machine with the subagent).
Refuses on FOUND (3) and on could-not-look (4): fails closed. Active only in a
repo that declares `rails/leak.toml` — a repo with no household data has
nothing to compare against. Never prints a value.
"""

from __future__ import annotations

import os
import re
import shlex
from pathlib import Path

from rails import leak, store
from rails.hookio import Deny, Event

NAME = "leak_dispatch"

_GH = re.compile(r"\bgh(?:\.exe)?\s+(pr|issue|release|gist|api|repo)\b")
_GIT_COMMIT = re.compile(
    r"\bgit(?:\.exe)?\s+(?:(?:-C|-c)\s+(?:\S*\"[^\"]*\"\S*|\S*'[^']*'\S*|\S+)\s+"
    r"|--(?:git-dir|work-tree|namespace|exec-path)\s+\S+\s+|--[\w-]+(?:=\S+)?\s+)*commit\b"
)
#: A statement that runs a script or a shell: what a heredoc writes may run, so its bodies
#: stay visible to the trigger (`cat > ship.sh <<'EOF' ... EOF; bash ship.sh`, `bash <<'EOF'`).
_RUNS_SCRIPT = re.compile(
    r"(?:^|[;&|(\s])(?:bash|sh|zsh|pwsh|powershell|python3?|node|source|\.)(?:\.exe)?(?=\s|$)"
    r"|(?:^|[;&|(\s])\.{0,2}/\S+\.(?:sh|ps1|py)\b|(?:^|[;&|(\s])&\s*\S+\.ps1\b",
    re.IGNORECASE,
)
#: A file read into a text flag: `"$(cat f)"`, `"$(< f)"`, PowerShell `(Get-Content f -Raw)`.
_READ_INTO = re.compile(
    r"\$?\(\s*(?:cat|<|Get-Content|gc|type)\s+['\"]?([^'\"\s)]+)['\"]?(?:\s+-Raw)?\s*\)",
    re.IGNORECASE,
)
#: PowerShell's file readers (`type` and `cat` are Get-Content's aliases there), and the switches
#: among their parameters: every other parameter takes the next word as its value.
_PS_READERS = frozenset({"get-content", "gc", "type", "cat"})
_PS_SWITCHES = frozenset({"raw", "force", "wait", "asbytestream", "verbose", "debug", "whatif", "confirm"})
_PS_PATH = frozenset({"path", "literalpath", "lp", "pspath"})
#: bash's file readers, and the flags among theirs that take a value (`cat` takes none: `-n`
#: numbers its lines). `type` in bash describes commands, so it reads no file.
_BASH_READERS = {"cat": frozenset(), "tail": frozenset({"-n", "-c", "--lines", "--bytes"}),
                 "head": frozenset({"-n", "-c", "--lines", "--bytes"})}


def _reader_files(stage: list[str], shell: str) -> list[str]:
    """The files one pipeline stage's reader command names: its file arguments. Redirects (an input
    redirect is `_input_redirects`'), heredoc operators (`cat <<'EOF'` reads no file; its body is
    read as a body), flags and their values are not files."""
    from rails.gates.destructive import command_name
    from rails.shell import is_redirect, takes_target

    if not stage:
        return []
    name, args, files = command_name(stage[0]).lower(), stage[1:], []
    if shell == "powershell":
        if name not in _PS_READERS:
            return files
        positional, i = [], 0
        while i < len(args):
            tok = args[i]
            if tok.startswith("-") and len(tok) > 1:
                key, colon, glued = tok[1:].partition(":")
                if key.lower() in _PS_PATH:
                    value = glued if colon else (args[i + 1] if i + 1 < len(args) else "")
                    files.extend(value.split(","))
                    i += 1 if colon else 2
                elif colon or key.lower() in _PS_SWITCHES:
                    i += 1
                else:
                    i += 2
                continue
            if is_redirect(tok):
                i += 2 if takes_target(tok) else 1
                continue
            positional.append(tok)
            i += 1
        if positional:
            files.extend(positional[0].split(","))
        return [f for f in files if f]
    valued = _BASH_READERS.get(name)
    if valued is None:
        return files
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in valued:
            i += 2
        elif is_redirect(tok):
            i += 2 if takes_target(tok) else 1
        else:
            if not (tok.startswith(("-", "+")) or tok.isdigit()):
                files.append(tok)
            i += 1
    return [f for f in files if f]


#: The bash commands whose output is the input they read, so a file fed on stdin is what they
#: send (`$(sort < f)`); a count (`wc -l < f`) or a program's result is not. "" is a bare `< f`.
_BASH_INPUT_COMMANDS = frozenset({"", "cat", "tail", "head", "sort", "uniq", "grep", "tr", "sed", "cut"})
#: An input redirect the shell reads: `<` that is not `<<`, `<&`, `<>` or a process substitution.
_INPUT_REDIRECT = re.compile(r"(?<![<\w&])<(?![<&>(])\s*")


def _input_redirects(raw: str, shell: str) -> list[str]:
    """The files a bash stage reads on stdin, found on the quote-blanked RAW text (a quoted
    `'<details>'` is text), with the target as written (`< "my log.txt"`)."""
    if shell == "powershell":
        return []
    from rails.shell import scrub

    visible = scrub(raw, "bash", comments=True)
    out = []
    for m in _INPUT_REDIRECT.finditer(visible):
        target = re.match(r"'[^']*'|\"[^\"]*\"|[^\s;&|)<>]+", raw[m.end() :])
        if target:
            out.append(target.group(0).strip("'\""))
    return out


def _files_read(statement: str, shell: str, depth: int = 0) -> list[str]:
    """The files the substitutions in a RAW sending statement read, wherever they sit (a text
    flag, `-f body=$(...)`, a title): `--body "Here's the log: $(tail -20 log.txt)"`, `$(cat < f)`,
    PowerShell `--body (Get-Content -Raw f)`. Found with the statement's own quoting, so a
    single-quoted or escaped `$(cat f)` reads nothing; each substitution is split into its
    statements (`$(tail f || echo none)`), and only the first stage of each is a reader. Best
    effort: a name it finds that cannot be read adds nothing (see `extract_all`)."""
    from rails.gates.destructive import _substitutions, command_name
    from rails.shell import segments

    texts = list(_substitutions(statement, shell))
    if shell == "powershell":
        from rails.shell.powershell import groups

        texts += groups(statement)
    files: list[str] = []
    for text in texts:
        for seg in segments(text, shell):
            first = _stages(seg, shell)[0]  # split on the raw text: `tail f|grep x`
            words = _words(first, shell)
            command = "" if not words or words[0].startswith("<") else command_name(words[0]).lower()
            if command in _BASH_INPUT_COMMANDS:
                files.extend(_input_redirects(first, shell))
            if words and command:
                files.extend(_reader_files(words, shell))
            if depth < 4:
                files.extend(_files_read(seg, shell, depth + 1))  # `$((Get-Content f -Raw).Trim())`
    return files


_TEXT_FLAGS = {"--body", "-b", "--title", "-t", "--message", "-m", "--notes", "-n"}
_FILE_FLAGS = {"--body-file", "--input", "--notes-file", "--file"}
_FIELD_FLAGS = {"-f", "-F", "--field", "--raw-field"}


def _words(command: str, shell: str) -> list[str]:
    try:
        from rails.shell import words  # the dispatcher's shell module, when present

        return words(command, shell)
    except Exception:  # noqa: BLE001
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return command.split()


#: The temp folder spellings a file path may start with.
_TEMP = re.compile(r"^(?:\$env:(?:TEMP|TMP)|\$\{?(?:TEMP|TMP|TMPDIR)\}?|%(?:TEMP|TMP)%)(?=$|[/\\])", re.IGNORECASE)


def _read(path: str, cwd: Path) -> str | None:
    """The file's text, or None when it cannot be read. The path is read as the shell names
    it: `/c/x` (Git Bash), `~`, `$HOME`, `$env:USERPROFILE`, `$env:TEMP`."""
    from rails.gates.destructive import folder_of

    path = path.strip("'\"")
    temp = _TEMP.match(path)
    if temp:
        base = os.environ.get("TEMP") or os.environ.get("TMP") or os.environ.get("TMPDIR") or ""
        path = base + path[temp.end() :] if base else path
    p = folder_of(path, cwd) if cwd is not None else Path(path)
    try:
        with open(p, encoding="utf-8", errors="replace") as handle:
            return handle.read(2_000_000)  # the head only, never the whole of a huge log in memory
    except (OSError, ValueError):  # ValueError: a NUL in the name
        return None


def _without_bodies(command: str, shell: str) -> str:
    """``command`` with heredoc / here-string bodies blanked: a `gh pr create` written INTO a
    script by a heredoc is not one the shell runs."""
    if shell == "powershell":
        from rails.shell.powershell import here_string_spans

        out = list(command)
        for a, b in here_string_spans(command):
            out[a:b] = " " * (b - a)
        return "".join(out)
    from rails.shell.bash import scrub

    return scrub(command, quotes=False)


def _bodies(command: str, shell: str) -> list[str]:
    if shell == "powershell":
        from rails.shell.powershell import here_string_bodies

        return here_string_bodies(command)
    from rails.shell.bash import heredoc_bodies

    return heredoc_bodies(command)


def extract(command: str, shell: str, cwd: Path) -> list[tuple[str, str]]:
    """(label, text) pairs a command would send off the box."""
    return extract_all(command, shell, cwd)[0]


def _statements(command: str, shell: str, depth: int = 0) -> list[tuple[str, list[str]]]:
    """(statement, words) for each statement, and for each statement one runs inside it: a
    command substitution (`url=$(gh pr create --body ...)`), a PowerShell group (`$u = (gh pr
    create ...)`) or script block (`if ($?) { git commit -m ... }`). A flag is read in the
    statement it belongs to."""
    from rails.shell import grouped, segments

    try:
        segs = segments(command, shell)
    except Exception:  # noqa: BLE001 - unparsable: read it as one statement
        return [(command, grouped(_words(command, shell)))]
    found: list[tuple[str, list[str]]] = []
    for seg in segs:
        found.append((seg, grouped(_words(seg, shell))))
        if depth >= 8:
            continue
        from rails.gates.destructive import _substitutions

        inner = list(_substitutions(seg, shell))
        if shell == "powershell":
            from rails.shell.powershell import blocks, groups

            inner += blocks(seg) + groups(seg)
        for text in inner:
            found.extend(_statements(text, shell, depth + 1))
    return found


#: The commands whose own words are what they write.
_LITERAL_COMMANDS = frozenset({"echo", "printf", "write-output"})
#: The commands that write a file they name: PowerShell cmdlets and `tee`.
_FILE_WRITERS = frozenset(
    {"out-file", "set-content", "sc", "add-content", "ac", "new-item", "ni", "tee", "tee-object"}
)
#: The writers whose text is a `-Value` (or a positional literal after the path).
_VALUE_WRITERS = frozenset({"set-content", "sc", "add-content", "ac", "new-item", "ni"})
#: A redirect and its target: `> body.md`, `>> "body.md"`, `2> log.txt`, `*> out.txt`.
_REDIRECT_TO = re.compile(r"(?:\d|\*|&)?(>>?)\s*(?P<target>'[^']*'|\"[^\"]*\"|[^\s;&|)}]+)")


def _outside_inner(statement: str, shell: str) -> str:
    """``statement`` with the inside of each PowerShell block and group blanked: the statements
    in there are listed on their own by `_statements`, and judged there."""
    if shell != "powershell":
        return statement
    from rails.shell.powershell import _top_groups

    out = list(statement)
    for opener in ("{", "("):
        for start, end, _ in _top_groups(statement, opener):
            out[start + 1 : end] = " " * (end - start - 1)
    return "".join(out)


def _stages(statement: str, shell: str) -> list[str]:
    """The raw text of each pipeline stage, split at a `|` the shell reads (not one in quotes)."""
    from rails.shell import scrub

    visible = scrub(statement, shell, comments=True)
    cuts, i = [0], 0
    while i < len(visible):
        if visible.startswith("||", i):
            i += 2
            continue
        if visible[i] == "|":
            cuts.append(i + 1)
        i += 1
    cuts.append(len(statement) + 1)
    return [statement[a : b - 1] for a, b in zip(cuts, cuts[1:])]


def _command_words(stage: str, shell: str) -> list[str]:
    """The stage's command words, shell syntax set aside (`then echo ...` is `echo ...`)."""
    from rails.gates.destructive import _syntax_stripped, command_words

    words = _words(stage, shell)
    return command_words(_syntax_stripped(words, shell)) or command_words(words)


def _first_command(stage: str, shell: str) -> str:
    from rails.gates.destructive import command_name

    words = _command_words(stage, shell)
    return command_name(words[0]).lower() if words else ""


def _same_path(a: str, b: str) -> bool:
    def norm(s: str) -> str:
        s = s.strip().strip("'\"").replace("\\", "/")
        while s.startswith("./"):
            s = s[2:]
        return s.lower()

    return bool(a.strip()) and norm(a) == norm(b)


def _stage_writes(stage: str, path: str, shell: str) -> tuple[str, bool] | None:
    """(kind, appends) when this pipeline stage writes exactly ``path``: a redirect the shell
    reads (not one inside quoted text) whose target is the path, or a writer command (a
    stage's command word, not a word in a title) naming it. None otherwise."""
    from rails.shell import scrub

    visible = scrub(stage, shell, comments=True)
    for m in _REDIRECT_TO.finditer(stage):
        if visible[m.start(1)] == ">" and _same_path(m.group("target"), path):
            return "redirect", m.group(1) == ">>"
    words = _command_words(stage, shell)
    if not words:
        return None
    from rails.gates.destructive import command_name

    first = command_name(words[0]).lower()
    if first not in _FILE_WRITERS:
        return None
    args = [w.split(":", 1)[1] if re.match(r"^-\w+:", w) else w for w in words[1:]]
    if not any(_same_path(a, path) for a in args if not a.startswith("-")):
        return None
    lowered = [w.lower() for w in words[1:]]
    appends = (
        first in ("add-content", "ac")
        or (first in ("out-file", "tee-object") and "-append" in lowered)
        or (first == "tee" and any(w in ("-a", "--append") for w in lowered))
    )
    return "cmdlet", appends


def _writers(path: str, statements: list[tuple[str, list[str]]], shell: str) -> list[tuple[str, int, bool]]:
    """(statement, stage index, appends) for every statement in ``statements`` that writes
    exactly ``path``. A write inside a PowerShell block or group belongs to the statement in
    there, which `_statements` lists on its own."""
    found = []
    for statement, _ in statements:
        for k, stage in enumerate(_stages(_outside_inner(statement, shell), shell)):
            hit = _stage_writes(stage, path, shell)
            if hit:
                found.append((statement, k, hit[1]))
                break
    return found


def _literal_writer(statement: str, k: int, path: str, command: str, shell: str) -> bool:
    """Whether ``statement``, whose stage ``k`` writes ``path``, writes it from the command's
    own text, so that text is what leaves: `echo "..." > f`, `cat > f <<'EOF'`, `'...' > f`,
    `@'...'@ | Out-File f`, `Set-Content f -Value '...'`. A stage that runs a program, a pipe
    from one, a substitution, a variable or a PowerShell group makes it a program's output."""
    from rails.shell import expanding, scrub

    stages = _stages(_outside_inner(statement, shell), shell)
    stage = stages[k]

    def literal_source(src: str) -> bool:
        first = _first_command(src, shell)
        quoted = shell == "powershell" and src.lstrip().startswith(("'", '"', "@'", '@"'))
        heredoc = first in ("cat", "tee") and "<<" in src
        return quoted or first in _LITERAL_COMMANDS or heredoc

    kind = _stage_writes(stage, path, shell)[0]
    first = _first_command(stage, shell)
    if kind == "redirect":
        ok = k == 0 and literal_source(stage)
    elif k == 0:
        ok = (
            (first in _VALUE_WRITERS and bool(
                re.search(r"-Value\s+@?['\"]", stage, re.IGNORECASE)
                or re.match(r"\s*\S+\s+(?:-\w+\s+)?\S+\s+@?['\"]", stage)
                or (first in ("new-item", "ni") and not re.search(r"-Value\b", stage, re.IGNORECASE))
            ))
            or first == "out-file"
            or (first == "tee" and "<<" in stage)
        )
    else:
        ok = k == 1 and len(stages) == 2 and literal_source(stages[0])
    if not ok:
        return False
    # The target path is not the text written: `Out-File $env:TEMP\body.md` expands nothing
    # that leaves.
    checked = re.sub(rf"(?<![\w$]){re.escape(path)}(?![\w])", lambda m: " " * len(m.group(0)), statement)
    visible = expanding(checked, shell)
    if shell == "powershell":
        # a variable or subexpression expands; a group outside quotes runs a command
        return not (re.search(r"(?<!`)\$[\w({]", visible) or "(" in scrub(checked, shell, comments=True))
    if re.search(r"(?<!\\)(?:\$[\w({]|`)", visible):
        return False
    if re.search(r"<<-?\s*\w", statement):
        # an unquoted heredoc delimiter expands its body
        return not any(re.search(r"\$[\w({]|`", b) for b in _bodies(command, shell))
    return True


def extract_all(command: str, shell: str, cwd: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """The (label, text) pairs a command would send off the box, and the files it names that
    could not be read (a check that could not look). Flags are read only in the statements
    that send: a `git commit` or a `gh` call, judged on the shell's own reading of the
    statement, so `rg -F "git commit" docs/` sends nothing."""
    unreadable: list[str] = []
    written: list[str] = []
    statements = _statements(command, shell)
    sending = 0  # index of the statement whose flags are being read

    def read_file(path: str) -> str:
        if path and path != "-":
            writers = _writers(path, statements[:sending], shell)
            if writers:
                # The command writes it before sending it. Every writer must be the command's
                # own text, and that text is read; one program among them and the file is
                # refused unread. The copy on disk is read too (a missing file adds nothing): an
                # append keeps it, and a writer may not run (`test -f f || echo x > f`).
                if not all(_literal_writer(s, k, path, command, shell) for s, k, _ in writers):
                    unreadable.append(path)
                    return ""
                written.extend(s for s, _, _ in writers if s not in written)
                return _read(path, cwd) or ""
        text = _read(path, cwd)
        if text is None:
            if path and path != "-":
                unreadable.append(path)
            return ""
        return text

    runs = _without_bodies(command, shell)
    if _RUNS_SCRIPT.search(runs):
        runs = command  # a body may be a script this command runs
    if not (_GH.search(runs) or _GIT_COMMIT.search(runs)):
        return [], []
    from rails.shell import scrub

    out: list[tuple[str, str]] = []
    for sending, (statement, words) in enumerate(statements):
        visible = scrub(statement, shell)
        is_git_commit = bool(_GIT_COMMIT.search(visible))
        if not (is_git_commit or _GH.search(visible)):
            continue
        is_gh_pr_create = bool(re.search(r"\bgh\s+(pr|issue)\s+(create|edit|comment)\b", visible))
        _read_flags(words, command, is_git_commit, is_gh_pr_create, read_file, out, shell)
        # `--body "Here's the log: $(tail -20 log.txt)"`, `-f body="$(cat f)"`, `--body-file - <
        # f`: a file a substitution in this statement reads, or its own stdin, is part of what it
        # sends. Best effort: a name found this way that cannot be read adds nothing (the
        # substitution's text is still read, as on main), so a misread word, a missing fallback or
        # `/dev/null` refuses nothing; a crash here degrades to main's reading too. A file the
        # command writes before sending it is judged by its writers, as any other body file.
        try:
            derived = list(dict.fromkeys(_files_read(statement, shell) + _input_redirects(statement, shell)))
        except Exception:  # noqa: BLE001 - best effort, never a hole in what main reads
            derived = []
        for name in derived:
            label = f"read by a substitution: {name}"
            if _writers(name, statements[:sending], shell):
                out.append((label, read_file(name)))
                continue
            text = _read(name, cwd)
            if text is not None:
                out.append((label, text))
    # `-m "$(cat <<'EOF' ...)"`, `--body-file - <<'EOF'`, PowerShell `$body = @'...'@` or
    # `@'...'@ | gh ... --body-file -`: the body is the text that leaves
    out.extend(("heredoc body", body) for body in _bodies(command, shell))
    # `echo "..." > body.md; gh ... --body-file body.md`: the file is the statement's text
    out.extend(("written in the command", text) for text in written)
    return [(label, text) for label, text in out if text], unreadable


def _read_flags(words, command, is_git_commit, is_gh_pr_create, read_file, out, shell="bash") -> None:
    """Append the (label, text) each sending flag of one statement carries."""
    i = 0
    while i < len(words):
        w = words[i]
        flag, eq, inline = w.partition("=")
        nxt = words[i + 1] if i + 1 < len(words) else ""
        value = inline if eq else nxt
        step = 1 if eq else 2
        if is_git_commit and not eq and re.fullmatch(r"-[a-zA-Z]+m", w):
            flag = "-m"  # `git commit -am "..."`, `-qm`: the cluster's last letter takes the value
        elif is_git_commit and re.fullmatch(r"-m.+", w):
            flag, value, step = "-m", w[2:], 1  # a glued `-m"..."`
        if flag in _TEXT_FLAGS:
            out.append((flag, value))
            read = _READ_INTO.fullmatch(value.strip())
            if read:
                out.append((f"{flag} {read.group(1)}", read_file(read.group(1))))  # `--body "$(cat f)"`
            elif "$" in value:
                out.append((flag, command))  # `-m $m`: the text was set elsewhere in the command
            i += step
            continue
        if w == "<<<" or (w.startswith("<<<") and len(w) > 3):
            # a here-string fed on stdin (`--body-file - <<< "..."`)
            out.append(("<<<", nxt if w == "<<<" else w[3:]))
            i += 2 if w == "<<<" else 1
            continue
        if is_git_commit and flag in ("-F", "--file") and value and value != "-" and "=" not in value:
            out.append((f"{flag} {value}", read_file(value)))  # `git commit -F msg.txt`
            i += step
            continue
        if flag in _FILE_FLAGS or (flag == "-F" and is_gh_pr_create):
            out.append((f"{flag} {value}", "" if value == "-" else read_file(value)))
            i += step
            continue
        if flag in _FIELD_FLAGS:
            _, _, field_value = value.partition("=")
            if field_value.startswith("@"):
                out.append((f"{flag} {value}", read_file(field_value[1:])))
            else:
                out.append((flag, field_value))
            i += step
            continue
        i += 1


def check(evt: Event):
    repo = store.find_repo(evt.cwd)
    if repo is None or not (repo.top / "rails" / "leak.toml").is_file():
        return None
    unreadable: list[str] = []
    if evt.tool_name in ("Agent", "Task"):
        pieces = [("subagent prompt", evt.prompt)] if evt.prompt else []
    else:
        pieces, unreadable = extract_all(evt.command, evt.shell or "bash", evt.cwd)
    if unreadable:
        return Deny(
            "rails: refused - this would send the text of "
            + ", ".join(f"`{p}`" for p in unreadable)
            + " off the box, and rails could not read it to check it for household values. "
            "Name the file by its full path (a Windows path, not `/c/...` or `/tmp/...`); if this "
            "command writes it from a program's output, write it in one call and send it in the next."
        )
    if not pieces:
        return None
    lines = []
    for label, text in pieces:
        lines.extend(leak.text_lines(label, text))
    result = leak.check_lines(repo, lines, leak.allowlist_for(repo.top))
    if result.code == leak.EXIT_CLEAN:
        return None
    return Deny(
        "rails: refused - this would send text off the box.\n" + result.report()
    )
