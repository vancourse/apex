"""The PR-body gate's own tests.

Two properties matter, and the second is the one that decides whether the gate
survives contact with real work:

1. It fails a body that skips what its diff calls for.
2. **It does not fire on legitimate PRs.** A blocking check that flags correct work
   gets routed around with `gh pr merge --admin`, which skips every other required
   check too — so a false positive here is worse than no gate at all.

The requirement set is derived from the diff, so most tests here are really tests of
that derivation: a typo fix must require almost nothing, and a new capability under a
configured custody path must require nearly everything.

The third block tests the configuration seam. `SENSITIVE_PREFIXES` is per-repository
by nature, so it is read from `[tool.apex]` rather than shipped as a guess, and the
**unconfigured case must stay silent** — an empty config that started demanding Risk
notes would fire on every repository that installed the gate without reading it.

Run with `pytest templates/gates/tests` (or from wherever these were installed);
the module is loaded by path, so the layout only has to keep the tests one directory
below the scripts.
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = _HERE.parent / "pr_body_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("pr_body_check", SCRIPT)
    assert spec is not None and spec.loader is not None, SCRIPT
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_body_check"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()

changed_paths = gate.changed_paths
check = gate.check
is_answered = gate.is_answered
is_shipped_source = gate.is_shipped_source
required_sections = gate.required_sections
sections = gate.sections

#: A stand-in for the repo's own `.github/pull_request_template.md`. Inline rather
#: than read from disk so the suite runs identically wherever these files land — the
#: placeholder rule is about *shape*, and this carries the shape.
TEMPLATE = """
## What this does

<!-- One paragraph. The change, not the changelog. -->

## Why this shape

<!-- The alternative you rejected and the reason. -->

### Reuse verdict

| New capability | Existing primitive checked | Verdict |
| --- | --- | --- |
|  |  |  |

## Wiring

<!-- Who imports this from a deployed process? -->

## Test plan

<!-- Which layer each test sits at. Paste the run. -->

## Risk note

<!-- Blast radius and rollback. -->
"""

FULL = """
## What this does
Adds a thing.
## Why this shape
The alternative was worse because of X.
## Reuse verdict
| parse rows | `record-store` | EXTEND |
## Wiring
Imported by the API service at boot.
## Test plan
Ran the suite; 12 new tests.
## Risk note
Blast radius is one endpoint; rollback is a revert.
"""

CONFIGURED_PREFIXES = ("auth/", "secrets/", "deploy/", ".github/workflows/")
CONFIGURED_SUBSTRINGS = ("migration", "credential")


@pytest.fixture
def configured(monkeypatch):
    """The gate as a repo that filled in `[tool.apex]` would see it."""
    monkeypatch.setattr(gate, "SENSITIVE_PREFIXES", CONFIGURED_PREFIXES)
    monkeypatch.setattr(gate, "SENSITIVE_SUBSTRINGS", CONFIGURED_SUBSTRINGS)


def _diff(*entries: tuple[str, str]) -> list[str]:
    return [f"{status}\t{path}\n" for status, path in entries]


# --------------------------------------------------------------- diff derivation


def test_a_docs_only_change_requires_only_the_universal_two() -> None:
    every, added = changed_paths(_diff(("M", "docs/adr/0001-x.md")))
    assert set(required_sections(every, added)) == {"What this does", "Why this shape"}


def test_touching_shipped_source_adds_tests_and_wiring() -> None:
    every, added = changed_paths(_diff(("M", "src/pipeline/run.py")))
    assert set(required_sections(every, added)) == {
        "What this does",
        "Why this shape",
        "Test plan",
        "Wiring",
    }


def test_adding_shipped_source_also_demands_a_reuse_verdict() -> None:
    """The server-side half of the reuse question — a hook asks, this refuses."""
    every, added = changed_paths(_diff(("A", "src/scoring/engine.py")))
    assert "Reuse verdict" in required_sections(every, added)


def test_a_custody_path_demands_a_risk_note(configured) -> None:
    every, added = changed_paths(_diff(("M", "secrets/vault.py")))
    assert "Risk note" in required_sections(every, added)


def test_a_test_only_change_does_not_demand_wiring() -> None:
    """Tests are not shipped source; a test-only PR has no wiring story to tell."""
    every, added = changed_paths(_diff(("A", "pipeline/tests/test_run.py")))
    assert set(required_sections(every, added)) == {"What this does", "Why this shape"}


def test_an_empty_diff_requires_nothing() -> None:
    assert required_sections([], []) == {}


@pytest.mark.parametrize(
    ("path", "shipped"),
    [
        ("src/session.py", True),
        ("ui/src/Button.tsx", True),
        ("internal/server/handler.go", True),
        ("src/auth/tests/test_session.py", False),
        ("web/src/x.test.ts", False),
        ("pkg/store/store_test.go", False),
        ("conftest.py", False),
        ("docs/adr/0001.md", False),
        ("uv.lock", False),
    ],
)
def test_shipped_source_classification(path: str, shipped: bool) -> None:
    assert is_shipped_source(path) is shipped


@pytest.mark.parametrize(
    "path",
    [
        "secrets/store.py",
        "auth/session.py",
        ".github/workflows/ci.yml",
        "deploy/Dockerfile",
        "services/api/migrations/003_add.sql",
        "src/account/credential_rotation.py",
    ],
)
def test_configured_sensitive_paths(configured, path: str) -> None:
    assert gate.is_sensitive(path)


def test_ordinary_paths_are_not_sensitive(configured) -> None:
    assert not gate.is_sensitive("src/reporting/cashflow.py")


def test_renames_count_as_added() -> None:
    every, added = changed_paths(["R100\told/x.py\tnew/x.py\n"])
    assert added == ["new/x.py"] and every == ["new/x.py"]


# ----------------------------------------------------------- sensitive-path config


def test_an_unconfigured_repo_never_demands_a_risk_note(tmp_path) -> None:
    """The fail-soft contract, stated as a test.

    A gate that guessed which trees are sensitive would fire on correct work in a
    repository it knows nothing about — the exact false positive that teaches people
    to reach for `--admin`. Silence is the safe default; the other three rules still
    apply.
    """
    assert gate.sensitive_patterns(tmp_path) == ((), ())


def test_pyproject_tool_apex_supplies_the_patterns(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.apex]\n"
        'sensitive_path_prefixes = ["auth/", "secrets/"]\n'
        'sensitive_path_substrings = ["Migration"]\n',
        encoding="utf-8",
    )
    prefixes, substrings = gate.sensitive_patterns(tmp_path)
    assert prefixes == ("auth/", "secrets/")
    assert substrings == ("migration",), "substrings are matched case-insensitively"


def test_a_dedicated_apex_toml_works_with_bare_keys(tmp_path) -> None:
    (tmp_path / ".apex.toml").write_text(
        'sensitive_path_prefixes = ["crypto/"]\n', encoding="utf-8"
    )
    assert gate.sensitive_patterns(tmp_path) == (("crypto/",), ())


def test_a_dedicated_apex_toml_also_accepts_the_pyproject_table_header(tmp_path) -> None:
    """So a block copied out of pyproject.toml keeps working when it is moved."""
    (tmp_path / ".apex.toml").write_text(
        '[tool.apex]\nsensitive_path_prefixes = ["crypto/"]\n', encoding="utf-8"
    )
    assert gate.sensitive_patterns(tmp_path) == (("crypto/",), ())


def test_pyproject_wins_over_the_dedicated_file(tmp_path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[tool.apex]\nsensitive_path_prefixes = ["auth/"]\n', encoding="utf-8"
    )
    (tmp_path / ".apex.toml").write_text(
        'sensitive_path_prefixes = ["ignored/"]\n', encoding="utf-8"
    )
    assert gate.sensitive_patterns(tmp_path)[0] == ("auth/",)


def test_a_malformed_config_is_silence_not_a_crash(tmp_path) -> None:
    """Somebody else's broken TOML is already failing their build; this check
    exploding on top of it adds noise, not signal."""
    (tmp_path / "pyproject.toml").write_text("[tool.apex\nbroken =", encoding="utf-8")
    assert gate.sensitive_patterns(tmp_path) == ((), ())


def test_non_string_entries_are_dropped_rather_than_crashing(tmp_path) -> None:
    (tmp_path / ".apex.toml").write_text(
        'sensitive_path_prefixes = ["auth/", 3, ""]\n', encoding="utf-8"
    )
    assert gate.sensitive_patterns(tmp_path)[0] == ("auth/",)


# ------------------------------------------------------------------- body checks


def test_a_complete_body_passes() -> None:
    every, added = changed_paths(_diff(("A", "src/reporting/new.py")))
    assert check(FULL, every, added, TEMPLATE) == []


def test_a_missing_section_is_reported_with_its_reason() -> None:
    every, added = changed_paths(_diff(("M", "src/pipeline/run.py")))
    body = "## What this does\nA thing.\n## Why this shape\nBecause.\n"
    findings = check(body, every, added, TEMPLATE)

    assert {f.section for f in findings} == {"Test plan", "Wiring"}
    assert "shipped source" in findings[0].reason
    assert "::error::" in findings[0].annotation()


def test_pasting_the_template_back_does_not_count_as_answering() -> None:
    """The obvious way to satisfy a section checker is to paste the skeleton."""
    every, added = changed_paths(_diff(("M", "docs/x.md")))
    findings = check(TEMPLATE, every, added, TEMPLATE)
    assert {f.section for f in findings} == {"What this does", "Why this shape"}
    assert all("placeholder" in f.problem for f in findings)


def test_a_heading_with_only_a_comment_is_not_answered() -> None:
    every, added = changed_paths(_diff(("M", "docs/x.md")))
    body = "## What this does\n<!-- describe it -->\n## Why this shape\nBecause X.\n"
    assert [f.section for f in check(body, every, added, TEMPLATE)] == [
        "What this does"
    ]


def test_an_unfilled_table_row_is_not_answered() -> None:
    assert not is_answered("|  |  |  |", "")
    assert is_answered("| parse rows | `record-store` | EXTEND |", "")


def test_heading_level_and_case_do_not_matter() -> None:
    every, added = changed_paths(_diff(("M", "docs/x.md")))
    body = "### WHAT THIS DOES\nA thing.\n#### why this shape:\nBecause.\n"
    assert check(body, every, added, TEMPLATE) == []


def test_sections_parses_content_under_each_heading() -> None:
    parsed = sections("## One\nalpha\n## Two\nbeta\ngamma\n")
    assert parsed == {"one": "alpha", "two": "beta\ngamma"}


# ------------------------------------------------------------------ end to end


def _run(
    body: str, diff: list[str], author_type: str = "User"
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input="".join(diff),
        capture_output=True,
        text=True,
        env={
            "PR_BODY": body,
            "PR_AUTHOR_TYPE": author_type,
            "PATH": "",
            "SYSTEMROOT": "",
        },
        timeout=60,
    )


def test_exit_codes_end_to_end() -> None:
    good = _run(FULL, _diff(("M", "src/pipeline/run.py")))
    assert good.returncode == 0, good.stdout + good.stderr

    bad = _run("## What this does\nA thing.\n", _diff(("M", "src/pipeline/run.py")))
    assert bad.returncode == 1
    assert "::error::" in bad.stdout


def test_the_skip_marker_needs_a_reason_and_is_logged() -> None:
    body = "nothing here\n<!-- pr-body-check: skip — release automation, body is generated -->"
    result = _run(body, _diff(("M", "src/pipeline/run.py")))
    assert result.returncode == 0
    assert "::notice::" in result.stdout
    assert "release automation" in result.stdout, "the reason must reach the log"


def test_a_bare_skip_marker_without_a_reason_does_not_excuse_the_body() -> None:
    result = _run("<!-- pr-body-check: skip -->", _diff(("M", "src/pipeline/run.py")))
    assert result.returncode == 1, "a skip with no stated reason is not a skip"


def test_documenting_the_skip_marker_does_not_annotate_a_passing_body() -> None:
    """Prose that merely *describes* the marker is not an attempt to use it.

    The script's own help text spells the marker out, so a PR describing the escape
    hatch once carried an `::error::` annotation on an otherwise green check.
    Mentioning a thing is not invoking it.
    """
    body = FULL + "\nThe escape hatch is `<!-- pr-body-check: skip — <why> -->`.\n"
    result = _run(body, _diff(("M", "src/pipeline/run.py")))

    assert result.returncode == 0
    assert "::error::" not in result.stdout, "a passing check must not carry an error"
    assert "::notice::" in result.stdout, (
        "but it should still say the marker was ignored"
    )


def test_bot_authors_are_exempt() -> None:
    """A dependency bot cannot write a reuse verdict, and blocking it helps nobody."""
    result = _run("Bumps x from 1 to 2.", _diff(("M", "uv.lock")), author_type="Bot")
    assert result.returncode == 0


def test_an_empty_body_fails_rather_than_passing_vacuously() -> None:
    result = _run("", _diff(("M", "src/pipeline/run.py")))
    assert result.returncode == 1


# --------------------------------------------------------------- wiring to CI


def _shipped_template() -> pathlib.Path | None:
    """The repo's real PR template, wherever this file was installed."""
    for candidate in (
        _HERE.parents[1] / "github" / "pull_request_template.md",
        _HERE.parents[1] / ".github" / "pull_request_template.md",
        gate.REPO_ROOT / ".github" / "pull_request_template.md",
    ):
        if candidate.is_file():
            return candidate
    return None


def _workflow_invoking_the_checker() -> pathlib.Path | None:
    workflows = gate.REPO_ROOT / ".github" / "workflows"
    if not workflows.is_dir():
        return None
    for path in sorted(workflows.glob("*.y*ml")):
        if "pr_body_check.py" in path.read_text(encoding="utf-8"):
            return path
    return None


def test_the_checker_is_actually_invoked_by_a_workflow() -> None:
    """A gate job nothing runs is decorative — the exact defect class this line of
    work exists to catch, applied to itself. Skipped where the gate has not been
    installed into a repository yet (the plugin's own vendored copy)."""
    workflow = _workflow_invoking_the_checker()
    if workflow is None:
        pytest.skip("no CI workflow invokes pr_body_check.py here")
    text = workflow.read_text(encoding="utf-8")
    assert "pull_request" in text, "the job must run on pull_request events"
    assert "PR_BODY" in text, "the job must pass the body in as an env var"


def test_the_template_carries_every_section_the_gate_can_require() -> None:
    """If the template is edited to drop a heading, the gate would demand something
    no contributor could copy from it."""
    template = _shipped_template()
    if template is None:
        pytest.skip("no pull_request_template.md found next to this installation")
    headings = set(sections(template.read_text(encoding="utf-8")))
    for name in (
        "What this does",
        "Why this shape",
        "Wiring",
        "Test plan",
        "Risk note",
        "Reuse verdict",
    ):
        assert name.lower() in headings, f"template lost the '{name}' section"
