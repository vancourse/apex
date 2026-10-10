"""`rails trunk`: the full suite runs once on the base branch's tip after merges, and a red
tip finds the commit that broke it and reverts it.

    rails trunk run       one pass: test the tip; on red, flake-check, bisect, act
    rails trunk watch     a pass whenever the tip moves; exits after 90 idle minutes
    rails trunk status    the last pass, its flakes and reverts, and whether a runner is live

A pass pools every merge since the last one. Each lane that declares ``trunk_command``
runs once on the tip, in a worktree kept under the rails data root and reused across
passes. Green: ``rails/trunk`` = success on the tip. Red: each failed test id the last
verdict did not already have is rerun alone at the tip with the lane's ``trunk_rerun``;
one that passes is a flake (it fails in the full run and passes alone) and is recorded,
never reverted. The rest are bisected over the first-parent commits since the last
verdict, rerunning only those ids; the first commit where an id fails is its culprit.

``trunk_revert`` (lanes file ``[settings]``) decides what happens to a culprit's PR:
``auto`` opens a revert PR through GitHub's ``revertPullRequest``, runs ``rails check
--post`` on its head and arms auto-squash when that is green; ``propose`` opens it and
leaves it unarmed; ``off`` only comments. Every culprit PR gets a comment naming the
failing tests. A revert the runner opened is never reverted again, only reported.

One runner per repository holds the machine lock ``trunk-<repo>``; a second finds it
held and leaves. The trunk lane does not take its ``lock`` (the pre-merge lane's), so a
pre-merge suite never queues behind a full run.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

from rails import VERSION, lanes as lanes_mod, store
from rails.gitutil import GitError, gh, gh_api, git, origin_slug, run

#: pytest's short summary: `FAILED path::test - message` / `ERROR path::test - message`.
_FAILED_ID = re.compile(r"^(?:FAILED|ERROR) (\S+?)(?: - .*)?$")
#: The status context a pass posts on the tip (a lane may not take this name).
CONTEXT = "trunk"
#: How often `watch` asks the remote for the tip, and how long it waits for a move.
POLL_SECS = 120.0
IDLE_SECS = 90 * 60.0
#: The title suffix that marks a revert the runner opened.
REVERT_MARK = "(rails trunk)"
#: pytest exit codes that mean "nothing ran", not "these ids failed".
_NOTHING_RAN = (4, 5)


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
        merged = [r for r in rows if isinstance(r, dict) and r.get("merged_at")]
        for row in merged or []:
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
        made = (((data or {}).get("data") or {}).get("revertPullRequest") or {}).get(
            "revertPullRequest"
        )
        if not made or (data or {}).get("errors"):
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


def failed_ids(log_text: str) -> list[str]:
    """Test ids from pytest's short summary, in order, each once."""
    seen: dict[str, None] = {}
    for line in log_text.splitlines():
        m = _FAILED_ID.match(line.strip())
        if m:
            seen.setdefault(m.group(1))
    return list(seen)


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
    if not target.exists():
        return False
    if not rest:
        return True
    name = rest.split("::")[-1].split("[")[0]
    try:
        return name in target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def _rerun(lane: lanes_mod.Lane, tree: Path, ids: list[str], log: Path) -> tuple[int, str]:
    from rails.check import run_lane

    rerun = lanes_mod.Lane(
        name=f"{lane.name}-rerun",
        command=[*lane.trunk_rerun, *ids],
        env=dict(lane.env),
        timeout_min=lane.timeout_min,
    )
    code, _ = run_lane(rerun, tree, log)
    text = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
    return code, text


# --- one pass ------------------------------------------------------------------------


@dataclass
class Culprit:
    sha: str
    ids: list[str]
    pr: int | None = None
    revert: int | None = None
    armed: bool = False
    note: str = ""


@dataclass
class Pass:
    tip: str
    state: str = ""  # green | red | baseline | still-red | error | unchanged
    failed: dict[str, list[str]] = field(default_factory=dict)
    flaky: list[str] = field(default_factory=list)
    culprits: list[Culprit] = field(default_factory=list)
    lane_runs: int = 0
    reruns: int = 0
    note: str = ""


def _remote_branch(base: str) -> tuple[str, str]:
    remote, _, branch = base.partition("/")
    return (remote, branch) if branch else ("origin", remote)


def _description(tree_sha: str, state: str, note: str) -> str:
    return " ".join(p for p in (f"trunk {state}", note, f"tree={tree_sha[:12]}", f"rails-{VERSION}") if p)


def run_pass(
    top: Path,
    *,
    forge: Forge,
    revert_check: Callable[[dict[str, Any]], bool],
    out=sys.stdout,
) -> Pass:
    """Test the base tip once, attribute what is newly red, act, record, post."""
    from rails.check import find_lanes_file, missing_prerequisite, run_lane

    repo = store.find_repo(top)
    assert repo is not None
    lanes_file = find_lanes_file(top)
    config = lanes_mod.load(lanes_file) if lanes_file else lanes_mod.LaneConfig(lanes=[])
    remote, branch = _remote_branch(config.base)
    git(top, "fetch", "--quiet", remote, branch, check=False)
    tip = git(top, "rev-parse", f"{remote}/{branch}")
    state = read_state(repo)
    result = Pass(tip=tip)
    if (state.get("last") or {}).get("sha") == tip:
        result.state = "unchanged"
        print(f"rails trunk: {tip[:12]} was already tested", file=out)
        return result

    root = trunk_dir(repo)
    tree_path = root / "tree"
    log_dir = root / "logs" / tip[:12]
    _checkout(top, tree_path, tip)
    tip_lanes = find_lanes_file(tree_path)
    tip_config = lanes_mod.load(tip_lanes) if tip_lanes else config
    trunk_lanes = [lane for lane in tip_config.lanes if lane.trunk]
    tree_sha = git(top, "rev-parse", f"{tip}^{{tree}}")
    if not trunk_lanes:
        print("rails trunk: no lane declares trunk_command; nothing to run", file=out)
        result.state = "unchanged"
        return result

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
        ids = failed_ids(log.read_text(encoding="utf-8", errors="replace") if log.exists() else "")
        if not ids:
            result.state = "error"
            result.note = f"{lane.name} exited {code} without naming a failed test"
            break
        failing[lane.name] = ids

    if result.state == "error":
        # No verdict: the tip is recorded as tried, the last verdict stays the bisect base.
        _post(forge, tip_config, tip, tree_sha, "failure", "error", result.note)
        _record(repo, state, result, verdict=None)
        return result

    result.failed = failing
    verdict = state.get("verdict") if isinstance(state.get("verdict"), dict) else None
    if not failing:
        result.state = "green"
        _post(forge, tip_config, tip, tree_sha, "success", "green", f"{result.lane_runs} lane(s)")
        _record(repo, state, result, verdict={"sha": tip, "failed": {}})
        return result

    if verdict is None or not _is_ancestor(top, str(verdict.get("sha", "")), tip):
        result.state = "baseline"
        count = sum(len(v) for v in failing.values())
        _post(forge, tip_config, tip, tree_sha, "failure", "baseline", f"red baseline: {count} failing")
        _record(repo, state, result, verdict={"sha": tip, "failed": failing})
        return result

    known = verdict.get("failed") or {}
    by_name = {lane.name: lane for lane in trunk_lanes}
    still: dict[str, list[str]] = {}
    new: dict[str, list[str]] = {}
    for name, ids in failing.items():
        seen = set(known.get(name) or [])
        still[name] = [i for i in ids if i in seen]
        fresh = [i for i in ids if i not in seen]
        if fresh:
            new[name] = fresh

    confirmed: dict[str, list[str]] = {}
    for name, ids in new.items():
        lane = by_name[name]
        if not lane.trunk_rerun:
            confirmed[name] = ids  # no way to tell a flake: every new id is attributed
            continue
        failing_now = _failing_at(top, tree_path, tip, lane, ids, log_dir / f"{name}.rerun.log", result)
        result.flaky.extend(i for i in ids if i not in failing_now)
        if failing_now:
            confirmed[name] = [i for i in ids if i in failing_now]
    if result.flaky:
        _remember_flakes(state, tip, result.flaky)

    carried = {k: v for k, v in still.items() if v}
    if not confirmed:
        result.state = "still-red" if carried else "green"
        note = f"{len(result.flaky)} flake(s)" if result.flaky else ""
        if carried:
            note = (note + "; " if note else "") + f"still red: {sum(len(v) for v in carried.values())} known"
        _post(
            forge,
            tip_config,
            tip,
            tree_sha,
            "failure" if carried else "success",
            result.state,
            note,
        )
        _record(repo, state, result, verdict={"sha": tip, "failed": carried})
        return result

    commits = _first_parent(top, str(verdict["sha"]), tip)
    found: dict[str, list[str]] = {}
    unattributed: list[str] = []
    for name, ids in confirmed.items():
        lane = by_name[name]
        if not lane.trunk_rerun:
            # Without a rerun there is no bisect: one merge is its own culprit, several
            # are reported for a person to split.
            if len(commits) == 1:
                found.setdefault(commits[0], []).extend(ids)
            else:
                unattributed.extend(ids)
            continue

        def probe(sha: str, wanted: list[str], lane=lane, name=name) -> set[str]:
            return _failing_at(
                top, tree_path, sha, lane, wanted, log_dir / f"{name}.bisect-{sha[:12]}.log", result
            )

        for sha, ids_here in _bisect(commits, ids, probe):
            found.setdefault(sha, []).extend(sorted(ids_here))
    if unattributed:
        result.note = f"{len(unattributed)} new failure(s) over {len(commits)} merges, no trunk_rerun to bisect"
    for sha in commits:
        if sha in found:
            result.culprits.append(Culprit(sha=sha, ids=found[sha]))
    for culprit in result.culprits:
        _act(repo, state, tip_config, forge, culprit, tip, revert_check, out)

    result.state = "red"
    named = ", ".join(
        f"{c.sha[:12]}" + (f" #{c.pr}" if c.pr else "") + (f" -> #{c.revert}" if c.revert else "")
        for c in result.culprits
    )
    words = [f"culprit {named}"] if named else []
    if result.note:
        words.append(result.note)
    _post(forge, tip_config, tip, tree_sha, "failure", "red", "; ".join(words))
    merged = {k: sorted(set(carried.get(k, [])) | set(confirmed.get(k, []))) for k in set(carried) | set(confirmed)}
    _record(repo, state, result, verdict={"sha": tip, "failed": merged})
    return result


def _failing_at(
    top: Path,
    tree: Path,
    sha: str,
    lane: lanes_mod.Lane,
    ids: list[str],
    log: Path,
    result: Pass,
) -> set[str]:
    """The subset of `ids` that fails at `sha`, by rerunning only those ids there."""
    _checkout(top, tree, sha)
    present = [i for i in ids if _present(tree, i)]
    if not present:
        return set()
    code, text = _rerun(lane, tree, present, log)
    result.reruns += 1
    if code == 0:
        return set()
    named = set(failed_ids(text)) & set(present)
    if named:
        return named
    if code in _NOTHING_RAN:
        return set()
    return set(present)  # it failed without naming ids: count every one as failing


def _bisect(
    commits: list[str], ids: list[str], probe: Callable[[str, list[str]], set[str]]
) -> list[tuple[str, set[str]]]:
    """Each id's first failing commit. Every id is known to fail at the last commit."""
    remaining = set(ids)
    out: list[tuple[str, set[str]]] = []
    start = 0
    cache: dict[tuple[int, frozenset[str]], set[str]] = {}

    def failing(index: int) -> set[str]:
        if index == len(commits) - 1:
            return set(remaining)
        key = (index, frozenset(remaining))
        if key not in cache:
            cache[key] = probe(commits[index], sorted(remaining)) & remaining
        return cache[key]

    while remaining and start < len(commits):
        lo, hi = start, len(commits) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if failing(mid):
                hi = mid
            else:
                lo = mid + 1
        here = failing(lo)
        if not here:
            break
        out.append((commits[lo], here))
        remaining -= here
        start = lo + 1
    return out


def _report(culprit: Culprit, tip: str) -> str:
    tests = "\n".join(f"- `{i}`" for i in culprit.ids[:20])
    more = f"\n- (+{len(culprit.ids) - 20} more)" if len(culprit.ids) > 20 else ""
    return (
        f"rails trunk: the full suite on the base tip `{tip[:12]}` fails tests that passed "
        f"before `{culprit.sha[:12]}` (this PR's merge):\n\n{tests}{more}\n"
    )


def _act(
    repo: store.RepoId,
    state: dict[str, Any],
    config: lanes_mod.LaneConfig,
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
    ours = {int(r["revert"]) for r in reverts if isinstance(r, dict) and r.get("revert")}
    report = _report(culprit, tip)
    if culprit.pr in ours or str(pr.get("title", "")).endswith(REVERT_MARK):
        culprit.note = "a runner revert; not reverted again"
        forge.comment(culprit.pr, report + "\nThis PR is a rails trunk revert, so it is not reverted again.")
        print(f"  culprit #{culprit.pr} is a runner revert; reported only", file=out)
        return
    if config.trunk_revert == "off":
        culprit.note = "reported"
        forge.comment(culprit.pr, report)
        return
    title = f"Revert #{culprit.pr}: master red at {tip[:12]} {REVERT_MARK}"
    body = report + f"\nOpened by rails trunk ({config.trunk_revert}). Re-land with a fix.\n"
    made = forge.revert(pr, title, body)
    if made is None:
        culprit.note = "the revert could not be opened (a conflict?)"
        forge.comment(culprit.pr, report + "\nrails trunk could not open a revert; fix forward.")
        print(f"  culprit #{culprit.pr}: no revert could be opened", file=out)
        return
    culprit.revert = int(made["number"])
    if config.trunk_revert == "auto":
        if revert_check(made):
            culprit.armed = forge.arm(culprit.revert)
            if not culprit.armed:
                culprit.note = "the revert could not be armed"
        else:
            culprit.note = "the revert's check is red; not armed"
    forge.comment(
        culprit.pr,
        report
        + f"\nReverted by #{culprit.revert}"
        + (" (auto-squash armed)." if culprit.armed else " (not armed: a person merges it).")
        + " Re-land with a fix.",
    )
    reverts.append(
        {
            "culprit": culprit.sha,
            "pr": culprit.pr,
            "revert": culprit.revert,
            "ids": culprit.ids,
            "armed": culprit.armed,
            "at": int(time.time()),
        }
    )
    del reverts[:-50]
    print(
        f"  culprit #{culprit.pr} ({culprit.sha[:12]}): revert #{culprit.revert}"
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
    rows.extend({"sha": tip, "id": i, "at": now} for i in ids)
    del rows[:-50]


def _record(
    repo: store.RepoId, state: dict[str, Any], result: Pass, *, verdict: dict[str, Any] | None
) -> None:
    state["last"] = {
        "sha": result.tip,
        "state": result.state,
        "note": result.note,
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


def check_revert(repo: store.RepoId, top: Path, made: dict[str, Any], out=sys.stdout) -> bool:
    """`rails check --post` on a revert PR's head, in the kept worktree."""
    tree_path = trunk_dir(repo) / "tree"
    git(top, "fetch", "--quiet", "origin", str(made["head_ref"]), check=False)
    _checkout(top, tree_path, str(made["head_sha"]))
    rails_bin = Path(__file__).resolve().parent.parent / "bin" / "rails"
    log = trunk_dir(repo) / "logs" / f"revert-{made['number']}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w", encoding="utf-8", errors="replace") as handle:
        done = subprocess.run(
            [sys.executable, str(rails_bin), "check", "--post"],
            cwd=str(tree_path),
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    print(f"  revert #{made['number']}: rails check --post exited {done.returncode} (log: {log})", file=out)
    return done.returncode == 0


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
            result = run_pass(top, forge=forge, revert_check=checker, out=out)
    except store.LockBusy:
        print("rails trunk: a runner is already live; it will test the tip", file=out)
        return 0
    return 0 if result.state in ("green", "unchanged") else 1


def _remote_tip(top: Path, base: str) -> str | None:
    remote, branch = _remote_branch(base)
    try:
        out = git(top, "ls-remote", remote, f"refs/heads/{branch}")
    except GitError:
        return None
    first = out.split()
    return first[0] if first else None


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
    """A pass whenever the remote tip moves past the last tested one; exit when idle."""
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
            while True:
                tip = _remote_tip(top, config.base)
                if tip and tip != (read_state(repo).get("last") or {}).get("sha"):
                    try:
                        run_pass(top, forge=forge, revert_check=checker, out=out)
                    except GitError as exc:
                        print(f"rails trunk: the pass failed to run: {exc}", file=out)
                    last_move = clock()
                elif clock() - last_move >= idle:
                    print(f"rails trunk: no new tip for {int(idle // 60)} min; stopping", file=out)
                    return 0
                sleep(poll)
    except store.LockBusy:
        print("rails trunk: a runner is already live", file=out)
        return 0


def runner_live(repo: store.RepoId) -> bool:
    try:
        with store.machine_lock(lock_name(repo), {}, wait=False):
            return False
    except store.LockBusy:
        return True


def start_background(top: Path, out=sys.stdout) -> bool:
    """Start `rails trunk watch` detached when the lanes declare a trunk lane and no runner
    is live. Its output goes to the trunk's own log. True when one was started."""
    from rails.check import find_lanes_file

    repo = store.find_repo(top)
    if repo is None:
        return False
    lanes_file = find_lanes_file(repo.main)
    if lanes_file is None or not any(l.trunk for l in lanes_mod.load(lanes_file).lanes):
        return False
    if runner_live(repo):
        print("  trunk: a runner is live; it tests the tip after this merges", file=out)
        return False
    log = trunk_dir(repo) / "watch.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    rails_bin = Path(__file__).resolve().parent.parent / "bin" / "rails"
    argv = [sys.executable, str(rails_bin), "trunk", "watch"]
    with open(log, "ab") as handle:
        kwargs: dict[str, Any] = {
            "cwd": str(repo.main),
            "stdout": handle,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            # No console window for the lanes it starts, its own process group, and out of
            # the caller's job object when the job allows it (a tool call's job may close).
            base = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
            try:
                subprocess.Popen(argv, creationflags=base | 0x01000000, **kwargs)  # CREATE_BREAKAWAY_FROM_JOB
            except OSError:
                subprocess.Popen(argv, creationflags=base, **kwargs)
        else:
            subprocess.Popen(argv, start_new_session=True, **kwargs)
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
        count = sum(len(v) for v in (verdict.get("failed") or {}).values())
        print(f"  verdict {str(verdict.get('sha', ''))[:12]}: {count} failing", file=out)
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
    "CONTEXT",
    "Culprit",
    "Forge",
    "GitHub",
    "Pass",
    "check_revert",
    "failed_ids",
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
