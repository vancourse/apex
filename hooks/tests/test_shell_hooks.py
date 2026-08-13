"""The three shell hooks this change repairs, driven the way the harness drives them.

Same argument as ``test_session_collisions_hook.py``: a hook has no importers and
produces no diff, its contract is to fail open, and so a dead one is
byte-indistinguishable from a healthy one with nothing to say. Every hook here is
*additionally* silent in its normal case, which means "no output" cannot be read
as health for any of them.

What each group pins, and why that property is the one that can hurt:

- **``run-python-hook.sh`` defers to the repo's own copy.** Without this, a repo
  keeping its own ``session_collisions.py`` runs both — two collision reports at
  one SessionStart, one of them from whichever fork is staler. The failure is not
  an error; it is a second answer, and nothing says which is current. The guard
  must be *per script*, or a repo that forked one hook loses the other two.

- **``format-on-save.sh`` runs the repo's pinned ruff.** The defect being fixed
  is disagreement, not absence: the edit-time formatter used PATH's ruff, the
  commit gate used the pin, and the gate rejected what the formatter produced.
  The assertions are on the resolved argv, because that is the whole behaviour —
  formatting output is ruff's business, not the hook's.

- **``suggest-review-on-stop.sh`` counts only this session's edits.** In a shared
  worktree the old version charged one session 573 lines it had not written. The
  sharp edge is the *absent* baseline: it must fail toward nudging, since a
  missing snapshot should cost precision, never silence the review.

Run with: ``python -m pytest hooks/tests/ -q``
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOKS = PLUGIN_ROOT / "hooks"
HOOKS_JSON = HOOKS / "hooks.json"


def _run(argv: list[str], stdin: str, env: dict[str, str], cwd: pathlib.Path):
    return subprocess.run(
        argv,
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(cwd),
        timeout=60,
    )


def _base_env(**overrides: str) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    env.pop("CLAUDE_PLUGIN_ROOT", None)
    env.update(overrides)
    return env


# --------------------------------------------------------------------------
# run-python-hook.sh — defer to the repo's own copy
# --------------------------------------------------------------------------

SHIM = HOOKS / "run-python-hook.sh"


@pytest.fixture
def fake_plugin(tmp_path: pathlib.Path) -> pathlib.Path:
    """A plugin root whose Python hook announces itself when it runs."""
    root = tmp_path / "plugin"
    (root / "hooks").mkdir(parents=True)
    (root / "hooks" / "session_collisions.py").write_text(
        "print('APEX-COPY-RAN')\n", encoding="utf-8"
    )
    (root / "hooks" / "artifact_templates.py").write_text(
        "print('APEX-TEMPLATES-RAN')\n", encoding="utf-8"
    )
    return root


def _fire_shim(script: str, plugin: pathlib.Path, project: pathlib.Path):
    env = _base_env(
        CLAUDE_PLUGIN_ROOT=str(plugin), CLAUDE_PROJECT_DIR=str(project)
    )
    return _run(["bash", str(SHIM), script], "{}", env, project)


def test_shim_runs_apexs_hook_when_the_repo_has_none(fake_plugin, tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    result = _fire_shim("session_collisions.py", fake_plugin, project)

    assert result.returncode == 0
    assert "APEX-COPY-RAN" in result.stdout, (
        "a repo without its own copy must still get apex's — the guard is a "
        "deferral, not a removal"
    )


def test_shim_defers_when_the_repo_ships_the_same_hook(fake_plugin, tmp_path):
    project = tmp_path / "project"
    (project / ".claude" / "hooks").mkdir(parents=True)
    (project / ".claude" / "hooks" / "session_collisions.py").write_text(
        "print('REPO-COPY-RAN')\n", encoding="utf-8"
    )

    result = _fire_shim("session_collisions.py", fake_plugin, project)

    assert result.returncode == 0
    assert result.stdout == "", (
        "apex's fork must stay silent; the repo registers its own copy and "
        "running both is what produced two collision reports at one startup"
    )


def test_shim_defers_per_script_not_wholesale(fake_plugin, tmp_path):
    """Forking one hook must not cost you the other two."""
    project = tmp_path / "project"
    (project / ".claude" / "hooks").mkdir(parents=True)
    (project / ".claude" / "hooks" / "session_collisions.py").write_text(
        "print('REPO-COPY-RAN')\n", encoding="utf-8"
    )

    result = _fire_shim("artifact_templates.py", fake_plugin, project)

    assert "APEX-TEMPLATES-RAN" in result.stdout


def test_shim_never_blocks_when_the_deferral_target_is_a_directory(
    fake_plugin, tmp_path
):
    """`-f` is the right test: a directory of that name is not a hook."""
    project = tmp_path / "project"
    (project / ".claude" / "hooks" / "session_collisions.py").mkdir(parents=True)

    result = _fire_shim("session_collisions.py", fake_plugin, project)

    assert result.returncode == 0
    assert "APEX-COPY-RAN" in result.stdout


# --------------------------------------------------------------------------
# format-on-save.sh — resolve ruff the way the repo's gates resolve it
# --------------------------------------------------------------------------

FORMATTER = HOOKS / "format-on-save.sh"
PIN = "ruff==0.14.2"


@pytest.fixture
def stub_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    """`uv`, `poetry` and `ruff` stubs that record their argv instead of running."""
    binp = tmp_path / "bin"
    binp.mkdir()
    log = tmp_path / "argv.log"
    for name in ("uv", "poetry", "ruff"):
        stub = binp / name
        stub.write_text(
            f'#!/usr/bin/env bash\nprintf "{name} %s\\n" "$*" >> "{log}"\nexit 0\n',
            encoding="utf-8",
        )
        stub.chmod(0o755)
    return binp


def _git_repo(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def _format(target: pathlib.Path, repo: pathlib.Path, stub_bin: pathlib.Path):
    env = _base_env(PATH=f"{stub_bin}:{os.environ.get('PATH', '')}")
    payload = json.dumps({"tool_input": {"file_path": str(target)}})
    result = _run(["bash", str(FORMATTER)], payload, env, repo)
    assert result.returncode == 0
    log = stub_bin.parent / "argv.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def test_formatter_uses_the_declared_pin_over_whatever_is_on_path(
    tmp_path, stub_bin
):
    repo = _git_repo(tmp_path / "repo")
    (repo / "ci").mkdir()
    (repo / "ci" / "pre_pr_check.py").write_text(
        f'RUFF_VERSION = "{PIN}"\n', encoding="utf-8"
    )
    target = repo / "mod.py"
    target.write_text("x=1\n", encoding="utf-8")

    argv = _format(target, repo, stub_bin)

    assert f"uv run --with {PIN} ruff format {target}" in argv, (
        "the pin the gates read is the pin the formatter must run — twelve "
        "patch versions apart is enough for the two to disagree"
    )
    assert not argv.startswith("ruff "), "PATH's ruff must not win over the pin"


def test_formatter_falls_back_to_the_lockfile_environment(tmp_path, stub_bin):
    """No explicit pin, but a lockfile: same rule as pre_pr_check.py's _runner()."""
    repo = _git_repo(tmp_path / "repo")
    (repo / "uv.lock").write_text("", encoding="utf-8")
    target = repo / "mod.py"
    target.write_text("x=1\n", encoding="utf-8")

    argv = _format(target, repo, stub_bin)

    assert f"uv run ruff format {target}" in argv


def test_formatter_falls_back_to_path_when_the_repo_declares_nothing(
    tmp_path, stub_bin
):
    """Nothing declared means nothing to disagree with — PATH's ruff is correct."""
    repo = _git_repo(tmp_path / "repo")
    target = repo / "mod.py"
    target.write_text("x=1\n", encoding="utf-8")

    argv = _format(target, repo, stub_bin)

    assert f"ruff format {target}" in argv
    assert "uv run" not in argv


def test_formatter_ignores_a_malformed_pin_rather_than_shipping_it_as_argv(
    tmp_path, stub_bin
):
    """A garbled RUFF_VERSION must degrade to the lockfile rule, not become a flag."""
    repo = _git_repo(tmp_path / "repo")
    (repo / "ci").mkdir()
    (repo / "ci" / "pre_pr_check.py").write_text(
        'RUFF_VERSION = "--nonsense"\n', encoding="utf-8"
    )
    (repo / "uv.lock").write_text("", encoding="utf-8")
    target = repo / "mod.py"
    target.write_text("x=1\n", encoding="utf-8")

    argv = _format(target, repo, stub_bin)

    assert "--nonsense" not in argv
    assert f"uv run ruff format {target}" in argv


def test_formatter_stays_silent_and_open_on_a_non_python_file(tmp_path, stub_bin):
    repo = _git_repo(tmp_path / "repo")
    (repo / "uv.lock").write_text("", encoding="utf-8")
    target = repo / "notes.txt"
    target.write_text("hello\n", encoding="utf-8")

    argv = _format(target, repo, stub_bin)

    assert argv == ""


# --------------------------------------------------------------------------
# session-baseline.sh + suggest-review-on-stop.sh — this session's edits only
# --------------------------------------------------------------------------

BASELINE = HOOKS / "session-baseline.sh"
STOP = HOOKS / "suggest-review-on-stop.sh"
SESSION = "sess-scoping-1"
CODE = "".join(f"line_{i} = {i}\n" for i in range(40))


@pytest.fixture
def worktree(tmp_path: pathlib.Path) -> pathlib.Path:
    """A repo with one commit, so `git diff HEAD` has something to compare to."""
    repo = _git_repo(tmp_path / "worktree")
    (repo / "seed.py").write_text("seed = 0\n", encoding="utf-8")
    env = _base_env()
    for argv in (
        ["git", "config", "user.email", "t@example.invalid"],
        ["git", "config", "user.name", "test"],
        ["git", "add", "-A"],
        ["git", "commit", "-qm", "seed"],
    ):
        subprocess.run(argv, cwd=str(repo), env=env, check=True)
    return repo


@pytest.fixture
def marker_dir(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "markers"
    d.mkdir()
    return d


def _fire(hook: pathlib.Path, repo: pathlib.Path, marker_dir: pathlib.Path):
    env = _base_env(TMPDIR=str(marker_dir))
    return _run(["bash", str(hook)], json.dumps({"session_id": SESSION}), env, repo)


def _blocked(result: subprocess.CompletedProcess) -> bool:
    assert result.returncode == 0, "the Stop hook must never fail closed"
    if not result.stdout.strip():
        return False
    return json.loads(result.stdout)["decision"] == "block"


def test_stop_ignores_edits_that_predate_the_session(worktree, marker_dir):
    """The measured failure: another session's 40 lines, charged to this one."""
    (worktree / "theirs.py").write_text(CODE, encoding="utf-8")

    _fire(BASELINE, worktree, marker_dir)
    result = _fire(STOP, worktree, marker_dir)

    assert not _blocked(result), (
        "a nudge that fires on work this session never touched is wrong every "
        "time it fires, which is how the correct hooks stop being read"
    )


def test_stop_still_fires_on_this_sessions_own_new_file(worktree, marker_dir):
    _fire(BASELINE, worktree, marker_dir)
    (worktree / "mine.py").write_text(CODE, encoding="utf-8")

    assert _blocked(_fire(STOP, worktree, marker_dir))


def test_stop_fires_when_this_session_edits_an_already_dirty_file(
    worktree, marker_dir
):
    """Status stays `M`, so only the content hash can tell these two apart."""
    target = worktree / "seed.py"
    target.write_text("seed = 1\n", encoding="utf-8")

    _fire(BASELINE, worktree, marker_dir)
    target.write_text(CODE, encoding="utf-8")

    assert _blocked(_fire(STOP, worktree, marker_dir))


def test_stop_fires_when_no_baseline_was_taken(worktree, marker_dir):
    """Fail open toward nudging — a missing snapshot costs precision, not the review."""
    (worktree / "mine.py").write_text(CODE, encoding="utf-8")

    assert _blocked(_fire(STOP, worktree, marker_dir))


def test_baseline_is_not_rewritten_on_clear_or_compact(worktree, marker_dir):
    """Those re-fire SessionStart with the same id; re-snapshotting would disown
    everything written before the compaction."""
    _fire(BASELINE, worktree, marker_dir)
    (worktree / "mine.py").write_text(CODE, encoding="utf-8")

    _fire(BASELINE, worktree, marker_dir)  # the `compact` firing

    assert _blocked(_fire(STOP, worktree, marker_dir))


def test_baseline_records_deletions_that_predate_the_session(worktree, marker_dir):
    """A path deleted by somebody else is absent from the tree but present in the
    diff — recorded as `-` so it is not read back as this session's work."""
    (worktree / "seed.py").unlink()
    (worktree / "theirs.py").write_text(CODE, encoding="utf-8")

    _fire(BASELINE, worktree, marker_dir)
    result = _fire(STOP, worktree, marker_dir)

    assert not _blocked(result)


def test_baseline_emits_nothing(worktree, marker_dir):
    """SessionStart output becomes session context; this hook has nothing to say."""
    result = _fire(BASELINE, worktree, marker_dir)

    assert result.returncode == 0
    assert result.stdout == ""


def test_baseline_is_silent_and_open_outside_a_git_repo(tmp_path, marker_dir):
    plain = tmp_path / "plain"
    plain.mkdir()

    result = _fire(BASELINE, plain, marker_dir)

    assert result.returncode == 0
    assert result.stdout == ""


# --------------------------------------------------------------------------
# suggest-skill-on-prompt.sh — phase transitions, never topics
# --------------------------------------------------------------------------

PROMPT_HOOK = HOOKS / "suggest-skill-on-prompt.sh"

# The three message shapes the removed review-keyword matcher was measured
# firing on — a read-only audit request, a message answering audit questions,
# and a status report containing no code — each naming files, which is the
# mechanism: it matched the characters `.py` inside a filename. Every one of
# these DOES fire the old matcher and must not fire this one. They are the
# regression suite for the rule that replaced it: match a stated intention,
# never a topic.
MEASURED_FALSE_POSITIVES = [
    "Audit hooks/format-on-save.sh and hooks/session_collisions.py in this repo "
    "and report back. Read-only — do not change anything, do not open a PR.",
    "Answering your four questions: (1) yes, hooks/_hooklib.py is shared; "
    "(2) session_collisions.py is the duplicated one; (3) no; (4) ruff 0.14.14.",
    "Status: the audit of _hooklib.py and artifact_templates.py is written up "
    "and the figures are measured. Nothing is committed yet.",
]


def _prompt(text: str) -> str:
    result = _run(
        ["bash", str(PROMPT_HOOK)], json.dumps({"prompt": text}), _base_env(), HOOKS
    )
    assert result.returncode == 0, "a UserPromptSubmit hook must never fail closed"
    if not result.stdout.strip():
        return ""
    payload = json.loads(result.stdout)
    out = payload["hookSpecificOutput"]
    # additionalContext under the wrong event name is dropped by the harness
    # silently, with a zero exit — indistinguishable from having nothing to say.
    assert out["hookEventName"] == "UserPromptSubmit"
    return out["additionalContext"]


@pytest.mark.parametrize("message", MEASURED_FALSE_POSITIVES)
def test_prompt_hook_says_nothing_about_prose_that_merely_mentions_code(message):
    """The measured 0-for-3. A filename is not an intention."""
    assert _prompt(message) == ""


def test_prompt_hook_no_longer_demands_a_review_for_a_topic():
    """`.py` inside a filename was the whole basis of the deleted matcher."""
    assert _prompt("Take a look at hooks/format-on-save.sh and _hooklib.py") == ""
    assert _prompt("What does the pytest suite cover in TypeScript?") == ""


def test_prompt_hook_gates_the_design_transition():
    context = _prompt("Let's design the new export pipeline")
    assert "apex:prd-review" in context


def test_prompt_hook_gates_the_impl_planning_transition():
    context = _prompt("The design is frozen — ready to plan")
    assert "apex:design-review" in context


def test_prompt_hook_gates_the_build_transition():
    context = _prompt("Plan looks good, start implementing")
    assert "apex:impl-plan-review" in context


def test_prompt_hook_nudges_recon_on_a_subtractive_trap():
    context = _prompt("This PR is bloated — can we shrink it?")
    assert "apex:recon" in context


def test_prompt_hook_concatenates_without_losing_a_gate():
    """Two transitions in one message must yield two nudges, not the last one."""
    context = _prompt("This module is too big — let's design a smaller one")

    assert "apex:recon" in context
    assert "apex:prd-review" in context


def test_prompt_hook_emits_valid_json_for_a_message_full_of_metacharacters():
    """The old raw-printf emit produced invalid JSON the harness drops silently."""
    context = _prompt('Let\'s design a "thing" with a \\backslash\tand a\nnewline')

    assert "apex:prd-review" in context  # parsed, so the JSON survived


# --------------------------------------------------------------------------
# hooks.json — the registrations these behaviours depend on
# --------------------------------------------------------------------------


def test_hooks_json_registers_the_baseline_on_session_start():
    """The Stop hook's scoping is inert unless the snapshot is actually taken."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    commands = [
        h["command"]
        for group in config["hooks"]["SessionStart"]
        for h in group["hooks"]
    ]
    assert any("session-baseline.sh" in c for c in commands)

    # No matcher: `resume` must snapshot too, or a resumed session inherits
    # whatever the worktree is holding as its own work.
    group = next(
        g
        for g in config["hooks"]["SessionStart"]
        if any("session-baseline.sh" in h["command"] for h in g["hooks"])
    )
    assert "matcher" not in group


def test_no_hook_references_a_script_that_is_not_shipped():
    """The count that drifts: a registration outliving its file is a hook error
    on every matching event, reported to the agent and to nobody else."""
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    for groups in config["hooks"].values():
        for group in groups:
            for hook in group["hooks"]:
                command = hook["command"]
                name = command.replace("${CLAUDE_PLUGIN_ROOT}/hooks/", "").split()
                assert (HOOKS / name[0]).is_file(), f"missing hook: {name[0]}"
                if len(name) > 1:  # run-python-hook.sh <script>.py
                    assert (HOOKS / name[1]).is_file(), f"missing hook: {name[1]}"
