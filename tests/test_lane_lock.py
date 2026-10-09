"""A lane's machine-wide lock: one holder at a time, a dead holder frees it, the wait
stays out of the lane's timeout and seconds, and a worktree that moved while waiting is
not certified."""

from __future__ import annotations

import errno
import importlib
import io
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from rails import check, lanes, receipts, store

ROOT = str(Path(__file__).resolve().parent.parent)

# Another process holding lock "t": writes `held` once it has the lock, then holds it
# until `release` exists. Mode "die" exits without releasing.
_HOLDER = """
import os, sys, time, pathlib
sys.path.insert(0, sys.argv[4])
from rails import store
held, release, mode = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3]
with store.machine_lock("t", {"leaf": "other-tree", "lane": "suite", "sha": "abc123"}, poll=0.02):
    held.write_text("1")
    if mode == "die":
        os._exit(0)
    deadline = time.monotonic() + 120
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
"""


@pytest.fixture
def hold(tmp_path):
    """Start a holder of lock "t"; whatever the test does, it is released at teardown."""
    started: list[tuple[subprocess.Popen, Path]] = []

    def start(mode: str = "hold") -> tuple[subprocess.Popen, Path]:
        held, release = tmp_path / "held", tmp_path / "release"
        proc = subprocess.Popen(
            [sys.executable, "-c", _HOLDER, str(held), str(release), mode, ROOT]
        )
        started.append((proc, release))
        deadline = time.monotonic() + 20
        while not held.exists():
            assert proc.poll() is None or mode == "die", "holder exited before taking the lock"
            assert time.monotonic() < deadline, "holder never took the lock"
            time.sleep(0.02)
        return proc, release

    yield start
    for proc, release in started:
        release.write_text("go")
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()


def _when_waiting(out: io.StringIO, lane: str, then) -> threading.Thread:
    """Run ``then()`` once ``rails check`` has printed its wait line for ``lane``."""

    def watch() -> None:
        deadline = time.monotonic() + 60
        while f"wait  {lane}" not in out.getvalue() and time.monotonic() < deadline:
            time.sleep(0.02)
        then()

    thread = threading.Thread(target=watch, daemon=True)
    thread.start()
    return thread


def test_a_lane_lock_is_parsed_and_defaults_to_none():
    config = lanes.loads('[[lane]]\nname = "suite"\nlock = "suite"\n[[lane]]\nname = "lint"\n')
    assert config.lane("suite").lock == "suite"
    assert config.lane("lint").lock == ""


@pytest.mark.parametrize("name", ["../x", "a/b", "a b", "-x", "x" * 65, "nul", "CON.lane", "com1"])
def test_a_lock_name_that_is_not_a_plain_word_is_refused(name):
    with pytest.raises(ValueError, match="plain word"):
        lanes.loads(f'[[lane]]\nname = "suite"\nlock = "{name}"\n')
    with pytest.raises(ValueError, match="plain word"):
        with store.machine_lock(name, {}):
            pass


@pytest.mark.parametrize("value", ["true", "1", '["suite"]'])
def test_a_lock_that_is_not_a_string_is_refused(value):
    with pytest.raises(ValueError, match="must be a string"):
        lanes.loads(f'[[lane]]\nname = "suite"\nlock = {value}\n')


def test_only_contention_counts_as_held_when_strict(tmp_path, monkeypatch):
    """A lock error that is not contention must raise, or a waiter waits for nobody."""
    module_name, call = ("msvcrt", "locking") if os.name == "nt" else ("fcntl", "flock")
    module = importlib.import_module(module_name)
    contended = errno.EACCES if os.name == "nt" else errno.EWOULDBLOCK

    def failing(code: int):
        def raiser(*_args, **_kwargs):
            raise OSError(code, "planted")

        return raiser

    with open(tmp_path / "x.lock", "a+b") as handle:
        monkeypatch.setattr(module, call, failing(errno.EBADF))
        assert store._try_lock(handle) is False
        with pytest.raises(OSError):
            store._try_lock(handle, strict=True)
        monkeypatch.setattr(module, call, failing(contended))
        assert store._try_lock(handle, strict=True) is False


def test_a_second_holder_waits_for_the_first_and_learns_who_it_is(hold):
    proc, release = hold()
    notes: list[object] = []

    def on_wait(holder, waited):
        notes.append(holder)
        release.write_text("go")

    with store.machine_lock("t", {"leaf": "mine"}, poll=0.02, on_wait=on_wait) as waited:
        assert proc.wait(timeout=20) == 0
        record = store.read_json(store.data_root() / "locks" / "t.holder.json", None)
        assert record["leaf"] == "mine"
    assert waited > 0
    assert len(notes) == 1 and notes[0]["leaf"] == "other-tree", notes
    assert not (store.data_root() / "locks" / "t.holder.json").exists()


def test_a_holder_that_dies_without_releasing_frees_the_lock(hold):
    proc, _ = hold(mode="die")
    assert proc.wait(timeout=20) == 0
    notes: list[object] = []
    with store.machine_lock("t", {"leaf": "mine"}, poll=0.02, on_wait=lambda h, w: notes.append(h)) as waited:
        pass
    assert notes == [] and waited < 1.0


def test_an_unwritable_holder_record_does_not_cost_the_lock(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "held open by a waiter")

    monkeypatch.setattr(store, "write_json", refuse)
    with store.machine_lock("t", {"leaf": "mine"}, poll=0.02) as waited:
        assert waited < 1.0


def _write_lanes(top: Path, *blocks: str) -> None:
    (top / "lanes.toml").write_text(
        '\n[settings]\nbase = "origin/main"\n' + "".join(blocks), encoding="utf-8"
    )


def _lane(name: str, py: str, *, lock: str = "", code: str = "print('ok')", extra: str = "") -> str:
    lock_line = f'lock = "{lock}"\n' if lock else ""
    return f'[[lane]]\nname = "{name}"\nalways = true\ncommand = ["{py}", "-c", "{code}"]\n{lock_line}{extra}'


#: Exit 0 only on the edited content: certifying the commit for it would be a lie.
_GATE = "import pathlib, sys; sys.exit(0 if 'x = 2' in pathlib.Path('src/a.py').read_text() else 1)"


def test_check_waits_for_the_lane_lock_outside_the_lane_time(repo, commit, py, hold):
    _write_lanes(repo, _lane("backend", py, lock="t"))
    sha = commit(repo, "src/a.py", "x = 1\n")
    proc, release = hold()
    out = io.StringIO()

    def let_go() -> None:
        time.sleep(1.1)
        release.write_text("go")

    watcher = _when_waiting(out, "backend", let_go)
    assert check.check(repo, out=out) == 0, out.getvalue()
    watcher.join(timeout=20)
    proc.wait(timeout=20)
    text = out.getvalue()
    assert "held by other-tree (suite at abc123)" in text, text
    assert text.index("wait  backend") < text.index("run   backend")
    (row,) = receipts.read(store.find_repo(repo), "lane", sha=sha)
    assert row["lock"] == "t" and row["waited"] >= 1.0, row
    assert row["secs"] < row["waited"], row
    assert receipts.valid(row)


def test_an_edit_made_while_waiting_fails_the_check_and_leaves_no_marker(repo, commit, py, hold):
    _write_lanes(repo, _lane("backend", py, lock="t", code=_GATE))
    sha = commit(repo, "src/a.py", "x = 1\n")
    proc, release = hold()
    out = io.StringIO()

    def edit_then_let_go() -> None:
        (repo / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
        release.write_text("go")

    watcher = _when_waiting(out, "backend", edit_then_let_go)
    assert check.check(repo, out=out) == 1, out.getvalue()
    watcher.join(timeout=20)
    proc.wait(timeout=20)
    assert "tracked files changed since the check started" in out.getvalue()
    assert "run   backend" not in out.getvalue()
    rid = store.find_repo(repo)
    assert not receipts.has_marker(rid, sha, full=True)
    (row,) = receipts.read(rid, "lane", sha=sha)
    assert row["exit"] == 125 and row["lock"] == "t", row


def test_a_moved_worktree_fails_even_an_advisory_lane_and_runs_nothing_after(
    repo, commit, py, hold
):
    """Advisory or not, the check no longer describes its commit: no marker, no later lane."""
    _write_lanes(
        repo,
        _lane("slow", py, lock="t", extra='advisory_until = "2099-01-01"\n'),
        _lane("backend", py, code=_GATE),
    )
    sha = commit(repo, "src/a.py", "x = 1\n")
    proc, release = hold()
    out = io.StringIO()

    def edit_then_let_go() -> None:
        (repo / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
        release.write_text("go")

    watcher = _when_waiting(out, "slow", edit_then_let_go)
    assert check.check(repo, out=out) == 1, out.getvalue()
    watcher.join(timeout=20)
    proc.wait(timeout=20)
    text = out.getvalue()
    assert "run   backend" not in text and "skip  backend" in text, text
    rid = store.find_repo(repo)
    assert not receipts.has_marker(rid, sha, full=True)
    assert {r["lane"] for r in receipts.read(rid, "lane", sha=sha)} == {"slow"}


def test_a_commit_made_while_waiting_fails_the_check(repo, commit, py, hold):
    _write_lanes(repo, _lane("backend", py, lock="t"))
    sha = commit(repo, "src/a.py", "x = 1\n")
    proc, release = hold()
    out = io.StringIO()

    def commit_then_let_go() -> None:
        commit(repo, "src/b.py", "y = 1\n", "moved on")
        release.write_text("go")

    watcher = _when_waiting(out, "backend", commit_then_let_go)
    assert check.check(repo, out=out) == 1, out.getvalue()
    watcher.join(timeout=20)
    proc.wait(timeout=20)
    assert "HEAD moved since the check started" in out.getvalue()
    assert not receipts.has_marker(store.find_repo(repo), sha, full=True)


def test_a_lane_without_a_lock_takes_none(repo, commit, py):
    _write_lanes(repo, _lane("backend", py))
    sha = commit(repo, "src/a.py", "x = 1\n")
    assert check.check(repo, out=io.StringIO()) == 0
    assert not (store.data_root() / "locks").exists()
    (row,) = receipts.read(store.find_repo(repo), "lane", sha=sha)
    assert "lock" not in row and "waited" not in row
