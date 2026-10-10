"""`rails ship`: one PR per worktree, Ready, auto-squash armed, statuses posted (design R27).

    rails ship [--title T] [--body-file F] [--base B] [--closes 123 --closes 456]
               [--detected-by ci|lane|hook|walk|boot|review|audit|operator|agent]

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
from rails.numbers import DETECTED_BY
from rails.gitutil import GitError, branch, dirty_tracked, gh, gh_api, head, origin_slug, toplevel


def _intent_title_body(top: Path) -> tuple[str, str]:
    from rails.intent import read_any

    text = (read_any(top / ".rails" / "intent.md") or "").strip()
    if not text:
        return "", ""
    lines = text.splitlines()
    title = ""
    for i, line in enumerate(lines):
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            lines = lines[i + 1 :]
            break
    return title, "\n".join(lines).strip()


#: A claim that something is ABSENT from the code - the kind a grep can get wrong (design
#: R29) - not every sentence with "no" or "only" in it. 1.0's word list flagged ordinary
#: prose ("no code", "the only lane") on every PR it shipped, which trains the reader to
#: skip the advisory.
_ABSENCE = re.compile(
    r"\b(?:does not exist|doesn'?t exist|is not (?:implemented|wired|called|used)|"
    r"(?:no|zero) (?:\w+ ){0,2}(?:callers?|consumers?|importers?|references?|readers?|writers?|"
    r"tests? (?:for|of|cover)|usages?|uses)\b|"
    r"never (?:called|used|read|written|imported|reached|wired)|"
    r"nothing (?:calls|reads|uses|writes|imports|references)|"
    r"(?:is|are) (?:missing|absent) from)",
    re.IGNORECASE,
)


def _import_acceptance(repo: store.RepoId, top: Path, number: str, out) -> None:
    """`--closes N` turns N's acceptance lines into work items (design R28), once.

    The turn-end gate then holds the PR to them: an armed PR may not close an item whose
    step has no passing walk receipt. Best effort - an unreadable issue is said, not fatal.
    """
    ref = f"#{number.lstrip('#')}"
    if any(i.get("closes") == ref and i.get("from_issue") for i in work.load(repo)["items"]):
        return
    try:
        raw = gh(top, "issue", "view", ref.lstrip("#"), "--json", "body").strip()
        body = json.loads(raw).get("body", "") if raw else ""
    except (GitError, ValueError) as exc:
        print(f"  work: could not read {ref} ({str(exc)[:80]}); its Done-when lines are NOT items", file=out)
        return
    added = work.add_from_issue(repo, ref, body) if body else []
    print(
        f"  work: {len(added)} acceptance line(s) from {ref} are now items"
        + ("" if added else " (the issue has no Done-when section or `step:` lines)"),
        file=out,
    )


_CODE_SUFFIXES = (".py", ".ps1", ".sh", ".cmd", ".bat", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".toml", ".yml", ".yaml")


def is_prose(path: str) -> bool:
    """Prose a reviewer need not read: docs/ that is not code, and README / CHANGELOG / LICENSE.

    Everything else is behaviour: agents/*.md and skills/*/SKILL.md are prompts that run,
    CLAUDE.md / AGENTS.md (at any depth) are the instructions every session obeys,
    templates/*.md are the shapes every artifact takes, and a script under docs/ is code
    (review of 1.3.0).
    """
    name = path.rsplit("/", 1)[-1].upper()
    if name in ("CLAUDE.MD", "AGENTS.MD"):
        return False
    if path.startswith("docs/"):
        return not path.endswith(_CODE_SUFFIXES)
    return "/" not in path and name.startswith(("README", "CHANGELOG", "LICENSE"))


def needs_review(top: Path, base_ref: str | None, rev: str = "HEAD") -> bool:
    """A diff that changes anything but prose gets the two-voice review. ``rev`` is the commit
    judged: HEAD for ship and arming, the pushed sha at pre-push (review of 1.3.0)."""
    from rails.check import find_lanes_file
    from rails import lanes as lanes_mod
    from rails.gitutil import changed_files, merge_base

    if not base_ref:
        lanes_file = find_lanes_file(top)
        base_ref = lanes_mod.load(lanes_file).base if lanes_file else None
    base_sha = None
    for ref in (base_ref, "origin/HEAD", "origin/main", "origin/master"):
        if ref and (base_sha := merge_base(top, ref, rev)):
            break
    if not base_sha:
        return True
    return any(not is_prose(p) for p in changed_files(top, base_sha, rev))


def _review_allows_arming(repo: store.RepoId, top: Path, out, base_ref: str | None = None) -> bool:
    """`ship_review`: a code diff arms only with a review of HEAD's tree and no open must-fix (R26)."""
    from rails import review
    from rails.githooks import _log, _shadowed
    from rails.gitutil import tree

    if not needs_review(top, base_ref):
        return True
    text = review.arming_problem(review.covering(repo, top, "HEAD"))
    if text is None:
        return True
    if _shadowed("ship_review"):
        _log(repo, "ship_review", "would-deny")
        print(f"  [rails shadow: ship_review would refuse to arm] {text}", file=out)
        return True
    print(f"rails ship: {text}", file=out)
    return False


def unreceipted_absences(body: str) -> list[str]:
    """Lines that claim an absence without naming the receipt that looked (design R29)."""
    return [
        line.strip()
        for line in body.splitlines()
        if _ABSENCE.search(line)
        and "receipt:" not in line
        and not line.strip().startswith(("Closes", "<!--"))
    ]


def compose_body(
    body: str,
    closes: list[str],
    repo: store.RepoId,
    sha: str,
    detected_by: str | None = None,
) -> str:
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
    try:
        from rails import review
        from rails.gitutil import tree, toplevel

        line = review.summary_line(review.covering(repo, toplevel(repo.top), "HEAD"))
    except Exception:  # noqa: BLE001 - the body must not fail to compose over a summary line
        line = ""
    if line:
        parts.append(line)
    if detected_by:
        # read back by `rails metrics` (the automation catch rate); one line, its own paragraph
        parts.append(f"Detected-by: {detected_by}")
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
    arm: bool = True,
    detected_by: str | None = None,
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
    # A re-ship of the same open PR rewrites its body; what the first ship said (Closes lines,
    # Detected-by, an explicit --body-file body) is carried, never dropped - but only onto that
    # PR: a merged one's lines must not leak into the next PR on a reused branch (1.3.0).
    closes = [str(c).lstrip("#") for c in closes]
    prev = store.read_json(repo.leaf_dir / "pr.json", None)
    if isinstance(prev, dict) and prev.get("number") and prev.get("branch") == branch(top):
        view = gh(top, "pr", "view", str(prev["number"]), "--json", "number,state", check=False).strip()
        try:
            info = json.loads(view) if view else {}
        except ValueError:
            info = {}
        if info.get("state") == "OPEN" and info.get("number") == prev.get("number"):
            closes = list(dict.fromkeys([*(str(c).lstrip("#") for c in prev.get("closes", [])), *closes]))
            detected_by = detected_by or prev.get("detected_by")
            body = body or str(prev.get("body", ""))
    explicit_body = body  # the intent's text is re-read on every ship, never frozen into pr.json
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
    for c in closes:
        _import_acceptance(repo, top, c, out)
    full_body = compose_body(body, closes, repo, sha, detected_by)
    if not detected_by and re.search(r"(?i)\b(fix|hotfix|bugfix)", title):
        print(
            "  advisory: this reads as a fix but has no --detected-by "
            f"({'|'.join(DETECTED_BY)}); `rails metrics` cannot count who caught it",
            file=out,
        )
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
            from rails.githooks import _log, _shadowed

            if _shadowed("leak_dispatch"):
                # The same 7-day shadow as the dispatcher's leak gate: log, do not refuse.
                _log(repo, "leak_dispatch", "would-deny")
                print("  [rails shadow: leak check would refuse] " + result.report().splitlines()[0], file=out)
            else:
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
        # Through the API with an ASCII-escaped JSON body, never argv: on Windows a
        # non-ASCII title passed as an argument arrives mangled (178 issues, 2026-09-26).
        slug = origin_slug(top)
        if slug is None:
            print("rails ship: origin is not a GitHub remote", file=out)
            return 2
        try:
            if not base:
                base = gh_api(top, f"repos/{slug}")["default_branch"]
            created = gh_api(
                top,
                f"repos/{slug}/pulls",
                method="POST",
                payload={"title": title, "head": br, "base": base, "body": full_body, "draft": False},
            )
        except (GitError, KeyError, TypeError) as exc:
            print(f"rails ship: creating the PR failed: {exc}", file=out)
            return 1
        number, url = created.get("number"), created.get("html_url", "")
    if number is None:
        print("rails ship: could not determine the PR number", file=out)
        return 1
    elif existing:
        # A re-ship (after `rails review record --accept`, or new commits) refreshes the body,
        # so the review line the operator judges by is the current one (review of 1.3.0).
        slug = origin_slug(top)
        try:
            if slug:
                gh_api(top, f"repos/{slug}/pulls/{number}", method="PATCH", payload={"body": full_body})
        except GitError as exc:
            print(f"  could not refresh the PR body: {exc}", file=out)
    armed = False
    if arm and not _review_allows_arming(repo, top, out, base):
        arm = False
        print("  not arming (the reason is above); `rails ship` again arms it once the review allows", file=out)
    if arm:
        done = subprocess.run(
            ["gh", "pr", "merge", str(number), "--auto", "--squash"],
            cwd=str(top),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        armed = done.returncode == 0
        if not armed:
            print(f"  could not arm auto-merge: {done.stderr.strip()[:300]}", file=out)
    store.write_json(
        repo.leaf_dir / "pr.json",
        {
            "number": number,
            "url": url,
            "branch": br,
            "state": "OPEN",
            "armed": armed,
            "sha": sha,
            "monitor": "unbound",
            "at": int(time.time()),
            "closes": closes,
            "detected_by": detected_by,
            "body": explicit_body,
        },
    )
    if len(closes) == 1:
        # Hand-added items (`rails work add`) belong to the one issue this PR closes; with
        # several, which item closes which is unknowable, so none is guessed (review of 1.3.0).
        with store.updating(work.path(repo), {}) as wdata:
            for item in wdata.get("items", []):
                if item.get("status") == "open" and not item.get("closes"):
                    item["closes"] = f"#{closes[0].lstrip('#')}"
    from rails.check import post

    post(top, out=out)
    receipts.write(repo, "ship", sha=sha, pr=number, armed=armed)
    # The full suite runs after merge: a trunk runner tests the base tip once this lands.
    try:
        from rails import trunk

        trunk.start_background(top, out=out)
    except Exception as exc:  # noqa: BLE001 - the PR is open and armed; this never fails ship
        print(f"  trunk: the runner could not be started ({type(exc).__name__}: {exc})", file=out)
    print(f"rails ship: PR #{number} {url}", file=out)
    if arm:
        print("  armed: auto-squash" if armed else "  NOT armed (see above)", file=out)
    else:
        print("  not armed (--no-arm): it waits for a named outside step; say which in the PR body", file=out)
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
    ap.add_argument("--no-arm", action="store_true", help="open it Ready but do not arm: it waits on an outside step")
    ap.add_argument(
        "--detected-by",
        choices=DETECTED_BY,
        default=None,
        help="for a fix: what found the defect first (written as `Detected-by:`; read by rails metrics)",
    )
    args = ap.parse_args(argv)
    body = Path(args.body_file).read_text(encoding="utf-8") if args.body_file else ""
    try:
        return ship(
            Path.cwd(),
            title=args.title,
            body=body,
            base=args.base,
            closes=args.closes,
            arm=not args.no_arm,
            detected_by=args.detected_by,
        )
    except GitError as exc:
        print(f"rails ship: {exc}")
        return 2
