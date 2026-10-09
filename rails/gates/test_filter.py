"""Refuse a test run narrowed on the command line (design R2: `pytest --deselect` / `-k not`).

A failing test filtered out of the run turns a red into a green that nobody decided:
the filter lives in a shell command, not in the tree, so no reviewer sees it and the next
run does not remember it. Quarantine in the code instead, where it is reviewable and
dated: ``@pytest.mark.skip(reason="#<issue>: ...")`` or the repo's quarantine marker.

Refused, when the command runs pytest (``pytest``, ``python -m pytest``, ``uv run [opts]
pytest``, ``docker compose exec svc python -m pytest``): ``--deselect``, a ``-k`` expression
with ``not`` in it, the same through ``-o addopts=...``, and the same set in
``PYTEST_ADDOPTS`` - as a prefix, or in an earlier statement of the same command (``export``,
``$env:``, ``set``, ``Set-Item Env:``, ``[Environment]::SetEnvironmentVariable``).
Not refused: ``-k name`` (running one test), ``-m "not db"`` (a marker the repo's own lanes
select by) and ``--ignore`` (lanes split by path) - and the word pytest inside a commit
message or other quoted text. Override in the command, where a reviewer sees it:
``# deselect-ok: #<issue>``.
"""

from __future__ import annotations

import re

from rails.gates.destructive import command_name, commands
from rails.hookio import Deny, Event

NAME = "test_filter"

_OVERRIDE = re.compile(r"#\s*deselect-ok:\s*#?\d+")
_NOT = re.compile(r"\bnot\b")
_PYTEST = ("pytest", "py.test")
#: Commands that run another command after their own options: pytest may sit after them.
_RUNNERS = ("uv", "uvx", "poetry", "pdm", "hatch", "rye", "pipx", "py", "docker", "docker-compose", "podman",
            "kubectl", "nox", "tox", "env", "sudo", "time", "timeout", "nice", "coverage", "xvfb-run")
#: --deselect, or a -k whose expression (before the next option) has "not" in it.
_NARROW_TEXT = re.compile(r"--deselect\b|(?<![\w-])-k\W{0,3}[^-]{0,80}?\bnot\b")
_ADDOPTS_SET = re.compile(
    r"(?:PYTEST_ADDOPTS\s*=|Env:PYTEST_ADDOPTS['\"]?\s+(?:-Value\s+)?|['\"]PYTEST_ADDOPTS['\"]\s*,)\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)


def _is_pytest(tokens: list[str]) -> bool:
    names = [command_name(t) for t in tokens]
    if names[0] in _PYTEST:
        return True
    if names[0] not in _RUNNERS and not names[0].startswith("python"):
        return False
    return any(n in _PYTEST for n in names[1:]) or any(
        names[i] == "-m" and names[i + 1] in _PYTEST for i in range(len(names) - 1)
    )


def _narrows(tokens: list[str]) -> bool:
    for i, tok in enumerate(tokens):
        if tok == "--deselect" or tok.startswith("--deselect="):
            return True
        if tok == "-k" and i + 1 < len(tokens) and _NOT.search(tokens[i + 1]):
            return True
        if tok.startswith("-k") and len(tok) > 2 and _NOT.search(tok[2:]):
            return True
        if tok == "-o" and i + 1 < len(tokens) and tokens[i + 1].lower().startswith("addopts="):
            if _NARROW_TEXT.search(tokens[i + 1].split("=", 1)[1]):
                return True
        if tok.lower().startswith(("-oaddopts=", "--override-ini=addopts=")) and _NARROW_TEXT.search(tok):
            return True
    return False


def _addopts_narrow(segment: str) -> bool:
    m = _ADDOPTS_SET.search(segment)
    return bool(m and _NARROW_TEXT.search(m.group(1)))


def check(evt: Event):
    shell = evt.shell
    command = evt.command or ""
    if shell is None or "pytest" not in command or _OVERRIDE.search(command):
        return None
    try:
        parsed = commands(command, shell)
    except Exception:  # noqa: BLE001
        return None
    env_narrowed = False
    for segment, tokens in parsed:
        if _addopts_narrow(segment):
            env_narrowed = True
        if _is_pytest(tokens) and (env_narrowed or _narrows(tokens)):
            return Deny(
                "rails: this narrows the test run on the command line (`--deselect` / `-k ... not ...`, directly, "
                "through `-o addopts` or PYTEST_ADDOPTS), which turns a failure into a pass nobody decided and "
                "nobody can review. Quarantine the test in code with its issue "
                "(`@pytest.mark.skip(reason=\"#<issue>: ...\")`), or say why here: `# deselect-ok: #<issue>`."
            )
    return None
