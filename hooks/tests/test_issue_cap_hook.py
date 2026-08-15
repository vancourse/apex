"""The issue-rate hook's tests — silence first, because silence is most of its job.

This hook says nothing on a session's first `gh issue create`, and the reason is the
same one that governs every gate here: **a hook that fires on correct work teaches the
reader to skip past it**, after which it is not there for the twelfth issue either.
One issue is a session doing its job. So the first block below pins the silence, and
it is longer than the block that pins the message.

The counter is deliberately outside the repo — a hook that writes into the working
tree makes every subsequent `git status` lie, and a `git add -A` commits its
bookkeeping into somebody's PR. `APEX_ISSUE_CAP_DIR` is how these tests drive it
without touching a real session's state, and one test asserts the tree stays clean.

Run with ``python -m pytest hooks/tests/ -q``.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import uuid

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = PLUGIN_ROOT / "hooks" / "issue_cap.py"


@pytest.fixture
def counter_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    directory = tmp_path / "counter"
    directory.mkdir()
    return directory


def _run(payload: str, counter_dir: pathlib.Path | None = None) -> str:
    env = {"PATH": "/usr/bin:/bin", "HOME": "/tmp"}
    if counter_dir is not None:
        env["APEX_ISSUE_CAP_DIR"] = str(counter_dir)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, (
        f"the hook must always exit 0 — a non-zero exit blocks the tool call.\n"
        f"stderr: {result.stderr}"
    )
    return result.stdout.strip()


def _bash(command: str, session: str, counter_dir: pathlib.Path) -> str:
    return _run(
        json.dumps(
            {
                "session_id": session,
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        ),
        counter_dir,
    )


def _context(raw: str) -> str:
    emitted = json.loads(raw)["hookSpecificOutput"]
    assert emitted["hookEventName"] == "PreToolUse"
    return emitted["additionalContext"]


# ── silence ───────────────────────────────────────────────────────────────────


def test_the_first_issue_of_a_session_is_silent(counter_dir: pathlib.Path) -> None:
    """PLANTED: drop the `count < 2` guard and the hook lectures every session that
    files one issue — which is a session doing its job. That is the fastest way to
    make a reader stop reading hooks."""
    assert _bash("gh issue create --title x", f"s-{uuid.uuid4()}", counter_dir) == ""


@pytest.mark.parametrize(
    "command",
    [
        "gh pr create --title x",
        "gh issue list",
        "gh issue view 12",
        "git commit -m 'mentions gh issue create in the message'",
        "echo 'gh issue create'",
        "ls",
    ],
)
def test_commands_that_do_not_file_an_issue_are_silent(
    counter_dir: pathlib.Path, command: str
) -> None:
    """Twice over: the second call would speak if the first had counted. `git commit`
    with the phrase in its message is the measured false positive that killed the
    substring version of this match in a sibling hook."""
    session = f"s-{uuid.uuid4()}"
    assert _bash(command, session, counter_dir) == ""
    assert _bash(command, session, counter_dir) == ""


def test_a_non_bash_tool_is_silent(counter_dir: pathlib.Path) -> None:
    assert (
        _run(
            json.dumps(
                {
                    "session_id": "s",
                    "tool_name": "Write",
                    "tool_input": {"file_path": "/tmp/x.md"},
                }
            ),
            counter_dir,
        )
        == ""
    )


def test_each_session_counts_separately(counter_dir: pathlib.Path) -> None:
    """PLANTED: key the counter on anything but the session and every session after
    the first one in a day is told it is over the rate — a claim about work it did
    not do."""
    _bash("gh issue create -t a", "session-one", counter_dir)
    assert _bash("gh issue create -t b", "session-two", counter_dir) == ""


# ── the message ───────────────────────────────────────────────────────────────


def test_the_second_issue_reports_the_count(counter_dir: pathlib.Path) -> None:
    session = f"s-{uuid.uuid4()}"
    _bash("gh issue create -t a", session, counter_dir)
    context = _context(_bash("gh issue create -t b", session, counter_dir))
    assert "issue #2" in context


def test_the_count_keeps_climbing(counter_dir: pathlib.Path) -> None:
    """A rate hook whose number is stuck at 2 is reporting nothing after the second
    issue, which is where it starts being worth reading."""
    session = f"s-{uuid.uuid4()}"
    for _ in range(4):
        _bash("gh issue create -t x", session, counter_dir)
    assert "issue #5" in _context(_bash("gh issue create -t y", session, counter_dir))


def test_the_message_carries_the_measurement_and_the_alternative(
    counter_dir: pathlib.Path,
) -> None:
    """The measurement is what makes this a finding rather than an opinion, and the
    alternative is what makes it actionable. A rate report with neither is nagging."""
    session = f"s-{uuid.uuid4()}"
    _bash("gh issue create -t a", session, counter_dir)
    context = _context(_bash("gh issue create -t b", session, counter_dir))
    assert "78%" in context
    assert "PR body" in context
    assert "not a refusal" in context


# ── the counter's location ────────────────────────────────────────────────────


def test_the_counter_never_touches_the_repo(tmp_path: pathlib.Path) -> None:
    """PLANTED: point `counter_dir()` at a repo-relative path and this goes red. A hook
    that dirties the working tree makes every `git status` lie, and a `git add -A`
    commits its bookkeeping into somebody's PR.

    This one deliberately does **not** set `APEX_ISSUE_CAP_DIR` — the override is the
    seam every other test here uses, and using it here would mean the default location
    was never exercised at all. `TMPDIR` redirects the real default instead, so the
    code path under test is the one that ships. (Found by mutation testing: the first
    version of this test passed with the counter writing into the repo.)
    """
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / "file.txt").write_text("x", encoding="utf-8")
    before = sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*"))

    temp = tmp_path / "tmp"
    temp.mkdir()
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(
            {
                "session_id": f"s-{uuid.uuid4()}",
                "cwd": str(repo),
                "tool_name": "Bash",
                "tool_input": {"command": "gh issue create -t a"},
            }
        ),
        capture_output=True,
        text=True,
        timeout=60,
        cwd=repo,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "TMPDIR": str(temp)},
    )
    assert result.returncode == 0, result.stderr
    assert sorted(p.relative_to(repo).as_posix() for p in repo.rglob("*")) == before
    assert list(temp.rglob("issue-cap-*")), "the counter went somewhere else entirely"


def test_an_unwritable_counter_directory_stays_silent(tmp_path: pathlib.Path) -> None:
    """Reporting 1 — the silent case — when the bookkeeping cannot be read. A hook
    that cannot measure should say nothing rather than assert a number it invented."""
    blocked = tmp_path / "file-not-a-dir"
    blocked.write_text("", encoding="utf-8")
    session = f"s-{uuid.uuid4()}"
    assert _bash("gh issue create -t a", session, blocked) == ""
    assert _bash("gh issue create -t b", session, blocked) == ""


# ── the fail-open contract ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        '{"tool_name": "Bash"}',
        '{"tool_name": "Bash", "tool_input": {"command": "gh issue create --title \\"unclosed"}}',
    ],
)
def test_malformed_input_exits_zero_silently(
    payload: str, counter_dir: pathlib.Path
) -> None:
    """Including a command `shlex` cannot tokenise. A hook that raises blocks the tool
    call, and the tool call here is somebody filing an issue."""
    assert _run(payload, counter_dir) == ""
