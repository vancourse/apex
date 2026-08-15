"""The session-narrative redirect's tests — the exemptions first, on purpose.

This hook exists because of a measurement — of 568 documents, **16 stayed maintained
and 383 were written once** — and the 16 are the reason its exemption list is
load-bearing rather than a politeness. Every one of the maintained documents was a
living registry, and a name-shaped rule catches those too: `HANDOFF.md` is both the
name of the genre that fails and the name of the registry that works. **A hook that
nags the 3% that work in order to stop the 67% that do not has it backwards**, so the
silent cases come first here and the flagging cases follow.

Per this suite's standing rule, the denylist and the allowlist each get a case from
**outside** their own list — a narrative document the patterns do not name, and a
living registry the exemptions do not name. Both must behave the way the rule's
stated limits say they will, and both are documented rather than fixed: widening a
name-shaped rule with guesses is how it starts firing on the registries.

The hook is driven over a subprocess with JSON on stdin, because the wire protocol is
the contract. Run with ``python -m pytest hooks/tests/ -q``.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import uuid

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2]
HOOK = PLUGIN_ROOT / "hooks" / "session_output_gate.py"


@pytest.fixture
def repo(tmp_path: pathlib.Path) -> pathlib.Path:
    """A target repo. `.git` is the only structural requirement."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "docs").mkdir()
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


def _write(path: object, tool: str = "Write") -> str:
    return _run(
        json.dumps(
            {
                "session_id": f"test-{uuid.uuid4()}",
                "tool_name": tool,
                "tool_input": {"file_path": str(path)},
            }
        )
    )


def _context(raw: str) -> str:
    emitted = json.loads(raw)["hookSpecificOutput"]
    assert emitted["hookEventName"] == "PreToolUse"
    return emitted["additionalContext"]


# ── silence, which is the answer most of the time ─────────────────────────────


@pytest.mark.parametrize(
    "relative",
    [
        "docs/ingest/design.md",
        "docs/ingest/prd.md",
        "docs/adr/0012-storage-engine.md",
        "docs/architecture.md",
        "docs/runbook.md",
    ],
)
def test_ordinary_documents_are_silent(repo: pathlib.Path, relative: str) -> None:
    """The normal case. Every one of these is a document meant to be re-read."""
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    assert _write(target) == ""


@pytest.mark.parametrize("name", ["GAPS.md", "DECISION_LOG.md", "HANDOFF.md"])
def test_the_named_living_registries_are_exempt(repo: pathlib.Path, name: str) -> None:
    """PLANTED: drop `EXEMPT_NAMES` and `HANDOFF.md` — one of the 16 documents that
    actually stayed maintained — gets nagged on creation by a hook whose entire
    argument is that the other 383 were not worth writing."""
    assert _write(repo / "docs" / name) == ""


def test_the_name_exemption_is_scoped_to_the_top_of_docs(repo: pathlib.Path) -> None:
    """PLANTED: drop the depth scope and every per-feature `handoff.md` inherits the
    standing register's exemption. A standing handoff register lives at a known place
    and everyone knows where it is; `docs/ingest/r2/handoff.md` is a note about one
    week of one feature, which is the genre this hook is about."""
    target = repo / "docs" / "ingest" / "r2" / "handoff.md"
    target.parent.mkdir(parents=True)
    assert "SESSION NARRATIVE" in _context(_write(target))


@pytest.mark.parametrize("directory", ["lessons", "templates", "adr"])
def test_exempt_directories_are_silent(repo: pathlib.Path, directory: str) -> None:
    """PLANTED: drop `EXEMPT_DIRS` and `docs/lessons/2026-08-15-audit.md` is flagged —
    a lessons directory is a living registry whose *contents* are the point."""
    target = repo / "docs" / directory / "2026-08-15-audit.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    assert _write(target) == ""


def test_a_living_registry_outside_the_exemption_list(repo: pathlib.Path) -> None:
    """The allowlist's case from outside itself. `RISK_REGISTER.md` is exactly the
    genre `EXEMPT_NAMES` protects and is not in it — and it is silent anyway, because
    the patterns are what decide and its name is not narrative. That is the design:
    the exemptions exist to rescue registries the *patterns* would otherwise catch,
    not to enumerate every good document in the world."""
    assert _write(repo / "docs" / "RISK_REGISTER.md") == ""


def test_a_narrative_document_outside_the_pattern_list(repo: pathlib.Path) -> None:
    """The denylist's case from outside itself, and an honest limit rather than a
    bug. `2026-08-15-postmortem.md` is the same write-once genre and is not flagged,
    because the rule reads names and this author did not name it after the genre. A
    name-shaped rule cannot be complete; widening it with guesses is how it starts
    firing on the registries above."""
    assert _write(repo / "docs" / "2026-08-15-postmortem.md") == ""


@pytest.mark.parametrize("relative", ["notes/triage-round-3.md", "2026-08-15-sweep.md"])
def test_a_narrative_name_outside_docs_is_silent(
    repo: pathlib.Path, relative: str
) -> None:
    """PLANTED: drop the `docs/` scope and the hook fires on a handoff note anywhere in
    the tree — including one a session was explicitly asked to write.

    Neither name is in `EXEMPT_NAMES`, and that is deliberate. Mutation testing showed
    the first version of this test used `notes/handoff.md`, which survived the mutation
    because the name exemption caught it on the way past — the test passed for a reason
    that had nothing to do with the guard it claimed to cover.
    """
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    assert _write(target) == ""


def test_a_non_markdown_file_is_silent(repo: pathlib.Path) -> None:
    assert _write(repo / "docs" / "sweep.json") == ""


def test_an_existing_file_is_silent(repo: pathlib.Path) -> None:
    """PLANTED: drop the `.exists()` test and the hook fires on every overwrite of a
    legacy file. Nagging every touch teaches a session to skim past the hook, and by
    the time it fires on something worth reading it has already been trained away."""
    target = repo / "docs" / "handoff-2026-08-15.md"
    target.write_text("already here", encoding="utf-8")
    assert _write(target) == ""


def test_it_does_not_fire_on_edit(repo: pathlib.Path) -> None:
    """Registered on `Write` only. This pins the hook's own guard as well, so a
    mis-registration in `hooks.json` cannot be masked by the script accepting Edit."""
    assert _write(repo / "docs" / "sweep.md", tool="Edit") == ""


def test_a_file_outside_any_repo_is_silent(tmp_path: pathlib.Path) -> None:
    assert _write(tmp_path / "docs" / "handoff.md") == ""


# ── the flagging cases ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "name",
    [
        "handoff-ingest.md",
        "hand-off.md",
        "2026-08-14-sweep.md",
        "readiness-report.md",
        "triage-round-3.md",
        "autonomous-session-notes.md",
        "session-summary.md",
        "completion-log.md",
    ],
)
def test_the_narrative_genre_is_flagged(repo: pathlib.Path, name: str) -> None:
    context = _context(_write(repo / "docs" / name))
    assert "SESSION NARRATIVE" in context


@pytest.mark.parametrize(
    "name",
    [
        "2026-08-15-inventory.md",
        "20260815-audit.md",
        "freeze-2026-08.md",
        "2026-08-15-log.md",
    ],
)
def test_dated_kinds_are_flagged(repo: pathlib.Path, name: str) -> None:
    assert "SESSION NARRATIVE" in _context(_write(repo / "docs" / name))


@pytest.mark.parametrize("name", ["inventory.md", "audit.md", "changelog.md"])
def test_the_same_kinds_undated_are_silent(repo: pathlib.Path, name: str) -> None:
    """PLANTED: drop the date requirement and `inventory.md` — a document somebody
    maintains — is flagged alongside `2026-08-15-inventory.md`, which never is. The
    date in the name is the tell that a document is a snapshot of a moment rather
    than a statement about the system."""
    assert _write(repo / "docs" / name) == ""


def test_it_is_flagged_at_any_depth_under_docs(repo: pathlib.Path) -> None:
    target = repo / "docs" / "ingest" / "r2" / "2026-08-15-sweep.md"
    target.parent.mkdir(parents=True)
    assert "SESSION NARRATIVE" in _context(_write(target))


def test_the_message_names_the_alternative_and_the_measurement(
    repo: pathlib.Path,
) -> None:
    """The redirect is the whole point. A hook that says "don't" without saying
    "here instead" is one the reader argues with rather than follows."""
    context = _context(_write(repo / "docs" / "readiness-report.md"))
    assert "PR body" in context
    assert "568" in context and "383" in context
    assert "Advisory" in context


def test_it_says_the_same_thing_only_once_per_path(repo: pathlib.Path) -> None:
    """Enough to inform, not enough to nag."""
    session = f"test-{uuid.uuid4()}"
    payload = json.dumps(
        {
            "session_id": session,
            "tool_name": "Write",
            "tool_input": {"file_path": str(repo / "docs" / "triage-round-3.md")},
        }
    )
    assert _run(payload) != ""
    assert _run(payload) == ""


# ── the fail-open contract ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "not json",
        "[]",
        "{}",
        '{"tool_name": "Write"}',
        '{"tool_name": "Write", "tool_input": {}}',
    ],
)
def test_malformed_input_exits_zero_silently(payload: str) -> None:
    """A hook that raises blocks the tool call. Every unexpected condition exits 0."""
    assert _run(payload) == ""
