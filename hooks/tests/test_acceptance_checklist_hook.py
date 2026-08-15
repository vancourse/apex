"""The acceptance-checklist hook's tests.

This is the only apex hook that shells out to the forge, so the fixture below puts a
**fake `gh` on PATH** — a script that answers `gh issue view` from a file and can be
told to fail. That is the seam worth testing: the hook's most important behaviour is
what it says when the issue read does *not* work, and a stubbed-out Python function
would never exercise the path where `gh` itself is missing or unauthenticated.

Two properties dominate:

1. **It stays silent unless there is something to inject.** It runs in front of a
   `gh pr create` a person is waiting on. A hook that fires on a PR whose body is
   already correct is one that gets disabled.
2. **A failed read is stated, never swallowed.** "This issue has no criteria" and
   "the token could not read this issue" produce identical silence, and the first is
   what the reader will assume. Two tests pin that they are distinguishable.

Run with ``python -m pytest hooks/tests/ -q``.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import uuid

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = PLUGIN_ROOT / "hooks" / "acceptance_checklist.py"

ISSUE_BODY = """\
### Kind

Capability — new behaviour

### Done when

- the golden test compares both lanes and asserts the rows match
- `ingest --dry-run` exits 0 on the customer export

### Production caller

- apps/ingest/loader.py
"""


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


@pytest.fixture
def fake_gh(tmp_path: pathlib.Path) -> pathlib.Path:
    """A `gh` that answers `issue view` from `issue.md`, or fails if `fail` exists.

    A real script on PATH rather than a patched function, because the contract under
    test includes what happens when the *process* fails — a missing token, a rate
    limit, `gh` not installed at all.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (tmp_path / "issue.md").write_text(ISSUE_BODY, encoding="utf-8")
    script = bindir / "gh"
    script.write_text(
        "#!/bin/sh\n"
        f'if [ -f "{tmp_path}/fail" ]; then\n'
        '  echo "gh: not authenticated" >&2\n'
        "  exit 1\n"
        "fi\n"
        f'cat "{tmp_path}/issue.md"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)
    return bindir


def _run(payload: str, bindir: pathlib.Path) -> str:
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PATH": f"{bindir}:{os.environ.get('PATH', '')}"},
    )
    assert result.returncode == 0, (
        f"the hook must always exit 0 — a non-zero exit blocks the tool call.\n"
        f"stderr: {result.stderr}"
    )
    return result.stdout.strip()


def _bash(command: str, repo: pathlib.Path, bindir: pathlib.Path) -> str:
    return _run(
        json.dumps(
            {
                "session_id": f"s-{uuid.uuid4()}",
                "cwd": str(repo),
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        ),
        bindir,
    )


def _context(raw: str) -> str:
    emitted = json.loads(raw)["hookSpecificOutput"]
    assert emitted["hookEventName"] == "PreToolUse"
    return emitted["additionalContext"]


# ── silence ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --body 'Refactors the loader.'",
        "gh pr create --body 'Related to #7, see also #9.'",
        "gh pr create --title 'x'",
        "gh issue create --body 'Closes #7'",
        "git commit -m 'gh pr create --body \"Closes #7\"'",
        "echo 'Closes #7'",
    ],
)
def test_commands_with_nothing_to_check_are_silent(
    repo: pathlib.Path, fake_gh: pathlib.Path, command: str
) -> None:
    """A body that merely *links* `#7` is not closing it, and a `gh issue create` is
    not a PR. None of these has anything to inject."""
    assert _bash(command, repo, fake_gh) == ""


def test_a_git_commit_that_merely_mentions_the_command_is_silent(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """PLANTED: match `gh pr create` as a substring rather than as consecutive tokens,
    and this fires — it reads the *commit's* `-F` as the PR body and demands a
    checklist from a commit. That is the measured false positive that already cost the
    sibling artifact-template hook a fix.

    The `-F` is the part that matters, and mutation testing is what surfaced it: an
    earlier version of this case put the whole phrase inside `-m`, where the substring
    mutation still found no body flag and stayed accidentally silent. The false
    positive needs a real body flag *outside* the quoted message to reproduce.
    """
    (repo / "msg.md").write_text("Closes #7\n", encoding="utf-8")
    command = "git commit -F msg.md -m 'ported from gh pr create'"
    assert _bash(command, repo, fake_gh) == ""


def test_an_unreadable_body_file_path_is_never_read_as_the_body(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """PLANTED: accept the `"unreadable"` kind alongside `"text"` and the hook scans
    the *path string* for closing keywords. The filename here is contrived on purpose
    — it is the smallest thing that makes the confusion observable — but the contract
    it pins is not: a path is not a body, and a `--body-file` a hook cannot open tells
    it nothing at all about what the PR closes."""
    assert _bash('gh pr create --body-file "$DIR/closes #7.md"', repo, fake_gh) == ""


def test_a_fully_ticked_body_is_silent(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """PLANTED: emit unconditionally once a body closes an issue, and the hook
    interrupts every correct PR to tell it that it is correct. It runs in front of a
    `gh pr create` somebody is waiting on."""
    (repo / "body.md").write_text(
        "Closes #7\n\n"
        "- [x] the golden test compares both lanes and asserts the rows match\n"
        "- [x] `ingest --dry-run` exits 0 on the customer export\n",
        encoding="utf-8",
    )
    assert _bash("gh pr create --body-file body.md", repo, fake_gh) == ""


def test_prose_acceptance_is_silent(
    repo: pathlib.Path, fake_gh: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The issue states acceptance as a paragraph, so there is nothing to inject —
    and nothing wrong. Silence is the correct answer, not an omission."""
    (tmp_path / "issue.md").write_text(
        "### Done when\n\nIt should handle the customer export sensibly.\n",
        encoding="utf-8",
    )
    assert _bash("gh pr create --body 'Closes #7'", repo, fake_gh) == ""


def test_an_unreadable_body_file_is_silent(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """A hook sees the command before the shell expands it, so `--body-file "$SP/b.md"`
    arrives unexpanded and unreadable. That tells us nothing about what the PR closes;
    reporting "closes nothing" would be silent and wrong."""
    assert _bash('gh pr create --body-file "$SCRATCH/body.md"', repo, fake_gh) == ""


# ── the injection ─────────────────────────────────────────────────────────────


def test_unticked_criteria_are_injected_as_a_pasteable_block(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    context = _context(_bash("gh pr create --body 'Closes #7'", repo, fake_gh))
    assert "ACCEPTANCE" in context
    assert (
        "- [ ] the golden test compares both lanes and asserts the rows match"
        in context
    )
    assert "#7" in context


def test_the_touches_list_is_not_demanded(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """PLANTED: run extraction to the end of the issue body instead of stopping at the
    next heading, and the hook asks the author to tick off `apps/ingest/loader.py`.
    Pinned here as well as in the gate's own suite because the hook and the gate must
    agree — they share one implementation precisely so they cannot drift."""
    context = _context(_bash("gh pr create --body 'Closes #7'", repo, fake_gh))
    assert "loader.py" not in context


def test_it_fires_on_pr_edit_too(repo: pathlib.Path, fake_gh: pathlib.Path) -> None:
    """The measured shape is a draft opened on commit one and given its real body
    later, so the closes-line often first appears at `edit`, not `create`."""
    context = _context(_bash("gh pr edit 12 --body 'Closes #7'", repo, fake_gh))
    assert "ACCEPTANCE" in context


def test_it_reads_a_body_file_it_can_open(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    (repo / "body.md").write_text("Closes #7\n", encoding="utf-8")
    context = _context(_bash("gh pr create --body-file body.md", repo, fake_gh))
    assert "ACCEPTANCE" in context


def test_the_message_asks_for_honesty_not_ticks(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """A prompt that only offers "tick it" manufactures ticks. The out — say in the
    body that the criterion was wrong — has to be offered, or the check degrades into
    a formality that costs a paste and proves nothing."""
    context = _context(_bash("gh pr create --body 'Closes #7'", repo, fake_gh))
    assert "Tick honestly" in context
    assert "wrong" in context


# ── the failed read, which must be audible ────────────────────────────────────


def test_a_failed_issue_read_is_stated(
    repo: pathlib.Path, fake_gh: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """PLANTED: swallow the `ForgeReadError` and this returns nothing — identical to
    the prose-acceptance case above, which the reader will assume it was. The two must
    be distinguishable, which is the entire reason this hook speaks here at all."""
    (tmp_path / "fail").write_text("", encoding="utf-8")
    context = _context(_bash("gh pr create --body 'Closes #7'", repo, fake_gh))
    assert "Could NOT read #7" in context
    assert "not a report that they have no criteria" in context


def test_a_missing_gh_binary_is_stated_not_silent(repo: pathlib.Path) -> None:
    """The same requirement, one layer down: `gh` absent from PATH entirely."""
    empty = repo / "emptybin"
    empty.mkdir()
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(
            {
                "session_id": f"s-{uuid.uuid4()}",
                "cwd": str(repo),
                "tool_name": "Bash",
                "tool_input": {"command": "gh pr create --body 'Closes #7'"},
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": str(empty), "HOME": "/tmp"},
    )
    assert result.returncode == 0
    assert "Could NOT read #7" in _context(result.stdout.strip())


# ── the fail-open contract ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        '{"tool_name": "Bash"}',
        '{"tool_name": "Bash", "tool_input": {"command": "gh pr create --body \\"unclosed"}}',
        '{"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.md"}}',
    ],
)
def test_malformed_input_exits_zero_silently(
    payload: str, fake_gh: pathlib.Path
) -> None:
    assert _run(payload, fake_gh) == ""


def test_it_says_the_same_thing_only_once_per_command(
    repo: pathlib.Path, fake_gh: pathlib.Path
) -> None:
    """Enough to inform, not enough to nag — but keyed on the command, so a corrected
    retry is checked again rather than muted."""
    payload = json.dumps(
        {
            # A fresh id per run: `warn_once` markers live in the shared temp dir and
            # outlive the process, so a fixed id would make this pass once and then
            # fail on every subsequent run of the suite.
            "session_id": f"s-{uuid.uuid4()}",
            "cwd": str(repo),
            "tool_name": "Bash",
            "tool_input": {"command": "gh pr create --body 'Closes #7'"},
        }
    )
    assert _run(payload, fake_gh) != ""
    assert _run(payload, fake_gh) == ""
