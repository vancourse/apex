"""PR-A1 tests — apex.profile.toml schema / value-shape lint / loader (design §C).

Standalone-runnable (plain asserts, no pytest dependency required):
    python tests/test_profile.py
Also pytest-discoverable (each test_* is a no-arg function).

Mirrors PRD scenarios: S1.1 (valid round-trip), S1.2 (value-shape lint catches every
field-kind violation incl. the no-secrets decidability), S1.3 (AC2 field-presence),
S7-edge (malformed/absent), repo_path confinement (F1).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import profile as P  # noqa: E402

VALID = {
    "tracker": {
        "kind": "github",
        "mcp": "mcp__github__*",
        "cli": "gh",
        "bug_label": "bug",
    },
    "observability": {
        "kind": "console",
        "mcp": "",
        "cli": "grep",
        "log_path": "logs/app.log",
    },
    "vcs": {"host": "github", "repo": "owner/apex"},
    "reproduce": {
        "local": "docker-compose up && make test",
        "staging_url": "https://staging.example.com",
    },
}


def _write(tmp: Path, data: dict) -> Path:
    """Write a profile dict to TOML by round-tripping through the writer."""
    p = tmp / "apex.profile.toml"
    P.write_profile(data, p)
    return p


def test_s1_1_valid_profile_loads_and_round_trips(tmp: Path) -> None:
    p = _write(tmp, VALID)
    prof = P.load_profile(p, repo_root=tmp)
    assert isinstance(prof, P.Profile), prof
    assert prof.tracker.kind == "github" and prof.tracker.cli == "gh"
    assert prof.observability.mcp == ""  # present-but-empty is legal (AC2a)
    assert prof.observability.extras["log_path"] == "logs/app.log"
    assert prof.vcs["repo"] == "owner/apex"


def test_s1_2_token_in_identifier_rejected(tmp: Path) -> None:
    bad = {**VALID, "vcs": {"host": "github", "repo": "ghp_" + "a" * 36}}
    errs = P.validate_profile_dict(bad, tmp)
    assert any(e.field == "vcs.repo" and e.code == P.SHAPE_VIOLATION for e in errs), (
        errs
    )


def test_s1_2_secret_value_in_secret_ref_rejected(tmp: Path) -> None:
    bad = {
        **VALID,
        "observability": {**VALID["observability"], "secret_ref": "sk-live-abc123XYZ"},
    }
    errs = P.validate_profile_dict(bad, tmp)
    assert any(e.field == "observability.secret_ref" for e in errs), errs
    # but a real env-var NAME is fine
    ok = {
        **VALID,
        "observability": {**VALID["observability"], "secret_ref": "DD_API_KEY"},
    }
    assert P.validate_profile_dict(ok, tmp) == []


def test_s1_2_cli_with_separators_or_flags_rejected(tmp: Path) -> None:
    for evil in ("gh; curl evil", "gh --token=x", "/usr/bin/gh", "gh && rm"):
        bad = {**VALID, "tracker": {**VALID["tracker"], "cli": evil}}
        errs = P.validate_profile_dict(bad, tmp)
        assert any(e.field == "tracker.cli" for e in errs), (
            f"{evil!r} should be rejected: {errs}"
        )


def test_s1_2_bad_enum_and_bad_mcp_rejected(tmp: Path) -> None:
    bad_kind = {**VALID, "tracker": {**VALID["tracker"], "kind": "bitbucket"}}
    assert any(
        e.field == "tracker.kind" for e in P.validate_profile_dict(bad_kind, tmp)
    )
    bad_mcp = {**VALID, "tracker": {**VALID["tracker"], "mcp": "evilprefix"}}
    assert any(e.field == "tracker.mcp" for e in P.validate_profile_dict(bad_mcp, tmp))


def test_s1_3_routed_axis_missing_binding(tmp: Path) -> None:
    bad = {
        **VALID,
        "tracker": {"kind": "github", "mcp": "mcp__github__*"},
    }  # no cli key
    errs = P.validate_profile_dict(bad, tmp)
    assert any(
        e.code == P.MISSING_BINDING and e.field == "tracker.cli" for e in errs
    ), errs


def test_s7_edge_malformed_and_absent(tmp: Path) -> None:
    bad = tmp / "apex.profile.toml"
    bad.write_text("this is not = valid = toml ===", encoding="utf-8")
    r = P.load_profile(bad, repo_root=tmp)
    assert isinstance(r, P.ProfileError) and r.code == P.MALFORMED, r
    missing = P.load_profile(tmp / "nope.toml", repo_root=tmp)
    assert isinstance(missing, P.ProfileError) and missing.code == P.MALFORMED


def test_repo_path_confinement(tmp: Path) -> None:
    # traversal + absolute rejected
    for evil in ("../../etc/passwd", "/etc/passwd", "logs/../../secret"):
        bad = {**VALID, "observability": {**VALID["observability"], "log_path": evil}}
        errs = P.validate_profile_dict(bad, tmp)
        assert any(e.field == "observability.log_path" for e in errs), (
            f"{evil!r}: {errs}"
        )
    # an escaping symlink is rejected (realpath leaves the tree)
    outside = tmp.parent / "outside_secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (tmp / "logs").mkdir(exist_ok=True)
    link = tmp / "logs" / "evil.log"
    try:
        os.symlink(outside, link)
        bad = {
            **VALID,
            "observability": {**VALID["observability"], "log_path": "logs/evil.log"},
        }
        errs = P.validate_profile_dict(bad, tmp)
        assert any(e.field == "observability.log_path" for e in errs), (
            f"escaping symlink not caught: {errs}"
        )
    finally:
        if link.exists() or link.is_symlink():
            link.unlink()


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


# pytest fixture shim so the same functions run under pytest too
try:
    import pytest

    @pytest.fixture
    def tmp(tmp_path):  # noqa: D103
        return tmp_path
except ImportError:  # standalone mode
    pass


if __name__ == "__main__":
    raise SystemExit(_run())
