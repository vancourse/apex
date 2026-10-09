"""pipe_mask: cases ported from jarvis ci/test_pipe_mask_gate.py, plus PowerShell.

Both edges are pinned. Too loud blocks read-only pipes, the pipefail remedy and
prose in commit messages; too mute is a gate that stopped firing with nothing
to show for it.
"""

from __future__ import annotations

import pytest

from rails.gates import pipe_mask

OBSERVED_PYTEST = "uv run pytest -q ci/ 2>&1 | tail -40"
OBSERVED_GH_EDIT = "gh pr edit 1197 --body-file body.md | tail -2"


def test_denies_the_observed_shapes(verdict):
    assert verdict(pipe_mask, OBSERVED_PYTEST) == "deny"
    assert verdict(pipe_mask, OBSERVED_GH_EDIT) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "git push -u origin branch 2>&1 | tail -3",
        "git commit -F msg.txt | tail -1",
        "gh pr create --title t --body-file b.md | head -1",
        "gh pr merge 42 --squash --auto | tail -2",
        "gh issue create --title t --body-file b.md | grep -oE '[0-9]+$'",
        "pytest ci/test_hooks.py -q | grep -c passed",
        "pytest -q | wc -l",
        "cd /repo && uv run pytest -q 2>&1 | tail -20",
        "pytest -q 2>&1 | sed 's/x/y/' ",
        "python -m pytest -q | tail -5",
        "uv run --no-project --with pytest python -m pytest tests -q | tail -30",
        ".venv/bin/pytest -q | tail",
        "git status\npytest -q | tail -3",
    ],
)
def test_denies_every_masking_shape(verdict, command):
    assert verdict(pipe_mask, command) == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "set -o pipefail; uv run pytest -q ci/ 2>&1 | tail -40",
        "uv run pytest -q > out.txt; tail -40 out.txt",
        "git push -u origin branch",
        "gh pr create --title t --body-file b.md",
        "uv run pytest -q ci/test_hooks.py",
        "gh pr view 1223 --json state | head -5",
        "git log --oneline | head -10",
        "git status --short | wc -l",
        "grep -rn 'pattern' ci/ | tail -5",
        "gh run list --limit 5 | grep ci",
        "pytest -q 2>&1 | tee log.txt",
        'git commit -m "document the pytest | tail trap"',
        "echo 'never run pytest | tail'",
        "cat cases.txt | xargs pytest -q",
        "git fetch origin master",
        "ls -la",
        # Outside the original's list, measured live 2026-10-06: the word
        # `pytest` inside a FILENAME is not a test run.
        "cat pytest.ini | tail -3",
        "grep -n addopts pytest.ini | head",
        # Quoted separators no longer split a quoted message into two statements.
        'git commit -m "a; b" && git log | head -3',
    ],
)
def test_allows_remedies_and_ordinary_commands(verdict, command):
    assert verdict(pipe_mask, command) == "allow", command


def test_prose_inside_a_heredoc_body_cannot_arm_the_gate(verdict):
    commit = (
        "git commit -F - <<'EOF'\n"
        "feat(hooks): refuse a masked exit code\n\n"
        "The shape `pytest | tail -40` reports tail's 0, not pytest's 4.\n"
        "Same for git push 2>&1 | tail -3.\n"
        "EOF"
    )
    assert verdict(pipe_mask, commit) == "allow"


def test_a_pipe_on_the_heredoc_opener_line_is_still_seen(verdict):
    assert verdict(pipe_mask, "git commit -F - <<'EOF' | tail -1\nmsg\nEOF") == "deny"


def test_an_unterminated_heredoc_fails_open(verdict):
    command = "git commit -F - <<'EOF'\npytest | tail with no terminator"
    assert verdict(pipe_mask, command) == "allow"


def test_a_very_long_command_does_not_hang(verdict):
    assert verdict(pipe_mask, "echo " + "a" * 20000) == "allow"


def test_message_names_the_remedy_and_override(reason):
    text = reason(pipe_mask, OBSERVED_PYTEST)
    assert "set -o pipefail" in text
    assert "JARVIS_PIPE_OK=1" in text


# --- PowerShell ------------------------------------------------------------------


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest -q 2>&1 | Select-Object -Last 40",
        "git push origin HEAD:feature 2>&1 | Select-Object -First 3",
        "gh pr edit 12 --body-file b.md | select -first 1",
        "pytest -q | Select-String passed",
        "pytest -q | Measure-Object -Line",
        "git commit -F msg.txt | Out-String",
        "uv run pytest -q | tail -40",
        "& pytest -q | findstr FAILED",
    ],
)
def test_powershell_masking_shapes_are_denied(verdict, command):
    assert verdict(pipe_mask, command, tool="PowerShell") == "deny", command


@pytest.mark.parametrize(
    "command",
    [
        "git log --oneline | Select-Object -First 10",
        "Get-Content pytest.ini | Select-Object -Last 3",
        "uv run pytest -q *> out.txt; Get-Content out.txt -Tail 40",
        "git commit -m 'the pytest | Select-Object -First 1 trap'",
        "pytest -q | Select-Object Name",
    ],
)
def test_powershell_reads_and_quoted_prose_pass(verdict, command):
    assert verdict(pipe_mask, command, tool="PowerShell") == "allow", command


def test_powershell_message_names_its_own_remedy(reason):
    text = reason(pipe_mask, "pytest -q | Select-Object -First 5", tool="PowerShell")
    assert "$LASTEXITCODE" in text
    assert "$env:JARVIS_PIPE_OK=1;" in text
    assert "set -o pipefail" not in text


# --- overrides ---------------------------------------------------------------------


def test_override_as_documented_allows(verdict):
    assert verdict(pipe_mask, f"JARVIS_PIPE_OK=1 {OBSERVED_PYTEST}") == "allow"
    assert verdict(pipe_mask, f"RAILS_PIPE_OK=1 {OBSERVED_PYTEST}") == "allow"


def test_powershell_override_allows(verdict):
    command = "$env:RAILS_PIPE_OK=1; pytest -q | Select-Object -First 5"
    assert verdict(pipe_mask, command, tool="PowerShell") == "allow"


def test_empty_override_does_not_allow(verdict):
    assert verdict(pipe_mask, f"JARVIS_PIPE_OK= {OBSERVED_PYTEST}") == "deny"


def test_operator_environment_override_allows(verdict, monkeypatch):
    monkeypatch.setenv("RAILS_PIPE_OK", "1")
    assert verdict(pipe_mask, OBSERVED_PYTEST) == "allow"


def test_non_shell_tools_are_untouched(verdict):
    assert verdict(pipe_mask, OBSERVED_PYTEST, tool="Read") == "allow"


@pytest.mark.parametrize(
    "command",
    [
        "timeout 900 uv run pytest -q ci/ 2>&1 | tail -40",
        "env PYTHONUTF8=1 uv run pytest -q | tail -5",
        "nice pytest -q | tail",
        "py -3 -m pytest | tail",
        "python -X utf8 -m pytest | tail",
        "xvfb-run pytest | grep passed",
        "coverage run -m pytest | tail",
    ],
)
def test_a_wrapper_still_runs_pytest(command):
    """jarvis's copy caught these by the bare word; jarvis now relies on this one (1.3.0)."""
    assert pipe_mask._STATUS_BEARING.search(command)
