"""`rails check` and `rails post`: CI on the laptop, verified by CI in seconds.

    rails check            run every lane the diff selects; seal a marker when all pass
    rails check --quick    only lanes marked quick (the pre-PR push requirement)
    rails check --post     ...then post one `rails/<lane>` commit status per lane
    rails check --lane X   run one lane (repeatable); never writes the full marker
    rails post             post statuses from the receipts already written for HEAD

The diff is HEAD against merge-base(HEAD, settings.base). The tree must be
clean (tracked files): a marker certifies a COMMIT, and a check that ran over
uncommitted edits certifies nothing about the commit that gets pushed.

Lane output goes to ``<store>/<repo>/<leaf>/logs/<sha12>/<lane>.log``; a failing
lane's last lines are printed. Each lane leaves a sealed receipt; the marker is
written only when every selected lane passed at this exact commit.
"""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from rails import VERSION, lanes as lanes_mod, receipts, store
from rails.gitutil import (
    GitError,
    changed_files,
    dirty_tracked,
    gh,
    gh_api,
    head,
    merge_base,
    origin_slug,
    toplevel,
    tree,
)

LANES_FILES = ("rails/lanes.toml", "lanes.toml")
TAIL_LINES = 60


def find_lanes_file(top: Path) -> Path | None:
    for rel in LANES_FILES:
        if (top / rel).is_file():
            return top / rel
    return None


def _postgres_reachable() -> bool:
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/postgres"
    )
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _docker_alive() -> bool:
    if not shutil.which("docker"):
        return False
    try:
        return (
            subprocess.run(
                ["docker", "info"], capture_output=True, timeout=20
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def missing_prerequisite(lane: lanes_mod.Lane) -> str | None:
    for need in lane.needs:
        if need in ("uv", "node", "pnpm", "gh") and not shutil.which(need):
            return f"`{need}` is not on PATH"
        if need == "docker" and not _docker_alive():
            return "Docker is not answering (`docker info` failed) - not a code failure"
        if need == "postgres" and not _postgres_reachable():
            return "Postgres is not reachable at DATABASE_URL - not a code failure"
    return None


def _resolve(argv: list[str]) -> list[str]:
    """Resolve argv[0] through PATH (and PATHEXT on Windows: `pnpm` is `pnpm.cmd`)."""
    found = shutil.which(argv[0])
    return [found, *argv[1:]] if found else argv


def run_lane(lane: lanes_mod.Lane, top: Path, log_path: Path) -> tuple[int, float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update(lane.env)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    started = time.monotonic()
    with open(log_path, "w", encoding="utf-8", errors="replace", newline="\n") as log:
        log.write(f"$ {' '.join(lane.command)}\n")
        log.flush()
        try:
            proc = subprocess.run(
                _resolve(lane.command),
                cwd=str(top),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=lane.timeout_min * 60,
            )
            code = proc.returncode
        except subprocess.TimeoutExpired:
            log.write(f"\nRAILS: lane timed out after {lane.timeout_min} min\n")
            code = 124
        except OSError as exc:
            log.write(f"\nRAILS: could not start: {exc}\n")
            code = 127
    return code, time.monotonic() - started


def _tail(path: Path, n: int = TAIL_LINES) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:])


def check(
    cwd: Path,
    *,
    quick: bool = False,
    post_after: bool = False,
    only: list[str] | None = None,
    allow_dirty: bool = False,
    out=sys.stdout,
) -> int:
    repo = store.find_repo(cwd)
    if repo is None:
        print("rails check: not inside a git checkout", file=out)
        return 2
    top = toplevel(cwd)
    lanes_file = find_lanes_file(top)
    if lanes_file is None:
        print(
            f"rails check: no {' or '.join(LANES_FILES)} in {top}; run `rails adopt` first",
            file=out,
        )
        return 2
    config = lanes_mod.load(lanes_file)
    dirty = dirty_tracked(top)
    if dirty and not allow_dirty:
        print(
            "rails check: uncommitted changes to tracked files; a marker certifies a commit.",
            file=out,
        )
        print(
            "  commit first (a commit is your save point; it is never blocked):",
            file=out,
        )
        for path in dirty[:10]:
            print(f"    {path}", file=out)
        return 2
    sha = head(top)
    tree_sha = tree(top)
    base_sha = merge_base(top, config.base)
    if base_sha is None:
        print(
            f"rails check: {config.base} does not resolve here (git fetch?); selecting EVERY lane",
            file=out,
        )
        changed = list(config.all_lanes_on) or ["<unknown>"]
        selection = lanes_mod.Selection(selected=list(config.lanes), skipped=[])
    else:
        changed = changed_files(top, base_sha)
        selection = lanes_mod.select(config, changed, quick=quick)
    selected = selection.selected
    if only:
        unknown = [
            name for name in only if name not in {lane.name for lane in config.lanes}
        ]
        if unknown:
            print(f"rails check: unknown lane(s): {', '.join(unknown)}", file=out)
            return 2
        selected = [config.lane(name) for name in only]
    print(
        f"rails check {sha[:12]}  {len(changed)} changed path(s) vs {config.base}",
        file=out,
    )
    for lane, reason in selection.skipped:
        if not only or lane.name in only:
            print(f"  skip  {lane.name:<14} {reason}", file=out)
    failed: list[str] = []
    advisory_failed: list[str] = []
    passed: list[str] = []
    from rails import structural

    for finding in structural.run(top, base_sha):
        print(f"  FAIL  {finding.check:<14} {finding.message}", file=out)
        failed.append(finding.check)
    if not selected:
        print("  nothing selected", file=out)
    log_dir = repo.leaf_dir / "logs" / sha[:12]
    for lane in selected:
        why = missing_prerequisite(lane)
        if why:
            print(f"  FAIL  {lane.name:<14} prerequisite: {why}", file=out)
            receipts.write(
                repo,
                "lane",
                lane=lane.name,
                sha=sha,
                tree=tree_sha,
                exit=125,
                secs=0,
                why=why,
            )
            (advisory_failed if lane.advisory() else failed).append(lane.name)
            continue
        print(f"  run   {lane.name:<14} {' '.join(lane.command)}", file=out, flush=True)
        log_path = log_dir / f"{lane.name}.log"
        code, secs = run_lane(lane, top, log_path)
        receipts.write(
            repo,
            "lane",
            lane=lane.name,
            sha=sha,
            tree=tree_sha,
            exit=code,
            secs=round(secs, 1),
            cmd=" ".join(lane.command),
            dirty=bool(dirty),
        )
        if code == 0:
            print(f"  PASS  {lane.name:<14} {secs:6.0f}s", file=out, flush=True)
            passed.append(lane.name)
        else:
            print(
                f"  FAIL  {lane.name:<14} {secs:6.0f}s exit {code}  log: {log_path}",
                file=out,
            )
            tail = _tail(log_path)
            if tail:
                print("  ---- last lines ----", file=out)
                print("\n".join("  | " + line for line in tail.splitlines()), file=out)
            (advisory_failed if lane.advisory() else failed).append(lane.name)
    for name in advisory_failed:
        lane = config.lane(name)
        print(
            f"  ADVISORY {name}: failed or could not run; it gates nothing until {lane.advisory_until}",
            file=out,
        )
    whole_selection = not only
    if not failed and whole_selection and not dirty:
        path = receipts.write_marker(repo, sha, tree_sha, passed, quick=quick)
        print(
            f"rails check: GREEN ({'quick' if quick else 'full'} marker {path.name})",
            file=out,
        )
    elif failed:
        print(f"rails check: RED - {', '.join(failed)}", file=out)
    else:
        print(
            "rails check: lanes green; no marker (a --lane run or a dirty tree certifies nothing)",
            file=out,
        )
    if post_after and not failed:
        post(cwd, out=out)
    elif post_after:
        print("rails check: not posting statuses - the check is RED", file=out)
    return 1 if failed else 0


def post(cwd: Path, *, out=sys.stdout, rerun: bool = True) -> int:
    """Post the latest receipt per lane for HEAD as `rails/<lane>` commit statuses."""
    repo = store.find_repo(cwd)
    if repo is None:
        print("rails post: not inside a git checkout", file=out)
        return 2
    top = toplevel(cwd)
    lanes_file = find_lanes_file(top)
    config = (
        lanes_mod.load(lanes_file) if lanes_file else lanes_mod.LaneConfig(lanes=[])
    )
    slug = origin_slug(top)
    if slug is None:
        print("rails post: origin is not a GitHub remote", file=out)
        return 2
    sha = head(top)
    tree_sha = tree(top)
    rows = [r for r in receipts.read(repo, "lane", sha=sha) if receipts.valid(r)]
    if not rows:
        print(
            f"rails post: no lane receipts for {sha[:12]}; run `rails check` first",
            file=out,
        )
        return 1
    latest = receipts.latest_by(rows, "lane")
    posted = 0
    for lane_name, row in sorted(latest.items()):
        if row.get("dirty"):
            print(
                f"  skip  {lane_name:<14} ran over a dirty tree; re-run on the commit",
                file=out,
            )
            continue
        advisory = any(
            lane.name == lane_name and lane.advisory() for lane in config.lanes
        )
        if advisory and row.get("exit") != 0:
            # A red status for a lane that gates nothing reads as a broken PR and
            # wakes every CI monitor. It is reported locally and in the PR body.
            print(
                f"  skip  {lane_name:<14} advisory and not green; not posted", file=out
            )
            continue
        state = "success" if row.get("exit") == 0 else "failure"
        description = f"tree={str(row.get('tree', ''))[:12]} {int(row.get('secs', 0))}s rails-{VERSION} local"
        try:
            gh_api(
                top,
                f"repos/{slug}/statuses/{sha}",
                method="POST",
                payload={
                    "state": state,
                    "context": config.context(lane_name),
                    "description": description[:140],
                },
            )
        except GitError as exc:
            print(f"rails post: could not post {lane_name}: {exc}", file=out)
            print(
                "  (the commit must be pushed before a status can be set on it)",
                file=out,
            )
            return 1
        posted += 1
        print(f"  {state:<8}{config.context(lane_name)}", file=out)
    receipts.write(
        repo, "post", sha=sha, tree=tree_sha, lanes=sorted(latest), slug=slug
    )
    print(f"rails post: {posted} status(es) on {slug}@{sha[:12]}", file=out)
    if rerun and config.gate_workflow:
        _rerun_failed_gate(top, sha, config.gate_workflow, out)
    return 0


def _rerun_failed_gate(top: Path, sha: str, workflow: str, out) -> None:
    """A gate run that started before the statuses landed is re-run once, not left red."""
    try:
        raw = gh(
            top,
            "run",
            "list",
            "--commit",
            sha,
            "--workflow",
            workflow,
            "--json",
            "databaseId,conclusion,status",
            check=False,
        )
    except GitError:
        return
    import json

    try:
        runs = json.loads(raw or "[]")
    except ValueError:
        return
    for run in runs:
        if run.get("status") == "completed" and run.get("conclusion") == "failure":
            try:
                gh(top, "run", "rerun", str(run["databaseId"]), check=False)
                print(
                    f"  re-ran {workflow} run {run['databaseId']} (it finished before the statuses landed)",
                    file=out,
                )
            except GitError:
                pass


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="rails check")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--post", action="store_true")
    ap.add_argument("--lane", action="append", default=[])
    ap.add_argument(
        "--allow-dirty",
        action="store_true",
        help="run lanes over uncommitted edits (no marker)",
    )
    args = ap.parse_args(argv)
    try:
        return check(
            Path.cwd(),
            quick=args.quick,
            post_after=args.post,
            only=args.lane or None,
            allow_dirty=args.allow_dirty,
        )
    except GitError as exc:
        print(f"rails check: {exc}")
        return 2
