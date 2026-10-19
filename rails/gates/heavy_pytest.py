"""Refuse a heavy pytest suite that no machine lock sees; name `rails lock suite -- ...`.

`rails check` runs a repo's suite lanes one at a time across the machine (`lock = "suite"`
in `rails/lanes.toml`, rails 1.4.0). A suite an agent starts itself takes no lock, so it
runs beside them. Measured on jarvis, 2026-10-18 14:44: four `pytest -n 4` suites at once
(one `rails check` lane, the `rails trunk` pass, two an agent started through bash) with
Windows commit at 43.7 of 46.4 GB; Docker Desktop's engine died twice that day of the
commit limit (errno 1455). The replay behind the registry row (`hooks/gates.toml`) is the
measurement: in that repo's agent transcripts for 2026-10-05..18, 104 of 1,699 distinct
pytest commands were runs this gate refuses.

**Heavy** = more than one xdist worker over more than ``MAX_NARROW_FILES`` distinct test
files, or over the whole tree (no target). pytest is recognised in command position only:
``pytest``, ``python -m pytest``, or the command after ``uv run`` / ``uvx`` / ``poetry run``
/ ``coverage run -m`` and the like, behind ``timeout`` / ``nice`` / ``env`` / ``time`` and
loop keywords; never as a package name (``uv pip install pytest``). The worker count is the
one pytest would use: the last ``-n`` / ``--numprocesses`` on the command line, else
``PYTEST_ADDOPTS`` (a prefix on that statement; else exported or set earlier in the same
command, ``$env:`` in PowerShell; else this hook's own environment, which the shell
inherits), else ``-o addopts=...``, else the ``addopts`` of the config file pytest itself
picks. That search is pytest 9's: from the common ancestor of the targets that exist (else
the working directory) upward, the first ``pytest.toml`` / ``.pytest.toml`` /
``pytest.ini`` / ``.pytest.ini`` / ``pyproject.toml`` with ``[tool.pytest]`` or
``[tool.pytest.ini_options]`` / ``tox.ini`` ``[pytest]`` / ``setup.cfg`` ``[tool:pytest]``.
That last step is how jarvis's root ``addopts = "... -n auto"`` makes a bare
``uv run pytest ci/`` sixteen workers, while ``uv run pytest apps/purser/tests`` reads that
package's own config and runs serially. A directory counts its ``test_*.py`` /
``*_test.py`` files outside dot directories, ``node_modules`` and the like (pytest's
``norecursedirs``) and outside ``--ignore``; node ids count their file once; a target not
on disk counts one; a target the hook cannot resolve (``$VAR`` it never saw assigned)
counts nothing, and a run whose only targets are unresolved is not judged.

**Not refused:** up to ``MAX_NARROW_FILES`` test files (parallel runs of 2-10 files took a
median 15-27 s in those transcripts); ``-n 0``, ``-n 1``, ``-p no:xdist``; ``--co`` and the
other options that run no test; a run under ``rails lock suite``; pytest in a container
(``docker``, ``podman``, ``kubectl``, ``wsl``: its config and its tree are not this hook's
to read); a repo whose lanes name no ``suite`` lock (there is no queue to send it to).
Quoted spans are data (``rails.shell``): pytest inside ``bash -c "..."`` is not seen, nor
is ``ci/local_lanes.py suite`` run by hand (no pytest word; morphyxAI/jarvis follow-up).

**Also refused:** a statement that sets ``RAILS_LOCKS_HELD`` to a value itself (a prefix,
``export``, ``env``, ``$env:``, ``Set-Item Env:``, ``SetEnvironmentVariable``). `rails lock`
sets it for the command it runs, so a `rails check` under it re-enters the lock it holds
(`rails.store`); set by hand, it would let a suite skip the queue. Reading, clearing or
naming it in an argument is not setting it.

The working directory is followed through ``cd`` / ``Set-Location``, ``pushd`` / ``popd``,
``uv run --directory`` and subshells, whose ``cd`` ends with them.

The remedy is the queue, not an override: the same command with
``rails lock suite --`` in front of the pytest statement, which waits for the running suite
and then runs it (in the background: the wait can be long), or a narrower run. The
operator's switch is ``RAILS_GATES_OFF=heavy_pytest``.
"""

from __future__ import annotations

import glob
import os
import re
import tomllib
from configparser import ConfigParser
from pathlib import Path
from typing import Callable

from rails.gates.destructive import command_name, command_words, pipeline_stages
from rails.hookio import Deny, Event
from rails.shell import scrub, scrubbed_segments, spans, words

NAME = "heavy_pytest"

#: The lock `rails check` takes for a repo's suite lanes, and the one this gate queues on.
LOCK = "suite"
#: More distinct test files than this, run by more than one worker, is a suite.
MAX_NARROW_FILES = 30

_PYTEST = ("pytest", "py.test")
_MENTION = re.compile(r"py\.?test", re.IGNORECASE)
_CD = ("cd", "set-location", "sl", "pushd", "push-location", "chdir")  # popd: judge()
#: Words that run the rest of the statement as a command: shell keywords and plain prefixes.
_PASS_THROUGH = frozenset({"do", "then", "else", "elif", "if", "while", "until", "{", "(", "!",
                           "time", "nohup", "exec", "command", "builtin", "sudo", "&"})
#: Runners whose subcommand runs a command (`uv run X`), and that subcommand.
_RUN_SUBCOMMAND = {"uv": "run", "poetry": "run", "pdm": "run", "hatch": "run", "rye": "run",
                   "pipenv": "run", "pipx": "run"}
#: Those runners' options that take a separate value.
_RUNNER_VALUED = frozenset({
    "--with", "--with-editable", "--with-requirements", "--python", "-p", "--directory",
    "--project", "--package", "--env-file", "--extra", "--group", "--only-group", "--no-group",
    "--index", "--default-index", "--index-url", "-i", "--extra-index-url", "--find-links", "-f",
    "--cache-dir", "--config-file", "--color", "--refresh-package", "--upgrade-package", "-P",
    "--reinstall-package", "--resolution", "--prerelease", "--exclude-newer", "--link-mode",
    "--keyring-provider", "--index-strategy", "--python-platform", "--from", "-e", "--env",
    "-C", "--directory", "--spec",
})
#: pytest options (core and the common plugins) whose value is a separate word, not a target.
_VALUED = frozenset({
    "-k", "-m", "-n", "-p", "-c", "-o", "-W", "-r", "--tb", "--maxfail", "--rootdir",
    "--basetemp", "--deselect", "--ignore", "--ignore-glob", "--junitxml", "--junit-xml",
    "--durations", "--durations-min", "--cov", "--cov-report", "--cov-config",
    "--cov-fail-under", "--timeout", "--timeout-method", "--log-level", "--log-cli-level",
    "--log-file", "--log-file-level", "--log-format", "--confcutdir", "--import-mode", "--dist",
    "--numprocesses", "--maxprocesses", "--max-worker-restart", "--tx", "--rsyncdir",
    "--override-ini", "--capture", "--color", "--code-highlight", "--report-log", "--html",
    "--count", "--repeat-scope", "--asyncio-mode", "--randomly-seed", "--splits", "--group",
    "--reruns", "--reruns-delay", "--json-report-file", "--alluredir", "--benchmark-json",
    "--hypothesis-seed", "--hypothesis-profile", "--last-failed-no-failures", "--lfnf",
    "--config-file", "--inifile",
})
#: pytest's (and the common plugins') long options that take no value. Any other long option
#: followed by a word that does not look like a path is read as taking that word as its value,
#: so an unlisted valued option's value never stands in for a target.
_FLAGS = frozenset({
    "--lf", "--last-failed", "--ff", "--failed-first", "--nf", "--new-first", "--sw",
    "--stepwise", "--sw-skip", "--stepwise-skip", "--exitfirst", "--pdb", "--trace",
    "--no-header", "--no-summary", "--strict-markers", "--strict-config", "--strict",
    "--runxfail", "--disable-warnings", "--disable-pytest-warnings", "--showlocals",
    "--cache-clear", "--setup-show", "--setup-only", "--verbose", "--quiet", "--full-trace",
    "--doctest-modules", "--doctest-continue-on-failure", "--cov-append", "--no-cov",
    "--looponfail", "--forked", "--keep-duplicates", "--noconftest",
    "--continue-on-collection-errors", "--pyargs", "--debug", "--trace-config", "--version",
    "--help", "--co", "--collect-only", "--collectonly", "--fixtures", "--markers",
    "--fixtures-per-test", "--cache-show", "--setup-plan", "--locked",
    "--frozen", "--no-sync", "--isolated", "--offline", "--no-project", "--active",
    "--exact", "--inexact", "--all-extras", "--no-dev", "--dev", "--quiet", "--no-progress",
})
#: Options that collect or report but run no test.
_NO_RUN = frozenset({"--co", "--collect-only", "--collectonly", "--version", "-V", "--help",
                     "-h", "--fixtures", "--funcargs", "--markers", "--fixtures-per-test",
                     "--cache-show", "--setup-plan"})
#: pytest 9's config file names, in its search order (`_pytest/config/findpaths.py`).
_CONFIG_NAMES = ("pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini", "pyproject.toml",
                 "tox.ini", "setup.cfg")
#: pytest's default `norecursedirs`, as far as a test tree holds them (dot dirs separately).
_SKIP_DIRS = frozenset({"node_modules", "venv", "build", "dist", "CVS", "_darcs", "{arch}",
                        "__pycache__", "site-packages"})

#: `2>&1`, `*>&1`: the shell's, alone. `>`, `2>>`, `*>`, `&>`, `<`: a file follows.
#: `>out`, `2>err`, `&>>log`: the file is joined on.
_REDIRECT_DUP = re.compile(r"^(?:\d+|\*)?(?:>>?|<)&\d+$")
_REDIRECT_OP = re.compile(r"^(?:\d+|\*|&)?(?:>>?|<)$")
_REDIRECT_JOINED = re.compile(r"^(?:\d+|\*|&)?(?:>>?|<)")
_MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)")
_VAR = re.compile(r"\$env:(\w+)|\$\{(\w+)\}|\$(\w+)", re.IGNORECASE)
_ASSIGN = re.compile(r"^([A-Za-z_]\w*)=(.*)$", re.DOTALL)
_PS_ASSIGN = re.compile(r"^\s*\$(\w+)\s*=\s*['\"]?([^'\";]+?)['\"]?\s*$")
_PS_ADDOPTS = re.compile(
    r"(?:\$env:PYTEST_ADDOPTS\s*=|Env:PYTEST_ADDOPTS['\"]?\s+(?:-Value\s+)?"
    r"|['\"]PYTEST_ADDOPTS['\"]\s*,)\s*['\"]?([^'\";)]*)",
    re.IGNORECASE,
)
_LEADING_ASSIGNMENTS = re.compile(r"""^\s*(?:[A-Za-z_]\w*=(?:"[^"]*"|'[^']*'|[^\s"'])*\s+)*""")
#: PowerShell setting RAILS_LOCKS_HELD to a value (`$env:X = v`, `Set-Item Env:X v`), read on
#: the scrubbed statement; and the .NET call, whose quoted name scrubbing would hide.
_FORGE_PS_ENV = re.compile(r"\$env:RAILS_LOCKS_HELD\s*=(?!=)", re.IGNORECASE)
_FORGE_PS_ITEM = re.compile(r"(?:Set|New)-Item\s+(?:-Path\s+)?Env:\\?RAILS_LOCKS_HELD\b", re.IGNORECASE)
#: The .NET call: found on the scrubbed text (code, not a quoted mention); its quoted name
#: and value are read from the original at that offset.
_FORGE_CALL = re.compile(r"SetEnvironmentVariable\s*\(", re.IGNORECASE)
_FORGE_CALL_ARGS = re.compile(
    r"""\s*['"]RAILS_LOCKS_HELD['"]\s*,(?!\s*(?:\$null\b|''|""|\)))""", re.IGNORECASE
)
#: `cd` to the repo's top, the worktree idiom.
_TOPLEVEL = re.compile(r"""\$\(\s*git\s+rev-parse\s+--show-toplevel\s*\)|`\s*git\s+rev-parse\s+--show-toplevel\s*`""")


# --- where the shell is, and what a path means there -------------------------------------


def local_path(raw: str, variables: dict[str, str]) -> str:
    """A path as the shell would see it: `$VAR` / `${VAR}` / `$env:VAR` from assignments
    earlier in the command or the environment, quotes dropped, `~` expanded, and on Windows
    Git Bash's `/c/...` as `C:/...`. A variable it cannot resolve stays as written."""

    def value(m: re.Match[str]) -> str:
        name = m.group(1) or m.group(2) or m.group(3)
        found = variables.get(name) if m.group(1) is None else None
        if found is None:
            found = os.environ.get(name)
        if found is None and name.upper() == "HOME":
            found = str(Path.home())
        return found if found is not None else m.group(0)

    text = _VAR.sub(value, raw).strip("'\"")
    if os.name == "nt":
        text = _MSYS_DRIVE.sub(lambda m: f"{m.group(1).upper()}:", text)
    if text == "~" or text.startswith(("~/", "~\\")):
        text = str(Path.home()) + text[1:]
    return text


def resolve(base: Path, raw: str, variables: dict[str, str]) -> Path:
    path = Path(local_path(raw, variables))
    return path if path.is_absolute() else base / path


def _unresolved(text: str) -> bool:
    return "$" in text or "`" in text or "%" in text


# --- what runs: pytest, in command position ------------------------------------------------


def _looks_like_path(word: str) -> bool:
    return any(mark in word for mark in ("/", "\\", ".py", "::", "*")) or word in (".", "..")


def _is_command(word: str) -> bool:
    """A word that starts a command this gate reads (pytest, python, a runner, rails)."""
    name = command_name(word)
    return (
        name in _PYTEST
        or name in _RUN_SUBCOMMAND
        or name in ("uvx", "coverage", "rails", "rails.py", "py")
        or name.startswith("python")
    )


def _strip_prefix(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    """The command a prefix runs (`timeout 600 X`, `nice -n 5 X`, `env A=1 X`, `do X`,
    `(cd X`), and the variables the prefix sets for it."""
    tokens = list(tokens)
    assigned: dict[str, str] = {}
    i = 0
    while i < len(tokens):
        word, name = tokens[i], command_name(tokens[i])
        if len(word) > 1 and word[0] in "({":
            tokens[i] = word[1:]  # `(cd`: a subshell or group opened on the word
            continue
        found = _ASSIGN.match(word)
        if found:
            assigned[found.group(1)] = found.group(2)
            i += 1
        elif name in _PASS_THROUGH:
            i += 1
        elif name == "timeout":
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 2 if tokens[i] in ("-s", "-k", "--signal", "--kill-after") else 1
            i += 1  # the duration
        elif name == "nice":
            i += 1
            if i < len(tokens) and tokens[i] == "-n":
                i += 2
            elif i < len(tokens) and re.match(r"^-(?:n)?-?\d+$", tokens[i]):
                i += 1
        elif name == "env":
            i += 1
            while i < len(tokens) and (tokens[i].startswith("-") or _ASSIGN.match(tokens[i])):
                found = _ASSIGN.match(tokens[i])
                if found:
                    assigned[found.group(1)] = found.group(2)
                i += 2 if tokens[i] in ("-u", "--unset", "-C", "--chdir") else 1
        elif name in ("xvfb-run", "stdbuf"):
            i += 1
            while i < len(tokens) and tokens[i].startswith("-"):
                i += 1
        else:
            break
    return tokens[i:], assigned


def _skip_options(words_: list[str]) -> tuple[list[str], str | None]:
    """A runner's own options, skipped: the words after them, and `--directory`'s value. A
    long option it does not know takes the next word as its value unless that word starts a
    command (`uv run --no-extra gpu pytest`, but `uv run --locked pytest`)."""
    directory = None
    j = 0
    while j < len(words_) and words_[j].startswith("-"):
        word = words_[j]
        if word == "--":
            return words_[j + 1 :], directory
        if word == "--directory" and j + 1 < len(words_):
            directory = words_[j + 1]
        elif word.startswith("--directory="):
            directory = word.split("=", 1)[1]
        if word in _RUNNER_VALUED:
            j += 2
        elif (
            word.startswith("--")
            and "=" not in word
            and word not in _FLAGS
            and j + 1 < len(words_)
            and not words_[j + 1].startswith("-")
            and not _is_command(words_[j + 1])
            and words_[j + 1] not in _RUN_SUBCOMMAND.values()
            and words_[j + 1] != "tool"
        ):
            j += 2
        else:
            j += 1
    return words_[j:], directory


def _coverage(words_: list[str]) -> tuple[str, list[str], str | None] | None:
    """`coverage run [its options] -m pytest ...` (or a pytest script)."""
    if words_[:1] != ["run"]:
        return None
    rest = words_[1:]
    for j, word in enumerate(rest):
        if word == "-m":
            target = rest[j + 1] if j + 1 < len(rest) else ""
            return ("pytest", rest[j + 2 :], None) if target in _PYTEST else None
        if not word.startswith("-") and command_name(word) in _PYTEST:
            return "pytest", rest[j + 1 :], None
    return None


def _after_rails(words_: list[str]) -> tuple[str, list[str], str | None] | None:
    """`rails lock <name> -- X`: queued when the name is the suite lock, else X is judged."""
    if len(words_) >= 2 and words_[0] == "lock":
        if words_[1] == LOCK:
            return None
        rest = words_[2:]
        return invocation(rest[1:] if rest[:1] == ["--"] else rest)
    return None


def _python_module(words_: list[str]) -> tuple[str, list[str], str | None] | None:
    """`python [options] -m pytest ...`, or a pytest (or rails) script run by python."""
    j = 0
    while j < len(words_):
        word = words_[j]
        if word == "-m":
            target = words_[j + 1] if j + 1 < len(words_) else ""
            if target == "coverage":
                return _coverage(words_[j + 2 :])
            return ("pytest", words_[j + 2 :], None) if target in _PYTEST else None
        if word.startswith("-m") and len(word) > 2:
            return ("pytest", words_[j + 1 :], None) if word[2:] in _PYTEST else None
        if word in ("-c", "-"):
            return None
        if word in ("-X", "-W", "-Q"):
            j += 2
            continue
        if word.startswith("-"):
            j += 1
            continue
        name = command_name(word)
        if name in _PYTEST:
            return "pytest", words_[j + 1 :], None
        if name == "rails.py" or name == "rails":
            return _after_rails(words_[j + 1 :])
        return None
    return None


def invocation(tokens: list[str]) -> tuple[str, list[str], str | None] | None:
    """``("pytest", args, directory)`` when this statement runs pytest on this machine, else
    None. ``directory`` is a runner's `--directory`, if any. A container runner (`docker`,
    `podman`, `kubectl`, `wsl`) is not one of the runners read here: its pytest reads a
    config and a tree this hook cannot see."""
    tokens, _ = _strip_prefix([t.strip() for t in tokens if t.strip()])
    if not tokens:
        return None
    name = command_name(tokens[0])
    if name in _PYTEST:
        return "pytest", tokens[1:], None
    if name == "rails":
        return _after_rails(tokens[1:])
    if name in ("python", "python3", "py") or re.match(r"^python\d+(?:\.\d+)?$", name):
        return _python_module(tokens[1:])
    if name == "uvx" or (name == "uv" and tokens[1:3] == ["tool", "run"]):
        rest, directory = _skip_options(tokens[1:] if name == "uvx" else tokens[3:])
        if rest and command_name(rest[0]) in _PYTEST:
            return "pytest", rest[1:], directory
        return None
    if name == "coverage":
        return _coverage(tokens[1:])
    sub = _RUN_SUBCOMMAND.get(name)
    if sub is None:
        return None
    rest, directory = _skip_options(tokens[1:])
    if not rest or rest[0] != sub:
        return None
    rest, inner_directory = _skip_options(rest[1:])
    inner = invocation(rest)
    if inner is None:
        return None
    kind, args, nested = inner
    return kind, args, nested or inner_directory or directory


# --- what pytest is asked to do ----------------------------------------------------------


def _workers(value: str) -> int | None:
    value = value.strip().lower()
    if value in ("auto", "logical"):
        return os.cpu_count() or 2
    try:
        return int(value)
    except ValueError:
        return None


def explicit_workers(args: list[str]) -> int | None:
    """The worker count these words set (the last one wins), or None when they set none."""
    found: int | None = None
    i = 0
    while i < len(args):
        tok = args[i]
        if tok in ("-n", "--numprocesses") and i + 1 < len(args):
            value = _workers(args[i + 1])
            found = value if value is not None else found
            i += 2
            continue
        if tok.startswith("--numprocesses="):
            found = _workers(tok.split("=", 1)[1])
        elif tok.startswith("-n") and len(tok) > 2 and not tok.startswith("--"):
            found = _workers(tok[2:].lstrip("="))
        elif tok == "-p" and i + 1 < len(args) and args[i + 1] == "no:xdist":
            found = 0
        elif tok == "-pno:xdist":
            found = 0
        i += 1
    return found


def _option_values(args: list[str], *names: str) -> list[str]:
    found = []
    for i, tok in enumerate(args):
        if tok in names and i + 1 < len(args):
            found.append(args[i + 1])
        for name in names:
            if name.startswith("--") and tok.startswith(name + "="):
                found.append(tok.split("=", 1)[1])
    return found


def _addopts_override(args: list[str]) -> str | None:
    """`-o addopts=...` replaces the config's addopts outright."""
    for value in _option_values(args, "-o", "--override-ini"):
        if value.lower().startswith("addopts="):
            return value.split("=", 1)[1]
    for tok in args:
        if tok.lower().startswith("-oaddopts="):
            return tok[len("-oaddopts=") :]
    return None


def targets(args: list[str], exists: Callable[[str], bool] | None = None) -> list[str]:
    """The paths and node ids pytest is given: not options, their values, or redirections.
    A word after a long option it does not know is that option's value, unless ``exists``
    says it is on disk (`--runslow tests`)."""
    found: list[str] = []
    args = ["" if a.strip() in (")", "}") else a.strip() for a in args]
    i = 0
    while i < len(args):
        tok = args[i]
        if not tok or tok == "&":
            i += 1
        elif _REDIRECT_DUP.match(tok):
            i += 1
        elif _REDIRECT_OP.match(tok):
            i += 2
        elif _REDIRECT_JOINED.match(tok):
            i += 1
        elif tok == "--":
            # Everything after is a target, bar the shell's own words.
            rest = args[i + 1 :]
            j = 0
            while j < len(rest):
                word = rest[j]
                if _REDIRECT_OP.match(word):
                    j += 2
                    continue
                if word.strip() and word != "&" and not _REDIRECT_JOINED.match(word):
                    found.append(word)
                j += 1
            break
        elif tok in _VALUED:
            i += 2
        elif (
            tok.startswith("--")
            and "=" not in tok
            and tok not in _FLAGS
            and i + 1 < len(args)
            and args[i + 1]
            and not args[i + 1].startswith("-")
            and not _looks_like_path(args[i + 1])
            and not (exists is not None and exists(args[i + 1]))
        ):
            i += 2  # an option it does not know, with a value that is no path
        elif tok.startswith("-"):
            i += 1
        else:
            found.append(tok)
            i += 1
    return found


# --- the config pytest would read ------------------------------------------------------


def _read_toml(path: Path) -> dict | None:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None


def _pytest_table(path: Path) -> dict | None:
    """The pytest settings a config file holds, or None when it is not a pytest config. Read
    by kind, as pytest reads a `-c` file of any name: `.toml` (the `[pytest]` table of a
    pytest.toml, else `[tool.pytest]`), `.cfg` (`[tool:pytest]`), anything else as ini."""
    try:
        if not path.is_file():
            return None
    except OSError:
        return None
    if path.name in ("pytest.toml", ".pytest.toml"):
        data = _read_toml(path)
        table = data.get("pytest", {}) if data else {}
        return table if isinstance(table, dict) else {}  # always pytest's config, even empty
    if path.suffix == ".toml":
        data = _read_toml(path)
        tool = (data or {}).get("tool", {}).get("pytest")
        if not isinstance(tool, dict):
            return None
        native = {k: v for k, v in tool.items() if k != "ini_options"}
        if native:
            return native
        ini = tool.get("ini_options")
        return ini if isinstance(ini, dict) else None
    parser = ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except Exception:  # noqa: BLE001 - a file pytest cannot read either
        return None
    section = "tool:pytest" if path.suffix == ".cfg" else "pytest"
    if parser.has_section(section):
        return dict(parser.items(section))
    return {} if path.name in ("pytest.ini", ".pytest.ini") else None


def find_config(base: Path, paths: list[Path]) -> tuple[Path, dict] | None:
    """pytest's own search: the common ancestor of the targets that exist (else the working
    directory), then upward; the first file that configures pytest, with its settings."""
    existing = []
    for path in paths:
        try:
            if path.exists():
                existing.append(path.resolve())
        except OSError:
            continue
    ancestor = base.resolve()
    if existing:
        try:
            ancestor = Path(os.path.commonpath([str(p) for p in existing]))
        except ValueError:  # targets on different drives
            pass
        if ancestor.is_file():
            ancestor = ancestor.parent
    for directory in (ancestor, *ancestor.parents):
        for name in _CONFIG_NAMES:
            table = _pytest_table(directory / name)
            if table is not None:
                return directory / name, table
    return None


def _addopts_words(table: dict) -> list[str]:
    value = table.get("addopts", "")
    if isinstance(value, list):
        return [str(v) for v in value]
    return str(value).split()


def _norm(path: Path) -> str:
    try:
        path = path.resolve()
    except OSError:
        pass
    return os.path.normcase(str(path))


def count_test_files(paths: list[Path], limit: int, ignored: list[Path] | None = None) -> int:
    """How many distinct test files the targets name, counting no further than ``limit + 1``."""
    skip = {_norm(p) for p in ignored or []}

    def is_ignored(text: str) -> bool:
        return any(text == s or text.startswith(s.rstrip("\\/") + os.sep) for s in skip)

    files: set[str] = set()
    for path in paths:
        norm = _norm(path)
        if is_ignored(norm):
            continue
        if str(path).endswith(".py") or path.is_file():
            files.add(norm)
        elif path.is_dir():
            # Walked resolved, as `--ignore` paths are: a cwd reached through a junction or a
            # symlink must still match them.
            for root, dirs, names in os.walk(path.resolve()):
                dirs[:] = [
                    d for d in dirs
                    if d not in _SKIP_DIRS and not d.startswith(".")
                    and not is_ignored(os.path.normcase(os.path.join(root, d)))
                ]
                for f in names:
                    if f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py")):
                        full = os.path.normcase(os.path.join(root, f))
                        if not is_ignored(full):
                            files.add(full)
                if len(files) > limit:
                    return len(files)
        else:
            files.add(norm)  # not on disk: one unknown target, which pytest refuses anyway
        if len(files) > limit:
            return len(files)
    return len(files)


def suite_lock_declared(where: Path) -> bool:
    """Whether the repo at ``where`` runs its suite lanes under the `suite` lock."""
    from rails import lanes, store
    from rails.check import find_lanes_file

    repo = store.find_repo(where)
    if repo is None:
        return False
    path = find_lanes_file(repo.top)
    if path is None:
        return False
    try:
        config = lanes.load(path)
    except Exception:  # noqa: BLE001 - a broken lanes file is `rails check`'s to report
        return False
    return any(lane.lock == LOCK for lane in config.lanes)


# --- the verdict -----------------------------------------------------------------------


def _toplevel(base: Path) -> Path:
    """What `git rev-parse --show-toplevel` prints from ``base``: its worktree's top."""
    from rails import store

    repo = store.find_repo(base)
    return repo.top if repo is not None else base


def _cd_target(tokens: list[str]) -> str | None:
    """Where `cd` / `pushd` / `Set-Location` goes: its first word that is no option and no
    redirection (`pushd apps > /dev/null`)."""
    i = 1
    while i < len(tokens):
        word = tokens[i]
        if _REDIRECT_OP.match(word):
            i += 2
            continue
        if word in ("-", "-Path", "-LiteralPath") or word.startswith("-") or _REDIRECT_JOINED.match(word):
            i += 1
            continue
        return word.rstrip(")")
    return None


def judge(command: str, shell: str, cwd: Path) -> tuple[str, int, int] | None:
    """``(why, start, end)`` for the first heavy pytest run in ``command`` (the offsets of its
    statement), else None."""
    base = cwd
    lost = False  # after a `cd` it could not resolve: where the shell is, it cannot tell
    subshells: list[tuple[Path, bool]] = []  # where each open `(` will return to
    pushed: list[tuple[Path, bool]] = []  # pushd's stack
    variables: dict[str, str] = {}
    persistent = os.environ.get("PYTEST_ADDOPTS")  # what the shell inherits
    for start, end in spans(command, shell):
        segment = command[start:end]
        if shell == "powershell":
            found = _PS_ADDOPTS.search(segment)
            if found:
                persistent = found.group(1)
            assigned = _PS_ASSIGN.match(segment)
            if assigned:
                variables[assigned.group(1)] = local_path(assigned.group(2), variables)
        # A `\`-newline continuation is a word of its own (`targets` and `invocation` strip
        # one that ends a word).
        stages = [[t for t in stage if t.strip()] for stage in pipeline_stages(words(segment, shell))]
        stages = [stage for stage in stages if stage]
        opened, closed = _subshell_edges(segment, shell, stages, len(subshells))
        subshells.extend([(base, lost)] * opened)
        for stage in stages:
            local: str | None = None
            for tok in stage:
                assigned = _ASSIGN.match(tok)
                if not assigned:
                    break
                variables[assigned.group(1)] = local_path(assigned.group(2), variables)
                if assigned.group(1) == "PYTEST_ADDOPTS":
                    local = assigned.group(2)
            tokens = command_words(stage)
            if not tokens:
                # A plain shell variable reaches pytest only when it is already exported.
                if local is not None and persistent is not None:
                    persistent = local
                continue
            tokens, prefixed = _strip_prefix(tokens)
            if "PYTEST_ADDOPTS" in prefixed:  # `env PYTEST_ADDOPTS=... X`, `do A=1 X`
                local = prefixed["PYTEST_ADDOPTS"]
            if not tokens:
                continue
            name = command_name(tokens[0])
            if name == "export":
                for tok in tokens[1:]:
                    assigned = _ASSIGN.match(tok)
                    if assigned:
                        variables[assigned.group(1)] = local_path(assigned.group(2), variables)
                        if assigned.group(1) == "PYTEST_ADDOPTS":
                            persistent = assigned.group(2)
                continue
            if name == "unset" and "PYTEST_ADDOPTS" in tokens:
                persistent = None
                continue
            if name in _CD:
                target = _cd_target(tokens)
                if target:
                    if name in ("pushd", "push-location"):
                        pushed.append((base, lost))
                    # `cd "$(git rev-parse --show-toplevel)/pkg"`: the worktree's top, then the rest.
                    top = _toplevel(base).as_posix()
                    if _TOPLEVEL.search(target):
                        target = _TOPLEVEL.sub(lambda _m: top, target)
                    elif _TOPLEVEL.search(segment):  # unquoted: the substitution split into words
                        target = top
                    # A directory it cannot resolve (`cd "$DIR"`, DIR set out of its sight)
                    # leaves the shell where it cannot follow: what runs there is not judged.
                    lost = _unresolved(local_path(target, variables))
                    if not lost:
                        base = resolve(base, target, variables)
                continue
            if name in ("popd", "pop-location"):
                base, lost = pushed.pop() if pushed else (base, lost)
                continue
            found = invocation(tokens)
            if found is None or lost:
                continue
            _, args, directory = found
            if any(a in _NO_RUN for a in args):
                continue
            here = resolve(base, directory, variables) if directory else base
            env_addopts = local if local is not None else persistent
            why = _heavy(args, here, variables, env_addopts)
            if why:
                return why, start, end
        for _ in range(closed):
            # A subshell's `cd` ends with it: later statements run where it started.
            base, lost = subshells.pop()
    return None


def _subshell_edges(
    segment: str, shell: str, stages: list[list[str]], open_before: int
) -> tuple[int, int]:
    """How many subshells this statement opens (`(` leading its first word) and closes, with
    those parens stripped from the words in place. A closing `)` is one the statement's code
    does not balance (quoted text and `$(...)` balance their own), wherever it sits: before a
    redirection, a pipe or `&` as well as last. Never more close than are open."""
    opened = 0
    first = stages[0] if stages else []
    at = 0  # past prefix words: `time (`, `if (`, `! (`
    while at < len(first) and not first[at].startswith("(") and command_name(first[at]) in _PASS_THROUGH:
        at += 1
    while at < len(first) and first[at].startswith("("):
        word = first[at]
        bare = word.lstrip("(")
        opened += len(word) - len(bare)
        if bare:
            first[at] = bare
            break
        del first[at]
    code = scrub(segment, shell)
    unmatched = code.count(")") - (code.count("(") - opened)
    closed = max(0, min(unmatched, open_before + opened))
    left = closed
    for stage in stages:  # from the start: the subshell closes before a pipe's later stages
        j = 0
        while j < len(stage) and left:
            word = stage[j]
            extra = word.count(")") - word.count("(")
            # The parens end the word, or come just before an operator glued on (`4)&`,
            # `4)>log`, `4)|tail`): that operator and what follows are the shell's.
            tail = re.search(r"(\)+)([&|<>].*)?$", word)
            if extra > 0 and tail:
                count = min(extra, left, len(tail.group(1)))
                left -= count
                word = word[: tail.start()] + tail.group(1)[count:]
                if word:
                    stage[j] = word
                else:
                    del stage[j]
                    continue
            j += 1
    return opened, closed


def _heavy(args: list[str], here: Path, variables: dict[str, str], env_addopts: str | None) -> str | None:
    if not suite_lock_declared(here):
        return None
    raw_targets = targets(args, lambda word: resolve(here, word, variables).exists())
    resolved = [t for t in raw_targets if not _unresolved(local_path(t.split("::", 1)[0], variables))]
    if raw_targets and not resolved:
        return None  # only targets it cannot read: not judged
    paths = [p for raw in resolved for p in _expand(here, raw, variables)]
    workers = explicit_workers(args)
    source = "on the command line"
    if workers is None and env_addopts:
        workers = explicit_workers(env_addopts.split())
        source = "from PYTEST_ADDOPTS"
    if workers is None:
        override = _addopts_override(args)
        if override is not None:
            workers = explicit_workers(override.split())
            source = "from -o addopts"
        else:
            named = _option_values(args, "-c", "--config-file", "--inifile")
            if named:
                config = resolve(here, named[-1], variables)
                table = _pytest_table(config)  # pytest reads a `-c` file of any name
                found = (config, table if table is not None else {})
            else:
                found = find_config(here, paths)
            if found is not None:
                workers = explicit_workers(_addopts_words(found[1]))
                source = f"from addopts in {found[0].name}"
    if not workers or workers <= 1:
        return None
    if paths:
        ignored = [resolve(here, v, variables) for v in _option_values(args, "--ignore")]
        if count_test_files(paths, MAX_NARROW_FILES, ignored) <= MAX_NARROW_FILES:
            return None
    scope = " ".join(raw_targets) if raw_targets else "the whole tree"
    return f"{workers} workers ({source}) over {scope[:120]}"


def _expand(here: Path, raw: str, variables: dict[str, str]) -> list[Path]:
    node = raw.split("::", 1)[0]
    path = resolve(here, node, variables)
    if any(ch in node for ch in "*?["):
        matches = sorted(glob.glob(str(path)))
        if matches:
            return [Path(m) for m in matches]
    return [path]


def queued(command: str, start: int, end: int, shell: str) -> str:
    """The command as typed, with `rails lock suite --` in front of the command of the
    statement at ``command[start:end]`` (after its `VAR=value` prefixes), or a placeholder
    when that cannot be shown."""
    statement = command[start:end]
    lead = _LEADING_ASSIGNMENTS.match(statement).end() if shell == "bash" else 0  # type: ignore[union-attr]
    body = statement[lead:].lstrip()
    placeholder = f"rails lock {LOCK} -- <this pytest command>"
    if not body or body[0] in "({" or command_name(body.split()[0]) in _PASS_THROUGH:
        return placeholder
    rewritten = f"{statement[:lead]}rails lock {LOCK} -- {body}".strip()
    whole = f"{command[:start]}{rewritten}{command[end:]}".strip()
    for text in (whole, rewritten):
        if len(text) <= 300 and "\n" not in text:
            return text
    return placeholder


def _sets_marker(word: str) -> bool:
    found = _ASSIGN.match(word)
    return bool(found and found.group(1) == "RAILS_LOCKS_HELD" and found.group(2).strip())


def forges_held_lock(command: str, shell: str) -> bool:
    """Whether a statement sets `RAILS_LOCKS_HELD` to a value itself: as a command's prefix,
    through `export` / `env`, `$env:`, `Set-Item Env:` or `SetEnvironmentVariable`. Reading,
    clearing, or naming it in an argument or quoted text is not setting it."""
    if "RAILS_LOCKS_HELD" not in command:
        return False

    def a_value(text: str) -> bool:
        text = text.strip()
        return bool(text) and not text.lower().startswith("$null") and not text.startswith(("''", '""'))

    for original, scrubbed in scrubbed_segments(command, shell):
        # The name (or the call) is code on the scrubbed text; a value, often quoted, is read
        # from the original at the same offset.
        for found in _FORGE_CALL.finditer(scrubbed):
            if _FORGE_CALL_ARGS.match(original, found.end()):
                return True
        if shell == "powershell":
            for found in _FORGE_PS_ITEM.finditer(scrubbed):
                rest = original[found.end() :].strip()
                rest = re.sub(r"^-Value\s+", "", rest, flags=re.IGNORECASE)
                if a_value(rest.split(";")[0]):
                    return True
            for found in _FORGE_PS_ENV.finditer(scrubbed):
                if a_value(original[found.end() :]):
                    return True
        for stage in pipeline_stages(words(original, shell)):
            stage = [t for t in stage if t.strip()]
            i = 0
            while i < len(stage) and _ASSIGN.match(stage[i]):
                if _sets_marker(stage[i]):
                    return True
                i += 1
            if i < len(stage) and command_name(stage[i]) in ("export", "env", "set", "setx", "declare", "typeset"):
                # Its own assignments only, up to the command it runs.
                for word in stage[i + 1 :]:
                    if _ASSIGN.match(word):
                        if _sets_marker(word):
                            return True
                    elif not word.startswith("-"):
                        break
    return False


def check(evt: Event):
    shell = evt.shell
    command = evt.command or ""
    if shell is None:
        return None
    if forges_held_lock(command, shell):
        return Deny(
            "rails: `RAILS_LOCKS_HELD` is how `rails lock` tells the command it runs that the "
            "lock is already held; set by hand, it lets a suite skip the queue for every lock it "
            f"names. Run the command as `rails lock {LOCK} -- <command>`, which sets it."
        )
    if not _MENTION.search(command):
        return None
    try:
        found = judge(command, shell, evt.cwd)
    except Exception:  # noqa: BLE001 - fail open: a hook bug never blocks a test run
        return None
    if found is None:
        return None
    why, start, end = found
    return Deny(
        f"rails: this pytest runs {why}: a heavy suite that no lock on this machine sees. "
        f"`rails check` runs suites one at a time (lock `{LOCK}`), and a suite started beside "
        "them is how four ran at once and Windows hit its commit limit (2026-10-18). Queue it: "
        f"`{queued(command, start, end, shell)}` (run it in the background; it waits for the "
        f"suite that is running). Or make it light: name up to {MAX_NARROW_FILES} test files, "
        "or add `-n 0`."
    )
