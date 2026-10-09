"""The session loop: claims, work items, intent read-back, the operator's words, state, turn end,
the store guard and the leak check at dispatch. Each `*_planted` test is the planted defect its
hooks/gates.toml row names."""

from __future__ import annotations

import json
import time
from pathlib import Path

from rails import claims, intent, leak, metrics, receipts, ship, store, work
from rails.dispatch import GateRow, dispatch
from rails.gates import state as state_gate
from rails.hookio import Event


def _evt(name, cwd, **payload):
    return Event(
        name=name,
        payload={
            "hook_event_name": name,
            "cwd": str(cwd),
            "session_id": "s1",
            **payload,
        },
    )


def _row(name, events, tools=(), shadow=False):
    return GateRow(
        name=name,
        module=name,
        events=list(events),
        tools=list(tools),
        mode="shadow" if shadow else "enforce",
    )


def _transcript(tmp_path, text):
    path = tmp_path / "t.jsonl"
    rows = [
        {"type": "user", "message": {"content": "do it"}},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return str(path)


# --- claims ----------------------------------------------------------------------


def test_claims_share_jarvis_store_format(repo):
    rid = store.find_repo(repo)
    ok, _ = claims.add(rid, "work", ["#12", "#34"])
    assert ok
    raw = json.loads(claims.claims_path(rid.main).read_text())
    assert raw == {
        "claims": {
            rid.leaf: {
                "branch": "work",
                "items": ["#12", "#34"],
                "at": raw["claims"][rid.leaf]["at"],
            }
        }
    }
    assert claims.mine(rid).items == ["#12", "#34"]
    claims.release(rid)
    assert claims.mine(rid) is None


def test_wip_one_app_refuses_a_second_release_milestone(repo, tmp_path):
    rid = store.find_repo(repo)
    other = store.RepoId(
        main=rid.main, top=tmp_path / "other", key=rid.key, leaf="other"
    )
    assert claims.add(other, "b", ["Purser R14"], kind="release")[0]
    ok, message = claims.add(rid, "work", ["Sherpa R2"], kind="release")
    assert not ok and "WIP is one app" in message
    assert claims.add(rid, "work", ["Sherpa R2"], kind="prep")[0]
    store.write_json(rid.dir / "state.json", {"used": [{"milestone": "Purser R14"}]})
    assert claims.add(rid, "work", ["Sherpa R2"], kind="release")[0]


def test_claim_edit_planted(repo):
    """No claim + a source edit -> deny. A claim -> allowed, and the path is recorded."""
    evt = _evt(
        "PreToolUse",
        repo,
        tool_name="Edit",
        tool_input={"file_path": str(repo / "src" / "a.py")},
    )
    rows = [_row("claim_edit", ["PreToolUse"], ["Edit"])]
    assert dispatch(evt, rows).denies
    claims.add(store.find_repo(repo), "work", ["#1"])
    assert not dispatch(evt, rows).denies
    assert "src/a.py" in claims.load(store.find_repo(repo))[0].paths


def test_claim_edit_ignores_paths_outside_any_repo(tmp_path):
    evt = _evt(
        "PreToolUse",
        tmp_path,
        tool_name="Write",
        tool_input={"file_path": str(tmp_path / "scratch.md")},
    )
    assert not dispatch(evt, [_row("claim_edit", ["PreToolUse"], ["Write"])]).denies


# --- work items ------------------------------------------------------------------


def test_item_closes_only_on_a_passing_step(repo):
    rid = store.find_repo(repo)
    work.add(rid, "export works", step="a1")
    ok, message = work.mark_done(rid, "a1")
    assert not ok and "no passing walk receipt" in message
    receipts.write(
        rid, "walk", instrument="walk:fixture", steps=[{"step": "a1", "pass": True}]
    )
    assert not work.mark_done(rid, "a1")[0], "a fixture instrument cannot close an item"
    receipts.write(
        rid, "walk", instrument="walk:planted", steps=[{"step": "a1", "pass": True}]
    )
    assert work.mark_done(rid, "a1")[0]


def test_decision_needed_requires_a_recommendation(repo):
    rid = store.find_repo(repo)
    assert not work.set_stop_reason(rid, "decision_needed", "should I?")[0]
    assert work.set_stop_reason(
        rid, "decision_needed", "A or B; B costs a day; recommend A"
    )[0]


# --- intent ----------------------------------------------------------------------------


def _intent(repo, text="# Export CSV\n\nBuilds: the export button.\n"):
    (repo / ".rails").mkdir(exist_ok=True)
    (repo / ".rails" / "intent.md").write_text(text, encoding="utf-8")
    return intent.current_hash(repo)


def test_intent_shown_planted(repo, tmp_path):
    """An intent never shown blocks the Stop once; shown with its marker, it stamps and passes."""
    h = _intent(repo)
    rows = [_row("intent_shown", ["Stop"])]
    out = dispatch(
        _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done, all good")),
        rows,
    )
    assert out.blocks and intent.marker(h) in out.blocks[0]
    again = dispatch(
        _evt("Stop", repo, transcript_path=_transcript(tmp_path, "still nothing")), rows
    )
    assert not again.blocks, "blocks once per hash, never loops"
    shown = dispatch(
        _evt(
            "Stop",
            repo,
            transcript_path=_transcript(tmp_path, f"Plan:\n...\n{intent.marker(h)}"),
        ),
        rows,
    )
    assert not shown.blocks
    assert intent.get(store.find_repo(repo))["shown_at"]


def test_next_human_message_acks_or_corrects(repo, tmp_path):
    h = _intent(repo)
    rid = store.find_repo(repo)
    intent.update(rid, hash=h, shown_at=int(time.time()) - 60)
    rows = [_row("prompt_words", ["UserPromptSubmit"])]
    out = dispatch(
        _evt("UserPromptSubmit", repo, prompt="no, export to xlsx instead"), rows
    )
    assert "Rewrite .rails/intent.md" in out.notices[0]
    assert intent.get(rid).get("acked_hash") == ""
    # The corrected intent is no longer "shown": the next message cannot ack it (review of 1.3.0).
    out = dispatch(_evt("UserPromptSubmit", repo, prompt="how is it going?"), rows)
    assert not out.notices and not intent.acked(rid, repo)
    # Re-shown unchanged, it still is not acked: the operator corrected that text.
    assert not intent.stamp_if_shown(rid, repo, f"...{intent.marker(h)}")
    out = dispatch(_evt("UserPromptSubmit", repo, prompt="ok"), rows)
    assert not intent.acked(rid, repo)
    # Rewritten and shown, the next message acks the new text.
    (repo / ".rails" / "intent.md").write_text("# Export to xlsx\n\nAs corrected.\n", encoding="utf-8")
    h2 = intent.current_hash(repo)
    assert h2 != h and intent.stamp_if_shown(rid, repo, f"...{intent.marker(h2)}")
    intent.update(rid, shown_at=int(time.time()) - 60)
    out = dispatch(_evt("UserPromptSubmit", repo, prompt="looks right"), rows)
    assert f"intent {h2} acked by message" in out.notices[0]
    assert intent.acked(rid, repo)


def test_machine_messages_never_ack(repo):
    h = _intent(repo)
    rid = store.find_repo(repo)
    intent.update(rid, hash=h, shown_at=int(time.time()) - 60)
    rows = [_row("prompt_words", ["UserPromptSubmit"])]
    dispatch(
        _evt(
            "UserPromptSubmit",
            repo,
            prompt="<task-notification>done</task-notification>",
        ),
        rows,
    )
    dispatch(_evt("UserPromptSubmit", repo, prompt="ok", agent_id="sub1"), rows)
    assert not intent.acked(rid, repo)


def test_classifier_fixture_per_class():
    for text in (
        "no, do X",
        "Actually make it blue",
        "wait",
        "use B instead of A",
        "that's not what I asked",
        "I meant the other one",
    ):
        assert intent.classify(text) == "changes", text
    for text in ("yes", "looks good, go", "ship it", "great - and also check the docs"):
        assert intent.classify(text) == "approves", text


# --- the operator's words -------------------------------------------------------------


def test_hold_and_release_words(repo):
    rows = [_row("prompt_words", ["UserPromptSubmit"])]
    rid = store.find_repo(repo)
    dispatch(_evt("UserPromptSubmit", repo, prompt="hold"), rows)
    assert store.read_json(rid.dir / "state.json")["hold"]["on"] is True
    dispatch(_evt("UserPromptSubmit", repo, prompt="release"), rows)
    assert store.read_json(rid.dir / "state.json")["hold"]["on"] is False
    dispatch(
        _evt(
            "UserPromptSubmit", repo, prompt="used #76 shipped one PR through the loop"
        ),
        rows,
    )
    assert store.read_json(rid.dir / "state.json")["used"][0]["milestone"] == "#76"
    log = store.read_jsonl(rid.dir / "ceremony.jsonl")
    assert [r["class"] for r in log] == ["hold", "release", "used"]
    assert all("prompt" not in r and "text" not in r for r in log), (
        "the ceremony log never stores text"
    )


# --- state -------------------------------------------------------------------------------


def test_state_fits_the_budget_even_when_everything_is_on(repo):
    rid = store.find_repo(repo)
    claims.add(rid, "work", [f"#{n}" for n in range(1000, 1200)])
    store.write_json(rid.dir / "state.json", {"hold": {"on": True, "since": "now"}})
    for n in range(40):
        work.add(rid, f"item {n}", step=f"s{n}")
    text = state_gate.render(rid)
    assert len(text) <= state_gate.MAX_CHARS
    assert "HOLD is on" in text


def test_state_touches_the_heartbeat(repo):
    dispatch(_evt("SessionStart", repo), [_row("state", ["SessionStart"])])
    assert (store.data_root() / "heartbeat").exists()


# --- turn end ------------------------------------------------------------------------------


def test_turn_end_planted(repo, tmp_path):
    """An armed PR with an unproven closing step blocks; the fourth try records `unverified`."""
    rid = store.find_repo(repo)
    item = work.add(rid, "export", step="a1")
    with store.updating(work.path(rid), {}) as data:
        data["items"][0]["closes"] = "#9"
    store.write_json(
        rid.leaf_dir / "pr.json", {"number": 5, "armed": True, "monitor": "bound"}
    )
    rows = [_row("turn_end", ["Stop"])]
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    for _ in range(3):
        assert dispatch(evt, rows).blocks
    assert not dispatch(evt, rows).blocks
    assert work.load(rid)["items"][0]["status"] == "unverified"
    assert item["id"] == "a1"


def test_turn_end_offer_shape_blocks_once_without_a_stop_reason(repo, tmp_path):
    rid = store.find_repo(repo)
    work.add(rid, "next thing")
    rows = [_row("turn_end", ["Stop"])]
    offer = _evt(
        "Stop",
        repo,
        transcript_path=_transcript(tmp_path, "Done with A. Want me to do B next?"),
    )
    assert dispatch(offer, rows).blocks
    work.set_stop_reason(rid, "wip", "B waits for the operator's used")
    assert not dispatch(offer, rows).blocks


def test_turn_end_shadow_has_no_side_effects(repo, tmp_path):
    rid = store.find_repo(repo)
    work.add(rid, "export", step="a1")
    with store.updating(work.path(rid), {}) as data:
        data["items"][0]["closes"] = "#9"
    store.write_json(
        rid.leaf_dir / "pr.json", {"number": 5, "armed": True, "monitor": "unbound"}
    )
    rows = [_row("turn_end", ["Stop"], shadow=True)]
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    for _ in range(5):
        assert not dispatch(evt, rows).blocks
    assert work.load(rid)["items"][0]["status"] == "open"
    assert [f["verdict"] for f in store.read_jsonl(rid.dir / "firings.jsonl")].count(
        "would-block"
    ) == 5


# --- store guard and leak at dispatch --------------------------------------------------------


def test_store_guard_planted(repo):
    rows = [_row("store_guard", ["PreToolUse"], ["Bash", "Read", "PowerShell"])]
    key_read = _evt(
        "PreToolUse",
        repo,
        tool_name="Read",
        tool_input={"file_path": "C:\\Users\\x\\.claude\\rails\\receipts.key"},
    )
    assert dispatch(key_read, rows).denies
    marker_write = _evt(
        "PreToolUse",
        repo,
        tool_name="PowerShell",
        tool_input={
            "command": "Set-Content C:/Users/x/.claude/rails/K/leaf/markers/check-1.ok x"
        },
    )
    assert dispatch(marker_write, rows).denies
    switch = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": "RAILS_OPERATOR=1 git push"},
    )
    assert dispatch(switch, rows).denies
    log_read = _evt(
        "PreToolUse",
        repo,
        tool_name="Read",
        tool_input={"file_path": "C:/Users/x/.claude/rails/K/leaf/logs/abc/suite.log"},
    )
    assert not dispatch(log_read, rows).denies
    cli = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": "rails check --post"},
    )
    assert not dispatch(cli, rows).denies


def _leaky_repo(repo):
    (repo / "rails").mkdir(exist_ok=True)
    (repo / "rails" / "leak.toml").write_text(
        '[snapshot]\nstore_env = "HOUSEHOLD_STORE"\n', encoding="utf-8"
    )
    rid = store.find_repo(repo)
    store.write_json(
        leak.snapshot_path(rid),
        leak.build_snapshot(["1234.56"], {"SOMEPLACE": "descriptor"}, "t"),
    )
    return rid


def test_leak_dispatch_planted(repo):
    """A gh api --input file carrying a snapshot value is refused, and the value is never echoed."""
    _leaky_repo(repo)
    body = repo / "body.json"
    body.write_text(
        json.dumps({"body": "we paid 1,234.56 at SQ *SOME PLACE"}), encoding="utf-8"
    )
    rows = [_row("leak_dispatch", ["PreToolUse"], ["Bash", "PowerShell", "Agent"])]
    evt = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={
            "command": f"gh api repos/o/r/issues --method POST --input {body.name}"
        },
    )
    out = dispatch(evt, rows)
    assert (
        out.denies
        and "1,234.56" not in out.denies[0]
        and "1234.56" not in out.denies[0]
        and "SOME" not in out.denies[0]
    )
    ps = _evt(
        "PreToolUse",
        repo,
        tool_name="PowerShell",
        tool_input={"command": 'gh pr create --title "x" --body "total 1234.56"'},
    )
    assert dispatch(ps, rows).denies
    commit_msg = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": 'git commit -m "fix: 1234.56 rounding"'},
    )
    assert dispatch(commit_msg, rows).denies
    agent = _evt(
        "PreToolUse",
        repo,
        tool_name="Agent",
        tool_input={"prompt": "the user spent 1234.56 at someplace"},
    )
    assert dispatch(agent, rows).denies
    clean = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": 'gh pr create --title "x" --body "no values here"'},
    )
    assert not dispatch(clean, rows).denies


def test_leak_dispatch_inactive_without_leak_toml(repo):
    rows = [_row("leak_dispatch", ["PreToolUse"], ["Bash"])]
    evt = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": 'gh pr create --body "1234.56"'},
    )
    assert not dispatch(evt, rows).denies


def test_leak_dispatch_fails_closed_without_snapshot(repo):
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text("[snapshot]\n", encoding="utf-8")
    rows = [_row("leak_dispatch", ["PreToolUse"], ["Bash"])]
    evt = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": 'gh issue create --title t --body "hello"'},
    )
    out = dispatch(evt, rows)
    assert out.denies and "could not look" in out.denies[0]


# --- metrics and ship text -------------------------------------------------------------------


def test_metrics_usage_and_the_70_percent_line():
    items = [
        {
            "product": "actions",
            "repositoryName": "jarvis",
            "unitType": "Minutes",
            "quantity": 2200,
            "grossAmount": 13.2,
            "netAmount": 0,
        },
        {
            "product": "actions",
            "repositoryName": "other",
            "unitType": "Minutes",
            "quantity": 900,
            "grossAmount": 5,
            "netAmount": 5,
        },
        {
            "product": "actions",
            "repositoryName": "jarvis",
            "unitType": "GigabyteHours",
            "quantity": 9,
            "grossAmount": 0.1,
            "netAmount": 0,
        },
    ]
    m = metrics.summarise_usage(items, "jarvis")
    assert m["minutes_month"] == 2200
    assert metrics.line_for({**m, "included_minutes": 3000}).startswith(
        "CI minutes 2200/3000"
    )
    assert metrics.line_for({**m, "included_minutes": 4000}) is None


def test_ship_body_puts_each_close_on_its_own_line(repo):
    rid = store.find_repo(repo)
    body = ship.compose_body("Intent here.", ["12", "#34"], rid, "deadbeef" * 5)
    assert "Closes #12\n\nCloses #34" in body


def _ship_fixture(repo, git, commit, monkeypatch):
    """A repo with a bare origin, a sealed full marker, and gh faked at the module seam."""
    import subprocess as sp

    remote = repo.parent / "origin.git"
    sp.run(["git", "init", "-q", "--bare", str(remote)], check=True)
    git(repo, "remote", "add", "origin", "https://github.com/acme/app.git")
    git(repo, "config", f"url.{remote.as_posix()}.insteadOf", "https://github.com/acme/app.git")
    sha = commit(repo, "a.txt", "x\n")
    rid = store.find_repo(repo)
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    calls = {"api": [], "gh": [], "merge": []}

    def fake_gh(top, *args, check=True, timeout=60):
        calls["gh"].append(args)
        return ""  # `gh pr view`: no open PR yet

    def fake_api(top, path, *, method="GET", payload=None, timeout=60):
        calls["api"].append((path, method, payload))
        if path == "repos/acme/app":
            return {"default_branch": "main"}
        return {"number": 7, "html_url": "https://github.com/acme/app/pull/7"}

    real_run = sp.run

    def fake_run(args, *a, **kw):
        if args and args[0] == "gh":
            calls["merge"].append(args)
            return sp.CompletedProcess(args, 0, "", "")
        return real_run(args, *a, **kw)

    monkeypatch.setattr(ship, "gh", fake_gh)
    monkeypatch.setattr(ship, "gh_api", fake_api)
    monkeypatch.setattr(ship.subprocess, "run", fake_run)
    import rails.check as check_mod

    monkeypatch.setattr(check_mod, "post", lambda top, out=None: 0)
    return rid, sha, calls


def test_ship_opens_one_pr_through_the_api_and_arms_it(repo, git, commit, monkeypatch):
    import io

    rid, sha, calls = _ship_fixture(repo, git, commit, monkeypatch)
    out = io.StringIO()
    code = ship.ship(repo, title="Export CSV — the summary", body="b", base=None, closes=["12"], out=out)
    assert code == 0, out.getvalue()
    created = [c for c in calls["api"] if c[0] == "repos/acme/app/pulls"]
    assert len(created) == 1 and created[0][2]["title"] == "Export CSV — the summary"
    assert "Closes #12" in created[0][2]["body"]
    assert calls["merge"] == [["gh", "pr", "merge", "7", "--auto", "--squash"]]
    pr = store.read_json(rid.leaf_dir / "pr.json")
    assert pr["number"] == 7 and pr["armed"] is True and pr["sha"] == sha


def test_ship_no_arm_leaves_the_pr_unarmed(repo, git, commit, monkeypatch):
    import io

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    assert ship.ship(repo, title="t", body="b", base="main", closes=[], arm=False, out=io.StringIO()) == 0
    assert calls["merge"] == []
    assert store.read_json(rid.leaf_dir / "pr.json")["armed"] is False


def test_a_reship_refreshes_the_open_prs_body(repo, git, commit, monkeypatch):
    """The review line (and an --accept reason) must reach the PR the operator reads."""
    import io

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    monkeypatch.setattr(
        ship, "gh", lambda top, *a, check=True, timeout=60: '{"number": 7, "state": "OPEN", "url": "u"}'
    )
    out = io.StringIO()
    assert ship.ship(repo, title="t", body="the new body", base="main", closes=[], arm=False, out=out) == 0
    patched = [c for c in calls["api"] if c[0] == "repos/acme/app/pulls/7" and c[1] == "PATCH"]
    assert len(patched) == 1 and "the new body" in patched[0][2]["body"]
    assert not [c for c in calls["api"] if c[0] == "repos/acme/app/pulls"]  # reused, not created


def test_a_reship_keeps_the_first_ships_closes_line(repo, git, commit, monkeypatch):
    """`rails ship --closes 457` unarmed, then `rails ship` as told: #457 must still close."""
    import io

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    assert ship.ship(repo, title="t", body="b", base="main", closes=["457"], arm=False, out=io.StringIO()) == 0
    monkeypatch.setattr(
        ship, "gh", lambda top, *a, check=True, timeout=60: '{"number": 7, "state": "OPEN", "url": "u"}'
    )
    assert ship.ship(repo, title="t", body="", base="main", closes=[], arm=False, out=io.StringIO()) == 0
    patched = [c for c in calls["api"] if c[0] == "repos/acme/app/pulls/7" and c[1] == "PATCH"]
    assert patched and "Closes #457" in patched[-1][2]["body"] and "b" in patched[-1][2]["body"]


def test_claims_hold_an_issue_in_one_worktree_and_follow_a_branch_switch(repo, git, tmp_path):
    rid = store.find_repo(repo)
    assert claims.add(rid, "work", ["#12"])[0]
    other_top = tmp_path / "other"
    git(repo, "worktree", "add", "-q", "-b", "other", str(other_top))
    other = store.find_repo(other_top)
    ok, message = claims.add(other, "other", ["#12"])
    assert not ok and "already held by" in message
    assert claims.add(other, "other", ["#13"])[0]
    assert claims.add(rid, "work2", ["#14"])[0]  # same worktree, new branch: the claim follows
    mine = claims.mine(rid)
    assert mine.branch == "work2" and set(mine.items) == {"#12", "#14"}


def test_ship_refuses_without_the_full_marker(repo, commit):
    import io

    commit(repo, "a.txt", "x\n")
    out = io.StringIO()
    assert ship.ship(repo, title="t", body="b", base=None, closes=[], out=out) == 1
    assert "no full check marker" in out.getvalue()


def test_ship_leak_check_follows_the_leak_gates_shadow(repo, git, commit, monkeypatch):
    import io

    from rails import githooks

    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text("[snapshot]\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "leak config")
    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    monkeypatch.setattr(githooks, "_shadowed", lambda name: True)
    out = io.StringIO()
    assert ship.ship(repo, title="t", body="b", base="main", closes=[], arm=False, out=out) == 0
    assert "rails shadow: leak check would refuse" in out.getvalue()
    monkeypatch.setattr(githooks, "_shadowed", lambda name: False)
    out = io.StringIO()
    assert ship.ship(repo, title="t", body="b", base="main", closes=[], arm=False, out=out) == 1
    assert "could not look" in out.getvalue()
