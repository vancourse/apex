"""The completion gate's own tests — false positives first, on purpose.

**Green on a first run is the least informative signal available**, because an
implementation that returns `[]` is also green. So this suite is ordered against
that: the cases where the gate must stay *silent* come first and outnumber the
findings, and each of the gate's four conditions has a test that fails when that
condition **alone** is removed. Those are marked `PLANTED:` and were verified by
actually deleting the line and watching this file go red — a guard nobody watched
fail is a guard nobody knows is wired up.

The judgement is a pure function over already-read data with the per-milestone
timestamp lookup injected, so everything below runs with no token and no network.
The `gh` layer is exercised separately, at the seam where its output becomes data
(`parse_milestones`, `parse_closed_at`), because that is the part that can silently
change shape under us.

Run with `pytest templates/gates/tests`.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from datetime import datetime, timedelta, timezone

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = _HERE.parent / "milestone_completion_gate.py"


def _load():
    spec = importlib.util.spec_from_file_location("milestone_completion_gate", SCRIPT)
    assert spec is not None and spec.loader is not None, SCRIPT
    module = importlib.util.module_from_spec(spec)
    sys.modules["milestone_completion_gate"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
GRACE = timedelta(hours=24)


def milestone(**kwargs):
    defaults = dict(
        number=1, title="Ingest R2", state="open", open_issues=0, closed_issues=4
    )
    defaults.update(kwargs)
    return gate.Milestone(**defaults)


def at(hours_ago: float):
    """A lookup that answers `hours_ago` for every milestone."""
    return lambda _m: NOW - timedelta(hours=hours_ago)


def run(milestones, finished_at, grace=GRACE):
    return gate.findings(milestones, finished_at, now=NOW, grace=grace)


# ── false positives first: every shape the gate must stay silent on ────────────


def test_open_issues_remaining_is_not_a_finding():
    """The ordinary case — a release still being worked on."""
    assert run([milestone(open_issues=3)], at(500)) == []


def test_closed_milestone_is_not_a_finding():
    """PLANTED: drop the `state != "open"` guard and this fires on every closed
    release the repo has ever shipped — the gate's own success cases."""
    assert run([milestone(state="closed")], at(500)) == []


def test_empty_milestone_is_not_a_finding():
    """PLANTED: drop the `closed_issues == 0` guard and every placeholder milestone
    is reported. The measured repo had 47 of them; the 11 real findings would arrive
    buried under 36 that are not, and a report you have to filter is unread."""
    assert run([milestone(closed_issues=0)], at(9000)) == []


def test_inside_the_grace_period_is_not_a_finding():
    """PLANTED: drop the grace comparison and the gate fires in the window between
    the final merge and the operator closing the tab — on correct work. That is what
    teaches people to reach for `--admin`, which skips every other check too."""
    assert run([milestone()], at(2)) == []


def test_exactly_at_the_grace_boundary_is_not_a_finding():
    """`<=`, not `<`. An off-by-one here fires a day early, which is the same defect
    as no grace period at all, only rarer and therefore harder to diagnose."""
    assert run([milestone()], at(24)) == []


def test_a_repo_with_no_milestones_at_all_is_silent():
    assert run([], at(9000)) == []


def test_the_lookup_is_not_called_for_milestones_that_cannot_be_findings():
    """Cost, and a real failure mode: an issue query per open milestone is 47 API
    calls on the measured repo, and one of them raising on a milestone the gate was
    never going to report would fail the lane for nothing."""
    called = []

    def lookup(m):
        called.append(m.number)
        return NOW - timedelta(hours=500)

    run(
        [
            milestone(number=1, open_issues=3),
            milestone(number=2, closed_issues=0),
            milestone(number=3, state="closed"),
            milestone(number=4),
        ],
        lookup,
    )
    assert called == [4]


# ── the true positive, and what it says ───────────────────────────────────────


def test_a_finished_milestone_past_grace_is_reported():
    found = run([milestone(number=12, title="Ingest R2")], at(72))
    assert len(found) == 1
    assert found[0].milestone.number == 12


def test_the_finding_says_what_to_do_not_merely_what_is_wrong():
    """Naming the condition leaves the reader to infer the action, and the inference
    they usually make is that the gate is complaining about something out of their
    hands. Both legitimate actions are named because only a person can pick."""
    text = run([milestone()], at(72))[0].annotation()
    assert "Close it, or reopen the work it is missing." in text
    assert text.startswith("::error::")


def test_the_finding_reports_the_age_it_measured():
    """The age is the whole argument for the finding, so it is in the message. A
    finding that asserts staleness without showing it cannot be checked by a reader
    who thinks the gate is wrong."""
    assert "72h ago" in run([milestone()], at(72))[0].annotation()


def test_a_lowered_grace_period_changes_the_verdict():
    """The grace period is configuration, so this pins that it is actually read
    rather than shadowed by the constant."""
    assert run([milestone()], at(2), grace=timedelta(hours=1)) != []


# ── the clock: issue close times, never the milestone's updated_at ────────────


def test_the_clock_is_the_injected_lookup_not_any_milestone_field():
    """The load-bearing one. `updated_at` moves when somebody edits a description or
    retitles an issue, so a gate reading it would see a six-week-old abandoned
    release as zero hours old after one edited word — and would never fire on
    precisely the milestones that have been abandoned longest.

    Modelled here as a milestone whose own metadata says "just touched" while its
    issues closed six weeks ago. The finding must follow the issues.
    """
    found = run([milestone(title="edited five minutes ago")], at(24 * 42))
    assert len(found) == 1
    assert found[0].age > timedelta(days=41)


def test_max_not_min_across_the_issues():
    """The milestone finished when its LAST issue closed. Taking the earliest would
    age every long release past its grace period on day one."""
    stamps = [
        "2026-06-01T10:00:00Z",
        "2026-08-15T09:00:00Z",
        "2026-07-04T12:00:00Z",
    ]
    assert gate.parse_closed_at(stamps, milestone()) == datetime(
        2026, 8, 15, 9, 0, tzinfo=timezone.utc
    )


def test_pull_requests_do_not_move_the_clock(monkeypatch):
    """The issues endpoint returns PRs too, and a PR merged after the last issue
    closed would make a finished milestone look younger — the exact error
    `updated_at` makes. The filter lives in the `--jq` expression, so this asserts
    on the argv actually handed to `gh`."""
    monkeypatch.setattr(gate, "_gh", lambda args: (captured.append(args), "")[1])
    captured: list[list[str]] = []
    with pytest.raises(gate.ForgeReadError):  # empty answer, correctly a failed read
        gate.gh_finished_at(milestone(number=12))
    assert 'select(has("pull_request") | not)' in " ".join(captured[0])


# ── reads that did not work must raise, never resolve to a verdict ────────────


def test_all_closed_but_no_closed_at_raises():
    """PLANTED: return `now` (or skip the milestone) instead of raising, and a
    broken credential becomes either a silent pass on every milestone or a wave of
    findings dated today. Neither is distinguishable from the truth by the reader."""
    with pytest.raises(gate.ForgeReadError):
        gate.parse_closed_at(["null", "", "null"], milestone())


def test_no_issues_came_back_at_all_raises():
    with pytest.raises(gate.ForgeReadError):
        gate.parse_closed_at([], milestone())


def test_the_raise_propagates_out_of_the_judgement():
    """`findings` must not swallow it into an empty list — that is the silent-green
    failure this gate exists to avoid, applied to the gate itself."""

    def broken(_m):
        raise gate.ForgeReadError("token cannot read issues")

    with pytest.raises(gate.ForgeReadError):
        run([milestone()], broken)


def test_the_cli_reports_a_failed_read_as_exit_2_not_a_pass(monkeypatch):
    """Exit 2, distinct from 0 (clean) and 1 (findings). A failed read that exits 0
    is a gate that has stopped working and says nothing."""

    def broken():
        raise gate.ForgeReadError("gh not authenticated")

    monkeypatch.setattr(gate, "gh_milestones", broken)
    assert gate.main([]) == 2


def test_the_cli_exits_1_on_findings_and_0_when_clean(monkeypatch):
    monkeypatch.setattr(gate, "gh_milestones", lambda: [milestone()])
    monkeypatch.setattr(gate, "gh_finished_at", at(500))
    assert gate.main([]) == 1
    monkeypatch.setattr(gate, "gh_finished_at", at(1))
    assert gate.main([]) == 0


# ── the gh seam: where output becomes data ────────────────────────────────────


def test_parse_milestones_reads_the_tsv_projection():
    rows = [
        "12\topen\t0\t4\tIngest R2 — a CSV lands and the dashboard shows its rows",
        "13\topen\t2\t1\tIngest R3",
    ]
    parsed = gate.parse_milestones(rows)
    assert [m.number for m in parsed] == [12, 13]
    assert parsed[0].closed_issues == 4
    assert parsed[0].title.endswith("shows its rows")


def test_a_malformed_row_is_skipped_not_fatal():
    """A scheduled lane failing over one unparseable title would take the whole
    report down for a milestone it was probably not going to name."""
    parsed = gate.parse_milestones(["not a row", "", "12\topen\t0\t4\tIngest R2"])
    assert [m.number for m in parsed] == [12]


def test_a_title_containing_a_tab_does_not_split_the_record():
    """`@tsv` escapes real tabs, but a title arriving with one anyway must not shift
    every following field by one and turn a count into a title."""
    parsed = gate.parse_milestones(["12\topen\t0\t4\tIngest\tR2"])
    assert parsed[0].closed_issues == 4 and parsed[0].title == "Ingest\tR2"


def _argv(monkeypatch, call) -> list[str]:
    """The argv one of the `gh` wrappers actually builds."""
    captured: list[list[str]] = []

    def fake(args):
        captured.append(args)
        return ""

    monkeypatch.setattr(gate, "_gh", fake)
    try:
        call()
    except gate.ForgeReadError:
        pass  # an empty answer is correctly a failed read; the argv is what we want
    assert captured, "the wrapper did not call gh at all"
    return captured[0]


def test_it_reads_milestones_over_rest_never_the_search_api(monkeypatch):
    """Search is unavailable in some repos and answers an unavailable search with an
    **empty list** rather than an error — which reads here as "no findings", so the
    gate would go permanently and silently green."""
    argv = _argv(monkeypatch, gate.gh_milestones)
    assert argv[0] == "repos/:owner/:repo/milestones?state=open&per_page=100"
    assert not any("search" in arg for arg in argv)


@pytest.mark.parametrize(
    "call_name, arg", [("gh_milestones", None), ("gh_finished_at", milestone())]
)
def test_both_reads_paginate(monkeypatch, call_name, arg):
    """`per_page=100` alone truncates at 100 — silently. On the issues query that
    yields a `max(closed_at)` which is simply wrong rather than missing, and a wrong
    clock is the one failure this gate has no way to notice."""
    call = getattr(gate, call_name)
    argv = _argv(monkeypatch, call if arg is None else (lambda: call(arg)))
    assert "--paginate" in argv
