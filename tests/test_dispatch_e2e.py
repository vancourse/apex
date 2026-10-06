"""The hook the harness runs, driven the way the harness drives it.

``python3 hooks/rails_hook.py PreToolUse`` with the payload on stdin, as a
subprocess: the contract under test is the wire protocol and the process, not
the functions. A hook has no importers and emits no diff when it dies, so
"no output" cannot be read as health — every allow case here is paired with a
deny case through the same process.
"""

from __future__ import annotations

import importlib.util
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

from rails.dispatch import load_registry

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "rails_hook.py"


def _env() -> dict[str, str]:
    """The test's (tmp) store, no inherited override, and rows whose module is
    not written yet switched off — their 'missing' notice is a different test."""
    env = dict(os.environ)
    for name in list(env):
        upper = name.upper()
        if upper.startswith(("JARVIS_", "RAILS_")) and (
            upper.endswith("_OK") or upper.endswith("_PR_LOOKUP_FIXTURE")
        ):
            env.pop(name)
    missing = [
        row.name
        for row in load_registry()
        if importlib.util.find_spec(f"rails.gates.{row.module}") is None
    ]
    env["RAILS_GATES_OFF"] = ",".join(missing)
    assert env.get("RAILS_DATA"), "the root conftest must point RAILS_DATA at tmp"
    return env


def _run(stdin: str, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK), "PreToolUse"],
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
        cwd=str(ROOT),
    )


def _payload(command: str, tool: str, cwd: Path) -> str:
    return json.dumps(
        {
            "hook_event_name": "PreToolUse",
            "session_id": "e2e",
            "tool_name": tool,
            "tool_input": {"command": command, "description": "e2e"},
            "cwd": str(cwd),
        }
    )


@pytest.mark.parametrize("tool", ["Bash", "PowerShell"])
def test_git_stash_is_denied_over_the_wire(repo, tool):
    done = _run(_payload("git stash", tool, repo), _env())
    assert done.returncode == 0, done.stderr
    body = json.loads(done.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "refs/stash" in body["hookSpecificOutput"]["permissionDecisionReason"]


def test_git_status_produces_no_output(repo):
    done = _run(_payload("git status", "Bash", repo), _env())
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""


@pytest.mark.parametrize("stdin", ["", "not json at all", "[]", "null", "{"])
def test_malformed_stdin_is_silent_and_exits_zero(stdin):
    done = _run(stdin, _env())
    assert done.returncode == 0, done.stderr
    assert done.stdout == ""


def test_median_latency_of_a_bash_call(repo):
    env = _env()
    stdin = _payload("git status --short", "Bash", repo)
    _run(stdin, env)  # warm the filesystem cache once; not counted
    timings = []
    for _ in range(20):
        started = time.perf_counter()
        done = _run(stdin, env)
        timings.append((time.perf_counter() - started) * 1000)
        assert done.returncode == 0
    median = statistics.median(timings)
    print(
        f"\nrails_hook.py PreToolUse/Bash: median {median:.0f} ms over 20 calls "
        f"(min {min(timings):.0f}, max {max(timings):.0f})"
    )
    assert median < 400, f"median {median:.0f} ms"
