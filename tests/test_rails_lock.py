"""`rails lock <name> -- <command...>`: a suite started by hand queues with every lane that
names the same lock, as the `heavy_pytest` gate tells an agent to run it."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RAILS = [sys.executable, str(ROOT / "bin" / "rails")]

# Another process holding lock "suite", as a `rails check` suite lane does: writes `held`
# once it has the lock, then holds it until `release` exists.
_HOLDER = """
import sys, time, pathlib
sys.path.insert(0, sys.argv[3])
from rails import store
held, release = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
with store.machine_lock("suite", {"leaf": "other-tree", "lane": "suite", "sha": "abc123"}, poll=0.02):
    held.write_text("1")
    deadline = time.monotonic() + 120
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
"""

# The command run under the lock: records what holds the lock while it runs, exits 3.
_COMMAND = """
import os, pathlib, sys
record = pathlib.Path(os.environ["RAILS_DATA"]) / "locks" / "suite.holder.json"
pathlib.Path(sys.argv[1]).write_text(record.read_text(encoding="utf-8"), encoding="utf-8")
sys.exit(3)
"""


@pytest.fixture
def holder(tmp_path):
    held, release = tmp_path / "held", tmp_path / "release"
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER, str(held), str(release), str(ROOT)])
    deadline = time.monotonic() + 20
    while not held.exists():
        assert proc.poll() is None, "holder exited before taking the lock"
        assert time.monotonic() < deadline, "holder never took the lock"
        time.sleep(0.02)
    yield release
    release.write_text("go")
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()


def _stderr_lines(proc: subprocess.Popen) -> list[str]:
    lines: list[str] = []

    def read() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            lines.append(line)

    threading.Thread(target=read, daemon=True).start()
    return lines


def _rails(*args: str, cwd: Path, **kwargs) -> subprocess.Popen:
    return subprocess.Popen(
        [*RAILS, *args],
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )


def test_a_second_heavy_suite_waits_for_the_first_then_runs(holder, tmp_path):
    marker = tmp_path / "ran"
    proc = _rails("lock", "suite", "--", sys.executable, "-c", _COMMAND, str(marker), cwd=tmp_path)
    lines = _stderr_lines(proc)
    deadline = time.monotonic() + 30
    while not any("wait" in line for line in lines):
        assert proc.poll() is None, f"rails lock exited without waiting: {lines}"
        assert time.monotonic() < deadline, f"no wait line: {lines}"
        time.sleep(0.05)
    wait_line = next(line for line in lines if "wait" in line)
    assert "lock 'suite' held by other-tree (suite at abc123)" in wait_line, wait_line
    time.sleep(0.5)  # well past the 1 s poll's first retry: still waiting, command not started
    assert proc.poll() is None
    assert not marker.exists(), "the command started while another process held the lock"

    holder.write_text("go")
    assert proc.wait(timeout=30) == 3, "rails lock must exit with its command's code"
    record = marker.read_text(encoding="utf-8")
    assert '"lane": "rails lock: ' in record and '"leaf": "' + tmp_path.name in record, record


def test_an_uncontended_lock_runs_at_once_and_passes_the_exit_code_through(tmp_path):
    proc = _rails("lock", "suite", sys.executable, "-c", "import sys; print('out'); sys.exit(0)", cwd=tmp_path)
    out, err = proc.communicate(timeout=30)
    assert proc.returncode == 0
    assert out.strip() == "out", "the command's stdout is its own"
    assert "wait" not in err


@pytest.mark.parametrize(
    "args",
    [
        ["lock"],
        ["lock", "suite"],
        ["lock", "suite", "--"],
        ["lock", "../suite", "--", "python", "-c", "pass"],
        ["lock", "suite", "--", "uv", "run", "python", "ci/rails.py", "check"],
        ["lock", "suite", "--", "rails", "check", "--lane", "suite"],
    ],
)
def test_refused_without_taking_the_lock(holder, tmp_path, args):
    """No command, a name that is not a lock, or `rails` itself (which takes its lanes' locks
    and would wait for its own parent): refused at once, even while the lock is held."""
    proc = _rails(*args, cwd=tmp_path)
    proc.communicate(timeout=20)
    assert proc.returncode == 2


@pytest.mark.skipif(os.name != "nt", reason="PowerShell 5.1 is Windows-only")
def test_powershell_passes_the_separator_through(tmp_path):
    """The gate's remedy is typed into PowerShell too; 5.1 hands `--` to a native command."""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"& '{sys.executable}' '{RAILS[1]}' lock suite -- '{sys.executable}' -c 'import sys; sys.exit(5)'; exit $LASTEXITCODE"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 5, done.stdout + done.stderr
