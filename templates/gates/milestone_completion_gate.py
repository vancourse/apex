#!/usr/bin/env python3
"""Scheduled CI check: a milestone whose work is finished must not stay open.

Every gate a project normally has guards an **entry** condition — may this work
start, is it declared, is it reviewed, is it releasable. Almost nothing guards the
**exit**: the mechanical moment a release is declared done. Measured on a real repo
over its first 33 days: **47 milestones open, 0 closed, 11 of them holding zero open
issues**, three of which were releases of the very component its operator believed
was incomplete. Nothing was broken. Every issue had closed correctly through
`Closes #N`. There was simply no moment anywhere that said *this release is done,
stop touching it*, so the tracker could not display success and the project felt
permanently incomplete.

This is that moment, mechanized. It reports milestones that are **open**, hold **no
open issues**, hold **at least one closed issue**, and finished longer ago than a
grace period.

Why each condition is there
---------------------------
**`closed_issues > 0` — an empty milestone is skipped.** A milestone with nothing in
it is a release nobody has started, not a release nobody closed. Reporting those
buries the real findings under every placeholder the project ever created, and a
report you have to filter is a report nobody reads.

**The grace period is load-bearing, and its default is 24h.** At zero this fires in
the window between a release's final merge and the operator closing the tab — that
is, on correct work. **A gate that fires on correct work teaches people to reach for
`--admin`, which skips every other check too**, so a single false positive here costs
far more than this gate is worth.

**The clock is `max(closed_at)` across the milestone's ISSUES — never the milestone's
own `updated_at`.** `updated_at` moves when somebody edits a description or retitles
an issue inside it, so one edited word would reset a six-week-old finished release's
age to zero and the gate would never fire on precisely the milestones that have been
abandoned longest. The issues' close times are the only timestamps that mean "the
work stopped".

**REST, never the search API.** The obvious implementation is one
`search/issues?q=milestone:...`, and it is wrong: search is unavailable in some repos
(it is disabled for a repo with search off, and unavailable to some token scopes), and
it answers an unavailable search with an **empty list** rather than an error. An empty
list here reads as "no findings" — the gate would go permanently, silently green. The
milestones REST endpoint either answers or fails.

**An unreadable close time raises.** If every issue in a milestone is closed and not
one of them carries a `closed_at`, that is a read that did not work — not a milestone
finished now, and not a milestone with no age. Guessing either way turns a broken
credential into either a silent pass or a wave of false findings. It raises instead.

Structure
---------
The judgement is a **pure function over already-read data** (`findings`), with the
per-milestone timestamp lookup **injected**. Tests drive the whole decision table with
no token and no network; only `gh_milestones` / `gh_finished_at` touch the forge.

Usage — from a **scheduled** lane, not a PR lane. The condition it watches becomes
true *after* the last PR merges, when no PR lane is running::

    - name: Finished milestones are closed (gate)
      if: ${{ github.event_name == 'schedule' }}
      env: { GH_TOKEN: "${{ github.token }}" }
      run: python ci/milestone_completion_gate.py

Exit 0 when clean, 1 with a `::error::` annotation per finding, 2 when a read failed.

Honest limit: this cannot tell whether a milestone *should* be finished. It sees that
every issue filed under it is closed. A release still missing an issue nobody filed
reads as finished here — which is why the numbered demo in the milestone description
is the actual definition of done (see `apex:release-loop`), and this is its backstop.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable

#: 24h. Long enough that the operator who merged the last PR at 18:00 gets their
#: evening; short enough that a finished release is reported the next working day.
DEFAULT_GRACE_HOURS = 24


class ForgeReadError(RuntimeError):
    """A read that did not work. Never a finding, never silently treated as clean."""


@dataclass(frozen=True)
class Milestone:
    number: int
    title: str
    state: str
    open_issues: int
    closed_issues: int


@dataclass(frozen=True)
class Finding:
    milestone: Milestone
    finished: datetime
    age: timedelta

    def annotation(self) -> str:
        """A `::error::` line that says what to DO.

        Naming the condition ("milestone 12 has no open issues") leaves the reader to
        infer the action, and the inference they usually make is that the gate is
        complaining about something out of their hands. Both actions are named because
        both are legitimate: the release is finished, or it is missing work nobody
        filed — and only a person can say which.
        """
        hours = int(self.age.total_seconds() // 3600)
        return (
            f"::error::Milestone #{self.milestone.number} "
            f"'{self.milestone.title}' — all {self.milestone.closed_issues} of its "
            f"issues are closed and the last one closed {hours}h ago "
            f"({self.finished:%Y-%m-%d %H:%M} UTC), but it is still open. "
            f"Close it, or reopen the work it is missing."
        )


def parse_milestones(lines: Iterable[str]) -> list[Milestone]:
    """TSV rows of `number, state, open_issues, closed_issues, title` -> milestones.

    A TSV projection rather than raw JSON because `gh api --paginate` concatenates one
    JSON array per page, which no JSON parser accepts; projecting through `--jq` to
    `@tsv` yields one record per line across every page, and `@tsv` escapes any tab or
    newline inside a title so a record can never span two lines.

    A row that does not parse is skipped rather than fatal: a malformed title field is
    not worth failing a scheduled lane over, and the milestone it belongs to simply
    goes unreported.
    """
    milestones = []
    for line in lines:
        parts = line.rstrip("\n").split("\t")
        if len(parts) < 5:
            continue
        try:
            number, state = int(parts[0]), parts[1]
            open_issues, closed_issues = int(parts[2]), int(parts[3])
        except ValueError:
            continue
        milestones.append(
            Milestone(
                number=number,
                title="\t".join(parts[4:]),
                state=state,
                open_issues=open_issues,
                closed_issues=closed_issues,
            )
        )
    return milestones


def findings(
    milestones: Iterable[Milestone],
    finished_at: Callable[[Milestone], datetime],
    now: datetime,
    grace: timedelta,
) -> list[Finding]:
    """The judgement, over data somebody else read.

    `finished_at` is called only for milestones that pass every cheap test, so a repo
    with 47 open milestones and 11 finished ones makes 11 issue queries, not 47.
    It may raise `ForgeReadError`; that propagates, because a milestone whose age
    cannot be established is not a milestone that is fine.
    """
    found = []
    for milestone in milestones:
        if milestone.state != "open":
            continue
        if milestone.open_issues != 0:
            continue
        if milestone.closed_issues == 0:
            # A release nobody started, not a release nobody closed.
            continue
        finished = finished_at(milestone)
        age = now - finished
        if age <= grace:
            continue
        found.append(Finding(milestone=milestone, finished=finished, age=age))
    return found


def parse_closed_at(values: Iterable[str], milestone: Milestone) -> datetime:
    """The latest `closed_at` among a milestone's closed issues.

    Raises rather than returning a sentinel when nothing usable came back. The caller
    has already established that this milestone reports closed issues, so an empty or
    all-null answer contradicts the milestones endpoint — which means the read failed,
    not that the work has no end.
    """
    stamps = []
    for raw in values:
        text = raw.strip()
        if not text or text == "null":
            continue
        try:
            stamps.append(
                datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(
                    timezone.utc
                )
            )
        except ValueError:
            continue
    if not stamps:
        raise ForgeReadError(
            f"milestone #{milestone.number} '{milestone.title}' reports "
            f"{milestone.closed_issues} closed issues but none of them came back with "
            f"a usable closed_at — treating this as a failed read, not as finished."
        )
    return max(stamps)


def _gh(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", "api", *args], capture_output=True, text=True, timeout=120
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ForgeReadError(f"could not run `gh api`: {exc}") from exc
    if result.returncode != 0:
        raise ForgeReadError(
            f"`gh api {' '.join(args)}` exited {result.returncode}: "
            f"{result.stderr.strip() or '(no stderr)'}"
        )
    return result.stdout


def gh_milestones() -> list[Milestone]:
    """Every OPEN milestone. REST — see the module docstring on why not search."""
    return parse_milestones(
        _gh(
            [
                "repos/:owner/:repo/milestones?state=open&per_page=100",
                "--paginate",
                "--jq",
                ".[] | [.number, .state, .open_issues, .closed_issues, .title] | @tsv",
            ]
        ).splitlines()
    )


def gh_finished_at(milestone: Milestone) -> datetime:
    """When this milestone's work stopped: `max(closed_at)` over its closed issues.

    Pull requests are filtered out. The issues endpoint returns them alongside issues,
    and a PR merged after the last issue closed would push the clock forward — making a
    finished milestone look younger than it is, which is the exact error `updated_at`
    makes and the reason this function exists.
    """
    output = _gh(
        [
            f"repos/:owner/:repo/issues?milestone={milestone.number}"
            "&state=closed&per_page=100",
            "--paginate",
            "--jq",
            '.[] | select(has("pull_request") | not) | .closed_at',
        ]
    )
    return parse_closed_at(output.splitlines(), milestone)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--grace-hours",
        type=float,
        default=DEFAULT_GRACE_HOURS,
        help=(
            "how long a finished milestone may sit open before it is reported "
            f"(default {DEFAULT_GRACE_HOURS}). Lowering this toward zero makes the "
            "gate fire between the last merge and the operator closing the tab."
        ),
    )
    args = parser.parse_args(argv)

    try:
        found = findings(
            gh_milestones(),
            gh_finished_at,
            now=datetime.now(timezone.utc),
            grace=timedelta(hours=args.grace_hours),
        )
    except ForgeReadError as exc:
        print(f"::error::milestone completion gate could not read the forge: {exc}")
        return 2

    if not found:
        print("Every finished milestone is closed.")
        return 0

    for finding in found:
        print(finding.annotation())
    print(
        f"\n{len(found)} finished milestone(s) left open. A release that cannot be "
        "declared done reads as a release that failed."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
