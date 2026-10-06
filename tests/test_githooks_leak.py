"""Pre-push refusals, hook chaining, adopt, and the value-snapshot leak check."""

from __future__ import annotations

import datetime as _dt
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rails import adopt, githooks, leak, receipts, store
from rails.dispatch import GateRow

ZERO = "0" * 40


def _no_shadow(monkeypatch, shadow: set[str] = frozenset()):
    rows = {
        name: GateRow(
            name=name,
            module="prepush",
            events=["git:pre-push"],
            mode="shadow" if name in shadow else "enforce",
        )
        for name in ("prepush_hold", "prepush_marker", "prepush_leak")
    }
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: False)


def _snapshot(rid, amounts=(), words=None, age_days=0):
    body = leak.build_snapshot(list(amounts), dict(words or {}), "test_role")
    body["created"] -= age_days * 86400
    store.write_json(leak.snapshot_path(rid), body)


def _refs(sha):
    return [f"refs/heads/work {sha} refs/heads/work {ZERO}"]


def test_push_without_marker_refused(repo, commit, monkeypatch):
    _no_shadow(monkeypatch)
    rid = store.find_repo(repo)
    _snapshot(rid, ["1234.56"])
    sha = commit(repo, "a.txt", "plain\n")
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 1 and "no quick check marker" in msgs[0]
    receipts.write_marker(rid, sha, "t", ["checks"], quick=True)
    assert githooks.pre_push([], _refs(sha), rid) == (0, [])


def test_open_pr_needs_the_full_marker(repo, commit, monkeypatch):
    _no_shadow(monkeypatch)
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: True)
    rid = store.find_repo(repo)
    _snapshot(rid, ["1234.56"])
    sha = commit(repo, "a.txt", "plain\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=True)
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 1 and "no full check marker" in msgs[0]


def test_hold_refuses_and_operator_skips_marker_and_hold_never_leak(
    repo, commit, monkeypatch
):
    _no_shadow(monkeypatch)
    rid = store.find_repo(repo)
    _snapshot(rid, ["1234.56"])
    sha = commit(repo, "a.txt", "plain\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    store.write_json(rid.dir / "state.json", {"hold": {"on": True, "since": "now"}})
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 1 and "hold" in msgs[0]
    monkeypatch.setenv("RAILS_OPERATOR", "1")
    assert githooks.pre_push([], _refs(sha), rid)[0] == 0
    sha2 = commit(repo, "b.txt", "spent 1,234.56 here\n")
    code, msgs = githooks.pre_push([], _refs(sha2), rid)
    assert (
        code == 1
        and "FOUND" in msgs[0]
        and "1234.56" not in msgs[0]
        and "1,234.56" not in msgs[0]
    )


def test_operator_switch_ignored_inside_an_agent(repo, commit, monkeypatch):
    _no_shadow(monkeypatch)
    rid = store.find_repo(repo)
    _snapshot(rid, [])
    _snapshot(rid, ["1234.56"])
    sha = commit(repo, "a.txt", "plain\n")
    monkeypatch.setenv("RAILS_OPERATOR", "1")
    monkeypatch.setenv("CLAUDECODE", "1")
    assert githooks.pre_push([], _refs(sha), rid)[0] == 1


def test_leak_check_fails_closed_without_a_fresh_snapshot(repo, commit, monkeypatch):
    _no_shadow(monkeypatch)
    rid = store.find_repo(repo)
    sha = commit(repo, "a.txt", "plain\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 1 and "could not look" in msgs[0]
    _snapshot(rid, ["1234.56"], age_days=15)
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 1 and "days old" in msgs[0]


def test_shadow_logs_and_lets_the_push_through(repo, commit, monkeypatch):
    _no_shadow(monkeypatch, shadow={"prepush_marker", "prepush_leak"})
    rid = store.find_repo(repo)
    sha = commit(repo, "a.txt", "plain\n")
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 0
    assert any("shadow" in m for m in msgs)
    verdicts = [f["verdict"] for f in store.read_jsonl(rid.dir / "firings.jsonl")]
    assert verdicts.count("would-deny") == 2


def test_commit_message_is_checked(repo, commit, monkeypatch):
    _no_shadow(monkeypatch)
    rid = store.find_repo(repo)
    _snapshot(rid, ["1234.56"])
    sha = commit(repo, "a.txt", "plain\n", message="paid 1234.56 to them")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    code, msgs = githooks.pre_push([], _refs(sha), rid)
    assert code == 1 and "message" in msgs[0]


# --- the matcher ----------------------------------------------------------------


def test_matcher_amounts_and_words_on_token_boundaries(repo):
    rid = store.find_repo(repo)
    _snapshot(
        rid,
        ["1234.56", "99.99", "1200.00"],
        {"SOMEPLACE": "descriptor", "AB12CD34": "booking id"},
    )
    snap = leak.load_snapshot(rid)
    lines = [
        ("f", 1, "amount 1234.56"),
        ("f", 2, "grouped 1,234.56"),
        ("f", 3, "small 99.99 and round 1200.00"),
        ("f", 4, 'merchant "SQ *SOME PLACE"'),
        ("f", 5, "SOMEPLACEHOLDER is not it"),
        ("f", 6, "ref ab12-cd34"),
        ("f", 7, "x = 11234.567"),
    ]
    hits = {(n, k) for _, n, k, _ in leak.scan(lines, snap)}
    assert hits == {(1, "amount"), (2, "amount"), (4, "descriptor"), (6, "booking id")}


def test_snapshot_holds_no_plaintext(repo):
    rid = store.find_repo(repo)
    _snapshot(rid, ["4321.09"], {"SECRETPLACE": "descriptor"})
    raw = leak.snapshot_path(rid).read_text()
    assert "4321.09" not in raw and "SECRETPLACE" not in raw


def test_allowlist_covers_a_reviewed_line(repo):
    rid = store.find_repo(repo)
    _snapshot(rid, ["1234.56"])
    allow = repo / "allow.toml"
    ident = leak.line_id("price 1234.56")
    allow.write_text(
        f'[[allow]]\npath = "docs/*"\nkind = "amount"\nlines = ["{ident}"]\nwhy = "a public price"\n'
    )
    r = leak.check_lines(rid, [("docs/x.md", 1, "price 1234.56")], allow)
    assert r.code == leak.EXIT_CLEAN
    r = leak.check_lines(rid, [("src/x.py", 1, "price 1234.56")], allow)
    assert r.code == leak.EXIT_FOUND


# --- chaining and adopt ---------------------------------------------------------


def test_adopt_sets_hooks_path_and_chains_the_previous_dir(repo, tmp_path, git):
    prev = tmp_path / "prev-hooks"
    prev.mkdir()
    marker = tmp_path / "chained-ran"
    (prev / "pre-commit").write_text(
        f'#!/bin/sh\necho ran > "{marker.as_posix()}"\n', encoding="utf-8", newline="\n"
    )
    git(repo, "config", "core.hooksPath", str(prev))
    assert adopt.adopt(repo, out=io.StringIO()) == 0
    assert (
        Path(git(repo, "config", "--get", "core.hooksPath")).resolve()
        == adopt.HOOKS_DIR.resolve()
    )
    assert (
        Path(git(repo, "config", "--get", "rails.chainHooksPath")).resolve()
        == prev.resolve()
    )
    (repo / "x.txt").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "x")
    assert marker.exists(), "the repo's own pre-commit must still run after adopt"
    assert ".rails/" in (repo / ".git" / "info" / "exclude").read_text()
    assert (
        adopt.adopt(repo, out=io.StringIO()) == 0
    )  # idempotent: does not chain into itself
    assert (
        Path(git(repo, "config", "--get", "rails.chainHooksPath")).resolve()
        == prev.resolve()
    )


def test_adopt_retires_the_push_consent_gate(repo, git):
    githooks_dir = repo / ".githooks"
    githooks_dir.mkdir()
    (githooks_dir / "pre-push").write_text(
        '#!/bin/sh\n[ -n "$JARVIS_PUSH_OK" ] || exit 1\n'
    )
    adopt.adopt(repo, retire_push_consent=True, out=io.StringIO())
    assert not (githooks_dir / "pre-push").exists()
    assert any(
        p.name.startswith("pre-push.retired-by-rails-") for p in githooks_dir.iterdir()
    )


def test_git_hook_wrapper_runs_end_to_end(repo, commit, git, monkeypatch):
    """A real `git push` to a bare remote goes through the plugin's pre-push."""
    remote = repo.parent / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", str(remote))
    adopt.adopt(repo, out=io.StringIO())
    sha = commit(repo, "a.txt", "plain\n")
    rid = store.find_repo(repo)
    _snapshot(rid, ["1234.56"])
    env = {**__import__("os").environ}
    done = subprocess.run(
        ["git", "push", "-q", "origin", "work"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    gates = [f["gate"] for f in store.read_jsonl(rid.dir / "firings.jsonl")]
    assert "prepush_marker" in gates, done.stderr
    receipts.write_marker(rid, sha, "t", ["checks"], quick=True)
    done = subprocess.run(
        ["git", "push", "-q", "origin", "work"],
        cwd=repo,
        capture_output=True,
        text=True,
        env=env,
    )
    assert done.returncode == 0, done.stderr
