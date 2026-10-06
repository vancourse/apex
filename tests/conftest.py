"""Shared fixtures. Every test runs against a throwaway store and throwaway git repos.

Nothing here may touch the real ``~/.claude/rails`` or ``~/.claude/repo-claims``:
the ``isolated_store`` fixture is autouse and points both at a tmp dir.

pytest runs with ``--import-mode=importlib`` (pytest.ini), so test modules cannot
``from conftest import ...``; shared helpers are fixtures (``git``, ``commit``, ``py``).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def isolated_store(tmp_path_factory, monkeypatch):
    home = tmp_path_factory.mktemp("rails-home")
    monkeypatch.setenv("RAILS_DATA", str(home / "rails"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "claude"))
    for name in ("RAILS_SHADOW_ALL", "RAILS_GATES_OFF", "RAILS_OPERATOR", "CLAUDECODE"):
        monkeypatch.delenv(name, raising=False)
    return home


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr}")
    return done.stdout.strip()


@pytest.fixture
def git():
    return _git


@pytest.fixture
def commit():
    def _commit(top: Path, rel: str, text: str, message: str = "change") -> str:
        path = top / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        _git(top, "add", "-A")
        _git(top, "commit", "-q", "-m", message)
        return _git(top, "rev-parse", "HEAD")

    return _commit


@pytest.fixture
def py() -> str:
    return sys.executable.replace("\\", "/")


@pytest.fixture
def repo(tmp_path) -> Path:
    """A git repo with one commit, `origin/main` at it, and branch `work` checked out."""
    top = tmp_path / "app"
    top.mkdir()
    _git(top, "init", "-q", "-b", "main")
    _git(top, "config", "user.email", "t@example.invalid")
    _git(top, "config", "user.name", "t")
    _git(top, "config", "core.autocrlf", "false")
    _git(top, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (top / "README.md").write_text("hello\n", encoding="utf-8")
    _git(top, "add", "-A")
    _git(top, "commit", "-q", "-m", "init")
    _git(top, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(top, "checkout", "-q", "-b", "work")
    return top
