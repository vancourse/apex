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
from rails.gates import allow_edit, arm_review, milestone_close, operator_bounds, store_guard, test_filter
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
    assert [(i["id"], i["closes"]) for i in added] == [("42-a1", "#42"), ("42-2", "#42")]
    assert work.add_from_issue(rid, "#42", ISSUE) == []
    # a second issue from the same template keeps its own `step: a1`
    assert [i["id"] for i in work.add_from_issue(rid, "43", ISSUE)] == ["43-a1", "43-2"]
    # an edited issue adds the new line instead of dropping it on an id collision
    edited = ISSUE.replace("a row with no date", "a row with a blank date")
    assert [i["id"] for i in work.add_from_issue(rid, "42", edited)] == ["42-2.2"]


def test_a_steps_to_reproduce_section_is_not_acceptance():
    body = "## Steps to reproduce\n- open the export\n- click save\n\n**Done when** the save keeps closed accounts\n"
    assert work.acceptance_lines(body) == [("the save keeps closed accounts", "")]


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
    out = io.StringIO()
    assert ship._review_allows_arming(rid, repo, out) is False and "must-fix" in out.getvalue()  # open items
    clean = '{"reviewed_sha": "abc", "must_fix": [], "consider": []}\n' + "y" * 220
    (tmp_path / "c.md").write_text("Steelman.\n" + clean, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean, encoding="utf-8")
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
        # from a shell: nothing tells the operator's terminal from an agent's, so it does not close
        state.setdefault("used", []).append({"milestone": "#7", "task": "x", "at": 1, "by": "shell"})
    code, text = close.close(repo, "#7")
    assert code == 1 and "no `used` record" in text
    with store.updating(rid.dir / "state.json", {}) as state:
        state["used"].append({"milestone": "#7", "task": "filed a real claim", "at": 2, "by": "prompt"})
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


def test_test_filter_reads_the_command_word_not_the_text():
    # pytest named in a commit message, or a `-k` with "not" in a non-pytest command
    assert test_filter.check(_evt("Bash", {"command": "git commit -m 'pytest -k not slow is refused now'"})) is None
    assert test_filter.check(_evt("Bash", {"command": "grep -k 'not' pytest.ini"})) is None
    assert test_filter.check(_evt("Bash", {"command": "uv run pytest -m 'not db' tests"})) is None  # a marker lane
    assert test_filter.check(_evt("PowerShell", {"command": "python -m pytest '-knot slow' tests"}))
    assert test_filter.check(_evt("Bash", {"command": "PYTEST_ADDOPTS='-k \"not slow\"' uv run pytest tests"}))
    assert test_filter.check(_evt("Bash", {"command": "cd x && pytest --deselect=tests/a.py::t"}))


def test_test_filter_sees_addopts_set_earlier_and_pytest_after_runner_options():
    ps = "$env:PYTEST_ADDOPTS='--deselect tests/test_x.py::test_y'; uv run pytest"
    assert test_filter.check(_evt("PowerShell", {"command": ps}))
    assert test_filter.check(_evt("Bash", {"command": "export PYTEST_ADDOPTS=\"-k 'not slow'\" && pytest"}))
    assert test_filter.check(_evt("Bash", {"command": "uv run --directory apps/purser python -m pytest -k 'not flaky'"}))
    assert test_filter.check(_evt("Bash", {"command": "docker compose exec -T api python -m pytest -k 'not slow'"}))
    assert test_filter.check(_evt("Bash", {"command": "pytest -o addopts='--deselect tests/a.py::t'"}))
    assert test_filter.check(_evt("Bash", {"command": "$env:PYTEST_ADDOPTS='-q'; uv run pytest"})) is None
    # pytest as an argument of something that is not a runner is not a test run
    assert test_filter.check(_evt("Bash", {"command": "echo pytest --deselect is refused now"})) is None


def test_allow_edit_sees_a_shell_write_and_the_leak_config():
    assert allow_edit.check(_evt("Bash", {"command": "echo '[[allow]]' >> rails/leak_allow.toml"}, agent_id="s"))
    assert allow_edit.check(_evt("PowerShell", {"command": "Set-Content rails/leak.toml ''"}, agent_id="s"))
    assert allow_edit.check(_evt("Edit", {"file_path": "C:/r/rails/leak.toml", "old_string": "a", "new_string": "b"}, agent_id="s"))
    assert allow_edit.check(_evt("Bash", {"command": "cat rails/leak_allow.toml"}, agent_id="s")) is None
    assert allow_edit.check(_evt("Bash", {"command": "echo x >> rails/leak_allow.toml"})) is None  # the session itself
    one_liner = "python -c \"open('rails/leak.toml','w').write('[guard]\\nnames = []\\n')\""
    assert allow_edit.check(_evt("Bash", {"command": one_liner}, agent_id="s"))
    assert allow_edit.check(_evt("Bash", {"command": "perl -pi -e 's/a/b/' rails/x_allow.toml"}, agent_id="s"))
    assert allow_edit.check(_evt("Bash", {"command": "cat rails/leak.toml 2>/dev/null"}, agent_id="s")) is None
    reads = "python -c \"print(open('rails/leak.toml').read())\""
    assert allow_edit.check(_evt("Bash", {"command": reads}, agent_id="s")) is None


def test_milestone_close_sees_a_variable_number_and_an_input_file(tmp_path):
    cwd = str(tmp_path)
    assert milestone_close.check(_evt("Bash", {"command": 'gh api "repos/a/b/milestones/$N" -X PATCH -f state=closed'}, cwd=cwd))
    assert milestone_close.check(
        _evt("Bash", {"command": "python -c \"subprocess.run(['gh','api','repos/a/b/milestones/7','-X','PATCH','-f','state=closed'])\""}, cwd=cwd)
    )
    (tmp_path / "body.json").write_text('{"state": "closed"}', encoding="utf-8")
    assert milestone_close.check(_evt("Bash", {"command": "gh api repos/a/b/milestones/7 -X PATCH --input body.json"}, cwd=cwd))
    (tmp_path / "desc.json").write_text('{"description": "operator correction"}', encoding="utf-8")
    assert milestone_close.check(_evt("Bash", {"command": "gh api repos/a/b/milestones/7 -X PATCH --input desc.json"}, cwd=cwd)) is None


def test_milestone_close_sees_quoted_variables_stdin_and_the_post_alias(tmp_path):
    cwd = str(tmp_path)
    for command in (
        'gh api repos/a/b/milestones/"$N" -X PATCH -f state=closed',
        'gh api "repos/a/b/milestones/$($m.number)" -X PATCH -f state=closed',
        "gh api repos/a/b/milestones/75 -f state=closed",  # gh sends POST; GitHub takes it as PATCH
        "gh api repos/a/b/milestones/75 -X PATCH --input -",  # a body from nowhere it can read
    ):
        assert milestone_close.check(_evt("Bash", {"command": command}, cwd=cwd)), command
    (tmp_path / "body.json").write_text('{"state": "closed"}', encoding="utf-8")
    piped = "Get-Content body.json | gh api repos/a/b/milestones/75 -X PATCH --input -"
    assert milestone_close.check(_evt("PowerShell", {"command": piped}, cwd=cwd))
    (tmp_path / "desc.json").write_text('{"description": "x"}', encoding="utf-8")
    fine = "cat desc.json | gh api repos/a/b/milestones/75 -X PATCH --input -"
    assert milestone_close.check(_evt("Bash", {"command": fine}, cwd=cwd)) is None
    assert milestone_close.check(_evt("Bash", {"command": "gh api 'repos/a/b/milestones?state=closed'"}, cwd=cwd)) is None


def test_operator_bounds_refuses_naming_the_store(repo):
    """The household store by name: in a command, and in a file an agent would then run."""
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text('[guard]\nnames = ["house-db-1", "house_db"]\n', encoding="utf-8")
    cwd = str(repo)
    assert operator_bounds.check(_evt("Bash", {"command": "docker exec house-db-1 psql -d house_db -c 'select 1'"}, cwd=cwd))
    assert operator_bounds.check(_evt("Bash", {"command": "docker exec other-db-1 psql -c 'select 1'"}, cwd=cwd)) is None
    # no `rails` exemption: snapshot is the operator's (their shell is never seen here), and
    # `rails receipt -- <cmd>` runs whatever follows it
    assert operator_bounds.check(_evt("Bash", {"command": "rails snapshot --store docker://house-db-1/u/house_db"}, cwd=cwd))
    assert operator_bounds.check(_evt("Bash", {"command": "rails receipt -- docker exec house-db-1 psql -c 'select 1'"}, cwd=cwd))
    assert operator_bounds.check(_evt("Bash", {"command": "rails check; docker exec house-db-1 psql"}, cwd=cwd))
    assert operator_bounds.check(_evt("Write", {"file_path": f"{cwd}/q.sh", "content": "psql -d house_db"}, cwd=cwd))
    assert operator_bounds.check(_evt("Write", {"file_path": f"{cwd}/q.sh", "content": "psql -d planted"}, cwd=cwd)) is None
    assert store_guard.check(_evt("Bash", {"command": "docker exec house-db-1 psql"}, cwd=cwd)) is None  # one owner


def test_operator_bounds_refuses_touching_the_agent_marker(tmp_path):
    for command in (
        "CLAUDECODE=0 rails used #75 x",
        "env -u CLAUDECODE git push",
        "$env:CLAUDECODE=''; rails release",
        "Remove-Item Env:CLAUDE*; rails used 75 walked",
        "unset ${!CLAUDE@}; git push",
        "env -i PATH=/usr/bin rails release",
        "for v in ${!CLAUDE@}; do export $v=; done; rails release",
    ):
        assert operator_bounds.check(_evt("Bash", {"command": command})), command
    # a script written to run next
    script = {"file_path": f"{tmp_path}/u.sh", "content": "CLAUDECODE= rails used 75 'invited my spouse'\n"}
    assert operator_bounds.check(_evt("Write", script))
    # naming or reading it is not touching it; a test file's planted inputs are not a script
    assert operator_bounds.check(_evt("Bash", {"command": "git grep -n CLAUDECODE rails/"})) is None
    assert operator_bounds.check(_evt("Bash", {"command": "rails check"})) is None
    reads = {"file_path": f"{tmp_path}/g.py", "content": 'return os.environ.get("CLAUDECODE") == "1"\n'}
    assert operator_bounds.check(_evt("Write", reads)) is None
    planted = {"file_path": f"{tmp_path}/tests/test_x.py", "content": '"CLAUDECODE=0 rails used #75 x"\n'}
    assert operator_bounds.check(_evt("Write", planted)) is None


def test_the_operators_shell_words_are_recorded_but_weaker(repo, monkeypatch, capsys):
    """An agent can clear CLAUDECODE and its tool calls report a TTY (measured on Windows), so
    a word from a shell neither closes a milestone nor lifts a hold set in a prompt."""
    monkeypatch.chdir(repo)
    assert cli.cmd_words("used", ["walked", "it"]) == 2  # not a milestone number
    assert cli.cmd_words("used", ["76", "filed", "a", "claim"]) == 0
    rid = store.find_repo(repo)
    rows = store.read_json(rid.dir / "state.json")["used"]
    assert rows[-1]["milestone"] == "#76" and rows[-1]["by"] == "shell"
    assert close.used_records(rid, "76") == []
    with store.updating(rid.dir / "state.json", {}) as state:
        state["hold"] = {"on": True, "since": "now", "by": "prompt"}
    assert cli.cmd_words("release", []) == 2
    assert store.read_json(rid.dir / "state.json")["hold"]["on"] is True
    with store.updating(rid.dir / "state.json", {}) as state:
        state["hold"] = {"on": True, "since": "now", "by": "shell"}
    assert cli.cmd_words("release", []) == 0


def _pushed(git, repo):
    git(repo, "update-ref", "refs/remotes/origin/work", "HEAD")


def test_arm_review_refuses_a_hand_armed_merge_without_a_review(repo, commit, git, tmp_path, monkeypatch):
    """The planted defect for `arm_review`: `gh pr merge --auto` skips what `rails ship` checks."""
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    cwd = str(repo)
    arm = _evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=cwd)
    assert "review" in arm_review.check(arm).reason
    assert arm_review.check(_evt("Bash", {"command": "gh pr merge 12 --squash"}, cwd=cwd)) is None  # not an arm
    monkeypatch.chdir(repo)
    open_fix = '{"reviewed_sha": "abc", "must_fix": [{"what": "drops a blank date", "reproducer": "feed one"}]}\n' + "x" * 220
    (tmp_path / "c.md").write_text("Steelman.\n" + open_fix, encoding="utf-8")
    (tmp_path / "a.md").write_text(open_fix, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    assert "must-fix" in arm_review.check(arm).reason
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md", accept="the blank date is refused upstream, see #9")
    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "armed": False})
    assert arm_review.check(arm) is None
    assert store.read_json(rid.leaf_dir / "pr.json")["armed"] is True  # turn_end now holds the turn


def test_arm_review_reads_words_and_judges_the_pushed_head(repo, commit, git, tmp_path):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    cwd = str(repo)
    for command in (
        "gh.exe pr merge 12 --auto --squash",
        "gh -R acme/app pr merge 12 --squash --auto",
        "gh pr merge 12 \\\n  --auto --squash",
        "gh api graphql -f query='mutation { enablePullRequestAutoMerge(input: {pullRequestId: \"x\"}) { clientMutationId } }'",
    ):
        assert arm_review.check(_evt("Bash", {"command": command}, cwd=cwd)), command
    (repo / "arm.graphql").write_text("mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }", encoding="utf-8")
    assert arm_review.check(_evt("Bash", {"command": "gh api graphql -F query=@arm.graphql"}, cwd=cwd))
    # mentioning the command is not arming
    assert arm_review.check(_evt("Bash", {"command": "git commit -m 'refuse gh pr merge --auto by hand'"}, cwd=cwd)) is None
    assert arm_review.check(_evt("Bash", {"command": "rg -n enablePullRequestAutoMerge rails/"}, cwd=cwd)) is None
    # a local commit not yet pushed: auto-merge would merge the remote head, not this one
    commit(repo, "src/a.py", "x = 2\n")
    assert "push" in arm_review.check(_evt("Bash", {"command": "gh pr merge 12 --auto"}, cwd=cwd)).reason


def test_must_fix_counts_the_reviewers_json_list():
    assert review.must_fix_count('{"must_fix": [{"a": 1}, {"b": 2}], "consider": [{"c": 3}]}') == 2
    assert review.must_fix_count('{"must_fix": []}') == 0
    assert review.must_fix_count("Must-fix: one\n- must fix: two\nwe must fix nothing else in prose") == 2


def test_must_fix_never_counts_zero_by_accident(repo, commit, tmp_path, monkeypatch):
    # a brace in the prose before the JSON object (`${N}`), and a Markdown heading section
    braced = 'Steelman: reads `milestones/${N}`.\n{"reviewed_sha": "c", "must_fix": [{"file": "a"}], "questions": []}'
    assert review.must_fix_count(braced) == 1
    assert review.must_fix_count("## Must-fix\n- one\n- two\n## Consider\n- three\n") == 2
    assert review.must_fix_count('{"must_fix": [ {"file": "a"} ') is None  # uncountable, not 0
    monkeypatch.chdir(repo)
    commit(repo, "src/a.py", "x = 1\n")
    (tmp_path / "c.md").write_text("Steelman.\n" + '{"must_fix": [ broken ' + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text('{"must_fix": []}' + "y" * 220, encoding="utf-8")
    code, text = review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    assert code == 2 and "does not parse" in text


def test_review_refuses_a_dirty_working_copy(repo, commit, tmp_path, monkeypatch):
    """The voices read the disk; the receipt names HEAD's tree. They must be the same."""
    monkeypatch.chdir(repo)
    commit(repo, "src/a.py", "x = 1\n")
    (repo / "src" / "a.py").write_text("x = 2  # the fix, uncommitted\n", encoding="utf-8")
    (tmp_path / "c.md").write_text("Steelman.\n" + '{"must_fix": []}' + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text('{"must_fix": []}' + "y" * 220, encoding="utf-8")
    code, text = review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    assert code == 2 and "uncommitted" in text


def test_a_push_to_an_open_pr_needs_a_review_of_the_pushed_tree(repo, commit, monkeypatch, tmp_path):
    """Arming is checked once; auto-merge merges whatever is pushed later (review of 1.3.0)."""
    _rows(monkeypatch, names=("prepush_hold", "prepush_marker", "prepush_retired", "prepush_leak", "ship_review"))
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: True)
    rid = store.find_repo(repo)
    from rails import leak

    store.write_json(leak.snapshot_path(rid), leak.build_snapshot(["9999.99"], {}, "t"))
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    line = [f"refs/heads/work {sha} refs/heads/work {ZERO}"]
    code, msgs = githooks.pre_push([], line, rid)
    assert code == 1 and any("open PR" in m for m in msgs)
    monkeypatch.chdir(repo)
    clean = '{"must_fix": []}'
    (tmp_path / "c.md").write_text("Steelman.\n" + clean + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean + "y" * 220, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    assert githooks.pre_push([], line, rid) == (0, [])
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: False)
    sha2 = commit(repo, "src/a.py", "x = 2\n")
    receipts.write_marker(rid, sha2, "t", ["checks"], quick=True)
    line2 = [f"refs/heads/work {sha2} refs/heads/work {ZERO}"]
    assert githooks.pre_push([], line2, rid) == (0, [])  # before a PR exists, no review is asked


def _pushable(monkeypatch, repo, commit, *, shadow_review: bool):
    """A leak snapshot, a full marker and an open PR for one pushed commit."""
    names = ("prepush_hold", "prepush_marker", "prepush_retired", "prepush_leak", "ship_review")
    rows = {
        n: GateRow(
            name=n,
            module="prepush",
            events=["git:pre-push"],
            mode="shadow" if (shadow_review and n == "ship_review") else "enforce",
        )
        for n in names
    }
    monkeypatch.setattr(githooks, "_registry_rows", lambda: rows)
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: True)
    rid = store.find_repo(repo)
    from rails import leak

    store.write_json(leak.snapshot_path(rid), leak.build_snapshot(["9999.99"], {}, "t"))
    return rid


def _armed(monkeypatch, number: int | None = 12) -> list[tuple[int, str]]:
    disarmed: list[tuple[int, str]] = []
    monkeypatch.setattr(githooks, "armed_pr", lambda repo, branch: number)
    monkeypatch.setattr(
        githooks, "disarm", lambda repo, n, note: disarmed.append((n, note)) or True
    )
    return disarmed


def test_p2a_an_unreviewed_push_to_an_armed_pr_disarms_it(repo, commit, monkeypatch):
    """The planted defect for `prepush_disarm`: `ship_review` in shadow lets the push through,
    and GitHub's auto-merge would merge the unreviewed tree."""
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch)
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    lines = [f"refs/heads/work {sha} refs/heads/work {ZERO}"]
    code, msgs = githooks.pre_push(["origin", "u"], lines, rid)
    assert code == 0 and disarmed == [], "nothing is disarmed before the chained hook passed"
    msgs = githooks.disarm_after_push(["origin", "u"], lines, rid)
    assert [n for n, _ in disarmed] == [12]
    assert sha[:12] in disarmed[0][1]
    assert githooks.pr_holds(rid)["12"]["sha"] == sha, "a disarm holds the PR for every folder"
    assert any("disarmed PR #12" in m and "rails ship" in m for m in msgs), msgs


def test_p2_a_push_to_another_remote_disarms_nothing(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch)
    sha = commit(repo, "src/a.py", "x = 1\n")
    assert githooks.disarm_after_push(["backup", "u"], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid) == []
    assert disarmed == []


def test_p2_a_push_the_chained_hook_refuses_disarms_nothing(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    called: list[object] = []
    monkeypatch.setattr(githooks, "pre_push", lambda *a: (0, []))
    monkeypatch.setattr(githooks, "run_chained", lambda *a: 1)
    monkeypatch.setattr(githooks, "disarm_after_push", lambda *a: called.append(a) or [])
    monkeypatch.chdir(repo)
    monkeypatch.setattr(githooks.sys, "stdin", io.StringIO(""))
    assert githooks.main(["x", "pre-push", "origin", "u"]) == 1
    assert called == []
    monkeypatch.setattr(githooks, "run_chained", lambda *a: 0)
    assert githooks.main(["x", "pre-push", "origin", "u"]) == 0
    assert len(called) == 1
    assert rid


def test_p2a_the_operator_s_own_push_disarms_too(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=False)
    disarmed = _armed(monkeypatch)
    monkeypatch.setenv("RAILS_OPERATOR", "1")
    monkeypatch.setattr(githooks, "operator", lambda: True)
    sha = commit(repo, "src/a.py", "x = 1\n")
    lines = [f"refs/heads/work {sha} refs/heads/work {ZERO}"]
    code, msgs = githooks.pre_push(["origin", "u"], lines, rid)
    assert code == 0, msgs
    githooks.disarm_after_push(["origin", "u"], lines, rid)
    assert [n for n, _ in disarmed] == [12]


def test_p2_a_refused_push_lands_nothing_and_disarms_nothing(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=False)
    disarmed = _armed(monkeypatch)
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    code, _ = githooks.pre_push([], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid)
    assert code == 1 and disarmed == []


def test_p2b_a_prose_only_push_after_the_review_stays_armed(
    repo, commit, monkeypatch, tmp_path
):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch)
    sha = commit(repo, "src/a.py", "x = 1\n")
    monkeypatch.chdir(repo)
    clean = '{"must_fix": []}'
    (tmp_path / "c.md").write_text("Steelman.\n" + clean + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean + "y" * 220, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    prose = commit(repo, "docs/notes.md", "# notes\n")
    receipts.write_marker(rid, prose, "t", ["checks"], quick=False)
    lines = [f"refs/heads/work {prose} refs/heads/work {ZERO}"]
    code, msgs = githooks.pre_push([], lines, rid)
    assert code == 0, msgs
    msgs = githooks.disarm_after_push(["origin", "u"], lines, rid)
    assert disarmed == [], msgs
    assert sha  # the reviewed code commit is the one the receipt covers


def test_p2_a_pr_that_is_not_armed_is_left_alone(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch, number=None)
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    lines = [f"refs/heads/work {sha} refs/heads/work {ZERO}"]
    code, msgs = githooks.pre_push([], lines, rid)
    assert code == 0, msgs
    msgs = githooks.disarm_after_push(["origin", "u"], lines, rid)
    assert disarmed == [] and not any("disarmed" in m for m in msgs)


def test_p2_disarm_never_blanks_a_body_it_could_not_read(repo, monkeypatch):
    """`gh pr view` failing must not lead to `gh pr edit` with an empty body."""
    rid = store.find_repo(repo)
    calls: list[list[str]] = []

    def fake_run(argv, **_):
        calls.append(argv)
        ok = argv[:3] == ["gh", "pr", "merge"]
        return subprocess.CompletedProcess(argv, 0 if ok else 1, stdout="", stderr="boom")

    monkeypatch.setattr(githooks.subprocess, "run", fake_run)
    assert githooks.disarm(rid, 12, "note") is True
    assert [c[:3] for c in calls] == [["gh", "pr", "merge"], ["gh", "pr", "view"]]


def test_a_ticked_box_is_still_owed_and_comments_are_not():
    body = (
        "## Acceptance criteria\n- [x] `step: a1` the invite opens on her phone\n- [ ] she sees only her items\n"
        "<!--\n- a template hint inside a comment\n-->\n"
    )
    assert work.acceptance_lines(body) == [
        ("`step: a1` the invite opens on her phone", "a1"),
        ("she sees only her items", ""),
    ]


def test_check_does_not_post_after_red(hooked, git, monkeypatch):
    base = git(hooked, "rev-parse", "origin/main")
    git(hooked, "rm", "-q", ".claude/hooks/old_gate.py")
    git(hooked, "commit", "-q", "-m", "retire the hook")
    assert structural.run(hooked, base)
    posted = []
    monkeypatch.setattr(check_mod, "post", lambda cwd, out=None: posted.append(cwd))
    out = io.StringIO()
    assert check_mod.check(hooked, out=out, post_after=True) == 1
    assert posted == [] and "not posting" in out.getvalue()


def test_an_expired_placeholder_may_be_deleted(hooked, git, monkeypatch):
    import datetime as dt

    structural.retire_hook(hooked, ".claude/hooks/old_gate.py", today=dt.date(2026, 10, 8))
    git(hooked, "add", "-A")
    git(hooked, "commit", "-q", "-m", "placeholder")
    git(hooked, "update-ref", "refs/remotes/origin/main", "HEAD")
    base = git(hooked, "rev-parse", "origin/main")
    git(hooked, "rm", "-q", ".claude/hooks/old_gate.py")
    git(hooked, "commit", "-q", "-m", "delete the placeholder")
    assert structural.hook_removals(hooked, base, today=dt.date(2026, 10, 9)) != []  # before its date
    assert structural.hook_removals(hooked, base, today=dt.date(2027, 1, 1)) == []  # after it


def test_used_needs_a_milestone_number():
    from rails.gates import prompt_words

    assert prompt_words._USED.match("used #75 invited my spouse")
    assert prompt_words._USED.match("Used 3 hours on this, still broken") is None
    assert prompt_words._USED.match("used it twice") is None


def test_markdown_that_runs_is_not_prose():
    assert ship.is_prose("docs/design/x.md") and ship.is_prose("CHANGELOG.md")
    assert not ship.is_prose("agents/reviewer-coop.md")
    assert not ship.is_prose("skills/rails/SKILL.md")
    assert not ship.is_prose("templates/spec.md")
    assert not ship.is_prose("CLAUDE.md") and not ship.is_prose("apps/x/AGENTS.md")  # instructions that run
    assert not ship.is_prose("docs/CLAUDE.md")
    assert not ship.is_prose("docs/tools/render.py")  # code under docs/
    assert ship.is_prose("docs/process/the-loop.html")


def test_every_intent_reader_takes_what_powershell_writes(repo):
    """UTF-16 (`>` in PS 5.1) and a UTF-8 BOM (`Set-Content -Encoding UTF8`) read the same."""
    path = repo / ".rails" / "intent.md"
    path.parent.mkdir()
    text = "# Build the export — closed accounts too\n\nBody.\n"
    path.write_text(text, encoding="utf-8")
    plain = intent.current_hash(repo)
    for encoding in ("utf-16", "utf-8-sig"):
        path.write_bytes(text.encode(encoding))
        assert intent.current_hash(repo) == plain, encoding
        assert ship._intent_title_body(repo)[0] == "Build the export — closed accounts too", encoding


def test_the_push_intent_check_fails_closed(repo, commit, monkeypatch):
    _rows(monkeypatch)
    rid = store.find_repo(repo)
    sha = commit(repo, "a.txt", "plain\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=True)
    from rails import leak

    store.write_json(leak.snapshot_path(rid), leak.build_snapshot(["9999.99"], {}, "t"))
    monkeypatch.setenv("CLAUDECODE", "1")

    def boom(top):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(intent, "current_hash", boom)
    code, msgs = githooks.pre_push([], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid)
    assert code == 1 and any("could not be read" in m for m in msgs)


# --- third review round -------------------------------------------------------------------


def test_the_push_check_judges_the_pushed_commit_not_head(repo, commit, git, monkeypatch):
    """A code commit pushed from a checkout whose HEAD is elsewhere still needs its review."""
    _rows(monkeypatch, names=("prepush_hold", "prepush_marker", "prepush_retired", "prepush_leak", "ship_review"))
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: True)
    rid = store.find_repo(repo)
    from rails import leak

    store.write_json(leak.snapshot_path(rid), leak.build_snapshot(["9999.99"], {}, "t"))
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    git(repo, "checkout", "-q", "--detach", "origin/main")  # HEAD's own diff is empty
    code, msgs = githooks.pre_push([], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid)
    assert code == 1 and any("open PR" in m for m in msgs)


def test_must_fix_reads_the_reviewers_last_object_and_its_sections():
    quoted = 'Steelman: the clean case `{"must_fix": []}` is pinned.\n{"reviewed_sha": "d", "must_fix": [{"file": "a"}]}'
    assert review.must_fix_count(quoted) == 1
    sub = "## Must-fix\n\n### 1. ship.py:308 drops Closes\nReproducer: x\n\n### 2. githooks.py:201\n\n## Questions\n- q\n"
    assert review.must_fix_count(sub) == 2
    assert review.must_fix_count("## Must-fix\n**1. ship.py** drops it\n**2. cli.py** too\n") == 2
    assert review.must_fix_count("**Must-fix:** none\n") == 0
    assert review.must_fix_count("## Must-fix\n- None\n## Consider\n- x\n") == 0


def test_a_docs_commit_after_the_review_is_still_covered(repo, commit, tmp_path, monkeypatch):
    monkeypatch.chdir(repo)
    commit(repo, "src/a.py", "x = 1\n")
    clean = '{"must_fix": []}'
    (tmp_path / "c.md").write_text("Steelman.\n" + clean + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean + "y" * 220, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    rid = store.find_repo(repo)
    commit(repo, "docs/notes.md", "the design amendment\n")
    assert review.covering(rid, repo, "HEAD") is not None  # prose after the review: covered
    commit(repo, "src/a.py", "x = 2\n")
    assert review.covering(rid, repo, "HEAD") is None  # code after the review: not


def test_arm_review_sees_graphql_bodies_and_refuses_a_detached_head(repo, commit, git, tmp_path):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    cwd = str(repo)
    (repo / "arm.json").write_text('{"query": "mutation { enablePullRequestAutoMerge(input: {}) { x } }"}', encoding="utf-8")
    (repo / "read.json").write_text('{"query": "query { viewer { login } }"}', encoding="utf-8")
    for command in (
        "gh api graphql --input arm.json",
        "Get-Content arm.json | gh api graphql --input -",
        "$q = 'mutation { enablePullRequestAutoMerge(input: {}) { x } }'; gh api graphql -f query=$q",
        "gh api graphql --input missing.json",  # a body it cannot read counts
    ):
        assert arm_review.check(_evt("PowerShell", {"command": command}, cwd=cwd)), command
    assert arm_review.check(_evt("Bash", {"command": "gh api graphql --input read.json"}, cwd=cwd)) is None
    git(repo, "checkout", "-q", "--detach", "HEAD")
    assert "detached" in arm_review.check(_evt("Bash", {"command": "gh pr merge 12 --auto"}, cwd=cwd)).reason


def test_arm_review_counts_origin_branch_as_pushed_and_fails_closed(repo, commit, git, tmp_path, monkeypatch):
    commit(repo, "docs/a.md", "prose only\n")
    _pushed(git, repo)
    git(repo, "remote", "add", "origin", "https://example.invalid/app.git")
    git(repo, "branch", "--set-upstream-to=origin/main")  # cut from master: @{u} is not the PR head
    store.write_json(store.find_repo(repo).leaf_dir / "pr.json", {"number": 12})  # this worktree's PR (p3f)
    arm = _evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo))
    assert arm_review.check(arm) is None  # origin/work holds HEAD; a prose diff needs no review

    def boom(*a, **k):
        raise ValueError("lanes.toml: duplicate lane")

    monkeypatch.setattr(ship, "needs_review", boom)
    assert "could not be checked" in arm_review.check(arm).reason


def test_operator_bounds_reads_shapes_not_mentions(repo, tmp_path):
    for command in (
        "Write-Output $env:CLAUDECODE",
        "Get-ChildItem Env:CLAUDE*",
        "Remove-Item C:/Users/me/AppData/Local/Temp/claude/proj/scratchpad/out.json",
        "Get-Content \"$env:USERPROFILE/.claude/settings.json\"",
        "git commit -m 'operator_bounds: refuse env -i'",
    ):
        assert operator_bounds.check(_evt("PowerShell", {"command": command})) is None, command
    py = {"file_path": f"{tmp_path}/launcher.py", "content": "os.environ.update(env)\n# the harness exports CLAUDECODE=1\n"}
    assert operator_bounds.check(_evt("Write", py)) is None
    script = {"file_path": f"{tmp_path}/tests/u.ps1", "content": "Remove-Item Env:CLAUDECODE; rails used 75 walked\n"}
    assert operator_bounds.check(_evt("Write", script))  # a shell script under tests/ is still a script
    pyset = {"file_path": f"{tmp_path}/u.py", "content": "os.environ.pop('CLAUDECODE')\n"}
    assert operator_bounds.check(_evt("Write", pyset))


def test_operator_bounds_judges_store_names_only_where_a_database_is_reached(repo):
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text('[guard]\nnames = ["house-db-1", "house_db"]\n', encoding="utf-8")
    cwd = str(repo)
    assert operator_bounds.check(_evt("Bash", {"command": "rg -n house_db scripts/"}, cwd=cwd)) is None
    assert operator_bounds.check(_evt("Bash", {"command": "git log -S house_db --oneline"}, cwd=cwd)) is None
    fleet = {"file_path": f"{cwd}/scripts/fleet.py", "content": 'DATABASE = "house_db"\n'}
    assert operator_bounds.check(_evt("Write", fleet, cwd=cwd)) is None
    assert operator_bounds.check(_evt("Bash", {"command": "psql -h 127.0.0.1 -d house_db -c 'select 1'"}, cwd=cwd))


def test_milestone_close_judges_the_writing_statement_only(tmp_path):
    cwd = str(tmp_path)
    for command in (
        "gh api repos/o/r/milestones/75; gh issue list --milestone 75 --state closed",
        "gh api repos/o/r/milestones/75 --jq 'select(.state==\"closed\")'",
    ):
        assert milestone_close.check(_evt("Bash", {"command": command}, cwd=cwd)) is None, command
    (tmp_path / "c.json").write_text('{"state": "closed"}', encoding="utf-8")
    unread = "gh api repos/o/r/milestones/75 -X PATCH --input $env:TEMP/c.json"
    assert milestone_close.check(_evt("PowerShell", {"command": unread}, cwd=cwd))  # cannot read it: fail closed


def test_allow_edit_sees_powershell_copy_aliases():
    assert allow_edit.check(_evt("PowerShell", {"command": "copy $env:TEMP/a.toml rails/leak_allow.toml"}, agent_id="s"))
    assert allow_edit.check(_evt("Bash", {"command": "rm rails/leak.toml"}, agent_id="s"))


def test_test_filter_sees_every_way_to_set_addopts():
    for command in (
        "Set-Item Env:PYTEST_ADDOPTS '--deselect tests/a.py::t'; uv run pytest",
        "[Environment]::SetEnvironmentVariable('PYTEST_ADDOPTS','--deselect tests/a.py::t'); uv run pytest",
        "timeout 600 pytest -k 'not slow'",
        "python3.12 -m pytest -k 'not slow'",
    ):
        assert test_filter.check(_evt("PowerShell", {"command": command})), command


def test_the_push_check_takes_the_merge_base_of_the_pushed_commit(repo, commit, git, monkeypatch):
    """Trunk took the same change since: from HEAD's merge-base the diff is empty, from the
    pushed commit's it is the code change the review must cover."""
    _rows(monkeypatch, names=("prepush_hold", "prepush_marker", "prepush_retired", "prepush_leak", "ship_review"))
    monkeypatch.setattr(githooks, "open_pr", lambda repo, branch: True)
    rid = store.find_repo(repo)
    from rails import leak

    store.write_json(leak.snapshot_path(rid), leak.build_snapshot(["9999.99"], {}, "t"))
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write_marker(rid, sha, "t", ["checks"], quick=False)
    git(repo, "checkout", "-q", "-b", "trunk", "origin/main")
    commit(repo, "src/a.py", "x = 1\n", "trunk took the same change")
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(repo, "checkout", "-q", "--detach", "origin/main")
    code, msgs = githooks.pre_push([], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid)
    assert code == 1 and any("open PR" in m for m in msgs)


def test_open_pr_reads_a_gh_failure_as_open(repo, monkeypatch):
    import shutil
    import subprocess as sp

    rid = store.find_repo(repo)
    monkeypatch.setattr(shutil, "which", lambda name: "gh")

    def gh(stderr):
        return lambda *a, **k: sp.CompletedProcess(a[0], 1, "", stderr)

    monkeypatch.setattr(githooks.subprocess, "run", gh("no pull requests found for branch \"work\""))
    assert githooks.open_pr(rid, "work") is False
    monkeypatch.setattr(githooks.subprocess, "run", gh("HTTP 401: Bad credentials"))
    assert githooks.open_pr(rid, "work") is True  # unknown: the full marker and the review are asked


def test_a_corrected_intent_is_not_acked_even_if_marked_shown(repo):
    from rails.dispatch import dispatch
    from rails.gates import prompt_words

    (repo / ".rails").mkdir()
    (repo / ".rails" / "intent.md").write_text("# build the export\n", encoding="utf-8")
    rid = store.find_repo(repo)
    h = intent.current_hash(repo)
    import time as _t

    intent.update(rid, hash=h, shown_at=int(_t.time()) - 60, corrected_hash=h)  # an older stamp
    row = GateRow(name="prompt_words", module="prompt_words", events=["UserPromptSubmit"], mode="enforce")
    evt = Event(name="UserPromptSubmit", payload={"hook_event_name": "UserPromptSubmit", "cwd": str(repo),
                                                  "session_id": "s", "prompt": "ok"})
    dispatch(evt, [row])
    assert not intent.acked(rid, repo)
    assert prompt_words.NAME == "prompt_words"


def test_a_python_test_file_may_plant_the_marker_code():
    planted = {"file_path": "C:/r/tests/test_bounds.py", "content": "os.environ.pop('CLAUDECODE')\n"}
    assert operator_bounds.check(_evt("Write", planted)) is None


# --- verify-only round on 8d87dac ---------------------------------------------------------


def test_a_shell_hold_does_not_relabel_the_operators_prompt_hold(repo, monkeypatch):
    monkeypatch.chdir(repo)
    rid = store.find_repo(repo)
    with store.updating(rid.dir / "state.json", {}) as state:
        state["hold"] = {"on": True, "since": "now", "by": "prompt"}
    monkeypatch.setenv("CLAUDECODE", "1")
    assert cli.cmd_words("hold", []) == 0
    monkeypatch.delenv("CLAUDECODE")
    assert cli.cmd_words("release", []) == 2
    assert store.read_json(rid.dir / "state.json")["hold"] == {"on": True, "since": "now", "by": "prompt"}


def test_a_correction_lets_the_stop_hook_ask_for_the_rewrite(repo):
    from rails.dispatch import dispatch
    from rails.gates import intent_shown

    (repo / ".rails").mkdir()
    (repo / ".rails" / "intent.md").write_text("# build the export\n", encoding="utf-8")
    rid = store.find_repo(repo)
    h = intent.current_hash(repo)
    import time as _t

    intent.update(rid, hash=h, shown_at=int(_t.time()) - 60, blocked_hash=h)  # blocked once before
    row = GateRow(name="prompt_words", module="prompt_words", events=["UserPromptSubmit"], mode="enforce")
    evt = Event(name="UserPromptSubmit", payload={"hook_event_name": "UserPromptSubmit", "cwd": str(repo),
                                                  "session_id": "s", "prompt": "no, use xlsx instead"})
    dispatch(evt, [row])
    assert intent.get(rid).get("blocked_hash") == ""
    out = intent_shown.check(Event(name="Stop", payload={"hook_event_name": "Stop", "cwd": str(repo),
                                                          "session_id": "s", "transcript_path": ""}))
    assert out is not None and "Rewrite" in out.reason


def test_store_names_are_judged_across_a_command_that_reaches_a_database(repo):
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text('[guard]\nnames = ["house-db-1", "house_db"]\n', encoding="utf-8")
    cwd = str(repo)
    assert operator_bounds.check(_evt("Bash", {"command": "export PGDATABASE=house_db; psql -c 'select 1'"}, cwd=cwd))
    assert operator_bounds.check(_evt("PowerShell", {"command": "$c='house-db-1'; docker exec $c psql -c 'select 1'"}, cwd=cwd))
    edit = {"file_path": f"{cwd}/q.sh", "old_string": "planted", "new_string": "house_db"}
    assert operator_bounds.check(_evt("Edit", edit, cwd=cwd))  # a fragment swapped into a script
    assert operator_bounds.check(_evt("PowerShell", {"command": "Get-ChildItem Env:CLAUDE* | Remove-Item; rails release"}))


def test_milestone_close_attached_flags_and_a_variable_endpoint(tmp_path):
    cwd = str(tmp_path)
    for command in (
        "U=repos/a/b/milestones/75; gh api $U -X PATCH -f state=closed",
        "gh api repos/a/b/milestones/75 -XPATCH -fstate=closed",
        "gh api repos/a/b/milestones/75 -fstate=closed",
    ):
        assert milestone_close.check(_evt("Bash", {"command": command}, cwd=cwd)), command


def test_must_fix_ignores_nested_and_quoted_clean_objects():
    nested = '{"must_fix": [{"file": "a", "x": {"must_fix": []}}]}'
    assert review.must_fix_count(nested) == 1
    after = '{"reviewed_sha": "d", "must_fix": [{"file": "a"}]}\nThe clean case is `{"must_fix": []}`.'
    assert review.must_fix_count(after) == 1
    detail = "## Must-fix\n### 1. ship.py drops it\n- reproducer: x\n- why: y\n### 2. cli.py\n"
    assert review.must_fix_count(detail) == 2


def test_allow_edit_does_not_read_a_mention_as_a_write():
    assert allow_edit.check(_evt("Bash", {"command": "rg -n copy rails/leak.toml"}, agent_id="s")) is None
    assert allow_edit.check(_evt("Bash", {"command": "git log -- rails/leak_allow.toml | head"}, agent_id="s")) is None
    assert allow_edit.check(_evt("Bash", {"command": "cat a.toml | tee rails/leak_allow.toml"}, agent_id="s"))


def test_claims_wip_counts_only_prompt_recorded_use(repo):
    from rails import claims

    rid = store.find_repo(repo)
    with store.updating(rid.dir / "state.json", {}) as state:
        state["used"] = [{"milestone": "#7", "by": "shell"}, {"milestone": "#8", "by": "prompt"}]
    assert claims.used_milestones(rid) == {"#8"}


def test_the_marker_set_behind_other_assignments_or_by_env(tmp_path):
    for command in ("env CLAUDECODE=0 git push origin HEAD", "GIT_TRACE=0 CLAUDECODE= git push", "(CLAUDECODE= git push)"):
        assert operator_bounds.check(_evt("Bash", {"command": command})), command
    script = {"file_path": f"{tmp_path}/p.sh", "content": "env CLAUDECODE=0 git push\n"}
    assert operator_bounds.check(_evt("Write", script))
    assert operator_bounds.check(_evt("Bash", {"command": "env PYTHONUTF8=1 git push"})) is None


def test_a_python_script_that_connects_and_names_the_store(repo):
    (repo / "rails").mkdir()
    (repo / "rails" / "leak.toml").write_text('[guard]\nnames = ["house-db-1", "house_db"]\n', encoding="utf-8")
    cwd = str(repo)
    probe = {"file_path": f"{cwd}/scratch/probe.py", "content": 'import psycopg\npsycopg.connect("host=127.0.0.1 dbname=house_db")\n'}
    assert operator_bounds.check(_evt("Write", probe, cwd=cwd))
    assert operator_bounds.check(_evt("Bash", {"command": "$env:PGDATABASE='house_db'; psql -h 127.0.0.1 -c 'select 1'"}, cwd=cwd))


def test_milestone_close_sees_powershell_and_python_writes(tmp_path):
    cwd = str(tmp_path)
    for command in (
        "Invoke-RestMethod -Method Patch -Uri https://api.github.com/repos/o/r/milestones/75 -Body '{\"state\":\"closed\"}'",
        "irm -Method Post -Uri https://api.github.com/repos/o/r/milestones/75 -Body '{\"state\":\"closed\"}'",
        "python -c \"import requests; requests.patch('https://api.github.com/repos/o/r/milestones/75', json={'state': 'closed'})\"",
        "curl -XPATCH https://api.github.com/repos/o/r/milestones/75 -d'{\"state\":\"closed\"}'",
    ):
        assert milestone_close.check(_evt("PowerShell", {"command": command}, cwd=cwd)), command


def test_arm_review_prefers_the_prs_branch_over_the_upstream(repo, commit, git):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)  # origin/work holds the reviewed-or-not code commit
    git(repo, "remote", "add", "origin", "https://example.invalid/app.git")
    git(repo, "branch", "--set-upstream-to=origin/main")
    git(repo, "reset", "-q", "--hard", "origin/main")  # HEAD == @{u}, but not the PR's head
    reason = arm_review.check(_evt("Bash", {"command": "gh pr merge 12 --auto"}, cwd=str(repo))).reason
    assert "push" in reason


def test_a_main_checkout_claim_does_not_fence_an_issue_off(repo, git, tmp_path):
    from rails import claims

    rid = store.find_repo(repo)  # the main checkout
    assert claims.add(rid, "work", ["#12"])[0]
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "wt", str(wt))
    assert claims.add(store.find_repo(wt), "wt", ["#12"])[0]


def test_a_nested_must_fix_list_is_not_the_report():
    assert review.must_fix_count('{"must_fix": [], "notes": {"must_fix": [1, 2]}}') == 0


# --- p3g: pr.json follows the PR after it merges -------------------------------------


def test_p3g_a_merged_pr_stops_reading_open_on_the_next_command(repo, monkeypatch):
    from rails import gitutil

    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 7, "state": "OPEN", "armed": True})
    answers = {"state": "OPEN"}
    asked: list[tuple[str, ...]] = []

    def fake_gh(cwd, *args, check=True, timeout=60):
        asked.append(args)
        return json.dumps(answers)

    monkeypatch.setattr(gitutil, "gh", fake_gh)
    assert cli.refresh_pr_state(repo, now=1000.0) is None  # still open: recorded, unchanged
    assert store.read_json(rid.leaf_dir / "pr.json", {})["state"] == "OPEN"
    answers["state"] = "MERGED"
    assert cli.refresh_pr_state(repo, now=1030.0) is None  # within the minute: not asked again
    assert len(asked) == 1
    assert cli.refresh_pr_state(repo, now=1100.0) == "MERGED"
    record = store.read_json(rid.leaf_dir / "pr.json", {})
    assert record["state"] == "MERGED" and record["armed"] is False
    assert cli.refresh_pr_state(repo, now=2000.0) is None  # not OPEN: never asked again
    assert len(asked) == 2


def test_p3g_an_unanswerable_gh_leaves_the_record_alone(repo, monkeypatch):
    from rails import gitutil

    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 7, "state": "OPEN"})

    def broken(cwd, *args, check=True, timeout=60):
        raise gitutil.GitError("gh failed to run")

    monkeypatch.setattr(gitutil, "gh", broken)
    assert cli.refresh_pr_state(repo, now=1000.0) is None
    record = store.read_json(rid.leaf_dir / "pr.json", {})
    assert record["state"] == "OPEN" and record["state_checked_at"] == 1000.0
    asked: list[object] = []
    monkeypatch.setattr(gitutil, "gh", lambda *a, **k: asked.append(a) or "{}")
    assert cli.refresh_pr_state(repo, now=1030.0) is None
    assert asked == [], "a failure is remembered for the minute too"


# --- p3h: a GraphQL read is judged by a body it can read --------------------------------


def test_p3h_a_graphql_read_whose_input_file_exists_is_not_refused(repo, commit, git):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    (repo / "q.json").write_text('{"query": "query { viewer { login } }"}', encoding="utf-8")
    (repo / "sub").mkdir()
    (repo / "sub" / "q2.json").write_text('{"query": "query { viewer { id } }"}', encoding="utf-8")
    cwd = str(repo)
    assert arm_review.check(_evt("Bash", {"command": "gh api graphql --input q.json"}, cwd=cwd)) is None
    assert arm_review.check(_evt("Bash", {"command": "cat q.json | gh api graphql --input -"}, cwd=cwd)) is None
    assert arm_review.check(_evt("Bash", {"command": "cd sub && gh api graphql --input q2.json"}, cwd=cwd)) is None
    rid = store.find_repo(repo)
    assert store.read_json(rid.leaf_dir / "pr.json", None) is None  # a read never stamps a PR armed


def test_p3h_a_body_it_cannot_read_is_refused_naming_the_path(repo, commit, git):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    cwd = str(repo)
    for command, path in (
        ("gh api graphql --input missing.json", "missing.json"),
        ("Get-Content gone.json | gh api graphql --input -", "gone.json"),
        ("gh api graphql --input=nowhere/q.json", "nowhere/q.json"),
    ):
        deny = arm_review.check(_evt("Bash", {"command": command}, cwd=cwd))
        assert deny is not None and path in deny.reason and "cannot be read" in deny.reason, command


# --- p3j: a close sent from a script file ----------------------------------------------


@pytest.mark.parametrize(
    ("name", "script", "command"),
    [
        pytest.param(
            "close.py",
            "import subprocess\nsubprocess.run(['gh', 'api', 'repos/a/b/milestones/75', '-X', 'PATCH', '-f', 'state=closed'])\n",
            "python close.py",
            id="python",
        ),
        pytest.param(
            "close.sh",
            "#!/bin/sh\ngh api repos/a/b/milestones/75 -X PATCH -f state=closed\n",
            "bash close.sh",
            id="sh",
        ),
        pytest.param(
            "close.ps1",
            "gh api repos/a/b/milestones/75 --method PATCH -f 'state=closed'\n",
            "pwsh -File close.ps1",
            id="ps1",
        ),
    ],
)
def test_p3j_a_close_from_a_script_file_is_refused(tmp_path, name, script, command):
    (tmp_path / name).write_text(script, encoding="utf-8")
    deny = milestone_close.check(_evt("Bash", {"command": command}, cwd=str(tmp_path)))
    assert deny is not None and name in deny.reason, command
    shell = "PowerShell" if name.endswith(".ps1") else "Bash"
    deny = milestone_close.check(_evt(shell, {"command": f"./{name}"}, cwd=str(tmp_path)))
    assert deny is not None, f"./{name}"


def test_p3j_a_script_that_reads_closed_milestones_is_allowed(tmp_path):
    (tmp_path / "list.py").write_text(
        "import subprocess\nsubprocess.run(['gh', 'api', 'repos/a/b/milestones?state=closed'])\n",
        encoding="utf-8",
    )
    assert milestone_close.check(_evt("Bash", {"command": "python list.py"}, cwd=str(tmp_path))) is None
    assert milestone_close.check(_evt("Bash", {"command": "uv run python missing.py"}, cwd=str(tmp_path))) is None


# --- p3f: a PR number from another worktree ----------------------------------------------


def _reviewed(repo, commit, git, tmp_path, monkeypatch):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    monkeypatch.chdir(repo)
    clean = '{"must_fix": []}'
    (tmp_path / "c.md").write_text("Steelman.\n" + clean + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean + "y" * 220, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    return store.find_repo(repo)


def test_p3f_a_pr_headed_by_another_worktree_s_branch_is_refused(repo, commit, git, tmp_path, monkeypatch):
    from rails import gitutil

    rid = _reviewed(repo, commit, git, tmp_path, monkeypatch)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "armed": False})
    monkeypatch.setattr(gitutil, "gh", lambda cwd, *a, **k: json.dumps({"headRefName": "other-line"}))
    deny = arm_review.check(_evt("Bash", {"command": "gh pr merge 34 --auto --squash"}, cwd=str(repo)))
    assert deny is not None and "PR #34 heads other-line" in deny.reason
    assert store.read_json(rid.leaf_dir / "pr.json")["armed"] is False  # nothing stamped
    # its own PR, by pr.json or by GitHub naming this branch, arms
    assert arm_review.check(_evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo))) is None
    monkeypatch.setattr(gitutil, "gh", lambda cwd, *a, **k: json.dumps({"headRefName": "work"}))
    assert arm_review.check(_evt("Bash", {"command": "gh pr merge 56 --auto"}, cwd=str(repo))) is None


def test_p3f_a_pr_whose_head_cannot_be_read_is_refused(repo, commit, git, tmp_path, monkeypatch):
    from rails import gitutil

    _reviewed(repo, commit, git, tmp_path, monkeypatch)

    def broken(cwd, *a, **k):
        raise gitutil.GitError("gh failed to run")

    monkeypatch.setattr(gitutil, "gh", broken)
    deny = arm_review.check(_evt("Bash", {"command": "gh pr merge 34 --auto"}, cwd=str(repo)))
    assert deny is not None and "could not be read" in deny.reason


# --- p3b: an agent's --accept arms only after the operator names the PR -----------------


def _operator_says(repo, text):
    from rails.dispatch import dispatch

    row = GateRow(name="prompt_words", module="prompt_words", events=["UserPromptSubmit"], mode="enforce")
    evt = Event(name="UserPromptSubmit", payload={"hook_event_name": "UserPromptSubmit", "cwd": str(repo),
                                                  "session_id": "s", "prompt": text})
    return dispatch(evt, [row])


def test_p3b_an_agent_accept_does_not_arm_until_the_operator_names_the_pr(repo, commit, git, tmp_path, monkeypatch):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    monkeypatch.chdir(repo)
    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "armed": False})
    open_fix = '{"reviewed_sha": "abc", "must_fix": [{"what": "drops a blank date", "reproducer": "feed one"}]}\n' + "x" * 220
    (tmp_path / "c.md").write_text("Steelman.\n" + open_fix, encoding="utf-8")
    (tmp_path / "a.md").write_text(open_fix, encoding="utf-8")
    monkeypatch.setenv("CLAUDECODE", "1")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md", accept="the blank date is refused upstream")
    monkeypatch.delenv("CLAUDECODE")
    arm = _evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo))
    deny = arm_review.check(arm)
    assert deny is not None and "accept #12" in deny.reason
    tree12 = git(repo, "rev-parse", "HEAD^{tree}")[:12]
    _operator_says(repo, f"accept #34 {tree12}")  # another PR's word lifts nothing here
    assert arm_review.check(arm) is not None
    _operator_says(repo, "accept #12 0000000")  # another tree's word lifts nothing either
    assert arm_review.check(arm) is not None
    _operator_says(repo, f"accept #12 {tree12}")
    assert arm_review.check(arm) is None


def test_p3b_the_operator_s_own_accept_arms_as_before(repo, commit, git, tmp_path, monkeypatch):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    monkeypatch.chdir(repo)
    store.write_json(store.find_repo(repo).leaf_dir / "pr.json", {"number": 12})
    open_fix = '{"reviewed_sha": "abc", "must_fix": [{"what": "x", "reproducer": "y"}]}\n' + "x" * 220
    (tmp_path / "c.md").write_text("Steelman.\n" + open_fix, encoding="utf-8")
    (tmp_path / "a.md").write_text(open_fix, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md", accept="checked by hand")
    assert arm_review.check(_evt("Bash", {"command": "gh pr merge 12 --auto"}, cwd=str(repo))) is None



# --- apex review round 1 ---------------------------------------------------------------


def test_p2_check_post_disarms_a_push_that_skipped_the_hook(repo, commit, git, monkeypatch):
    from rails import check as check_mod

    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch)
    sha = commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    receipts.write(rid, "lane", sha=sha, lane="checks", exit=0, secs=1)
    monkeypatch.setattr(check_mod, "origin_slug", lambda top: "acme/app")
    monkeypatch.setattr(check_mod, "gh_api", lambda *a, **k: {}, raising=False)
    out = io.StringIO()
    check_mod.post(repo, out=out, rerun=False)
    assert [n for n, _ in disarmed] == [12], out.getvalue()


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("gh pr merge https://github.com/o/r/pull/34 --auto --squash", id="url"),
        pytest.param("gh pr merge '#34' --auto", id="hash"),
    ],
)
def test_p3f_a_pr_url_selector_is_judged_as_its_number(repo, commit, git, tmp_path, monkeypatch, command):
    from rails import gitutil

    rid = _reviewed(repo, commit, git, tmp_path, monkeypatch)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "armed": False})
    monkeypatch.setattr(gitutil, "gh", lambda cwd, *a, **k: json.dumps({"headRefName": "other-line"}))
    deny = arm_review.check(_evt("Bash", {"command": command}, cwd=str(repo)))
    assert deny is not None and "PR #34 heads other-line" in deny.reason


def test_p3b_an_arm_with_no_selector_is_judged_for_this_worktrees_pr(repo, commit, git, tmp_path, monkeypatch):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    monkeypatch.chdir(repo)
    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "armed": False})
    open_fix = '{"reviewed_sha": "abc", "must_fix": [{"what": "x", "reproducer": "y"}]}\n' + "x" * 220
    (tmp_path / "c.md").write_text("Steelman.\n" + open_fix, encoding="utf-8")
    (tmp_path / "a.md").write_text(open_fix, encoding="utf-8")
    monkeypatch.setenv("CLAUDECODE", "1")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md", accept="checked")
    monkeypatch.delenv("CLAUDECODE")
    tree12 = git(repo, "rev-parse", "HEAD^{tree}")[:12]
    _operator_says(repo, f"accept #12 {tree12}")
    assert arm_review.check(_evt("Bash", {"command": "gh pr merge --auto --squash"}, cwd=str(repo))) is None


def test_p3e_an_alias_reaches_arm_review(repo, commit, git, tmp_path, monkeypatch):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    config = tmp_path / "ghconf"
    config.mkdir()
    (config / "config.yml").write_text("aliases:\n    am: pr merge --auto --squash\n", encoding="utf-8")
    monkeypatch.setenv("GH_CONFIG_DIR", str(config))
    deny = arm_review.check(_evt("Bash", {"command": "gh am 12"}, cwd=str(repo)))
    assert deny is not None and "review" in deny.reason


def test_p3e_an_alias_substitutes_its_arguments(tmp_path, monkeypatch):
    from rails.gates.destructive import commands

    config = tmp_path / "ghconf"
    config.mkdir()
    (config / "config.yml").write_text("aliases:\n    pm: pr merge $1 --auto --squash\n", encoding="utf-8")
    monkeypatch.setenv("GH_CONFIG_DIR", str(config))
    found = [t for _, t in commands("gh pm 42", "bash")]
    assert ["gh", "pr", "merge", "42", "--auto", "--squash"] in found, found


def test_p3e_launchers_nested_too_deep_are_refused():
    import shlex

    from rails.gates import destructive

    command = "ls"
    for _ in range(10):
        command = "bash -c " + shlex.quote(command)
    deny = destructive.check(_evt("Bash", {"command": command}))
    assert deny is not None and "nested too deep" in deny.reason


def test_p3e_a_script_s_dash_c_argument_is_not_a_command():
    from rails.gates.destructive import commands

    found = [t for _, t in commands("bash deploy.sh -c 'rm -rf /'", "bash")]
    assert ["rm", "-rf", "/"] not in found, found


def test_p3h_a_heredoc_or_echo_body_is_read_from_the_command(repo, commit, git):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    for command in (
        "gh api graphql --input - <<'EOF'\n{\"query\": \"query { viewer { login } }\"}\nEOF",
        "echo '{\"query\": \"query { viewer { login } }\"}' | gh api graphql --input -",
    ):
        assert arm_review.check(_evt("Bash", {"command": command}, cwd=str(repo))) is None, command


@pytest.mark.parametrize(
    ("name", "text", "command"),
    [
        pytest.param(
            "test_planted.py",
            "x = 'milestones/75 -X PATCH -f state=closed'\n",
            "python -m pytest test_planted.py",
            id="pytest-s-test-file",
        ),
        pytest.param(
            "tests/test_planted.py",
            "x = 'milestones/75 -X PATCH -f state=closed'\n",
            "python tests/test_planted.py",
            id="a-test-file-run-directly",
        ),
        pytest.param(
            "report.py",
            "import requests\nr = requests.get(API + '/milestones', params={'state': 'closed'})\ndata = r.json()\n",
            "python report.py",
            id="a-read-with-a-data-assignment",
        ),
    ],
)
def test_p3j_a_read_or_a_test_file_is_not_a_close(tmp_path, name, text, command):
    (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / name).write_text(text, encoding="utf-8")
    assert milestone_close.check(_evt("Bash", {"command": command}, cwd=str(tmp_path))) is None



# --- apex review round 2 ---------------------------------------------------------------


def test_p2_a_hand_rearm_of_a_disarmed_pr_is_refused(repo, commit, git, tmp_path, monkeypatch):
    """The planted defect for `rearm_disarmed`: arm_review only logs this week, and a hand
    `gh pr merge N --auto` undid the disarm."""
    from rails.gates import rearm_disarmed

    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "state": "OPEN", "armed": False})
    githooks.hold_pr(rid, 12, "abc", "a push no review covers disarmed it")
    deny = rearm_disarmed.check(_evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo)))
    assert deny is not None and "PR #12" in deny.reason
    assert rearm_disarmed.check(_evt("Bash", {"command": "gh pr merge --auto --squash"}, cwd=str(repo))) is not None
    assert rearm_disarmed.check(_evt("Bash", {"command": "gh pr merge 12 --squash"}, cwd=str(repo))) is not None
    githooks.release_pr_hold(rid, 12)
    assert rearm_disarmed.check(_evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo))) is None


def test_p2_a_reviewed_rearm_of_a_disarmed_pr_is_allowed(repo, commit, git, tmp_path, monkeypatch):
    from rails.gates import rearm_disarmed

    rid = _reviewed(repo, commit, git, tmp_path, monkeypatch)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "state": "OPEN", "armed": False, "disarmed_by": "abc"})
    githooks.hold_pr(rid, 12, "abc", "a push no review covers disarmed it")
    arm = _evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo))
    assert rearm_disarmed.check(arm) is None
    assert arm_review.check(arm) is None
    pr = store.read_json(rid.leaf_dir / "pr.json")
    assert pr["armed"] is True and "disarmed_by" not in pr, "an arm past every check clears the mark"
    assert "12" not in githooks.pr_holds(rid)


def test_p2_check_post_judges_the_pushed_head_only(repo, commit, git, monkeypatch):
    from rails import check as check_mod

    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch)
    sha = commit(repo, "src/a.py", "x = 1\n")
    receipts.write(rid, "lane", sha=sha, lane="checks", exit=0, secs=1)
    monkeypatch.setattr(check_mod, "origin_slug", lambda top: "acme/app")
    monkeypatch.setattr(check_mod, "gh_api", lambda *a, **k: {}, raising=False)
    check_mod.post(repo, out=io.StringIO(), rerun=False)
    assert disarmed == [], "an unpushed HEAD is not what the armed PR merges"


def test_p2_check_post_disarms_with_no_lane_receipts(repo, commit, git, monkeypatch):
    from rails import check as check_mod

    _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch)
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    monkeypatch.setattr(check_mod, "origin_slug", lambda top: "acme/app")
    assert check_mod.post(repo, out=io.StringIO(), rerun=False) == 1
    assert [n for n, _ in disarmed] == [12]


def _worktree_with_unreviewed_push(repo, git, tmp_path):
    wt = tmp_path / "feat"
    git(repo, "worktree", "add", "-q", "-b", "feat", str(wt))
    (wt / "src").mkdir(exist_ok=True)
    (wt / "src" / "b.py").write_text("y = 2\n", encoding="utf-8")
    git(wt, "add", "-A")
    git(wt, "commit", "-q", "-m", "code")
    git(wt, "update-ref", "refs/remotes/origin/feat", "HEAD")
    return wt


@pytest.mark.parametrize("spelling", ["native", "git-bash"])
def test_p3f_an_arm_after_cd_judges_the_worktree_it_moved_to(repo, git, tmp_path, spelling):
    import os

    wt = _worktree_with_unreviewed_push(repo, git, tmp_path)
    _pushed(git, repo)  # the folder the session started in is clean and pushed: nothing to judge there
    target = str(wt).replace("\\", "/")
    if spelling == "git-bash":
        if os.name != "nt":
            pytest.skip("a Git Bash drive path is a Windows spelling")
        target = "/" + target[0].lower() + target[2:].replace("\\", "/")
    deny = arm_review.check(_evt("Bash", {"command": f"cd {target} && gh pr merge --auto --squash"}, cwd=str(repo)))
    assert deny is not None and "no review receipt" in deny.reason


def test_p3f_a_branch_selector_for_another_branch_is_refused(repo, git, tmp_path):
    _worktree_with_unreviewed_push(repo, git, tmp_path)
    git(repo, "update-ref", "refs/remotes/origin/work", "HEAD")
    deny = arm_review.check(_evt("Bash", {"command": "gh pr merge feat --auto --squash"}, cwd=str(repo)))
    assert deny is not None and "another branch" in deny.reason


@pytest.mark.parametrize(
    "command",
    [
        pytest.param('echo "arming"; gh api graphql --input - < q.json', id="an-echo-elsewhere"),
        pytest.param("git commit -q --allow-empty -F - <<EOF\nmsg\nEOF\ngh api graphql --input - < q.json", id="a-heredoc-elsewhere"),
    ],
)
def test_p3h_a_file_fed_to_input_is_read_beside_an_inline_body(repo, commit, git, command):
    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    (repo / "q.json").write_text('{"query": "mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }"}', encoding="utf-8")
    deny = arm_review.check(_evt("Bash", {"command": command}, cwd=str(repo)))
    assert deny is not None and "review" in deny.reason, command


_CLOSE = "import subprocess\nsubprocess.run(['gh', 'api', 'repos/a/b/milestones/75', '-X', 'PATCH', '-f', 'state=closed'])\n"


@pytest.mark.parametrize(
    "command",
    ["uv run python close.py", "uv run close.py", "uv run python3 close.py", "uv run --with requests python close.py"],
)
def test_p3j_uv_runs_a_close_script(tmp_path, command):
    (tmp_path / "close.py").write_text(_CLOSE, encoding="utf-8")
    deny = milestone_close.check(_evt("Bash", {"command": command}, cwd=str(tmp_path)))
    assert deny is not None and "close.py" in deny.reason, command


def test_p3j_a_script_handed_to_a_module_is_its_argument(tmp_path):
    (tmp_path / "close.py").write_text(_CLOSE, encoding="utf-8")
    assert milestone_close.check(_evt("Bash", {"command": "python -m mytool close.py"}, cwd=str(tmp_path))) is None


@pytest.mark.parametrize(
    "command",
    [
        pytest.param('bash -lc "git push --force origin master"', id="bash-lc"),
        pytest.param('sh -ec "git push --force origin master"', id="sh-ec"),
        pytest.param('bash -o pipefail -c "git push --force origin master"', id="bash-o-pipefail"),
        pytest.param(
            'powershell -NoProfile -ExecutionPolicy Bypass -Command "git push --force origin master"',
            id="powershell-with-options",
        ),
    ],
)
def test_p3e_shell_options_before_the_command_are_skipped(command):
    from rails.gates import destructive

    assert destructive.check(_evt("Bash", {"command": command})) is not None, command



# --- apex review round 3 ---------------------------------------------------------------


def test_p2_a_held_pr_cannot_be_armed_from_a_folder_that_does_not_hold_it(repo, commit, git, tmp_path, monkeypatch):
    from rails.gates import rearm_disarmed

    rid = _reviewed(repo, commit, git, tmp_path, monkeypatch)
    with store.updating(rid.dir / "state.json", {}) as state:
        state["held_prs"] = {"12": {"sha": "abc", "leaf": "another-worktree", "why": "a push disarmed it"}}
    deny = rearm_disarmed.check(_evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo)))
    assert deny is not None and "does not hold its branch" in deny.reason


def test_p2_a_held_pr_is_judged_on_its_pushed_head(repo, commit, git, tmp_path, monkeypatch):
    """A review of an unpushed fix does not cover the head GitHub would merge."""
    from rails.gates import rearm_disarmed

    rid = _reviewed(repo, commit, git, tmp_path, monkeypatch)
    githooks.hold_pr(rid, 12, "abc", "a push no review covers disarmed it")
    commit(repo, "src/b.py", "y = 2\n")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")
    deny = rearm_disarmed.check(_evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo)))
    assert deny is not None and "Push, then arm" in deny.reason


def test_p2_disable_auto_is_never_a_merge():
    from rails.gates import merge_by_effect

    assert merge_by_effect.check(_evt("Bash", {"command": "gh pr merge 12 --disable-auto"})) is None
    assert merge_by_effect.check(_evt("Bash", {"command": "gh pr merge 12 --admin --disable-auto"})) is not None


def test_p2_the_disarm_reads_the_body_as_utf8(repo, monkeypatch):
    rid = store.find_repo(repo)
    seen: list[dict] = []

    def fake_run(argv, **kw):
        seen.append({"argv": argv[:3], **kw})
        return subprocess.CompletedProcess(argv, 0, stdout='{"body": "Purser fix — stage 2"}', stderr="")

    monkeypatch.setattr(githooks.subprocess, "run", fake_run)
    assert githooks.disarm(rid, 12, "note") is True
    view = next(s for s in seen if s["argv"] == ["gh", "pr", "view"])
    assert view.get("encoding") == "utf-8"
    written = (rid.leaf_dir / "disarm-12.md").read_bytes()
    assert "—".encode("utf-8") in written and b"\r\n" not in written



# --- apex review round 4 ---------------------------------------------------------------


def test_p2_a_hold_is_judged_on_the_held_pr_s_branch(repo, commit, git, tmp_path, monkeypatch):
    """A worktree that switched branch cannot arm its old PR's unreviewed head."""
    from rails import gitutil
    from rails.gates import rearm_disarmed

    commit(repo, "src/a.py", "x = 1\n")
    _pushed(git, repo)
    rid = store.find_repo(repo)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "branch": "work", "state": "OPEN"})
    githooks.hold_pr(rid, 12, git(repo, "rev-parse", "HEAD"), "a push no review covers landed on it", "work")
    git(repo, "checkout", "-q", "-b", "next")
    commit(repo, "src/b.py", "y = 2\n")
    git(repo, "update-ref", "refs/remotes/origin/next", "HEAD")
    monkeypatch.chdir(repo)
    clean = '{"must_fix": []}'
    (tmp_path / "c.md").write_text("Steelman.\n" + clean + "x" * 220, encoding="utf-8")
    (tmp_path / "a.md").write_text(clean + "y" * 220, encoding="utf-8")
    review.record(repo, tmp_path / "c.md", tmp_path / "a.md")

    def offline(*a, **k):
        raise gitutil.GitError("offline")

    monkeypatch.setattr(gitutil, "gh", offline)
    arm = _evt("Bash", {"command": "gh pr merge 12 --auto --squash"}, cwd=str(repo))
    assert arm_review.check(arm) is not None, "pr.json names #12 for work, and this is next"
    deny = rearm_disarmed.check(arm)
    assert deny is not None and "Check out work" in deny.reason


def test_p2_an_unreviewed_push_to_an_unarmed_pr_holds_it(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    disarmed = _armed(monkeypatch, number=None)
    store.write_json(rid.leaf_dir / "pr.json", {"number": 12, "branch": "work", "state": "OPEN", "armed": False})
    sha = commit(repo, "src/a.py", "x = 1\n")
    msgs = githooks.disarm_after_push(["origin", "u"], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid)
    assert disarmed == [] and githooks.pr_holds(rid)["12"]["branch"] == "work"
    assert any("held off auto-merge" in m for m in msgs), msgs


def test_p2_a_disarm_that_fails_still_holds(repo, commit, monkeypatch):
    rid = _pushable(monkeypatch, repo, commit, shadow_review=True)
    monkeypatch.setattr(githooks, "armed_pr", lambda repo, branch: 12)
    monkeypatch.setattr(githooks, "disarm", lambda repo, n, note: False)
    sha = commit(repo, "src/a.py", "x = 1\n")
    msgs = githooks.disarm_after_push(["origin", "u"], [f"refs/heads/work {sha} refs/heads/work {ZERO}"], rid)
    assert "12" in githooks.pr_holds(rid)
    assert any("could not be turned off" in m for m in msgs), msgs


@pytest.mark.parametrize(
    ("shell", "template", "expect"),
    [
        pytest.param("Bash", 'WT={wt}; cd "$WT" && gh pr merge --auto --squash', "cannot follow", id="cd-to-a-variable"),
        pytest.param("PowerShell", "Push-Location {wt}; gh pr merge --auto --squash", "PR #12", id="push-location"),
        pytest.param("PowerShell", "Set-Location -Path {wt}; gh pr merge --auto --squash", "PR #12", id="set-location-path"),
        pytest.param("Bash", "gh pr merge feat --squash", "does not hold its branch", id="a-branch-selector"),
        pytest.param("Bash", "cd {wt} && gh pr merge --squash", "PR #12", id="a-direct-merge-after-cd"),
    ],
)
def test_p2_a_held_pr_is_found_however_the_command_reaches_it(repo, git, tmp_path, shell, template, expect):
    from rails.gates import rearm_disarmed

    wt = _worktree_with_unreviewed_push(repo, git, tmp_path)
    _pushed(git, repo)
    githooks.hold_pr(store.find_repo(wt), 12, "abc", "a push no review covers landed on it", "feat")
    command = template.format(wt=str(wt).replace("\\", "/"))
    deny = rearm_disarmed.check(_evt(shell, {"command": command}, cwd=str(repo)))
    assert deny is not None and expect in deny.reason, command


def test_p2_a_push_rails_refuses_disarms_nothing(repo, commit, monkeypatch):
    """Drives `main`: a push rails refused never reaches the disarm."""
    _pushable(monkeypatch, repo, commit, shadow_review=True)
    called: list[object] = []
    monkeypatch.setattr(githooks, "pre_push", lambda *a: (1, ["refused"]))
    monkeypatch.setattr(githooks, "run_chained", lambda *a: 0)
    monkeypatch.setattr(githooks, "disarm_after_push", lambda *a: called.append(a) or [])
    monkeypatch.chdir(repo)
    monkeypatch.setattr(githooks.sys, "stdin", io.StringIO(""))
    assert githooks.main(["x", "pre-push", "origin", "u"]) == 1
    assert called == []
