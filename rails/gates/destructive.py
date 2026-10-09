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

import re
from pathlib import Path

from rails.hookio import Deny, Event
from rails.shell import segments, words
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
        for stage in pipeline_stages(words(segment, shell)):
            tokens = command_words(stage)
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


def git_subcommand(tokens: list[str], cwd: Path) -> tuple[str, list[str], Path]:
    """`(subcommand, its args, the directory git runs in)` for a git statement."""
    index = 1
    where = cwd
    while index < len(tokens):
        tok = tokens[index]
        if tok in _GIT_VALUED and index + 1 < len(tokens):
            if tok == "-C":
                where = (cwd / tokens[index + 1]).resolve() if cwd else cwd
            index += 2
            continue
        if tok.startswith("-"):
            index += 1
            continue
        return tok, tokens[index + 1 :], where
    return "", [], where


def push_targets(args: list[str], where: Path) -> tuple[list[str], dict[str, bool]]:
    """The destination branches of a `git push`, and its flags of interest.

    A push with no refspec (or `HEAD`) lands on the branch checked out in
    `where`. `+ref` is a forced refspec.
    """
    flags = {"force": False, "dry_run": False, "all": False, "delete": False}
    positional: list[str] = []
    skip = False
    for tok in args:
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
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/") :]
        if dst in ("HEAD", "@"):
            dst = head_branch(where) or ""
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


def _ps_remove_recurse(tokens: list[str]) -> bool:
    if command_name(tokens[0]) not in _PS_REMOVE:
        return False
    recurse = False
    targets: list[str] = []
    skip = False
    for tok in tokens[1:]:
        if skip:
            skip = False
            continue
        low = tok.lower()
        if low in _PS_REMOVE_VALUED:
            skip = True
            continue
        if low.startswith("-") and len(low) > 2 and "-recurse".startswith(low):
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


def _verdict(tokens: list[str], cwd: Path) -> str | None:
    """The original rule's label for the first rule this statement breaks."""
    if tokens and tokens[0] == TOO_DEEP:
        return "launchers nested too deep to judge what they run"
    if _rm_rf(tokens) or _ps_remove_recurse(tokens):
        return "rm -rf targeting root, home, or parent directory"
    if command_name(tokens[0]) == "git":
        sub, args, where = git_subcommand(tokens, cwd)
        if sub == "push":
            targets, flags = push_targets(args, where)
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
        label = _verdict(tokens, evt.cwd)
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
