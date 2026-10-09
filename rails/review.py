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
import re
from pathlib import Path

from rails import receipts, store
from rails.gitutil import head, toplevel, tree

_MUST_FIX = re.compile(r"(?im)^\s*(?:[-*]\s*|\d+[.)]\s*)?(?:\*\*)?must[- ]fix\b")


def must_fix_count(text: str) -> int:
    return len(_MUST_FIX.findall(text))


def record(cwd: Path, coop: Path, adversary: Path) -> tuple[int, str]:
    repo = store.find_repo(cwd)
    if repo is None:
        return 2, "rails review: not inside a git checkout"
    top = toplevel(cwd)
    texts = {}
    for voice, path in (("coop", coop), ("adversary", adversary)):
        try:
            texts[voice] = path.read_text(encoding="utf-8")
        except OSError as exc:
            return 2, f"rails review: cannot read the {voice} report {path}: {exc}"
        if len(texts[voice].strip()) < 200:
            return 2, f"rails review: the {voice} report is under 200 characters - that is not a review"
    if texts["coop"].strip() == texts["adversary"].strip():
        return 2, "rails review: the two reports are identical - two voices, two reports"
    sha, tree_sha = head(top), tree(top)
    counts = {voice: must_fix_count(text) for voice, text in texts.items()}
    receipts.write(
        repo,
        "review",
        sha=sha,
        tree=tree_sha,
        coop_sha256=hashlib.sha256(texts["coop"].encode("utf-8")).hexdigest(),
        adversary_sha256=hashlib.sha256(texts["adversary"].encode("utf-8")).hexdigest(),
        must_fix_coop=counts["coop"],
        must_fix_adversary=counts["adversary"],
    )
    return 0, (
        f"rails review: recorded for tree {tree_sha[:12]} "
        f"(must-fix: coop {counts['coop']}, adversary {counts['adversary']})"
    )


def latest_for_tree(repo: store.RepoId, tree_sha: str) -> dict | None:
    rows = [r for r in receipts.read(repo, "review") if receipts.valid(r) and r.get("tree") == tree_sha]
    return rows[-1] if rows else None


def main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="rails review")
    sub = ap.add_subparsers(dest="cmd", required=True)
    rec = sub.add_parser("record", help="seal the two voices' reports for HEAD's tree")
    rec.add_argument("--coop", required=True, type=Path)
    rec.add_argument("--adversary", required=True, type=Path)
    sub.add_parser("status", help="is HEAD's tree reviewed?")
    args = ap.parse_args(argv)
    if args.cmd == "record":
        code, text = record(Path.cwd(), args.coop, args.adversary)
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
