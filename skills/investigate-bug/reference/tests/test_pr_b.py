"""PR-B tests — resolver (S5.1/S5.2), adapters (S8), conformance (S9). Design §A/§B.

Standalone-runnable: `python tests/test_pr_b.py`. Consolidates the impl-plan's
test_resolver / test_adapters / test_conformance for this build.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

REF = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REF))
sys.path.insert(0, str(REF / "adapters"))

import contracts as C  # noqa: E402
import resolver as R  # noqa: E402
from adapters import gh_tracker, grep_obs  # noqa: E402


def _ax(mcp: str = "", cli: str = "") -> SimpleNamespace:
    return SimpleNamespace(kind="github", mcp=mcp, cli=cli, extras={})


def _boom(_prefix: str) -> bool:
    raise AssertionError("mcp_probe must NOT be consulted in unattended mode (S5.2)")


# ── S5.2 — the structural guarantee: MCP-only is impossible (the de-risking bet) ──
def test_s5_2_unattended_never_touches_mcp(tmp: Path) -> None:
    a = _ax(mcp="mcp__github__*", cli="")  # mcp present, NO cli
    b = R.resolve(
        a, R.Mode.UNATTENDED, mcp_probe=_boom
    )  # _boom raises if mcp consulted
    assert isinstance(b, R.AskUserBinding), b  # never McpBinding — escalates instead


def test_s5_2_unattended_uses_cli(tmp: Path) -> None:
    a = _ax(mcp="mcp__github__*", cli="gh")
    b = R.resolve(a, R.Mode.UNATTENDED, mcp_probe=_boom)
    assert isinstance(b, R.CliBinding) and b.command == "gh", b


# ── S5.1 — interactive ladder: MCP-first → CLI fallback → ask-user ────────────
def test_s5_1_interactive_mcp_first(tmp: Path) -> None:
    b = R.resolve(
        _ax(mcp="mcp__github__*", cli="gh"),
        R.Mode.INTERACTIVE,
        mcp_probe=lambda p: True,
    )
    assert isinstance(b, R.McpBinding) and b.prefix == "mcp__github__*", b


def test_s5_1_interactive_cli_fallback(tmp: Path) -> None:
    # mcp declared but not connected → falls to cli (grep is on PATH in any POSIX env)
    b = R.resolve(
        _ax(mcp="mcp__x__*", cli="grep"), R.Mode.INTERACTIVE, mcp_probe=lambda p: False
    )
    assert isinstance(b, R.CliBinding) and b.command == "grep", b


def test_s5_1_interactive_ask_user_last(tmp: Path) -> None:
    b = R.resolve(
        _ax(mcp="", cli="definitely_not_a_real_cmd_xyz"),
        R.Mode.INTERACTIVE,
        mcp_probe=lambda p: False,
    )
    # cli declared-but-not-on-PATH in interactive → ask-user (real terminal, §B.3)
    assert isinstance(b, R.AskUserBinding), b


# ── S8 — adapter verbs return normalized shapes (producer-side normalization) ──
def test_s8_gh_fetch_issue_normalizes(tmp: Path) -> None:
    fake_json = (
        '{"number": 123, "title": "boom", "body": "null deref", '
        '"labels": [{"name": "bug"}, {"name": "sev1"}], '
        '"comments": [{"body": "repro: click X"}], "url": "https://gh/owner/repo/issues/123"}'
    )
    runner = lambda argv: SimpleNamespace(returncode=0, stdout=fake_json, stderr="")
    issue = gh_tracker.GhTrackerAdapter(runner=runner).fetch_issue("123")
    assert isinstance(issue, C.NormalizedIssue)
    assert (
        issue.id == "123" and issue.title == "boom" and issue.labels == ["bug", "sev1"]
    )
    assert issue.comments == ["repro: click X"] and issue.url.endswith("/123")


def test_s8_gh_error_maps_to_adapter_error(tmp: Path) -> None:
    runner = lambda argv: SimpleNamespace(
        returncode=1, stdout="", stderr="gh: issue not found"
    )
    try:
        gh_tracker.GhTrackerAdapter(runner=runner).fetch_issue("999")
        assert False, "should have raised AdapterError"
    except C.AdapterError as e:
        assert e.code == C.AdapterErrorCode.NOT_FOUND, e.code


def test_s8_grep_query_logs_window_and_literal(tmp: Path) -> None:
    (tmp / "logs").mkdir()
    log = tmp / "logs" / "app.log"
    log.write_text(
        "2026-06-07T12:00:00 INFO start\n"
        "2026-06-07T12:05:00 ERROR req=abc boom\n"
        "2026-06-07T13:30:00 ERROR req=xyz late\n"
        "no-timestamp junk line\n",
        encoding="utf-8",
    )
    win = C.TimeWindow(datetime(2026, 6, 7, 12, 0, 0), datetime(2026, 6, 7, 12, 10, 0))
    lines = grep_obs.query_logs(
        win, query="req=abc", log_path="logs/app.log", repo_root=tmp
    )
    assert len(lines) == 1 and lines[0].text.endswith("boom"), lines
    assert all(isinstance(x, C.LogLine) for x in lines)
    # window excludes the 13:30 line even without a query
    allwin = grep_obs.query_logs(win, log_path="logs/app.log", repo_root=tmp)
    assert len(allwin) == 2, allwin  # the two 12:0x lines; the 13:30 and junk excluded


def test_s8_grep_query_is_literal_not_regex(tmp: Path) -> None:
    # a regex-special query must match literally (no ReDoS passthrough, F2)
    (tmp / "logs").mkdir()
    (tmp / "logs" / "app.log").write_text(
        "2026-06-07T12:00:00 cost=(a+)+ literal\n", encoding="utf-8"
    )
    win = C.TimeWindow(datetime(2026, 6, 7, 11, 0, 0), datetime(2026, 6, 7, 13, 0, 0))
    lines = grep_obs.query_logs(
        win, query="(a+)+", log_path="logs/app.log", repo_root=tmp
    )
    assert len(lines) == 1, lines  # matched the literal "(a+)+", did not regex-explode


def test_grep_confinement_rejects_escape(tmp: Path) -> None:
    try:
        grep_obs.query_logs(
            C.TimeWindow(datetime(2026, 6, 7), datetime(2026, 6, 8)),
            log_path="../../etc/passwd",
            repo_root=tmp,
        )
        assert False, "should reject path escaping the repo root"
    except C.AdapterError as e:
        assert e.code == C.AdapterErrorCode.MALFORMED, e.code


# ── S9 — stub conformance: a new adapter drops in with zero investigate-bug diff ──
def test_s9_conformance(tmp: Path) -> None:
    class GoodTracker:
        def fetch_issue(self, ref): ...
        def comment(self, ref, body): ...

    class BadTracker:  # missing comment
        def fetch_issue(self, ref): ...

    assert isinstance(GoodTracker(), C.TrackerAdapter)
    assert not isinstance(BadTracker(), C.TrackerAdapter)
    # the SHIPPED adapters conform to their axis Protocols
    assert isinstance(gh_tracker.GhTrackerAdapter(), C.TrackerAdapter)
    assert isinstance(grep_obs.GrepObsAdapter(), C.ObservabilityAdapter)


def _run() -> int:
    import tempfile

    tests = [
        v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)
    ]
    failed = 0
    for t in tests:
        with tempfile.TemporaryDirectory() as d:
            try:
                t(Path(d))
                print(f"  PASS {t.__name__}")
            except AssertionError as e:
                print(f"  FAIL {t.__name__}: {e}")
                failed += 1
            except Exception as e:  # noqa: BLE001
                print(f"  ERROR {t.__name__}: {type(e).__name__}: {e}")
                failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


try:
    import pytest

    @pytest.fixture
    def tmp(tmp_path):  # noqa: D103
        return tmp_path
except ImportError:
    pass


if __name__ == "__main__":
    raise SystemExit(_run())
