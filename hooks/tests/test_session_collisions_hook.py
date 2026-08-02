"""The session-collision hook, driven the way the harness drives it.

A hook is uniquely easy to break silently: it has no importers, it produces no
diff, and its whole contract is to fail open — so a dead one emits nothing and
exits 0, exactly like a healthy one with nothing to say. A suite like this exists
because a dropped `import json` did precisely that once and nothing noticed.
This hook has a second, sharper version of the same edge: it is *supposed* to be
silent most of the time, so "no output" is its normal state and cannot be read as
health.

The properties pinned here, in order of how badly getting them wrong would hurt:

- **It finds sessions in OTHER worktrees.** This is the whole point, and the
  first draft got it wrong: the harness keys a project directory on the launch
  path, so a session started inside a worktree gets its own directory and a
  single-directory scan finds only itself. That version ran green, emitted
  nothing, and looked identical to "no collisions".
- **It announces the right hook event.** `additionalContext` under the wrong
  `hookEventName` is dropped by the harness silently, with a zero exit.
- **It never blocks.** Malformed payload, missing tree, unreadable transcript —
  every one exits 0.

Run with: ``python -m pytest hooks/tests/ -q``
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = PLUGIN_ROOT / "hooks" / "session_collisions.py"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"


def _base_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"}


def _fire(payload: object, config_home: pathlib.Path) -> str:
    """Run the hook exactly as the harness does: subprocess, JSON on stdin."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**_base_env(), "CLAUDE_CONFIG_DIR": str(config_home)},
    )
    assert result.returncode == 0, f"hook must never block: {result.stderr}"
    return result.stdout


def _context(stdout: str) -> str:
    if not stdout.strip():
        return ""
    payload = json.loads(stdout)
    block = payload["hookSpecificOutput"]
    assert block["hookEventName"] == "SessionStart", (
        "context under the wrong event name is dropped by the harness, silently"
    )
    return block["additionalContext"]


@pytest.fixture
def workspace(tmp_path: pathlib.Path) -> pathlib.Path:
    """A minimal repo — `find_repo_root` keys on `.git`, in any language."""
    (tmp_path / ".git").mkdir()
    return tmp_path


def _set_branch(repo: pathlib.Path, branch: str) -> None:
    """Point the repo's HEAD at `branch`.

    Written directly rather than shelling out to git: the hook reads `.git/HEAD`
    itself, so this drives the same file it consumes and needs no git binary.
    """
    (repo / ".git" / "HEAD").write_text(f"ref: refs/heads/{branch}\n", encoding="utf-8")


def _slug(path: pathlib.Path) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(path))


def _transcript(
    project_dir: pathlib.Path,
    session: str,
    *,
    title: str,
    branch: str,
    cwd: str,
) -> None:
    project_dir.mkdir(parents=True, exist_ok=True)
    records = [
        {"type": "custom-title", "customTitle": title},
        {"type": "user", "gitBranch": branch, "cwd": cwd},
    ]
    (project_dir / f"{session}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )


def test_a_session_in_another_worktree_is_reported(
    workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The case the first draft missed entirely.

    The sibling's transcript lives in its OWN project directory, keyed on the
    worktree path — not in this session's. A scan of one directory finds nobody.
    """
    home = tmp_path / "cfg"
    mine = home / "projects" / "repo-slug"
    theirs = home / "projects" / "repo-slug--worktrees-feature"
    _transcript(mine, "me", title="my work", branch="main", cwd=str(workspace))
    _transcript(
        theirs,
        "them",
        title="contract types",
        branch="claude/contract-types",
        cwd=str(workspace / "wt" / "contract-types"),
    )
    # Both directories must share the prefix the hook derives from the repo path.
    for directory in (mine, theirs):
        directory.rename(
            directory.parent / directory.name.replace("repo-slug", _slug(workspace))
        )

    context = _context(_fire({"session_id": "me", "cwd": str(workspace)}, home))

    assert "contract types" in context
    assert "claude/contract-types" in context


def test_the_current_session_is_not_reported_as_its_own_rival(
    workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    home = tmp_path / "cfg"
    _transcript(
        home / "projects" / _slug(workspace),
        "me",
        title="only me",
        branch="main",
        cwd=str(workspace),
    )

    assert _context(_fire({"session_id": "me", "cwd": str(workspace)}, home)) == ""


def test_a_stale_session_falls_outside_the_window(
    workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Yesterday's finished session is not a rival, and reporting it as one is
    how a useful warning becomes noise the reader learns to skip."""
    home = tmp_path / "cfg"
    project = home / "projects" / _slug(workspace)
    _transcript(project, "me", title="mine", branch="main", cwd=str(workspace))
    _transcript(
        project, "old", title="yesterday", branch="claude/old", cwd=str(workspace)
    )
    fresh = (project / "me.jsonl").stat().st_mtime
    os.utime(project / "old.jsonl", (fresh - 60 * 60 * 24, fresh - 60 * 60 * 24))

    assert _context(_fire({"session_id": "me", "cwd": str(workspace)}, home)) == ""


def test_a_shared_branch_is_called_out_as_a_collision(
    workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """Two sessions on one branch is the loudest case: whoever commits second
    is building on a tree the other is already changing."""
    _set_branch(workspace, "claude/shared")
    home = tmp_path / "cfg"
    project = home / "projects" / _slug(workspace)
    _transcript(
        project, "me", title="mine", branch="claude/shared", cwd=str(workspace)
    )
    _transcript(
        project,
        "them",
        title="same branch",
        branch="claude/shared",
        cwd=str(workspace / "wt"),
    )

    context = _context(_fire({"session_id": "me", "cwd": str(workspace)}, home))

    assert "COLLISION" in context
    assert "claude/shared" in context


def test_a_shared_issue_number_is_called_out(
    workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    """The duplicate-claim case: two different branches, one work item."""
    _set_branch(workspace, "claude/issue-325-mine")
    home = tmp_path / "cfg"
    project = home / "projects" / _slug(workspace)
    _transcript(
        project, "me", title="mine", branch="claude/issue-325-mine", cwd=str(workspace)
    )
    _transcript(
        project,
        "them",
        title="scaffold",
        branch="claude/issue-325-theirs",
        cwd=str(workspace / "wt"),
    )

    context = _context(_fire({"session_id": "me", "cwd": str(workspace)}, home))

    assert "COLLISION" in context
    assert "325" in context


# --- it never blocks -------------------------------------------------------- #
@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        json.dumps({"cwd": "/nonexistent/path/xyz"}),
        json.dumps({}),
    ],
)
def test_bad_input_exits_zero_and_says_nothing(
    payload: str, tmp_path: pathlib.Path
) -> None:
    assert _fire(payload, tmp_path / "cfg").strip() == ""


def test_a_missing_config_home_is_survivable(
    workspace: pathlib.Path, tmp_path: pathlib.Path
) -> None:
    assert (
        _fire({"session_id": "me", "cwd": str(workspace)}, tmp_path / "absent").strip()
        == ""
    )


def test_the_hook_is_registered_for_sessionstart() -> None:
    """A correct hook nobody wired up is the same as no hook — and this one
    cannot self-report, because silence is its normal output."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entry in config["hooks"].get("SessionStart", [])
        for hook in entry["hooks"]
    ]
    assert any("session_collisions.py" in c for c in commands), (
        "session_collisions.py is not registered under SessionStart in hooks/hooks.json"
    )
