"""The session loop: claims, work items, intent read-back, the operator's words, state, turn end,
the store guard and the leak check at dispatch. Each `*_planted` test is the planted defect its
hooks/gates.toml row names."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

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


def test_turn_end_planted(repo, tmp_path, monkeypatch):
    """An armed PR with an unproven closing step blocks; the fourth try records `unverified`."""
    _lookup(tmp_path, monkeypatch, None)  # GitHub gives no answer: the PR may still be open
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


def test_turn_end_shadow_has_no_side_effects(repo, tmp_path, monkeypatch):
    _lookup(tmp_path, monkeypatch, None)
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


def _lookup(tmp_path, monkeypatch, rows, branch="work"):
    """What GitHub answers for `branch`, through `merged_pr_push`'s lookup fixture. `None` is no
    answer at all (no `gh`, a timeout, an error)."""
    path = tmp_path / "lookup.json"
    if rows is not None:
        path.write_text(json.dumps({branch: rows}), encoding="utf-8")
    monkeypatch.setenv("RAILS_PR_LOOKUP_FIXTURE", str(path))


def _armed(rid, **fields):
    record = {"number": 5, "branch": "work", "state": "OPEN", "armed": True, "monitor": "unbound"}
    store.write_json(rid.leaf_dir / "pr.json", {**record, **fields})


def _items(rid, *items):
    """Work items as (id, step, closes)."""
    with store.updating(work.path(rid), {}) as data:
        data["items"] = [
            {"id": ident, "text": ident, "step": step, "status": "open", "closes": closes}
            for ident, step, closes in items
        ]


@pytest.mark.parametrize(
    "fields",
    [{}, {"branch": None}, {"armed_pr": 5}],
    ids=["recorded branch", "current branch", "armed by hand as this number"],
)
def test_turn_end_does_not_hold_a_turn_for_a_pr_that_merged(repo, tmp_path, monkeypatch, fields):
    """Observed 2026-10-20: a PR merged at 16:00 UTC and the Stop hook still blocked "armed with no
    monitor bound", because nothing re-read pr.json's `armed` after the merge. A record with no
    branch is looked up by the worktree's current branch."""
    rid = store.find_repo(repo)
    _armed(rid, **fields)
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    assert not dispatch(evt, [_row("turn_end", ["Stop"])]).blocks
    record = store.read_json(rid.leaf_dir / "pr.json")
    assert (record["state"], record["armed"]) == ("MERGED", False)


@pytest.mark.parametrize(
    ("record", "branch", "rows"),
    [
        ({}, "work", [{"number": 5, "state": "OPEN"}]),
        ({}, "work", None),
        ({}, "work", [{"number": 4, "state": "MERGED"}]),
        ({}, "work", [{"number": 5, "state": "MERGED"}, {"number": 6, "state": "OPEN"}]),
        ({"state": "MERGED"}, "work", [{"number": 5, "state": "MERGED"}]),
        ({"branch": "old"}, "old", [{"number": 5, "state": "MERGED"}]),
        ({"armed_pr": 6}, "work", [{"number": 5, "state": "MERGED"}]),
        ({"armed_pr": None}, "work", [{"number": 5, "state": "MERGED"}]),
    ],
    ids=[
        "open",
        "no answer",
        "another PR merged",
        "a newer PR is open on the branch",
        "re-armed after it was settled",
        "the record names another branch",
        "armed by hand as another number",
        "armed by hand naming no number",
    ],
)
def test_turn_end_still_holds_an_armed_pr_it_cannot_settle(
    repo, tmp_path, monkeypatch, record, branch, rows
):
    """Blocks as on 1.6.0. The last four are a PR armed by hand after a re-cut: `arm_review` stamps
    `armed` onto the older record, so that record's merge says nothing about the armed PR unless
    the arm named the record's own number (review of 1.6.2)."""
    rid = store.find_repo(repo)
    _armed(rid, **record)
    before = store.read_json(rid.leaf_dir / "pr.json")
    _lookup(tmp_path, monkeypatch, rows, branch)
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    out = dispatch(evt, [_row("turn_end", ["Stop"])])
    assert out.blocks and "armed with no monitor bound" in out.blocks[0]
    assert store.read_json(rid.leaf_dir / "pr.json") == before


def test_turn_end_runs_no_lookup_when_it_would_not_block(repo, tmp_path, monkeypatch):
    rid = store.find_repo(repo)
    _armed(rid, monitor="bound")
    before = store.read_json(rid.leaf_dir / "pr.json")
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    assert not dispatch(evt, [_row("turn_end", ["Stop"])]).blocks
    assert store.read_json(rid.leaf_dir / "pr.json") == before


def test_a_merged_pr_records_its_unproven_steps_as_debt_at_once(repo, tmp_path, monkeypatch):
    """The steps can no longer be proven before the merge: blocking three times first changes
    nothing. Only the items for the issues that PR closes, with a step and no walk receipt, become
    debt; a closing item with no step, and items for another issue, stay open. A PR closed unmerged
    closed no item, so nothing becomes debt."""
    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"), ("a2", "", "#9"), ("b1", "b1", "#10"))
    rows = [_row("turn_end", ["Stop"])]
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    _armed(rid, monitor="bound", closes=["9"])
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "CLOSED"}])
    assert not dispatch(evt, rows).blocks
    record = store.read_json(rid.leaf_dir / "pr.json")
    assert (record["state"], record["armed"]) == ("CLOSED", False)
    assert {i["id"]: i["status"] for i in work.load(rid)["items"]} == {
        "a1": "open", "a2": "open", "b1": "open",
    }
    _armed(rid, monitor="bound", closes=["9"])
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    assert not dispatch(evt, rows).blocks
    assert {i["id"]: i["status"] for i in work.load(rid)["items"]} == {
        "a1": "unverified", "a2": "open", "b1": "open",
    }


def test_a_settled_pr_lets_an_offer_shaped_ending_through_once_its_items_are_debt(
    repo, tmp_path, monkeypatch
):
    """The wording check reads the items as the settle left them, not as loaded before it."""
    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"))
    _armed(rid, monitor="bound", closes=["9"])
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    offer = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "Merged. Want me to start B?"))
    assert not dispatch(offer, [_row("turn_end", ["Stop"])]).blocks


@pytest.mark.parametrize(
    "newer",
    [
        {"number": 6, "branch": "work", "state": "OPEN", "armed": True, "monitor": "unbound"},
        {"number": 5, "branch": "work", "state": "OPEN", "armed": True, "monitor": "unbound", "armed_pr": 6},
        {"number": 5, "branch": "work", "state": "OPEN", "armed": True, "monitor": "unbound", "armed_pr": None},
    ],
    ids=[
        "rails ship recorded another PR",
        "an arm by hand named another PR",
        "an arm by hand named no PR",
    ],
)
def test_a_record_rewritten_during_the_lookup_is_not_overwritten(repo, tmp_path, monkeypatch, newer):
    """A record that changed while `gh` answered about the old PR is kept, and the turn blocks
    over the PR it now names (review of 1.6.2)."""
    from rails.gates import merged_pr_push

    rid = store.find_repo(repo)
    _armed(rid)

    def answer(branch, cwd=None):
        store.write_json(rid.leaf_dir / "pr.json", newer)
        return [{"number": 5, "state": "MERGED"}]

    monkeypatch.setattr(merged_pr_push, "pull_requests", answer)
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    assert dispatch(evt, [_row("turn_end", ["Stop"])]).blocks
    assert store.read_json(rid.leaf_dir / "pr.json") == newer


def test_turn_end_shadow_writes_nothing_for_a_merged_pr(repo, tmp_path, monkeypatch):
    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"))
    _armed(rid, closes=["9"])
    before = store.read_json(rid.leaf_dir / "pr.json")
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    assert not dispatch(evt, [_row("turn_end", ["Stop"], shadow=True)]).blocks
    assert store.read_json(rid.leaf_dir / "pr.json") == before
    assert work.load(rid)["items"][0]["status"] == "open"
    assert "would-block" not in [f["verdict"] for f in store.read_jsonl(rid.dir / "firings.jsonl")]


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
    # the default heredoc forms: a body inside a quoted substitution, and one fed on stdin
    for command in (
        "git commit -m \"$(cat <<'EOF'\nfix: 1234.56 rounding\nEOF\n)\"",
        "gh pr create --title x --body \"$(cat <<'EOF'\ntotal 1234.56\nEOF\n)\"",
        "gh pr create --title x --body-file - <<'EOF'\ntotal 1234.56\nEOF",
    ):
        heredoc = _evt("PreToolUse", repo, tool_name="Bash", tool_input={"command": command})
        assert dispatch(heredoc, rows).denies, command
    # a here-string on stdin, a commit message file, and PowerShell's variable and pipe forms
    (repo / "msg.txt").write_text("fix: 1234.56 rounding\n", encoding="utf-8")
    for shell, command in (
        ("Bash", 'gh pr create --title x --body-file - <<< "total 1234.56"'),
        ("Bash", "git commit -F msg.txt"),
        ("PowerShell", "$body = @'\ntotal 1234.56\n'@\ngh pr create --title x --body $body"),
        ("PowerShell", "@'\ntotal 1234.56\n'@ | gh pr create --title x --body-file -"),
        ("Bash", 'git -c user.name=x commit -m "fix: 1234.56 rounding"'),
        ("Bash", 'gh pr create --title x --body "$(cat msg.txt)"'),
        ("Bash", 'git commit -am "fix: 1234.56 rounding"'),
        ("Bash", 'git commit -m"fix: 1234.56 rounding"'),
        ("Bash", 'm="fix: 1234.56 rounding"; git commit -m "$m"'),
        ("Bash", 'git -c user.name="A B" commit -m "fix: 1234.56 rounding"'),
        ("Bash", 'gh pr create --title x --body "$(< msg.txt)"'),
        ("PowerShell", "gh pr create --title x --body (Get-Content msg.txt -Raw)"),
        ("Bash", "bash <<'EOF'\ngh pr create --title x --body 'total 1234.56'\nEOF"),
        ("Bash", "cat > ship.sh <<'EOF'\ngh pr create --title x --body 'total 1234.56'\nEOF\nbash ship.sh"),
        ("Bash", "git commit -m wip && gh api repos/o/r/issues/5/comments -F body=@msg.txt"),
        ("Bash", "git --work-tree . commit -m \"fix: 1234.56 rounding\""),
        ("Bash", "gh pr create --title x --body-file not-written-yet.md"),
    ):
        sent = _evt("PreToolUse", repo, tool_name=shell, tool_input={"command": command})
        assert dispatch(sent, rows).denies, command
    # a gh command written INTO a script is not one the shell runs
    script = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": "cat > ship.sh <<'EOF'\ngh pr create --fill --body 'total 1234.56'\nEOF"},
    )
    assert not dispatch(script, rows).denies
    ps_script = _evt(
        "PreToolUse",
        repo,
        tool_name="PowerShell",
        tool_input={"command": "@'\ngh pr create --fill --body 'total 1234.56'\n'@ | Out-File ship.ps1"},
    )
    assert not dispatch(ps_script, rows).denies
    # a file the command writes itself is read as its heredoc body, not refused as unreadable
    written = _evt(
        "PreToolUse",
        repo,
        tool_name="Bash",
        tool_input={"command": "cat > body.md <<'EOF'\nno values here\nEOF\ngh pr create --title x --body-file body.md"},
    )
    assert not dispatch(written, rows).denies
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
    # `ship_review` left shadow on 2026-10-15 (hooks/gates.toml): a code diff arms only behind a clean review.
    _clean_review(repo)
    return rid, sha, calls


def _clean_review(repo):
    """A review receipt with no open items for HEAD's tree, so arming is down to ship alone."""
    from rails import review

    clean = '{"reviewed_sha": "abc", "must_fix": [], "consider": []}\n' + "y" * 220
    coop, adversary = repo.parent / "coop.md", repo.parent / "adversary.md"
    coop.write_text("Steelman.\n" + clean, encoding="utf-8")
    adversary.write_text(clean, encoding="utf-8")
    code, text = review.record(repo, coop, adversary)
    assert code == 0, text


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


def test_ship_refuses_a_deferred_finding_with_no_issue(repo, git, commit, monkeypatch):
    """morphyxAI/jarvis#2663: a finding a PR leaves open is an issue, never only a bullet
    (operator ruling, 2026-09-11). A bullet under "Findings left for later" with no `#N`
    is refused by name before anything is pushed; with `#N`, or `no-issue: <reason>`
    for an answer rather than a finding, the same body ships."""
    import io

    from rails import githooks

    rid, _, calls = _ship_fixture(repo, git, commit, monkeypatch)
    monkeypatch.setattr(githooks, "_shadowed", lambda name: False)
    body = (
        "## What this does\n\n- Exports the summary as CSV.\n\n"
        "## Findings left for later\n\n"
        "**Accepted at ship:**\n"
        "- **Stage flags.** A deferred selection reports `frontend` as a narrow one does.\n"
        "- **The rename tests.** Command-line git config outranks them (#41).\n\n"
        "## Test plan\n\n- the CSV round-trips\n"
    )
    out = io.StringIO()
    assert ship.ship(repo, title="t", body=body, base="main", closes=[], arm=False, out=out) == 1
    assert "Stage flags" in out.getvalue() and "rename tests" not in out.getvalue(), out.getvalue()
    assert "round-trips" not in out.getvalue() and "Exports" not in out.getvalue()
    assert calls["api"] == [] and git(repo.parent / "origin.git", "for-each-ref") == ""  # nothing pushed
    for fixed in ("(#42)", "no-issue: nothing reads the flags under a deferral"):
        good = body.replace("as a narrow one does.", f"as a narrow one does {fixed}.")
        out = io.StringIO()
        assert ship.ship(repo, title="t", body=good, base="main", closes=[], arm=False, out=out) == 0, out.getvalue()
    monkeypatch.setattr(githooks, "_shadowed", lambda name: True)
    out = io.StringIO()
    assert ship.ship(repo, title="t", body=body, base="main", closes=[], arm=False, out=out) == 0
    assert "rails shadow: ship_findings would refuse" in out.getvalue()


def test_sections_that_hold_no_deferred_findings_do_not_flag():
    """Questions put to the reviewer, and a section saying what this PR follows up, hold no
    finding left open (review of 1.5.2). A follow-ups section does."""
    body = (
        "## Open questions\n\n- Should the export include archived rows?\n\n"
        "## Follow-up to #2600\n\n- Moves the CSV writer into the toolbox.\n\n"
        "### Follow-up on the review\n\n- Renamed the flag.\n\n"
        "## Follow-ups\n\n- The XLSX writer still buffers the whole file.\n"
    )
    assert ship.unlinked_findings(body) == ["- The XLSX writer still buffers the whole file."]


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
    # Another PR's code reached origin/main after the review here (which covers only the
    # fixture's tree); local `main` never fetched it. Against local `main` the diff holds that
    # code and no receipt covers it; against origin/main it is prose only.
    commit(repo, "src/other.py", "y = 2\n")
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



def test_p2_a_ship_whose_statuses_were_held_back_says_so(repo, git, commit, monkeypatch):
    import io

    import rails.check as check_mod

    _ship_fixture(repo, git, commit, monkeypatch)
    monkeypatch.setattr(check_mod, "post", lambda top, out=None: 1)
    out = io.StringIO()
    code = ship.ship(repo, title="t", body="b", base="main", closes=[], arm=False, out=out)
    assert code == 1 and "statuses NOT posted" in out.getvalue(), out.getvalue()


# --- review round 5 (2026-10-20): leak_dispatch ---------------------------------------------


def _leak(repo, shell, command):
    rows = [_row("leak_dispatch", ["PreToolUse"], ["Bash", "PowerShell", "Agent"])]
    out = dispatch(_evt("PreToolUse", repo, tool_name=shell, tool_input={"command": command}), rows)
    # a gate that raises lets the call through: a "refuses nothing" test must not pass on a crash
    assert not any("crashed" in n for n in out.notices), out.notices
    return out.denies


#: Words a misparse would read as files: each planted holding a value, so a misread one refuses.
_MISREAD = ("notes.txt", "none", "ok", "SilentlyContinue", "x", "gh", "20", "utf8", "testcase", "echo", "log.txt;")


def _plant_misreads(repo):
    for name in _MISREAD:
        (repo / name).write_text("total 1234.56\n", encoding="utf-8")


def test_r5_leak_dispatch_reads_a_body_sent_from_inside_a_powershell_block(repo):
    _leaky_repo(repo)
    (repo / "msg.txt").write_text("total 1234.56\n", encoding="utf-8")
    for command in (
        'git add -A; if ($?) { git commit -m "fix: 1234.56 rounding" }',
        "if ($?) { gh pr create --title x --body-file msg.txt }",
        'if ($LASTEXITCODE -eq 0) { git add -A; git commit -m "fix: 1234.56 rounding" }',
    ):
        assert _leak(repo, "PowerShell", command), command


def test_r5_a_file_flag_outside_the_sending_statement_is_not_a_body(repo):
    _leaky_repo(repo)
    for command in (
        'rg -F "git commit" docs/',
        'grep -F -r "gh pr create" .',
        "grep -F needle README.md && git commit -m wip",
    ):
        assert not _leak(repo, "Bash", command), command


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", "uv run python report.py > body.md && gh pr comment 5 --body-file body.md", id="bash-program"),
        pytest.param("PowerShell", "python report.py | Out-File body.md; gh pr comment 5 --body-file body.md", id="ps-program"),
        pytest.param("Bash", "python gen.py | tee body.md && gh pr comment 5 --body-file body.md", id="bash-tee"),
    ],
)
def test_r5_a_body_a_program_writes_in_the_command_is_refused_unread(repo, shell, command):
    _leaky_repo(repo)
    assert _leak(repo, shell, command), command


def test_r5_a_body_written_from_the_command_s_own_text_is_read(repo):
    _leaky_repo(repo)
    clean = (
        ("Bash", "cat > body.md <<'EOF'\nhello\nEOF\ngh pr comment 5 --body-file body.md"),
        ("Bash", 'echo "hello" > body.md && gh pr comment 5 --body-file body.md'),
        ("PowerShell", "@'\nhello\n'@ | Out-File body.md; gh pr comment 5 --body-file body.md"),
        ("PowerShell", "Set-Content body.md -Value 'hello'; gh pr comment 5 --body-file body.md"),
    )
    for shell, command in clean:
        assert not _leak(repo, shell, command), command
    leaky = (
        ("Bash", "cat > body.md <<'EOF'\ntotal 1234.56\nEOF\ngh pr comment 5 --body-file body.md"),
        ("Bash", 'echo "total 1234.56" > body.md && gh pr comment 5 --body-file body.md'),
        ("PowerShell", "@'\ntotal 1234.56\n'@ | Out-File body.md; gh pr comment 5 --body-file body.md"),
        ("PowerShell", "Set-Content body.md -Value 'total 1234.56'; gh pr comment 5 --body-file body.md"),
    )
    for shell, command in leaky:
        assert _leak(repo, shell, command), command


# --- review round 6 (2026-10-20): leak_dispatch ---------------------------------------------


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param(
            "Bash",
            'echo "## Report" > body.md && uv run python report.py >> body.md && gh pr comment 5 --body-file body.md',
            id="literal-header-then-a-program-appends",
        ),
        pytest.param(
            "PowerShell",
            "'## Report' | Out-File body.md; python report.py | Out-File body.md -Append; gh pr comment 5 --body-file body.md",
            id="ps-literal-header-then-a-program-appends",
        ),
        pytest.param("Bash", "echo x | python render.py > body.md && gh pr comment 5 --body-file body.md", id="a-program-in-the-pipe"),
        pytest.param(
            "Bash", '"/c/Python312/python.exe" report.py > body.md && gh pr comment 5 --body-file body.md', id="a-quoted-program"
        ),
        pytest.param("PowerShell", "echo (python report.py) > body.md; gh pr comment 5 --body-file body.md", id="ps-a-group-runs"),
    ],
)
def test_r6_any_program_writing_the_body_refuses_it_unread(repo, shell, command):
    _leaky_repo(repo)
    assert _leak(repo, shell, command), command


def test_r6_a_body_file_on_disk_is_not_what_the_command_sends_when_the_command_rewrites_it(repo):
    _leaky_repo(repo)
    (repo / "body.md").write_text("hello\n", encoding="utf-8")
    assert _leak(repo, "Bash", "python report.py > body.md && gh pr comment 5 --body-file body.md")
    assert _leak(repo, "Bash", 'echo "total 1234.56" > body.md && gh pr comment 5 --body-file body.md')
    assert not _leak(repo, "Bash", 'echo "hello again" > body.md && gh pr comment 5 --body-file body.md')


def test_r6_a_literal_written_inside_a_powershell_block_is_read(repo):
    _leaky_repo(repo)
    assert not _leak(repo, "PowerShell", "if ($?) { 'hello' | Out-File body.md }; gh pr comment 5 --body-file body.md")
    assert _leak(repo, "PowerShell", "if ($?) { 'total 1234.56' | Out-File body.md }; gh pr comment 5 --body-file body.md")


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'url=$(gh pr create --title x --body "total 1234.56")', id="bash-substitution"),
        pytest.param("Bash", 'url=`gh pr create --title x --body "total 1234.56"`', id="bash-backticks"),
        pytest.param("PowerShell", '$url = (gh pr create --title x --body "total 1234.56")', id="ps-group"),
        pytest.param("PowerShell", '$url = $(gh pr create --title x --body "total 1234.56")', id="ps-subexpression"),
    ],
)
def test_r6_a_gh_call_inside_a_substitution_is_read(repo, shell, command):
    _leaky_repo(repo)
    assert _leak(repo, shell, command), command


# --- review round 7 (2026-10-20): leak_dispatch body files ----------------------------------


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'echo "Closes #457" >> body.md && gh pr create --title x --body-file body.md', id="bash-append"),
        pytest.param("PowerShell", "Add-Content body.md 'Closes #457'; gh pr create --title x --body-file body.md", id="add-content"),
        pytest.param(
            "PowerShell", "'Closes #457' | Out-File body.md -Append; gh pr create --title x --body-file body.md", id="out-file-append"
        ),
        pytest.param("Bash", "echo 'Closes #457' | tee -a body.md && gh pr create --title x --body-file body.md", id="tee-a"),
        pytest.param("Bash", "echo 'Refs #5' >> body.md && git commit -F body.md", id="commit-file-append"),
    ],
)
def test_r7_an_append_keeps_the_copy_on_disk_and_it_is_read(repo, shell, command):
    _leaky_repo(repo)
    (repo / "body.md").write_text("total 1234.56\n", encoding="utf-8")
    assert _leak(repo, shell, command), command


def test_r7_an_append_to_a_missing_file_reads_only_what_it_appends(repo):
    _leaky_repo(repo)
    assert not _leak(repo, "Bash", 'echo "Closes #5" >> new.md && gh pr create --title x --body-file new.md')
    assert _leak(repo, "Bash", 'echo "total 1234.56" >> new.md && gh pr create --title x --body-file new.md')


def test_r7_a_writer_named_in_quoted_text_writes_nothing(repo):
    _leaky_repo(repo)
    (repo / "body.md").write_text("hello\n", encoding="utf-8")
    (repo / "issue.md").write_text("hello\n", encoding="utf-8")
    assert not _leak(repo, "Bash", 'gh pr create --title "ci: tee the suite log" --body-file body.md')
    assert not _leak(repo, "Bash", 'gh issue create --title "Out-File writes UTF-16 on PS 5.1" --body-file issue.md')
    assert not _leak(repo, "Bash", "gh pr create --title 'note: > body.md is a redirect' --body-file body.md")


def test_r7_only_a_writer_of_that_exact_file_before_the_send_counts(repo):
    _leaky_repo(repo)
    (repo / "body.md").write_text("total 1234.56\n", encoding="utf-8")
    for shell, command in (
        ("PowerShell", "'draft' | Out-File old-body.md; gh pr comment 5 --body-file body.md"),
        ("PowerShell", "'draft' | Out-File body.md.bak; gh pr comment 5 --body-file body.md"),
        ("Bash", "gh pr comment 5 --body-file body.md; echo hi > body.md"),
    ):
        assert _leak(repo, shell, command), command


def test_r7_a_literal_writer_s_target_path_is_not_an_expansion(repo, tmp_path, monkeypatch):
    _leaky_repo(repo)
    monkeypatch.setenv("TEMP", str(tmp_path))
    command = "'hello' | Out-File $env:TEMP\\body.md; gh pr comment 5 --body-file $env:TEMP\\body.md"
    assert not _leak(repo, "PowerShell", command)


def test_r7_a_literal_writer_after_a_keyword_is_literal(repo):
    _leaky_repo(repo)
    command = 'if true; then echo "hello" > body.md; fi\ngh pr comment 5 --body-file body.md'
    assert not _leak(repo, "Bash", command)


def test_r7_a_writer_named_in_an_earlier_statement_s_text_writes_nothing(repo):
    _leaky_repo(repo)
    (repo / "body.md").write_text("hello\n", encoding="utf-8")
    for command in (
        "git commit -m 'note: > body.md is a redirect' && gh pr comment 5 --body-file body.md",
        "grep -n tee body.md && gh pr comment 5 --body-file body.md",
    ):
        assert not _leak(repo, "Bash", command), command


def test_p3g_a_record_armed_for_another_pr_stays_armed_when_its_own_pr_leaves_open(repo, monkeypatch):
    """`armed_pr` (1.6.2) names the PR an arm by hand armed; the refresh clears `armed` only for
    the record's own, as turn_end._settled does."""
    from rails import cli, githooks, gitutil

    rid = store.find_repo(repo)
    store.write_json(
        rid.leaf_dir / "pr.json", {"number": 5, "state": "OPEN", "armed": True, "armed_pr": 6}
    )
    githooks.hold_pr(rid, 6, "x", "held")
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "MERGED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "MERGED"
    record = store.read_json(rid.leaf_dir / "pr.json")
    assert (record["state"], record["armed"], record["armed_pr"]) == ("MERGED", True, 6)
    assert "6" in githooks.pr_holds(rid)
    store.write_json(
        rid.leaf_dir / "pr.json", {"number": 7, "state": "OPEN", "armed": True, "armed_pr": 7}
    )
    assert cli.refresh_pr_state(repo, now=10**10) == "MERGED"
    assert store.read_json(rid.leaf_dir / "pr.json")["armed"] is False


# --- review round 8 (2026-10-20): the refresh and 1.6.2's turn_end, body files ---------------


def test_r8_a_refresh_after_the_merge_records_the_debt_turn_end_would(repo, tmp_path, monkeypatch):
    """Any rails command after a merge refreshes pr.json before the Stop (`rails walk`, `rails
    work monitor-bound`): the debt turn_end._settle would write is still written, at the Stop
    (review of #52 rounds 8 and 9)."""
    from rails import cli, gitutil

    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"), ("a2", "", "#9"), ("b1", "b1", "#10"))
    _armed(rid, monitor="bound", closes=["9"])
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "MERGED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "MERGED"
    assert store.read_json(rid.leaf_dir / "pr.json")["pending_debt"] is True
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    assert not dispatch(evt, [_row("turn_end", ["Stop"])]).blocks
    assert {i["id"]: i["status"] for i in work.load(rid)["items"]} == {
        "a1": "unverified", "a2": "open", "b1": "open",
    }
    # a PR closed unmerged closed no item: no debt
    _items(rid, ("a1", "a1", "#9"))
    _armed(rid, monitor="bound", closes=["9"])
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "CLOSED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "CLOSED"
    assert work.load(rid)["items"][0]["status"] == "open"


def test_r8_a_refresh_writes_nothing_onto_a_record_rewritten_during_its_lookup(repo, monkeypatch):
    from rails import cli, gitutil

    rid = store.find_repo(repo)
    path = rid.leaf_dir / "pr.json"
    store.write_json(path, {"number": 5, "state": "OPEN", "armed": True})

    def gh_while_shipping_another(*a, **k):
        store.write_json(path, {"number": 9, "state": "OPEN", "armed": True})
        return '{"state": "MERGED"}'

    monkeypatch.setattr(gitutil, "gh", gh_while_shipping_another)
    cli.refresh_pr_state(repo, now=10**10)
    record = store.read_json(path)
    assert (record["number"], record["state"], record["armed"]) == (9, "OPEN", True)


def test_r8_a_variable_that_starts_with_the_path_still_expands(repo):
    _leaky_repo(repo)
    (repo / "notes.txt").write_text("total 1234.56\n", encoding="utf-8")
    ps = '$out = "body.md"; $output = (Get-Content notes.txt -Raw); "Notes:`n$output" | Out-File $out; gh pr comment 5 --body-file $out'
    assert _leak(repo, "PowerShell", ps)
    assert _leak(repo, "Bash", 'echo "$body" > body && gh pr create --title x --body-file body')


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'test -f body.md || echo "draft" > body.md; gh pr create --title x --body-file body.md', id="bash-or"),
        pytest.param(
            "PowerShell",
            "if (-not (Test-Path body.md)) { 'Summary' | Out-File body.md }; gh pr create --title x --body-file body.md",
            id="ps-if",
        ),
    ],
)
def test_r8_a_writer_that_may_not_run_leaves_the_disk_copy_read(repo, shell, command):
    _leaky_repo(repo)
    (repo / "body.md").write_text("total 1234.56\n", encoding="utf-8")
    assert _leak(repo, shell, command), command


@pytest.mark.parametrize(
    "command",
    [
        "ac body.md 'total 1234.56'; gh pr create --title x --body-file body.md",
        "sc body.md 'total 1234.56'; gh pr create --title x --body-file body.md",
        "New-Item -Path body.md -Value 'total 1234.56'; gh pr create --title x --body-file body.md",
    ],
    ids=["ac", "sc", "new-item"],
)
def test_r8_powershell_aliases_and_new_item_are_writers(repo, command):
    _leaky_repo(repo)
    (repo / "body.md").write_text("hello\n", encoding="utf-8")
    assert _leak(repo, "PowerShell", command), command


def test_r8_a_file_read_into_part_of_a_text_flag_is_read(repo):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("total 1234.56\n", encoding="utf-8")
    assert _leak(repo, "Bash", 'gh pr comment 5 --body "Tests: $(tail -20 log.txt)"')
    assert _leak(repo, "PowerShell", 'gh pr comment 5 --body "Tests: $(Get-Content log.txt -Tail 20)"')
    assert not _leak(repo, "Bash", 'git commit -m "release $(date +%F)"')


def test_r8_a_line_count_in_a_read_is_not_a_file(repo):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("all green\n", encoding="utf-8")
    assert not _leak(repo, "Bash", 'gh pr comment 5 --body "Tests: $(tail -n 20 log.txt)"')
    assert not _leak(repo, "PowerShell", 'gh pr comment 5 --body "Tests: $(Get-Content log.txt -Tail 20)"')


# --- review round 9 (2026-10-20) ---------------------------------------------------------------


def test_r9_the_default_heredoc_message_with_no_value_is_sent(repo):
    _leaky_repo(repo)
    for command in (
        "git commit -m \"$(cat <<'EOF'\nfix: tidy the parser\nEOF\n)\"",
        "gh pr create --title x --body \"$(cat <<'EOF'\nclean body\nEOF\n)\"",
    ):
        assert not _leak(repo, "Bash", command), command


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(cat log.txt 2>/dev/null)"', id="redirect"),
        pytest.param("Bash", 'gh pr comment 5 --body "$(cat log.txt | head -5)"', id="pipe"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content log.txt -Raw | Out-String)"', id="ps-pipe"),
        pytest.param("Bash", 'gh pr comment 5 --body "$(tail -n +5 log.txt)"', id="plus-count"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content log.txt -Encoding utf8)"', id="ps-encoding"),
        pytest.param("Bash", "gh pr comment 5 --body \"$(cat 'my notes.txt')\"", id="quoted-path-with-a-space"),
        pytest.param("Bash", 'gh pr comment 5 --body "$(< log.txt)"', id="redirect-read"),
    ],
)
def test_r9_a_reader_in_a_text_flag_reads_its_files_only(repo, shell, command):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("all green\n", encoding="utf-8")
    (repo / "my notes.txt").write_text("all green\n", encoding="utf-8")
    assert not _leak(repo, shell, command), command
    (repo / "log.txt").write_text("total 1234.56\n", encoding="utf-8")
    (repo / "my notes.txt").write_text("total 1234.56\n", encoding="utf-8")
    assert _leak(repo, shell, command), command


def test_r9_a_walk_after_the_merge_and_before_the_stop_leaves_no_debt(repo, tmp_path, monkeypatch):
    """`rails walk` refreshes pr.json before it walks: the merge's debt is judged at the Stop (or
    the next ship), against the walk receipts as they stand then, as turn_end alone does."""
    from rails import cli, gitutil

    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"), ("b1", "b1", "#9"))
    _armed(rid, monitor="bound", closes=["9"])
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "MERGED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "MERGED"
    assert {i["id"]: i["status"] for i in work.load(rid)["items"]} == {"a1": "open", "b1": "open"}
    receipts.write(rid, "walk", instrument="walk:planted", steps=[{"step": "a1", "pass": True}], **work.walk_scope(rid))
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "MERGED"}])
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    assert not dispatch(evt, [_row("turn_end", ["Stop"])]).blocks
    assert {i["id"]: i["status"] for i in work.load(rid)["items"]} == {"a1": "open", "b1": "unverified"}
    assert "pending_debt" not in store.read_json(rid.leaf_dir / "pr.json")


def test_r9_ship_judges_a_pending_merge_debt_before_it_closes_more(repo, git, commit):
    import io

    rid = store.find_repo(repo)
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, git(repo, "rev-parse", "HEAD^{tree}"), ["checks"], quick=False)
    _items(rid, ("a1", "a1", "#9"))
    store.write_json(
        rid.leaf_dir / "pr.json",
        {"number": 5, "state": "MERGED", "armed": False, "closes": ["9"], "pending_debt": True},
    )
    out = io.StringIO()
    assert ship.ship(repo, title="t", body="b", base="main", closes=["10"], out=out) == 1
    assert "unverified: a1" in out.getvalue(), out.getvalue()


def test_r9_a_substitution_that_reads_no_file_names_no_file(repo):
    _leaky_repo(repo)
    assert not _leak(repo, "Bash", 'gh pr comment 5 --body "Built $(git rev-parse --short HEAD)"')


def test_r9_a_shadowed_stop_leaves_a_pending_debt_pending(repo, tmp_path, monkeypatch):
    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"))
    store.write_json(
        rid.leaf_dir / "pr.json",
        {"number": 5, "state": "MERGED", "armed": False, "closes": ["9"], "pending_debt": True},
    )
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    dispatch(evt, [_row("turn_end", ["Stop"], shadow=True)])
    assert work.load(rid)["items"][0]["status"] == "open"
    assert store.read_json(rid.leaf_dir / "pr.json")["pending_debt"] is True


# --- review round 10 (2026-10-20): the files a sending statement's substitutions read ---------


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", "gh pr comment 5 --body \"Here's the log: $(tail -20 log.txt)\"", id="apostrophe"),
        pytest.param("Bash", 'gh pr comment 5 --body "Re #12: $(tail -20 log.txt)"', id="hash"),
        pytest.param("PowerShell", "gh pr comment 5 --body \"Today's run: $(Get-Content log.txt -Tail 20)\"", id="ps-apostrophe"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "Fixes #12: $(Get-Content log.txt -Raw)"', id="ps-hash"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(cat < log.txt)"', id="input-redirect"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(head -5 <log.txt)"', id="glued-input-redirect"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(sort < log.txt)"', id="any-command-s-input"),
        pytest.param("Bash", 'gh pr comment 5 --body "$(cat -n log.txt)"', id="cat-n-is-a-switch"),
        pytest.param("PowerShell", "gh pr create --title x --body (Get-Content -Raw log.txt)", id="ps-group"),
        pytest.param("PowerShell", "gh pr create --title x --body (Get-Content log.txt -Raw -Encoding utf8)", id="ps-group-flags"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$((Get-Content log.txt -Raw).Trim())"', id="ps-nested-group"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: `cat log.txt`"', id="backticks"),
        pytest.param("Bash", 'gh api repos/o/r/issues/5/comments -f body="$(cat log.txt)"', id="a-field-value"),
    ],
)
def test_r10_a_file_a_substitution_reads_is_read_wherever_it_sits(repo, shell, command):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("total 1234.56\n", encoding="utf-8")
    assert _leak(repo, shell, command), command


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'gh pr comment 5 --body "Tests: $(tail -5 log.txt 2>/dev/null || echo none)"', id="or-list"),
        pytest.param("Bash", 'gh pr comment 5 --body "$(cat log.txt; echo)"', id="semicolon"),
        pytest.param("Bash", 'gh pr comment 5 --body "$(cat log.txt && echo ok)"', id="and-list"),
        pytest.param(
            "PowerShell", 'gh pr comment 5 --body "Tests: $(Get-Content log.txt -Raw -ErrorAction SilentlyContinue)"', id="ps-erroraction"
        ),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content log.txt -ea SilentlyContinue -OutVariable x)"', id="ps-common"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content -Encoding utf8 log.txt)"', id="ps-valued-before-the-path"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content -Tail 20 log.txt)"', id="ps-tail-before-the-path"),
        pytest.param("Bash", 'gh pr comment 5 --body "Built with $(type -P gh)"', id="bash-type-is-not-a-reader"),
        pytest.param("Bash", "git commit -m 'docs: show $(cat notes.txt) in the example'", id="single-quoted-literal"),
        pytest.param("Bash", 'git commit -m "docs: show \\$(cat notes.txt) in the example"', id="escaped"),
        pytest.param("PowerShell", "git commit -m 'docs: show $(Get-Content notes.txt) in the example'", id="ps-single-quoted"),
    ],
)
def test_r10_only_a_reader_s_files_are_read(repo, shell, command):
    _leaky_repo(repo)
    _plant_misreads(repo)
    (repo / "log.txt").write_text("all green\n", encoding="utf-8")
    assert not _leak(repo, shell, command), command


def test_r10_a_pr_closed_unmerged_leaves_no_pending_debt(repo, tmp_path, monkeypatch):
    from rails import cli, gitutil

    rid = store.find_repo(repo)
    _items(rid, ("a1", "a1", "#9"))
    _armed(rid, monitor="bound", closes=["9"])
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: '{"state": "CLOSED"}')
    assert cli.refresh_pr_state(repo, now=10**10) == "CLOSED"
    assert "pending_debt" not in store.read_json(rid.leaf_dir / "pr.json")
    _lookup(tmp_path, monkeypatch, [{"number": 5, "state": "CLOSED"}])
    evt = _evt("Stop", repo, transcript_path=_transcript(tmp_path, "done"))
    dispatch(evt, [_row("turn_end", ["Stop"])])
    assert work.load(rid)["items"][0]["status"] == "open"


# --- review round 11 (2026-10-20): input redirects on raw text; a derived name it cannot read ---


@pytest.mark.parametrize(
    "command",
    [
        "gh pr comment 5 --body \"Tests: $(grep -c '<testcase' junit.xml)\"",
        "gh pr comment 5 --body \"$(printf '<details>\\n%s\\n</details>' \"$(tail -20 log.txt)\")\"",
        "gh pr comment 5 --body \"$(echo '<!-- rails -->')\"",
        'gh pr comment 5 --body "$(diff <(git show HEAD:log.txt) log.txt)"',
        'gh pr comment 5 --body "Tests: $(tail -30 log.txt|grep -v DEBUG)"',
        'gh release create v1 --notes "v$(cat VERSION 2>/dev/null || echo dev)"',
        'gh pr comment 5 --body "Lines: $(wc -l < log.txt)"',
        'gh pr comment 5 --body "Notes: $(cat notes/missing.md)"',
    ],
    ids=["quoted-lt", "quoted-details", "quoted-comment", "process-substitution", "glued-pipe",
         "missing-fallback", "a-count-of-its-input", "a-derived-name-it-cannot-read"],
)
def test_r11_shell_syntax_and_missing_files_refuse_nothing(repo, command):
    _leaky_repo(repo)
    _plant_misreads(repo)
    (repo / "log.txt").write_text("total 1234.56\n" if "wc -l" in command else "all green\n", encoding="utf-8")
    assert not _leak(repo, "Bash", command), command


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'gh pr create --title x --body "$(<log.txt)"', id="glued-input"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(< log.txt)"', id="spaced-input"),
        pytest.param("Bash", 'gh api repos/o/r/issues/5/comments -f body="$(< log.txt)"', id="field-input"),
        pytest.param("Bash", 'gh pr comment 5 --body "Tests: $(tail -30 log.txt|grep -v DEBUG)"', id="glued-pipe"),
        pytest.param("Bash", "gh pr create --title x --body-file - < log.txt", id="the-sender-s-own-stdin"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "Tests: $(Get-Content log.txt -Raw -ErrorAction SilentlyContinue)"', id="ps-erroraction"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content log.txt -ea SilentlyContinue -OutVariable x)"', id="ps-common"),
    ],
)
def test_r11_a_file_read_on_stdin_or_after_common_parameters_is_read(repo, shell, command):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("total 1234.56\n", encoding="utf-8")
    denies = _leak(repo, shell, command)
    assert denies and not any("could not read" in d for d in denies), (command, denies)


def test_r11_a_found_value_not_a_missing_file_is_why_the_r10_cases_refuse(repo):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("total 1234.56\n", encoding="utf-8")
    for shell, command in (
        ("Bash", "gh pr comment 5 --body \"Here's the log: $(tail -20 log.txt)\""),
        ("PowerShell", "gh pr create --title x --body (Get-Content -Raw log.txt)"),
        ("Bash", 'gh pr comment 5 --body "Log: `cat log.txt`"'),
    ):
        denies = _leak(repo, shell, command)
        assert denies and not any("could not read" in d for d in denies), (command, denies)


def test_r11_a_process_substitution_is_not_an_input_redirect(repo):
    """`<(...)` runs a command; read as `< (git` it would name a file - here one that exists."""
    _leaky_repo(repo)
    (repo / "(git").write_text("total 1234.56\n", encoding="utf-8")
    assert not _leak(repo, "Bash", 'gh pr comment 5 --body "Diff: $(cat <(git show HEAD:log.txt))"')


# --- review round 12 (2026-10-20) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("shell", "command"),
    [
        pytest.param("Bash", 'gh pr create --title x --body-file - < "log.txt"', id="quoted-stdin"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(cat < "log.txt")"', id="quoted-substitution-input"),
        pytest.param("Bash", 'gh pr comment 5 --body "Log: $(LC_ALL=C sort < log.txt)"', id="env-prefix"),
        pytest.param("Bash", "cat log.txt | gh pr create --title x --body-file -", id="a-reader-piped-into-the-sender"),
        pytest.param("PowerShell", "Get-Content log.txt -Raw | gh pr create --title x --body-file -", id="ps-reader-piped-in"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content -Tail 20 log.txt)"', id="ps-tail-before-the-path"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content -Encoding utf8 log.txt)"', id="ps-encoding-before-the-path"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content -Path log.txt -Raw)"', id="ps-path"),
        pytest.param("PowerShell", 'gh pr comment 5 --body "$(Get-Content -Path:log.txt -Raw)"', id="ps-path-colon"),
    ],
)
def test_r12_a_file_read_in_these_shapes_is_read(repo, shell, command):
    _leaky_repo(repo)
    (repo / "log.txt").write_text("total 1234.56\n", encoding="utf-8")
    denies = _leak(repo, shell, command)
    assert denies and not any("could not read" in d for d in denies), (command, denies)


def test_r12_a_quoted_target_with_a_space_is_read(repo):
    _leaky_repo(repo)
    (repo / "my log.txt").write_text("total 1234.56\n", encoding="utf-8")
    assert _leak(repo, "Bash", 'gh pr create --title x --body-file - < "my log.txt"')


@pytest.mark.parametrize(
    "command",
    [
        'git fetch -q 2>/dev/null; gh pr comment 5 --body "done" < /dev/null',
        'gh api repos/o/r/actions/artifacts 2>/dev/null | while read id; do gh api -X DELETE "repos/o/r/actions/artifacts/$id" < /dev/null; done',
        "gh pr comment 5 --body-file /dev/null",
    ],
    ids=["stdin-after-a-stderr-redirect", "the-prune-loop", "a-null-body-file"],
)
def test_r12_the_null_device_is_neither_written_nor_unreadable(repo, command):
    _leaky_repo(repo)
    assert not _leak(repo, "Bash", command), command


def test_r12_a_file_a_program_writes_and_a_substitution_reads_is_refused_unread(repo):
    _leaky_repo(repo)
    denies = _leak(repo, "Bash", 'uv run python report.py > out.txt && gh pr comment 5 --body "Log: $(tail -20 out.txt)"')
    assert denies and "could not read" in denies[0], denies


def test_r12_the_sender_s_own_stdin_is_a_whole_body(repo):
    _leaky_repo(repo)
    denies = _leak(repo, "Bash", "gh pr create --title x --body-file - < missing-body.md")
    assert denies and "could not read" in denies[0], denies


def test_r12_a_read_is_capped_and_a_nul_name_is_unreadable(repo):
    from rails.gates import leak_dispatch

    (repo / "big.txt").write_text("x" * 3_000_000, encoding="utf-8")
    assert len(leak_dispatch._read("big.txt", repo)) == 2_000_000
    assert leak_dispatch._read("a\x00b.txt", repo) is None
    assert leak_dispatch._read(".", repo) is None  # a folder, not a file


def test_r12_a_redirect_inside_a_substitution_is_not_the_sender_s_stdin(repo):
    _leaky_repo(repo)
    command = "uv run pytest -q > out.txt; gh api repos/o/r/issues/5/comments -f body=done -F lines=$(wc -l < out.txt)"
    assert not _leak(repo, "Bash", command)
