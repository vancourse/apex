"""The trunk runner: one full run per base tip, a culprit found by bisecting reruns, a
flake forgiven, a known or pre-existing failure not attributed, an unanswerable rerun
never turned into a verdict, and the culprit's PR reverted exactly once.

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

# The trunk lane. argv: runs-counter, flaky-switch, environment-switch.
# `test_b` / `test_c` fail while src/b.py / src/c.py say boom; `test_c` also fails while
# the environment switch exists (a failure from outside the repo); `test_p[b]` fails
# while src/p.py says boom; `test_flaky` fails one full run after its switch is set.
SUITE = """
import pathlib, sys
count = pathlib.Path(sys.argv[1])
n = (int(count.read_text()) if count.exists() else 0) + 1
count.write_text(str(n))
root = pathlib.Path.cwd()
fails = []
def boom(name):
    src = root / "src" / f"{name}.py"
    return src.exists() and "boom" in src.read_text()
if boom("b"):
    fails.append("tests/test_x.py::test_b - boom")
c_file = "tests/test_y.py" if (root / "tests" / "test_y.py").exists() else "tests/test_x.py"
if boom("c") or pathlib.Path(sys.argv[3]).exists():
    fails.append(c_file + "::test_c - boom")
if boom("p"):
    fails.append("tests/test_x.py::test_p[b] - boom")
if pathlib.Path(sys.argv[5]).exists():  # an outside cause breaks one case of test_p
    fails.append("tests/test_x.py::test_p[a] - outside")
flag = pathlib.Path(sys.argv[2])
if flag.exists():
    flag.unlink()
    fails.append("tests/test_x.py::test_flaky - flaky")
if count.with_name("load.txt").exists():  # load from a concurrent suite breaks test_c
    fails.append(c_file + "::test_c - load")
probe = count.with_name("lockprobe.txt")
if probe.exists():
    name, home = probe.read_text().split("|")
    sys.path.insert(0, home)
    from rails import store
    try:
        with store.machine_lock(name, {}, wait=False):
            seen = "full free"
    except store.LockBusy:
        seen = "full held"
    with open(probe.with_name("lockseen.txt"), "a") as fh:
        fh.write(seen + "\\n")
for line in fails:
    print("FAILED " + line)
# The teardown switch: each failing test also errors in teardown, as pytest reports it
# (a second summary line for the same id), and the closing tally counts both.
if fails and pathlib.Path(sys.argv[4]).exists():
    for line in fails:
        print("ERROR " + line.split(" - ")[0] + " - RuntimeError: teardown")
    print(f"==== {len(fails)} failed, {len(fails)} error in 0.10s ====")
sys.exit(1 if fails else 0)
"""

# The rerun. argv: reruns-counter, environment-switch, test_p[a]-switch, then the ids. A `[b]` id that
# does not exist at this commit (no src/p.py) makes the whole run fail like pytest's
# "not found": exit 4, nothing named. A flake passes.
RERUN = """
import pathlib, sys
count = pathlib.Path(sys.argv[1])
n = (int(count.read_text()) if count.exists() else 0) + 1
count.write_text(str(n))
root = pathlib.Path.cwd()
ids = sys.argv[4:]
# load.txt: the rerun numbers (this counter's values) during which load still breaks test_c.
load = count.with_name("load.txt")
loaded = load.exists() and str(n) in load.read_text().split(",")
probe = count.with_name("lockprobe.txt")
if probe.exists():
    name, home = probe.read_text().split("|")
    sys.path.insert(0, home)
    from rails import store
    try:
        with store.machine_lock(name, {}, wait=False):
            seen = "rerun free"
    except store.LockBusy:
        seen = "rerun held"
    with open(probe.with_name("lockseen.txt"), "a") as fh:
        fh.write(seen + "\\n")
def boom(name):
    src = root / "src" / f"{name}.py"
    return src.exists() and "boom" in src.read_text()
if any(i.endswith("[b]") for i in ids) and not (root / "src" / "p.py").exists():
    print("ERROR: not found: tests/test_x.py::test_p[b]")
    sys.exit(4)
bad = []
for test_id in ids:
    if test_id.endswith("::test_b") and boom("b"):
        bad.append(test_id)
    if test_id.endswith("::test_c") and (boom("c") or pathlib.Path(sys.argv[2]).exists() or loaded):
        bad.append(test_id)
    if test_id.endswith("::test_p[a]") and pathlib.Path(sys.argv[3]).exists():
        bad.append(test_id)
    if test_id.endswith("::test_p[b]") and boom("p"):
        bad.append(test_id)
for test_id in bad:
    print("FAILED " + test_id + " - boom")
sys.exit(1 if bad else 0)
"""

TESTS = "def test_b(): pass\ndef test_c(): pass\ndef test_p(): pass\ndef test_flaky(): pass\n"


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

    def post_status(self, sha: str, context: str, state: str, description: str) -> None:
        self.statuses.append({"sha": sha, "context": context, "state": state, "description": description})

    def pr_for_commit(self, sha: str):
        return self.prs.get(sha)

    def revert(self, pr: dict, title: str, body: str):
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
    runs, reruns = tmp_path / "runs.txt", tmp_path / "reruns.txt"
    flaky, env_broken = tmp_path / "flaky.on", tmp_path / "env.broken"
    teardown = tmp_path / "teardown.on"
    pa_broken = tmp_path / "pa.broken"
    s = lambda p: str(p).replace("\\", "/")  # noqa: E731

    def lanes(revert: str = "auto", rerun: str | None = "default", needs: str = "") -> str:
        rerun_line = {
            "default": f'trunk_rerun = ["{PY}", "{s(scripts / "rerun.py")}", "{s(reruns)}", "{s(env_broken)}", "{s(pa_broken)}"]',
            "exit4": f'trunk_rerun = ["{PY}", "-c", "import sys; sys.exit(4)"]',
            None: "",
        }[rerun]
        return f"""
[settings]
base = "origin/main"
trunk_revert = "{revert}"
[[lane]]
name = "suite"
always = true
command = ["{PY}", "-c", "print('pre-merge')"]
trunk_command = ["{PY}", "{s(scripts / 'suite.py')}", "{s(runs)}", "{s(flaky)}", "{s(env_broken)}", "{s(teardown)}", "{s(pa_broken)}"]
{rerun_line}
{needs}
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

    def move(src: str, dst: str) -> str:
        """A merged PR that only moves a file."""
        _git(app, "mv", src, dst)
        n = numbers["next"]
        numbers["next"] += 1
        _git(app, "commit", "-q", "-m", f"PR {n}: move {src}")
        _git(app, "push", "-q", "origin", "main")
        sha = _git(app, "rev-parse", "HEAD")
        forge.prs[sha] = {"number": n, "node_id": f"PR_{n}", "head_ref": f"feature-{n}", "title": f"PR {n}"}
        return sha

    def count(path: Path) -> int:
        return int(path.read_text()) if path.exists() else 0

    class Site:
        pass

    site = Site()
    site.app, site.forge, site.merge, site.lanes, site.move = app, forge, merge, lanes, move
    site.flaky, site.env_broken, site.teardown = flaky, env_broken, teardown
    site.pa_broken = pa_broken
    site.tmp = tmp_path  # type: ignore[attr-defined]
    site.runs = lambda: count(runs)  # type: ignore[attr-defined]
    site.reruns = lambda: count(reruns)  # type: ignore[attr-defined]
    site.checked = []  # type: ignore[attr-defined]
    site.repo = store.find_repo(app)  # type: ignore[attr-defined]
    return site


def _pass(site, *, check=None) -> tuple[int, str]:
    out = io.StringIO()

    def revert_check(made: dict) -> bool:
        site.checked.append(made["number"])
        return True if check is None else check(made)

    code = trunk.run_once(site.app, forge=site.forge, revert_check=revert_check, out=out)
    return code, out.getvalue()


def _relanes(site, **kwargs) -> None:
    (site.app / "lanes.toml").write_text(site.lanes(**kwargs), encoding="utf-8")
    _git(site.app, "commit", "-q", "-am", "lanes")
    _git(site.app, "push", "-q", "origin", "main")


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
    """a2: one full run; reruns are the tip's flake check, one at the last verdict, at
    most two bisect probes, and one probe confirming the culprit (#2668)."""
    _pass(site)
    site.merge("src/a.py", "a = 1\n")
    bad = site.merge("src/b.py", "boom = 1\n")
    tip = site.merge("src/d.py", "d = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert site.runs() == 2
    assert site.reruns() <= 5, f"{site.reruns()} reruns"
    pr = site.forge.prs[bad]["number"]
    assert [r["pr"] for r in site.forge.reverts] == [pr]
    assert "(rails trunk)" in site.forge.reverts[0]["title"]
    assert site.checked == [900 + pr] and site.forge.armed == [900 + pr]
    assert any(n == pr and "tests/test_x.py::test_b" in body and f"#{900 + pr}" in body for n, body in site.forge.comments)
    status = site.forge.last()
    assert status["sha"] == tip and status["state"] == "failure"
    assert bad[:12] in status["description"] and f"#{pr}" in status["description"]


def test_load_that_lasts_through_the_tip_rerun_blames_no_merge(site):
    """#2668: load from a concurrent suite fails test_c in the full run and in the tip's
    rerun, and is gone by the rerun at the last verdict. Every bisect probe then passes;
    the tip is probed again instead of assumed red, so the newest merge is not blamed and
    nothing is reverted."""
    _pass(site)
    site.merge("src/a.py", "a = 1\n")
    site.merge("src/d.py", "d = 1\n")
    first = site.reruns() + 1
    (site.tmp / "load.txt").write_text(str(first), encoding="utf-8")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == [] and site.forge.armed == []
    assert "unattributed" in site.forge.last()["description"]


def test_a_false_failure_in_one_bisect_probe_names_no_culprit(site):
    """#2668: load breaks test_c in the tip's rerun and in the first bisect probe (the
    middle of three merges), and nowhere else. The probe that would name the culprit is
    repeated before it counts, so the middle merge is not reverted."""
    _pass(site)
    for name in ("a", "d", "e"):
        site.merge(f"src/{name}.py", f"{name} = 1\n")
    first = site.reruns() + 1
    # Rerun `first` is the tip's; `first + 1` the last verdict's; `first + 2` the middle merge.
    (site.tmp / "load.txt").write_text(f"{first},{first + 2}", encoding="utf-8")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == [] and site.forge.armed == []
    assert "unattributed" in site.forge.last()["description"]


def test_the_attribution_reruns_hold_the_lanes_lock_and_the_revert_check_does_not(site):
    """#2668: the reruns that name a culprit run under the lane's machine lock, so a
    session's pre-merge suite cannot load them. The long full run does not take it (each
    session's suite would wait out the whole pass), and the revert's own check runs after
    it is released: that check takes the same lock."""
    _relanes(site, needs='lock = "trunklock"')
    _pass(site)
    home = str(Path(trunk.__file__).resolve().parents[1])
    (site.tmp / "lockprobe.txt").write_text(f"trunklock|{home}", encoding="utf-8")
    bad = site.merge("src/b.py", "boom = 1\n")
    at_check: list[str] = []

    def check(made: dict) -> bool:
        try:
            with store.machine_lock("trunklock", {}, wait=False):
                at_check.append("free")
        except store.LockBusy:
            at_check.append("held")
        return True

    code, text = _pass(site, check=check)
    assert code == 1, text
    seen = (site.tmp / "lockseen.txt").read_text(encoding="utf-8").split()
    lines = [" ".join(seen[i : i + 2]) for i in range(0, len(seen), 2)]
    assert "full free" in lines, lines
    assert "rerun held" in lines and "rerun free" not in lines, lines
    assert at_check == ["free"]
    assert [r["pr"] for r in site.forge.reverts] == [site.forge.prs[bad]["number"]]


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
    assert status["sha"] == tip and status["state"] == "failure" and "still-red" in status["description"]


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
    """a6, second half: the policy is read at the last verdict's commit."""
    _relanes(site, revert="propose")
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    code, _ = _pass(site)
    assert code == 1
    assert len(site.forge.reverts) == 1 and site.forge.armed == [] and site.checked == []


def test_a_culprit_cannot_switch_off_its_own_revert(site):
    _pass(site)
    (site.app / "lanes.toml").write_text(site.lanes(revert="off"), encoding="utf-8")
    site.merge("src/b.py", "boom = 1\n")  # one PR: breaks test_b and sets trunk_revert = off
    _pass(site)
    assert len(site.forge.reverts) == 1, "the policy at the last verdict was auto"


def test_a_red_revert_check_leaves_the_revert_unarmed(site):
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    _pass(site, check=lambda made: False)
    assert len(site.forge.reverts) == 1 and site.forge.armed == []
    assert any("not armed" in body for _, body in site.forge.comments)


def test_a_revert_is_recorded_before_its_check_and_never_opened_twice(site):
    """A check that raises (a failed fetch, a killed run) is a red check; the revert row
    is already saved, so a pass that attributes the same PR again opens nothing."""
    _pass(site)
    before = trunk.read_state(site.repo)["verdict"]
    site.merge("src/b.py", "boom = 1\n")

    def explode(made):
        raise trunk.GitError("fetch failed")

    code, text = _pass(site, check=explode)
    assert code == 1, text
    state = trunk.read_state(site.repo)
    assert [r["armed"] for r in state["reverts"]] == [False]
    assert site.forge.armed == []
    state["verdict"], state["last"] = before, {}  # as if the pass had died before recording
    trunk.write_state(site.repo, state)
    _pass(site)
    assert len(site.forge.reverts) == 1


def test_a_runner_killed_during_the_revert_check_leaves_the_revert_on_record(site):
    """A kill is not an exception the pass can catch: the revert row must already be on
    disk, or the next pass opens a second revert of the same PR."""
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")

    def killed(made):
        raise SystemExit(137)

    with pytest.raises(SystemExit):
        _pass(site, check=killed)
    pr = site.forge.reverts[0]["pr"]
    assert [r["pr"] for r in trunk.read_state(site.repo)["reverts"]] == [pr]
    assert site.forge.armed == [] and site.forge.comments == []
    _pass(site)  # the tip was never recorded, so this pass attributes the same PR again
    assert len(site.forge.reverts) == 1
    # ...and finishes what the killed pass did not reach: the check, the arm, the comment.
    assert site.checked == [900 + pr, 900 + pr] and site.forge.armed == [900 + pr]
    assert [n for n, _ in site.forge.comments] == [pr]


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


def test_an_id_a_probe_cannot_find_does_not_empty_the_probe(site):
    """pytest refuses a whole run for one id it cannot find; the probe asks again one id
    at a time, so the earlier culprit is still named (review of 001122d)."""
    _pass(site)
    b = site.merge("src/b.py", "boom = 1\n")
    site.merge("src/d.py", "d = 1\n")
    p = site.merge("src/p.py", "boom = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert sorted(r["pr"] for r in site.forge.reverts) == sorted(
        [site.forge.prs[b]["number"], site.forge.prs[p]["number"]]
    )


def test_a_failure_already_red_at_the_last_verdict_is_not_blamed(site):
    """Something outside the repo breaks test_c everywhere: it fails at the last verdict
    too, so no merge in the range is reverted (review of 001122d)."""
    _pass(site)
    site.merge("src/a.py", "a = 1\n")
    site.merge("src/d.py", "d = 1\n")
    site.env_broken.write_text("on", encoding="utf-8")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == []
    status = site.forge.last()
    assert status["state"] == "failure" and "unattributed" in status["description"]


def test_a_known_failure_whose_file_a_merge_moved_is_not_blamed_on_the_move(site):
    """test_c is red at the last verdict (an outside cause). A merge moves its file, so it
    fails under a new id that does not exist at the last verdict: the same test name is
    known, so it is reported, not blamed on the move (review of cb61211)."""
    _pass(site)
    site.env_broken.write_text("on", encoding="utf-8")
    site.merge("src/a.py", "a = 1\n")
    _pass(site)
    assert trunk.read_state(site.repo)["verdict"]["failed"] == {"suite": ["tests/test_x.py::test_c"]}
    site.move("tests/test_x.py", "tests/test_y.py")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == []
    assert "unattributed" in site.forge.last()["description"]


def test_a_new_failing_case_of_a_known_failing_test_is_still_blamed(site):
    """One case of a parametrized test stays red from an outside cause; a merge breaks a
    second case. The known case still fails at the tip, so it cannot be the new case's
    old copy: the merge is bisected and reverted (review of be89cc3)."""
    _pass(site)
    site.pa_broken.write_text("on", encoding="utf-8")
    site.merge("src/a.py", "a = 1\n")
    _pass(site)
    assert "tests/test_x.py::test_p[a]" in trunk.read_state(site.repo)["verdict"]["failed"]["suite"]
    bad = site.merge("src/p.py", "boom = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert [r["pr"] for r in site.forge.reverts] == [site.forge.prs[bad]["number"]]


def test_twins_are_files_that_no_longer_define_the_test_at_the_tip(site):
    """A file that still defines the name at the tip holds a test of its own; one gone at
    the tip, or one the test was split out of, is where a moved test came from."""
    (site.app / "tests" / "test_z.py").write_text(TESTS, encoding="utf-8")
    (site.app / "tests" / "test_w.py").write_text(TESTS, encoding="utf-8")
    _git(site.app, "add", "-A")
    _git(site.app, "commit", "-q", "-m", "more files define the same tests")
    base = _git(site.app, "rev-parse", "HEAD")
    _git(site.app, "mv", "tests/test_x.py", "tests/test_y.py")
    (site.app / "tests" / "test_w.py").write_text("def test_b(): pass\n", encoding="utf-8")
    _git(site.app, "add", "-A")
    _git(site.app, "commit", "-q", "-m", "move x to y, split test_c out of w")
    tip = _git(site.app, "rev-parse", "HEAD")
    twins = trunk._twins(site.app, base, tip, "tests/test_y.py::test_c")
    assert sorted(twins) == ["tests/test_w.py::test_c", "tests/test_x.py::test_c"]


def test_a_twin_search_git_cannot_answer_is_none(site):
    """A bad revision (exit 128) is not "no twins": the id is left unattributed."""
    tip = _git(site.app, "rev-parse", "HEAD")
    assert trunk._twins(site.app, "f" * 40, tip, "tests/test_y.py::test_c") is None


def test_a_test_split_out_of_a_file_that_stays_is_not_blamed_on_the_split(site):
    """Green at the last verdict; an outside cause breaks test_c, and in the same range a
    merge splits test_c out of tests/test_x.py, which stays. Its old copy fails at the
    last verdict too, so the split is not reverted (review of e547ff9)."""
    _pass(site)
    site.env_broken.write_text("on", encoding="utf-8")
    (site.app / "tests" / "test_x.py").write_text(TESTS.replace("def test_c(): pass\n", ""), encoding="utf-8")
    site.merge("tests/test_y.py", "def test_c(): pass\n")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == []
    assert "unattributed" in site.forge.last()["description"]


def test_only_a_known_failure_gone_from_the_tip_can_be_a_moved_tests_old_copy():
    known = {"suite": ["apps/a/tests/test_h.py::test_healthz", "tests/old.py::test_c"]}
    failing = {"suite": ["apps/a/tests/test_h.py::test_healthz", "tests/new.py::test_c"]}
    # test_healthz still fails under its own id: a new test_healthz elsewhere is new.
    assert trunk._moved_tails(known, failing) == {"test_c"}


def test_a_known_collection_error_is_not_every_files_old_copy():
    """pytest names a collection error by its file alone; its empty tail must not match
    a new collection error in another file (review of e547ff9)."""
    assert trunk._moved_tails({"suite": ["tests/test_old.py"]}, {"suite": ["tests/test_new.py"]}) == set()


def test_a_param_holding_a_double_colon_keeps_its_test_name():
    """jarvis parametrizes over IPv6 addresses (`[64:ff9b::a9fe:a9fe]`); the name comes
    from before the brackets, as pytest reads it (review of be89cc3)."""
    test_id = "runtime/x/tests/test_r.py::test_denied[64:ff9b::a9fe:a9fe]"
    assert trunk._leaf(test_id) == "test_denied"
    assert trunk._tail(test_id) == "test_denied[64:ff9b::a9fe:a9fe]"
    assert trunk._leaf("t.py::TestA::test_b[::1]") == "test_b"


def test_a_moved_known_failure_is_reported_even_when_its_old_file_cannot_be_found(site, monkeypatch):
    """The known name alone is enough: a twin search that finds nothing (a class-based id,
    a test renamed with its file) does not turn a known failure into the move's culprit."""
    _pass(site)
    site.env_broken.write_text("on", encoding="utf-8")
    site.merge("src/a.py", "a = 1\n")
    _pass(site)
    site.move("tests/test_x.py", "tests/test_y.py")
    monkeypatch.setattr(trunk, "_twins", lambda *a, **k: [])
    code, _ = _pass(site)
    assert code == 1 and site.forge.reverts == []


def test_a_test_moved_in_the_same_range_it_broke_in_is_asked_under_its_old_file(site):
    """Green at the last verdict; then an outside cause breaks test_c and a merge moves its
    file in the same range. At the last verdict the new id does not exist, but the same
    test under its old file fails there too, so the move is not blamed (review of cb61211)."""
    _pass(site)
    site.env_broken.write_text("on", encoding="utf-8")
    site.move("tests/test_x.py", "tests/test_y.py")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == []


def test_a_rerun_that_cannot_answer_is_red_not_a_flake(site):
    """A trunk_rerun that runs nothing (pytest exit 4) says nothing: the tip stays red,
    no flake is recorded, nothing is reverted (review of 001122d)."""
    _relanes(site, rerun="exit4")
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    code, text = _pass(site)
    assert code == 1, text
    assert site.forge.reverts == []
    status = site.forge.last()
    assert status["state"] == "failure" and "unattributed" in status["description"]
    assert not trunk.read_state(site.repo).get("flaky")


def test_a_lane_without_a_rerun_reports_its_culprit_and_never_reverts(site):
    _relanes(site, rerun=None)
    _pass(site)
    site.flaky.write_text("on", encoding="utf-8")
    bad = site.merge("src/a.py", "a = 1\n")
    code, _ = _pass(site)
    assert code == 1
    assert site.forge.reverts == [] and site.forge.armed == []
    assert any(n == site.forge.prs[bad]["number"] for n, _ in site.forge.comments)


def test_an_error_pass_posts_error_and_is_retried(site, monkeypatch):
    from rails import check

    site.merge("src/a.py", "a = 1\n")
    calls = {"n": 0}

    def missing(lane):
        calls["n"] += 1
        return "Postgres is not reachable" if calls["n"] == 1 else None

    monkeypatch.setattr(check, "missing_prerequisite", missing)
    code, _ = _pass(site)
    assert code == 1 and site.runs() == 0
    assert site.forge.last()["state"] == "error"
    code, text = _pass(site)  # `rails trunk run` retries an error at once
    assert code == 0 and site.runs() == 1, text


def test_a_lane_that_names_fewer_failures_than_it_counts_is_an_error(site, monkeypatch):
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    real = trunk.failure_tally
    monkeypatch.setattr(trunk, "failure_tally", lambda text: 2 if "FAILED" in text else real(text))
    code, _ = _pass(site)
    assert code == 1 and site.forge.reverts == []
    assert site.forge.last()["state"] == "error"


def test_a_second_runner_leaves_the_tip_to_the_first(site):
    """a7."""
    site.merge("src/a.py", "a = 1\n")
    with store.machine_lock(trunk.lock_name(site.repo), {"leaf": "other"}):
        code, text = _pass(site)
    assert code == 0 and "already live" in text
    assert site.runs() == 0


def _watch(site, *, idle: float = 300.0, until: float = 10_000.0) -> tuple[int, str]:
    now = [0.0]
    out = io.StringIO()

    def sleep(_secs: float) -> None:
        now[0] += 60.0
        assert now[0] < until, "watch did not stop"

    code = trunk.watch(
        site.app,
        forge=site.forge,
        revert_check=lambda made: True,
        out=out,
        poll=60.0,
        idle=idle,
        clock=lambda: now[0],
        sleep=sleep,
    )
    return code, out.getvalue()


def test_watch_runs_a_pass_when_the_tip_moves_and_stops_when_idle(site):
    site.merge("src/a.py", "a = 1\n")
    code, text = _watch(site)
    assert code == 0 and "stopping" in text, text
    assert site.runs() == 1, "one pass for the moved tip, none while idle"


def test_watch_stops_when_the_tip_has_no_trunk_lane(site):
    (site.app / "lanes.toml").write_text(
        '[settings]\nbase = "origin/main"\n[[lane]]\nname = "suite"\ncommand = ["x"]\n', encoding="utf-8"
    )
    _git(site.app, "commit", "-q", "-am", "no trunk lane")
    _git(site.app, "push", "-q", "origin", "main")
    code, text = _watch(site)
    assert code == 0 and "stopping" in text, text


def test_watch_stops_when_every_retry_of_an_error_is_spent(site, monkeypatch):
    from rails import check

    monkeypatch.setattr(check, "missing_prerequisite", lambda lane: "Postgres is not reachable")
    monkeypatch.setattr(trunk, "ERROR_RETRY_SECS", 0.0)
    site.merge("src/a.py", "a = 1\n")
    code, text = _watch(site)
    assert code == 0 and "stopping" in text, text
    assert trunk.read_state(site.repo)["last"]["attempts"] == trunk.ERROR_ATTEMPTS


def test_ship_starts_a_runner_only_for_a_trunk_lane_and_kicks_a_live_one(site, monkeypatch):
    started: list[list[str]] = []

    class Popen:
        def __init__(self, argv, **_kwargs) -> None:
            started.append(argv)

    monkeypatch.setattr(trunk, "_spawn", Popen)
    assert trunk.start_background(site.app, out=io.StringIO()) is True
    assert started and started[0][-2:] == ["trunk", "watch"]
    before = trunk._read_kick(site.repo)
    with store.machine_lock(trunk.lock_name(site.repo), {"leaf": "w"}):
        assert trunk.start_background(site.app, out=io.StringIO()) is False
    assert trunk._read_kick(site.repo) != before, "a live runner is told a merge is coming"
    no_trunk = '[settings]\nbase = "origin/main"\n[[lane]]\nname = "suite"\ncommand = ["x"]\n'
    # A stale working tree (the main checkout, merges behind) does not hide the base's keys.
    (site.app / "lanes.toml").write_text(no_trunk, encoding="utf-8")
    assert trunk._declares_trunk(site.app), "origin/main still declares the trunk lane"
    # Neither the worktree nor the base declares one: no runner.
    _git(site.app, "commit", "-q", "-am", "no trunk lane")
    _git(site.app, "push", "-q", "origin", "main")
    assert trunk.start_background(site.app, out=io.StringIO()) is False
    assert len(started) == 1


def test_a_branch_that_adds_the_trunk_lane_starts_the_runner_from_its_own_lanes_file(site, monkeypatch):
    """The PR that switches the runner on ships before the base has the keys."""
    started: list[list[str]] = []

    class Popen:
        def __init__(self, argv, **_kwargs) -> None:
            started.append(argv)

    monkeypatch.setattr(trunk, "_spawn", Popen)
    with_trunk = (site.app / "lanes.toml").read_text(encoding="utf-8")
    (site.app / "lanes.toml").write_text(
        '[settings]\nbase = "origin/main"\n[[lane]]\nname = "suite"\ncommand = ["x"]\n', encoding="utf-8"
    )
    _git(site.app, "commit", "-q", "-am", "base without a trunk lane")
    _git(site.app, "push", "-q", "origin", "main")
    _git(site.app, "checkout", "-q", "-b", "switch-on")
    (site.app / "lanes.toml").write_text(with_trunk, encoding="utf-8")
    _git(site.app, "commit", "-q", "-am", "the trunk lane")
    assert trunk.start_background(site.app, out=io.StringIO()) is True and len(started) == 1


def test_ids_that_fail_the_leak_check_are_not_posted(site, monkeypatch):
    from rails import leak

    (site.app / "rails").mkdir()
    (site.app / "rails" / "leak.toml").write_text("", encoding="utf-8")
    monkeypatch.setattr(leak, "check_lines", lambda *a, **k: leak.Result(leak.EXIT_COULD_NOT_LOOK, [], "no snapshot"))
    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    _pass(site)
    bodies = [body for _, body in site.forge.comments] + [r["body"] for r in site.forge.reverts]
    assert bodies and not any("test_b" in body for body in bodies)


def test_bisect_finds_each_ids_first_failing_commit():
    commits = ["c0", "c1", "c2", "c3", "c4"]
    breaks = {"t1": 1, "t2": 3}
    probes: list[str] = []

    def probe(sha: str, wanted: list[str]) -> trunk.Answer:
        probes.append(sha)
        index = commits.index(sha)
        failed = {t for t in wanted if index >= breaks[t]}
        return trunk.Answer(failed=failed, passed=set(wanted) - failed)

    found, lost = trunk._bisect(commits, ["t1", "t2"], probe)
    assert found == [("c1", {"t1"}), ("c3", {"t2"})] and lost == set()
    assert len(probes) <= 7  # the search's five, and one confirmation per culprit (#2668)
    assert probes[-2:] == ["c1", "c3"]


@pytest.mark.parametrize(
    ("breaks", "unsure_at", "located", "lost"),
    [
        # coop, round 2: t2's drop at c1 had set hi; t1 still breaks at c3.
        ({"t1": 3, "t2": 2}, {"c1": "t2"}, [("c3", {"t1"})], {"t2"}),
        # adversary, round 2: t1 dropped at c0; t2 breaks only at the tip.
        ({"t1": 1, "t2": 4}, {"c0": "t1"}, [("c4", {"t2"})], {"t1"}),
    ],
)
def test_bisect_keeps_searching_after_an_id_is_dropped(breaks, unsure_at, located, lost):
    commits = ["c0", "c1", "c2", "c3", "c4"]

    def probe(sha: str, wanted: list[str]) -> trunk.Answer:
        index = commits.index(sha)
        failed = {t for t in wanted if index >= breaks[t]}
        passed = set(wanted) - failed
        if sha in unsure_at:
            failed.discard(unsure_at[sha])
            passed.discard(unsure_at[sha])
        return trunk.Answer(failed=failed, passed=passed)

    assert trunk._bisect(commits, ["t1", "t2"], probe) == (located, lost)


def test_bisect_drops_an_id_a_probe_cannot_answer():
    commits = ["c0", "c1", "c2"]

    def probe(sha: str, wanted: list[str]) -> trunk.Answer:
        failed = {"t1"} & set(wanted) if sha == "c2" else set()
        return trunk.Answer(failed=failed, passed={t for t in wanted if t != "t2"} - failed)

    found, lost = trunk._bisect(commits, ["t1", "t2"], probe)
    assert lost == {"t2"} and found == [("c2", {"t1"})]


def test_bisect_probes_the_tip_before_blaming_it():
    """#2668: an id seen failing at the tip once (its rerun there) and passing at every
    probe after is not blamed on the newest commit: the confirmation probes the tip, and
    the id is lost."""
    commits = ["c0", "c1", "c2"]
    probes: list[str] = []

    def probe(sha: str, wanted: list[str]) -> trunk.Answer:
        probes.append(sha)
        return trunk.Answer(passed=set(wanted))

    assert trunk._bisect(commits, ["t1"], probe) == ([], {"t1"})
    assert "c2" in probes


def test_bisect_names_a_culprit_only_when_its_probe_repeats():
    """#2668: a failure that one probe saw and its repeat does not is no culprit."""
    commits = ["c0", "c1", "c2"]
    seen: list[str] = []

    def probe(sha: str, wanted: list[str]) -> trunk.Answer:
        seen.append(sha)
        once = sha == "c1" and seen.count("c1") == 1
        failed = set(wanted) if sha == "c2" or once else set()
        return trunk.Answer(failed=failed, passed=set(wanted) - failed)

    assert trunk._bisect(commits, ["t1"], probe) == ([], {"t1"})
    assert seen.count("c1") == 2


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


def test_failed_ids_reads_pytest_short_summary_including_spaced_params():
    log = "\n".join(
        [
            "....F.E",
            "FAILED tests/a.py::test_one - AssertionError: x",
            "ERROR tests/b.py::test_two - psycopg.OperationalError",
            "FAILED tests/a.py::test_one - again",
            "FAILED pkg/tests/t.py::test_id[mem ber] - AssertionError: a - b",
            "FAILED pkg/tests/t.py::test_bare[x y]",
            "FAILED pkg/tests/t.py::test_dash[a - b] - AssertionError",
            "==== 5 failed, 1 error, 9 passed in 2.01s ====",
        ]
    )
    assert trunk.failed_ids(log) == [
        "tests/a.py::test_one",
        "tests/b.py::test_two",
        "pkg/tests/t.py::test_id[mem ber]",
        "pkg/tests/t.py::test_bare[x y]",
        "pkg/tests/t.py::test_dash[a - b]",
    ]
    assert trunk.failure_tally(log) == 6
    assert trunk.failure_tally("FAILED x - 3 failed things in total\n") is None


def test_captured_log_records_are_not_test_ids():
    """pytest's default captured-log line starts with the level name padded to 8: an
    ERROR record reads `ERROR    name:file.py:N msg` (review of cb61211)."""
    with_banner = "\n".join(
        [
            "------ Captured log call ------",
            "ERROR    root:test_x.py:4 boom",
            "------ Captured stdout call ------",
            "ERROR app.retry - giving up",  # a test's own print: id-shaped, before the banner
            "=========== short test summary info ============",
            "FAILED tests/test_x.py::test_flaky - assert False",
            "1 failed, 3 passed in 0.05s",
        ]
    )
    without_banner = "ERROR    app.net:net.py:9 timed out\nFAILED tests/t.py::test_a - x\n"
    assert trunk.failed_ids(with_banner) == ["tests/test_x.py::test_flaky"]
    assert trunk.failed_ids(without_banner) == ["tests/t.py::test_a"]
    # A failing test whose captured output holds a nested pytest run: the real summary is
    # the LAST banner, printed after all captured output.
    nested = "\n".join(
        [
            "------ Captured stdout call ------",
            "=========== short test summary info ============",
            "FAILED inner/test_fake.py::test_inner - planted",
            "=========== short test summary info ============",
            "FAILED tests/t.py::test_outer - x",
        ]
    )
    assert trunk.failed_ids(nested) == ["tests/t.py::test_outer"]


def test_a_failure_and_its_teardown_error_are_one_id_and_two_reports(site, monkeypatch):
    """A test that fails and then errors in teardown is listed twice and tallied twice:
    that is a verdict, not an error pass (review of cb61211)."""
    log = "FAILED tests/t.py::test_a - x\nERROR tests/t.py::test_a - teardown\n=== 1 failed, 1 error in 0.5s ===\n"
    assert trunk.failed_ids(log) == ["tests/t.py::test_a"]
    assert trunk.failure_tally(log) == len(trunk._summary_entries(log)) == 2
    # The same through a pass: a culprit is found and reverted, the tip is not an error.
    _pass(site)
    site.teardown.write_text("on", encoding="utf-8")
    site.merge("src/b.py", "boom = 1\n")
    code, _ = _pass(site)
    assert code == 1 and site.forge.last()["state"] == "failure"
    assert len(site.forge.reverts) == 1


def test_a_rerun_that_skips_an_asked_id_has_no_answer_for_it(tmp_path):
    script = tmp_path / "skip.py"
    script.write_text("print('=== 1 passed, 1 skipped in 0.1s ===')\n", encoding="utf-8")
    lane = lanes_mod.Lane(name="s", command=["x"], trunk_command=["x"], trunk_rerun=[PY, str(script)])
    answer, nothing = trunk._run_ids(lane, tmp_path, ["t.py::a", "t.py::b"], tmp_path / "r.log")
    assert answer.unknown(["t.py::a", "t.py::b"]) == {"t.py::a", "t.py::b"} and not nothing


def test_a_lone_id_is_absent_only_when_pytest_says_it_found_nothing(tmp_path):
    usage = tmp_path / "usage.py"
    usage.write_text("import sys; print('ImportError while loading conftest'); sys.exit(4)\n", encoding="utf-8")
    missing = tmp_path / "missing.py"
    missing.write_text("import sys; print('ERROR: not found: t.py::a'); sys.exit(4)\n", encoding="utf-8")
    for script, absent in ((usage, False), (missing, True)):
        lane = lanes_mod.Lane(name="s", command=["x"], trunk_command=["x"], trunk_rerun=[PY, str(script)])
        _, nothing = trunk._run_ids(lane, tmp_path, ["t.py::a"], tmp_path / "r.log")
        assert nothing is absent, script.name


def test_a_probe_whose_prerequisite_died_has_no_answer(site, monkeypatch):
    from rails import check

    _pass(site)
    site.merge("src/b.py", "boom = 1\n")
    monkeypatch.setattr(check, "missing_prerequisite", lambda lane: None)
    real_ask = trunk._ask
    calls = {"n": 0}

    def ask(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:  # the tip's flake check sees Postgres go away
            monkeypatch.setattr(check, "missing_prerequisite", lambda lane: "Postgres is not reachable")
        return real_ask(*args, **kwargs)

    monkeypatch.setattr(trunk, "_ask", ask)
    code, _ = _pass(site)
    assert code == 1 and site.forge.reverts == []
    assert "unattributed" in site.forge.last()["description"]


def test_the_policy_is_the_default_when_the_verdict_has_no_lanes_file(site, tmp_path):
    base = _git(site.app, "rev-parse", "HEAD")
    assert trunk._policy(site.app, base) == "auto"
    (site.app / "rails").mkdir()
    _git(site.app, "mv", "lanes.toml", "rails/lanes.toml")
    _git(site.app, "commit", "-q", "-m", "move lanes")
    moved = _git(site.app, "rev-parse", "HEAD")
    assert trunk._policy(site.app, moved) == "auto", "found under rails/lanes.toml"
    _git(site.app, "rm", "-q", "rails/lanes.toml")
    _git(site.app, "commit", "-q", "-m", "drop lanes")
    assert trunk._policy(site.app, _git(site.app, "rev-parse", "HEAD")) == "propose"


def test_a_rootdir_relative_id_matches_the_id_that_was_asked():
    asked = ["toolbox-x/tests/test_p.py::test_a", "toolbox-y/tests/test_q.py::test_a"]
    assert trunk._match(asked, ["tests/test_p.py::test_a"]) == {"toolbox-x/tests/test_p.py::test_a"}
    assert trunk._match(asked + ["toolbox-z/tests/test_p.py::test_a"], ["tests/test_p.py::test_a"]) == set()


def test_github_revert_sends_the_mutation_and_reads_the_new_pr(monkeypatch, tmp_path):
    sent: list[tuple[str, dict]] = []

    def gh_api(top, path, *, method="GET", payload=None, timeout=60):
        sent.append((path, payload))
        return {"data": {"revertPullRequest": {"revertPullRequest": {"number": 7, "headRefName": "revert-5-x", "headRefOid": "a" * 40}}}}

    monkeypatch.setattr(trunk, "gh_api", gh_api)
    made = trunk.GitHub(tmp_path, "o/r").revert({"node_id": "PR_x"}, "t", "b")
    assert made == {"number": 7, "head_ref": "revert-5-x", "head_sha": "a" * 40}
    path, payload = sent[0]
    assert path == "graphql" and payload["variables"] == {"id": "PR_x", "title": "t", "body": "b"}
    assert "revertPullRequest(input:" in payload["query"]
    monkeypatch.setattr(trunk, "gh_api", lambda *a, **k: {"errors": [{"message": "conflict"}]})
    assert trunk.GitHub(tmp_path, "o/r").revert({"node_id": "PR_x"}, "t", "b") is None
