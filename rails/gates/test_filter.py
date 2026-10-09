"""Refuse a test run narrowed on the command line (design R2: `pytest --deselect` / `-k not`).

A failing test filtered out of the run turns a red into a green that nobody decided:
the filter lives in a shell command, not in the tree, so no reviewer sees it and the next
run does not remember it. Quarantine in the code instead, where it is reviewable and
dated: ``@pytest.mark.skip(reason="#<issue>: ...")`` or the repo's quarantine marker.

Refused (agent commands, both shells): ``pytest ... --deselect ...`` and
``pytest ... -k "not ..."``. Selecting *in* (``-k name``) is how a session runs one test
and stays allowed. Override in the command, where a reviewer sees it: ``# deselect-ok: #<issue>``.
"""

from __future__ import annotations

import re

from rails.hookio import Deny, Event

NAME = "test_filter"

_PYTEST = re.compile(r"\bpytest\b")
_DESELECT = re.compile(r"--deselect\b")
_K_NOT = re.compile(r"""(?:^|\s)-k\s*(?:=\s*)?["']?\s*not\b|(?:^|\s)-k\s*["'][^"']*\band not\b""")
_OVERRIDE = re.compile(r"#\s*deselect-ok:\s*#?\d+")


def check(evt: Event):
    command = evt.command or ""
    if not command or not _PYTEST.search(command) or _OVERRIDE.search(command):
        return None
    if _DESELECT.search(command) or _K_NOT.search(command):
        return Deny(
            "rails: this narrows the test run on the command line (`--deselect` / `-k not`), which turns a "
            "failure into a pass nobody decided and nobody can review. Quarantine the test in code with its "
            "issue (`@pytest.mark.skip(reason=\"#<issue>: ...\")`), or say why here: `# deselect-ok: #<issue>`."
        )
    return None
