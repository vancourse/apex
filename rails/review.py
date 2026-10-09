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
from rails.gitutil import head, toplevel, tree

_MUST_FIX = re.compile(r"(?im)^\s*(?:[-*]\s*|\d+[.)]\s*)?(?:\*\*)?must[- _]fix\b")


def _json_report(text: str) -> dict | None:
    """The reviewers' own format (agents/reviewer-*.md): a JSON object with ``must_fix``."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def must_fix_count(text: str) -> int:
    data = _json_report(text)
    if data is not None and isinstance(data.get("must_fix"), list):
        return len(data["must_fix"])
    return len(_MUST_FIX.findall(text))


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
        try:
            texts[voice] = path.read_text(encoding="utf-8")
        except OSError as exc:
            return 2, f"rails review: cannot read the {voice} report {path}: {exc}"
        if len(texts[voice].strip()) < 200:
            return 2, f"rails review: the {voice} report is under 200 characters - that is not a review"
    if texts["coop"].strip() == texts["adversary"].strip():
        return 2, "rails review: the two reports are identical - two voices, two reports"
    sha, tree_sha = head(top), tree(top)
    for voice, text in texts.items():
        named = reviewed_sha(text).lower()
        if re.fullmatch(r"[0-9a-f]{7,40}", named) and not sha.startswith(named):
            return 2, f"rails review: the {voice} report reviewed {named[:12]}, not HEAD {sha[:12]} - re-run it on HEAD"
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
