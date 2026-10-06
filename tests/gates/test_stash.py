"""stash: cases ported from jarvis ci/test_stash_gate.py, run in both shells."""

from __future__ import annotations

import pytest

from rails.gates import stash

DENIED = [
    "git stash",
    "git stash push -m 'wip'",
    "git stash save wip",
    "git stash pop",
    "git stash apply",
    "git stash drop",
    "git stash clear",
    "git -C /some/worktree stash",
    "git status && git stash",
    "git stash -u",
    # New in the port: a stash on its own line, and inside a group.
    "git status\ngit stash",
    "(git stash)",
]

ALLOWED = [
    "git status --porcelain",
    "git stash list",
    "git stash show -p",
    "git add -A && git commit -m wip",
    "pnpm -C apps/sherpa/frontend gate:a",
    "echo 'never git stash here'",
    'gh issue comment 1 --body "do not git stash"',
    "git stash  # stash-ok",
    'git commit -m "note: do not; git stash here"',
    "git commit -F - <<'EOF'\nnever git stash\nEOF",
]


@pytest.mark.parametrize("command", DENIED)
def test_a_stash_that_pushes_or_consumes_is_refused(verdict, command):
    assert verdict(stash, command) == "deny", command


@pytest.mark.parametrize("command", ALLOWED)
def test_reading_the_stack_and_quoting_the_rule_both_pass(verdict, command):
    assert verdict(stash, command) == "allow", command


@pytest.mark.parametrize(
    "command",
    [
        "git stash",
        "git -C C:\\Users\\dev\\repo stash; git pull --ff-only",
        "& git stash pop",
        "git status; git stash apply",
        "Set-Location C:\\repo\ngit stash -u",
        "& { git stash }",
    ],
)
def test_powershell_stash_is_refused(verdict, command):
    assert verdict(stash, command, tool="PowerShell") == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "git stash list",
        "Write-Output 'never git stash here'",
        "git commit -m @'\nnote; git stash\n'@",
        "git stash  # stash-ok",
    ],
)
def test_powershell_reads_and_quotes_pass(verdict, command):
    assert verdict(stash, command, tool="PowerShell") == "allow", command


@pytest.mark.parametrize("name", ["JARVIS_STASH_OK", "RAILS_STASH_OK"])
def test_the_operator_override_reaches_only_the_operator(verdict, monkeypatch, name):
    assert verdict(stash, "git stash") == "deny"
    monkeypatch.setenv(name, "1")
    assert verdict(stash, "git stash") == "allow"


def test_a_text_prefix_is_not_an_override(verdict):
    """The original's override is the environment or `# stash-ok`, never a prefix."""
    assert verdict(stash, "JARVIS_STASH_OK=1 git stash") == "deny"


def test_the_message_names_the_commit_remedy_per_shell(reason):
    assert "git add -A && git commit" in reason(stash, "git stash")
    assert "git add -A; git commit" in reason(stash, "git stash", tool="PowerShell")


def test_a_non_shell_tool_is_untouched(verdict):
    assert verdict(stash, tool="Write", content="git stash", file_path="x") == "allow"
