"""The review receipt (design R26): two isolated voices read the change before a PR may arm.

The voices are the plugin's agents, `rails:reviewer-coop` (steelman, then what must change)
and `rails:reviewer-adversary` (break it at its seams), run by the session as subagents
with nothing but the diff and the intent. Each writes its report to a file; then

    rails review record --coop <file> --adversary <file>

seals a ``review`` receipt for HEAD's tree: both reports' sha256, their must-fix counts,
and the tree they read. `rails ship` looks for a receipt whose tree is HEAD's before it
arms auto-merge (registry row ``ship_review``). A later commit changes the tree, so a
review of an older tree does not count: re-run the voices on what will actually merge.

What it does not prove: that the voices were independent or read carefully. The receipt
makes the review exist and be tied to the exact tree; its quality is the operator's to
judge from the PR body, where the counts are printed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from rails import receipts, store
from rails.intent import read_any
from rails.gitutil import dirty_tracked, head, toplevel, tree

_MUST_FIX = re.compile(r"(?i)^\s*(?:[-*]\s*|\d+[.)]\s*)?(?:\*\*)?must[- _]fix\b")
_MUST_FIX_HEADING = re.compile(r"(?i)^\s*#{1,6}\s*(?:\*\*)?must[- _]fix")
_HEADING = re.compile(r"^\s*#{1,6}\s")
_ITEM = re.compile(r"^\s*(?:(?:[-*+]|\d+[.)])\s+\S|\*\*\d+[.)])")
#: "Must-fix: none", "- None", "**Must-fix:** n/a" - an empty list said in words.
_NONE = re.compile(r"(?i)^\s*(?:[-*+]\s*|\d+[.)]\s*)?(?:\*\*)?(?:must[- _]fix\W*)?(?:none|n/?a|nothing)\b\W*$")
_JSON_KEY = re.compile(r"[\"']must_fix[\"']\s*:")


def _json_report(text: str) -> dict | None:
    """The reviewers' own format (agents/reviewer-*.md): a JSON object with ``must_fix``.

    Found wherever it sits: the object is decoded from each ``{`` in turn, so a brace in
    the prose around it (``${N}``) no longer makes the whole report unparsable, which used
    to fall through to a count of 0 (review of 1.3.0).
    """
    decoder = json.JSONDecoder()
    first, last = None, None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, dict):
            if isinstance(obj.get("must_fix"), list):
                last = obj  # the reviewer's own object comes last; a quoted one comes before it
            first = first if first is not None else obj
    return last if last is not None else first


def must_fix_count(text: str) -> int | None:
    """Open must-fix items in a report; None when it cannot be counted (never a silent 0).

    The JSON report's ``must_fix`` list when one parses. A report that names a
    ``must_fix`` key but whose JSON does not parse is uncountable. Otherwise Markdown: items
    under a ``## Must-fix`` heading, and lines that start with "must-fix" elsewhere.
    """
    data = _json_report(text)
    if data is not None and isinstance(data.get("must_fix"), list):
        return len(data["must_fix"])
    if _JSON_KEY.search(text):
        return None
    count, in_section, level = 0, False, 0
    for line in text.splitlines():
        if _HEADING.match(line):
            depth = len(line.strip()) - len(line.strip().lstrip("#"))
            if in_section and depth > level:
                count += 1  # "### 1. ship.py:308 ..." under "## Must-fix" is an item
                continue
            in_section, level = bool(_MUST_FIX_HEADING.match(line)), depth
            continue
        if _NONE.search(line):
            continue
        if (in_section and _ITEM.match(line)) or (not in_section and _MUST_FIX.match(line)):
            count += 1
    return count


def reviewed_sha(text: str) -> str:
    data = _json_report(text)
    return str(data.get("reviewed_sha", "")) if data else ""


def record(cwd: Path, coop: Path, adversary: Path, accept: str = "") -> tuple[int, str]:
    repo = store.find_repo(cwd)
    if repo is None:
        return 2, "rails review: not inside a git checkout"
    top = toplevel(cwd)
    texts = {}
    for voice, path in (("coop", coop), ("adversary", adversary)):
        text = read_any(path)
        if text is None:
            return 2, f"rails review: cannot read the {voice} report {path}"
        texts[voice] = text
        if len(texts[voice].strip()) < 200:
            return 2, f"rails review: the {voice} report is under 200 characters - that is not a review"
    if texts["coop"].strip() == texts["adversary"].strip():
        return 2, "rails review: the two reports are identical - two voices, two reports"
    if dirty_tracked(top):
        return 2, (
            "rails review: the working copy has uncommitted changes - the reviewers read the disk, the receipt "
            "names HEAD's tree. Commit, re-run them, then record."
        )
    sha, tree_sha = head(top), tree(top)
    for voice, text in texts.items():
        named = reviewed_sha(text).lower()
        if re.fullmatch(r"[0-9a-f]{7,40}", named) and not sha.startswith(named):
            return 2, f"rails review: the {voice} report reviewed {named[:12]}, not HEAD {sha[:12]} - re-run it on HEAD"
    counts = {voice: must_fix_count(text) for voice, text in texts.items()}
    for voice, count in counts.items():
        if count is None:
            return 2, (
                f"rails review: the {voice} report names a must_fix list but its JSON does not parse - "
                "save the reviewer's JSON object as it returned it"
            )
    receipts.write(
        repo,
        "review",
        sha=sha,
        tree=tree_sha,
        coop_sha256=hashlib.sha256(texts["coop"].encode("utf-8")).hexdigest(),
        adversary_sha256=hashlib.sha256(texts["adversary"].encode("utf-8")).hexdigest(),
        must_fix_coop=counts["coop"],
        must_fix_adversary=counts["adversary"],
        accepted=accept.strip()[:400],
    )
    open_count = counts["coop"] + counts["adversary"]
    note = ""
    if open_count and not accept.strip():
        note = " - this tree will not arm: fix them and re-review, or record why with --accept \"<reason>\""
    return 0, (
        f"rails review: recorded for tree {tree_sha[:12]} "
        f"(must-fix: coop {counts['coop']}, adversary {counts['adversary']}){note}"
    )


def covering(repo: store.RepoId, top: Path, rev: str = "HEAD") -> dict | None:
    """The newest valid receipt for ``rev``'s tree, or for an earlier tree that differs from
    it only in prose (`ship.is_prose`): a docs commit after the review does not need the voices
    again. Anything else that changed needs a new review."""
    from rails.gitutil import git
    from rails.ship import is_prose

    target = tree(top, rev)
    rows = [r for r in receipts.read(repo, "review") if receipts.valid(r) and r.get("tree")]
    for row in reversed(rows):
        if row["tree"] == target:
            return row
        out = git(top, "diff", "--name-only", "--no-renames", row["tree"], target, check=False)
        names = [n for n in out.splitlines() if n.strip()]
        if names and all(is_prose(n) for n in names):
            return row
    return None


def latest_for_tree(repo: store.RepoId, tree_sha: str) -> dict | None:
    rows = [r for r in receipts.read(repo, "review") if receipts.valid(r) and r.get("tree") == tree_sha]
    return rows[-1] if rows else None


def arming_problem(row: dict | None) -> str | None:
    """Why a reviewed tree may not arm, or None. Open must-fixes block unless accepted with a reason."""
    if row is None:
        return (
            "no review receipt for HEAD's tree. Run the rails:reviewer-coop and rails:reviewer-adversary agents "
            "on the diff, save each report, then `rails review record --coop F --adversary F`."
        )
    open_count = int(row.get("must_fix_coop", 0)) + int(row.get("must_fix_adversary", 0))
    if open_count and not str(row.get("accepted", "")).strip():
        return (
            f"the review of HEAD's tree has {open_count} open must-fix item(s). Fix them, commit, re-review; "
            "or, if a finding is wrong, record why: `rails review record ... --accept \"<reason>\"`."
        )
    return None


def summary_line(row: dict | None) -> str:
    """One line for the PR body, so the operator sees what the review found."""
    if row is None:
        return ""
    accepted = f"; accepted open items: {row['accepted']}" if row.get("accepted") else ""
    return (
        f"**Review** (two voices, tree {str(row.get('tree', ''))[:12]}): must-fix coop "
        f"{row.get('must_fix_coop', 0)}, adversary {row.get('must_fix_adversary', 0)}{accepted}"
    )


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="rails review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="seal the two voices' reports for HEAD's tree")
    rec.add_argument("--coop", required=True, type=Path)
    rec.add_argument("--adversary", required=True, type=Path)
    rec.add_argument("--accept", default="", help="why the open must-fix items are wrong (shown in the PR body)")
    sub.add_parser("status", help="is HEAD's tree reviewed?")
    args = ap.parse_args(argv)
    if args.cmd == "record":
        code, text = record(Path.cwd(), args.coop, args.adversary, args.accept)
        print(text)
        return code
    repo = store.find_repo(Path.cwd())
    if repo is None:
        print("rails review: not inside a git checkout")
        return 2
    row = latest_for_tree(repo, tree(toplevel(Path.cwd())))
    if row is None:
        print("rails review: HEAD's tree has no review receipt. Run rails:reviewer-coop and "
              "rails:reviewer-adversary on the diff, then `rails review record --coop F --adversary F`.")
        return 1
    print(f"rails review: reviewed (must-fix: coop {row.get('must_fix_coop')}, adversary {row.get('must_fix_adversary')})")
    return 0
