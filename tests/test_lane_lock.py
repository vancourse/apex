"""A lane's machine-wide lock: one holder at a time, a dead holder frees it, and the
wait stays out of the lane's timeout and seconds."""

from __future__ import annotations

import io
import subprocess
import sys
import time
from pathlib import Path

import pytest

from rails import check, lanes, receipts, store

ROOT = str(Path(__file__).resolve().parent.parent)

# Another process holding lock "t": writes `held` once it has the lock, then holds it
# until `release` exists or `hold_secs` pass. Mode "die" exits without releasing.
_HOLDER = """
import os, sys, time, pathlib
sys.path.insert(0, sys.argv[5])
from rails import store
held, release, hold_secs, mode = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), float(sys.argv[3]), sys.argv[4]
with store.machine_lock("t", {"leaf": "other-tree", "lane": "suite", "sha": "abc123"}, poll=0.02):
    held.write_text("1")
    if mode == "die":
        os._exit(0)
    deadline = time.monotonic() + hold_secs
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
"""


def _hold(tmp_path: Path, hold_secs: float, mode: str = "hold"):
    held, release = tmp_path / "held", tmp_path / "release"
    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER, str(held), str(release), str(hold_secs), mode, ROOT]
    )
    deadline = time.monotonic() + 20
    while not held.exists():
        assert proc.poll() is None or mode == "die", "holder exited before taking the lock"
        assert time.monotonic() < deadline, "holder never took the lock"
        time.sleep(0.02)
    return proc, release


def test_a_lane_lock_is_parsed_and_defaults_to_none():
    config = lanes.loads(
        '[[lane]]\nname = "suite"\nlock = "suite"\n[[lane]]\nname = "lint"\n'
    )
    assert config.lane("suite").lock == "suite"
    assert config.lane("lint").lock == ""


@pytest.mark.parametrize("name", ["../x", "a/b", "a b", "-x", "x" * 65])
def test_a_lock_name_that_is_not_a_plain_word_is_refused(name):
    with pytest.raises(ValueError, match="plain word"):
        lanes.loads(f'[[lane]]\nname = "suite"\nlock = "{name}"\n')
    with pytest.raises(ValueError, match="plain word"):
        with store.machine_lock(name, {}):
            pass


def test_a_second_holder_waits_for_the_first_and_learns_who_it_is(tmp_path):
    proc, release = _hold(tmp_path, hold_secs=60)
    notes: list[dict | None] = []

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


def test_a_holder_that_dies_without_releasing_frees_the_lock(tmp_path):
    proc, _ = _hold(tmp_path, hold_secs=60, mode="die")
    assert proc.wait(timeout=20) == 0
    notes: list[dict | None] = []
    with store.machine_lock("t", {"leaf": "mine"}, poll=0.02, on_wait=lambda h, w: notes.append(h)) as waited:
        pass
    assert notes == [] and waited < 1.0


def _lanes_with_lock(top: Path, py: str, lock: str) -> None:
    lock_line = f'lock = "{lock}"\n' if lock else ""
    (top / "lanes.toml").write_text(
        f"""
[settings]
base = "origin/main"
[[lane]]
name = "backend"
always = true
command = ["{py}", "-c", "print('ok')"]
{lock_line}""",
        encoding="utf-8",
    )


def test_check_waits_for_the_lane_lock_outside_the_lane_time(repo, commit, py, tmp_path):
    _lanes_with_lock(repo, py, "t")
    sha = commit(repo, "src/a.py", "x = 1\n")
    proc, _ = _hold(tmp_path, hold_secs=2.0)
    out = io.StringIO()
    assert check.check(repo, out=out) == 0, out.getvalue()
    proc.wait(timeout=20)
    text = out.getvalue()
    assert "wait  backend" in text and "held by other-tree (suite at abc123)" in text, text
    assert text.index("wait  backend") < text.index("run   backend")
    (row,) = receipts.read(store.find_repo(repo), "lane", sha=sha)
    assert row["lock"] == "t" and row["waited"] >= 1.0, row
    assert row["secs"] < row["waited"], row
    assert receipts.valid(row)


def test_a_lane_without_a_lock_takes_none(repo, commit, py):
    _lanes_with_lock(repo, py, "")
    sha = commit(repo, "src/a.py", "x = 1\n")
    assert check.check(repo, out=io.StringIO()) == 0
    assert not (store.data_root() / "locks").exists()
    (row,) = receipts.read(store.find_repo(repo), "lane", sha=sha)
    assert "lock" not in row and "waited" not in row
