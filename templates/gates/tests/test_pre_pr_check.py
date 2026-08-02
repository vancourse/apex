"""The pre-PR gate's orchestration logic, loaded by path.

Only the planning is tested here: which steps get built, in what order, which ref
the run diffs against, and whether a step is skipped for a stated reason. Actually
running the linters and the test suite is proven by using the script — re-running a
whole suite from a unit test would be a slow, redundant copy of that suite.

The two preflight blocks are the exception, and they get end-to-end coverage against
real temporary repositories. The predicate tests prove the logic; they cannot prove
the gate is *wired* to git at all. `preflight` could stop reading git entirely and
every predicate test would still pass — the same mute-failure mode that lets a
dropped import kill a check in total silence.

Run with `pytest templates/gates/tests` (or from wherever these were installed).
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

_HERE = pathlib.Path(__file__).resolve().parent
_SCRIPT_PATH = _HERE.parent / "pre_pr_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("pre_pr_check", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None, _SCRIPT_PATH
    module = importlib.util.module_from_spec(spec)
    sys.modules["pre_pr_check"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


def _python_repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A tree carrying the config every optional step keys on."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 88\n\n[tool.pyright]\nstrict = []\n",
        encoding="utf-8",
    )
    (repo / "uv.lock").write_text("# lock\n", encoding="utf-8")
    return repo


# --- step planning --------------------------------------------------------


def test_cheapest_gates_run_before_the_test_suite(tmp_path, monkeypatch):
    """Order matters: a broken format should fail in ~1s, not after a 2-minute test
    run — that ordering is the entire point of the tool."""
    monkeypatch.setattr(gate, "REPO_ROOT", _python_repo(tmp_path))
    names = [s.name for s in gate.build_steps(base="origin/main", skip_tests=False)]

    assert names[0] == "format (ruff)"
    assert names[1] == "lint (ruff)"
    assert names[2] == "lockfile"
    assert names[-1] == "tests", "the test suite must be the last, most expensive step"


def test_skip_tests_omits_the_test_step_only(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "REPO_ROOT", _python_repo(tmp_path))
    with_tests = [
        s.name for s in gate.build_steps(base="origin/main", skip_tests=False)
    ]
    without_tests = [
        s.name for s in gate.build_steps(base="origin/main", skip_tests=True)
    ]

    assert "tests" in with_tests
    assert "tests" not in without_tests
    assert without_tests == with_tests[:-1]


def test_the_types_step_is_conditional_on_a_type_config(tmp_path, monkeypatch):
    """A repo without a type gate configured should not be told it failed one."""
    repo = _python_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    assert any(
        s.name == "types (pyright)"
        for s in gate.build_steps(base="origin/main", skip_tests=True)
    )

    (repo / "pyproject.toml").write_text("[tool.ruff]\n", encoding="utf-8")
    assert not any(
        s.name.startswith("types")
        for s in gate.build_steps(base="origin/main", skip_tests=True)
    )


def test_a_repo_with_no_recognised_config_gets_no_gates(tmp_path, monkeypatch):
    """Better an empty run that says so than a spurious ruff failure in a repo that
    never used ruff — a gate that fires on correct work gets routed around, and then
    none of the gates run."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(gate, "REPO_ROOT", empty)

    assert gate.build_steps(base="origin/main", skip_tests=True) == []


def test_the_lockfile_step_picks_the_runner_the_repo_actually_locks_with(
    tmp_path, monkeypatch
):
    """The local run has to resolve the same pinned versions CI resolves, so the
    prefix is derived from the lockfile rather than from whatever is on PATH."""
    repo = _python_repo(tmp_path)
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    steps = {s.name: s.argv for s in gate.build_steps(base="origin/main", skip_tests=True)}

    assert steps["format (ruff)"][:2] == ["uv", "run"]
    assert steps["lockfile"] == ["uv", "lock", "--check"]


def test_only_the_test_step_declares_an_env_requirement(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "REPO_ROOT", _python_repo(tmp_path))
    monkeypatch.setattr(gate, "TEST_ENV", "DATABASE_URL")
    steps = gate.build_steps(base="origin/main", skip_tests=False)

    assert [s.name for s in steps if s.requires_env] == ["tests"]


def test_an_unresolvable_base_falls_back_to_the_full_suite_rather_than_erroring():
    """A base ref that cannot be diffed (typo, unfetched branch) must not crash the
    tool or silently run nothing — it must be the safe default: run everything."""
    assert gate.changed_files(base="not-a-real-ref-xyz") == []


# --- the default branch ---------------------------------------------------


def _git(repo: pathlib.Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )


def _commit(repo: pathlib.Path, path: str, subject: str) -> None:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(subject, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", subject)


def test_the_default_branch_is_read_from_the_remote_not_assumed(tmp_path, monkeypatch):
    """Hardcoding a branch name is how a tool starts reporting on the wrong base in
    every repo that named its trunk something else."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "trunk")
    _commit(repo, "docs/start.md", "docs: initial")
    _git(repo, "update-ref", "refs/remotes/origin/trunk", "HEAD")
    _git(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")

    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    assert gate.default_base() == "origin/trunk"


def test_a_repo_with_no_origin_head_falls_back_to_a_conventional_name(
    tmp_path, monkeypatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _commit(repo, "docs/start.md", "docs: initial")

    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    assert gate.default_base() == "origin/main"


# --- preflight: the base check -------------------------------------------


def test_a_merged_pr_commit_on_the_branch_is_flagged_as_inherited():
    """A branch of the author's own docs commits plus one squash-merge commit
    inherited from a rewritten base. Only the inherited one may be named."""
    commits = [
        ("953dd4f", "docs(adr): ADR-0023 — collapse the design"),
        ("f3e697d", "docs(adr): ADR-0020 draft"),
        ("dccb084", "feat(reporting): statement parsers and engines (#206)"),
    ]

    assert gate.inherited_commits(commits) == [
        ("dccb084", "feat(reporting): statement parsers and engines (#206)")
    ]


def test_a_clean_branch_has_no_inherited_commits():
    commits = [
        ("1536ff7", "docs(adr): ADR-0023 — collapse the design"),
        ("5e014f1", "docs(adr): the 1:1 assumption belongs in the type"),
    ]

    assert gate.inherited_commits(commits) == []


def test_a_revert_of_a_merged_pr_is_not_treated_as_inherited():
    """`Revert "feat(x): thing (#123)"` ends in a quote, not the number, and is a
    legitimate commit an author writes by hand. The distinction is the whole reason
    the pattern is anchored to end-of-subject."""
    commits = [("aaaaaaa", 'Revert "feat(x): thing (#123)"')]

    assert gate.inherited_commits(commits) == []


def test_an_issue_reference_mid_subject_is_not_treated_as_inherited():
    commits = [("bbbbbbb", "docs(adr): close the finding from (#365) in rev 3")]

    assert gate.inherited_commits(commits) == []


# --- preflight: the scope check ------------------------------------------


def test_docs_only_commits_declare_a_docs_only_scope():
    commits = [
        ("aaa", "docs(adr): ADR-0023"),
        ("bbb", "design(resource): rev 7"),
    ]

    assert gate.declares_docs_only(commits) is True


def test_one_source_commit_widens_the_declared_scope():
    """A branch that says it changes code is allowed to change code — the check fires
    on a broken promise, not on the absence of one."""
    commits = [
        ("aaa", "docs(adr): ADR-0023"),
        ("bbb", "feat(reporting): three math engines"),
    ]

    assert gate.declares_docs_only(commits) is False


def test_an_unlabelled_commit_widens_rather_than_narrows():
    """No parseable type means no promise. Treating it as a docs promise would fire
    the check on branches that never claimed anything."""
    commits = [("aaa", "docs(adr): ADR-0023"), ("bbb", "wip")]

    assert gate.declares_docs_only(commits) is False


def test_no_commits_is_not_a_docs_promise():
    assert gate.declares_docs_only([]) is False


def test_source_paths_are_the_strays_on_a_docs_branch():
    paths = [
        "docs/adr/0023-multi-tenant.md",
        "README.md",
        "src/reporting/statements/parser.py",
        "uv.lock",
    ]

    assert gate.non_doc_paths(paths) == [
        "src/reporting/statements/parser.py",
        "uv.lock",
    ]


def test_an_inherited_commit_does_not_get_to_widen_the_declared_scope():
    """The composition point between the two checks. A single inherited `feat(...)`
    commit would otherwise license every source file it dragged in, and the scope
    check would stay silent on the exact branch that motivated it."""
    commits = [
        ("f3e697d", "docs(adr): ADR-0020 draft"),
        ("dccb084", "feat(reporting): statement parsers and engines (#206)"),
    ]
    inherited = gate.inherited_commits(commits)
    own = [c for c in commits if c not in inherited]

    assert gate.declares_docs_only(commits) is False, "the raw list looks like code work"
    assert gate.declares_docs_only(own) is True, "with the inherited commit dropped, it is docs"


# --- preflight end-to-end, against a real git repository ------------------


def test_preflight_fires_on_a_branch_shaped_like_the_one_that_motivated_it(
    tmp_path, monkeypatch
):
    """An inherited squash-merge commit that drags source into a branch whose own
    commits are all prose."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _commit(repo, "docs/start.md", "docs: initial")
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "src/parsers.py", "feat(reporting): statement parsers (#206)")
    _commit(repo, "docs/adr/0023.md", "docs(adr): ADR-0023")

    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    assert gate.preflight("main") == ["base (git history)", "scope"]


def test_preflight_passes_on_a_branch_cut_from_the_current_base(tmp_path, monkeypatch):
    """The other half: a green run has to be reachable, or the gate is a wall rather
    than a check. Same docs commit, no inherited commit, no source."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _commit(repo, "docs/start.md", "docs: initial")
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "docs/adr/0023.md", "docs(adr): ADR-0023")

    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    assert gate.preflight("main") == []


def test_a_source_branch_that_declares_itself_is_left_alone(tmp_path, monkeypatch):
    """The false-positive guard. Ordinary feature work touches source and must pass —
    the scope check keys on a *broken promise*, not on source itself."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _commit(repo, "docs/start.md", "docs: initial")
    _git(repo, "checkout", "-b", "feature")
    _commit(repo, "src/engines.py", "feat(reporting): three math engines")
    _commit(repo, "docs/adr/0023.md", "docs(adr): record the decision")

    monkeypatch.setattr(gate, "REPO_ROOT", repo)

    assert gate.preflight("main") == []
