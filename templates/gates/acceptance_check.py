#!/usr/bin/env python3
"""CI check: a PR that closes an issue must answer that issue's `Done when`.

`Closes #N` is the mechanism that makes a milestone's issue count mean anything —
and it is also the moment nobody re-reads what #N actually asked for. The issue's
acceptance criteria were written when the work was understood least, the PR is
merged when it is understood most, and between those two moments no step forces a
comparison. This is that step: every criterion #N states arrives in the PR body as
a tick-box, and an unticked or absent one fails the check.

What it does **not** do, stated here rather than discovered later
-----------------------------------------------------------------
**It cannot tell whether a ticked box is TRUE.** A `- [x]` is an author's claim, and
this check reads claims. **It cannot make an unfalsifiable criterion good** either: if
#N's acceptance is "a decision is recorded", ticking it is free and the check learns
nothing — that defect lives in the issue form, not here (see the falsifiability
demand in `templates/github/work-item.yml`).

What it buys is one thing, and the whole design is sized to it: **a forced re-read of
the issue at close time**, by the person closing it, in the body reviewers read. Do
not extend it into a claim of verification.

The extraction rules, and why each one exists
---------------------------------------------
**Only bullets under the acceptance heading, stopping at the next heading.** A GitHub
issue *form* renders each field as its own heading, and the work-item form puts a
`Production caller` field — a bullet list of paths — directly after `Done when`.
Running to the end of the body swallows it, and the check then demands the PR tick off
file paths that were never acceptance criteria.

**Prose acceptance yields no criteria, and is NOT a finding.** Plenty of real issues
state acceptance as a paragraph. Failing those fires the gate on correct work, and a
gate that fires on correct work teaches people to reach for `--admin`, which skips
every *other* check too. An issue with no acceptance section at all is the same case.

**Comparison is normalised** — non-alphanumerics stripped, lowercased. An author who
drops the bold while ticking, or fixes a typo, or changes `->` to `→`, is doing nothing
wrong, and a check that fails them is teaching them to route around it.

**An unreadable issue raises.** Reporting "no criteria" for an issue the token could
not fetch would turn a broken credential into a silent pass on every PR.

Usage::

    PR_BODY="$(gh pr view "$PR" --json body -q .body)" python ci/acceptance_check.py
    python ci/acceptance_check.py --body-file body.md --print-checklist

`--print-checklist` emits the pasteable block rather than checking. A check is only
fair if satisfying it is trivial, and "go and transcribe seven bullets by hand" is not
trivial — so the gate ships the thing it wants you to paste.

Exit 0 when satisfied, 1 with a `::error::` annotation per finding, 2 when a read
failed.

Honest limit: matching is over the *whole* PR body, not per-issue sections. Two issues
stating a byte-identical criterion are satisfied by one tick. The alternative — binding
each tick to the heading above it — makes the check brittle against reformatting, for
a case that costs nothing when it happens.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Iterable

#: GitHub's full closing-keyword set, not a subset. The forge accepts all nine and
#: closes the issue for any of them, so a gate that recognised only `Closes` would go
#: silent on a PR that really is closing an issue — silence being indistinguishable
#: from "this PR closes nothing".
CLOSES = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.IGNORECASE
)

#: A heading. ATX form is what GitHub issue forms render field labels as (`### Done
#: when`); the bold-only line is what hand-written issues use instead, and treating it
#: as a heading is what stops extraction at the right place in those.
HEADING = re.compile(r"^\s{0,3}(?:#{1,6}\s+\S|\*\*[^*].*\*\*:?\s*$)")

#: `- foo`, `* foo`, `+ foo`, with an optional task box.
BULLET = re.compile(r"^\s*[-*+]\s+(?:\[(?P<box>[ xX])\]\s*)?(?P<text>.+?)\s*$")

#: Which headings hold acceptance. Matched against the normalised heading text, by
#: prefix, so `Done when`, `Done when:`, `Acceptance` and `Acceptance criteria` all hit.
ACCEPTANCE_HEADINGS = ("donewhen", "acceptance")


class ForgeReadError(RuntimeError):
    """A read that did not work. Never reported as "this issue has no criteria"."""


@dataclass(frozen=True)
class Finding:
    issue: int
    criterion: str
    problem: str  # "not ticked" | "missing from the PR body"

    def annotation(self) -> str:
        return (
            f"::error::#{self.issue} acceptance — {self.problem}: "
            f"{self.criterion!r}. Tick it if it is true, or say in the body why it "
            f"turned out to be the wrong criterion."
        )


def normalise(text: str) -> str:
    """Comparison form: alphanumerics only, lowercased.

    Deliberately lossy. The things it discards — bold markers, punctuation, arrows,
    trailing colons — are the things an author edits while ticking a box, and none of
    them change what the criterion says.
    """
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def closed_issue_numbers(pr_body: str) -> list[int]:
    """Issue numbers this PR closes, in order, deduplicated.

    Same-repo `#N` only. `owner/repo#N` and full URLs close cross-repo issues on the
    forge and are not recognised here — the check would have to know which repo to
    query, and a cross-repo close is not the case this gate was built for. It reports
    nothing for them rather than guessing.
    """
    seen: list[int] = []
    for match in CLOSES.finditer(pr_body):
        number = int(match.group(1))
        if number not in seen:
            seen.append(number)
    return seen


def acceptance_criteria(issue_body: str) -> list[str]:
    """The bullets under the issue's acceptance heading. Empty is a valid answer.

    Empty means one of three things, all of them fine: the issue states acceptance as
    prose, the issue has no acceptance section, or the section is there and holds no
    bullets. None of the three is a finding — see the module docstring.
    """
    lines = issue_body.splitlines()
    start = None
    for index, line in enumerate(lines):
        if not HEADING.match(line):
            continue
        text = normalise(line.strip().lstrip("#").strip().strip("*").strip())
        if text.startswith(ACCEPTANCE_HEADINGS):
            start = index + 1
            break
    if start is None:
        return []

    criteria = []
    for line in lines[start:]:
        if HEADING.match(line):
            # The next field begins. `Production caller` is a bullet list of paths;
            # swallowing it makes this gate demand the PR tick off file names.
            break
        if match := BULLET.match(line):
            if text := match.group("text").strip():
                criteria.append(text)
    return criteria


def ticked_claims(pr_body: str) -> dict[str, bool]:
    """Normalised task-list text -> whether it is ticked, over the whole PR body.

    A criterion that appears twice is ticked if *either* occurrence is — a body that
    both restates and ticks a criterion is answering it, not half-answering it.
    """
    claims: dict[str, bool] = {}
    for line in pr_body.splitlines():
        match = BULLET.match(line)
        if not match or match.group("box") is None:
            continue
        key = normalise(match.group("text"))
        if not key:
            continue
        claims[key] = claims.get(key, False) or match.group("box").lower() == "x"
    return claims


def check(pr_body: str, criteria_by_issue: dict[int, list[str]]) -> list[Finding]:
    """The judgement, over data somebody else read."""
    claims = ticked_claims(pr_body)
    found = []
    for issue, criteria in criteria_by_issue.items():
        for criterion in criteria:
            key = normalise(criterion)
            if key not in claims:
                found.append(Finding(issue, criterion, "missing from the PR body"))
            elif not claims[key]:
                found.append(Finding(issue, criterion, "not ticked"))
    return found


def checklist(criteria_by_issue: dict[int, list[str]]) -> str:
    """The pasteable block. Its bullet text is the criterion verbatim.

    Verbatim matters mechanically, not only politely: the issue reference sits in the
    heading rather than inside the bullet, because anything prepended to the bullet
    text would change what it normalises to and the paste would not satisfy the check
    it came from.
    """
    blocks = []
    for issue, criteria in criteria_by_issue.items():
        if not criteria:
            continue
        blocks.append(
            f"## Acceptance — #{issue}\n\n"
            + "\n".join(f"- [ ] {criterion}" for criterion in criteria)
        )
    return "\n\n".join(blocks)


def gh_issue_body(number: int, timeout: float = 60) -> str:
    """#N's body, or raise. Never an empty string standing in for a failed read.

    `timeout` is a parameter because the two callers have opposite risk profiles: a CI
    lane can afford to wait, while apex's `acceptance_checklist.py` hook runs this
    *before* a `gh pr create` a human is watching, and a hook that stalls is one the
    reader disables.
    """
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(number), "--json", "body", "-q", ".body"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ForgeReadError(f"could not run `gh issue view {number}`: {exc}") from exc
    if result.returncode != 0:
        raise ForgeReadError(
            f"`gh issue view {number}` exited {result.returncode}: "
            f"{result.stderr.strip() or '(no stderr)'}"
        )
    return result.stdout


def collect(
    pr_body: str, fetch_issue_body: Callable[[int], str] | None = None
) -> dict[int, list[str]]:
    """Every closed issue's criteria, keyed by issue number. The lookup is injected.

    The default is resolved here rather than in the signature. A default argument
    binds at import, which silently pins the module-level function an installer or a
    test has replaced since — the seam would look injectable and not be.
    """
    fetch = fetch_issue_body if fetch_issue_body is not None else gh_issue_body
    return {
        number: acceptance_criteria(fetch(number))
        for number in closed_issue_numbers(pr_body)
    }


def _read_body(argv_body_file: str | None) -> str:
    if argv_body_file:
        if argv_body_file == "-":
            return sys.stdin.read()
        with open(argv_body_file, encoding="utf-8") as handle:
            return handle.read()
    return os.environ.get("PR_BODY", "")


def _report(found: Iterable[Finding]) -> int:
    found = list(found)
    if not found:
        print("Every acceptance criterion of every closed issue is ticked.")
        return 0
    for finding in found:
        print(finding.annotation())
    print(
        f"\n{len(found)} acceptance criterion/criteria unanswered. Run with "
        "--print-checklist to get the block to paste."
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--body-file", help="the PR body; `-` for stdin. Defaults to $PR_BODY."
    )
    parser.add_argument(
        "--print-checklist",
        action="store_true",
        help="print the pasteable tick-box block instead of checking.",
    )
    args = parser.parse_args(argv)

    body = _read_body(args.body_file)
    if not body.strip():
        print("::error::no PR body supplied (set $PR_BODY or pass --body-file).")
        return 2

    try:
        criteria = collect(body)
    except ForgeReadError as exc:
        print(f"::error::acceptance check could not read an issue: {exc}")
        return 2

    if args.print_checklist:
        block = checklist(criteria)
        print(block if block else "No closed issue states bullet acceptance criteria.")
        return 0

    return _report(check(body, criteria))


if __name__ == "__main__":
    sys.exit(main())
