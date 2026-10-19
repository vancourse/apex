"""heavy_pytest: an agent's suite goes through the `suite` lock, a narrow run does not.

Both edges are pinned. Too loud queues a two-file check behind a half-hour suite; too mute
lets a sixteen-worker run start beside `rails check` again, which is what ran Windows out
of commit on 2026-10-18.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
from pathlib import Path

import pytest

from rails import dispatch
from rails.dispatch import load_registry
from rails.gates import heavy_pytest
from rails.hookio import Event

ROOT = Path(__file__).resolve().parents[2]

SUITE_LANES = """
[[lane]]
name = "suite"
command = ["uv", "run", "python", "ci/local_lanes.py", "suite"]
lock = "suite"
"""
UNLOCKED_LANES = """
[[lane]]
name = "suite"
command = ["uv", "run", "pytest"]
"""
ROOT_CONFIG = '[tool.pytest.ini_options]\naddopts = "--import-mode=importlib -n auto"\n'
PACKAGE_CONFIG = '[project]\nname = "pkg"\n[tool.pytest.ini_options]\naddopts = "-q"\n'


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _make_repo(top: Path, lanes: str | None = SUITE_LANES) -> Path:
    """A repo shaped like jarvis: root addopts `-n auto`, a 33-file `apps/`, a package
    with its own config (so it runs serially), and the suite lanes under a lock."""
    top.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(top)], check=True, timeout=60)
    _write(top / "pyproject.toml", ROOT_CONFIG)
    if lanes is not None:
        _write(top / "rails" / "lanes.toml", lanes)
    for n in range(31):
        _write(top / "apps" / "big" / "tests" / f"test_b{n}.py")
    _write(top / "apps" / "big" / "tests" / "conftest.py")
    for n in range(2):
        _write(top / "apps" / "small" / "tests" / f"test_s{n}.py")
    _write(top / "pkg" / "pyproject.toml", PACKAGE_CONFIG)
    for n in range(40):
        _write(top / "pkg" / "tests" / f"test_p{n}.py")
    _write(top / "tests" / "test_one.py")
    # pytest's default norecursedirs skips these, so their tests make no suite.
    for n in range(40):
        _write(top / "apps" / "small" / "frontend" / "node_modules" / "pkg" / "tests" / f"test_v{n}.py")
        _write(top / "apps" / "small" / ".venv" / "lib" / f"test_e{n}.py")
    return top


@pytest.fixture
def repo(tmp_path):
    return _make_repo(tmp_path / "repo")


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def _msys(path: Path) -> str:
    text = _posix(path)
    return f"/{text[0].lower()}{text[2:]}" if os.name == "nt" and text[1] == ":" else text


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest apps/ -q",
        "uv run pytest -q",
        "pytest apps/big/tests",
        "python -m pytest apps",
        ".venv/Scripts/python.exe -m pytest apps/big",
        "uv run --locked pytest apps/big/tests -x",
        "uv run pytest -n 4 apps/big/tests",
        "uv run pytest apps/big/tests -n4",
        "uv run pytest --numprocesses=6 apps/big/tests",
        "uv run pytest pkg/tests -n 8",
        'PYTEST_ADDOPTS="-n 4" uv run pytest pkg/tests',
        'export PYTEST_ADDOPTS="-n 4"; uv run pytest pkg/tests -q',
        'uv run pytest pkg/tests -o addopts="-n 4"',
        "cd apps && uv run pytest big",
        "uv run pytest 'apps/*/tests'",
        "uv run pytest apps/small/tests apps/big/tests",
        "timeout 1800 uv run pytest apps/ -q > out.txt 2>&1",
        'uv run pytest -k "totals" apps/',
        "uv run python ci/rails.py lock docker -- uv run pytest apps/",
        "uv run pytest apps/ -n 0 -n 4",
    ],
)
def test_a_heavy_suite_is_refused(verdict, repo, command):
    assert verdict(heavy_pytest, command, cwd=repo) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest tests/test_one.py",
        "uv run pytest tests/test_one.py::test_x -n 4",
        "uv run pytest apps/small/tests",
        "uv run pytest apps/small",
        "uv run pytest apps/big/tests/test_b1.py apps/big/tests/test_b2.py apps/big/tests/test_b3.py",
        "uv run pytest apps/ -n 0",
        "uv run pytest apps/ -n0",
        "uv run pytest apps/ -n 1",
        "uv run pytest apps/ -p no:xdist",
        "uv run pytest apps/ -n 4 -n 0",
        "uv run pytest pkg/tests",
        "cd pkg && uv run pytest",
        "uv run pytest apps/ --co -q",
        "uv run pytest --version",
        'uv run pytest apps/ -o addopts=""',
        "rails lock suite -- uv run pytest apps/ -q",
        "uv run python ci/rails.py lock suite -- uv run pytest apps/ -q",
        "docker compose exec app python -m pytest -n 4",
        'git commit -m "uv run pytest apps/ -q took Docker down"',
        "cat pytest.ini",
        "uv run python ci/local_lanes.py suite",
    ],
)
def test_a_narrow_or_queued_run_passes(verdict, repo, command):
    assert verdict(heavy_pytest, command, cwd=repo) == "allow"


def test_the_refusal_names_the_queued_command(reason, repo):
    text = reason(heavy_pytest, "DATABASE_URL=postgresql://x uv run pytest apps/ -q", cwd=repo)
    assert "`DATABASE_URL=postgresql://x rails lock suite -- uv run pytest apps/ -q`" in text, text
    assert f"{os.cpu_count() or 2} workers (from addopts in pyproject.toml)" in text, text
    assert "-n 0" in text


def test_a_redirect_is_not_a_target(verdict, repo, tmp_path):
    """A redirect's file is the shell's: read as a target that exists, it would move pytest's
    config search off the repo and let a sixteen-worker run through."""
    log = tmp_path / "logs" / "out.txt"
    _write(log, "an earlier run's output")
    command = f"uv run pytest apps/ -q > {_posix(log)} 2>&1"
    assert verdict(heavy_pytest, command, cwd=repo) == "deny"
    assert verdict(heavy_pytest, f"uv run pytest apps/small/tests 2>&1 > {_posix(log)}", cwd=repo) == "allow"


def test_powershell_spellings(verdict, reason, repo):
    assert verdict(heavy_pytest, "uv run pytest apps/ -q", tool="PowerShell", cwd=repo) == "deny"
    assert (
        verdict(heavy_pytest, '$env:PYTEST_ADDOPTS="-n 4"; uv run pytest pkg/tests', tool="PowerShell", cwd=repo)
        == "deny"
    )
    assert verdict(heavy_pytest, "uv run pytest apps/ -n 0", tool="PowerShell", cwd=repo) == "allow"
    text = reason(heavy_pytest, "Set-Location apps; uv run pytest big -q", tool="PowerShell", cwd=repo)
    assert "rails lock suite -- uv run pytest big -q" in text


def test_a_cd_by_absolute_path_and_variable_is_followed(verdict, repo, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert verdict(heavy_pytest, f"cd {_msys(repo)} && uv run pytest apps/", cwd=elsewhere) == "deny"
    assert verdict(heavy_pytest, f'WT={_msys(repo)}\ncd "$WT" && uv run pytest apps/', cwd=elsewhere) == "deny"
    assert verdict(heavy_pytest, f"uv run --directory {_posix(repo)} pytest apps/", cwd=elsewhere) == "deny"
    assert verdict(heavy_pytest, "uv run pytest apps/", cwd=elsewhere) == "allow"


def test_a_repo_that_locks_no_suite_is_left_alone(verdict, tmp_path):
    unlocked = _make_repo(tmp_path / "unlocked", lanes=UNLOCKED_LANES)
    bare = _make_repo(tmp_path / "bare", lanes=None)
    for top in (unlocked, bare):
        assert verdict(heavy_pytest, "uv run pytest apps/ -q", cwd=top) == "allow"
        assert verdict(heavy_pytest, "uv run pytest -n 8", cwd=top) == "allow"


def test_a_broken_config_or_cwd_fails_open(verdict, repo, tmp_path):
    _write(repo / "pyproject.toml", "[tool.pytest.ini_options\naddopts = = broken")
    assert verdict(heavy_pytest, "uv run pytest apps/", cwd=repo) == "allow"
    assert verdict(heavy_pytest, "uv run pytest apps/ -n 4", cwd=repo) == "deny"
    assert verdict(heavy_pytest, "uv run pytest apps/ -n 4", cwd=tmp_path / "missing") == "allow"


def test_the_planted_suite_is_refused_by_the_real_dispatcher(repo):
    """The registry's planted defect: the shape of 2026-10-18's two raw suites, fed to the
    dispatcher with the row forced to enforce."""
    event = Event(
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "session_id": "planted-heavy-pytest",
            "cwd": str(repo),
            "tool_name": "Bash",
            "tool_input": {"command": "uv run pytest apps/ -q", "description": "Run the suite"},
        },
    )
    row = next(r for r in load_registry(ROOT / "hooks" / "gates.toml") if r.name == "heavy_pytest")
    outcome = dispatch.dispatch(event, rows=[dataclasses.replace(row, mode="enforce", shadow_until="")])
    assert not any("crashed" in n or "unguarded" in n for n in outcome.notices), outcome.notices
    assert outcome.denies, "heavy_pytest did not refuse its own planted defect"
    rendered = json.loads(outcome.render())["hookSpecificOutput"]
    assert rendered["permissionDecision"] == "deny"
    assert "rails lock suite -- uv run pytest apps/ -q" in rendered["permissionDecisionReason"]
