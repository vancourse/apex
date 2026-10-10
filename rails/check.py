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
import contextlib
import os
import shutil
import signal
import socket
import struct
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

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
    """Whether Postgres at DATABASE_URL takes a session, as `pg_isready` asks: a startup
    packet answered by an authentication request, or by any error but "cannot connect
    now" (SQLSTATE 57P03: starting up, shutting down, in recovery), is up. A TCP connect
    is not enough: a restarting Postgres accepts it and refuses every session, every test
    then errors, and a rerun read that as failures that blamed a merge (#2668)."""
    url = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:5432/postgres"
    )
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    user = unquote(parsed.username or "postgres")
    database = unquote(parsed.path.lstrip("/")) or user
    params = b"user\0" + user.encode() + b"\0database\0" + database.encode() + b"\0\0"
    body = struct.pack("!I", 196608) + params  # protocol 3.0
    reply = b""
    try:
        with socket.create_connection((host, port), timeout=3) as conn:
            conn.settimeout(3)
            conn.sendall(struct.pack("!I", len(body) + 4) + body)
            kind = conn.recv(1)
            if kind in (b"R", b"v"):  # an authentication request; a protocol negotiation
                return True
            if kind != b"E":
                return False
            while len(reply) < 4 or len(reply) < struct.unpack("!I", reply[:4])[0]:
                chunk = conn.recv(4096)
                if not chunk or len(reply) > 65536:
                    break
                reply += chunk
    except OSError:
        return False
    # An ErrorResponse is fields of (type byte, text, NUL); the SQLSTATE is type `C`.
    return b"\0C57P03\0" not in b"\0" + reply[4:]


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
            return (
                "Postgres at DATABASE_URL is not taking sessions (down, starting up or "
                "shutting down) - not a code failure"
            )
    return None


def _resolve(argv: list[str]) -> list[str]:
    """Resolve argv[0] through PATH (and PATHEXT on Windows: `pnpm` is `pnpm.cmd`)."""
    found = shutil.which(argv[0])
    return [found, *argv[1:]] if found else argv


def _descendants(pid: int) -> list[int] | None:
    """POSIX: every process below `pid` by parent pid, parents before children.

    None when the process table could not be read."""
    try:
        listed = subprocess.run(
            ["ps", "-A", "-o", "pid=", "-o", "ppid="],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if listed.returncode != 0:
        return None
    children: dict[int, list[int]] = {}
    for line in listed.stdout.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[0].isdigit() and fields[1].isdigit():
            children.setdefault(int(fields[1]), []).append(int(fields[0]))
    found: list[int] = []
    seen = {pid}
    queue = [pid]
    while queue:
        for child in children.get(queue.pop(0), []):
            if child not in seen:
                seen.add(child)
                found.append(child)
                queue.append(child)
    return found


def _freeze_tree(pid: int, frozen: list[int]) -> bool:
    """POSIX: SIGSTOP `pid` and every process under it into `frozen`, parents first,
    walking again until a walk finds nothing new: a stopped process cannot start
    another, so nothing is born between the listing and the kill. `frozen` stays empty
    when the process table could not be read. The caller owns the list, so what was
    stopped is killed even when the walk is cut short. False when the walk did not
    finish (a later `ps` failed, or 20 walks kept finding more)."""
    seen: set[int] = set()
    for _ in range(20):
        below = _descendants(pid)
        if below is None:
            return False
        new = [p for p in [pid, *below] if p not in seen]
        if not new:
            return True
        for p in new:
            seen.add(p)
            frozen.append(p)
            try:
                os.kill(p, signal.SIGSTOP)
            except OSError:
                pass
    return False


def _kill_tree(proc: subprocess.Popen) -> str:
    """Kill a timed-out lane and every process under it, reap it, and say what happened.

    `subprocess.run(timeout=...)` killed only the direct child, a launcher (`uv run`,
    `pnpm`); pytest and its xdist workers ran ~9 minutes past a 60-minute timeout,
    beside another session's suite (2026-10-09). The tree is found by parent pid, as
    `taskkill /T` does on Windows; the lane stays in rails's process group, so Ctrl+C,
    a hangup or a kill aimed at the group still reach it as before. A process whose
    parent had already exited is not found, nor, on Windows, one started while
    taskkill works (POSIX freezes the tree first)."""
    if os.name == "nt":
        # By full path: a bare name is looked up in the current directory first.
        root = os.environ.get("SystemRoot", r"C:\Windows")
        taskkill = os.path.join(root, "System32", "taskkill.exe")
        try:
            done = subprocess.run(
                [taskkill, "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=60,
            )
            said = " ".join((done.stdout + done.stderr).split())
            note = f"taskkill /T /F exit {done.returncode}" + (
                "" if done.returncode == 0 else f": {said[-300:]}"
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            note = f"taskkill could not run ({exc}); stopped only the lane's own process"
    else:
        frozen: list[int] = []
        complete = False
        killed, missed = 0, []
        try:
            complete = _freeze_tree(proc.pid, frozen)
        finally:
            # Whatever was stopped dies, even if Ctrl+C cut the walk short. Leaves
            # first: a frozen parent's death would SIGCONT an orphaned stopped group.
            for pid in reversed(frozen):
                try:
                    os.kill(pid, signal.SIGKILL)
                    killed += 1
                except ProcessLookupError:
                    pass  # it exited between the listing and the kill
                except OSError as exc:
                    missed.append(f"{pid} ({exc.strerror})")
        if not frozen:
            note = "could not read the process table (`ps`); stopped only the lane's own process"
        else:
            note = f"killed {killed} of the lane's {len(frozen)} process(es)"
            if missed:
                note += f"; could not kill {', '.join(missed)}"
            if not complete:
                note += "; the walk of the process table did not finish, so the list may be short"
    try:
        proc.kill()  # a no-op once it is gone
    except OSError:
        pass
    proc.wait()
    return note


def _lane_lock(
    lane: lanes_mod.Lane, repo: store.RepoId, sha: str, out
) -> contextlib.AbstractContextManager[float]:
    """The lane's machine-wide lock, or nothing when it names none.

    Every `rails check` on the box whose lane names the same lock runs that lane one at
    a time: concurrent full suites against one database slowed each other past their
    timeouts and ran the box out of ports. The wait is taken here, before `run_lane`
    starts its clock, so it counts against neither the timeout nor the lane's seconds.
    """
    if not lane.lock:
        return contextlib.nullcontext(0.0)

    def note(holder: object, waited: float) -> None:
        who = "another check"
        if isinstance(holder, dict):
            since = "?"
            stamp = holder.get("since")
            if isinstance(stamp, (int, float)):
                with contextlib.suppress(OSError, ValueError, OverflowError):
                    since = time.strftime("%H:%M", time.localtime(stamp))
            who = (
                f"{holder.get('leaf', '?')} ({holder.get('lane', '?')} at "
                f"{str(holder.get('sha', ''))[:12]}) since {since}"
            )
        print(
            f"  wait  {lane.name:<14} lock {lane.lock!r} held by {who}; "
            f"waited {waited / 60:.0f} min",
            file=out,
            flush=True,
        )

    holder = {"repo": str(repo.main), "leaf": repo.leaf, "lane": lane.name, "sha": sha}
    return store.machine_lock(lane.lock, holder, on_wait=note)


def _moved_since_start(
    top: Path, sha: str, tree_sha: str, dirty: list[str], allow_dirty: bool
) -> str | None:
    """Why the worktree no longer is the snapshot this check certifies, if it is not.

    A marker certifies the commit read at the start, and a lock wait can last an hour,
    long enough for its author to commit or edit. Only a run that was already dirty
    with ``--allow-dirty`` certifies nothing (no marker, `post` skips it), so only that
    one is held to HEAD and the tree alone; a clean start is held to staying clean.
    """
    if head(top) != sha or tree(top) != tree_sha:
        return "HEAD moved since the check started"
    if not (allow_dirty and dirty):
        now = dirty_tracked(top)
        if sorted(now) != sorted(dirty):
            changed = sorted(set(now) ^ set(dirty))
            shown = ", ".join(changed[:3]) + (" ..." if len(changed) > 3 else "")
            return f"tracked files changed since the check started ({shown})"
    return None


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
            proc = subprocess.Popen(
                _resolve(lane.command),
                cwd=str(top),
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        except OSError as exc:
            log.write(f"\nRAILS: could not start: {exc}\n")
            return 127, time.monotonic() - started
        try:
            code = proc.wait(timeout=lane.timeout_min * 60)
        except subprocess.TimeoutExpired:
            stopped = _kill_tree(proc)
            log.write(f"\nRAILS: lane timed out after {lane.timeout_min} min\n")
            log.write(f"RAILS: {stopped}\n")
            code = 124
        except BaseException:
            # Ctrl+C reached the lane's own processes too (same process group, same
            # console), so they run their own teardown; as subprocess.run did, stop
            # the direct child and go.
            proc.kill()
            proc.wait()
            raise
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
    for index, lane in enumerate(selected):
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
                dirty=bool(dirty),
            )
            (advisory_failed if lane.advisory() else failed).append(lane.name)
            continue
        log_path = log_dir / f"{lane.name}.log"
        lock_fields: dict[str, object] = {}
        moved = prerequisite = None
        with _lane_lock(lane, repo, sha, out) as waited:
            if lane.lock:
                lock_fields = {"lock": lane.lock, "waited": round(waited, 1)}
                # The slow probe first, the git re-read last: the window between the
                # re-read and the lane's start stays as short as it can be.
                prerequisite = missing_prerequisite(lane)
                moved = _moved_since_start(top, sha, tree_sha, dirty, allow_dirty)
            if moved is None and prerequisite is None:
                print(f"  run   {lane.name:<14} {' '.join(lane.command)}", file=out, flush=True)
                code, secs = run_lane(lane, top, log_path)
        if moved is not None:
            # The whole check stops describing `sha`, so it fails whatever the lane's
            # advisory date, and no later lane runs on the moved tree under `sha`.
            why = f"{moved}, checked after lock {lane.lock!r} (waited {waited:.0f}s)"
            print(f"  FAIL  {lane.name:<14} {why}", file=out)
            receipts.write(
                repo,
                "lane",
                lane=lane.name,
                sha=sha,
                tree=tree_sha,
                exit=125,
                secs=0,
                why=why,
                dirty=bool(dirty),
                **lock_fields,
            )
            failed.append(lane.name)
            for rest in selected[index + 1 :]:
                print(f"  skip  {rest.name:<14} not run: the worktree moved", file=out)
            break
        if prerequisite is not None:
            print(f"  FAIL  {lane.name:<14} prerequisite: {prerequisite}", file=out)
            receipts.write(
                repo,
                "lane",
                lane=lane.name,
                sha=sha,
                tree=tree_sha,
                exit=125,
                secs=0,
                why=prerequisite,
                dirty=bool(dirty),
                **lock_fields,
            )
            (advisory_failed if lane.advisory() else failed).append(lane.name)
            continue
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
            **lock_fields,
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
        help="run lanes over uncommitted edits (no marker when the tree is dirty)",
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
