"""heavy_pytest: an agent's suite goes through the `suite` lock, a narrow run does not.

Both edges are pinned. Too loud queues a two-file check (or a `pip install pytest`) behind
a half-hour suite; too mute lets a sixteen-worker run start beside `rails check` again,
which is what ran Windows out of commit on 2026-10-18. The allowed cases call `judge`
directly: `check` fails open on an exception, so an allow through it proves nothing.
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


@pytest.fixture(autouse=True)
def no_inherited_addopts(monkeypatch):
    """The gate reads PYTEST_ADDOPTS from its own environment, as the shell inherits it."""
    monkeypatch.delenv("PYTEST_ADDOPTS", raising=False)


def _write(path: Path, text: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _make_repo(top: Path, lanes: str | None = SUITE_LANES) -> Path:
    """A repo shaped like jarvis: root addopts `-n auto`, a 33-file `apps/`, a package with
    its own config (so it runs serially), and the suite lanes under a lock."""
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


def _judge(command: str, cwd: Path, shell: str = "bash"):
    return heavy_pytest.judge(command, shell, cwd)


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest apps/ -q",
        "uv run pytest -q",
        "pytest apps/big/tests",
        "py.test apps/",
        "python -m pytest apps",
        "python -X utf8 -m pytest apps",
        ".venv/Scripts/python.exe -m pytest apps/big",
        "uv run --locked pytest apps/big/tests -x",
        "uv run --with pytest-timeout pytest apps/",
        "uv run --with pytest python -m pytest -q",
        "uvx pytest apps/",
        "coverage run -m pytest apps/",
        "uv run pytest -n 4 apps/big/tests",
        "uv run pytest apps/big/tests -n4",
        "uv run pytest --numprocesses=6 apps/big/tests",
        "uv run pytest pkg/tests -n 8",
        'PYTEST_ADDOPTS="-n 4" uv run pytest pkg/tests',
        'export PYTEST_ADDOPTS="-n 4"; uv run pytest pkg/tests -q',
        "PYTEST_ADDOPTS=-n0 uv run pytest tests/test_one.py; uv run pytest apps/",
        'uv run pytest pkg/tests -o addopts="-n 4"',
        "cd apps && uv run pytest big",
        "uv run pytest apps/*/tests",
        "uv run pytest apps/small/tests apps/big/tests",
        "timeout 1800 uv run pytest apps/ -q > out.txt 2>&1",
        "uv run pytest -q > out.txt 2>&1 &",
        "uv run pytest &",
        "nohup uv run pytest apps/ -q &>> log.txt &",
        "DATABASE_URL=postgresql://x \\\n  uv run pytest apps/ -q",
        "uv run pytest \\\n  -q",
        'A=1 \\\n  PYTEST_ADDOPTS="-n 4" uv run pytest pkg/tests',
        "for i in 1 2; do uv run pytest apps/ -q; done",
        'uv run pytest -k "totals" apps/',
        "uv run python ci/rails.py lock docker -- uv run pytest apps/",
        "rails lock docker -- uv run pytest apps/",
        "uv run pytest apps/ -n 0 -n 4",
        "uv run pytest apps/ --ignore=apps/small",
        "(cd apps && uv run pytest big)",
        "( cd apps && uv run pytest big )",
        "pushd apps > /dev/null && uv run pytest big",
        "if uv run pytest apps/ -q; then echo ok; fi",
        "python -m coverage run -m pytest apps/",
        "uv run python -m coverage run -m pytest apps/",
        "coverage run --source apps -m pytest apps/",
        "uv run --no-extra gpu pytest apps/",
        'env PYTEST_ADDOPTS="-n 4" uv run pytest pkg/tests',
        "uv run pytest --random-order-seed 1",
        "uv run pytest apps/\\\n  -q",
        "cd apps\\\n  && uv run pytest big",
        "(cd apps && uv run pytest)",
        "(cd pkg && uv run pytest tests -n 4)",
        # A subshell's cd ends with it: the later pytest runs at the root.
        "(cd pkg && echo hi) && uv run pytest apps/ -q",
        "pushd apps > /dev/null && uv run pytest small/tests && popd > /dev/null && uv run pytest apps/ -q",
        # The subshell closes before a redirection or a pipe, not only as the last word.
        "(cd pkg && uv run pytest tests -n 4) 2>&1 | tail -20",
        "(cd apps && uv run pytest) 2>&1 | tail -30",
        "(cd pkg && echo hi) > /dev/null && uv run pytest apps/ -q",
        "(cd apps && X=$(pwd) && uv run pytest big)",
        'cd "$(git rev-parse --show-toplevel)" && uv run pytest apps/',
    ],
)
def test_a_heavy_suite_is_refused(verdict, repo, command):
    assert verdict(heavy_pytest, command, cwd=repo) == "deny"


@pytest.mark.parametrize(
    "command",
    [
        "uv run pytest tests/test_one.py",
        "uv run pytest tests/test_one.py::test_x -n 4",
        " ".join(["uv run pytest"] + [f"apps/big/tests/test_b1.py::test_{n}" for n in range(40)]),
        "uv run pytest apps/small/tests",
        "uv run pytest apps/small",
        "uv run pytest apps/big/tests/test_b1.py apps/big/tests/test_b2.py apps/big/tests/test_b3.py",
        "uv run pytest apps/big --ignore=apps/big/tests",
        "uv run pytest -d tests/test_one.py",
        "uv run pytest apps/ -n 0",
        "uv run pytest apps/ -n0",
        "uv run pytest apps/ -n 1",
        "uv run pytest apps/ -p no:xdist",
        "uv run pytest apps/ -n 4 -n 0",
        "uv run pytest pkg/tests",
        "cd pkg && uv run pytest",
        'PYTEST_ADDOPTS="-n 4" uv run pytest tests/test_one.py; uv run pytest pkg/tests',
        "uv run pytest apps/ --co -q",
        "uv run pytest --version",
        'uv run pytest apps/ -o addopts=""',
        "uv run pytest $CHANGED_TESTS",
        "rails lock suite -- uv run pytest apps/ -q",
        "uv run python ci/rails.py lock suite -- uv run pytest apps/ -q",
        "docker compose exec app python -m pytest -n 4",
        "timeout 600 docker compose exec app pytest -n 4",
        'git commit -m "uv run pytest apps/ -q took Docker down"',
        "cat pytest.ini",
        "uv run python ci/local_lanes.py suite",
        "uv pip install pytest",
        "uv pip show pytest",
        "uv add --dev pytest",
        "uv lock --upgrade-package pytest",
        "uv tree --package pytest",
        "python -m pip install -U pytest",
        "pip install pytest-xdist",
        "tox -e pytest",
        "uv run pip install pytest",
        "env PYTEST_ADDOPTS=-n0 uv run pytest apps/",
        # Not exported, so pytest never sees it: the package config's serial run stands.
        'PYTEST_ADDOPTS="-n 4"; uv run pytest pkg/tests',
        "uv run pytest --lf tests/test_one.py",
        "(cd pkg && uv run pytest)",
        # An unknown flag before a directory that is there: the directory is the target.
        "uv run pytest --runslow tests",
        "{ cd pkg; uv run pytest; }",
    ],
)
def test_a_narrow_queued_or_non_test_command_passes(repo, command):
    assert _judge(command, repo) is None


def test_the_refusal_names_the_queued_command(reason, repo):
    text = reason(heavy_pytest, "DATABASE_URL=postgresql://x uv run pytest apps/ -q", cwd=repo)
    assert "`DATABASE_URL=postgresql://x rails lock suite -- uv run pytest apps/ -q`" in text, text
    assert f"{os.cpu_count() or 2} workers (from addopts in pyproject.toml)" in text, text
    assert "-n 0" in text


@pytest.mark.parametrize(
    ("command", "suggested"),
    [
        ("UV_CACHE_DIR=/c/uv uv run pytest apps/ -q", "UV_CACHE_DIR=/c/uv rails lock suite -- uv run pytest apps/ -q"),
        ("cd apps && uv run pytest big", "cd apps && rails lock suite -- uv run pytest big"),
        ("for i in 1 2; do uv run pytest apps/ -q; done", "rails lock suite -- <this pytest command>"),
        # The heavy statement is queued, not an earlier one its text begins.
        (
            "uv run pytest apps/big/tests/test_b1.py && uv run pytest apps/",
            "uv run pytest apps/big/tests/test_b1.py && rails lock suite -- uv run pytest apps/",
        ),
        ("uv run pytest apps/ -n 0; uv run pytest apps/", "uv run pytest apps/ -n 0; rails lock suite -- uv run pytest apps/"),
    ],
)
def test_the_suggestion_is_the_whole_command_queued(reason, repo, command, suggested):
    assert f"`{suggested}`" in reason(heavy_pytest, command, cwd=repo)


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        ("RAILS_LOCKS_HELD=suite:1 rails check", "Bash"),
        ("export RAILS_LOCKS_HELD=suite:1; uv run python ci/rails.py check", "Bash"),
        ("env RAILS_LOCKS_HELD=suite:1 rails check", "Bash"),
        ('$env:RAILS_LOCKS_HELD = "suite:1"; rails check', "PowerShell"),
        ("Set-Item Env:RAILS_LOCKS_HELD suite:1", "PowerShell"),
        ("[Environment]::SetEnvironmentVariable('RAILS_LOCKS_HELD', 'suite:1')", "PowerShell"),
        ("declare -x RAILS_LOCKS_HELD=suite:1; rails check", "Bash"),
        ("env A=1 RAILS_LOCKS_HELD=suite:1 rails check", "Bash"),
    ],
)
def test_setting_the_held_lock_marker_by_hand_is_refused(verdict, reason, repo, command, tool):
    """`rails lock` sets RAILS_LOCKS_HELD for the command it runs; set by hand it would let a
    suite skip the queue."""
    assert verdict(heavy_pytest, command, tool=tool, cwd=repo) == "deny"
    assert "RAILS_LOCKS_HELD" in reason(heavy_pytest, command, tool=tool, cwd=repo)


@pytest.mark.parametrize(
    ("command", "tool"),
    [
        ("echo $RAILS_LOCKS_HELD", "Bash"),
        ("echo RAILS_LOCKS_HELD=$RAILS_LOCKS_HELD", "Bash"),
        ("grep -rn RAILS_LOCKS_HELD= rails/", "Bash"),
        ("RAILS_LOCKS_HELD= rails check", "Bash"),
        ('git commit -m "rails lock sets RAILS_LOCKS_HELD=suite:<pid>"', "Bash"),
        ("Write-Output $env:RAILS_LOCKS_HELD", "PowerShell"),
        ("$env:RAILS_LOCKS_HELD = $null", "PowerShell"),
        ("git commit -m '$env:RAILS_LOCKS_HELD = 1'", "PowerShell"),
        ("""git commit -m "gate: refuse [Environment]::SetEnvironmentVariable('RAILS_LOCKS_HELD', 'x')" """, "Bash"),
        ("[Environment]::SetEnvironmentVariable('RAILS_LOCKS_HELD', $null)", "PowerShell"),
        ("Set-Item Env:RAILS_LOCKS_HELD ''", "PowerShell"),
        ("env A=1 tool --flag RAILS_LOCKS_HELD=x", "Bash"),
    ],
)
def test_reading_or_quoting_the_marker_passes(verdict, repo, command, tool):
    assert verdict(heavy_pytest, command, tool=tool, cwd=repo) == "allow"


def test_a_c_config_of_any_name_is_read(repo):
    _write(repo / "ci" / "fast.ini", "[pytest]\naddopts = -n 8\n")
    assert _judge("uv run pytest -c ci/fast.ini pkg/tests", repo) is not None
    _write(repo / "ci" / "fast.ini", "[pytest]\naddopts = -q\n")
    assert _judge("uv run pytest -c ci/fast.ini apps/", repo) is None


def test_ignore_matches_from_a_cwd_reached_through_a_link(repo, tmp_path):
    link = tmp_path / "linked"
    try:
        if os.name == "nt":
            import _winapi

            _winapi.CreateJunction(str(repo), str(link))
        else:
            link.symlink_to(repo, target_is_directory=True)
    except (OSError, AttributeError) as exc:
        pytest.skip(f"cannot make a directory link here: {exc}")
    assert _judge("uv run pytest apps/big --ignore=apps/big/tests", link) is None
    assert _judge("uv run pytest apps/big", link) is not None


def test_powershell_spellings(verdict, reason, repo):
    assert verdict(heavy_pytest, "uv run pytest apps/ -q", tool="PowerShell", cwd=repo) == "deny"
    assert verdict(heavy_pytest, "uv run pytest -q *> out.txt", tool="PowerShell", cwd=repo) == "deny"
    assert (
        verdict(heavy_pytest, '$env:PYTEST_ADDOPTS="-n 4"; uv run pytest pkg/tests', tool="PowerShell", cwd=repo)
        == "deny"
    )
    assert verdict(heavy_pytest, "Push-Location apps; uv run pytest big", tool="PowerShell", cwd=repo) == "deny"
    assert _judge("uv run pytest apps/ -n 0", repo, "powershell") is None
    text = reason(heavy_pytest, "Set-Location apps; uv run pytest big -q", tool="PowerShell", cwd=repo)
    assert "`Set-Location apps; rails lock suite -- uv run pytest big -q`" in text, text


def test_the_inherited_environment_counts(repo, monkeypatch):
    monkeypatch.setenv("PYTEST_ADDOPTS", "-p no:xdist")
    assert _judge("uv run pytest apps/", repo) is None
    monkeypatch.setenv("PYTEST_ADDOPTS", "-n 8")
    assert _judge("uv run pytest pkg/tests", repo) is not None
    assert _judge("unset PYTEST_ADDOPTS; uv run pytest pkg/tests", repo) is None


def test_a_cd_by_absolute_path_variable_or_home_is_followed(verdict, repo, tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert verdict(heavy_pytest, f"cd {_msys(repo)} && uv run pytest apps/", cwd=elsewhere) == "deny"
    assert verdict(heavy_pytest, f'WT={_msys(repo)}\ncd "$WT" && uv run pytest apps/', cwd=elsewhere) == "deny"
    assert verdict(heavy_pytest, f"uv run --directory {_posix(repo)} pytest apps/", cwd=elsewhere) == "deny"
    monkeypatch.setenv("HOME", str(repo.parent))
    assert verdict(heavy_pytest, f"cd $HOME/{repo.name} && uv run pytest apps/", cwd=elsewhere) == "deny"
    assert _judge("uv run pytest apps/", elsewhere) is None


def test_a_redirect_is_not_a_target(verdict, repo, tmp_path):
    """A redirect's file is the shell's: read as a target that exists, it would move pytest's
    config search off the repo and let a sixteen-worker run through."""
    log = tmp_path / "logs" / "out.txt"
    _write(log, "an earlier run's output")
    assert verdict(heavy_pytest, f"uv run pytest apps/ -q > {_posix(log)} 2>&1", cwd=repo) == "deny"
    assert _judge(f"uv run pytest apps/small/tests 2>&1 > {_posix(log)}", repo) is None


def test_pytest_9_config_files_are_read(repo):
    """jarvis pins pytest 9.1.1, whose search adds pytest.toml / .pytest.toml and a native
    [tool.pytest] table ahead of the ini forms."""
    _write(repo / "pkg" / "pytest.toml", '[pytest]\naddopts = ["-n", "auto"]\n')
    assert _judge("uv run pytest pkg/tests", repo) is not None
    _write(repo / "pkg" / "pytest.toml", "[pytest]\n")  # always the config, even with no addopts
    assert _judge("uv run pytest pkg/tests", repo) is None
    (repo / "pkg" / "pytest.toml").unlink()
    _write(repo / "pkg" / "pyproject.toml", '[project]\nname = "pkg"\n[tool.pytest]\naddopts = ["-n", "4"]\n')
    assert _judge("uv run pytest pkg/tests", repo) is not None
    # Read as pkg's own config, not passed over for the root's `-n auto`.
    _write(repo / "pkg" / "pyproject.toml", '[project]\nname = "pkg"\n[tool.pytest]\naddopts = ["-q"]\n')
    assert _judge("uv run pytest pkg/tests", repo) is None


def test_a_repo_that_locks_no_suite_is_left_alone(tmp_path):
    unlocked = _make_repo(tmp_path / "unlocked", lanes=UNLOCKED_LANES)
    bare = _make_repo(tmp_path / "bare", lanes=None)
    for top in (unlocked, bare):
        assert _judge("uv run pytest apps/ -q", top) is None
        assert _judge("uv run pytest -n 8", top) is None


def test_a_broken_config_or_cwd_fails_open(verdict, repo, tmp_path):
    _write(repo / "pyproject.toml", "[tool.pytest.ini_options]\naddopts = = broken\n")
    assert _judge("uv run pytest apps/", repo) is None
    assert verdict(heavy_pytest, "uv run pytest apps/ -n 4", cwd=repo) == "deny"
    assert _judge("uv run pytest apps/ -n 4", tmp_path / "missing") is None


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
