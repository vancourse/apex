"""The acceptance gate's own tests — false positives first, on purpose.

This gate reads acceptance criteria out of real issue bodies, and the ways it can be
*wrong* all look like the ways it can be *right*: an empty criteria list is what a
prose-acceptance issue correctly produces AND what a broken extractor produces. So
the silent cases come first and outnumber the findings, and each extraction rule has
a test that fails when that rule **alone** is removed. Those are marked `PLANTED:`
and were verified by deleting the line and watching this file go red.

The issue bodies below are the shape GitHub actually renders an **issue form** into —
`### <field label>` per field — because that is what apex's `work-item.yml` produces
and it is the reason the "stop at the next heading" rule exists at all.

Run with `pytest templates/gates/tests`.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

_HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = _HERE.parent / "acceptance_check.py"


def _load():
    spec = importlib.util.spec_from_file_location("acceptance_check", SCRIPT)
    assert spec is not None and spec.loader is not None, SCRIPT
    module = importlib.util.module_from_spec(spec)
    sys.modules["acceptance_check"] = module
    spec.loader.exec_module(module)
    return module


check = _load()

#: A rendered work-item form. `Production caller` is a bullet list, and it sits
#: directly after the acceptance field — which is the whole reason extraction stops
#: at the next heading.
FORM_ISSUE = """\
### Kind

Capability — new behaviour

### Done when

- the golden test compares both lanes and asserts the rows match
- `ingest --dry-run` exits 0 on the customer export

### Production caller

- apps/ingest/loader.py
- apps/api/routes/upload.py

### Effort

M
"""

PROSE_ISSUE = """\
### Done when

The importer should handle the customer's export without falling over, and we
should feel reasonably confident about the edge cases before we ship it.

### Effort

S
"""


# ── false positives first: what must NOT be a finding ─────────────────────────


def test_prose_acceptance_yields_no_criteria():
    """PLANTED: the tempting "fall back to any bullets in the body" rule makes this
    issue contribute nothing here but makes plenty of real issues contribute their
    `Touches` list. Prose acceptance is common, and failing it fires the gate on
    correct work — which teaches people to reach for `--admin`."""
    assert check.acceptance_criteria(PROSE_ISSUE) == []


def test_prose_acceptance_produces_no_findings():
    assert check.check("Closes #7", {7: check.acceptance_criteria(PROSE_ISSUE)}) == []


def test_an_issue_with_no_acceptance_section_at_all_is_not_a_finding():
    assert check.acceptance_criteria("### Kind\n\nDocs\n") == []


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            "- the loader crashes on quoted newlines\n- only on the customer export\n",
            id="a hand-written issue that is just a bullet list",
        ),
        pytest.param(
            "- apps/ingest/loader.py\n- apps/api/routes/upload.py\n\n### Kind\n\nDocs\n",
            id="bullets before the first heading",
        ),
    ],
)
def test_no_acceptance_heading_means_no_criteria_even_when_the_issue_has_bullets(body):
    """PLANTED: fall back to "any bullets in the body" when the acceptance heading is
    absent, and an issue's incidental bullets — file paths, symptoms — become criteria
    the PR must tick off.

    Both shapes were needed. Mutation testing killed two earlier versions of this test:
    every other no-criteria case in this file had no bullets at all, and then the
    replacement put its bullets *after* a heading, where the extractor stops on the
    first line either way. Only bullets reachable from line 0 tell the two
    implementations apart.
    """
    assert check.acceptance_criteria(body) == []


def test_a_pr_that_closes_nothing_is_not_a_finding():
    assert check.closed_issue_numbers("Refactors the loader. No issue.") == []


def test_a_body_merely_mentioning_an_issue_is_not_a_close():
    """`#12` alone links; it does not close. Treating it as a close would demand a
    checklist from a PR that only referenced a neighbour."""
    assert check.closed_issue_numbers("Related to #12, see also #13.") == []


def test_all_criteria_ticked_is_clean():
    body = (
        "Closes #7\n\n"
        "## Acceptance — #7\n\n"
        "- [x] the golden test compares both lanes and asserts the rows match\n"
        "- [x] `ingest --dry-run` exits 0 on the customer export\n"
    )
    assert check.check(body, {7: check.acceptance_criteria(FORM_ISSUE)}) == []


def test_reformatting_while_ticking_is_not_a_finding():
    """PLANTED: drop the normalisation and every one of these fails the author for
    doing nothing wrong — dropped backticks, added bold, a fixed typo in punctuation,
    a changed dash. Comparison is over alphanumerics only, for exactly this."""
    criteria = check.acceptance_criteria(FORM_ISSUE)
    body = (
        "Closes #7\n\n"
        "- [x] The golden test compares both lanes and asserts the rows match.\n"
        "- [x] **ingest --dry-run** exits 0 on the customer export\n"
    )
    assert check.check(body, {7: criteria}) == []


def test_a_criterion_ticked_anywhere_in_the_body_counts():
    """The checklist block is a convenience, not a required location. Binding ticks
    to a heading would fail a body that answered every criterion in its own prose
    structure."""
    body = "Closes #7\n\n## Test plan\n\n- [x] `ingest --dry-run` exits 0 on the customer export\n"
    assert (
        check.check(body, {7: ["`ingest --dry-run` exits 0 on the customer export"]})
        == []
    )


# ── the extraction rules ──────────────────────────────────────────────────────


def test_extraction_stops_at_the_next_heading():
    """PLANTED: remove the `break` on the next heading and the gate demands the PR
    tick off `apps/ingest/loader.py` — file paths that were never acceptance
    criteria. This is the single most likely way this gate becomes hated."""
    criteria = check.acceptance_criteria(FORM_ISSUE)
    assert len(criteria) == 2
    assert not any("loader.py" in c for c in criteria)


def test_extraction_finds_the_heading_under_several_spellings():
    for heading in (
        "### Done when",
        "## Acceptance",
        "## Acceptance criteria",
        "**Done when**",
    ):
        body = f"{heading}\n\n- a thing happens\n\n### Effort\n\nS\n"
        assert check.acceptance_criteria(body) == ["a thing happens"], heading


def test_checkbox_markers_are_stripped_from_the_criterion():
    """An issue may write its own criteria as boxes. `- [ ] x` and `- x` must extract
    to the same text, or the PR's tick can never match the issue's phrasing."""
    boxed = check.acceptance_criteria("### Done when\n\n- [ ] a thing happens\n")
    plain = check.acceptance_criteria("### Done when\n\n- a thing happens\n")
    assert boxed == plain == ["a thing happens"]


def test_every_github_closing_keyword_is_recognised():
    """PLANTED: shrink this to `Closes` and the gate goes silent on a PR that really
    is closing an issue. Silence here is indistinguishable from "this PR closes
    nothing", so a partial keyword set is a gate that stops firing without saying so.
    Includes `Resolved` and `Fixed`, which are outside the brief's own three."""
    for keyword in (
        "Close",
        "Closes",
        "Closed",
        "Fix",
        "Fixes",
        "Fixed",
        "Resolve",
        "Resolves",
        "Resolved",
    ):
        assert check.closed_issue_numbers(f"{keyword} #7") == [7], keyword


def test_multiple_issues_are_collected_in_order_without_duplicates():
    assert check.closed_issue_numbers("Closes #9\nFixes #3\nCloses #9") == [9, 3]


# ── the findings ──────────────────────────────────────────────────────────────


def test_an_unticked_criterion_is_a_finding():
    body = "Closes #7\n\n- [ ] the golden test compares both lanes and asserts the rows match\n"
    found = check.check(body, {7: check.acceptance_criteria(FORM_ISSUE)})
    assert [f.problem for f in found] == ["not ticked", "missing from the PR body"]


def test_a_missing_criterion_is_a_finding():
    found = check.check("Closes #7\n\nNothing here.", {7: ["a thing happens"]})
    assert len(found) == 1 and found[0].problem == "missing from the PR body"


def test_the_finding_names_the_issue_and_offers_the_honest_out():
    """ "Tick it if it is true, or say why it was the wrong criterion" is the whole
    point. A gate that only offers "tick it" is a gate that manufactures ticks."""
    text = check.check("Closes #7", {7: ["a thing happens"]})[0].annotation()
    assert text.startswith("::error::#7 acceptance")
    assert "wrong criterion" in text


# ── the checklist it ships, which must satisfy the check it came from ─────────


def test_the_printed_checklist_satisfies_the_gate_once_ticked():
    """The load-bearing property of `--print-checklist`: pasting it and ticking must
    clear the check. If the emitted bullet text differed from the criterion by so
    much as a prepended issue number, the paste would normalise differently and the
    gate would fail the person who did exactly what it asked."""
    criteria = {7: check.acceptance_criteria(FORM_ISSUE)}
    block = check.checklist(criteria)
    body = "Closes #7\n\n" + block.replace("- [ ]", "- [x]")
    assert check.check(body, criteria) == []


def test_the_checklist_puts_the_issue_reference_outside_the_bullet():
    block = check.checklist({7: ["a thing happens"]})
    assert "#7" in block
    assert "- [ ] a thing happens" in block


def test_the_checklist_skips_issues_with_no_bullet_criteria():
    assert check.checklist({7: []}) == ""


# ── reads that did not work must raise ────────────────────────────────────────


def test_gh_issue_body_raises_when_gh_itself_fails(monkeypatch):
    """PLANTED: return "" on a non-zero `gh issue view` and a broken token becomes a
    silent pass on every PR — permanently green, and nothing says so.

    This drives the real `gh_issue_body` with a failing subprocess rather than
    injecting a raising stub. Found by mutation testing: every other test here
    replaced the function, so removing its raise changed nothing that was checked.
    """

    class Failed:
        returncode, stdout, stderr = 1, "", "gh: not authenticated"

    monkeypatch.setattr(check.subprocess, "run", lambda *a, **k: Failed())
    with pytest.raises(check.ForgeReadError) as exc:
        check.gh_issue_body(7)
    assert "not authenticated" in str(exc.value)


def test_gh_issue_body_raises_when_gh_is_absent(monkeypatch):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(check.subprocess, "run", missing)
    with pytest.raises(check.ForgeReadError):
        check.gh_issue_body(7)


def test_an_unreadable_issue_propagates_out_of_collect():
    """`collect` must not swallow it into "this issue has no criteria"."""

    def broken(_number):
        raise check.ForgeReadError("gh not authenticated")

    with pytest.raises(check.ForgeReadError):
        check.collect("Closes #7", broken)


def test_the_cli_reports_a_failed_read_as_exit_2(monkeypatch):
    monkeypatch.setattr(
        check,
        "gh_issue_body",
        lambda n, timeout=60: (_ for _ in ()).throw(check.ForgeReadError("boom")),
    )
    monkeypatch.setenv("PR_BODY", "Closes #7")
    assert check.main([]) == 2


def test_the_cli_exits_1_on_findings_and_0_when_clean(monkeypatch):
    monkeypatch.setattr(check, "gh_issue_body", lambda n, timeout=60: FORM_ISSUE)
    monkeypatch.setenv("PR_BODY", "Closes #7")
    assert check.main([]) == 1
    monkeypatch.setenv(
        "PR_BODY",
        "Closes #7\n"
        "- [x] the golden test compares both lanes and asserts the rows match\n"
        "- [x] `ingest --dry-run` exits 0 on the customer export\n",
    )
    assert check.main([]) == 0


def test_an_absent_pr_body_is_exit_2_not_a_pass(monkeypatch):
    """An empty `$PR_BODY` means the workflow is misconfigured. Exiting 0 there is a
    gate that appears to run on every PR and checks none of them."""
    monkeypatch.delenv("PR_BODY", raising=False)
    assert check.main([]) == 2
