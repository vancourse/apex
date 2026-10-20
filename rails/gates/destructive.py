"""Refuse the obviously destructive commands — apex's ``guard-destructive.sh``,
reworked to read one statement's tokens instead of the whole command line.

The five rules are the original's: ``rm -rf`` on root, home or a parent
directory; a force push to ``main``/``master``; ``git reset --hard`` to an
``origin`` ref; a write or delete aimed at a ``.env`` file; ``--no-verify`` on
``git commit``/``push``.

**Why the rework.** The shell original matched each regex against the ENTIRE
command text and blocked 33 times, mostly falsely (apex #38, unfixed from
2026-08-05): ``.*`` spanned separators, so ``git push --force origin my-branch
&& gh pr edit 36 --base main`` was a "force push to main"; the branch name had
no left boundary, so ``fix/remain`` was ``main``; ``rm old.txt && cat
.env.example`` was a ".env modification"; and the hook blocked the bug report
about itself because the heredoc body quoted the cases. Meanwhile the real
disaster, a bare ``git push --force`` while ``main`` is checked out, passed.
Here each rule reads the tokens of one statement (``rails.shell.segments`` +
``words``): quoted text and heredoc bodies are data, separators end a
statement, a branch is compared whole, and a push with no refspec is judged on
the branch HEAD names (read from ``.git/HEAD`` in Python, no subprocess).

**PowerShell** spellings are covered where they exist: ``Remove-Item -Recurse``
(and ``rm``/``ri``/``del``/``erase``/``rd``/``rmdir``) on ``\\``, a drive root,
``~``, ``$HOME``, ``$env:USERPROFILE`` or ``..``; ``Set-Content``/
``Add-Content``/``Out-File``/``Tee-Object``/``Remove-Item``/``Move-Item``/
``Clear-Content`` on a ``.env`` file. The git rules are the same command.

The original had no override: it said to ask the user. That stays — the
operator runs the command themselves (``!`` at the prompt) — and the only
switch is ``RAILS_DESTRUCTIVE_OK`` in the hook's OWN environment, which an
agent cannot set by typing it into a command.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from rails.hookio import Deny, Event
from rails.shell import arguments, is_substitution, segments, words
from rails.shell.override import in_environment

NAME = "destructive"

OVERRIDES = ("RAILS_DESTRUCTIVE_OK",)

DEFAULT_BRANCHES = frozenset({"main", "master"})

#: Leading words that run the next word as the command.
_WRAPPERS = frozenset({"sudo", "command", "builtin", "exec", "nohup", "time", "&"})

#: rm targets: root (or `/*`), or anything at or under home or a parent dir —
#: the original's `(/|~|\$HOME|\.\.)([[:space:]]|$|/)`, as a whole token.
_RM_TARGET = re.compile(r"^(?:/\*?|//.*|(?:~|\$HOME|\$\{HOME\}|\.\.)(?:/.*)?)$")
_PS_RM_TARGET = re.compile(
    r"^(?:[/\\]\*?|[A-Za-z]:[/\\]?\*?|\$env:HOMEDRIVE[/\\]?"
    r"|(?:~|\$HOME|\$\{HOME\}|\$env:USERPROFILE|\.\.)(?:[/\\].*)?)$",
    re.IGNORECASE,
)
_PS_REMOVE = frozenset({"remove-item", "rm", "ri", "del", "erase", "rd", "rmdir"})
_PS_REMOVE_VALUED = frozenset(
    {"-filter", "-include", "-exclude", "-credential", "-stream"}
)

#: A token naming a .env file: the original's `\.env([[:space:]]|$|\.)`.
_ENV_FILE = re.compile(r"\.env(?:$|\.)")
_ENV_WRITERS = frozenset(
    {
        "rm",
        "mv",
        "tee",
        "remove-item",
        "ri",
        "del",
        "erase",
        "move-item",
        "mi",
        "move",
        "set-content",
        "sc",
        "add-content",
        "ac",
        "out-file",
        "tee-object",
        "clear-content",
        "clc",
    }
)
_REDIRECT = re.compile(r"^(?:\d|\*|&)?>>?\|?(?P<path>.*)$")

_GIT_VALUED = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace"})
_PUSH_VALUED = frozenset({"-o", "--push-option", "--receive-pack", "--exec", "--repo"})


def head_branch(cwd: Path) -> str | None:
    """The branch `.git/HEAD` names for the checkout containing `cwd`, or None.

    Pure Python, because a hook runs on every tool call and `git rev-parse`
    costs 30-50 ms on Windows. Handles a linked worktree's `.git` file.
    """
    try:
        start = cwd.resolve()
    except OSError:
        return None
    if not start.is_dir():
        return None  # a folder that does not exist (`git -C "$WT"`) has no branch
    for candidate in [start, *start.parents]:
        dotgit = candidate / ".git"
        try:
            if dotgit.is_dir():
                gitdir = dotgit
            elif dotgit.is_file():
                text = dotgit.read_text(encoding="utf-8", errors="replace").strip()
                if not text.startswith("gitdir:"):
                    return None
                gitdir = Path(text.split(":", 1)[1].strip())
                if not gitdir.is_absolute():
                    gitdir = candidate / gitdir
            else:
                continue
            head = (gitdir / "HEAD").read_text(encoding="utf-8").strip()
        except OSError:
            return None
        prefix = "ref: refs/heads/"
        return head[len(prefix) :] if head.startswith(prefix) else None
    return None


def command_words(tokens: list[str]) -> list[str]:
    """Drop `VAR=x` prefixes and wrappers (`sudo`, PowerShell's `&`)."""
    index = 0
    while index < len(tokens) and (
        tokens[index] in _WRAPPERS or re.match(r"^[A-Za-z_]\w*=", tokens[index])
    ):
        index += 1
    return tokens[index:]


#: Shell syntax a statement can start with; the command follows it (`then gh pr merge`).
_KEYWORDS = frozenset({"if", "then", "else", "elif", "do", "while", "until", "!", "{", "(", "}", ")"})


def _substitutions(segment: str, shell: str) -> list[str]:
    """The commands a statement's `$(...)` (and, in bash, backtick) substitutions run.
    Found on the text the shell expands, so one inside a single-quoted string, a quoted
    heredoc body or a comment is text, not a command: a commit message that mentions a
    command runs nothing. One inside double quotes runs (`out="$(gh pr merge 12)"`), so it
    is found; an escaped one (`\\$(`, PowerShell's `` `$( ``) is text. PowerShell's backtick
    is an escape, not a substitution."""
    from rails.shell import expanding

    visible = expanding(segment, shell)
    powershell = shell == "powershell"
    escape = "`" if powershell else "\\"
    out: list[str] = []
    i, n = 0, len(segment)
    while i < n:
        if visible[i] == escape:
            i += 2
            continue
        if visible.startswith("$(", i) and not visible.startswith("$((", i):
            if powershell:
                from rails.shell.powershell import _skip_group

                end = _skip_group(segment, i + 1)
            else:
                from rails.shell.bash import _skip_subst

                end = _skip_subst(segment, i + 2)
            closed = end <= n and segment[end - 1 : end] == ")"
            out.append(segment[i + 2 : end - 1 if closed else end])
            i = max(end, i + 1)
            continue
        if not powershell and visible[i] == "`":
            from rails.shell.bash import _skip_backtick

            end = _skip_backtick(segment, i + 1)
            out.append(segment[i + 1 : max(end - 1, i + 1)])
            i = max(end, i + 1)
            continue
        i += 1
    return [inner for inner in out if inner.strip()]


def _syntax_stripped(tokens: list[str], shell: str) -> list[str]:
    """The command words of a statement once shell syntax is set aside: leading keywords,
    a subshell's `(` and `)`, and a PowerShell `$x =` assignment."""
    out = list(tokens)
    while out and out[0].lower() in _KEYWORDS:
        out = out[1:]
    # a PowerShell assignment first, so `$out = (git push ...)` reaches its `(`
    if shell == "powershell" and len(out) > 2 and out[0].startswith("$") and out[1] == "=":
        out = out[2:]
    elif shell == "powershell" and out and re.match(r"^\$[\w:]+=", out[0]):
        # `$r=gh pr merge ...`: the assignment is glued to the command's first word
        rest = out[0].split("=", 1)[1]
        out = ([rest] if rest else []) + out[1:]
    if out and out[0].startswith("(") and out[0] != "(":
        out[0] = out[0].lstrip("(")
    # Only the statement's excess `)`, taken from the words nearest its end that end in one:
    # the subshell's `)` may sit before a redirect (`(...) 2>&1`) or after one (`> log)`), and
    # `push origin $(git branch --show-current)` keeps its own.
    excess = sum(t.count(")") for t in out) - sum(t.count("(") for t in out)
    k = len(out) - 1
    while excess > 0 and k >= 0:
        if out[k].endswith(")"):
            take = min(excess, len(out[k]) - len(out[k].rstrip(")")))
            out[k] = out[k][:-take]
            excess -= take
        k -= 1
    return [tok for tok in out if tok]


def before_block_end(text: str, shell: str) -> str:
    """``text`` up to the first `}` that closes a block opened before it, read on the
    quote-blanked text. A `;` inside `if ($?) { git push; gh pr merge --auto } else { ... }`
    leaves `gh pr merge --auto } else { ... }`: its command ends at the block's `}`, and what
    follows (`else { ... }`) is a block `blocks` opens and judges on its own."""
    from rails.shell import scrub

    visible = scrub(text, shell, comments=True)
    depth = 0
    for i, c in enumerate(visible):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                return text[:i]
    return text


def pipeline_stages(tokens: list[str]) -> list[list[str]]:
    """Split a statement's tokens at `|` / `|&`: each stage is its own command."""
    stages: list[list[str]] = [[]]
    for tok in tokens:
        if tok in ("|", "|&"):
            stages.append([])
        else:
            stages[-1].append(tok)
    return [stage for stage in stages if stage]


def commands(command: str, shell: str, _depth: int = 0) -> list[tuple[str, list[str]]]:
    """`(statement text, command words)` for every pipeline stage of every
    statement — the unit the tokenised gates judge. A command reached through a
    launcher or a `gh` alias is judged as its plain form (p3e): `env ... cmd`,
    `cmd /c cmd`, `bash -c "cmd"`, `pwsh -c "cmd"`, `Start-Process cmd
    -ArgumentList ...`, and `gh <alias>` from gh's own config."""
    found: list[tuple[str, list[str]]] = []
    for segment in segments(command, shell):
        if _depth < 8:
            # `out=$(gh pr merge ...)`, `` x=`cmd` ``, PowerShell `$(...)`: the inner command
            # runs, so it is judged as one. Its statement text starts with `$(`, so a
            # caller following `cd` knows it ran in a child shell.
            for inner in _substitutions(segment, shell):
                found.extend((f"$({s})", t) for s, t in commands(inner, shell, _depth + 1))
        if _depth < 8 and shell == "powershell":
            # `if ($LASTEXITCODE -eq 0) { gh pr merge ... }`, one glued to its condition
            # (`if($?){...}`), the unclosed first piece of a block a `;` cut, and a group
            # (`Write-Host (gh pr merge 12)`, `@(...)`): their statements run, so they are
            # judged. Read on the raw statement, so braces and parentheses in quoted text or a
            # here-string stay text.
            from rails.shell.powershell import blocks, groups

            for inner in blocks(segment) + groups(segment):
                found.extend(commands(inner, shell, _depth + 1))
        for stage in pipeline_stages(words(before_block_end(segment, shell), shell)):
            # The command once shell syntax is set aside (`then gh ...`, `(cd x`, `$r = gh
            # ...`). When that leaves nothing, the statement's own words are judged instead
            # (`$env:CLAUDECODE=''`), or the bare assignment itself (`CLAUDECODE=0`):
            # operator_bounds reads them.
            tokens = command_words(_syntax_stripped(stage, shell)) or command_words(stage) or stage
            for tokens in (tokens,):
                if tokens:
                    # The launcher's own words stay judged too (`env -u CLAUDECODE ...` is
                    # operator_bounds' business); the command it runs is added beside them.
                    found.append((segment, tokens))
                    found.extend((segment, t) for t in _launched(tokens, _depth) if t != tokens)
    return found


_SHELL_STRING = {
    "bash": ("bash", ("-c",)),
    "sh": ("bash", ("-c",)),
    "zsh": ("bash", ("-c",)),
    "pwsh": ("powershell", ("-c", "-command")),
    "powershell": ("powershell", ("-c", "-command")),
}
#: Shell options that take a value, so the value is not where the command starts.
_SHELL_VALUED = {
    "bash": frozenset({"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}),
    "powershell": frozenset(
        {"-executionpolicy", "-ep", "-ex", "-windowstyle", "-w", "-workingdirectory", "-wd", "-version",
         "-inputformat", "-if", "-outputformat", "-of", "-configurationname", "-psconsolefile", "-settingsfile"}
    ),
}
_START = frozenset({"start-process", "saps", "start"})
#: The command a launcher nest too deep to judge stands for; `destructive` refuses it.
TOO_DEEP = "rails-launchers-nested-too-deep"


def _launched(tokens: list[str], depth: int) -> list[list[str]]:
    """The command words a launcher runs, or ``[tokens]`` when it is not one."""
    if not tokens:
        return [tokens]
    if depth > 8:
        # Launchers nested past this are judged as one command no gate allows.
        return [[TOO_DEEP]]
    name = command_name(tokens[0])
    rest = tokens[1:]
    if name == "env":
        i = 0
        while i < len(rest) and (rest[i].startswith("-") or re.match(r"^[A-Za-z_]\w*=", rest[i])):
            i += 2 if rest[i] in ("-u", "--unset", "-C", "--chdir") else 1
        return _launched(rest[i:], depth + 1) if rest[i:] else [tokens]
    if name == "cmd":
        for i, tok in enumerate(rest):
            if tok.lower() in ("/c", "/k"):
                inner = rest[i + 1 :]
                if len(inner) == 1:
                    return [c for _, c in commands(inner[0], "bash", depth + 1)] or [tokens]
                return _launched(inner, depth + 1) if inner else [tokens]
        return [tokens]
    if name in _SHELL_STRING:
        inner_shell, flags = _SHELL_STRING[name]
        valued = _SHELL_VALUED[inner_shell]
        i = 0
        while i < len(rest) - 1:
            tok = rest[i]
            # `bash -lc`, `sh -ec`: a cluster of short options that holds c
            if tok.lower() in flags or (inner_shell == "bash" and re.fullmatch(r"-[a-z]*c[a-z]*", tok)):
                return [c for _, c in commands(rest[i + 1], inner_shell, depth + 1)] or [tokens]
            if not tok.startswith(("-", "+")):
                break  # `bash script.sh -c x`: -c is the script's argument
            # `bash -o pipefail -c`, `powershell -ExecutionPolicy Bypass -Command`
            i += 2 if (tok.lower() if inner_shell == "powershell" else tok) in valued else 1
        return [tokens]
    if name in _START:
        target, args, i = "", [], 0
        while i < len(rest):
            tok = rest[i]
            low = tok.lower()
            if low in ("-filepath", "-file") and i + 1 < len(rest):
                target, i = rest[i + 1], i + 2
                continue
            if low in ("-argumentlist", "-args") and i + 1 < len(rest):
                args += [a for part in rest[i + 1].split(",") for a in part.split() if a]
                i += 2
                continue
            if low.startswith("-"):
                i += 2 if low in ("-workingdirectory", "-verb", "-windowstyle") else 1
                continue
            if not target:
                target = tok
            else:
                args.append(tok)
            i += 1
        stripped = [a.strip("'\"") for a in args]
        return _launched([target.strip("'\""), *stripped], depth + 1) if target else [tokens]
    if name == "gh" and rest:
        expansion = gh_aliases().get(rest[0])
        if expansion is not None:
            if expansion.startswith("!"):
                return [c for _, c in commands(expansion[1:], "bash", depth + 1)] or [tokens]
            words, extra = expansion.split(), list(rest[1:])
            # gh substitutes $1..$9 with the arguments, then appends the rest.
            used: set[int] = set()
            for i, word in enumerate(words):
                if len(word) == 2 and word[0] == "$" and word[1].isdigit():
                    n = int(word[1]) - 1
                    if 0 <= n < len(extra):
                        words[i] = extra[n]
                        used.add(n)
            return [[tokens[0], *words, *(a for i, a in enumerate(extra) if i not in used)]]
    return [tokens]


def gh_aliases() -> dict[str, str]:
    """`gh alias` definitions from gh's config file (``GH_CONFIG_DIR``, else the platform's
    default). A tiny reader of the ``aliases:`` block, no YAML library: a value it cannot read
    is skipped, never guessed."""
    import os

    candidates = []
    if os.environ.get("GH_CONFIG_DIR"):
        candidates.append(Path(os.environ["GH_CONFIG_DIR"]) / "config.yml")
    if os.environ.get("APPDATA"):
        candidates.append(Path(os.environ["APPDATA"]) / "GitHub CLI" / "config.yml")
    candidates.append(Path.home() / ".config" / "gh" / "config.yml")
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        out: dict[str, str] = {}
        inside = False
        for line in text.splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            if not line.startswith((" ", "\t")):
                inside = line.split(":", 1)[0].strip() == "aliases"
                continue
            if inside and ":" in line:
                key, value = line.strip().split(":", 1)
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                    value = value[1:-1]
                if key and value:
                    out[key.strip()] = value
        return out
    return {}


def command_name(token: str) -> str:
    name = token.replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def native_path(path: str) -> str:
    """A Git Bash path (`/c/Users/x`) as Windows reads it (`c:/Users/x`); on Windows only."""
    found = re.match(r"^/([a-zA-Z])(/.*)?$", path)
    if found and os.name == "nt":
        return f"{found.group(1)}:{found.group(2) or '/'}"
    return path


def folder_of(path: str, cwd: Path) -> Path:
    """The folder a `-C` path names, from ``cwd``: `~/x`, `$HOME/x` and `$env:USERPROFILE/x`
    are under home, `/c/x` is `c:/x`."""
    home = re.match(r"^(?:~|\$HOME|\$\{HOME\}|\$env:(?:USERPROFILE|HOME))(?=$|[/\\])[/\\]?", path, re.IGNORECASE)
    if home:
        return Path.home() / path[home.end() :]
    return cwd / native_path(path)


def git_subcommand(tokens: list[str], cwd: Path) -> tuple[str, list[str], Path]:
    """`(subcommand, its args, the directory git runs in)` for a git statement."""
    index = 1
    where = cwd
    while index < len(tokens):
        tok = tokens[index]
        if tok in _GIT_VALUED and index + 1 < len(tokens):
            if tok == "-C":
                # `git -C a -C b` is `a/b`: each one from the folder before it
                where = folder_of(tokens[index + 1], where).resolve()
            index += 2
            continue
        if tok.startswith("-"):
            index += 1
            continue
        return tok, tokens[index + 1 :], where
    return "", [], where


#: A substitution that names the current branch, and its own `-C` folder if it has one.
_CURRENT_BRANCH = re.compile(
    r"^(?:\$\(|`|\()\s*git\s+(?:-C\s+(?P<dir>\S+)\s+)?"
    r"(?:branch\s+--show-current|rev-parse\s+--abbrev-ref\s+HEAD|symbolic-ref\s+(?:-q\s+)?--short\s+HEAD)"
    r"(?:\s+\d?>&?\s*\S+)*\s*[)`]$"
)


def refspec_dst(spec: str) -> str:
    """The destination of a refspec `src:dst`, or the whole spec. A `:` inside a substitution
    (the drive colon of `$(git -C C:/x branch --show-current)`) separates nothing."""
    depth, tick = 0, False
    for index, ch in enumerate(spec):
        if ch == "`":
            tick = not tick
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == ":" and depth <= 0 and not tick:
            return spec[index + 1 :]
    return spec


def substituted_branch(word: str, cwd: Path | None) -> str | None:
    """The branch a `$(git branch --show-current)`-shaped word names. The substitution runs in
    the shell's folder ``cwd`` (or its own `-C`), not in the pushing git's `-C` folder. None
    for any other word: what `$(make-branch-name)` prints cannot be told."""
    found = _CURRENT_BRANCH.match(word)
    if not found or cwd is None:
        return None
    folder = folder_of(found.group("dir"), cwd) if found.group("dir") else cwd
    return head_branch(folder)  # None for a folder rails cannot find (`$(git -C $WT ...)`)


def push_targets(
    args: list[str], where: Path, cwd: Path | None = None
) -> tuple[list[str], dict[str, bool]]:
    """The destination branches of a `git push`, and its flags of interest.

    A push with no refspec (or `HEAD`) lands on the branch checked out in
    `where`. `+ref` is a forced refspec.
    """
    flags = {"force": False, "dry_run": False, "all": False, "delete": False}
    positional: list[str] = []
    skip = False
    for tok in arguments(args, _PUSH_VALUED):  # `2>&1` is not a refspec
        if skip:
            skip = False
            continue
        if tok in _PUSH_VALUED:
            skip = True
            continue
        if tok.startswith("--"):
            name = tok.split("=", 1)[0]
            if name in ("--force", "--force-with-lease"):
                flags["force"] = True
            elif name == "--dry-run":
                flags["dry_run"] = True
            elif name in ("--all", "--mirror", "--branches"):
                flags["all"] = True
            elif name == "--delete":
                flags["delete"] = True
            continue
        if tok.startswith("-") and len(tok) > 1:
            letters = tok[1:]
            if "f" in letters:
                flags["force"] = True
            if "n" in letters:
                flags["dry_run"] = True
            if "d" in letters:
                flags["delete"] = True
            continue
        positional.append(tok)
    targets: list[str] = []
    refspecs = positional[1:]
    for spec in refspecs:
        if spec.startswith("+"):
            flags["force"] = True
            spec = spec[1:]
        dst = refspec_dst(spec)
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/") :]
        if dst in ("HEAD", "@"):
            dst = head_branch(where) or ""
        elif is_substitution(dst):
            # `$(git branch --show-current)` runs in the shell's folder, not the pushing git's
            dst = substituted_branch(dst, cwd if cwd is not None else where) or ""
        if dst:
            targets.append(dst)
    if not refspecs and not flags["all"]:
        current = head_branch(where)
        if current:
            targets.append(current)
    return targets, flags


def _rm_rf(tokens: list[str]) -> bool:
    if command_name(tokens[0]) != "rm":
        return False
    letters = ""
    long_flags: set[str] = set()
    targets: list[str] = []
    for tok in tokens[1:]:
        if tok.startswith("--"):
            long_flags.add(tok)
        elif tok.startswith("-") and len(tok) > 1:
            letters += tok[1:]
        else:
            targets.append(tok)
    recursive = "r" in letters or "R" in letters or "--recursive" in long_flags
    force = "f" in letters or "--force" in long_flags
    return recursive and force and any(_RM_TARGET.match(t) for t in targets)


def _ps_remove_recurse(tokens: list[str], shell: str = "bash") -> bool:
    if command_name(tokens[0]) not in _PS_REMOVE:
        return False
    recurse = False
    targets: list[str] = []
    skip = False
    # `-r` is `-Recurse` in PowerShell (where `rm` is Remove-Item too); bash `rm -r` keeps
    # `_rm_rf`'s rule
    shortest = 2 if shell != "powershell" and command_name(tokens[0]) == "rm" else 1
    for tok in tokens[1:]:
        if skip:
            skip = False
            continue
        low = tok.lower()
        if low in _PS_REMOVE_VALUED:
            skip = True
            continue
        if low.startswith("-") and len(low) > shortest and "-recurse".startswith(low):
            recurse = True
            continue
        if low.startswith("-"):
            continue
        targets.extend(t for t in tok.split(",") if t)
    return recurse and any(_PS_RM_TARGET.match(t) for t in targets)


def _env_write(tokens: list[str]) -> bool:
    for index, tok in enumerate(tokens):
        redirect = _REDIRECT.match(tok)
        if redirect and ">" in tok:
            path = redirect.group("path")
            if not path and index + 1 < len(tokens):
                path = tokens[index + 1]
            if path and _ENV_FILE.search(path):
                return True
    if command_name(tokens[0]) in _ENV_WRITERS:
        return any(
            _ENV_FILE.search(tok) for tok in tokens[1:] if not tok.startswith("-")
        )
    return False


def _verdict(tokens: list[str], cwd: Path, shell: str = "bash") -> str | None:
    """The original rule's label for the first rule this statement breaks."""
    if tokens and tokens[0] == TOO_DEEP:
        return "launchers nested too deep to judge what they run"
    if _rm_rf(tokens) or _ps_remove_recurse(tokens, shell):
        return "rm -rf targeting root, home, or parent directory"
    if command_name(tokens[0]) == "git":
        sub, args, where = git_subcommand(tokens, cwd)
        if sub == "push":
            targets, flags = push_targets(args, where, cwd)
            if (
                flags["force"]
                and not flags["dry_run"]
                and (flags["all"] or DEFAULT_BRANCHES.intersection(targets))
            ):
                return "force push to main/master"
        if sub == "reset" and "--hard" in args:
            if any(a.startswith("origin") for a in args if not a.startswith("-")):
                return "git reset --hard to remote ref"
        if sub in ("commit", "push") and "--no-verify" in args:
            return "--no-verify bypasses pre-commit checks"
        if sub == "commit" and "-n" in args:
            return "--no-verify bypasses pre-commit checks"
    if _env_write(tokens):
        return "modification of .env file"
    return None


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command:
        return None
    if in_environment(*OVERRIDES):
        return None
    for _segment, tokens in commands(command, shell):
        label = _verdict(tokens, evt.cwd, shell)
        if label:
            shown = command if len(command) <= 400 else command[:400] + " ..."
            return Deny(
                f"BLOCKED: {label}\n"
                f"Command: {shown}\n"
                f"Ask the user to confirm before proceeding, or use a safer alternative.\n"
                f"(The operator can run it themselves with `!` at the prompt; an agent "
                f"cannot override this from the command line.)"
            )
    return None
