"""`rails ship`: one PR per worktree, Ready, auto-squash armed, statuses posted (design R27).

    rails ship [--title T] [--body-file F] [--base B] [--closes 123 --closes 456]

1. HEAD must carry the FULL check marker (`rails check`) and the tree must be clean.
2. Refuses while work.json has `unverified` items and the PR would close issues.
3. Title and body: from the flags, else from ``.rails/intent.md`` (first heading =
   title, the rest = body). Every `Closes #N` gets its own line — `Closes #A, #B`
   closes only #A.
4. Leak-checks title and body (repos with rails/leak.toml) BEFORE any gh call.
5. Pushes the branch (through the pre-push hook), opens ONE Ready PR — or reuses
   the open one — arms `--auto --squash`, posts the lane statuses, writes pr.json.
6. Prints the monitor step: the desktop's ccd_pr bind_pr + set_monitor, then
   `rails work monitor-bound`.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from rails import leak, receipts, store, work
from rails.gitutil import GitError, branch, dirty_tracked, gh, head, toplevel


def _intent_title_body(top: Path) -> tuple[str, str]:
    path = top / ".rails" / "intent.md"
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return "", ""
    lines = text.splitlines()
    title = ""
    for i, line in enumerate(lines):
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            lines = lines[i + 1 :]
            break
    return title, "\n".join(lines).strip()


_ABSENCE = re.compile(
    r"\b(no|never|missing|does not exist|nothing|only)\b", re.IGNORECASE
)


def unreceipted_absences(body: str) -> list[str]:
    """Lines that claim an absence without naming the receipt that looked (design R29)."""
    return [
        line.strip()
        for line in body.splitlines()
        if _ABSENCE.search(line)
        and "receipt:" not in line
        and not line.strip().startswith(("Closes", "<!--"))
    ]


def compose_body(body: str, closes: list[str], repo: store.RepoId, sha: str) -> str:
    rows = [r for r in receipts.read(repo, "lane", sha=sha) if receipts.valid(r)]
    latest = receipts.latest_by(rows, "lane")
    lanes = ", ".join(
        f"{name} {'pass' if r.get('exit') == 0 else 'FAIL'} {int(r.get('secs', 0))}s"
        for name, r in sorted(latest.items())
    )
    parts = [body.strip()] if body.strip() else []
    if lanes:
        parts.append(
            f"**Local lanes at {sha[:12]}** (posted as `rails/<lane>` statuses): {lanes}"
        )
    for number in closes:
        parts.append(f"Closes #{number.lstrip('#')}")
    return "\n\n".join(parts) + "\n"


def ship(
    cwd: Path,
    *,
    title: str,
    body: str,
    base: str | None,
    closes: list[str],
    out=sys.stdout,
) -> int:
    repo = store.find_repo(cwd)
    if repo is None:
        print("rails ship: not inside a git checkout", file=out)
        return 2
    top = toplevel(cwd)
    if dirty_tracked(top):
        print("rails ship: commit first; a PR ships commits", file=out)
        return 2
    sha = head(top)
    if not receipts.has_marker(repo, sha, full=True):
        print(
            f"rails ship: no full check marker for {sha[:12]}. Run `rails check` on this commit first.",
            file=out,
        )
        return 1
    data = work.load(repo)
    unverified = [i["id"] for i in data["items"] if i.get("status") == "unverified"]
    if unverified and closes:
        print(
            f"rails ship: refusing to close issues while items are unverified: {', '.join(unverified)}",
            file=out,
        )
        return 1
    if not title:
        title, intent_body = _intent_title_body(top)
        body = body or intent_body
    if not title:
        print(
            "rails ship: no title (pass --title or write .rails/intent.md with a heading)",
            file=out,
        )
        return 2
    full_body = compose_body(body, closes, repo, sha)
    for line in unreceipted_absences(full_body):
        print(
            f"  advisory: an absence claim with no `receipt:` id: {line[:120]}",
            file=out,
        )
    if (top / "rails" / "leak.toml").is_file():
        result = leak.check_lines(
            repo,
            list(leak.text_lines("title", title))
            + list(leak.text_lines("body", full_body)),
            leak.allowlist_for(top),
        )
        if result.code != leak.EXIT_CLEAN:
            print("rails ship: refused - " + result.report(), file=out)
            return 1
    br = branch(top)
    if not br:
        print("rails ship: detached HEAD; ship from a branch", file=out)
        return 2
    push = subprocess.run(
        ["git", "push", "-u", "origin", f"HEAD:refs/heads/{br}"], cwd=str(top)
    )
    if push.returncode != 0:
        print("rails ship: push refused (see above)", file=out)
        return 1
    existing = gh(
        top, "pr", "view", br, "--json", "number,state,url", check=False
    ).strip()
    number, url = None, ""
    if existing:
        try:
            info = json.loads(existing)
            if info.get("state") == "OPEN":
                number, url = info["number"], info.get("url", "")
        except ValueError:
            pass
    if number is None:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8"
        ) as fh:
            fh.write(full_body)
            body_file = fh.name
        args = [
            "pr",
            "create",
            "--title",
            title,
            "--body-file",
            body_file,
            "--head",
            br,
        ]
        if base:
            args += ["--base", base]
        try:
            url = gh(top, *args).strip().splitlines()[-1]
        except GitError as exc:
            print(f"rails ship: gh pr create failed: {exc}", file=out)
            return 1
        m = re.search(r"/pull/(\d+)", url)
        number = int(m.group(1)) if m else None
    if number is None:
        print("rails ship: could not determine the PR number", file=out)
        return 1
    armed = gh(top, "pr", "merge", str(number), "--auto", "--squash", check=False)
    store.write_json(
        repo.leaf_dir / "pr.json",
        {
            "number": number,
            "url": url,
            "branch": br,
            "state": "OPEN",
            "armed": True,
            "sha": sha,
            "monitor": "unbound",
            "at": int(time.time()),
        },
    )
    for c in closes:
        with store.updating(work.path(repo), {}) as wdata:
            for item in wdata.get("items", []):
                if item.get("status") == "open" and not item.get("closes"):
                    item["closes"] = f"#{c.lstrip('#')}"
    from rails.check import post

    post(top, out=out)
    receipts.write(repo, "ship", sha=sha, pr=number)
    print(f"rails ship: PR #{number} {url}", file=out)
    print(
        "  armed: auto-squash" + ("" if armed is not None else " (could not confirm)"),
        file=out,
    )
    print(
        "  next: bind the monitor (ccd_pr bind_pr + set_monitor), then `rails work monitor-bound`",
        file=out,
    )
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="rails ship")
    ap.add_argument("--title", default="")
    ap.add_argument("--body-file", default="")
    ap.add_argument("--base", default=None)
    ap.add_argument("--closes", action="append", default=[])
    args = ap.parse_args(argv)
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else ""
    try:
        return ship(
            Path.cwd(), title=args.title, body=body, base=args.base, closes=args.closes
        )
    except GitError as exc:
        print(f"rails ship: {exc}")
        return 2
