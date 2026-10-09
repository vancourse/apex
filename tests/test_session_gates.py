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
    store.write_json(rid.dir / "state.json", {"used": [{"milestone": "Purser R14", "by": "shell"}]})
    assert not claims.add(rid, "work", ["Sherpa R2"], kind="release")[0]  # a shell `used` lifts nothing
    store.write_json(rid.dir / "state.json", {"used": [{"milestone": "Purser R14", "by": "prompt"}]})
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
        rid,
        "walk",
        instrument="walk:fixture",
        steps=[{"step": "a1", "pass": True}],
        **work.walk_scope(rid),
    )
    assert not work.mark_done(rid, "a1")[0], "a fixture instrument cannot close an item"
    receipts.write(
        rid,
        "walk",
        instrument="walk:planted",
        steps=[{"step": "a1", "pass": True}],
        **work.walk_scope(rid),
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


def test_ship_opens_one_pr_through_the_api_and_arms_it(repo, git, commit, monkeypatch, tmp_path):
    """A reviewed tree arms; an unreviewed one does not, shadow week or not (p2)."""
    import io

    from rails import review

    rid, sha, calls = _ship_fixture(repo, git, commit, monkeypatch)
    clean = '{"must_fix": []}'
    (tmp_path / "c.md").write_text("Steelman.\n" + clean + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean + "y" * 220, encoding="utf-8")
    monkeypatch.chdir(repo)
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    from rails import githooks

    githooks.hold_pr(rid, 7, "earlier", "a push no review covers disarmed it")
    out = io.StringIO()
    code = ship.ship(repo, title="Export CSV — the summary", body="b", base=None, closes=["12"], out=out)
    assert code == 0, out.getvalue()
    created = [c for c in calls["api"] if c[0] == "repos/acme/app/pulls"]
    assert len(created) == 1 and created[0][2]["title"] == "Export CSV — the summary"
    assert "Closes #12" in created[0][2]["body"]
    assert calls["merge"] == [["gh", "pr", "merge", "7", "--auto", "--squash"]]
    pr = store.read_json(rid.leaf_dir / "pr.json")
    assert pr["number"] == 7 and pr["armed"] is True and pr["sha"] == sha
    assert "7" not in githooks.pr_holds(rid), "a reviewed arm releases the hold"


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
    body = patched[-1][2]["body"]
    assert "Closes #457" in body and body.startswith("b\n") and body.count("Closes #457") == 1


def test_a_merged_prs_lines_do_not_leak_into_the_next_pr(repo, git, commit, monkeypatch):
    import io

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    assert ship.ship(repo, title="t", body="first", base="main", closes=["#457"], detected_by="review",
                     arm=False, out=io.StringIO()) == 0
    monkeypatch.setattr(
        ship, "gh", lambda top, *a, check=True, timeout=60: '{"number": 7, "state": "MERGED", "url": "u"}'
    )
    assert ship.ship(repo, title="next", body="second", base="main", closes=[], arm=False, out=io.StringIO()) == 0
    created = [c for c in calls["api"] if c[0] == "repos/acme/app/pulls"]
    assert "Closes #457" not in created[-1][2]["body"] and "Detected-by" not in created[-1][2]["body"]


def test_claims_hold_an_issue_in_one_worktree_and_follow_a_branch_switch(repo, git, tmp_path):
    first_top = tmp_path / "first"
    git(repo, "worktree", "add", "-q", "-b", "first", str(first_top))
    rid = store.find_repo(first_top)  # a worktree, not the main checkout (whose claims are advisory)
    assert claims.add(rid, "first", ["#12"])[0]
    other_top = tmp_path / "other"
    git(repo, "worktree", "add", "-q", "-b", "other", str(other_top))
    other = store.find_repo(other_top)
    ok, message = claims.add(other, "other", ["#12"])
    assert not ok and "already held by" in message
    assert claims.add(other, "other", ["#13"])[0]
    assert claims.add(rid, "first2", ["#14"])[0]  # same worktree, new branch: the claim follows
    mine = claims.mine(rid)
    assert mine.branch == "first2" and set(mine.items) == {"#12", "#14"}


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


def test_a_reship_reads_the_current_intent_not_the_first_ones(repo, git, commit, monkeypatch):
    import io

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    (repo / ".rails").mkdir(exist_ok=True)
    (repo / ".rails" / "intent.md").write_text("# Export\n\nBuilds: CSV.\n", encoding="utf-8")
    assert ship.ship(repo, title="", body="", base="main", closes=[], arm=False, out=io.StringIO()) == 0
    (repo / ".rails" / "intent.md").write_text("# Export\n\nBuilds: XLSX.\n", encoding="utf-8")
    monkeypatch.setattr(
        ship, "gh", lambda top, *a, check=True, timeout=60: '{"number": 7, "state": "OPEN", "url": "u"}'
    )
    assert ship.ship(repo, title="", body="", base="main", closes=[], arm=False, out=io.StringIO()) == 0
    patched = [c for c in calls["api"] if c[0] == "repos/acme/app/pulls/7" and c[1] == "PATCH"]
    assert "XLSX" in patched[-1][2]["body"] and "CSV" not in patched[-1][2]["body"]


# --- p3c, p3d: a walk receipt is bound to its tree and its line of work ---------------


def _walked(rid, step="a1"):
    receipts.write(
        rid,
        "walk",
        instrument="walk:planted",
        steps=[{"step": step, "pass": True}],
        **work.walk_scope(rid),
    )


def test_p3c_a_receipt_from_another_code_tree_closes_nothing(repo, commit):
    rid = store.find_repo(repo)
    work.add(rid, "export works", step="a1")
    _walked(rid)
    commit(repo, "docs/notes.md", "# notes\n")
    assert work.mark_done(rid, "a1")[0], "a prose-only change keeps the walk"
    work.add(rid, "import works", step="b1")
    _walked(rid, step="b1")
    commit(repo, "src/app.py", "x = 2\n")
    ok, message = work.mark_done(rid, "b1")
    assert not ok and "no passing walk receipt" in message


def test_p3d_two_lines_of_work_do_not_share_a_receipt(repo):
    rid = store.find_repo(repo)
    assert claims.add(rid, "work", ["#1"])[0]
    _walked(rid)
    claims.release(rid)
    assert claims.add(rid, "work", ["#2"])[0]
    work.add(rid, "the second line's a1", step="a1")
    ok, message = work.mark_done(rid, "a1")
    assert not ok and "no passing walk receipt" in message


# --- p3i: a session started in the main folder, working in a worktree --------------------


def test_p3i_a_worktree_intent_is_shown_and_acked_from_the_main_folder(repo, git, tmp_path):
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "line", str(wt))
    (wt / ".rails").mkdir()
    (wt / ".rails" / "intent.md").write_text("# build the export\n", encoding="utf-8")
    h = intent.current_hash(wt)
    other = store.find_repo(wt)
    stop = dispatch(
        _evt("Stop", repo, transcript_path=_transcript(tmp_path, f"Intent:\n...\n{intent.marker(h)}")),
        [_row("intent_shown", ["Stop"])],
    )
    assert not stop.blocks
    assert intent.get(other).get("shown_at"), "the worktree's intent is stamped shown"
    intent.update(other, shown_at=int(time.time()) - 60)
    out = dispatch(
        _evt("UserPromptSubmit", repo, prompt="looks right"), [_row("prompt_words", ["UserPromptSubmit"])]
    )
    assert intent.acked(other, wt), out.notices
    assert not intent.acked(store.find_repo(repo), repo)


# --- p1c: rails state prints every worktree's line of work ------------------------------


def test_p1c_state_lists_every_worktree_s_line_of_work(repo, git, tmp_path):
    from rails.gates.state import lines_of_work

    wt = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", "-b", "other-line", str(wt))
    rid, other = store.find_repo(repo), store.find_repo(wt)
    assert claims.add(rid, "work", ["#12"])[0]
    assert claims.add(other, "other-line", ["#34"])[0]
    store.write_json(other.leaf_dir / "pr.json", {"number": 56, "state": "OPEN", "armed": True})
    rows = lines_of_work(rid)
    assert len(rows) == 2, rows
    assert any("work" in r and "#12" in r and "no claim" not in r for r in rows), rows
    assert any("other-line" in r and "#34" in r and "PR #56 OPEN armed" in r for r in rows), rows



# --- apex review round 1 ---------------------------------------------------------------


def test_p2_ship_does_not_rearm_a_pr_its_push_disarmed(repo, git, commit, monkeypatch):
    """`ship_review` only logs this week; a ship after the disarm must not undo it."""
    import io

    from rails import githooks
    from rails.dispatch import GateRow

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    sha = commit(repo, "src/app.py", "x = 1\n")
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    rows = {"ship_review": GateRow(name="ship_review", module="cli", events=["rails:ship"], mode="shadow")}
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 7, "state": "OPEN", "branch": "work", "disarmed_by": sha})
    out = io.StringIO()
    ship.ship(repo, title="t", body="b", base="main", closes=[], out=out)
    assert calls["merge"] == [], out.getvalue()
    pr = store.read_json(rid.leaf_dir / "pr.json")
    assert pr["armed"] is False and pr["disarmed_by"] == sha


def test_p3c_a_walk_over_a_dirty_tree_is_refused(repo, monkeypatch, capsys):
    from rails import cli

    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    monkeypatch.chdir(repo)
    assert cli.cmd_walk([]) == 2
    assert "commit first" in capsys.readouterr().out


def test_p3d_a_claim_that_grows_keeps_its_line(repo, monkeypatch):
    rid = store.find_repo(repo)
    assert claims.add(rid, "work", ["#1"])[0]
    line = work.line_of_work(rid)
    stamps = iter(["2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", "2026-01-03T00:00:00Z"])

    class _Later:
        @staticmethod
        def now(tz=None):
            class _At:
                def strftime(self, fmt):
                    return next(stamps)

            return _At()

    monkeypatch.setattr(claims, "datetime", _Later)
    assert claims.add(rid, "work", ["#2"])[0]
    assert claims.add(rid, "work", ["#3"])[0]
    assert work.line_of_work(rid) == line, "adding issues to the same line keeps its walks"
    claims.release(rid)
    assert claims.add(rid, "work", ["#1"])[0]
    assert work.line_of_work(rid) != line, "a release and a new claim is a new line"


def test_p3i_a_binding_acks_only_the_intent_that_session_showed(repo, git, tmp_path):
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "line2", str(wt))
    (wt / ".rails").mkdir()
    (wt / ".rails" / "intent.md").write_text("# first\n", encoding="utf-8")
    h1 = intent.current_hash(wt)
    dispatch(_evt("Stop", repo, transcript_path=_transcript(tmp_path, intent.marker(h1))), [_row("intent_shown", ["Stop"])])
    (wt / ".rails" / "intent.md").write_text("# a later intent another session shows\n", encoding="utf-8")
    other = store.find_repo(wt)
    intent.update(other, hash=intent.current_hash(wt), shown_at=int(time.time()) - 60)
    dispatch(_evt("UserPromptSubmit", repo, prompt="looks right"), [_row("prompt_words", ["UserPromptSubmit"])])
    assert not intent.acked(other, wt), "this session showed h1, not the later intent"


def test_p3_receipt_fields_cannot_overwrite_its_marker(repo, monkeypatch):
    rid = store.find_repo(repo)
    monkeypatch.setenv("CLAUDECODE", "1")
    row = receipts.write(rid, "review", via_agent=False, ts=0)
    assert row["via_agent"] is True and row["ts"] > 0



# --- apex review round 2 ---------------------------------------------------------------


def test_p2_a_shadow_ship_of_an_uncovered_tree_does_not_arm(repo, git, commit, monkeypatch):
    """The disarm acts this week; a ship that armed would be undone by its own post()."""
    import io

    from rails import githooks
    from rails.dispatch import GateRow

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    sha = commit(repo, "src/app.py", "x = 1\n")
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    rows = {"ship_review": GateRow(name="ship_review", module="cli", events=["rails:ship"], mode="shadow")}
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    out = io.StringIO()
    ship.ship(repo, title="t", body="b", base="main", closes=[], out=out)
    assert calls["merge"] == [], out.getvalue()
    assert "not arming" in out.getvalue()
    assert store.read_json(rid.leaf_dir / "pr.json")["armed"] is False


def test_p2_another_pr_does_not_inherit_a_disarm(repo, git, commit, monkeypatch):
    import io

    from rails import githooks
    from rails.dispatch import GateRow

    rid, _, _ = _ship_fixture(repo, git, commit, monkeypatch)
    sha = commit(repo, "src/app.py", "x = 1\n")
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    rows = {"ship_review": GateRow(name="ship_review", module="cli", events=["rails:ship"], mode="shadow")}
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 3, "state": "MERGED", "branch": "work", "disarmed_by": "x"})
    ship.ship(repo, title="t", body="b", base="main", closes=[], out=io.StringIO())
    pr = store.read_json(rid.leaf_dir / "pr.json")
    assert pr["number"] != 3 and pr["disarmed_by"] is None, pr


def test_p2_a_pr_that_left_open_forgets_its_disarm(repo, monkeypatch):
    from rails import cli, gitutil

    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 7, "state": "OPEN", "armed": False, "disarmed_by": "x"})
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "MERGED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "MERGED"
    assert "disarmed_by" not in store.read_json(rid.leaf_dir / "pr.json")


def test_p1c_state_survives_a_deleted_worktree(repo, git, tmp_path):
    import shutil

    gone = tmp_path / "gone"
    git(repo, "worktree", "add", "-q", "-b", "gone", str(gone))
    shutil.rmtree(gone)
    lines = state_gate.lines_of_work(store.find_repo(repo))
    assert any("(folder gone)" in line for line in lines), lines


def test_p3i_a_main_folder_with_its_own_intent_still_acks_the_worktree_s(repo, git, tmp_path):
    (repo / ".rails").mkdir()
    (repo / ".rails" / "intent.md").write_text("# the main folder's old intent\n", encoding="utf-8")
    main = store.find_repo(repo)
    hm = intent.current_hash(repo)
    intent.update(main, hash=hm, shown_at=1, acked_hash=hm)
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "line3", str(wt))
    (wt / ".rails").mkdir()
    (wt / ".rails" / "intent.md").write_text("# the worktree's intent\n", encoding="utf-8")
    hw = intent.current_hash(wt)
    dispatch(_evt("Stop", repo, transcript_path=_transcript(tmp_path, intent.marker(hw))), [_row("intent_shown", ["Stop"])])
    other = store.find_repo(wt)
    assert intent.get(other).get("shown_at"), "the worktree's intent was shown"
    intent.update(other, shown_at=int(time.time()) - 60)
    dispatch(_evt("UserPromptSubmit", repo, prompt="looks right"), [_row("prompt_words", ["UserPromptSubmit"])])
    assert intent.acked(other, wt)



# --- apex review round 3 ---------------------------------------------------------------


def test_p2_a_ship_that_declines_holds_the_pr(repo, git, commit, monkeypatch):
    import io

    from rails import githooks
    from rails.dispatch import GateRow

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    sha = commit(repo, "src/app.py", "x = 1\n")
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    rows = {"ship_review": GateRow(name="ship_review", module="cli", events=["rails:ship"], mode="shadow")}
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    out = io.StringIO()
    ship.ship(repo, title="t", body="b", base="main", closes=[], out=out)
    assert calls["merge"] == [] and githooks.pr_holds(rid)["7"]["sha"] == sha
    assert "NOT armed: no review covers this tree" in out.getvalue()


def test_p2_ship_judges_the_review_against_the_remote_base(repo, git, commit, monkeypatch):
    """A local `main` behind origin/main must not count other PRs' code as this one's."""
    import io

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    sha = commit(repo, "docs/notes.md", "# notes\n")
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    out = io.StringIO()
    ship.ship(repo, title="t", body="b", base="main", closes=[], out=out)
    assert calls["merge"], out.getvalue()


def test_p3d_a_claim_made_by_jarvis_s_claim_py_keeps_its_line(repo):
    """jarvis's claim.py writes {branch, items, at} only, and moves `at` on every add."""
    rid = store.find_repo(repo)
    claims._write(rid.main, {rid.leaf: {"branch": "work", "items": ["#1"], "at": "2026-01-01T00:00:00Z"}})
    line = work.line_of_work(rid)
    claims._write(rid.main, {rid.leaf: {"branch": "work", "items": ["#1", "#2"], "at": "2026-01-02T00:00:00Z"}})
    assert work.line_of_work(rid) == line


def test_p1c_state_treats_a_half_removed_worktree_as_gone(repo, git, tmp_path):
    half = tmp_path / "half"
    git(repo, "worktree", "add", "-q", "-b", "half", str(half))
    (half / ".git").unlink()
    lines = state_gate.lines_of_work(store.find_repo(repo))
    assert any("(folder gone)" in line and "half" in line for line in lines), lines


def test_p2_a_pr_that_left_open_releases_its_hold(repo, monkeypatch):
    from rails import cli, githooks, gitutil

    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 7, "state": "OPEN", "armed": False})
    githooks.hold_pr(rid, 7, "x", "test")
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "MERGED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "MERGED"
    assert "7" not in githooks.pr_holds(rid)
