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
    ],
)
def test_refused_without_taking_the_lock(holder, tmp_path, args):
    """No command, or a name that is not a lock: refused at once, even while it is held."""
    proc = _rails(*args, cwd=tmp_path)
    proc.communicate(timeout=20)
    assert proc.returncode == 2


# Takes the lock again from inside the command, as a `rails check` lane under it would.
_NESTED = """
import sys
sys.path.insert(0, sys.argv[1])
from rails import store
with store.machine_lock("suite", {"leaf": "nested"}, poll=0.02) as waited:
    print(f"re-entered after {waited}")
sys.exit(4)
"""


def _finish(proc: subprocess.Popen, timeout: float) -> tuple[str, str]:
    """``communicate``, but a run that hangs (a deadlock) is killed with its tree first."""
    try:
        return proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        from rails import check

        check._kill_tree(proc)
        pytest.fail(f"rails lock still running after {timeout} s: it waited for its own parent")


def test_a_lock_taken_again_under_rails_lock_re_enters_instead_of_waiting(tmp_path):
    """`rails check` (or another `rails lock`) under `rails lock suite` would wait forever for
    its own parent; it re-enters the lock its ancestor holds for it."""
    proc = _rails("lock", "suite", "--", sys.executable, "-c", _NESTED, str(ROOT), cwd=tmp_path)
    out, err = _finish(proc, 30)
    assert proc.returncode == 4, err
    assert "re-entered after 0.0" in out
    nested = _rails(
        "lock", "suite", "--", *RAILS, "lock", "suite", "--", sys.executable, "-c", "import sys; sys.exit(6)",
        cwd=tmp_path,
    )
    _finish(nested, 30)
    assert nested.returncode == 6


def test_a_lock_named_in_the_environment_is_not_re_entered_without_its_holder(holder, tmp_path):
    """RAILS_LOCKS_HELD re-enters only when the pid it names holds the lock: a stale or
    copied value queues like anything else."""
    marker = tmp_path / "ran"
    env = {**os.environ, "RAILS_LOCKS_HELD": f"suite:{os.getpid()}"}
    proc = _rails("lock", "suite", "--", sys.executable, "-c", _COMMAND, str(marker), cwd=tmp_path, env=env)
    lines = _stderr_lines(proc)
    deadline = time.monotonic() + 30
    while not any("wait" in line for line in lines):
        assert proc.poll() is None, f"rails lock ran without the lock: {lines}"
        assert time.monotonic() < deadline, f"no wait line: {lines}"
        time.sleep(0.05)
    assert not marker.exists()
    holder.write_text("go")
    assert proc.wait(timeout=30) == 3


def _alive(pid: int) -> bool:
    import ctypes

    kernel32 = ctypes.WinDLL("kernel32")
    handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    code = ctypes.c_ulong()
    try:
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


# The command: starts a worker of its own (as pytest starts xdist workers), records its
# pid, then runs on.
_SPAWNS = """
import pathlib, subprocess, sys, time
worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path(sys.argv[1]).write_text(str(worker.pid))
time.sleep(120)
"""


@pytest.mark.skipif(os.name != "nt", reason="the job object is Windows-only")
def test_a_killed_rails_lock_takes_its_command_tree_with_it(tmp_path):
    """The OS frees the lock when `rails lock` dies; the suite must not run on without it.
    TerminateProcess, as a harness stopping a background task does, is not Ctrl+C."""
    pidfile = tmp_path / "worker.pid"
    proc = _rails("lock", "suite", "--", sys.executable, "-c", _SPAWNS, str(pidfile), cwd=tmp_path)
    deadline = time.monotonic() + 30
    while not pidfile.exists() or not pidfile.read_text():
        assert proc.poll() is None, proc.communicate()
        assert time.monotonic() < deadline, "the command never started its worker"
        time.sleep(0.05)
    worker = int(pidfile.read_text())
    assert _alive(worker)
    proc.kill()
    proc.wait(timeout=20)
    deadline = time.monotonic() + 20
    while _alive(worker):
        assert time.monotonic() < deadline, "the worker ran on after rails lock was killed"
        time.sleep(0.1)
    from rails import store

    with store.machine_lock("suite", {"leaf": "after"}, wait=False):
        pass  # free again


@pytest.mark.skipif(os.name != "nt", reason="PowerShell 5.1 is Windows-only")
def test_the_remedy_runs_as_typed_into_powershell(tmp_path):
    """The gate's remedy is typed into PowerShell too: it runs there and its exit code comes
    back through `$LASTEXITCODE`."""
    done = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"& '{sys.executable}' '{RAILS[1]}' lock suite -- '{sys.executable}' -c 'import sys; sys.exit(5)'; exit $LASTEXITCODE"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 5, done.stdout + done.stderr
