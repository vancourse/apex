"""PR-A2 tests — detect-stack detectors + conflict rule + profile builder (design §D).

Standalone-runnable: `python tests/test_detect.py`. Mirrors S1 (deps→kind), S2/S2.1
(AC2b no-drop), S3 (AC7 un-inferable→prompt), S10/U7 (conflicting signals), malformed-
manifest resilience, and the vcs URL parse.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detect as D  # noqa: E402
import profile as P  # noqa: E402


def test_s1_deps_infers_observability_kind(tmp: Path) -> None:
    (tmp / "package.json").write_text(
        json.dumps({"dependencies": {"@datadog/browser-rum": "^5"}}), encoding="utf-8"
    )
    assert D.detect_deps(tmp)["observability_kind"] == "datadog"
    (tmp / "package.json").write_text(
        json.dumps({"dependencies": {"@sentry/node": "^7"}}), encoding="utf-8"
    )
    assert D.detect_deps(tmp)["observability_kind"] == "sentry"


def test_malformed_manifest_is_a_gap_not_a_crash(tmp: Path) -> None:
    (tmp / "package.json").write_text("{ this is not json", encoding="utf-8")
    res = D.detect_deps(tmp)  # must not raise
    assert res["observability_kind"] is None
    assert any("package.json" in g for g in res["gaps"]), res["gaps"]


def test_s10_conflicting_signals_never_silently_picked(tmp: Path) -> None:
    kind, note = D.resolve_tracker_kind("github", {"gitlab"})
    assert kind == "" and note and "conflicting" in note, (kind, note)
    # single signal resolves cleanly
    assert D.resolve_tracker_kind("github", {"github"}) == ("github", None)
    # no signal → un-inferable, no fabrication
    assert D.resolve_tracker_kind(None, set()) == ("", None)


def test_detect_ci_finds_each_host(tmp: Path) -> None:
    (tmp / ".github" / "workflows").mkdir(parents=True)
    (tmp / ".github" / "workflows" / "ci.yml").write_text("on: push", encoding="utf-8")
    assert D.detect_ci(tmp) == {"github"}
    (tmp / ".gitlab-ci.yml").write_text("stages: [test]", encoding="utf-8")
    assert D.detect_ci(tmp) == {"github", "gitlab"}


def test_parse_remote_url(tmp: Path) -> None:
    for url, host, repo in [
        ("git@github.com:vancourse/apex.git", "github", "vancourse/apex"),
        ("https://github.com/vancourse/apex", "github", "vancourse/apex"),
        ("git@gitlab.com:team/proj.git", "gitlab", "team/proj"),
    ]:
        r = D.parse_remote_url(url)
        assert r.get("host") == host and r.get("repo") == repo, (url, r)


def test_s3_uninferable_field_is_prompted_not_guessed(tmp: Path) -> None:
    # empty repo (no deps, no CI, no git remote in tmp) → tracker.kind un-inferable → prompted
    prof, prompts = D.build_profile(tmp, mcp_prefixes=[])
    assert "tracker.kind" in prompts, prompts
    assert prof["tracker"]["kind"] == "", prof[
        "tracker"
    ]  # honest-empty, never a default
    # console obs with no log_path → prompted
    assert any("log_path" in p for p in prompts), prompts


def test_s2_1_available_cli_binding_recorded_not_dropped(tmp: Path) -> None:
    # grep is on PATH in any POSIX test env → AC2b: it must be recorded, not dropped
    prof, _ = D.build_profile(tmp, mcp_prefixes=[])
    assert prof["observability"]["cli"] == "grep", prof["observability"]


def test_build_profile_output_validates(tmp: Path) -> None:
    # the assembled dict (minus meta keys) must pass the PR-A1 value-shape allowlist
    prof, _ = D.build_profile(tmp, mcp_prefixes=[])
    clean = {
        k: {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
        for k, v in prof.items()
        if isinstance(v, dict)
    }
    errs = P.validate_profile_dict(clean, tmp)
    assert errs == [], errs


def test_s2_1_conflict_axis_prompts_and_marks(tmp: Path) -> None:
    (tmp / ".github" / "workflows").mkdir(parents=True)
    (tmp / ".github" / "workflows" / "ci.yml").write_text("on: push", encoding="utf-8")
    (tmp / ".gitlab-ci.yml").write_text("stages: [test]", encoding="utf-8")
    prof, prompts = D.build_profile(tmp, mcp_prefixes=[])
    # build_profile uses detect_vcs (no git in tmp → host None) + CI {github,gitlab} → conflict
    assert prof["tracker"]["kind"] == "", prof["tracker"]
    assert any("conflict" in p.lower() for p in prompts), prompts
    assert "_conflict" in prof["tracker"] and "TODO" in prof["tracker"]["_conflict"]


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
