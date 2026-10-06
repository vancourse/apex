"""merge_by_effect: every agent merge path but arming auto-merge is refused."""

from __future__ import annotations

import subprocess

import pytest

from rails.gates import merge_by_effect


@pytest.fixture
def on_main(tmp_path):
    repo = tmp_path / "on-main"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-q", "-b", "main", str(repo)], check=True, timeout=60
    )
    return repo


DENIED = [
    "gh api repos/acme/app/pulls/42/merge -X PUT -f merge_method=squash",
    "gh api -X PUT /repos/{owner}/{repo}/pulls/42/merge",
    "gh api repos/acme/app/merges -f base=main -f head=feature",
    "gh api graphql -f query='mutation { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
    "curl -X PUT -H 'Authorization: token x' https://api.github.com/repos/acme/app/pulls/42/merge",
    "gh pr merge 42 --admin --squash",
    "gh pr merge 42 --squash",
    "gh pr merge 42 --merge --auto",
    "gh pr merge --auto --rebase",
    "git push origin master",
    "git push origin HEAD:master",
    "git push origin +main",
    "git push origin feature:refs/heads/main",
    "git push --delete origin main",
    "git push --all origin",
    "git fetch && git push -u origin main",
]

ALLOWED = [
    "gh pr merge 42 --auto --squash",
    "gh pr merge 42 --auto --squash --delete-branch",
    "gh pr merge https://github.com/acme/app/pull/42 --auto -s -d",
    "gh pr merge --auto --squash -R acme/app 42",
    "gh api repos/acme/app/pulls/42",
    "gh api -X GET repos/acme/app/pulls/42/merge",
    "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }'",
    "gh pr view 42 --json mergedAt",
    "git push origin feature",
    "git push -u origin HEAD:feature/main-menu",
    "git push --dry-run origin main",
    "git push -n origin HEAD:master",
    'git commit -m "never git push origin main"',
    "echo 'gh pr merge 42 --admin'",
]


@pytest.mark.parametrize("command", DENIED)
def test_bash_merge_paths_are_denied(verdict, command):
    assert verdict(merge_by_effect, command) == "deny", command


@pytest.mark.parametrize("command", ALLOWED)
def test_arming_and_ordinary_work_pass(verdict, command):
    assert verdict(merge_by_effect, command) == "allow", command


@pytest.mark.parametrize(
    "command",
    [
        "gh pr merge 2443 --squash --admin --delete-branch",
        "& gh api -X PUT repos/acme/app/pulls/7/merge",
        "Invoke-RestMethod -Method Put -Uri https://api.github.com/repos/a/b/pulls/7/merge",
        "git push origin HEAD:main",
    ],
)
def test_powershell_merge_paths_are_denied(verdict, command):
    assert verdict(merge_by_effect, command, tool="PowerShell") == "deny", command


def test_powershell_arming_passes(verdict):
    assert (
        verdict(merge_by_effect, "gh pr merge 7 --auto --squash", tool="PowerShell")
        == "allow"
    )


def test_a_bare_push_on_the_default_branch_is_denied(verdict, on_main):
    assert verdict(merge_by_effect, "git push", cwd=on_main) == "deny"
    assert verdict(merge_by_effect, "git push origin HEAD", cwd=on_main) == "deny"


def test_the_message_names_the_arming_command(reason):
    assert "gh pr merge <n> --auto --squash" in reason(
        merge_by_effect, "gh pr merge 1 --admin"
    )


def test_only_the_operator_environment_overrides(verdict, monkeypatch):
    assert (
        verdict(merge_by_effect, "RAILS_MERGE_BY_EFFECT_OK=1 gh pr merge 1 --admin")
        == "deny"
    )
    monkeypatch.setenv("RAILS_MERGE_BY_EFFECT_OK", "1")
    assert verdict(merge_by_effect, "gh pr merge 1 --admin") == "allow"
