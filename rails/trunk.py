"""`rails trunk`: the full suite runs once on the base branch's tip after merges, and a red
tip finds the commit that broke it and reverts it.

    rails trunk run       one pass: test the tip; on red, flake-check, bisect, act
    rails trunk watch     a pass whenever the tip moves; exits after 90 idle minutes
    rails trunk status    the last pass, its flakes and reverts, and whether a runner is live

A pass pools every merge since the last one. Each lane that declares ``trunk_command``
runs once on the tip, in a worktree kept under the rails data root and reused across
passes. Green: ``rails/trunk`` = success on the tip.

Red is attributed only on definite answers. Each failed test id the last verdict did
not already have is rerun alone at the tip (``trunk_rerun``):

* it passes: a flake (it fails in the full run and passes alone), recorded, never reverted;
* it fails again: it is rerun at the last verdict's commit. Failing there too, it was
  already broken (an environment change, a renamed lane): reported, not attributed.
  Passing there, it is bisected over the first-parent commits between, rerunning only
  those ids, and the first commit where it fails is its culprit. Not there at all, it is
  a new test or one a merge moved: a known failure with the same id after its file, gone
  from the tip, or the same test failing at the last verdict in a file gone from the
  tip, makes it the old one (reported); otherwise it is bisected;
* the rerun could not answer (pytest ran nothing, skipped it, named other ids, crashed,
  or the lane's prerequisite went away): the tip stays red and the id is reported, never
  attributed.

``trunk_revert`` (lanes file ``[settings]``, read at the last verdict's commit so a culprit
cannot switch off its own revert) decides what happens to a culprit's PR: ``auto`` opens
a revert PR through GitHub's ``revertPullRequest``, runs ``rails check`` and ``rails post``
on its head and arms auto-squash when both pass; ``propose`` opens it and leaves it
unarmed; ``off`` only comments. A revert is recorded the moment it opens, a PR already
reverted is never reverted again, and neither is a revert the runner opened. A lane with
no ``trunk_rerun`` cannot tell a flake, so its culprits are reported, never reverted.

A pass that could not reach a verdict (a missing prerequisite, a lane that failed without
naming every failure, a crash) posts ``error`` and is retried: at once by ``rails trunk
run``, by ``watch`` after a backoff and at most a few times per tip.

One runner per repository holds the machine lock ``trunk-<repo>``; a second finds it
held and leaves. The trunk lane does not take its ``lock`` (the pre-merge lane's), so a
pre-merge suite never queues behind a full run.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

from rails import VERSION, lanes as lanes_mod, store
from rails.gitutil import GitError, gh, gh_api, git, origin_slug, run

#: The status context a pass posts on the tip (a lane may not take this name).
CONTEXT = "trunk"
#: How often `watch` asks the remote for the tip, and how long it waits for a move.
POLL_SECS = 120.0
IDLE_SECS = 90 * 60.0
#: An error pass is retried by `watch` after this long, at most this many times per tip.
ERROR_RETRY_SECS = 30 * 60.0
ERROR_ATTEMPTS = 3
#: The title suffix that marks a revert the runner opened.
REVERT_MARK = "(rails trunk)"
#: pytest exit codes that mean "nothing ran", not "these ids failed".
_NOTHING_RAN = (4, 5)
#: pytest's short summary prefixes, and its closing tally (`2 failed, 1 error in 3s`).
_PREFIXES = ("FAILED ", "ERROR ")
_SUMMARY_BANNER = "short test summary info"
_NOT_FOUND = re.compile(r"ERROR: (?:not found|file or directory not found)|no tests ran|collected 0 items")
_PASSED = re.compile(r"(\d+) passed\b")
#: A group that gets no answer is re-asked one id at a time, at most this many.
_MAX_ALONE = 20
#: The same test name looked for under other files at the last verdict, at most this many.
_MAX_TWINS = 10
_TALLY_LINE = re.compile(
    r"^=*\s*\d+ (?:failed|passed|errors?|skipped|deselected|xfailed|xpassed|warnings?)\b.* in [\d.]+s"
)
_TALLY = re.compile(r"(\d+) (failed|errors?)\b")
#: Log directories kept under the trunk dir (one per tested tip).
_KEEP_LOG_DIRS = 20


# --- the code host -------------------------------------------------------------------


class Forge(Protocol):
    """What a pass needs from the code host; `GitHub` in use, a fake in tests."""

    def post_status(self, sha: str, context: str, state: str, description: str) -> None: ...

    def pr_for_commit(self, sha: str) -> dict[str, Any] | None:
        """{number, node_id, head_ref, title} of the merged PR that made `sha`, or None."""

    def revert(self, pr: dict[str, Any], title: str, body: str) -> dict[str, Any] | None:
        """Open a PR reverting `pr`: {number, head_ref, head_sha}, or None when it cannot."""

    def arm(self, number: int) -> bool: ...

    def comment(self, number: int, body: str) -> None: ...


_REVERT_MUTATION = """
mutation($id: ID!, $title: String!, $body: String!) {
  revertPullRequest(input: {pullRequestId: $id, title: $title, body: $body}) {
    revertPullRequest { number headRefName headRefOid }
  }
}
"""


class GitHub:
    def __init__(self, top: Path, slug: str) -> None:
        self.top, self.slug = top, slug

    def post_status(self, sha: str, context: str, state: str, description: str) -> None:
        gh_api(
            self.top,
            f"repos/{self.slug}/statuses/{sha}",
            method="POST",
            payload={"state": state, "context": context, "description": description[:140]},
        )

    def pr_for_commit(self, sha: str) -> dict[str, Any] | None:
        try:
            rows = gh_api(self.top, f"repos/{self.slug}/commits/{sha}/pulls") or []
        except (GitError, ValueError):
            return None
        for row in rows:
            if isinstance(row, dict) and row.get("merged_at"):
                return {
                    "number": int(row["number"]),
                    "node_id": str(row.get("node_id", "")),
                    "head_ref": str((row.get("head") or {}).get("ref", "")),
                    "title": str(row.get("title", "")),
                }
        return None

    def revert(self, pr: dict[str, Any], title: str, body: str) -> dict[str, Any] | None:
        try:
            data = gh_api(
                self.top,
                "graphql",
                method="POST",
                payload={
                    "query": _REVERT_MUTATION,
                    "variables": {"id": pr["node_id"], "title": title, "body": body},
                },
            )
        except (GitError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("errors"):
            return None
        made = ((data.get("data") or {}).get("revertPullRequest") or {}).get("revertPullRequest")
        if not made:
            return None
        return {
            "number": int(made["number"]),
            "head_ref": str(made["headRefName"]),
            "head_sha": str(made["headRefOid"]),
        }

    def arm(self, number: int) -> bool:
        try:
            gh(self.top, "pr", "merge", str(number), "--auto", "--squash")
        except GitError:
            return False
        return True

    def comment(self, number: int, body: str) -> None:
        try:
            gh_api(
                self.top,
                f"repos/{self.slug}/issues/{number}/comments",
                method="POST",
                payload={"body": body},
            )
        except GitError:
            pass


# --- state ---------------------------------------------------------------------------


def trunk_dir(repo: store.RepoId) -> Path:
    return store.data_root() / "trunk" / repo.key


def lock_name(repo: store.RepoId) -> str:
    return "trunk-" + hashlib.sha1(repo.key.encode("utf-8")).hexdigest()[:12]


def read_state(repo: store.RepoId) -> dict[str, Any]:
    raw = store.read_json(trunk_dir(repo) / "state.json", {})
    return raw if isinstance(raw, dict) else {}


def write_state(repo: store.RepoId, state: dict[str, Any]) -> None:
    store.write_json(trunk_dir(repo) / "state.json", state)


def _node_id(rest: str) -> str:
    """The node id at the start of a short-summary line's remainder. A parametrize id may
    hold spaces (`test_x[mem ber]`), so the id ends at the bracket that closes it."""
    rest = rest.rstrip()
    dash = rest.find(" - ")
    bracket = rest.find("[")
    if bracket != -1 and (dash == -1 or bracket < dash):
        close = rest.find("] - ", bracket)
        if close != -1:
            return rest[: close + 1]
        return rest
    return rest if dash == -1 else rest[:dash]


def _summary_entries(log_text: str) -> list[str]:
    """Every FAILED/ERROR node id in pytest's short summary, repeats kept: a test that
    fails and then errors in teardown is listed twice, and the tally counts it twice.
    When the log has the summary banner only what follows it is read, because captured
    log records (`ERROR    app:x.py:9 msg`) start with the same word; without one, a line
    whose id would start with whitespace is such a record and is skipped."""
    lines = log_text.splitlines()
    # The last banner: pytest prints the real summary after all captured output, which
    # may hold a nested run's banner.
    for index in range(len(lines) - 1, -1, -1):
        if _SUMMARY_BANNER in lines[index]:
            lines = lines[index + 1 :]
            break
    out: list[str] = []
    for line in lines:
        line = line.strip()
        for prefix in _PREFIXES:
            if line.startswith(prefix):
                rest = line[len(prefix) :]
                if rest and not rest[0].isspace():
                    node = _node_id(rest)
                    if node:
                        out.append(node)
    return out


def failed_ids(log_text: str) -> list[str]:
    """Test ids from pytest's short summary, in order, each once."""
    return list(dict.fromkeys(_summary_entries(log_text)))


def _tally_line(log_text: str) -> str | None:
    for line in reversed(log_text.splitlines()):
        line = line.strip()
        if _TALLY_LINE.match(line):
            return line
    return None


def failure_tally(log_text: str) -> int | None:
    """`failed + errors` from pytest's closing tally line, or None when there is none."""
    line = _tally_line(log_text)
    return None if line is None else sum(int(n) for n, _ in _TALLY.findall(line))


def _passed_tally(log_text: str) -> int | None:
    line = _tally_line(log_text)
    if line is None:
        return None
    found = _PASSED.search(line)
    return int(found.group(1)) if found else 0


def _match(asked: list[str], named: list[str]) -> set[str]:
    """The asked ids that `named` reports, allowing a rootdir-relative spelling
    (`tests/t.py::x` for `pkg/tests/t.py::x`) when exactly one asked id fits."""
    out: set[str] = set()
    for name in named:
        if name in asked:
            out.add(name)
            continue
        fits = [a for a in asked if a.endswith("/" + name)]
        if len(fits) == 1:
            out.add(fits[0])
    return out


def _leaf(test_id: str) -> str:
    """A test's own name, without its file, class or parameters."""
    # Parameters first: they may hold "::" (`test_x[64:ff9b::a9fe:a9fe]`), as pytest does.
    return test_id.split("[", 1)[0].rsplit("::", 1)[-1]


def _tail(test_id: str) -> str:
    """Everything after the file: class, name and parameters (`Class::test_x[a]`)."""
    return test_id.partition("::")[2]


# --- the worktree a pass runs in -----------------------------------------------------


def _checkout(top: Path, path: Path, sha: str) -> None:
    """Put the kept worktree at `sha`, creating it the first time. Ignored files
    (`.venv`, `node_modules`, caches) survive, so a pass does not re-sync from cold."""
    if not (path / ".git").exists():
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
        git(top, "worktree", "prune", check=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        run(["git", "worktree", "add", "--detach", str(path), sha], top, timeout=600)
        return
    run(["git", "checkout", "--detach", "--force", "--quiet", sha], path, timeout=600)
    run(["git", "clean", "-ffd", "-q"], path, timeout=600)


def _is_ancestor(top: Path, old: str, new: str) -> bool:
    done = subprocess.run(
        ["git", "merge-base", "--is-ancestor", old, new], cwd=str(top), capture_output=True
    )
    return done.returncode == 0


def _first_parent(top: Path, old: str, new: str) -> list[str]:
    out = git(top, "rev-list", "--first-parent", "--reverse", f"{old}..{new}")
    return [line for line in out.splitlines() if line.strip()]


def _present(tree: Path, test_id: str) -> bool:
    """Whether `test_id` can exist at the checked-out commit: its file is there and, for
    a `file::name` id, the name appears in it. An id added later fails nothing earlier."""
    file, _, rest = test_id.partition("::")
    target = tree / file
    if not target.is_file():
        return False
    if not rest:
        return True
    try:
        return _leaf(test_id) in target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _moved_tails(known: dict[str, list[str]], failing: dict[str, list[str]]) -> set[str]:
    """The ids (after their file) of known failures gone from the tip: not failing there
    under their own id. Only such a failure can be the old copy of a test a merge moved;
    one still failing at the tip is another test with the same name (`test_healthz` in
    two apps) and must not hide a new failure of it."""
    failing_now = {i for ids in failing.values() for i in ids}
    # A file-level id (a collection error) has an empty tail, which would match every
    # other file-level id; it can only be matched by its own file, so it is left out.
    return {_tail(i) for ids in known.values() for i in ids if "::" in i and i not in failing_now}


def _grep(top: Path, sha: str, pattern: str, paths: list[str]) -> list[str] | None:
    """The paths at `sha` whose text matches `pattern`. None when git could not answer:
    exit 1 is "no match", anything above it (a bad revision) is not an answer."""
    try:
        done = subprocess.run(
            ["git", "grep", "-l", "-E", pattern, sha, "--", *paths],
            cwd=str(top), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode > 1:
        return None
    return [line.split(":", 1)[1] for line in done.stdout.splitlines() if ":" in line]


def _twins(top: Path, sha: str, tip: str, test_id: str) -> list[str] | None:
    """The old copy of a moved test: the same name defined at `sha` in another `.py`
    file that no longer defines it at the tip (moved with its file, or split out of a
    file that stays), with the rest of the id kept. A file that still defines it at the
    tip holds a test of its own (`test_healthz` in two apps). None when git could not
    answer."""
    file, _, rest = test_id.partition("::")
    if not rest:
        return []
    pattern = rf"def {re.escape(_leaf(test_id))}\b"
    then = _grep(top, sha, pattern, ["*.py"])
    if then is None:
        return None
    candidates = [p for p in then if p != file]
    if not candidates:
        return []
    still = _grep(top, tip, pattern, candidates)
    if still is None:
        return None
    left = [p for p in candidates if p not in still]
    return [f"{path}::{rest}" for path in left][:_MAX_TWINS]


@dataclass
class Answer:
    """What a rerun said about the ids it was asked: each is failed, passed, absent (it
    cannot exist at that commit), or none of these (the rerun could not answer)."""

    failed: set[str] = field(default_factory=set)
    passed: set[str] = field(default_factory=set)
    absent: set[str] = field(default_factory=set)

    def unknown(self, ids: list[str]) -> set[str]:
        return set(ids) - self.failed - self.passed - self.absent


def _run_ids(lane: lanes_mod.Lane, tree: Path, ids: list[str], log: Path) -> tuple[Answer, bool]:
    """The rerun's answer, and whether pytest said it found nothing to run (exit 4 or 5
    with "not found" / "no tests ran": the ids do not exist here). A conftest or usage
    error also exits 4, says neither, and is no answer."""
    from rails.check import run_lane

    rerun = lanes_mod.Lane(
        name=f"{lane.name}-rerun",
        command=[*lane.trunk_rerun, *ids],
        env={**lane.env, "PY_COLORS": "0"},  # a coloured summary line parses as nothing
        timeout_min=lane.timeout_min,
    )
    code, _ = run_lane(rerun, tree, log)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    passed = _passed_tally(text)
    if code == 0:
        if passed is not None and passed < len(ids):
            return Answer(), False  # some asked ids did not run (skipped, deselected)
        return Answer(passed=set(ids)), False
    entries = _summary_entries(text)
    named = _match(ids, entries)
    tally = failure_tally(text)
    if named and (tally is None or tally <= len(entries)):
        if passed is not None and passed + len(named) < len(ids):
            return Answer(failed=named), False  # some asked ids did not run
        return Answer(failed=named, passed=set(ids) - named), False
    if named:
        return Answer(failed=named), False  # more failed than it named: the rest are unknown
    # Nothing ran, a crash, or ids in a form we cannot match: no answer.
    return Answer(), code in _NOTHING_RAN and bool(_NOT_FOUND.search(text))


def _ask(
    top: Path, tree: Path, sha: str, lane: lanes_mod.Lane, ids: list[str], log: Path, result: "Pass"
) -> Answer:
    """Rerun `ids` at `sha`. pytest refuses a whole run for one id it cannot find, so a
    group that gets no answer is asked again one id at a time (at most `_MAX_ALONE` of
    them); one id that pytest finds nothing for alone does not exist at this commit (a
    parametrize case added later) and is absent. A probe that failed while the lane's
    prerequisite went away (Postgres stopped mid-pass) is no answer at all."""
    from rails.check import missing_prerequisite

    _checkout(top, tree, sha)
    present = [i for i in ids if _present(tree, i)]
    answer = Answer(absent=set(ids) - set(present))
    if not present:
        return answer
    got, nothing = _run_ids(lane, tree, present, log)
    result.reruns += 1
    if len(present) == 1:
        if nothing:
            answer.absent.update(present)
    elif got.unknown(present):
        for index, one in enumerate(sorted(got.unknown(present))[:_MAX_ALONE]):
            alone, nothing = _run_ids(lane, tree, [one], log.with_name(f"{log.stem}.{index}{log.suffix}"))
            result.reruns += 1
            got.failed |= alone.failed
            got.passed |= alone.passed
            if nothing:
                answer.absent.add(one)
    if got.failed and missing_prerequisite(lane):
        return Answer(absent=answer.absent)
    answer.failed, answer.passed = got.failed, got.passed
    return answer


# --- one pass ------------------------------------------------------------------------


@dataclass
class Culprit:
    sha: str
    ids: list[str]
    revertable: bool = True
    pr: int | None = None
    revert: int | None = None
    armed: bool = False
    note: str = ""


@dataclass
class Pass:
    tip: str
    state: str = ""  # green | red | baseline | still-red | error | unchanged | no-trunk-lane
    failed: dict[str, list[str]] = field(default_factory=dict)
    flaky: list[str] = field(default_factory=list)
    unattributed: list[str] = field(default_factory=list)
    culprits: list[Culprit] = field(default_factory=list)
    lane_runs: int = 0
    reruns: int = 0
    note: str = ""


def _remote_branch(base: str) -> tuple[str, str]:
    remote, _, branch = base.partition("/")
    return (remote, branch) if branch else ("origin", remote)


def _description(tree_sha: str, state: str, note: str) -> str:
    parts = (f"trunk {state}", note, f"tree={tree_sha[:12]}", f"rails-{VERSION}")
    return " ".join(p for p in parts if p)


def _skip(state: dict[str, Any], tip: str, *, force: bool, now: float) -> str | None:
    """Why this tip needs no pass now, or None. An error pass is retried: always when
    forced (`rails trunk run`), else after a backoff and only a few times."""
    last = state.get("last") or {}
    if last.get("sha") != tip:
        return None
    if last.get("state") != "error":
        return "was already tested"
    if force:
        return None
    if int(last.get("attempts", 1)) >= ERROR_ATTEMPTS:
        return f"errored {last.get('attempts')} times; `rails trunk run` retries it"
    if now - float(last.get("at", 0)) < ERROR_RETRY_SECS:
        return "errored; it is retried after a backoff"
    return None


def _policy(top: Path, verdict_sha: str) -> str:
    """`trunk_revert` as the last verdict's commit had it, so a culprit that edits, moves
    or adds a lanes file cannot switch off its own revert. A lanes file that is not there
    or does not parse at that commit gives the default, never the tip's value."""
    from rails.check import LANES_FILES

    for rel in LANES_FILES:
        try:
            text = git(top, "show", f"{verdict_sha}:{rel}")
        except GitError:
            continue
        try:
            return lanes_mod.loads(text).trunk_revert
        except ValueError:
            break
    return lanes_mod.LaneConfig(lanes=[]).trunk_revert


def run_pass(
    top: Path,
    *,
    forge: Forge,
    revert_check: Callable[[dict[str, Any]], bool],
    force: bool = False,
    out=sys.stdout,
) -> Pass:
    """Test the base tip once, attribute what is newly red, act, record, post."""
    from rails.check import find_lanes_file

    repo = store.find_repo(top)
    assert repo is not None
    lanes_file = find_lanes_file(top)
    config = lanes_mod.load(lanes_file) if lanes_file else lanes_mod.LaneConfig(lanes=[])
    remote, branch = _remote_branch(config.base)
    git(top, "fetch", "--quiet", remote, branch, check=False)
    tip = git(top, "rev-parse", f"{remote}/{branch}")
    state = read_state(repo)
    result = Pass(tip=tip)
    why = _skip(state, tip, force=force, now=time.time())
    if why:
        result.state = "unchanged"
        print(f"rails trunk: {tip[:12]} {why}", file=out)
        return result
    try:
        _run(repo, top, tip, branch, state, result, forge, revert_check, out)
    except Exception as exc:  # noqa: BLE001 - recorded as an error pass, retried with backoff
        result.state, result.note = "error", f"the pass crashed ({type(exc).__name__}: {exc})"[:300]
        _record(repo, state, result, verdict=None)
        raise
    return result


@contextlib.contextmanager
def _attribution_locks(
    repo: store.RepoId, lanes: list[lanes_mod.Lane], tip: str, out
) -> Iterator[None]:
    """Hold the trunk lanes' machine locks (`lock = "<name>"`) while reruns decide who
    broke the tip. A session's pre-merge suite on the same lock would load them, and a
    load failure that outlives one rerun blamed a merge (#2668). The full run does not
    take them: every session's suite would wait out the whole pass. A revert's own
    `rails check` takes the same locks, so the caller releases them before it."""
    with contextlib.ExitStack() as stack:
        for name in sorted({lane.lock for lane in lanes if lane.lock}):

            def note(holder: object, waited: float, name: str = name) -> None:
                who = holder.get("leaf", "?") if isinstance(holder, dict) else "another check"
                print(
                    f"  wait  lock {name!r} held by {who}; waited {waited / 60:.0f} min",
                    file=out,
                    flush=True,
                )

            holder = {"repo": str(repo.main), "leaf": "rails trunk", "lane": name, "sha": tip}
            stack.enter_context(store.machine_lock(name, holder, on_wait=note))
        yield


def _run(
    repo: store.RepoId,
    top: Path,
    tip: str,
    branch: str,
    state: dict[str, Any],
    result: Pass,
    forge: Forge,
    revert_check: Callable[[dict[str, Any]], bool],
    out,
) -> None:
    from rails.check import find_lanes_file, missing_prerequisite, run_lane

    root = trunk_dir(repo)
    tree_path = root / "tree"
    log_dir = root / "logs" / tip[:12]
    _checkout(top, tree_path, tip)
    _prune_logs(root / "logs")
    tip_lanes = find_lanes_file(tree_path)
    if tip_lanes is None:
        result.state = "no-trunk-lane"
        _record(repo, state, result, verdict=None)
        print("rails trunk: the tip has no lanes file; nothing to run", file=out)
        return
    tip_config = lanes_mod.load(tip_lanes)
    trunk_lanes = [lane for lane in tip_config.lanes if lane.trunk]
    tree_sha = git(top, "rev-parse", f"{tip}^{{tree}}")
    if not trunk_lanes:
        result.state = "no-trunk-lane"
        _record(repo, state, result, verdict=None)
        print("rails trunk: no lane declares trunk_command; nothing to run", file=out)
        return

    print(f"rails trunk: testing {tip[:12]} ({branch})", file=out, flush=True)
    failing: dict[str, list[str]] = {}
    for lane in trunk_lanes:
        why = missing_prerequisite(lane)
        if why:
            result.state, result.note = "error", f"{lane.name}: prerequisite: {why}"
            break
        log = log_dir / f"{lane.name}.log"
        code, secs = run_lane(lane.on_trunk(), tree_path, log)
        result.lane_runs += 1
        print(f"  {'PASS' if code == 0 else 'FAIL'}  {lane.name:<14} {int(secs)}s  log: {log}", file=out)
        if code == 0:
            continue
        text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
        entries = _summary_entries(text)
        ids = list(dict.fromkeys(entries))
        tally = failure_tally(text)
        # The tally counts reports, as the summary lines do (a failure plus a teardown
        # error is two of each, for one id).
        if not ids or (tally is not None and tally > len(entries)):
            result.state = "error"
            result.note = (
                f"{lane.name} exited {code} without naming a failed test"
                if not ids
                else f"{lane.name}: {tally} failures, {len(ids)} named"
            )
            break
        failing[lane.name] = ids

    if result.state == "error":
        # No verdict: the tip is retried, and the last verdict stays the bisect base.
        _post(forge, tip_config, tip, tree_sha, "error", "error", result.note)
        _record(repo, state, result, verdict=None)
        return

    result.failed = failing
    verdict = state.get("verdict") if isinstance(state.get("verdict"), dict) else None
    if not failing:
        result.state = "green"
        _post(forge, tip_config, tip, tree_sha, "success", "green", f"{result.lane_runs} lane(s)")
        _record(repo, state, result, verdict={"sha": tip, "failed": {}})
        return

    if verdict is None or not _is_ancestor(top, str(verdict.get("sha", "")), tip):
        result.state = "baseline"
        count = sum(len(v) for v in failing.values())
        _post(forge, tip_config, tip, tree_sha, "failure", "baseline", f"red baseline: {count} failing")
        _record(repo, state, result, verdict={"sha": tip, "failed": failing})
        return

    base_sha = str(verdict["sha"])
    known = verdict.get("failed") or {}
    moved_tails = _moved_tails(known, failing)
    by_name = {lane.name: lane for lane in trunk_lanes}
    carried: dict[str, list[str]] = {}
    new: dict[str, list[str]] = {}
    for name, ids in failing.items():
        seen = set(known.get(name) or [])
        if [i for i in ids if i in seen]:
            carried[name] = [i for i in ids if i in seen]
        if [i for i in ids if i not in seen]:
            new[name] = [i for i in ids if i not in seen]

    # The reruns that decide who broke the tip run under the lanes' locks; released
    # before `_act`, whose revert check takes them too (#2668).
    with _attribution_locks(repo, trunk_lanes, tip, out):
        reproduced: dict[str, list[str]] = {}
        no_rerun: dict[str, list[str]] = {}
        for name, ids in new.items():
            lane = by_name[name]
            if not lane.trunk_rerun:
                no_rerun[name] = ids
                continue
            answer = _ask(top, tree_path, tip, lane, ids, log_dir / f"{name}.rerun.log", result)
            result.flaky.extend(i for i in ids if i in answer.passed)
            result.unattributed.extend(i for i in ids if i not in answer.passed and i not in answer.failed)
            if answer.failed:
                reproduced[name] = [i for i in ids if i in answer.failed]
        if result.flaky:
            _remember_flakes(state, tip, result.flaky)

        commits = _first_parent(top, base_sha, tip)
        found: dict[str, list[str]] = {}
        unrevertable: set[str] = set()
        for name, ids in no_rerun.items():
            # Without a rerun there is no flake check and no bisect: one merge is named,
            # several are left to a person, and neither is reverted.
            if len(commits) == 1:
                found.setdefault(commits[0], []).extend(ids)
                unrevertable.add(commits[0])
            else:
                result.unattributed.extend(ids)
        for name, ids in reproduced.items():
            lane = by_name[name]
            at_base = _ask(top, tree_path, base_sha, lane, ids, log_dir / f"{name}.base.log", result)
            # Failing at the last verdict too (an environment change, a renamed lane), or no
            # answer there: not this range's to blame.
            result.unattributed.extend(i for i in ids if i in at_base.failed or i in at_base.unknown(ids))
            bisectable = [i for i in ids if i in at_base.passed]
            for index, test_id in enumerate(sorted(at_base.absent & set(ids))):
                # Absent at the last verdict: a new test, or an old one a merge moved. A known
                # failure with the same class, name and parameters that is gone from the tip,
                # or the same test in a file that no longer defines it at the tip failing (or
                # unanswerable) at the last verdict, makes it the old one: reported, not
                # blamed on the move.
                if _tail(test_id) in moved_tails:
                    result.unattributed.append(test_id)
                    continue
                twins = _twins(top, base_sha, tip, test_id)
                if twins is None:
                    result.unattributed.append(test_id)
                    continue
                if twins:
                    log = log_dir / f"{name}.twins-{index}.log"
                    seen = _ask(top, tree_path, base_sha, lane, twins, log, result)
                    if seen.failed or seen.unknown(twins):
                        result.unattributed.append(test_id)
                        continue
                bisectable.append(test_id)
            if not bisectable:
                continue

            def probe(sha: str, wanted: list[str], lane=lane, name=name) -> Answer:
                return _ask(top, tree_path, sha, lane, wanted, log_dir / f"{name}.bisect-{sha[:12]}.log", result)

            located, lost = _bisect(commits, bisectable, probe)
            result.unattributed.extend(sorted(lost))
            for sha, ids_here in located:
                found.setdefault(sha, []).extend(sorted(ids_here))

    for sha in commits:
        if sha in found:
            result.culprits.append(Culprit(sha=sha, ids=found[sha], revertable=sha not in unrevertable))
    mode = _policy(top, base_sha)
    for culprit in result.culprits:
        _act(repo, top, state, mode, forge, culprit, tip, revert_check, out)

    confirmed = {
        name: sorted(set(ids) - set(result.flaky)) for name, ids in new.items() if set(ids) - set(result.flaky)
    }
    still_failing = {
        name: sorted(set(carried.get(name, [])) | set(confirmed.get(name, [])))
        for name in set(carried) | set(confirmed)
    }
    words = []
    if result.culprits:
        words.append(
            "culprit "
            + ", ".join(
                f"{c.sha[:12]}" + (f" #{c.pr}" if c.pr else "") + (f" -> #{c.revert}" if c.revert else "")
                for c in result.culprits
            )
        )
    if result.unattributed:
        words.append(f"{len(result.unattributed)} unattributed")
    if carried:
        words.append(f"{sum(len(v) for v in carried.values())} known")
    if result.flaky:
        words.append(f"{len(result.flaky)} flake(s)")
    result.note = "; ".join(words)
    if not still_failing:
        result.state = "green"
        _post(forge, tip_config, tip, tree_sha, "success", "green", result.note)
    else:
        result.state = "red" if (confirmed or result.culprits) else "still-red"
        _post(forge, tip_config, tip, tree_sha, "failure", result.state, result.note)
    _record(repo, state, result, verdict={"sha": tip, "failed": still_failing})


def _bisect(
    commits: list[str], ids: list[str], probe: Callable[[str, list[str]], Answer]
) -> tuple[list[tuple[str, set[str]]], set[str]]:
    """Each id's first failing commit, confirmed by a second probe there, and the ids a
    probe could not answer for or a confirmation did not repeat. Every id is known to pass
    before the first commit and was seen failing at the last, in the tip's own rerun; the
    search takes that, but a culprit is only named on the confirmation's probe. The tip's
    rerun alone once named the newest merge for a failure that was load (#2668)."""
    remaining = set(ids)
    lost: set[str] = set()
    out: list[tuple[str, set[str]]] = []
    start = 0
    cache: dict[tuple[int, frozenset[str]], set[str]] = {}

    def failing(index: int) -> set[str]:
        if index == len(commits) - 1:
            return set(remaining)
        key = (index, frozenset(remaining))
        if key not in cache:
            answer = probe(commits[index], sorted(remaining))
            unsure = answer.unknown(sorted(remaining))
            if unsure:
                lost.update(unsure)
                remaining.difference_update(unsure)
            cache[(index, frozenset(remaining))] = answer.failed & remaining
            return answer.failed & remaining
        return cache[key]

    while remaining and start < len(commits):
        lo, hi = start, len(commits) - 1
        while lo < hi and remaining:
            mid = (lo + hi) // 2
            if failing(mid):
                hi = mid
            else:
                lo = mid + 1
        if not remaining:
            break
        here = failing(lo)
        if not here:
            # `hi` was set by an id dropped since. Every id still left passed at each
            # `lo = mid + 1` (decided on a superset of them) and at `lo`: search after it.
            start = lo + 1
            continue
        out.append((commits[lo], here))
        remaining -= here
        start = lo + 1
    lost |= remaining  # never located: reported, not lost
    # A culprit is named on two probes, not one: a single false failure (load, a database
    # restarting mid-probe) would otherwise move the blame to an innocent merge (#2668).
    confirmed: list[tuple[str, set[str]]] = []
    for sha, here in out:
        again = probe(sha, sorted(here))
        kept = again.failed & here
        lost |= here - kept
        if kept:
            confirmed.append((sha, kept))
    return confirmed, lost


def _report(culprit: Culprit, tip: str, ids_ok: bool) -> str:
    head = (
        f"rails trunk: the full suite on the base tip `{tip[:12]}` fails tests that passed "
        f"before `{culprit.sha[:12]}` (this PR's merge)"
    )
    if not ids_ok:
        return head + f": {len(culprit.ids)} test(s). Their ids are held on the operator's machine (`rails trunk status`).\n"
    tests = "\n".join(f"- `{i}`" for i in culprit.ids[:20])
    more = f"\n- (+{len(culprit.ids) - 20} more)" if len(culprit.ids) > 20 else ""
    return f"{head}:\n\n{tests}{more}\n"


def _ids_postable(repo: store.RepoId, top: Path, ids: list[str]) -> bool:
    """Test ids leave this machine only through the leak check `rails ship` applies; a
    repo without one posts them as they are."""
    if not (top / "rails" / "leak.toml").is_file():
        return True
    from rails import leak

    result = leak.check_lines(repo, list(leak.text_lines("trunk", "\n".join(ids))), leak.allowlist_for(top))
    return result.code == leak.EXIT_CLEAN


def _act(
    repo: store.RepoId,
    top: Path,
    state: dict[str, Any],
    mode: str,
    forge: Forge,
    culprit: Culprit,
    tip: str,
    revert_check: Callable[[dict[str, Any]], bool],
    out,
) -> None:
    pr = forge.pr_for_commit(culprit.sha)
    if pr is None:
        culprit.note = "no PR"
        print(f"  culprit {culprit.sha[:12]} has no PR; reported only", file=out)
        return
    culprit.pr = int(pr["number"])
    reverts = state.setdefault("reverts", [])
    report = _report(culprit, tip, _ids_postable(repo, top, culprit.ids))
    for row in reverts:
        if isinstance(row, dict) and int(row.get("pr", -1)) == culprit.pr:
            # Opened by an earlier pass: finish whatever that pass did not reach (it may
            # have been killed during the check), and open nothing new.
            culprit.revert = row.get("revert")
            culprit.note = "already reverted"
            print(f"  culprit #{culprit.pr} was already reverted by #{row.get('revert')}", file=out)
            _finish(repo, state, row, forge, culprit, report, revert_check, out)
            return
    ours = {int(r["revert"]) for r in reverts if isinstance(r, dict) and r.get("revert")}
    if culprit.pr in ours or str(pr.get("title", "")).endswith(REVERT_MARK):
        culprit.note = "a runner revert; not reverted again"
        forge.comment(culprit.pr, report + "\nThis PR is a rails trunk revert, so it is not reverted again.")
        print(f"  culprit #{culprit.pr} is a runner revert; reported only", file=out)
        return
    if mode == "off" or not culprit.revertable:
        culprit.note = "reported" if culprit.revertable else "reported (no trunk_rerun: no flake check)"
        forge.comment(culprit.pr, report)
        return
    title = f"Revert #{culprit.pr}: master red at {tip[:12]} {REVERT_MARK}"
    body = report + f"\nOpened by rails trunk ({mode}). Re-land with a fix.\n"
    made = forge.revert(pr, title, body)
    if made is None:
        culprit.note = "the revert could not be opened (a conflict?)"
        forge.comment(culprit.pr, report + "\nrails trunk could not open a revert; fix forward.")
        print(f"  culprit #{culprit.pr}: no revert could be opened", file=out)
        return
    culprit.revert = int(made["number"])
    row = {
        "culprit": culprit.sha,
        "pr": culprit.pr,
        "revert": culprit.revert,
        "head_ref": str(made.get("head_ref", "")),
        "head_sha": str(made.get("head_sha", "")),
        "mode": mode,
        "ids": culprit.ids,
        "armed": False,
        "checked": mode != "auto",
        "commented": False,
        "at": int(time.time()),
    }
    reverts.append(row)
    del reverts[:-50]
    write_state(repo, state)  # recorded before anything that can fail or take an hour
    _finish(repo, state, row, forge, culprit, report, revert_check, out)


def _finish(
    repo: store.RepoId,
    state: dict[str, Any],
    row: dict[str, Any],
    forge: Forge,
    culprit: Culprit,
    report: str,
    revert_check: Callable[[dict[str, Any]], bool],
    out,
) -> None:
    """The steps after a revert opens, each recorded as it completes: in auto mode the
    check and the arm, then the comment on the culprit PR. A pass that dies part-way
    leaves the rest to the next pass that names the same culprit."""
    if not row.get("checked", True):  # a row with no flag is done (written before them)
        made = {"number": row["revert"], "head_ref": row.get("head_ref", ""), "head_sha": row.get("head_sha", "")}
        try:
            ok = bool(revert_check(made))
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is a red check
            ok = False
            print(f"  revert #{row['revert']}: its check could not run ({type(exc).__name__}: {exc})", file=out)
        if ok:
            row["armed"] = forge.arm(int(row["revert"]))
            if not row["armed"]:
                culprit.note = "the revert could not be armed"
        else:
            culprit.note = "the revert's check is red; not armed"
        row["checked"] = True
        write_state(repo, state)
    culprit.armed = bool(row.get("armed"))
    if not row.get("commented", True):
        forge.comment(
            int(row["pr"]),
            report
            + f"\nReverted by #{row['revert']}"
            + (" (auto-squash armed)." if culprit.armed else " (not armed: a person merges it).")
            + " Re-land with a fix.",
        )
        row["commented"] = True
        write_state(repo, state)
    print(
        f"  culprit #{row['pr']} ({str(row.get('culprit', ''))[:12]}): revert #{row['revert']}"
        + (" armed" if culprit.armed else " NOT armed"),
        file=out,
    )


def _post(
    forge: Forge, config: lanes_mod.LaneConfig, tip: str, tree_sha: str, state: str, word: str, note: str
) -> None:
    try:
        forge.post_status(tip, config.context(CONTEXT), state, _description(tree_sha, word, note))
    except GitError:
        pass  # the record below is the receipt; a status that could not land is not a verdict


def _remember_flakes(state: dict[str, Any], tip: str, ids: list[str]) -> None:
    rows = state.setdefault("flaky", [])
    now = int(time.time())
    seen = {(r.get("sha"), r.get("id")) for r in rows if isinstance(r, dict)}
    rows.extend({"sha": tip, "id": i, "at": now} for i in ids if (tip, i) not in seen)
    del rows[:-50]


def _prune_logs(logs: Path) -> None:
    """Keep the newest `_KEEP_LOG_DIRS` tips' log directories and as many revert logs."""
    try:
        entries = list(logs.iterdir())
    except OSError:
        return
    for kind in (True, False):
        group = sorted((p for p in entries if p.is_dir() is kind), key=lambda p: p.stat().st_mtime)
        for old in group[:-_KEEP_LOG_DIRS]:
            if kind:
                shutil.rmtree(old, ignore_errors=True)
            else:
                old.unlink(missing_ok=True)


def _record(
    repo: store.RepoId, state: dict[str, Any], result: Pass, *, verdict: dict[str, Any] | None
) -> None:
    previous = state.get("last") or {}
    attempts = 1
    if result.state == "error" and previous.get("sha") == result.tip and previous.get("state") == "error":
        attempts = int(previous.get("attempts", 1)) + 1
    state["last"] = {
        "sha": result.tip,
        "state": result.state,
        "note": result.note,
        "attempts": attempts,
        "at": int(time.time()),
    }
    if verdict is not None:
        state["verdict"] = verdict
    write_state(repo, state)
    store.append_jsonl(
        trunk_dir(repo) / "passes.jsonl",
        {
            "sha": result.tip,
            "state": result.state,
            "failed": result.failed,
            "flaky": result.flaky,
            "unattributed": result.unattributed,
            "culprits": [c.__dict__ for c in result.culprits],
            "lane_runs": result.lane_runs,
            "reruns": result.reruns,
            "note": result.note,
            "at": int(time.time()),
        },
    )


# --- the runner ----------------------------------------------------------------------


def _context(cwd: Path, out) -> tuple[store.RepoId, Path, lanes_mod.LaneConfig] | None:
    from rails.check import find_lanes_file

    repo = store.find_repo(cwd)
    if repo is None:
        print("rails trunk: not inside a git checkout", file=out)
        return None
    top = repo.main
    lanes_file = find_lanes_file(top)
    if lanes_file is None:
        print("rails trunk: no lanes file", file=out)
        return None
    return repo, top, lanes_mod.load(lanes_file)


def _default_forge(top: Path, out) -> Forge | None:
    slug = origin_slug(top)
    if slug is None:
        print("rails trunk: origin is not a GitHub remote", file=out)
        return None
    return GitHub(top, slug)


def _python() -> str:
    """rails is standard library only, so the base interpreter runs it. A session
    worktree's venv would be pinned for the runner's whole life (and may be deleted)."""
    return getattr(sys, "_base_executable", "") or sys.executable


def check_revert(repo: store.RepoId, top: Path, made: dict[str, Any], out=sys.stdout) -> bool:
    """`rails check`, then `rails post`, on a revert PR's head in the kept worktree. Both
    must pass: a green check whose statuses never landed cannot merge."""
    tree_path = trunk_dir(repo) / "tree"
    git(top, "fetch", "--quiet", "origin", str(made["head_ref"]))
    _checkout(top, tree_path, str(made["head_sha"]))
    rails_bin = Path(__file__).resolve().parent.parent / "bin" / "rails"
    log = trunk_dir(repo) / "logs" / f"revert-{made['number']}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    codes = []
    with open(log, "w", encoding="utf-8", errors="replace") as handle:
        for sub in ("check", "post"):
            done = subprocess.run(
                [_python(), str(rails_bin), sub],
                cwd=str(tree_path),
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
            codes.append(done.returncode)
            if done.returncode != 0:
                break
    print(f"  revert #{made['number']}: rails check/post exited {codes} (log: {log})", file=out)
    return codes == [0, 0]


def run_once(
    cwd: Path,
    *,
    forge: Forge | None = None,
    revert_check: Callable[[dict[str, Any]], bool] | None = None,
    out=sys.stdout,
) -> int:
    found = _context(cwd, out)
    if found is None:
        return 2
    repo, top, _ = found
    forge = forge or _default_forge(top, out)
    if forge is None:
        return 2
    checker = revert_check or (lambda made: check_revert(repo, top, made, out))
    holder = {"leaf": repo.leaf, "lane": "trunk", "sha": ""}
    try:
        with store.machine_lock(lock_name(repo), holder, wait=False):
            result = run_pass(top, forge=forge, revert_check=checker, force=True, out=out)
    except store.LockBusy:
        print("rails trunk: a runner is already live; it will test the tip", file=out)
        return 0
    except Exception as exc:  # noqa: BLE001 - run_pass recorded it as an error pass
        print(f"rails trunk: the pass failed ({type(exc).__name__}: {exc})", file=out)
        return 1
    return 0 if result.state in ("green", "unchanged", "no-trunk-lane") else 1


def _remote_tip(top: Path, base: str) -> str | None:
    remote, branch = _remote_branch(base)
    try:
        out = git(top, "ls-remote", remote, f"refs/heads/{branch}")
    except GitError:
        return None
    first = out.split()
    return first[0] if first else None


def _kick_path(repo: store.RepoId) -> Path:
    return trunk_dir(repo) / "kick"


def _kick(repo: store.RepoId) -> None:
    """Tell a live watcher a merge is coming: it restarts its idle clock."""
    path = _kick_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(uuid.uuid4().hex, encoding="utf-8")  # unique, whatever the clock's resolution


def _read_kick(repo: store.RepoId) -> str:
    try:
        return _kick_path(repo).read_text(encoding="utf-8")
    except OSError:
        return ""


def watch(
    cwd: Path,
    *,
    forge: Forge | None = None,
    revert_check: Callable[[dict[str, Any]], bool] | None = None,
    out=sys.stdout,
    poll: float = POLL_SECS,
    idle: float = IDLE_SECS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """A pass whenever the remote tip moves past the last tested one (or an error pass is
    due a retry); exit after `idle` seconds with no pass and no kick from `rails ship`."""
    found = _context(cwd, out)
    if found is None:
        return 2
    repo, top, config = found
    forge = forge or _default_forge(top, out)
    if forge is None:
        return 2
    checker = revert_check or (lambda made: check_revert(repo, top, made, out))
    holder = {"leaf": repo.leaf, "lane": "trunk-watch", "sha": ""}
    try:
        with store.machine_lock(lock_name(repo), holder, wait=False):
            last_move = clock()
            kick = _read_kick(repo)
            while True:
                tip = _remote_tip(top, config.base)
                last = read_state(repo).get("last") or {}
                if tip and (tip != last.get("sha") or last.get("state") == "error"):
                    try:
                        result = run_pass(top, forge=forge, revert_check=checker, out=out)
                        if result.state != "unchanged":
                            last_move = clock()
                    except Exception as exc:  # noqa: BLE001 - recorded by run_pass; keep watching
                        # Not activity: a pass that keeps crashing must not keep the
                        # watcher alive. run_pass recorded it, so it is retried on backoff.
                        print(f"rails trunk: the pass failed ({type(exc).__name__}: {exc})", file=out)
                now_kick = _read_kick(repo)
                if now_kick != kick:
                    kick, last_move = now_kick, clock()
                if clock() - last_move >= idle:
                    print(f"rails trunk: no pass for {int(idle // 60)} min; stopping", file=out)
                    return 0
                sleep(poll)
    except store.LockBusy:
        print("rails trunk: a runner is already live", file=out)
        return 0


def _within(path: str, root: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def runner_live(repo: store.RepoId) -> bool:
    try:
        with store.machine_lock(lock_name(repo), {}, wait=False):
            return False
    except store.LockBusy:
        return True


def _spawn(argv: list[str], **kwargs: Any) -> None:
    """Start the detached watcher (one seam, so a test can stand in for it)."""
    subprocess.Popen(argv, **kwargs)


def _declares_trunk(top: Path) -> bool:
    """Whether this worktree's lanes file, or the base branch's committed one, declares a
    trunk lane. Never the main checkout's working tree: it may be any number of merges
    behind the base (review of the jarvis half, 4f47b9216)."""
    from rails.check import LANES_FILES, find_lanes_file

    configs: list[lanes_mod.LaneConfig] = []
    found = find_lanes_file(top)
    if found is not None:
        try:
            configs.append(lanes_mod.load(found))
        except (OSError, ValueError):
            pass
    base = configs[0].base if configs else lanes_mod.LaneConfig(lanes=[]).base
    for rel in LANES_FILES:
        try:
            text = git(top, "show", f"{base}:{rel}")
        except GitError:
            continue
        try:
            configs.append(lanes_mod.loads(text))
        except ValueError:
            pass
        break
    return any(lane.trunk for config in configs for lane in config.lanes)


def start_background(top: Path, out=sys.stdout) -> bool:
    """Start `rails trunk watch` detached when the lanes declare a trunk lane and no runner
    is live; a live one is kicked so it waits for this merge. True when one was started."""
    repo = store.find_repo(top)
    if repo is None:
        return False
    if not _declares_trunk(top):
        return False
    _kick(repo)
    if runner_live(repo):
        print("  trunk: a runner is live; it tests the tip after this merges", file=out)
        return False
    log = trunk_dir(repo) / "watch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    rails_bin = Path(__file__).resolve().parent.parent / "bin" / "rails"
    argv = [_python(), str(rails_bin), "trunk", "watch"]
    # The session's virtualenv is not the runner's: each lane resolves its own.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    venv = os.environ.get("VIRTUAL_ENV")
    if venv:
        # `uv run` put the session venv's scripts first on PATH; a lane must not find them.
        keep = [d for d in env.get("PATH", "").split(os.pathsep) if not _within(d, venv)]
        env["PATH"] = os.pathsep.join(keep)
    with open(log, "ab") as handle:
        kwargs: dict[str, Any] = {
            "cwd": str(repo.main),
            "stdout": handle,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
            "env": env,
        }
        if sys.platform == "win32":
            # No console window for the lanes it starts, its own process group, and out of
            # the caller's job object when the job allows it (a tool call's job may close).
            base = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            try:
                _spawn(argv, creationflags=base | 0x01000000, **kwargs)  # CREATE_BREAKAWAY_FROM_JOB
            except OSError:
                _spawn(argv, creationflags=base, **kwargs)
        else:
            _spawn(argv, start_new_session=True, **kwargs)
    print(f"  trunk: runner started; it logs to {log}", file=out)
    return True


def status(cwd: Path, out=sys.stdout) -> int:
    repo = store.find_repo(cwd)
    if repo is None:
        print("rails trunk: not inside a git checkout", file=out)
        return 2
    state = read_state(repo)
    last = state.get("last") or {}
    verdict = state.get("verdict") or {}
    if last:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(last.get("at", 0))))
        note = f" ({last['note']})" if last.get("note") else ""
        print(f"rails trunk: last pass {str(last.get('sha', ''))[:12]} {last.get('state')} at {when}{note}", file=out)
    else:
        print("rails trunk: no pass yet", file=out)
    if verdict:
        failed = verdict.get("failed") or {}
        print(f"  verdict {str(verdict.get('sha', ''))[:12]}: {sum(len(v) for v in failed.values())} failing", file=out)
        for name, ids in failed.items():
            for test_id in ids[:20]:
                print(f"    {name}: {test_id}", file=out)
    for row in (state.get("flaky") or [])[-5:]:
        print(f"  flake {row.get('id')} at {str(row.get('sha', ''))[:12]}", file=out)
    for row in (state.get("reverts") or [])[-5:]:
        print(
            f"  revert #{row.get('revert')} of #{row.get('pr')} ({str(row.get('culprit', ''))[:12]})"
            + (" armed" if row.get("armed") else " unarmed"),
            file=out,
        )
    print(f"  runner: {'live' if runner_live(repo) else 'not running'}", file=out)
    return 0


def main(argv: list[str]) -> int:
    sub = argv[0] if argv else "status"
    try:
        if sub == "run":
            return run_once(Path.cwd())
        if sub == "watch":
            return watch(Path.cwd())
        if sub == "status":
            return status(Path.cwd())
    except GitError as exc:
        print(f"rails trunk: {exc}")
        return 2
    print("usage: rails trunk run|watch|status")
    return 2


__all__ = [
    "Answer",
    "CONTEXT",
    "Culprit",
    "Forge",
    "GitHub",
    "Pass",
    "check_revert",
    "failed_ids",
    "failure_tally",
    "lock_name",
    "main",
    "read_state",
    "run_once",
    "run_pass",
    "runner_live",
    "start_background",
    "status",
    "trunk_dir",
    "watch",
]
