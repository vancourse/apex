"""Refuse a test run narrowed on the command line (design R2: `pytest --deselect` / `-k not`).

A failing test filtered out of the run turns a red into a green that nobody decided:
the filter lives in a shell command, not in the tree, so no reviewer sees it and the next
run does not remember it. Quarantine in the code instead, where it is reviewable and
dated: ``@pytest.mark.skip(reason="#<issue>: ...")`` or the repo's quarantine marker.

Refused, in a statement whose command is pytest (``pytest``, ``python -m pytest``,
``uv run pytest``): ``--deselect``, and a ``-k`` expression with ``not`` anywhere in it -
also when set through ``PYTEST_ADDOPTS``. Not refused: ``-k name`` (running one test),
``-m "not db"`` (a marker the repo's own lanes select by) and ``--ignore`` (lanes split by
path) - and the word pytest inside a commit message or other quoted text.
Override in the command, where a reviewer sees it: ``# deselect-ok: #<issue>``.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event
from rails.shell import segments, words

NAME = "test_filter"

_OVERRIDE = re.compile(r"#\s*deselect-ok:\s*#?\d+")
_NOT = re.compile(r"\bnot\b")


def _shell(evt: Event) -> str:
    return "powershell" if evt.tool_name == "PowerShell" else "bash"


def _is_pytest(tokens: list[str]) -> bool:
    names = [t.replace("\\", "/").rsplit("/", 1)[-1].lower() for t in tokens[:6]]
    return any(n in ("pytest", "pytest.exe", "py.test") for n in names) or any(
        names[i] == "-m" and names[i + 1] == "pytest" for i in range(len(names) - 1)
    )


def _narrows(tokens: list[str]) -> bool:
    for i, tok in enumerate(tokens):
        if tok == "--deselect" or tok.startswith("--deselect="):
            return True
        if tok == "-k" and i + 1 < len(tokens) and _NOT.search(tokens[i + 1]):
            return True
        if tok.startswith("-k") and len(tok) > 2 and _NOT.search(tok[2:]):
            return True
        if tok.startswith("PYTEST_ADDOPTS=") and ("--deselect" in tok or re.search(r"-k\W*[^-]*\bnot\b", tok)):
            return True
    return False


def check(evt: Event):
    command = evt.command or ""
    if "pytest" not in command or _OVERRIDE.search(command):
        return None
    shell = _shell(evt)
    try:
        parts = segments(command, shell) or [command]
    except Exception:  # noqa: BLE001
        parts = [command]
    for part in parts:
        try:
            tokens = words(part, shell)
        except Exception:  # noqa: BLE001
            continue
        if _is_pytest(tokens) and _narrows(tokens):
            return Deny(
                "rails: this narrows the test run on the command line (`--deselect` / `-k ... not ...`), which turns "
                "a failure into a pass nobody decided and nobody can review. Quarantine the test in code with its "
                "issue (`@pytest.mark.skip(reason=\"#<issue>: ...\")`), or say why here: `# deselect-ok: #<issue>`."
            )
    return None
