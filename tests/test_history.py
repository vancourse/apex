"""Retired history (rails/history.py), pre-push by remote ref, and the main-folder sync.

The rewrite is simulated the way jarvis's happened: a shared root A; the old history
B_old-C_old; trunk rewritten to B_new-C_new on the same root; a local branch keeps the
old tip alive, and worktrees sit on either side.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from rails import githooks, history, mainsync, receipts, leak, store
from rails.dispatch import GateRow
from rails.gates import state

ZERO = "0" * 40


@pytest.fixture
def rewritten(tmp_path, git, commit):
    """{top, A, old_tip, new_tip}: trunk (origin/main) was rewritten; `old-main` keeps the old tip."""
    top = tmp_path / "app"
    top.mkdir()
    git(top, "init", "-q", "-b", "main")
    git(top, "config", "user.email", "t@example.invalid")
    git(top, "config", "user.name", "t")
    git(top, "config", "core.autocrlf", "false")
    git(top, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    a = commit(top, "README.md", "hello\n", "A")
    commit(top, "notes.txt", "household value 1234.56\n", "B old")
    old_tip = commit(top, "more.txt", "more\n", "C old")
    git(top, "branch", "old-main", old_tip)
    git(top, "checkout", "-q", "--detach", a)
    commit(top, "notes.txt", "scrubbed\n", "B new")
    new_tip = commit(top, "more.txt", "more\n", "C new")
    git(top, "update-ref", "refs/remotes/origin/main", new_tip)
    git(top, "checkout", "-q", "-B", "main", new_tip)
    return {"top": top, "A": a, "old_tip": old_tip, "new_tip": new_tip}


def _branch(git, commit, top: Path, name: str, base: str) -> str:
    git(top, "checkout", "-q", "-B", name, base)
    sha = commit(top, f"{name}.txt", f"{name}\n", name)
    git(top, "checkout", "-q", "main")
    return sha


def _rows(monkeypatch):
    rows = {
        name: GateRow(name=name, module="prepush", events=["git:pre-push"], mode="enforce")
        for name in ("prepush_hold", "prepush_marker", "prepush_retired", "prepush_leak")
    }
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: False)


def _ready(rid, sha):
    """A quick marker and a fresh snapshot, so only the retired check can refuse."""
    receipts.write_marker(rid, sha, "t", ["checks"], quick=True)
    body = leak.build_snapshot(["9999.99"], {}, "test_role")
    store.write_json(leak.snapshot_path(rid), body)


def _line(sha: str, branch: str, source: str | None = None) -> str:
    return f"{source or 'refs/heads/' + branch} {sha} refs/heads/{branch} {ZERO}"


# --- the predicate ------------------------------------------------------------


def test_retire_refuses_a_tip_trunk_contains(rewritten):
    code, text = history.retire(rewritten["top"], rewritten["new_tip"], "origin/main")
    assert code == 2 and "refuse every push" in text
    assert history.tips(rewritten["top"]) == []


def test_retire_records_the_tip_and_the_trunk_once(rewritten):
    top = rewritten["top"]
    code, text = history.retire(top, "old-main", "origin/main")
    assert code == 0 and "2 commits not on origin/main" in text
    assert history.retire(top, "old-main")[0] == 0
    assert history.tips(top) == [rewritten["old_tip"]]
    assert history.trunk(top) == "origin/main"


def test_carried_by_separates_old_new_and_kept_ancestors(rewritten, git, commit):
    top = rewritten["top"]
    history.retire(top, "old-main", "origin/main")
    stale = _branch(git, commit, top, "stale", rewritten["old_tip"])
    fresh = _branch(git, commit, top, "fresh", rewritten["new_tip"])
    ancient = _branch(git, commit, top, "ancient", rewritten["A"])
    retired = history.load(top)
    assert retired is not None and not retired.problems
    assert retired.carried_by(stale) is not None
    assert retired.carried_by(rewritten["old_tip"]) == rewritten["old_tip"]
    assert retired.carried_by(fresh) is None
    assert retired.carried_by(ancient) is None  # shares only what the rewrite kept


# --- pre-push -----------------------------------------------------------------


def test_a_branch_built_on_retired_history_is_refused(rewritten, git, commit, monkeypatch):
    """The planted defect for `prepush_retired`."""
    _rows(monkeypatch)
    top = rewritten["top"]
    history.retire(top, "old-main", "origin/main")
    rid = store.find_repo(top)
    stale = _branch(git, commit, top, "stale", rewritten["old_tip"])
    fresh = _branch(git, commit, top, "fresh", rewritten["new_tip"])
    _ready(rid, stale)
    _ready(rid, fresh)
    code, msgs = githooks.pre_push([], [_line(stale, "stale")], rid)
    assert code == 1 and any("rewrote away" in m for m in msgs)
    assert githooks.pre_push([], [_line(fresh, "fresh")], rid) == (0, [])
    # a HEAD or raw-sha source is judged by what lands on the remote
    for source in ("HEAD", stale):
        code, msgs = githooks.pre_push([], [_line(stale, "x", source)], rid)
        assert code == 1 and any("rewrote away" in m for m in msgs)


def test_the_operator_switch_does_not_skip_retired_history(rewritten, git, commit, monkeypatch):
    _rows(monkeypatch)
    top = rewritten["top"]
    history.retire(top, "old-main", "origin/main")
    rid = store.find_repo(top)
    stale = _branch(git, commit, top, "stale", rewritten["old_tip"])
    _ready(rid, stale)
    monkeypatch.setenv("RAILS_OPERATOR", "1")
    code, msgs = githooks.pre_push([], [_line(stale, "stale")], rid)
    assert code == 1 and any("rewrote away" in m for m in msgs)


def test_a_retired_tip_missing_from_the_clone_fails_closed(rewritten, git, monkeypatch):
    _rows(monkeypatch)
    top = rewritten["top"]
    git(top, "config", "--add", history.CONFIG_TIPS, "1" * 40)
    git(top, "config", history.CONFIG_TRUNK, "origin/main")
    rid = store.find_repo(top)
    _ready(rid, rewritten["new_tip"])
    code, msgs = githooks.pre_push([], [_line(rewritten["new_tip"], "main")], rid)
    assert code == 1 and any("could not check" in m for m in msgs)


def test_a_repo_that_retired_nothing_is_untouched(repo, commit, monkeypatch):
    _rows(monkeypatch)
    rid = store.find_repo(repo)
    sha = commit(repo, "a.txt", "plain\n")
    _ready(rid, sha)
    assert history.load(repo) is None
    assert githooks.pre_push([], [_line(sha, "work")], rid) == (0, [])


def test_a_head_source_push_now_needs_its_marker(repo, commit, monkeypatch):
    """`git push origin HEAD:x` handed the hook local ref "HEAD" and skipped every check."""
    _rows(monkeypatch)
    rid = store.find_repo(repo)
    body = leak.build_snapshot(["9999.99"], {}, "test_role")
    store.write_json(leak.snapshot_path(rid), body)
    sha = commit(repo, "a.txt", "plain\n")
    code, msgs = githooks.pre_push([], [_line(sha, "x", "HEAD")], rid)
    assert code == 1 and "no quick check marker" in msgs[0]
    sha2 = commit(repo, "b.txt", "spent 9,999.99 here\n")
    receipts.write_marker(rid, sha2, "t", ["checks"], quick=True)
    code, msgs = githooks.pre_push([], [_line(sha2, "x", sha2)], rid)
    assert code == 1 and "FOUND" in msgs[0]


def test_carriers_lists_only_worktrees_on_retired_history(rewritten, git, commit, tmp_path):
    top = rewritten["top"]
    history.retire(top, "old-main", "origin/main")
    stale = _branch(git, commit, top, "stale", rewritten["old_tip"])
    _branch(git, commit, top, "fresh", rewritten["new_tip"])
    git(top, "worktree", "add", "-q", str(tmp_path / "wt-stale"), "stale")
    git(top, "worktree", "add", "-q", str(tmp_path / "wt-fresh"), "fresh")
    found = history.carriers(history.load(top))
    assert [(p.name, h) for p, _, h in found] == [("wt-stale", stale)]


def test_state_names_retired_history_under_this_worktree(rewritten, git, commit, tmp_path):
    top = rewritten["top"]
    history.retire(top, "old-main", "origin/main")
    _branch(git, commit, top, "stale", rewritten["old_tip"])
    git(top, "worktree", "add", "-q", str(tmp_path / "wt-stale"), "stale")
    text = state.render(store.find_repo(tmp_path / "wt-stale"))
    assert "RETIRED HISTORY" in text
    assert "RETIRED HISTORY" not in state.render(store.find_repo(top))


# --- the main folder ----------------------------------------------------------


@pytest.fixture
def behind(tmp_path, git, commit):
    """{main, wt}: main checkout on `main`, one commit behind origin/main; a worktree session."""
    main = tmp_path / "app"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "config", "user.email", "t@example.invalid")
    git(main, "config", "user.name", "t")
    git(main, "config", "core.autocrlf", "false")
    git(main, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    first = commit(main, "README.md", "hello\n", "first")
    commit(main, ".claude/hooks/old_gate.py", "print('x')\n", "a hook")
    second = commit(main, "src.txt", "v2\n", "second")
    git(main, "update-ref", "refs/remotes/origin/main", second)
    git(main, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(main, "reset", "-q", "--hard", "HEAD~1")
    git(main, "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "feature", "origin/main")
    del first
    return {"main": main, "wt": tmp_path / "wt", "trunk": second}


def test_session_start_fast_forwards_a_clean_main_folder(behind, git):
    rid = store.find_repo(behind["wt"])
    line = mainsync.at_session_start(rid, "me")
    assert line == "main folder fast-forwarded 1 commit(s) to origin/main"
    assert git(behind["main"], "rev-parse", "HEAD") == behind["trunk"]


def test_a_dirty_main_folder_is_not_touched(behind, git):
    (behind["main"] / "README.md").write_text("edited\n", encoding="utf-8")
    p = mainsync.plan(store.find_repo(behind["wt"]), "me")
    assert not p.act and "uncommitted" in p.line


def test_a_diverged_main_folder_is_not_touched(behind, git, commit):
    commit(behind["main"], "local.txt", "local\n", "local only")
    p = mainsync.plan(store.find_repo(behind["wt"]), "me")
    assert not p.act and "diverged" in p.line


def test_a_session_in_the_main_folder_does_not_move_it_under_itself(behind):
    p = mainsync.plan(store.find_repo(behind["main"]), "me")
    assert not p.act and "this session runs in it" in p.line


def test_an_update_that_deletes_a_hook_file_waits(behind, git, commit):
    main = behind["main"]
    git(main, "checkout", "-q", "--detach", "origin/main")
    git(main, "rm", "-q", ".claude/hooks/old_gate.py")
    git(main, "commit", "-q", "-m", "retire a hook")
    git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(main, "checkout", "-q", "main")
    p = mainsync.plan(store.find_repo(behind["wt"]), "me")
    assert not p.act and "under .claude/" in p.line
    assert mainsync.plan(store.find_repo(behind["wt"]), "me", manual=True, now=True).act


def test_another_active_session_in_the_main_folder_waits(behind, isolated_store):
    folder = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / store._key_for(behind["main"].resolve())
    folder.mkdir(parents=True)
    (folder / "me.jsonl").write_text("{}\n", encoding="utf-8")
    p = mainsync.plan(store.find_repo(behind["wt"]), "me")
    assert p.act  # only this session's own transcript
    (folder / "other.jsonl").write_text("{}\n", encoding="utf-8")
    p = mainsync.plan(store.find_repo(behind["wt"]), "me")
    assert not p.act and "1 other session(s)" in p.line
    old = time.time() - 3 * 3600
    os.utime(folder / "other.jsonl", (old, old))
    assert mainsync.plan(store.find_repo(behind["wt"]), "me").act


def test_a_main_folder_parked_on_another_branch_says_nothing(behind, git):
    git(behind["main"], "checkout", "-q", "-b", "parked")
    p = mainsync.plan(store.find_repo(behind["wt"]), "me")
    assert not p.act and p.line is None
