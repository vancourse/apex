"""lanes.toml selection, the `rails check` runner, markers and the CI verifier's arithmetic."""

from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from rails import check, lanes, receipts, store, verify


def test_glob_semantics():
    rx = lanes.glob_to_regex
    assert rx("apps/**").match("apps/purser/src/a.py")
    assert rx("apps/**/frontend/**").match("apps/purser/frontend/src/a.tsx")
    assert rx("apps/*/frontend/").match("apps/purser/frontend/src/a.tsx")
    assert not rx("apps/*/frontend/**").match("apps/purser/src/frontend.py")
    assert rx("**/*.md").match("README.md")
    assert rx("**/*.md").match("docs/x/y.md")
    assert not rx("*.md").match("docs/y.md")
    assert rx("./uv.lock").match("uv.lock")


CONFIG = """
[settings]
base = "origin/main"
all_lanes_on = ["lanes.toml"]
[[lane]]
name = "checks"
always = true
quick = true
command = ["true"]
[[lane]]
name = "backend"
paths = ["src/**", "*.py"]
paths_ignore = ["**/*.md"]
command = ["true"]
[[lane]]
name = "frontend"
paths = ["frontend/"]
command = ["true"]
"""


def test_select_reports_every_skip():
    cfg = lanes.loads(CONFIG)
    sel = lanes.select(cfg, ["src/app/x.py"])
    assert [l.name for l in sel.selected] == ["checks", "backend"]
    assert [(l.name, why) for l, why in sel.skipped] == [
        ("frontend", "no changed path matches its globs")
    ]
    assert [l.name for l in lanes.select(cfg, ["src/notes.md"]).selected] == ["checks"]
    assert [l.name for l in lanes.select(cfg, ["lanes.toml"]).selected] == [
        "checks",
        "backend",
        "frontend",
    ]
    assert [l.name for l in lanes.select(cfg, ["src/x.py"], quick=True).selected] == [
        "checks"
    ]


def test_command_must_be_argv():
    with pytest.raises(ValueError):
        lanes.loads('[[lane]]\nname = "x"\ncommand = "pytest -q"\n')


def _write_lanes(top: Path, py: str, fail_backend: bool = False) -> None:
    code = "import sys; sys.exit(3)" if fail_backend else "print('ok')"
    (top / "lanes.toml").write_text(
        f"""
[settings]
base = "origin/main"
[[lane]]
name = "checks"
always = true
quick = true
command = ["{py}", "-c", "print('lint ok')"]
[[lane]]
name = "backend"
paths = ["src/**"]
command = ["{py}", "-c", "{code}"]
""",
        encoding="utf-8",
    )


def test_check_green_writes_full_marker(repo, commit, py):
    _write_lanes(repo, py)
    sha = commit(repo, "src/a.py", "x = 1\n")
    out = io.StringIO()
    assert check.check(repo, out=out) == 0, out.getvalue()
    rid = store.find_repo(repo)
    assert receipts.has_marker(rid, sha, full=True)
    rows = receipts.read(rid, "lane", sha=sha)
    assert {r["lane"] for r in rows} == {"checks", "backend"}
    assert all(receipts.valid(r) for r in rows)


def test_planted_failing_lane_leaves_no_marker(repo, commit, py):
    _write_lanes(repo, py, fail_backend=True)
    sha = commit(repo, "src/a.py", "x = 1\n")
    out = io.StringIO()
    assert check.check(repo, out=out) == 1
    assert "FAIL  backend" in out.getvalue()
    rid = store.find_repo(repo)
    assert not receipts.has_marker(rid, sha, full=True)
    assert not receipts.has_marker(rid, sha, full=False)


def test_quick_marker_never_satisfies_full(repo, commit, py):
    _write_lanes(repo, py)
    sha = commit(repo, "src/a.py", "x = 1\n")
    assert check.check(repo, quick=True, out=io.StringIO()) == 0
    rid = store.find_repo(repo)
    assert receipts.has_marker(rid, sha, full=False)
    assert not receipts.has_marker(rid, sha, full=True)


def test_dirty_tree_refused(repo, commit, py):
    _write_lanes(repo, py)
    commit(repo, "src/a.py", "x = 1\n")
    (repo / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    out = io.StringIO()
    assert check.check(repo, out=out) == 2
    assert "uncommitted" in out.getvalue()


def test_single_lane_run_writes_no_marker(repo, commit, py):
    _write_lanes(repo, py)
    sha = commit(repo, "src/a.py", "x = 1\n")
    assert check.check(repo, only=["backend"], out=io.StringIO()) == 0
    assert not receipts.has_marker(store.find_repo(repo), sha, full=True)


def test_tampered_marker_is_not_a_marker(repo, commit, py):
    _write_lanes(repo, py)
    sha = commit(repo, "src/a.py", "x = 1\n")
    check.check(repo, out=io.StringIO())
    rid = store.find_repo(repo)
    path = receipts.marker_path(rid, sha, quick=False)
    body = json.loads(path.read_text())
    body["lanes"] = ["checks", "backend", "everything"]
    path.write_text(json.dumps(body))
    assert not receipts.has_marker(rid, sha, full=True)


def test_receipt_seal_detects_rewording(repo):
    rid = store.find_repo(repo)
    row = receipts.write(rid, "lane", lane="x", exit=1)
    assert receipts.valid(row)
    row["exit"] = 0
    assert not receipts.valid(row)


def test_forged_receipt_flagged_only_without_a_witness(repo, monkeypatch):
    rid = store.find_repo(repo)
    monkeypatch.setenv("CLAUDECODE", "1")
    receipts.write(rid, "lane", lane="x", exit=0)
    assert len(receipts.forged(rid, since=0)) == 1
    store.append_jsonl(
        rid.dir / "firings.jsonl",
        {
            "ts": int(__import__("time").time()) + 1,
            "leaf": rid.leaf,
            "gate": "receipt_writer",
            "verdict": "rails-cmd",
        },
    )
    assert receipts.forged(rid, since=0) == []


def test_missing_prerequisite_fails_the_lane_with_its_reason(monkeypatch):
    lane = lanes.Lane(name="db", needs=["postgres"])
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/x")
    assert "not a code failure" in check.missing_prerequisite(lane)


# --- a stopped lane stops everything it started --------------------------------


def _system32(exe: str) -> str:
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", exe)


def _alive(pid: int) -> bool:
    if os.name == "nt":
        listed = subprocess.run(
            [_system32("tasklist.exe"), "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True,
            text=True,
            errors="replace",
        ).stdout
        return f'"{pid}"' in listed
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:  # killed, but a zombie until its new parent reaps it
        stat = Path(f"/proc/{pid}/stat").read_text()
        return stat.rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return True


def _gone_within(pid: int, secs: float) -> bool:
    deadline = time.monotonic() + secs
    while _alive(pid):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.2)
    return True


def _reap(pid: int) -> None:
    """A failing test must not leave its planted sleeper behind."""
    if not _alive(pid):
        return
    if os.name == "nt":
        subprocess.run([_system32("taskkill.exe"), "/F", "/PID", str(pid)], capture_output=True)
    else:
        os.kill(pid, signal.SIGKILL)


def _planted_tree(tmp_path: Path, py: str, timeout_s: float):
    """A lane whose child starts a grandchild that sleeps 60 s, the way `uv run` starts pytest.

    On POSIX the grandchild leads its own session (as Playwright starts a browser), so a
    process-group kill would miss it; Windows ignores the flag. The pid lands by rename,
    so a reader never sees an empty file. The child's own pid goes to `child.pid` beside it."""
    pid_file = tmp_path / "grandchild.pid"
    child = (
        "import os, subprocess, sys, time; "
        f"open({str(tmp_path / 'child.pid')!r}, 'w').write(str(os.getpid())); "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], "
        "start_new_session=True); "
        f"open({str(pid_file)!r} + '.tmp', 'w').write(str(p.pid)); "
        f"os.replace({str(pid_file)!r} + '.tmp', {str(pid_file)!r}); "
        "time.sleep(60)"
    )
    lane = lanes.Lane(name="slow", command=[py, "-c", child], timeout_min=timeout_s / 60)
    return lane, pid_file


def test_a_timed_out_lane_stops_every_process_it_started(tmp_path, py):
    """The lane's child is a launcher (`uv run`). Killing only it left pytest and its workers
    running ~9 minutes past a 60-minute timeout, beside another session's suite (2026-10-09)."""
    assert _alive(os.getpid()), "the liveness probe cannot see a live process here"
    lane, pid_file = _planted_tree(tmp_path, py, timeout_s=6)
    log_path = tmp_path / "logs" / "slow.log"
    code, _ = check.run_lane(lane, tmp_path, log_path)
    assert pid_file.is_file(), "the planted child never started its grandchild"
    pid = int(pid_file.read_text())
    try:
        assert _gone_within(pid, 3), f"grandchild {pid} outlived the lane's timeout"
    finally:
        _reap(pid)
    log = log_path.read_text(encoding="utf-8")
    assert code == 124
    assert "RAILS: lane timed out after" in log
    assert ("taskkill /T /F exit" if os.name == "nt" else "of the lane's") in log, log


def test_a_tree_kill_that_fails_says_so_and_still_stops_the_lane(tmp_path, py, monkeypatch):
    """When taskkill or `ps` cannot do its part, the log says the tree may have survived."""
    if os.name == "nt":
        real_run = subprocess.run

        def taskkill_fails(argv, *args, **kwargs):
            if str(argv[0]).lower().endswith("taskkill.exe"):
                return subprocess.CompletedProcess(argv, 128, "ERROR: refused", "")
            return real_run(argv, *args, **kwargs)

        monkeypatch.setattr(check.subprocess, "run", taskkill_fails)
        expected = "taskkill /T /F exit 128: ERROR: refused"
    else:
        monkeypatch.setattr(check, "_descendants", lambda pid: None)
        expected = "could not read the process table (`ps`); stopped only the lane's own process"
    # A short sleep: with taskkill faked, a launcher's real python would outlive the lane.
    lane = lanes.Lane(
        name="slow", command=[py, "-c", "import time; time.sleep(10)"], timeout_min=2 / 60
    )
    log_path = tmp_path / "slow.log"
    assert check.run_lane(lane, tmp_path, log_path)[0] == 124
    log = log_path.read_text(encoding="utf-8")
    assert expected in log, log


@pytest.mark.skipif(os.name != "posix", reason="POSIX freezes the tree before the kill")
def test_a_lane_still_forking_at_the_timeout_leaves_nothing_behind(tmp_path, py):
    """A child started between the listing and the kill would be re-parented to init
    when its parent dies, and no parent-pid walk could find it again."""
    pids = tmp_path / "children"
    spawner = (
        "import subprocess, time\n"
        f"out = open({str(pids)!r}, 'a')\n"
        "while True:\n"
        "    out.write(f'{subprocess.Popen([\"sleep\", \"60\"]).pid}\\n'); out.flush()\n"
        "    time.sleep(0.005)\n"
    )
    lane = lanes.Lane(name="forks", command=[py, "-c", spawner], timeout_min=1.5 / 60)
    assert check.run_lane(lane, tmp_path, tmp_path / "forks.log")[0] == 124
    # Complete lines only: a pid cut short by the kill would name some other process.
    started = [int(line) for line in pids.read_text().split("\n")[:-1]]
    assert started, "the planted lane never started a child"
    try:
        deadline = time.monotonic() + 5  # SIGKILL lands asynchronously
        left = started
        while left and time.monotonic() < deadline:
            left = [pid for pid in left if _alive(pid)]
            time.sleep(0.2)
        assert not left, f"{len(left)} of {len(started)} children outlived the lane"
    finally:
        for pid in started:
            _reap(pid)


@pytest.mark.skipif(os.name != "posix", reason="POSIX freezes the tree before the kill")
def test_ctrl_c_during_the_freeze_leaves_nothing_stopped(tmp_path, py, monkeypatch):
    """A stopped process ignores everything but SIGKILL and SIGCONT; an interrupted
    freeze must not strand the lane frozen."""
    real = check._descendants
    walks: list[int] = []

    def interrupted_second_walk(pid):
        walks.append(pid)
        if len(walks) == 2:
            raise KeyboardInterrupt
        return real(pid)

    monkeypatch.setattr(check, "_descendants", interrupted_second_walk)
    lane, pid_file = _planted_tree(tmp_path, py, timeout_s=3)
    with pytest.raises(KeyboardInterrupt):
        check.run_lane(lane, tmp_path, tmp_path / "slow.log")
    assert len(walks) == 2 and pid_file.is_file()
    pid = int(pid_file.read_text())
    root = int((tmp_path / "child.pid").read_text())
    try:
        assert _gone_within(pid, 3), f"grandchild {pid} left frozen by an interrupted kill"
        assert _gone_within(root, 3), f"lane root {root} left frozen by an interrupted kill"
    finally:
        _reap(pid)
        _reap(root)


@pytest.mark.skipif(os.name != "posix", reason="process groups")
def test_a_lane_stays_in_rails_process_group(tmp_path, py):
    """Ctrl+C, a hangup and a kill aimed at the caller's group must still reach the lane
    itself; a lane in its own session is stopped only if rails lives to stop it."""
    out = tmp_path / "pgid"
    lane = lanes.Lane(
        name="pgid",
        command=[py, "-c", f"import os; open({str(out)!r}, 'w').write(str(os.getpgid(0)))"],
        timeout_min=1,
    )
    assert check.run_lane(lane, tmp_path, tmp_path / "pgid.log")[0] == 0
    assert int(out.read_text()) == os.getpgid(0)


# --- verifier arithmetic (CI side) --------------------------------------------


def _st(state, tree="abcdef123456789"):
    return {"state": state, "description": f"tree={tree[:12]} 10s rails-1.0.0 local"}


def test_verifier_requires_every_selected_lane():
    cfg = lanes.loads(CONFIG)
    needed = verify.required(cfg, ["src/x.py"])
    tree = "abcdef1234567890"
    ok = {"rails/checks": _st("success", tree), "rails/backend": _st("success", tree)}
    assert verify.evaluate(cfg, needed, ok, tree) == (
        [],
        ["rails/checks", "rails/backend"],
    )
    missing = {"rails/checks": _st("success", tree)}
    problems, _ = verify.evaluate(cfg, needed, missing, tree)
    assert problems == ["rails/backend: missing"]
    failed = {**ok, "rails/backend": _st("failure", tree)}
    assert verify.evaluate(cfg, needed, failed, tree)[0][0].startswith(
        "rails/backend: failure"
    )
    other_tree = {**ok, "rails/backend": _st("success", "999999999999")}
    assert "another tree" in verify.evaluate(cfg, needed, other_tree, tree)[0][0]


def test_verifier_treats_unlistable_diff_as_every_lane():
    cfg = lanes.loads(CONFIG)
    assert [l.name for l in verify.required(cfg, None)] == [
        "checks",
        "backend",
        "frontend",
    ]


def test_advisory_lane_reports_but_does_not_gate_until_its_date(repo, commit, py):
    import datetime as dt

    (repo / "lanes.toml").write_text(
        f"""
[settings]
base = "origin/main"
[[lane]]
name = "checks"
always = true
command = ["{py}", "-c", "print('ok')"]
[[lane]]
name = "image"
always = true
advisory_until = "2999-01-01"
command = ["{py}", "-c", "import sys; sys.exit(9)"]
""",
        encoding="utf-8",
    )
    sha = commit(repo, "src/a.py", "x = 1\n")
    out = io.StringIO()
    assert check.check(repo, out=out) == 0, out.getvalue()
    assert "ADVISORY image" in out.getvalue()
    assert receipts.has_marker(store.find_repo(repo), sha, full=True)
    cfg = lanes.load(repo / "lanes.toml")
    assert [l.name for l in verify.required(cfg, ["src/a.py"])] == ["checks"]
    after = dt.date(2999, 1, 2)
    assert [l.name for l in verify.required(cfg, ["src/a.py"], today=after)] == ["checks", "image"]


def test_an_advisory_lane_without_a_parseable_date_gates():
    lane = lanes.Lane(name="x", advisory_until="soon")
    assert lane.advisory() is False


def test_post_skips_an_advisory_lane_that_is_not_green(repo, commit, py, monkeypatch):
    (repo / "lanes.toml").write_text(
        f"""
[settings]
base = "origin/main"
[[lane]]
name = "checks"
always = true
command = ["{py}", "-c", "print('ok')"]
[[lane]]
name = "image"
always = true
advisory_until = "2999-01-01"
command = ["{py}", "-c", "import sys; sys.exit(9)"]
""",
        encoding="utf-8",
    )
    commit(repo, "src/a.py", "x = 1\n")
    check.check(repo, out=io.StringIO())
    posted = []
    monkeypatch.setattr(check, "origin_slug", lambda top: "acme/app")
    monkeypatch.setattr(check, "gh_api", lambda top, path, method="GET", payload=None: posted.append(payload["context"]))
    out = io.StringIO()
    assert check.post(repo, out=out, rerun=False) == 0
    assert posted == ["rails/checks"]
    assert "advisory and not green; not posted" in out.getvalue()
