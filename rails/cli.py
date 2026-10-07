"""The `rails` command line. Every subcommand runs under PowerShell 5.1 and Git Bash.

rails check [--quick] [--post] [--lane X]   run the lanes the diff needs; seal a marker
rails post                                  post rails/<lane> statuses for HEAD
rails ship [--title T] [--closes N]         one PR, Ready, auto-squash armed, statuses posted
rails walk [--name planted]                 run a walk; record step ids pass/fail
rails claim "#12,#34" | --milestone T [--kind release|harness|prep] | --adhoc "line" | --list | --release
rails work add "<text>" [--step a1] | done <id> | list | stop <kind> "<text>" | monitor-bound
rails hold | release | used <#milestone> <task> | approve <rulebook> <hash>   (the operator's words)
rails leak-check [--file F] [--stdin] [--pre-push]
rails snapshot                              operator shell only: hash the household's values
rails metrics                               the four numbers before/since the cut, CI minutes, firings
rails history retire <tip> | status         refuse pushes of history the repo rewrote away
rails sync [--now]                          fast-forward the main checkout to trunk, when it is safe
rails receipt -- <command...>               run a command, record a sealed receipt of what it printed
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
    print(__doc__)
    return 2


def cmd_words(word: str, argv: list[str]) -> int:
    repo = _repo_or_die()
    now = int(time.time())
    with store.updating(repo.dir / "state.json", {}) as state:
        if word == "hold":
            state["hold"] = {
                "on": True,
                "since": time.strftime("%Y-%m-%d %H:%M"),
                "by": "shell",
            }
        elif word == "release":
            state["hold"] = {"on": False, "since": "", "lifted": now}
        elif word == "used":
            if not argv:
                print("rails used <#milestone> <task>")
                return 2
            state.setdefault("used", []).append(
                {"milestone": argv[0], "task": " ".join(argv[1:])[:200], "at": now}
            )
        elif word == "approve":
            if len(argv) != 2:
                print("rails approve <rulebook> <examples_hash>")
                return 2
            state.setdefault("approved", {})[argv[0]] = {"hash": argv[1], "at": now}
    print(f"rails: {word} recorded")
    return 0


def cmd_walk(argv: list[str]) -> int:
    import tomllib

    from rails import receipts
    from rails.check import find_lanes_file
    from rails.gitutil import head, tree

    ap = argparse.ArgumentParser(prog="rails walk")
    ap.add_argument("--name", default="planted")
    args = ap.parse_args(argv)
    repo = _repo_or_die()
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
        tree=tree(repo.top),
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


def main(argv: list[str]) -> int:
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
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
        return leak.snapshot_main(repo.top, repo)
    if cmd == "metrics":
        from rails import metrics

        return metrics.main(rest)
    if cmd == "history":
        from rails import history

        return history.main(rest)
    if cmd == "sync":
        from rails import mainsync

        return mainsync.main(rest)
    if cmd == "receipt":
        return cmd_receipt(rest)
    if cmd == "whereis":
        return cmd_whereis(rest)
    if cmd == "state":
        from rails.gates.state import render

        print(render(_repo_or_die()))
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
