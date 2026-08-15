"""The artifact-template router's gate.

``hooks/artifact_templates.py`` routes an artifact being authored to the template
that shapes it — the doc skeletons on ``Write``, and the ``.github/`` templates on
``gh pr create`` / ``gh issue create``.

The ``gh`` half is the one worth explaining. GitHub applies ``.github/`` templates
only in its web UI; ``gh pr create --body-file …`` supplies the body directly and
skips them. Since that is how an agent files nearly every PR and issue, a repo's
templates are decorative for the actor filing most of its artifacts. These tests
pin that the check fires there, and that it names the *missing* sections rather
than reciting the template back.

**Why these tests exist at all.** A hook is uniquely easy to break silently: it
has no importers, it produces no diff, and it is fail-open by construction — so a
dead hook looks exactly like a healthy one with nothing to say. A dropped
``import json`` during a refactor did precisely that once, and only a suite like
this caught it.

**Why the fixture repo.** apex ships these hooks to *other* repos, so the contract
under test is "what the hook does to a target repo", not "what it does to apex".
Every test therefore drives a synthetic repo built in ``tmp_path`` from apex's own
shipped templates, over a subprocess with JSON on stdin — the wire protocol is the
contract.

Run with: ``python -m pytest hooks/tests/ -q``
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import uuid

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = PLUGIN_ROOT / "hooks" / "artifact_templates.py"
HOOKS_JSON = PLUGIN_ROOT / "hooks" / "hooks.json"
TEMPLATES = PLUGIN_ROOT / "templates"


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A target repo: a git marker plus the `.github/` templates apex ships.

    `.git` is the only structural requirement — the hook keys repo discovery on it
    rather than on any ecosystem's build manifest, so that it works in a repo of
    any language.
    """
    (tmp_path / ".git").mkdir()
    github = tmp_path / ".github"
    (github / "ISSUE_TEMPLATE").mkdir(parents=True)
    shutil.copy(
        TEMPLATES / "github" / "pull_request_template.md",
        github / "pull_request_template.md",
    )
    for form in ("work-item.yml", "defect.yml"):
        shutil.copy(TEMPLATES / "github" / form, github / "ISSUE_TEMPLATE" / form)
    return tmp_path


def _run(payload: str) -> str:
    result = subprocess.run(
        [sys.executable, str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"the hook must always exit 0 — a non-zero exit blocks the tool call.\n"
        f"stderr: {result.stderr}"
    )
    return result.stdout.strip()


def _write(path: object, session: str | None = None) -> str:
    return _run(
        json.dumps(
            {
                "session_id": session or f"test-{uuid.uuid4()}",
                "tool_name": "Write",
                "tool_input": {"file_path": str(path)},
            }
        )
    )


def _bash(command: str, cwd: object, session: str | None = None) -> str:
    return _run(
        json.dumps(
            {
                "session_id": session or f"test-{uuid.uuid4()}",
                "cwd": str(cwd),
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        )
    )


def _context(raw: str) -> str:
    emitted = json.loads(raw)["hookSpecificOutput"]
    assert emitted["hookEventName"] == "PreToolUse"
    return emitted["additionalContext"]


# --------------------------------------------------------------------------- wiring


def test_every_doc_rule_points_at_a_shipped_template() -> None:
    """A rule naming a missing skeleton makes the hook silently useless for that type."""
    source = HOOK.read_text(encoding="utf-8")
    referenced = {
        line.split('"')[1]
        for line in source.splitlines()
        if "template=" in line and '"' in line
    }
    doc_templates = {name for name in referenced if "/" not in name}
    assert doc_templates, "no doc template names parsed out of DOC_RULES"
    for name in doc_templates:
        assert (TEMPLATES / name).is_file(), f"rule points at missing template: {name}"


def test_every_gh_rule_template_is_shipped_for_installation() -> None:
    """The `.github/` paths are target-repo-relative, and apex ships a copy of each."""
    source = HOOK.read_text(encoding="utf-8")
    referenced = {
        line.split('"')[1]
        for line in source.splitlines()
        if "template=" in line and '"' in line
    }
    for relative in {name for name in referenced if name.startswith(".github/")}:
        assert (TEMPLATES / "github" / pathlib.Path(relative).name).is_file(), (
            f"no shipped copy of {relative}"
        )


def test_hook_is_wired_for_both_write_and_bash() -> None:
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    wired = {
        entry.get("matcher")
        for entry in config["hooks"]["PreToolUse"]
        for hook in entry["hooks"]
        if "artifact_templates.py" in hook["command"]
    }
    assert wired == {"Write", "Bash"}, f"expected both matchers wired, got {wired}"


# ----------------------------------------------------------------------- doc routing


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        ("docs/some-feature/prd.md", "PRD"),
        ("docs/some-feature/design.md", "DESIGN"),
        ("docs/some-feature/impl-plan.md", "IMPL-PLAN"),
        ("docs/some-feature/recon.md", "RECON"),
        ("docs/adr/0099-a-new-decision.md", "ADR"),
    ],
)
def test_routes_a_new_artifact_to_its_template(
    repo: pathlib.Path, relative: str, expected: str
) -> None:
    context = _context(_write(repo / relative))
    assert expected in context.splitlines()[0]


def test_injects_the_template_body_not_just_its_name(repo: pathlib.Path) -> None:
    context = _context(_write(repo / "docs/some-feature/prd.md"))
    skeleton = (TEMPLATES / "prd.md").read_text(encoding="utf-8")
    for heading in ("## Scenarios", "## Out of scope", "## Freeze record"):
        assert heading in skeleton and heading in context


def test_a_repo_template_wins_over_the_shipped_one(repo: pathlib.Path) -> None:
    """Repo first, plugin second — a repo that has decided its own shape keeps it."""
    local = repo / "docs" / "templates"
    local.mkdir(parents=True)
    (local / "prd.md").write_text("## Local Shape Only\n", encoding="utf-8")

    context = _context(_write(repo / "docs/some-feature/prd.md"))
    assert "## Local Shape Only" in context
    assert "docs/templates/prd.md" in context, "the message must name the source"
    assert "## Scenarios" not in context, "the shipped skeleton must not leak through"


@pytest.mark.parametrize(
    ("relative", "why"),
    [
        ("docs/adr/README.md", "the ADR index is not an ADR"),
        ("docs/adr/DECISION_LOG.md", "the decision log is not an ADR"),
        ("docs/some-feature/notes.md", "an unrecognised doc has no decided shape"),
        ("docs/adr/subdir/0099-nested.md", "ADRs are flat under docs/adr"),
        ("src/x.py", "source files are not authored artifacts"),
        ("README.md", "outside docs/"),
    ],
)
def test_stays_quiet(repo: pathlib.Path, relative: str, why: str) -> None:
    assert not _write(repo / relative), f"expected silence: {why}"


def test_existing_artifact_is_not_re_templated(repo: pathlib.Path) -> None:
    existing = repo / "docs" / "some-feature" / "prd.md"
    existing.parent.mkdir(parents=True)
    existing.write_text("# already here\n", encoding="utf-8")
    assert not _write(existing), "an existing file is a rewrite, not authoring"


# ------------------------------------------------------------------------ gh routing


def test_flags_the_sections_a_pr_body_is_missing(repo: pathlib.Path) -> None:
    body = repo / "body.md"
    body.write_text("## What this does\n\nA thing.\n", encoding="utf-8")
    context = _context(_bash(f'gh pr create --title x --body-file "{body}"', cwd=repo))

    assert "Test plan" in context, "a missing section must be named"
    assert "Risk note" in context
    # The one section that IS present must not be reported as missing.
    missing_block = context.split("does NOT have")[1]
    assert "What this does" not in missing_block


def test_confirms_a_complete_body_instead_of_nagging(repo: pathlib.Path) -> None:
    template = (repo / ".github" / "pull_request_template.md").read_text(
        encoding="utf-8"
    )
    body = repo / "body.md"
    body.write_text(
        "\n".join(
            line for line in template.splitlines() if line.strip().startswith("#")
        ),
        encoding="utf-8",
    )
    context = _context(_bash(f'gh pr create --body-file "{body}"', cwd=repo))
    assert "carries every section" in context
    assert "does NOT have" not in context


def test_checks_issue_bodies_against_the_form_fields(repo: pathlib.Path) -> None:
    body = repo / "issue.md"
    body.write_text("### Kind\n\nInfra / CI\n", encoding="utf-8")
    context = _context(_bash(f'gh issue create --body-file "{body}"', cwd=repo))
    for field in ("What", "Why now", "Done when", "Production caller"):
        assert field in context, f"form field {field!r} should be reported missing"


# ------------------------------------------------------------------- issue-form routing
#
# `.github/ISSUE_TEMPLATE/` holds more than one form. Checking every issue against
# `work-item.yml` reported a correctly-formed defect as missing every work-item
# field — a confident false positive, which is the failure mode that teaches a
# reader to ignore the check entirely.

_DEFECT_BODY = """### Where observed
CI
### Severity
Degraded or cosmetic
### What happened
A thing.
### What should have happened
Another thing.
### Reproduction
Steps.
### Consecutive runs (intermittent only)
3 fail / 5 runs, isolated.
### Regression guard
tests/ingest/test_loader.py::test_quoted_newlines
### Blast radius
Small.
### Which gate should have caught this?
None exists.
"""


def _defect_body(repo: pathlib.Path) -> pathlib.Path:
    body = repo / "defect.md"
    body.write_text(_DEFECT_BODY, encoding="utf-8")
    return body


@pytest.mark.parametrize(
    "flags, why",
    [
        ("--label defect", "the label the form declares"),
        ("-l defect", "the short flag"),
        ("--label=defect", "the joined form"),
        ('--title "[defect] a bug"', "the title prefix the form seeds"),
        ("--template defect.yml", "gh's own explicit selector"),
        ("--template defect", "the selector without its extension"),
    ],
)
def test_a_defect_is_checked_against_the_defect_form(
    repo: pathlib.Path, flags: str, why: str
) -> None:
    """Every signal that says "this is a defect" must route to defect.yml.

    The body carries every defect field and none of work-item's, so a wrong route is
    unmissable: it reports every section missing instead of none.
    """
    body = _defect_body(repo)
    context = _context(_bash(f'gh issue create {flags} --body-file "{body}"', cwd=repo))

    assert "defect.yml" in context, f"{why} should select the defect form"
    assert "work-item.yml" not in context
    assert "carries every section" in context, (
        "a complete defect body must not be reported as missing anything"
    )


def test_an_issue_with_no_routing_signal_falls_back_and_says_so(
    repo: pathlib.Path,
) -> None:
    """The fallback is fine; a *silent* fallback is not.

    An unrouted issue is checked against work-item, which is the primary lane —
    but the message has to name that choice, or a defect filed without a label
    reads as malformed rather than as mis-routed.
    """
    body = _defect_body(repo)
    context = _context(
        _bash(f'gh issue create --title plain --body-file "{body}"', cwd=repo)
    )

    assert "work-item.yml" in context
    assert "default" in context, "the fallback must be named as a fallback"
    assert "defect.yml" in context, "and it must point at the forms it did not pick"


def test_every_check_names_the_template_it_used(repo: pathlib.Path) -> None:
    """Applies to PRs too — the line is what makes a wrong route diagnosable."""
    body = repo / "b.md"
    body.write_text("## What this does\n", encoding="utf-8")
    for command, expected in (
        (f'gh pr create --body-file "{body}"', "pull_request_template.md"),
        (f'gh issue create --body-file "{body}"', "work-item.yml"),
    ):
        context = _context(_bash(command, cwd=repo))
        assert "Checked against" in context, f"no template named for: {command}"
        assert expected in context


def test_a_new_issue_form_is_routed_without_editing_the_hook(
    tmp_path: pathlib.Path,
) -> None:
    """The property itself, driven end to end rather than grepped for.

    A form declares its own `labels:`/`title:` and the hook reads them at run time,
    so a form this hook has never heard of must route correctly with no code change.
    That is the guarantee that stops the next form from silently being checked
    against work-item's fields.

    Deliberately not a "no filename appears in the source" assertion — that proxy
    fires on prose and on doc examples, and a test that cries wolf about a comment
    is the same disease as a check that cries wolf about a correct body.
    """
    (tmp_path / ".git").mkdir()
    forms = tmp_path / ".github" / "ISSUE_TEMPLATE"
    forms.mkdir(parents=True)
    (forms / "work-item.yml").write_text(
        'name: Work item\nlabels: ["work-item"]\nbody:\n'
        "  - type: input\n    attributes:\n      label: What\n",
        encoding="utf-8",
    )
    (forms / "spike.yml").write_text(
        'name: Spike\ntitle: "[spike] "\nlabels: ["spike"]\nbody:\n'
        "  - type: input\n    attributes:\n      label: Question to answer\n"
        "  - type: input\n    attributes:\n      label: Timebox\n",
        encoding="utf-8",
    )
    body = tmp_path / "b.md"
    body.write_text("### Question to answer\n\nIs it fast?\n", encoding="utf-8")

    context = _context(
        _bash(f'gh issue create --label spike --body-file "{body}"', cwd=tmp_path)
    )

    assert "spike.yml" in context, "a form the hook has never seen must still route"
    assert "work-item.yml" not in context
    # Checked against the spike form's OWN fields: Timebox is missing, and
    # work-item's "What" is not what this body is measured against.
    assert "Timebox" in context


def test_an_unreadable_body_is_not_reported_as_missing_everything(
    repo: pathlib.Path,
) -> None:
    """A hook sees the command before the shell expands it.

    `--body-file "$SP/body.md"` arrives with `$SP` unexpanded and cannot be opened.
    Treating that as an empty body produced a confident "you are missing all 7
    sections" against a body that had all 7 — a false positive that trains the
    reader to ignore the check, which is worse than not checking.
    """
    context = _context(_bash('gh issue create --body-file "$SP/issue.md"', cwd=repo))

    assert "Could not read the body file" in context
    assert "NOT a report that anything is missing" in context
    assert "does NOT have" not in context, "must not claim sections are absent"
    # It should still say what to check for.
    assert "Done when" in context


def test_a_missing_file_path_is_also_treated_as_unknown(repo: pathlib.Path) -> None:
    absent = repo / "never-written.md"
    context = _context(_bash(f'gh pr create --body-file "{absent}"', cwd=repo))
    assert "Could not read the body file" in context


def test_inline_body_is_checked_too(repo: pathlib.Path) -> None:
    context = _context(
        _bash('gh pr create --title x --body "just a sentence"', cwd=repo)
    )
    assert "does NOT have" in context


def test_quiet_when_no_body_is_supplied(repo: pathlib.Path) -> None:
    """Without a body flag gh pre-fills the template itself — nothing to warn about."""
    assert not _bash("gh pr create --title x --web", cwd=repo)


@pytest.mark.parametrize(
    "command",
    [
        "gh pr list",
        "gh pr view 321",
        "gh issue list --state open",
        "git commit -m 'gh pr create'",
        "python -m pytest -q",
    ],
)
def test_ignores_unrelated_commands(repo: pathlib.Path, command: str) -> None:
    assert not _bash(command, cwd=repo)


@pytest.mark.parametrize(
    ("command", "why"),
    [
        (
            "git commit -F - <<'EOF'\nfix: found by dogfooding `gh issue create`\nEOF",
            "a commit MESSAGE mentioning the command is not the command, and that "
            "commit's own -F is not a PR body",
        ),
        (
            'echo "run gh pr create --body-file notes.md"',
            "prose inside echo is not an invocation",
        ),
        (
            "grep -rn 'gh issue create' docs/",
            "a search pattern is not an invocation",
        ),
    ],
)
def test_does_not_fire_on_commands_that_merely_mention_gh(
    repo: pathlib.Path, command: str, why: str
) -> None:
    """The first version substring-matched the raw command and fired on all three.

    It then read `git commit -F -`'s flag as a body file, failed to open it, and
    reported every section missing — against a commit that had no body at all.
    """
    assert not _bash(command, cwd=repo), f"expected silence: {why}"


def test_still_fires_on_a_real_invocation_after_another_command(
    repo: pathlib.Path,
) -> None:
    """Scoping to the invocation must not lose the genuine case."""
    assert _bash('git add -A && gh pr create --body "thin"', cwd=repo)


# ------------------------------------------------------------------ safety contract


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "{}",
        '{"tool_name":"Write"}',
        '{"tool_name":"Bash"}',
        '{"tool_name":"Bash","tool_input":{"command":""}}',
        '{"tool_name":"Write","tool_input":{"file_path":""}}',
    ],
)
def test_fails_open_on_a_malformed_payload(payload: str) -> None:
    assert not _run(payload)


def test_payload_is_ascii_on_the_wire(repo: pathlib.Path) -> None:
    raw = _write(repo / "docs/some-feature/design.md")
    assert raw.isascii(), "cp1252 stdout on Windows would lose a non-ASCII payload"


def test_warns_once_per_artifact_per_session(repo: pathlib.Path) -> None:
    session = f"dedupe-{uuid.uuid4()}"
    first = _write(repo / "docs/feature-a/prd.md", session=session)
    again = _write(repo / "docs/feature-a/prd.md", session=session)
    other = _write(repo / "docs/feature-b/prd.md", session=session)

    assert first
    assert not again, "the same artifact twice in one session should stay quiet"
    assert other, "a different feature's PRD is a different artifact"
