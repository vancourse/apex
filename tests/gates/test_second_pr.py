"""second_pr: one line of work is one PR; the worktree's pr.json says which."""

from __future__ import annotations

import pytest

from rails import store
from rails.gates import second_pr

CREATE = "gh pr create --title 'slice 2' --body-file body.md"


def _record(repo, value) -> None:
    found = store.find_repo(repo)
    assert found is not None
    store.write_json(found.leaf_dir / "pr.json", value)


@pytest.fixture
def with_open_pr(repo):
    _record(repo, {"number": 41, "state": "OPEN", "armed": True})
    return repo


def test_a_second_pr_from_the_worktree_is_denied(verdict, reason, with_open_pr):
    assert verdict(second_pr, CREATE, cwd=with_open_pr) == "deny"
    assert "#41" in reason(second_pr, CREATE, cwd=with_open_pr)


def test_powershell_second_pr_is_denied(verdict, with_open_pr):
    command = "gh pr create --title 'slice 2' --body @'\nbody\n'@"
    assert verdict(second_pr, command, tool="PowerShell", cwd=with_open_pr) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "gh pr view 41",
        "gh pr edit 41 --body-file b.md",
        "git push",
        "echo 'gh pr create'",
    ],
)
def test_other_pr_commands_pass(verdict, with_open_pr, command):
    assert verdict(second_pr, command, cwd=with_open_pr) == "allow", command


def test_no_record_means_the_first_pr_passes(verdict, repo):
    assert verdict(second_pr, CREATE, cwd=repo) == "allow"


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_a_finished_pr_does_not_count(verdict, repo, state):
    _record(repo, {"number": 41, "state": state})
    assert verdict(second_pr, CREATE, cwd=repo) == "allow"


def test_outside_a_repo_passes(verdict, tmp_path):
    assert verdict(second_pr, CREATE, cwd=tmp_path) == "allow"


def test_the_override_needs_a_reason(verdict, with_open_pr):
    assert verdict(second_pr, f"{CREATE}  # second-pr-ok:", cwd=with_open_pr) == "deny"
    assert (
        verdict(
            second_pr,
            f"{CREATE}  # second-pr-ok: hotfix split from the feature line",
            cwd=with_open_pr,
        )
        == "allow"
    )


def test_operator_environment_overrides(verdict, with_open_pr, monkeypatch):
    monkeypatch.setenv("RAILS_SECOND_PR_OK", "1")
    assert verdict(second_pr, CREATE, cwd=with_open_pr) == "allow"
