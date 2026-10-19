"""Refuse a heavy pytest suite that no machine lock sees; name `rails lock suite -- ...`.

`rails check` runs a repo's suite lanes one at a time across the machine (`lock = "suite"`
in `rails/lanes.toml`, rails 1.4.0). A suite an agent starts itself takes no lock, so it
runs beside them. Measured on jarvis, 2026-10-18 14:44: four `pytest -n 4` suites at once
(one `rails check` lane, the `rails trunk` pass, two an agent started through bash) with
Windows commit at 43.7 of 46.4 GB; Docker Desktop's engine died twice that day of the
commit limit (errno 1455). In 14 days of that repo's transcripts, 1,732 of 10,102 agent
pytest commands were runs this gate refuses.

**Heavy** = more than one xdist worker over more than ``MAX_NARROW_FILES`` test files, or
over the whole tree (no target). The worker count is the one pytest would use: the last
``-n`` / ``--numprocesses`` on the command line, else ``PYTEST_ADDOPTS`` (a prefix, or set
in an earlier statement of the same command), else ``-o addopts=...``, else the ``addopts``
of the config file pytest itself picks: from the common ancestor of the targets that exist
(else the working directory) upward, the first ``pytest.ini`` / ``.pytest.ini`` /
``pyproject.toml`` with ``[tool.pytest.ini_options]`` / ``tox.ini`` ``[pytest]`` /
``setup.cfg`` ``[tool:pytest]``. That last step is how jarvis's root
``addopts = "... -n auto"`` makes a bare ``uv run pytest ci/`` sixteen workers, while
``uv run pytest apps/purser/tests`` reads that package's own config and runs serially.
A target directory counts its ``test_*.py`` / ``*_test.py`` files; a file or node id counts
one; a target that is not on disk counts one (never a reason to refuse).

**Not refused:** up to ``MAX_NARROW_FILES`` test files (parallel runs of 2-10 files took a
median 15-27 s in those transcripts); ``-n 0``, ``-n 1``, ``-p no:xdist``; ``--co`` and the
other options that run no test; a run already under ``rails lock suite``; pytest in a
container (``docker``, ``podman``, ``kubectl``, ``wsl``: its config and its tree are not
this hook's to read); a repo whose lanes name no ``suite`` lock (there is no queue to send
it to). Quoted spans are data (``rails.shell``): pytest inside ``bash -c "..."`` is not seen.

The remedy is the queue, not an override: ``rails lock suite -- <the same command>`` waits
for the running suite and then runs it (in the background: the wait can be long), or a
narrower run. The operator's switch is ``RAILS_GATES_OFF=heavy_pytest``.
"""

from __future__ import annotations

import glob
import os
import re
import tomllib
from configparser import ConfigParser
from pathlib import Path

from rails.gates.destructive import command_name, command_words, pipeline_stages
from rails.hookio import Deny, Event
from rails.shell import segments, words

NAME = "heavy_pytest"

#: The lock `rails check` takes for a repo's suite lanes, and the one this gate queues on.
LOCK = "suite"
#: More test files than this, run by more than one worker, is a suite.
MAX_NARROW_FILES = 30

_PYTEST = ("pytest", "py.test")
#: Commands that run another command after their own options: pytest may sit after them.
_RUNNERS = ("uv", "uvx", "poetry", "pdm", "hatch", "rye", "pipx", "py", "nox", "tox", "env",
            "sudo", "time", "timeout", "nice", "coverage", "xvfb-run")
#: Runners whose pytest reads a config this hook cannot see.
_CONTAINERS = ("docker", "docker-compose", "podman", "kubectl", "wsl")
_CD = ("cd", "set-location", "sl", "pushd", "chdir")
#: pytest options (core and the common plugins) whose value is a separate word, not a target.
_VALUED = frozenset({
    "-k", "-m", "-n", "-p", "-c", "-o", "-W", "-r", "--tb", "--maxfail", "--rootdir",
    "--basetemp", "--deselect", "--ignore", "--ignore-glob", "--junitxml", "--junit-xml",
    "--durations", "--durations-min", "--cov", "--cov-report", "--cov-config",
    "--cov-fail-under", "--timeout", "--timeout-method", "--log-level", "--log-cli-level",
    "--log-file", "--log-file-level", "--log-format", "--confcutdir", "--import-mode", "--dist",
    "-d", "--numprocesses", "--maxprocesses", "--max-worker-restart", "--tx", "--rsyncdir",
    "--override-ini", "--capture", "--color", "--code-highlight", "--report-log", "--html",
    "--count", "--repeat-scope", "--asyncio-mode", "--randomly-seed", "--splits", "--group",
    "--reruns", "--reruns-delay", "--json-report-file", "--alluredir", "--benchmark-json",
    "--hypothesis-seed", "--hypothesis-profile", "--last-failed-no-failures", "--lfnf",
    "--config-file", "--inifile",
})
#: Options that collect or report but run no test.
_NO_RUN = frozenset({"--co", "--collect-only", "--collectonly", "--version", "-V", "--help",
                     "-h", "--fixtures", "--funcargs", "--markers", "--fixtures-per-test",
                     "--cache-show", "--setup-plan"})
_INI_NAMES = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")
_SKIP_DIRS = frozenset({"node_modules", "__pycache__", "venv", "dist", "build", "site-packages"})

_REDIRECT = re.compile(r"^(?:\d|&)?>>?|^<|^\d?>&\d$")
_REDIRECT_WITH_TARGET = frozenset({">", ">>", "1>", "2>", "2>>", "&>", "<"})
_MSYS_DRIVE = re.compile(r"^/([A-Za-z])(?=/|$)")
_VAR = re.compile(r"\$\{(\w+)\}|\$(\w+)")
_ASSIGN = re.compile(r"^(?:export\s+)?([A-Za-z_]\w*)=(\S*)$")
_PS_ASSIGN = re.compile(r"^\s*\$(\w+)\s*=\s*['\"]?([^'\";]+?)['\"]?\s*$")
_ADDOPTS_SET = re.compile(
    r"PYTEST_ADDOPTS\s*=\s*['\"]?([^'\";]*)|Env:PYTEST_ADDOPTS['\"]?\s*(?:-Value\s+)?=?\s*['\"]([^'\"]*)",
    re.IGNORECASE,
)


# --- where the shell is, and what a path means there -------------------------------------


def local_path(raw: str, variables: dict[str, str]) -> str:
    """A path as the shell would see it: `$VAR` from assignments earlier in the command,
    quotes dropped, and on Windows Git Bash's `/c/...` as `C:/...`."""
    text = _VAR.sub(lambda m: variables.get(m.group(1) or m.group(2), m.group(0)), raw)
    text = text.strip("'\"")
    if os.name == "nt":
        text = _MSYS_DRIVE.sub(lambda m: f"{m.group(1).upper()}:", text)
    if text == "~" or text.startswith(("~/", "~\\")):
        text = str(Path.home()) + text[1:]
    return text


def resolve(base: Path, raw: str, variables: dict[str, str]) -> Path:
    path = Path(local_path(raw, variables))
    return path if path.is_absolute() else base / path


# --- what pytest is asked to do ----------------------------------------------------------


def pytest_args(tokens: list[str]) -> list[str] | None:
    """The words pytest gets, or None when this stage does not run pytest."""
    names = [command_name(t) for t in tokens]
    if names[0] in _PYTEST:
        return tokens[1:]
    first = names[0]
    if first not in _RUNNERS and first not in _CONTAINERS and not first.startswith("python"):
        return None
    for i, name in enumerate(names):
        if i and name in _PYTEST:
            return tokens[i + 1 :]  # `uv run pytest`, `python -m pytest`, `uv run python -m pytest`
    return None


def under_lock(tokens: list[str]) -> bool:
    """`rails lock suite -- ...` (or through `ci/rails.py`): already queued."""
    names = [command_name(t) for t in tokens]
    for i, name in enumerate(names[:-2]):
        if name in ("rails", "rails.py") and names[i + 1] == "lock" and tokens[i + 2] == LOCK:
            return True
    return False


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


def _addopts_override(args: list[str]) -> str | None:
    """`-o addopts=...` replaces the config's addopts outright."""
    for i, tok in enumerate(args):
        if tok in ("-o", "--override-ini") and i + 1 < len(args):
            if args[i + 1].lower().startswith("addopts="):
                return args[i + 1].split("=", 1)[1]
        for prefix in ("-oaddopts=", "--override-ini=addopts="):
            if tok.lower().startswith(prefix):
                return tok[len(prefix) :]
    return None


def _config_file(args: list[str]) -> str | None:
    for i, tok in enumerate(args):
        if tok in ("-c", "--config-file", "--inifile") and i + 1 < len(args):
            return args[i + 1]
        if tok.startswith(("--config-file=", "--inifile=")):
            return tok.split("=", 1)[1]
    return None


def targets(args: list[str]) -> list[str]:
    """The paths and node ids pytest is given: not options, their values, or redirections."""
    found: list[str] = []
    i = 0
    while i < len(args):
        tok = args[i]
        if _REDIRECT.match(tok):
            i += 2 if tok in _REDIRECT_WITH_TARGET else 1
            continue
        if tok == "--":
            found.extend(a for a in args[i + 1 :] if not _REDIRECT.match(a))
            break
        if tok.startswith("-"):
            i += 2 if tok in _VALUED else 1
            continue
        found.append(tok)
        i += 1
    return found


# --- the config pytest would read ------------------------------------------------------


def _configures_pytest(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        if path.name in ("pytest.ini", ".pytest.ini"):
            return True
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if path.name == "pyproject.toml":
        return "[tool.pytest.ini_options]" in text
    if path.name == "tox.ini":
        return re.search(r"^\[pytest\]", text, re.M) is not None
    if path.name == "setup.cfg":
        return re.search(r"^\[tool:pytest\]", text, re.M) is not None
    return False


def find_config(base: Path, paths: list[Path]) -> Path | None:
    """pytest's own search: the common ancestor of the targets that exist (else the working
    directory), then upward; the first file that configures pytest."""
    existing = [p.resolve() for p in paths if p.exists()]
    if existing:
        try:
            ancestor = Path(os.path.commonpath([str(p) for p in existing]))
        except ValueError:  # targets on different drives
            ancestor = base.resolve()
        if ancestor.is_file():
            ancestor = ancestor.parent
    else:
        ancestor = base.resolve()
    for directory in (ancestor, *ancestor.parents):
        for name in _INI_NAMES:
            if _configures_pytest(directory / name):
                return directory / name
    return None


def addopts(config: Path) -> str:
    try:
        if config.name == "pyproject.toml":
            data = tomllib.loads(config.read_text(encoding="utf-8"))
            options = data.get("tool", {}).get("pytest", {}).get("ini_options", {})
            value = options.get("addopts", "") if isinstance(options, dict) else ""
            return " ".join(value) if isinstance(value, list) else str(value)
        parser = ConfigParser(interpolation=None)
        parser.read(config, encoding="utf-8")
        section = "tool:pytest" if config.name == "setup.cfg" else "pytest"
        return parser.get(section, "addopts", fallback="")
    except Exception:  # noqa: BLE001 - an unreadable config sets nothing
        return ""


def test_files(paths: list[Path], limit: int) -> int:
    """How many test files the targets name, counting no further than ``limit + 1``."""
    count = 0
    for path in paths:
        text = str(path)
        if "::" in text or text.endswith(".py") or path.is_file():
            count += 1
        elif path.is_dir():
            for root, dirs, files in os.walk(path):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
                count += sum(
                    1 for f in files
                    if f.endswith(".py") and (f.startswith("test_") or f.endswith("_test.py"))
                )
                if count > limit:
                    return count
        else:
            count += 1  # not on disk: one unknown target, never a reason to refuse
        if count > limit:
            return count
    return count


def _expand(here: Path, raw: str, variables: dict[str, str]) -> list[Path]:
    node = raw.split("::", 1)[0]
    path = resolve(here, node, variables)
    if any(ch in node for ch in "*?["):
        matches = sorted(glob.glob(str(path)))
        if matches:
            return [Path(m) for m in matches]
    return [path]


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


def judge(command: str, shell: str, cwd: Path) -> tuple[str, str, str] | None:
    """``(why, statement, command word)`` for the first heavy pytest run, else None."""
    base = cwd
    variables: dict[str, str] = {}
    env_addopts = ""
    for segment in segments(command, shell):
        found = _ADDOPTS_SET.search(segment)
        if found:
            env_addopts = found.group(1) or found.group(2) or ""
        if shell == "powershell":
            assigned = _PS_ASSIGN.match(segment)
            if assigned:
                variables[assigned.group(1)] = local_path(assigned.group(2), variables)
        for stage in pipeline_stages(words(segment, shell)):
            for tok in stage:
                assigned = _ASSIGN.match(tok)
                if not assigned:
                    break
                variables[assigned.group(1)] = local_path(assigned.group(2), variables)
            tokens = command_words(stage)
            if not tokens:
                continue
            names = [command_name(t) for t in tokens]
            if names[0] == "export":
                for tok in tokens[1:]:
                    assigned = _ASSIGN.match(tok)
                    if assigned:
                        variables[assigned.group(1)] = local_path(assigned.group(2), variables)
                continue
            if names[0] in _CD:
                if len(tokens) > 1 and tokens[-1] not in ("-", "-Path", "-LiteralPath"):
                    base = resolve(base, tokens[-1], variables)
                continue
            if under_lock(tokens):
                continue
            args = pytest_args(tokens)
            if args is None or any(a in _NO_RUN for a in args):
                continue
            verdict = _heavy(tokens, names, args, base, variables, env_addopts)
            if verdict:
                return verdict, segment, tokens[0]
    return None


def _heavy(
    tokens: list[str],
    names: list[str],
    args: list[str],
    base: Path,
    variables: dict[str, str],
    env_addopts: str,
) -> str | None:
    here = base
    for i, tok in enumerate(tokens):
        if tok == "--directory" and i + 1 < len(tokens):
            here = resolve(base, tokens[i + 1], variables)
        elif tok.startswith("--directory="):
            here = resolve(base, tok.split("=", 1)[1], variables)
    if names[0] in _CONTAINERS or not suite_lock_declared(here):
        return None
    raw_targets = targets(args)
    paths = [p for raw in raw_targets for p in _expand(here, raw, variables)]
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
            named = _config_file(args)
            config = resolve(here, named, variables) if named else find_config(here, paths)
            workers = explicit_workers(addopts(config).split()) if config else None
            source = f"from addopts in {config.name}" if config else ""
    if not workers or workers <= 1:
        return None
    if paths and test_files(paths, MAX_NARROW_FILES) <= MAX_NARROW_FILES:
        return None
    scope = " ".join(raw_targets) if raw_targets else "the whole tree"
    return f"{workers} workers ({source}) over {scope[:120]}"


def _queued(statement: str, word: str) -> str:
    """The statement with `rails lock suite --` in front of its pytest command."""
    at = statement.find(word)
    if at < 0:
        return f"rails lock {LOCK} -- {statement.strip()}"
    return f"{statement[:at]}rails lock {LOCK} -- {statement[at:]}".strip()


def check(evt: Event):
    shell = evt.shell
    command = evt.command or ""
    if shell is None or "pytest" not in command:
        return None
    try:
        found = judge(command, shell, evt.cwd)
    except Exception:  # noqa: BLE001 - fail open: a hook bug never blocks a test run
        return None
    if found is None:
        return None
    why, statement, word = found
    queued = _queued(statement, word)
    if len(queued) > 300:
        queued = f"rails lock {LOCK} -- <this pytest command>"
    return Deny(
        f"rails: this pytest runs {why}: a heavy suite that no lock on this machine sees. "
        f"`rails check` runs suites one at a time (lock `{LOCK}`), and a suite started beside "
        "them is how four ran at once and Windows hit its commit limit (2026-10-18). Queue it: "
        f"`{queued}` (run it in the background; it waits for the suite that is running). "
        f"Or make it light: name up to {MAX_NARROW_FILES} test files, or add `-n 0`."
    )
