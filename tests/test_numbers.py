"""The four numbers (rails/numbers.py): each method on a planted history it must get right."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from rails import numbers, ship, store

DAY = 86400
T0 = 1_780_000_000  # a fixed epoch; every commit is dated from it


def _commit_at(top: Path, rel: str, text: str, when: int, message: str = "c") -> str:
    path = top / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    env = {**os.environ, "GIT_AUTHOR_DATE": f"@{when} +0000", "GIT_COMMITTER_DATE": f"@{when} +0000"}
    subprocess.run(["git", "add", "-A"], cwd=top, check=True, env=env)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=top, check=True, env=env)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=top, capture_output=True, text=True, check=True
    ).stdout.strip()


@pytest.fixture
def dated(repo):
    """c1 writes five lines; c2 (day 20) rewrites a 20-day-old line; c3 (day 25) rewrites
    c2's 5-day-old line; c4 only adds a file; c5 only touches a lock file."""
    lines = [f"line {i}" for i in range(1, 6)]
    shas = {"c1": _commit_at(repo, "a.txt", "\n".join(lines) + "\n", T0, "c1")}
    _commit_at(repo, "uv.lock", "v1\n", T0, "lock v1")
    lines[1] = "line 2 again"
    shas["c2"] = _commit_at(repo, "a.txt", "\n".join(lines) + "\n", T0 + 20 * DAY, "c2")
    lines[1] = "line 2 a third time"
    shas["c3"] = _commit_at(repo, "a.txt", "\n".join(lines) + "\n", T0 + 25 * DAY, "c3")
    shas["c4"] = _commit_at(repo, "b.txt", "new\n", T0 + 26 * DAY, "c4")
    shas["c5"] = _commit_at(repo, "uv.lock", "v2\n", T0 + 26 * DAY + 60, "c5")
    return repo, shas


def test_rework_is_a_rewrite_of_a_line_younger_than_14_days(dated):
    top, shas = dated
    assert numbers.is_rework(top, shas["c2"], T0 + 20 * DAY) is False
    assert numbers.is_rework(top, shas["c3"], T0 + 25 * DAY) is True
    assert numbers.is_rework(top, shas["c4"], T0 + 26 * DAY) is None  # adds only: not counted
    assert numbers.is_rework(top, shas["c5"], T0 + 26 * DAY + 60) is None  # lock files skipped


def test_rework_share_counts_only_commits_that_rewrite_lines(dated):
    top, _ = dated
    w = numbers.Window("w", T0 + 10 * DAY, T0 + 30 * DAY)
    result = numbers.rework_share(top, "HEAD", w, {})
    assert result == {"share": 0.5, "rework": 1, "counted": 2, "commits": 4}


def test_the_cut_is_the_commit_that_added_the_lanes_file(repo):
    _commit_at(repo, "src.py", "x = 1\n", T0, "before")
    _commit_at(repo, "rails/lanes.toml", "[lane]\n", T0 + 5 * DAY, "adopt")
    _commit_at(repo, "rails/lanes.toml", "[lane]\nx = 1\n", T0 + 9 * DAY, "edit")
    assert numbers.cut(repo, "HEAD") == T0 + 5 * DAY
    before, since = numbers.windows(T0 + 5 * DAY, T0 + 7 * DAY)
    assert (before.start, before.end) == (T0 + 5 * DAY - 30 * DAY, T0 + 5 * DAY)
    assert (since.start, since.end) == (T0 + 5 * DAY, T0 + 7 * DAY)


def test_detected_by_round_trips_through_the_pr_body(repo):
    rid = store.find_repo(repo)
    body = ship.compose_body("Fixes the thing.", ["12"], rid, "0" * 40, "lane")
    assert "Detected-by: lane" in body and body.rstrip().endswith("Closes #12")
    prs = [
        {"body": body},
        {"body": "x\n\nDetected-by: operator\n"},
        {"body": "a feature, no trailer"},
        {"body": "detected-by: HOOK"},
    ]
    assert numbers.catch_rate(prs) == {"share": 0.667, "automated": 2, "tagged": 3, "merged": 4}


def test_harness_share_separates_the_code_from_everything_else(monkeypatch, tmp_path):
    """r1 failed and the same workflow passed on the same commit (r2): harness. r3 failed in
    its own test step: code, and its `gate` only mirrors it. r4 never got past setup: harness."""
    runs = [
        {"id": 1, "workflow_id": 7, "head_sha": "a", "status": "completed", "conclusion": "failure", "run_attempt": 1},
        {"id": 2, "workflow_id": 7, "head_sha": "a", "status": "completed", "conclusion": "success", "run_attempt": 1},
        {"id": 3, "workflow_id": 7, "head_sha": "b", "status": "completed", "conclusion": "failure", "run_attempt": 1},
        {"id": 4, "workflow_id": 7, "head_sha": "c", "status": "completed", "conclusion": "failure", "run_attempt": 1},
    ]
    step = lambda name, c: {"name": name, "conclusion": c}  # noqa: E731
    jobs = {
        1: [{"name": "suite", "conclusion": "failure", "run_attempt": 1,
             "steps": [step("Set up job", "success"), step("pytest", "failure")]}],
        3: [{"name": "suite", "conclusion": "failure", "run_attempt": 1,
             "steps": [step("Set up job", "success"), step("pytest", "failure")]},
            {"name": "gate", "conclusion": "failure", "run_attempt": 1,
             "steps": [step("Set up job", "success"), step("verdict", "failure")]}],
        4: [{"name": "image", "conclusion": "failure", "run_attempt": 1,
             "steps": [step("Set up job", "failure")]}],
    }
    monkeypatch.setattr(numbers, "runs", lambda top, slug, w: runs)
    monkeypatch.setattr(
        numbers, "_gh_json",
        lambda top, path: {"jobs": jobs[int(path.split("/runs/")[1].split("/")[0])]},
    )
    cache: dict = {}
    result = numbers.harness_share(tmp_path, "o/r", numbers.Window("w", 0, 1), cache)
    assert result == {"share": 0.667, "harness": 2, "red_jobs": 3, "runs": 4}
    assert set(cache["jobs"]) == {"1:1", "3:1", "4:1"}  # completed runs are cached


def test_minutes_per_day_splits_at_the_cut(monkeypatch, tmp_path):
    import datetime as dt

    cut_ts = dt.datetime(2026, 10, 6, 12, tzinfo=dt.timezone.utc).timestamp()
    now = dt.datetime(2026, 10, 9, 12, tzinfo=dt.timezone.utc).timestamp()
    items = [
        {"date": "2026-09-20T00:00:00Z", "product": "actions", "repositoryName": "r", "unitType": "Minutes", "quantity": 600},
        {"date": "2026-10-06T00:00:00Z", "product": "actions", "repositoryName": "r", "unitType": "Minutes", "quantity": 300},
        {"date": "2026-10-07T00:00:00Z", "product": "actions", "repositoryName": "r", "unitType": "Minutes", "quantity": 4},
        {"date": "2026-10-08T00:00:00Z", "product": "actions", "repositoryName": "r", "unitType": "Minutes", "quantity": 2},
        {"date": "2026-10-08T00:00:00Z", "product": "actions", "repositoryName": "other", "unitType": "Minutes", "quantity": 99},
    ]
    seen = []

    def fake(top, path):
        seen.append(path)
        return {"usageItems": [i for i in items if f"month={int(i['date'][5:7])}" in path]}

    monkeypatch.setattr(numbers, "_gh_json", fake)
    result = numbers.minutes_per_day(tmp_path, "o", "r", cut_ts, now)
    assert result == {"before_per_day": 20.0, "since_per_day": 3.0, "since_days": 2}
    assert any("month=9" in p for p in seen) and any("month=10" in p for p in seen)


def test_render_says_n_and_never_compares_with_the_evidence_figures():
    n = {
        "cut": "2026-10-06",
        "before": {"rework": {"share": 0.4, "rework": 4, "counted": 10}, "catch": None,
                   "harness": {"share": 0.5, "harness": 1, "red_jobs": 2}},
        "since": {"rework": {"share": None, "rework": 0, "counted": 0}, "catch": {"share": None, "tagged": 0},
                  "harness": None, "ceremony": {"ceremony_share": 0.2, "messages": 5}},
        "minutes": {"before_per_day": 413.0, "since_per_day": None, "since_days": 0},
    }
    text = "\n".join(numbers.render(n))
    assert "40% (4/10)" in text and "-- (n=0)" in text and "could not look" in text
    assert "another instrument" in text and "413" in text
