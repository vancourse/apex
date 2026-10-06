"""status_forge: a commit status is posted from a receipt, never by hand."""

from __future__ import annotations

import pytest

from rails.gates import status_forge


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/acme/app/statuses/4f2c9e1 -f state=success -f context=rails/suite",
        "gh api -X POST /repos/{owner}/{repo}/statuses/$SHA -F state=success",
        "gh api --method POST repos/acme/app/statuses/abc --input status.json",
        'gh api "repos/acme/app/statuses/$(git rev-parse HEAD)" --field state=success',
        'curl -X POST -d \'{"state":"success"}\' https://api.github.com/repos/a/b/statuses/abc',
        "git rev-parse HEAD && gh api repos/a/b/statuses/abc -fstate=success",
    ],
)
def test_bash_forged_statuses_are_denied(verdict, command):
    assert verdict(status_forge, command) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/acme/app/commits/abc/statuses",
        "gh api repos/acme/app/commits/abc/status",
        "gh api repos/acme/app/statuses/abc",
        "gh api -X GET repos/acme/app/statuses/abc -f per_page=100",
        "rails check --post",
        "rails post",
        "gh pr checks 42",
        "echo 'gh api repos/a/b/statuses/abc -f state=success'",
    ],
)
def test_reads_and_the_rails_cli_pass(verdict, command):
    assert verdict(status_forge, command) == "allow", command


@pytest.mark.parametrize(
    "command",
    [
        "gh api repos/acme/app/statuses/abc -f state=success",
        "Invoke-RestMethod -Method Post -Uri https://api.github.com/repos/a/b/statuses/abc -Body $json",
        "irm https://api.github.com/repos/a/b/statuses/abc -Method POST",
    ],
)
def test_powershell_forged_statuses_are_denied(verdict, command):
    assert verdict(status_forge, command, tool="PowerShell") == "deny", command


def test_the_message_names_the_receipt_path(reason):
    text = reason(status_forge, "gh api repos/a/b/statuses/abc -f state=success")
    assert (
        "statuses are posted by `rails check --post` from a receipt; post them that way"
        in text
    )


def test_only_the_operator_environment_overrides(verdict, monkeypatch):
    command = "gh api repos/a/b/statuses/abc -f state=success"
    assert verdict(status_forge, f"RAILS_STATUS_FORGE_OK=1 {command}") == "deny"
    monkeypatch.setenv("RAILS_STATUS_FORGE_OK", "1")
    assert verdict(status_forge, command) == "allow"
