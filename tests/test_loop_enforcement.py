"""rails 1.3.0: the loop enforces itself, one template set, the hook-removal check.

Each test plants the defect the mechanism exists for and asserts it is refused, then the
clean case it must let through.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rails import check as check_mod
from rails import cli, close, githooks, intent, receipts, review, ship, store, structural, work
from rails.dispatch import GateRow
from rails.gates import allow_edit, milestone_close, store_guard, test_filter
from rails.hookio import Event

ZERO = "0" * 40
SETTINGS = (
    '{"hooks": {"UserPromptSubmit": [{"hooks": [{"type": "command", '
    '"command": "python3 \\"$CLAUDE_PROJECT_DIR/.claude/hooks/old_gate.py\\""}]}]}}'
)


# --- hook-removal (rails check) ---------------------------------------------------


@pytest.fixture
def hooked(repo, git, commit, py):
    """A repo whose base settings run .claude/hooks/old_gate.py, with lanes."""
    commit(repo, ".claude/settings.json", SETTINGS, "settings")
    commit(repo, ".claude/hooks/old_gate.py", "print(1)\n", "hook")
    commit(repo, ".claude/rules/old.md", "a rule\n", "rule")
    (repo / "lanes.toml").write_text(
        f'[settings]\nbase = "origin/main"\n[[lane]]\nname = "checks"\nalways = true\n'
        f'command = ["{py}", "-c", "print(1)"]\n',
        encoding="utf-8",
    )
    commit(repo, "lanes.toml", (repo / "lanes.toml").read_text(encoding="utf-8"), "lanes")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def test_deleting_a_hook_script_older_worktrees_run_fails_the_check(hooked, git):
    base = git(hooked, "rev-parse", "origin/main")
    git(hooked, "rm", "-q", ".claude/hooks/old_gate.py")
    git(hooked, "commit", "-q", "-m", "retire the hook")
    found = structural.run(hooked, base)
    assert [f.check for f in found] == ["hook-removal"] and "rails retire-hook" in found[0].message
    out = io.StringIO()
    assert check_mod.check(hooked, out=out) == 1
    assert "hook-removal" in out.getvalue() and "GREEN" not in out.getvalue()


def test_a_placeholder_or_a_retired_rule_passes(hooked, git):
    base = git(hooked, "rev-parse", "origin/main")
    code, text = structural.retire_hook(hooked, ".claude/hooks/old_gate.py")
    assert code == 0 and "placeholder" in text
    git(hooked, "rm", "-q", ".claude/rules/old.md")
    git(hooked, "add", "-A")
    git(hooked, "commit", "-q", "-m", "placeholder; drop a rule")
    assert structural.run(hooked, base) == []
    done = subprocess.run([sys.executable, str(hooked / ".claude/hooks/old_gate.py")], capture_output=True, text=True)
    assert (done.returncode, done.stdout) == (0, "")


# --- one template set ----------------------------------------------------------------


def test_rails_template_lists_and_prints_the_plugin_set(capsys):
    assert cli.main(["template"]) == 0
    listed = capsys.readouterr().out
    for name in ("intent", "spec", "adr", "milestone", "rulebook", "pull_request_template"):
        assert name in listed
    assert cli.main(["template", "spec"]) == 0
    assert "## Seams" in capsys.readouterr().out
    assert cli.main(["template", "prd"]) == 2  # retired: there is no second set


# --- work from acceptance lines ----------------------------------------------------------

ISSUE = """Some context about the defect.

## Done when
- [ ] `step: a1` the export lists every account, including closed ones
- [ ] a row with no date is refused with its line number

## Notes
- this is not an acceptance line
"""


def test_acceptance_lines_come_from_the_done_when_section_and_step_ids():
    lines = work.acceptance_lines(ISSUE)
    assert lines == [
        ("`step: a1` the export lists every account, including closed ones", "a1"),
        ("a row with no date is refused with its line number", ""),
    ]


def test_an_issue_form_done_when_box_is_read_line_by_line():
    form = "### What\n\nExport accounts.\n\n### Done when\n\nthe export lists closed accounts\n" \
           "step: b2 a blank date is refused\n\n### Notes\n\n_No response_\n"
    assert work.acceptance_lines(form) == [
        ("the export lists closed accounts", ""),
        ("step: b2 a blank date is refused", "b2"),
    ]


def test_add_from_issue_is_idempotent_and_closes_the_issue(repo):
    rid = store.find_repo(repo)
    added = work.add_from_issue(rid, "42", ISSUE)
    assert [(i["id"], i["closes"]) for i in added] == [("a1", "#42"), ("42-2", "#42")]
    assert work.add_from_issue(rid, "#42", ISSUE) == []


# --- intent at push -----------------------------------------------------------------


def _rows(monkeypatch, names=("prepush_hold", "prepush_marker", "prepush_retired", "prepush_leak", "prepush_intent")):
    rows = {n: GateRow(name=n, module="prepush", events=["git:pre-push"], mode="enforce") for n in names}
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: False)


def test_an_agent_push_needs_an_acked_intent(repo, commit, monkeypatch):
    """The planted defect for `prepush_intent`."""
    _rows(monkeypatch)
    rid = store.find_repo(repo)
    sha = commit(repo, "a.txt", "plain\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=True)
    from rails import leak

    store.write_json(leak.snapshot_path(rid), leak.build_snapshot(["9999.99"], {}, "t"))
    line = [f"refs/heads/work {sha} refs/heads/work {ZERO}"]
    monkeypatch.setenv("CLAUDECODE", "1")
    code, msgs = githooks.pre_push([], line, rid)
    assert code == 1 and any("no intent" in m for m in msgs)
    (repo / ".rails").mkdir()
    (repo / ".rails" / "intent.md").write_text("# build the export\n", encoding="utf-8")
    code, msgs = githooks.pre_push([], line, rid)
    assert code == 1 and any("not been acked" in m for m in msgs)
    intent.update(rid, acked_hash=intent.current_hash(repo))
    assert githooks.pre_push([], line, rid) == (0, [])
    monkeypatch.delenv("CLAUDECODE")
    (repo / ".rails" / "intent.md").write_text("# something else\n", encoding="utf-8")
    assert githooks.pre_push([], line, rid) == (0, [])  # the operator's own shell is not asked


# --- review before arming --------------------------------------------------------------


REPORT = "Must-fix: the parser drops a row when the date is blank; reproducer: feed it a blank date.\n" + "x" * 220


def test_review_record_refuses_thin_or_copied_reports_and_binds_the_tree(repo, commit, tmp_path, monkeypatch):
    monkeypatch.chdir(repo)
    commit(repo, "src/a.py", "x = 1\n")
    coop, adv = tmp_path / "coop.md", tmp_path / "adv.md"
    coop.write_text("too short", encoding="utf-8")
    adv.write_text(REPORT, encoding="utf-8")
    assert review.record(repo, coop, adv)[0] == 2
    coop.write_text(REPORT, encoding="utf-8")
    assert review.record(repo, coop, adv)[0] == 2  # identical: not two voices
    coop.write_text("Steelman first.\n" + REPORT, encoding="utf-8")
    code, text = review.record(repo, coop, adv)
    assert code == 0 and "must-fix: coop 1, adversary 1" in text
    rid = store.find_repo(repo)
    tree = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], capture_output=True, text=True).stdout.strip()
    assert review.latest_for_tree(rid, tree) is not None
    commit(repo, "src/a.py", "x = 2\n")
    tree2 = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], capture_output=True, text=True).stdout.strip()
    assert review.latest_for_tree(rid, tree2) is None  # a later commit is not reviewed


def test_ship_does_not_arm_a_code_diff_without_a_review(repo, commit, monkeypatch, tmp_path):
    """The planted defect for `ship_review`."""
    monkeypatch.setattr(githooks, "_shadowed", lambda name: False)
    rid = store.find_repo(repo)
    commit(repo, "src/a.py", "x = 1\n")
    out = io.StringIO()
    assert ship.needs_review(repo, "origin/main")
    assert ship._review_allows_arming(rid, repo, out) is False and "review record" in out.getvalue()
    monkeypatch.chdir(repo)
    (tmp_path / "c.md").write_text("Steelman. " + REPORT, encoding="utf-8")
    (tmp_path / "a.md").write_text(REPORT, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    assert ship._review_allows_arming(rid, repo, io.StringIO()) is True


def test_a_prose_only_diff_needs_no_review(repo, commit):
    commit(repo, "docs/notes.md", "words\n")
    assert not ship.needs_review(repo, "origin/main")


# --- close on use ----------------------------------------------------------------------


def test_close_needs_the_operators_used_and_no_open_issues(repo, monkeypatch, git):
    git(repo, "remote", "add", "origin", "https://github.com/acme/app.git")
    calls = []
    milestone = {"state": "open", "open_issues": 1, "title": "App R1"}

    def fake_api(top, path, *, method="GET", payload=None, timeout=60):
        calls.append((method, path, payload))
        return dict(milestone)

    monkeypatch.setattr(close, "gh_api", fake_api)
    code, text = close.close(repo, "7")
    assert code == 1 and "no `used` record" in text and calls == []
    rid = store.find_repo(repo)
    with store.updating(rid.dir / "state.json", {}) as state:
        state.setdefault("used", []).append({"milestone": "#7", "task": "filed a real claim", "at": 1})
    code, text = close.close(repo, "#7")
    assert code == 1 and "1 open issue" in text
    milestone["open_issues"] = 0
    code, text = close.close(repo, "7")
    assert code == 0 and calls[-1] == ("PATCH", "repos/acme/app/milestones/7", {"state": "closed"})


def test_the_operators_words_refuse_inside_an_agent(repo, monkeypatch, capsys):
    monkeypatch.chdir(repo)
    monkeypatch.setenv("CLAUDECODE", "1")
    for word in ("used", "approve", "release"):
        assert cli.cmd_words(word, ["#7", "x"]) == 2
    assert "operator's word" in capsys.readouterr().out
    assert cli.cmd_words("hold", []) == 0  # stopping work is safe for anyone to ask


# --- absence claims --------------------------------------------------------------------


def test_the_absence_advisory_flags_claims_not_prose():
    flagged = ship.unreceipted_absences(
        "Nothing calls the old loader.\nThere are no callers of export_rows.\nThe table does not exist on dev.\n"
        "No code changed in apps/.\nThe only lane selected was checks.\nNever mind the docs.\n"
    )
    assert flagged == [
        "Nothing calls the old loader.",
        "There are no callers of export_rows.",
        "The table does not exist on dev.",
    ]


# --- the new denies ----------------------------------------------------------------------


def _evt(tool, tool_input, **extra):
    payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input, "cwd": "."}
    payload.update(extra)
    return Event(name="PreToolUse", payload=payload)


def test_test_filter_refuses_deselect_and_k_not_but_not_selection():
    assert test_filter.check(_evt("Bash", {"command": "uv run pytest -k 'not slow' tests"}))
    assert test_filter.check(_evt("Bash", {"command": "pytest --deselect tests/a.py::t"}))
    assert test_filter.check(_evt("Bash", {"command": "pytest -k test_export tests"})) is None
    assert test_filter.check(_evt("Bash", {"command": "pytest --deselect tests/a.py::t  # deselect-ok: #12"})) is None


def test_allow_edit_refuses_only_a_subagent():
    write = {"file_path": "C:/r/rails/leak_allow.toml", "content": "x"}
    assert allow_edit.check(_evt("Write", write)) is None
    assert allow_edit.check(_evt("Write", write, agent_id="sub1"))
    assert allow_edit.check(_evt("Write", {"file_path": "C:/r/src/a.py", "content": "x"}, agent_id="sub1")) is None


def test_milestone_close_refuses_the_raw_patch_but_not_a_read():
    assert milestone_close.check(_evt("Bash", {"command": "gh api repos/a/b/milestones/76 -X PATCH -f state=closed"}))
    assert milestone_close.check(_evt("PowerShell", {"command": "gh api repos/a/b/milestones/76 --method PATCH -f 'state=closed'"}))
    assert milestone_close.check(_evt("Bash", {"command": "gh api repos/a/b/milestones/76"})) is None


def test_store_guard_refuses_a_command_naming_the_store(repo):
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text('[guard]\nnames = ["house-db-1", "house_db"]\n', encoding="utf-8")
    cwd = str(repo)
    assert store_guard.check(_evt("Bash", {"command": "docker exec house-db-1 psql -d house_db -c 'select 1'"}, cwd=cwd))
    assert store_guard.check(_evt("Bash", {"command": "docker exec other-db-1 psql -c 'select 1'"}, cwd=cwd)) is None
    assert store_guard.check(_evt("Bash", {"command": "rails snapshot --store docker://house-db-1/u/house_db"}, cwd=cwd)) is None
