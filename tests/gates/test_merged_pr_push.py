"""merged_pr_push: cases ported from jarvis ci/test_merged_pr_push_gate.py.

The PR lookup comes from a fixture file, so the gate is driven without the
network; the `gh` path itself is exercised for its fail-open contract.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from rails.gates import merged_pr_push
from rails.gates.merged_pr_push import merged_and_unwatched, target_branches

LOOKUP = {
    "merged-line": [{"number": 2185, "state": "MERGED"}],
    "merged-twice": [
        {"number": 2185, "state": "MERGED"},
        {"number": 2187, "state": "MERGED"},
    ],
    "reopened-line": [
        {"number": 2185, "state": "MERGED"},
        {"number": 2190, "state": "OPEN"},
    ],
    "open-line": [{"number": 2191, "state": "OPEN"}],
    "closed-unmerged": [{"number": 2192, "state": "CLOSED"}],
    "fresh-line": [],
}

DENIED = [
    "git push origin HEAD:merged-line",
    "git push -u origin merged-line",
    "git push origin merged-line",
    "git push -q origin HEAD:merged-twice",
    "JARVIS_PUSH_OK=1 git push -q origin HEAD:merged-line",
    "git -C /some/worktree push origin merged-line",
    "git fetch origin && git push origin HEAD:merged-line",
    "git push --force-with-lease origin merged-line",
    "git push origin HEAD:refs/heads/merged-line",
]

ALLOWED = [
    "git push origin HEAD:open-line",
    "git push -u origin fresh-line",
    "git push origin HEAD:reopened-line",
    "git push origin closed-unmerged",
    "git push origin --delete merged-line",
    "git push origin :merged-line",
    "git push origin v1.2.3:refs/tags/v1.2.3",
    "git push --tags origin",
    "git status && git log --oneline -3",
    "echo 'git push origin HEAD:merged-line'",
    'gh pr comment 1 --body "then git push origin merged-line"',
    "git push origin HEAD:merged-line  # merged-ok",
    "gh pr view 2185 --json state",
]


@pytest.fixture
def lookup(tmp_path, monkeypatch):
    path = tmp_path / "lookup.json"
    path.write_text(json.dumps(LOOKUP), encoding="utf-8")
    monkeypatch.setenv("RAILS_PR_LOOKUP_FIXTURE", str(path))
    return path


@pytest.mark.parametrize("command", DENIED)
def test_a_push_onto_a_merged_unwatched_branch_is_refused(verdict, lookup, command):
    assert verdict(merged_pr_push, command) == "deny", command


@pytest.mark.parametrize("command", ALLOWED)
def test_every_other_push_and_every_quote_of_one_passes(verdict, lookup, command):
    assert verdict(merged_pr_push, command) == "allow", command


@pytest.mark.parametrize(
    "command",
    [
        "git push origin HEAD:merged-line",
        "$env:JARVIS_PUSH_OK=1; git push -u origin merged-line",
        "& git push origin merged-line",
    ],
)
def test_powershell_push_onto_a_merged_branch_is_refused(verdict, lookup, command):
    assert verdict(merged_pr_push, command, tool="PowerShell") == "deny", command


def test_powershell_quoted_push_passes(verdict, lookup):
    command = "Write-Output 'git push origin merged-line'"
    assert verdict(merged_pr_push, command, tool="PowerShell") == "allow"


def test_the_original_fixture_variable_still_works(verdict, tmp_path, monkeypatch):
    path = tmp_path / "lookup.json"
    path.write_text(json.dumps(LOOKUP), encoding="utf-8")
    monkeypatch.setenv("JARVIS_PR_LOOKUP_FIXTURE", str(path))
    assert verdict(merged_pr_push, "git push origin merged-line") == "deny"


def test_a_bare_push_is_judged_on_the_checked_out_branch(verdict, lookup, tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "merged-line", str(repo)], check=True, timeout=60
    )
    assert verdict(merged_pr_push, "git push", cwd=repo) == "deny"


def test_when_nothing_can_answer_the_push_passes(verdict, tmp_path, monkeypatch):
    monkeypatch.setenv("RAILS_PR_LOOKUP_FIXTURE", str(tmp_path / "absent.json"))
    assert verdict(merged_pr_push, "git push origin HEAD:merged-line") == "allow"


def test_gh_failure_or_timeout_fails_open(verdict, monkeypatch):
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=kwargs.get("timeout"))

    monkeypatch.setattr(merged_pr_push.subprocess, "run", boom)
    assert verdict(merged_pr_push, "git push origin HEAD:merged-line") == "allow"


def test_gh_is_called_with_a_bounded_timeout(verdict, monkeypatch):
    seen = {}

    class Done:
        returncode = 0
        stdout = json.dumps([{"number": 7, "state": "MERGED"}])

    def fake(argv, **kwargs):
        seen["argv"] = argv
        seen["timeout"] = kwargs.get("timeout")
        return Done()

    monkeypatch.setattr(merged_pr_push.subprocess, "run", fake)
    assert verdict(merged_pr_push, "git push origin HEAD:feature") == "deny"
    assert seen["argv"][:4] == ["gh", "pr", "list", "--head"]
    assert seen["timeout"] is not None and seen["timeout"] <= 10


@pytest.mark.parametrize("name", ["JARVIS_MERGED_PUSH_OK", "RAILS_MERGED_PUSH_OK"])
def test_the_operator_override_reaches_only_the_operator(
    verdict, lookup, monkeypatch, name
):
    monkeypatch.setenv(name, "1")
    assert verdict(merged_pr_push, "git push origin HEAD:merged-line") == "allow"


def test_a_non_shell_tool_is_untouched(verdict, lookup):
    assert verdict(merged_pr_push, tool="Write", file_path="x") == "allow"


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ("origin HEAD:feature", ["feature"]),
        ("-u origin feature", ["feature"]),
        ("origin feature", ["feature"]),
        ("origin HEAD:refs/heads/feature", ["feature"]),
        ("--force-with-lease origin +HEAD:feature", ["feature"]),
        ("", [None]),
        ("origin", [None]),
        ("-q origin", [None]),
        ("origin --delete feature", []),
        ("origin :feature", []),
        ("origin v1:refs/tags/v1", []),
        ("--tags origin", []),
        ("-o ci.skip origin feature", ["feature"]),
        ("origin a:x b:y", ["x", "y"]),
    ],
)
def test_the_targets_of_a_push(args, expected):
    assert target_branches(args) == expected


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([{"number": 1, "state": "MERGED"}], [1]),
        ([{"number": 1, "state": "merged"}], [1]),
        ([{"number": 1, "state": "MERGED"}, {"number": 2, "state": "OPEN"}], []),
        ([{"number": 1, "state": "CLOSED"}], []),
        ([], []),
        ([{"number": 1, "state": "MERGED"}, {"number": 2, "state": "MERGED"}], [1, 2]),
    ],
)
def test_merged_and_unwatched(rows, expected):
    assert merged_and_unwatched(rows) == expected
