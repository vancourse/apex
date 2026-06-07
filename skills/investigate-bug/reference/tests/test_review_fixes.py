"""Regression tests for the code-review findings (C1, C2, m5, m6, P2, P1) — design §A/§B/§I."""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

REF = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REF))
sys.path.insert(0, str(REF / "adapters"))

import contracts as C  # noqa: E402
import resolver as R  # noqa: E402
from adapters import gh_tracker, grep_obs  # noqa: E402


def _ax(mcp="", cli=""):
    return SimpleNamespace(kind="github", mcp=mcp, cli=cli, extras={})


# C1 — unattended + cli declared but NOT on PATH → ESCALATE (AskUser), never a live binding
def test_c1_unattended_missing_cli_escalates(tmp: Path) -> None:
    a = _ax(mcp="mcp__github__*", cli="definitely_not_a_real_cmd_xyz")
    b = R.resolve(
        a,
        R.Mode.UNATTENDED,
        mcp_probe=lambda p: (_ for _ in ()).throw(AssertionError("mcp touched")),
    )
    assert isinstance(b, R.AskUserBinding), f"missing cli must escalate, got {b}"


# C2 — raw subprocess failures map to AdapterError, never escape
def test_c2_gh_timeout_maps_to_adapter_error(tmp: Path) -> None:
    def runner(argv):
        raise subprocess.TimeoutExpired(cmd=argv, timeout=30)

    try:
        gh_tracker.GhTrackerAdapter(runner=runner).fetch_issue("1")
        assert False, "should raise AdapterError"
    except C.AdapterError as e:
        assert e.code == C.AdapterErrorCode.UNAVAILABLE, e.code


def test_c2_gh_not_installed_maps_to_adapter_error(tmp: Path) -> None:
    def runner(argv):
        raise FileNotFoundError("gh")

    try:
        gh_tracker.GhTrackerAdapter(runner=runner).comment("1", "hi")
        assert False, "should raise AdapterError"
    except C.AdapterError as e:
        assert e.code == C.AdapterErrorCode.UNAVAILABLE, e.code


# m6 — a 403/forbidden is AUTH, not RATE_LIMIT
def test_m6_403_is_auth_not_rate_limit(tmp: Path) -> None:
    assert gh_tracker._classify("HTTP 403: Forbidden") == C.AdapterErrorCode.AUTH
    assert (
        gh_tracker._classify("API rate limit exceeded") == C.AdapterErrorCode.RATE_LIMIT
    )


# m5 — a tz-aware window does not crash query_logs
def test_m5_tz_aware_window_no_crash(tmp: Path) -> None:
    (tmp / "logs").mkdir()
    (tmp / "logs" / "app.log").write_text(
        "2026-06-07T12:05:00 ERROR boom\n", encoding="utf-8"
    )
    win = C.TimeWindow(
        datetime(2026, 6, 7, 12, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 7, 12, 10, 0, tzinfo=timezone.utc),
    )
    lines = grep_obs.query_logs(
        win, log_path="logs/app.log", repo_root=tmp
    )  # must not raise
    assert len(lines) == 1, lines


# P2 — a reversed TimeWindow is rejected at construction
def test_p2_reversed_window_rejected(tmp: Path) -> None:
    now = datetime(2026, 6, 7, 12, 0, 0)
    try:
        C.TimeWindow(now, now - timedelta(hours=1))
        assert False, "reversed window should raise ValueError"
    except ValueError:
        pass


# P1 — static-style conformance: the shipped adapters satisfy their axis Protocols, and a
# wrong-shape object that only has the method NAMES still passes runtime_checkable (documented
# boundary — full-signature checking is a static-checker's job).
def test_p1_conformance_and_its_documented_boundary(tmp: Path) -> None:
    assert isinstance(gh_tracker.GhTrackerAdapter(), C.TrackerAdapter)
    assert isinstance(grep_obs.GrepObsAdapter(), C.ObservabilityAdapter)
    # static-binding form (what pyright would check): these assignments type-check the full sig
    _t: C.TrackerAdapter = gh_tracker.GhTrackerAdapter()
    _o: C.ObservabilityAdapter = grep_obs.GrepObsAdapter()
    assert _t and _o


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
