"""Regression tests for the code-review findings (B1, M2, H2, m4) — design §C/§D."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detect as D  # noqa: E402
import profile as P  # noqa: E402

VALID = {
    "tracker": {"kind": "github", "mcp": "mcp__github__*", "cli": "gh"},
    "observability": {
        "kind": "console",
        "mcp": "",
        "cli": "grep",
        "log_path": "logs/app.log",
    },
}


def test_b1_secret_in_array_rejected(tmp: Path) -> None:
    bad = {**VALID, "vcs": {"host": "github", "owners": ["ok", "ghp_" + "a" * 36]}}
    errs = P.validate_profile_dict(bad, tmp)
    assert any("owners" in e.field for e in errs), errs


def test_b1_secret_in_nested_table_rejected(tmp: Path) -> None:
    bad = {
        **VALID,
        "tracker": {**VALID["tracker"], "meta": {"token": "ghp_" + "b" * 36}},
    }
    errs = P.validate_profile_dict(bad, tmp)
    assert any("token" in e.field for e in errs), errs


def test_m4_hyphenated_mcp_accepted(tmp: Path) -> None:
    ok = {**VALID, "tracker": {**VALID["tracker"], "mcp": "mcp__github-enterprise__*"}}
    assert P.validate_profile_dict(ok, tmp) == []
    # and what the producer would record round-trips
    prof, _ = D.build_profile(tmp, mcp_prefixes=["mcp__github-enterprise__*"])


def test_m2_non_console_obs_does_not_bind_grep(tmp: Path) -> None:
    (tmp / "package.json").write_text(
        json.dumps({"dependencies": {"@datadog/browser-rum": "^5"}}), encoding="utf-8"
    )
    prof, _ = D.build_profile(tmp, mcp_prefixes=[])
    assert prof["observability"]["kind"] == "datadog"
    assert prof["observability"]["cli"] == "", prof[
        "observability"
    ]  # honest-empty → ask-user, NOT grep


def test_h2_build_write_load_end_to_end(tmp: Path) -> None:
    # conflicting CI + a malformed manifest → build, write, read-back
    (tmp / ".github" / "workflows").mkdir(parents=True)
    (tmp / ".github" / "workflows" / "ci.yml").write_text("on: push", encoding="utf-8")
    (tmp / ".gitlab-ci.yml").write_text("stages: [test]", encoding="utf-8")
    (tmp / "package.json").write_text("{ broken json", encoding="utf-8")
    prof, _ = D.build_profile(tmp, mcp_prefixes=[])
    out = tmp / "apex.profile.toml"
    P.write_profile(prof, out)
    text = out.read_text(encoding="utf-8")
    assert "# TODO" in text, "conflict must surface as a comment"
    assert "# gap:" in text, "malformed-manifest gap must surface, not vanish"
    assert "_conflict" not in text and "_gaps" not in text, (
        "meta keys must not be written as fields"
    )
    loaded = P.load_profile(out, repo_root=tmp)
    assert isinstance(loaded, P.Profile), loaded
    assert loaded.tracker.kind == "", (
        "unresolved-conflict axis loads as empty-kind (→ ask-user)"
    )


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
