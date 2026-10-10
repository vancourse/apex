"""The trunk runner: one full run per base tip, a culprit found by bisecting reruns, a
flake forgiven, a known failure not attributed twice, and the culprit's PR reverted.

Real git throughout (a bare `origin`, a clone, linear "merged" commits on main); only
the code host is a fake that records what the runner posts, opens and arms.
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from rails import lanes as lanes_mod, store, trunk

PY = sys.executable.replace("\\", "/")

# The trunk lane: counts its runs; `test_b` fails while src/b.py says boom, `test_c`
# while src/c.py does, and `test_flaky` fails one full run after the flaky switch is
# set.
SUITE = """
import pathlib, sys
count = pathlib.Path(sys.argv[1])
n = (int(count.read_text()) if count.exists() else 0) + 1
count.write_text(str(n))
root = pathlib.Path.cwd()
fails = []
for name in ("b", "c"):
    src = root / "src" / f"{name}.py"
    if src.exists() and "boom" in src.read_text():
        fails.append(f"tests/test_x.py::test_{name} - boom")
flag = pathlib.Path(sys.argv[2])
if flag.exists():  # fails one full run, then clears itself
    flag.unlink()
    fails.append("tests/test_x.py::test_flaky - flaky")
for line in fails:
    print("FAILED " + line)
sys.exit(1 if fails else 0)
"""

# The rerun: the same verdicts for the ids it is handed, except that a flake passes.
RERUN = """
import pathlib, sys
count = pathlib.Path(sys.argv[1])
count.write_text(str((int(count.read_text()) if count.exists() else 0) + 1))
root = pathlib.Path.cwd()
bad = []
for test_id in sys.argv[2:]:
    name = test_id.rsplit("_", 1)[-1]
    src = root / "src" / f"{name}.py"
    if name in ("b", "c") and src.exists() and "boom" in src.read_text():
        bad.append(test_id)
for test_id in bad:
    print("FAILED " + test_id + " - boom")
sys.exit(1 if bad else 0)
"""

TESTS = "def test_b(): pass\ndef test_c(): pass\ndef test_flaky(): pass\n"


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout.strip()


class FakeForge:
    def __init__(self) -> None:
        self.prs: dict[str, dict] = {}
        self.statuses: list[dict[str, str]] = []
        self.reverts: list[dict] = []
        self.armed: list[int] = []
        self.comments: list[tuple[int, str]] = []
        self.revert_fails = False

    def post_status(self, sha: str, context: str, state: str, description: str) -> None:
        self.statuses.append({"sha": sha, "context": context, "state": state, "description": description})

    def pr_for_commit(self, sha: str):
        return self.prs.get(sha)

    def revert(self, pr: dict, title: str, body: str):
        if self.revert_fails:
            return None
        made = {"number": 900 + pr["number"], "head_ref": f"revert-{pr['number']}", "head_sha": "f" * 40}
        self.reverts.append({"pr": pr["number"], "title": title, "body": body, **made})
        return made

    def arm(self, number: int) -> bool:
        self.armed.append(number)
        return True

    def comment(self, number: int, body: str) -> None:
        self.comments.append((number, body))

    def last(self) -> dict[str, str]:
        return self.statuses[-1]


@pytest.fixture
def site(tmp_path):
    bare = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    app = tmp_path / "app"
    _git(tmp_path, "clone", "-q", str(bare), str(app))
    for key, value in (
        ("user.email", "t@example.invalid"),
        ("user.name", "t"),
        ("core.autocrlf", "false"),
        ("core.hooksPath", str(tmp_path / "no-hooks")),
    ):
        _git(app, "config", key, value)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "suite.py").write_text(SUITE, encoding="utf-8")
    (scripts / "rerun.py").write_text(RERUN, encoding="utf-8")
    runs, reruns, flaky = tmp_path / "runs.txt", tmp_path / "reruns.txt", tmp_path / "flaky.on"
    s = lambda p: str(p).replace("\\", "/")  # noqa: E731

    def lanes(revert: str = "auto") -> str:
        return f"""
[settings]
base = "origin/main"
trunk_revert = "{revert}"
[[lane]]
name = "suite"
always = true
command = ["{PY}", "-c", "print('pre-merge')"]
trunk_command = ["{PY}", "{s(scripts / 'suite.py')}", "{s(runs)}", "{s(flaky)}"]
trunk_rerun = ["{PY}", "{s(scripts / 'rerun.py')}", "{s(reruns)}"]
"""

    (app / "lanes.toml").write_text(lanes(), encoding="utf-8")
    (app / "tests").mkdir()
    (app / "tests" / "test_x.py").write_text(TESTS, encoding="utf-8")
    (app / "src").mkdir()
    (app / "src" / "shared.py").write_text("value = 0\n", encoding="utf-8")
    _git(app, "add", "-A")
    _git(app, "commit", "-q", "-m", "base")
    _git(app, "push", "-q", "origin", "main")
    forge = FakeForge()
    numbers = {"next": 1}

    def merge(rel: str, text: str, title: str = "") -> str:
        """A squash-merged PR: one commit on main, pushed, with a PR the forge knows."""
        path = app / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        _git(app, "add", "-A")
        n = numbers["next"]
        numbers["next"] += 1
        _git(app, "commit", "-q", "-m", title or f"PR {n}")
        _git(app, "push", "-q", "origin", "main")
        sha = _git(app, "rev-parse", "HEAD")
        forge.prs[sha] = {"number": n, "node_id": f"PR_{n}", "head_ref": f"feature-{n}", "title": title or f"PR {n}"}
        return sha

    def count(path: Path) -> int:
        return int(path.read_text()) if path.exists() else 0

    class Site:
        pass

    site = Site()
    site.app, site.forge, site.merge, site.flaky, site.lanes = app, forge, merge, flaky, lanes
    site.runs = lambda: count(runs)  # type: ignore[attr-defined]
    site.reruns = lambda: count(reruns)  # type: ignore[attr-defined]
    site.checked = []  # type: ignore[attr-defined]
    site.repo = store.find_repo(app)  # type: ignore[attr-defined]
    return site


def _pass(site, *, check_ok: bool = True) -> tuple[int, str]:
    out = io.StringIO()

    def revert_check(made: dict) -> bool:
        site.checked.append(made["number"])
        return check_ok

    code = trunk.run_once(site.app, forge=site.forge, revert_check=revert_check, out=out)
    return code, out.getvalue()


def test_two_merges_take_one_run_and_an_unchanged_tip_takes_none(site):
    """a1."""
    assert _pass(site)[0] == 0
    site.merge("src/a.py", "a = 1\n")
    tip = site.merge("src/d.py", "d = 1\n")
    code, text = _pass(site)
    assert code == 0, text
    assert site.runs() == 2, "one run for the base, one for both merges"
    status = site.forge.last()
    assert status["sha"] == tip and status["state"] == "success", status
    assert status["context"] == "rails/trunk" and "trunk green" in status["description"]
    code, text = _pass(site)
    assert code == 0 and "already tested" in text
    assert site.runs() == 2


def test_the_middle_merge_is_bisected_reverted_and_armed(site):
    """a2: one full run, at most two bisect reruns (plus the tip's flake check)."""
    _pass(site)
    site.merge("src/a.py", "a = 1\n")
    bad = site.merge("src/b.py", "boom = 1\n")
    tip = site.merge("src/d.py", "d = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert site.runs() == 2
    assert site.reruns() <= 3, f"{site.reruns()} reruns: one at the tip, at most two to bisect"
    pr = site.forge.prs[bad]["number"]
    assert [r["pr"] for r in site.forge.reverts] == [pr]
    assert "(rails trunk)" in site.forge.reverts[0]["title"]
    assert site.checked == [900 + pr] and site.forge.armed == [900 + pr]
    assert any(n == pr and "tests/test_x.py::test_b" in body and f"#{900 + pr}" in body for n, body in site.forge.comments)
    status = site.forge.last()
    assert status["sha"] == tip and status["state"] == "failure"
    assert bad[:12] in status["description"] and f"#{pr}" in status["description"]


def test_a_failure_that_passes_alone_is_a_flake(site):
    """a3."""
    _pass(site)
    site.flaky.write_text("on", encoding="utf-8")
    tip = site.merge("src/a.py", "a = 1\n")
    code, text = _pass(site)
    assert code == 0, text
    status = site.forge.last()
    assert status["sha"] == tip and status["state"] == "success" and "flake" in status["description"]
    assert site.forge.reverts == []
    assert [row["id"] for row in trunk.read_state(site.repo)["flaky"]] == ["tests/test_x.py::test_flaky"]


def test_a_known_failure_is_not_attributed_twice(site):
    """a4."""
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    _pass(site)
    assert len(site.forge.reverts) == 1
    tip = site.merge("src/e.py", "e = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert len(site.forge.reverts) == 1, "the revert in flight is the answer; no second one"
    status = site.forge.last()
    assert status["sha"] == tip and status["state"] == "failure" and "still red" in status["description"]


def test_the_first_pass_ever_red_is_a_baseline(site):
    """a5."""
    site.merge("src/b.py", "boom = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert site.reruns() == 0 and site.forge.reverts == []
    assert "baseline" in site.forge.last()["description"]


def test_a_runner_revert_is_reported_and_never_reverted_again(site):
    """a6, first half."""
    _pass(site)
    bad = site.merge("src/b.py", "boom = 1\n", title="Revert #5: master red at abc (rails trunk)")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == [] and site.forge.armed == []
    pr = site.forge.prs[bad]["number"]
    assert any(n == pr and "not reverted again" in body for n, body in site.forge.comments)


def test_propose_opens_the_revert_unarmed(site):
    """a6, second half."""
    (site.app / "lanes.toml").write_text(site.lanes("propose"), encoding="utf-8")
    _git(site.app, "commit", "-q", "-am", "propose")
    _git(site.app, "push", "-q", "origin", "main")
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    code, _ = _pass(site)
    assert code == 1
    assert len(site.forge.reverts) == 1 and site.forge.armed == [] and site.checked == []


def test_a_red_revert_check_leaves_the_revert_unarmed(site):
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    _pass(site, check_ok=False)
    assert len(site.forge.reverts) == 1 and site.forge.armed == []
    assert any("not armed" in body for _, body in site.forge.comments)


def test_two_culprits_are_found_in_one_pass(site):
    _pass(site)
    site.merge("src/a.py", "a = 1\n")
    b = site.merge("src/b.py", "boom = 1\n")
    site.merge("src/d.py", "d = 1\n")
    c = site.merge("src/c.py", "boom = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert sorted(r["pr"] for r in site.forge.reverts) == sorted(
        [site.forge.prs[b]["number"], site.forge.prs[c]["number"]]
    )


def test_a_second_runner_leaves_the_tip_to_the_first(site):
    """a7."""
    site.merge("src/a.py", "a = 1\n")
    with store.machine_lock(trunk.lock_name(site.repo), {"leaf": "other"}):
        code, text = _pass(site)
    assert code == 0 and "already live" in text
    assert site.runs() == 0


def test_watch_runs_a_pass_when_the_tip_moves_and_stops_when_idle(site):
    site.merge("src/a.py", "a = 1\n")
    now = [0.0]
    out = io.StringIO()

    def sleep(_secs: float) -> None:
        now[0] += 60.0

    code = trunk.watch(
        site.app,
        forge=site.forge,
        revert_check=lambda made: True,
        out=out,
        poll=60.0,
        idle=300.0,
        clock=lambda: now[0],
        sleep=sleep,
    )
    assert code == 0 and "stopping" in out.getvalue(), out.getvalue()
    assert site.runs() == 1, "one pass for the moved tip, none while idle"


def test_ship_starts_a_runner_only_for_a_trunk_lane_and_only_once(site, monkeypatch):
    started: list[list[str]] = []

    class Popen:
        def __init__(self, argv, **_kwargs) -> None:
            started.append(argv)

    monkeypatch.setattr(trunk.subprocess, "Popen", Popen)
    assert trunk.start_background(site.app, out=io.StringIO()) is True
    assert started and started[0][-2:] == ["trunk", "watch"]
    with store.machine_lock(trunk.lock_name(site.repo), {"leaf": "w"}):
        assert trunk.start_background(site.app, out=io.StringIO()) is False
    (site.app / "lanes.toml").write_text(
        '[settings]\nbase = "origin/main"\n[[lane]]\nname = "suite"\ncommand = ["x"]\n',
        encoding="utf-8",
    )
    assert trunk.start_background(site.app, out=io.StringIO()) is False
    assert len(started) == 1


def test_bisect_finds_each_ids_first_failing_commit():
    commits = ["c0", "c1", "c2", "c3", "c4"]
    breaks = {"t1": 1, "t2": 3}
    probes: list[str] = []

    def probe(sha: str, wanted: list[str]) -> set[str]:
        probes.append(sha)
        index = commits.index(sha)
        return {t for t in wanted if index >= breaks[t]}

    found = trunk._bisect(commits, ["t1", "t2"], probe)
    assert found == [("c1", {"t1"}), ("c3", {"t2"})]
    assert len(probes) <= 5


def test_a_lane_file_declares_trunk_keys_and_reserves_the_name():
    config = lanes_mod.loads(
        '[settings]\ntrunk_revert = "auto"\n[[lane]]\nname = "suite"\ncommand = ["x"]\n'
        'timeout_min = 30\ntrunk_command = ["y"]\ntrunk_rerun = ["z"]\n'
    )
    lane = config.lane("suite")
    assert lane.trunk and lane.on_trunk().command == ["y"] and lane.on_trunk().timeout_min == 60
    assert config.trunk_revert == "auto"
    with pytest.raises(ValueError, match="reserved"):
        lanes_mod.loads('[[lane]]\nname = "trunk"\ncommand = ["x"]\n')
    with pytest.raises(ValueError, match="needs a trunk_command"):
        lanes_mod.loads('[[lane]]\nname = "s"\ncommand = ["x"]\ntrunk_rerun = ["z"]\n')
    with pytest.raises(ValueError, match="trunk_revert"):
        lanes_mod.loads('[settings]\ntrunk_revert = "yes"\n[[lane]]\nname = "s"\ncommand = ["x"]\n')
    with pytest.raises(ValueError, match="argv list"):
        lanes_mod.loads('[[lane]]\nname = "s"\ncommand = ["x"]\ntrunk_command = "y"\n')


def test_failed_ids_reads_pytest_short_summary():
    log = "\n".join(
        [
            "....F.E",
            "FAILED tests/a.py::test_one - AssertionError: x",
            "ERROR tests/b.py::test_two - psycopg.OperationalError",
            "FAILED tests/a.py::test_one - again",
        ]
    )
    assert trunk.failed_ids(log) == ["tests/a.py::test_one", "tests/b.py::test_two"]
