"""The `rails` command line. Every subcommand runs under PowerShell 5.1 and Git Bash.

rails check [--quick] [--post] [--lane X]   run the lanes the diff needs; seal a marker
rails post                                  post rails/<lane> statuses for HEAD
rails ship [--title T] [--closes N]         one PR, Ready, auto-squash armed, statuses posted
rails trunk run | watch | status            the full suite once on the base tip after merges; bisect, revert
rails walk [--name planted]                 run a walk; record step ids pass/fail
rails claim "#12,#34" | --milestone T [--kind release|harness|prep] | --adhoc "line" | --list | --release
rails work add "<text>" [--step a1] | from-issue <N> | done <id> | list | stop <kind> "<text>" | monitor-bound
rails hold | release | used <#milestone> <task> | approve <rulebook> <hash>   (the operator's words)
rails review record --coop F --adversary F | status   seal the two reviewers' reports for HEAD's tree
rails close <milestone number>              close a milestone the operator used (no open issues)
rails template [name] [--path]              the one template set: intent, spec, adr, milestone, rulebook, PR
rails retire-hook <path>                    replace a hook script with a dated do-nothing placeholder
rails leak-check [--file F] [--stdin] [--pre-push]
rails snapshot [--store S]... [--remember]  operator shell only: hash the household's values
rails metrics                               the four numbers before/since the cut, CI minutes, firings
rails history retire <tip> | status         refuse pushes of history the repo rewrote away
rails sync [--now]                          fast-forward the main checkout to trunk, when it is safe
rails receipt -- <command...>               run a command, record a sealed receipt of what it printed
rails lock <name> -- <command...>           run a command holding a lane's machine-wide lock (waits for it)
rails whereis <term>                        search code, branches, PRs and issues before "we'd need to build X"
rails state                                 what SessionStart prints
rails new <app> [--dest DIR]                the starter kit
rails adopt [--retire-push-consent]         wire this repo's git hooks to rails
rails enable                                operator, once per machine
rails doctor                                is everything wired?
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rails import VERSION, store


def _repo_or_die() -> store.RepoId:
    repo = store.find_repo(Path.cwd())
    if repo is None:
        print("rails: not inside a git checkout")
        raise SystemExit(2)
    return repo


def cmd_claim(argv: list[str]) -> int:
    from rails import claims
    from rails.gitutil import branch

    ap = argparse.ArgumentParser(prog="rails claim")
    ap.add_argument("items", nargs="?", default="")
    ap.add_argument("--milestone", default="")
    ap.add_argument("--kind", default="", choices=["", *claims.KINDS])
    ap.add_argument("--adhoc", default="")
    ap.add_argument("--wip-override", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args(argv)
    repo = _repo_or_die()
    if args.list:
        for c in claims.load(repo):
            marker = "  <- this worktree" if c.leaf == repo.leaf else ""
            kind = f" [{c.kind}]" if c.kind else ""
            print(
                f"{c.leaf}{kind} ({c.branch}) at {c.at}{marker}\n    {', '.join(c.items)}"
            )
        return 0
    if args.release:
        print(claims.release(repo))
        return 0
    items = [i for i in args.items.split(",") if i.strip()]
    kind = args.kind
    if args.milestone:
        items.append(args.milestone)
        kind = kind or "release"
    if args.adhoc:
        items.append(f"adhoc: {args.adhoc}")
        kind = kind or "adhoc"
    if not items:
        ap.error("name what you are taking")
    ok, message = claims.add(
        repo,
        branch(repo.top),
        items,
        kind=kind,
        adhoc=args.adhoc,
        wip_override=args.wip_override,
    )
    print(message)
    return 0 if ok else 1


def cmd_work(argv: list[str]) -> int:
    from rails import work

    repo = _repo_or_die()
    if not argv or argv[0] == "list":
        data = work.load(repo)
        for item in data["items"]:
            print(
                f"{item['id']:<6} {item['status']:<11} {item.get('step') or '-':<6} {item['text']}"
            )
        if data.get("stop_reason"):
            print(
                f"stop_reason: {data['stop_reason']['kind']}: {data['stop_reason']['text']}"
            )
        return 0
    verb, rest = argv[0], argv[1:]
    if verb == "add":
        ap = argparse.ArgumentParser(prog="rails work add")
        ap.add_argument("text")
        ap.add_argument("--step", default="")
        a = ap.parse_args(rest)
        item = work.add(repo, a.text, a.step)
        print(f"added {item['id']}")
        return 0
    if verb == "done" and rest:
        ok, message = work.mark_done(repo, rest[0])
        print(message)
        return 0 if ok else 1
    if verb == "stop" and len(rest) >= 2:
        ok, message = work.set_stop_reason(repo, rest[0], " ".join(rest[1:]))
        print(message)
        return 0 if ok else 1
    if verb == "monitor-bound":
        with store.updating(repo.leaf_dir / "pr.json", {}) as pr:
            pr["monitor"] = "bound"
        print("monitor recorded as bound")
        return 0
    if verb == "from-issue" and rest:
        from rails.gitutil import GitError, gh

        number = rest[0].lstrip("#")
        try:
            body = json.loads(gh(repo.top, "issue", "view", number, "--json", "body")).get("body", "")
        except (GitError, ValueError) as exc:
            print(f"rails work from-issue: cannot read #{number}: {exc}")
            return 2
        added = work.add_from_issue(repo, number, body)
        for item in added:
            print(f"added {item['id']:<10} step {item.get('step') or '-':<6} {item['text'][:90]}")
        if not added:
            print(f"#{number}: no new acceptance lines (none under a Done-when/Acceptance/Steps heading, no `step:` ids)")
        return 0
    print(__doc__)
    return 2


def cmd_template(argv: list[str]) -> int:
    """The plugin's templates are the one set: print one, or list them."""
    folder = Path(__file__).resolve().parent.parent / "templates"
    names = sorted(p.stem for p in folder.glob("*.md"))
    if not argv:
        print(f"rails templates ({folder}):")
        for name in names:
            first = next(
                (l.strip() for l in (folder / f"{name}.md").read_text(encoding="utf-8").splitlines() if l.strip()),
                "",
            )
            print(f"  {name:<24} {first[:80]}")
        print("print one: rails template <name>   (its path: rails template <name> --path)")
        return 0
    name = argv[0].removesuffix(".md")
    path = folder / f"{name}.md"
    if not path.is_file():
        print(f"rails template: no {name!r}; have: {', '.join(names)}")
        return 2
    print(path if "--path" in argv[1:] else path.read_text(encoding="utf-8"), end="" if "--path" not in argv[1:] else "\n")
    return 0


def cmd_retire_hook(argv: list[str]) -> int:
    from rails import structural

    if not argv:
        print("rails retire-hook <path of the hook script, relative to the repo root>")
        return 2
    repo = _repo_or_die()
    code, text = structural.retire_hook(repo.top, argv[0])
    print(text)
    return code


_OPERATOR_WORDS = ("used", "approve", "release")


def cmd_words(word: str, argv: list[str]) -> int:
    """The operator's words from a shell. Recorded `by: shell`, and weaker than the prompt's.

    Nothing a command line carries tells the operator's terminal from an agent's tool call:
    `CLAUDECODE` can be cleared by the agent's own command, and stdin reports a TTY inside an
    agent's Bash and PowerShell calls on Windows (measured 2026-10-08). So `rails close`
    honours only a `used` the operator typed in a prompt, and a hold set in a prompt is
    lifted only by `release` in a prompt (review of 1.3.0).
    """
    from rails.gitutil import in_agent

    if word in _OPERATOR_WORDS and in_agent():
        print(
            f"rails {word} is the operator's word: they type `{word} ...` in a prompt. An agent recording it "
            "would forge the receipt it exists to be."
        )
        return 2
    repo = _repo_or_die()
    now = int(time.time())
    with store.updating(repo.dir / "state.json", {}) as state:
        if word == "hold":
            current = state.get("hold") if isinstance(state.get("hold"), dict) else {}
            if current.get("on") and current.get("by") == "prompt":
                print("rails: hold already on (set in a prompt)")
                return 0
            state["hold"] = {
                "on": True,
                "since": time.strftime("%Y-%m-%d %H:%M"),
                "by": "shell",
            }
        elif word == "release":
            hold = state.get("hold") if isinstance(state.get("hold"), dict) else {}
            if hold.get("on") and hold.get("by") == "prompt":
                print("rails: the hold was set in a prompt; the operator lifts it with `release` in a prompt")
                return 2
            state["hold"] = {"on": False, "since": "", "lifted": now, "by": "shell"}
        elif word == "used":
            # `#75` is a comment in both shells, so the number is typed bare here.
            if not argv or not argv[0].lstrip("#").isdigit():
                print("rails used <milestone number> <task>   e.g. rails used 75 filed a real claim")
                return 2
            state.setdefault("used", []).append(
                {"milestone": "#" + argv[0].lstrip("#"), "task": " ".join(argv[1:])[:200], "at": now, "by": "shell"}
            )
        elif word == "approve":
            if len(argv) != 2:
                print("rails approve <rulebook> <examples_hash>")
                return 2
            state.setdefault("approved", {})[argv[0]] = {"hash": argv[1], "at": now, "by": "shell"}
    print(f"rails: {word} recorded")
    return 0


def cmd_walk(argv: list[str]) -> int:
    import tomllib

    from rails import receipts, work
    from rails.check import find_lanes_file
    from rails.gitutil import head

    ap = argparse.ArgumentParser(prog="rails walk")
    ap.add_argument("--name", default="planted")
    args = ap.parse_args(argv)
    repo = _repo_or_die()
    from rails.gitutil import dirty_tracked

    if dirty_tracked(repo.top):
        # The receipt names HEAD's tree; a walk over uncommitted edits walked another one.
        print("rails walk: commit first - the receipt names HEAD's tree, and the working copy differs")
        return 2
    lanes_file = find_lanes_file(repo.top)
    walks = (
        tomllib.loads(lanes_file.read_text(encoding="utf-8")).get("walk", [])
        if lanes_file
        else []
    )
    spec = next((w for w in walks if w.get("name") == args.name), None)
    if spec is None:
        print(f"rails walk: no [[walk]] named {args.name!r} in the lanes file")
        return 2
    private = bool(spec.get("private"))
    log_dir = repo.leaf_dir / ("evidence" if private else "logs") / "walk"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = log_dir / f"{args.name}-{int(time.time())}.log"
    argv0 = shutil.which(spec["command"][0]) or spec["command"][0]
    env = dict(os.environ)
    env.update({str(k): str(v) for k, v in spec.get("env", {}).items()})
    done = subprocess.run(
        [argv0, *spec["command"][1:]],
        cwd=str(repo.top),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    log.write_text(done.stdout + "\n--- stderr ---\n" + done.stderr, encoding="utf-8")
    steps = []
    for line in reversed(done.stdout.strip().splitlines()):
        try:
            body = json.loads(line)
        except ValueError:
            continue
        if isinstance(body, dict) and "steps" in body:
            steps = body["steps"]
            break
    row = receipts.write(
        repo,
        "walk",
        name=args.name,
        sha=head(repo.top),
        **work.walk_scope(repo),
        instrument=spec.get("instrument", f"walk:{args.name}"),
        steps=[
            {"step": str(s.get("step")), "pass": bool(s.get("pass"))}
            for s in steps
            if isinstance(s, dict)
        ],
        exit=done.returncode,
    )
    for s in row["steps"]:
        print(f"  {'pass' if s['pass'] else 'FAIL'}  {s['step']}")
    where = "(evidence folder: the agent may not read it)" if private else str(log)
    print(
        f"rails walk {args.name}: exit {done.returncode}; {len(row['steps'])} step(s); log {where}"
    )
    return 0 if done.returncode == 0 else 1


def cmd_receipt(argv: list[str]) -> int:
    from rails import receipts

    if argv and argv[0] == "--":
        argv = argv[1:]
    if not argv:
        print("rails receipt -- <command...>")
        return 2
    repo = _repo_or_die()
    argv0 = shutil.which(argv[0]) or argv[0]
    done = subprocess.run(
        [argv0, *argv[1:]],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sys.stdout.write(done.stdout)
    sys.stderr.write(done.stderr)
    row = receipts.write(
        repo,
        "receipt",
        cmd=" ".join(argv)[:400],
        cmd_sha256=hashlib.sha256(" ".join(argv).encode()).hexdigest(),
        exit=done.returncode,
        stdout_sha256=hashlib.sha256(done.stdout.encode()).hexdigest(),
        identity=os.environ.get("USERNAME") or os.environ.get("USER") or "?",
    )
    print(f"\nreceipt: {row['hmac'][:12]} (exit {done.returncode})")
    return done.returncode


def _start_tied(argv: list[str], env: dict[str, str]) -> tuple[subprocess.Popen, bool]:
    """Start the command; on Windows, inside a job object the OS closes when this process
    exits, however it exits, killing every process in it. The OS frees the machine lock then
    too, and a suite must not run on without it. The command starts suspended, is put in the
    job, then resumed, so nothing it starts (a launcher's interpreter, xdist's workers) is
    born outside. Joining this process to the job and letting the command inherit it is not
    enough: under the Microsoft Store Python, a joined process's children were outside the
    job (measured, 2026-10-19). One thing no job holds: a Store-packaged interpreter the
    command starts (a venv built on the Store Python), which Windows activates outside any
    job. Returns the process and whether it is tied; never tied elsewhere.
    """
    if os.name != "nt":
        return subprocess.Popen(argv, env=env), False
    import ctypes
    from ctypes import wintypes

    class _Basic(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _Extended(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _Basic),
            ("IoInfo", ctypes.c_ulonglong * 6),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    job = kernel32.CreateJobObjectW(None, None)
    info = _Extended()
    # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, and no breakaway: a venv's launcher gives the
    # interpreter a job of its own whose children break away silently, and they leave every
    # job up the chain that permits breakaway. So `rails lock -- rails ship` loses its
    # detached trunk runner when rails lock exits.
    info.BasicLimitInformation.LimitFlags = 0x2000
    if not job or not kernel32.SetInformationJobObject(
        job, 9, ctypes.byref(info), ctypes.sizeof(info)  # JobObjectExtendedLimitInformation
    ):
        if job:
            kernel32.CloseHandle(job)
        return subprocess.Popen(argv, env=env), False
    proc = subprocess.Popen(argv, env=env, creationflags=0x4)  # CREATE_SUSPENDED
    handle = int(proc._handle)  # type: ignore[attr-defined]
    tied = bool(kernel32.AssignProcessToJobObject(job, handle))
    if ntdll.NtResumeProcess(handle) != 0:
        proc.kill()
        proc.wait()
        raise OSError("could not resume the command after starting it suspended")
    if not tied:
        kernel32.CloseHandle(job)
    # A tied job's handle stays open until this process exits: that is the point.
    return proc, tied


def cmd_lock(argv: list[str]) -> int:
    """Run a command while holding the machine lock `name`: the one `rails check` takes for
    a lane that names it (`lock = "suite"`), so a suite started by hand queues with the
    lanes instead of loading the box beside them (the `heavy_pytest` gate's remedy).

    The wait has no timeout and is printed, with who holds the lock, to stderr; the
    command's own output and exit code are passed through. The command runs with
    ``RAILS_LOCKS_HELD`` naming the lock and this process, so a `rails check` or `rails lock`
    under it re-enters the lock instead of waiting for its own parent. It cannot outlive the
    lock: Ctrl+C stops its process tree, and on Windows a job object kills the tree when
    this process dies any other way (the OS frees the lock then too).
    """
    from rails import check
    from rails.lanes import valid_lock_name

    usage = "rails lock <name> -- <command...>   e.g. rails lock suite -- uv run pytest apps/ -q"
    if not argv or argv[0] in ("-h", "--help"):
        print(usage)
        return 2
    name, command = argv[0], argv[1:]
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        print(usage)
        return 2
    if not valid_lock_name(name):
        print(f"rails lock: {name!r} is not a lock name (a plain word, as in `lock = \"suite\"`)")
        return 2
    repo = store.find_repo(Path.cwd())
    sha = ""
    if repo is not None:
        done = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo.top), capture_output=True, text=True
        )
        sha = done.stdout.strip() if done.returncode == 0 else ""
    shown = " ".join(command)
    holder = {
        "repo": str(repo.main) if repo else str(Path.cwd()),
        "leaf": repo.leaf if repo else Path.cwd().name,
        "lane": f"rails lock: {shown[:80]}",
        "sha": sha,
    }

    def note(who: object, waited: float) -> None:
        text = "another process"
        if isinstance(who, dict):
            since = "?"
            stamp = who.get("since")
            if isinstance(stamp, (int, float)):
                since = time.strftime("%H:%M", time.localtime(stamp))
            text = (
                f"{who.get('leaf', '?')} ({who.get('lane', '?')} at "
                f"{str(who.get('sha', ''))[:12]}) since {since}"
            )
        print(
            f"rails lock: wait  lock {name!r} held by {text}; waited {waited / 60:.0f} min",
            file=sys.stderr,
            flush=True,
        )

    with store.machine_lock(name, holder, on_wait=note) as waited:
        if waited >= 1:
            print(f"rails lock: took {name!r} after {waited / 60:.0f} min", file=sys.stderr, flush=True)
        holder_path = store.data_root() / "locks" / f"{name}.holder.json"
        record = store.read_json(holder_path, None)
        mine = isinstance(record, dict) and record.get("pid") == os.getpid()
        # Re-entered (nested under a holder that named it): the record is the holder's.
        if not mine and not store._held_for_us(name, holder_path):
            print(
                f"rails lock: could not write the holder record for {name!r}; a `rails check` "
                "or `rails lock` under this command will wait for it instead of re-entering",
                file=sys.stderr,
                flush=True,
            )
        child_env = dict(os.environ)
        child_env[store.HELD_ENV] = store.held_env([name], child_env)
        try:
            proc, tied = _start_tied(check._resolve(command), child_env)
        except OSError as exc:
            print(f"rails lock: could not start {command[0]!r}: {exc}", file=sys.stderr)
            return 127
        try:
            if os.name == "nt" and not tied:
                print(
                    "rails lock: Windows refused the job object; if this process is killed, "
                    "the command runs on without the lock",
                    file=sys.stderr,
                    flush=True,
                )
            while True:
                # In slices: Windows does not interrupt an infinite wait for Ctrl+C.
                try:
                    return proc.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    continue
        except BaseException:
            # The lock goes when this block exits: whatever the command started must not
            # run on without it.
            check._kill_tree(proc)
            raise


def cmd_whereis(argv: list[str]) -> int:
    if not argv:
        print("rails whereis <term>")
        return 2
    term = " ".join(argv)
    repo = _repo_or_die()
    print(f"rails whereis {term!r}")
    grep = subprocess.run(
        ["git", "-C", str(repo.top), "grep", "-I", "-i", "-l", "-F", term],
        capture_output=True,
        text=True,
    )
    files = grep.stdout.split()
    print(
        f"  code/docs: {len(files)} file(s)" + "".join(f"\n    {f}" for f in files[:15])
    )
    branches = subprocess.run(
        [
            "git",
            "-C",
            str(repo.top),
            "branch",
            "-a",
            "--list",
            f"*{term.replace(' ', '*')}*",
        ],
        capture_output=True,
        text=True,
    ).stdout.split()
    print(
        f"  branches: {len(branches)}"
        + "".join(f"\n    {b}" for b in branches[:10] if b != "*")
    )
    if shutil.which("gh"):
        for kind in ("pr", "issue"):
            out = subprocess.run(
                [
                    "gh",
                    kind,
                    "list",
                    "--state",
                    "all",
                    "--search",
                    term,
                    "--limit",
                    "10",
                    "--json",
                    "number,title,state",
                ],
                cwd=str(repo.top),
                capture_output=True,
                text=True,
            )
            try:
                rows = json.loads(out.stdout or "[]")
            except ValueError:
                rows = []
            label = "PRs" if kind == "pr" else "issues"
            if out.returncode != 0:
                print(f"  {label}: could not look (gh exited {out.returncode})")
                continue
            print(
                f"  {label}: {len(rows)}"
                + "".join(
                    f"\n    #{r['number']} [{r['state']}] {r['title'][:90]}"
                    for r in rows
                )
            )
    print("  A negative is scoped to these sources; say so when you report it.")
    return 0


def _doctor_history(repo: store.RepoId) -> int:
    """Retired history and the main folder; returns the number of problems found."""
    from rails import history, mainsync

    problems = 0
    retired = history.load(repo.top)
    if retired is None:
        print("  retired history: none recorded")
    elif retired.problems:
        print(f"  retired history: CANNOT CHECK - {retired.problems[0]} (pushes refuse)")
        problems += 1
    else:
        found = history.carriers(retired)
        print(
            f"  retired history: {len(retired.tips)} tip(s), {len(retired.commits)} commits not on {retired.trunk}; "
            f"{len(found)} worktree(s) carry it (their pushes refuse)"
        )
        for path, branch, head in found:
            print(f"    {path.name}  {branch}  {head[:12]}")
    p = mainsync.plan(repo, manual=True)
    if p.act:
        print(f"  main folder: {p.behind} behind trunk - `rails sync` fast-forwards it")
    else:
        print(f"  main folder: {p.line or 'at trunk'}")
        problems += 1 if p.line else 0
    return problems


def cmd_doctor(argv: list[str]) -> int:
    from rails.check import find_lanes_file

    problems = 0
    print(f"rails {VERSION} at {Path(__file__).resolve().parent.parent}")
    print(f"  python {sys.version.split()[0]}")
    hb = store.data_root() / "heartbeat"
    if hb.exists():
        age = time.time() - hb.stat().st_mtime
        print(f"  plugin heartbeat: {age / 3600:.1f} h ago")
    else:
        print(
            "  plugin heartbeat: none (the plugin's hooks have never run on this machine)"
        )
        problems += 1
    repo = store.find_repo(Path.cwd())
    if repo:
        hooks = subprocess.run(
            ["git", "-C", str(repo.top), "config", "--get", "core.hooksPath"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        wired = (
            hooks
            and Path(hooks).resolve()
            == (Path(__file__).resolve().parent.parent / "git-hooks").resolve()
        )
        print(
            f"  git hooks: {'rails' if wired else (hooks or 'default')}"
            + ("" if wired else "  -> run `rails adopt`")
        )
        problems += 0 if wired else 1
        lanes = find_lanes_file(repo.top)
        print(f"  lanes file: {lanes or 'MISSING'}")
        problems += 0 if lanes else 1
        problems += _doctor_history(repo)
    for tool in ("git", "gh", "uv", "node", "pnpm", "docker"):
        print(f"  {tool}: {'ok' if shutil.which(tool) else 'not on PATH'}")
    return 1 if problems else 0


#: How often a rails command re-reads an OPEN pr.json's state from GitHub.
PR_STATE_TTL_SECS = 60


def refresh_pr_state(cwd: Path, now: float | None = None) -> str | None:
    """p3g: a worktree's ``pr.json`` that still reads OPEN after its PR merged or closed made
    every gate that reads it (second_pr, turn_end, the push marker) act on a PR that is gone.
    Any rails command re-reads the state from GitHub, at most once a minute, and records what
    it found. Returns the new state when it changed; None otherwise, or when it cannot ask."""
    from rails.gitutil import GitError, gh

    repo = store.find_repo(cwd)
    if repo is None:
        return None
    path = repo.leaf_dir / "pr.json"
    pr = store.read_json(path, None)
    if not isinstance(pr, dict) or not pr.get("number"):
        return None
    if str(pr.get("state", "OPEN")).upper() != "OPEN":
        return None
    now = time.time() if now is None else now
    if now - float(pr.get("state_checked_at", 0) or 0) < PR_STATE_TTL_SECS:
        return None
    try:
        view = gh(repo.top, "pr", "view", str(pr["number"]), "--json", "state", check=False, timeout=10)
        state = str(json.loads(view).get("state", "")).upper() if view.strip() else ""
    except (GitError, ValueError, OSError):
        state = ""
    if not state:
        # Remembered, so a hung or offline gh costs one wait a minute, not one per command.
        with store.updating(path, {}) as record:
            record["state_checked_at"] = now
        return None
    # `store.updating` holds the lock `arm_review._stamp_armed` and `turn_end` take.
    with store.updating(path, {}) as record:
        record["state_checked_at"] = now
        if state != "OPEN":
            record["state"] = state
            # The arm is this record's own only when it named this number (or predates
            # `armed_pr`), as `turn_end._settled` reads it: a hand arm of #6 stamped onto #5's
            # record stays armed after #5 leaves OPEN.
            if "armed_pr" not in record or str(record.get("armed_pr")) == str(record.get("number")):
                record["armed"] = False
                record.pop("disarmed_by", None)
            from rails.githooks import release_pr_hold

            release_pr_hold(repo, record.get("number"))
    return state if state != "OPEN" else None


def main(argv: list[str]) -> int:
    # A lane's output carries characters a cp1252 console or a redirected stdout cannot
    # encode; printing its tail must never cost the lanes after it (1.4.0's crash).
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            pass
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd not in ("--version",):
        try:
            changed = refresh_pr_state(Path.cwd())
        except Exception:  # noqa: BLE001 - a state refresh never blocks a command
            changed = None
        if changed:
            print(f"rails: this worktree's PR is {changed} now; pr.json no longer reads OPEN")
    if cmd == "--version":
        print(VERSION)
        return 0
    if cmd == "check":
        from rails import check

        return check.main(rest)
    if cmd == "post":
        from rails import check

        return check.post(Path.cwd())
    if cmd == "ship":
        from rails import ship

        return ship.main(rest)
    if cmd == "trunk":
        from rails import trunk

        return trunk.main(rest)
    if cmd == "walk":
        return cmd_walk(rest)
    if cmd == "claim":
        return cmd_claim(rest)
    if cmd == "work":
        return cmd_work(rest)
    if cmd in ("hold", "release", "used", "approve"):
        return cmd_words(cmd, rest)
    if cmd == "leak-check":
        from rails import leak

        return leak.main(rest)
    if cmd == "snapshot":
        from rails import leak

        repo = _repo_or_die()
        return leak.snapshot_main(repo.top, repo, argv=rest)
    if cmd == "metrics":
        from rails import metrics

        return metrics.main(rest)
    if cmd == "template":
        return cmd_template(rest)
    if cmd == "retire-hook":
        return cmd_retire_hook(rest)
    if cmd == "review":
        from rails import review

        return review.main(rest)
    if cmd == "close":
        from rails import close

        if not rest:
            print("rails close <milestone number>")
            return 2
        code, text = close.close(Path.cwd(), rest[0])
        print(text)
        return code
    if cmd == "history":
        from rails import history

        return history.main(rest)
    if cmd == "sync":
        from rails import mainsync

        return mainsync.main(rest)
    if cmd == "receipt":
        return cmd_receipt(rest)
    if cmd == "lock":
        return cmd_lock(rest)
    if cmd == "whereis":
        return cmd_whereis(rest)
    if cmd == "state":
        from rails.gates.state import lines_of_work, render

        repo = _repo_or_die()
        print(render(repo))
        print()
        print("lines of work (every worktree):")
        for line in lines_of_work(repo):
            print(f"  {line}")
        return 0
    if cmd == "new":
        from rails import new

        return new.main(rest)
    if cmd in ("adopt", "enable"):
        from rails import adopt

        return adopt.main(rest, command=cmd)
    if cmd == "doctor":
        return cmd_doctor(rest)
    print(f"rails: unknown command {cmd!r}\n")
    print(__doc__)
    return 2
