"""Fixtures for the ported deny gates.

The root ``tests/conftest.py`` already isolates the store. This adds the one
thing a deny test must not inherit from the developer's shell: an exported
override. A developer who once ran ``export JARVIS_STASH_OK=1`` would otherwise
make every deny test pass vacuously on their machine only (the jarvis
originals dropped it from the inherited environment for the same reason).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from rails.hookio import Deny, Event


@pytest.fixture(autouse=True)
def no_inherited_overrides(monkeypatch):
    for name in list(os.environ):
        upper = name.upper()
        if upper.startswith(("JARVIS_", "RAILS_")) and (
            upper.endswith("_OK") or upper.endswith("_PR_LOOKUP_FIXTURE")
        ):
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def event():
    """Build a PreToolUse event: ``event("git stash")``, ``event(tool="Read", file_path=...)``."""

    def make(
        command: str | None = None,
        *,
        tool: str = "Bash",
        cwd: str | Path = ".",
        **tool_input,
    ) -> Event:
        body = dict(tool_input)
        if command is not None:
            body["command"] = command
        return Event(
            "PreToolUse",
            {
                "hook_event_name": "PreToolUse",
                "session_id": "test",
                "tool_name": tool,
                "tool_input": body,
                "cwd": str(cwd),
            },
        )

    return make


@pytest.fixture
def verdict(event):
    """``verdict(gate, command, tool=...)`` -> "deny" | "allow", plus the reason."""

    def run(gate, command=None, **kwargs) -> str:
        result = gate.check(event(command, **kwargs))
        if result is None:
            return "allow"
        assert isinstance(result, Deny), result
        return "deny"

    return run


@pytest.fixture
def reason(event):
    def run(gate, command=None, **kwargs) -> str:
        result = gate.check(event(command, **kwargs))
        assert isinstance(result, Deny), f"expected a deny for {command!r}"
        return result.reason

    return run
