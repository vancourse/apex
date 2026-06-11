"""Layer 1 tests — state_tool.py: S1.1, S1.2, S1.3, S1-edge, S3, S3-edge.

Mirrors PRD scenarios 1:1 as required by D5.  Run from the repo root:
  pytest skills/agent-rails/reference/tests/test_state_tool.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

# Make state_tool importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent.parent))
import state_tool  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def feature_dir(tmp_path: Path) -> Path:
    return tmp_path / "my-feature"


@pytest.fixture()
def initialized_dir(feature_dir: Path) -> Path:
    feature_dir.mkdir()
    state = {
        "version": 1,
        "feature": "my-feature",
        "artifacts": {
            "prd": {"status": "draft"},
            "design": {"status": "draft"},
            "impl-plan": {"status": "draft"},
        },
    }
    (feature_dir / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    return feature_dir


@pytest.fixture()
def prd_frozen_dir(tmp_path: Path) -> Path:
    """Feature dir: prd frozen (with real file + hash), design in-review."""
    d = tmp_path / "prd-frozen-feature"
    d.mkdir()

    prd_content = "# PRD\nS1 scenario\n## Freeze marker\nFrozen.\n"
    (d / "prd.md").write_text(prd_content)
    prd_sha = hashlib.sha256(prd_content.encode()).hexdigest()

    state = {
        "version": 1,
        "feature": "prd-frozen-feature",
        "artifacts": {
            "prd": {
                "status": "frozen",
                "gate": "prd-review",
                "at": "2026-06-11",
                "sha256": prd_sha,
                "signed_off_by": "PR #27",
            },
            "design": {"status": "in-review"},
            "impl-plan": {"status": "draft"},
        },
    }
    (d / "state.json").write_text(json.dumps(state, indent=2) + "\n")
    return d


@pytest.fixture()
def fixture_gates(tmp_path: Path) -> Path:
    """Minimal gates.json fixture for S1.3 registry join."""
    gates = {
        "version": 1,
        "phases": ["SPEC", "PLAN", "IMPL-PLAN", "IMPL"],
        "gates": [
            {
                "skill": "prd-review",
                "phases": ["SPEC"],
                "blocking": True,
                "freezes": "prd",
                "fires": "PRD authored or edited",
            },
            {
                "skill": "design-review",
                "phases": ["PLAN"],
                "blocking": True,
                "freezes": "design",
                "fires": "design drafted",
                "requires_frozen": ["prd"],
            },
            {
                "skill": "impl-plan-review",
                "phases": ["IMPL-PLAN"],
                "blocking": True,
                "freezes": "impl-plan",
                "fires": "impl-plan drafted",
                "requires_frozen": ["design"],
            },
        ],
    }
    p = tmp_path / "gates.json"
    p.write_text(json.dumps(gates, indent=2) + "\n")
    return p


# ---------------------------------------------------------------------------
# S1.1 — current phase named correctly
# ---------------------------------------------------------------------------

class TestS1Phase:
    def test_phase_is_plan_when_prd_frozen_design_not(self, prd_frozen_dir, fixture_gates, capsys):
        """S1.1: prd frozen + design in-review → phase reported as PLAN."""
        args = _make_args("report", dir=str(prd_frozen_dir), gates=str(fixture_gates))
        rc = state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert rc == 0
        assert "Phase: PLAN" in out

    def test_phase_naive_no_registry(self, prd_frozen_dir, capsys):
        """S1.1 (no registry): naive phase still names PLAN."""
        args = _make_args("report", dir=str(prd_frozen_dir), gates=None)
        rc = state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert rc == 0
        assert "Phase: PLAN" in out

    def test_phase_spec_when_prd_draft(self, initialized_dir, capsys):
        """Phase is SPEC when prd is still draft."""
        args = _make_args("report", dir=str(initialized_dir), gates=None)
        state_tool.cmd_report(args)
        out = capsys.readouterr().out
        assert "Phase: SPEC" in out


# ---------------------------------------------------------------------------
# S1.2 — every artifact's status + frozen hash listed
# ---------------------------------------------------------------------------

class TestS1Statuses:
    def test_all_statuses_listed(self, prd_frozen_dir, capsys):
        """S1.2: report lists prd:frozen, design:in-review, impl-plan:draft."""
        args = _make_args("report", dir=str(prd_frozen_dir), gates=None)
        state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert "prd: frozen" in out
        assert "design: in-review" in out
        assert "impl-plan: draft" in out

    def test_frozen_artifact_shows_hash_prefix(self, prd_frozen_dir, capsys):
        """S1.2: frozen artifact output includes sha256 (truncated)."""
        args = _make_args("report", dir=str(prd_frozen_dir), gates=None)
        state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert "sha256=" in out
        assert "gate=prd-review" in out
        assert "signed_off_by=PR #27" in out


# ---------------------------------------------------------------------------
# S1.3 — next required gate named from registry
# ---------------------------------------------------------------------------

class TestS1NextGate:
    def test_next_gate_is_design_review(self, prd_frozen_dir, fixture_gates, capsys):
        """S1.3: prd frozen + design not frozen → next gate = design-review."""
        args = _make_args("report", dir=str(prd_frozen_dir), gates=str(fixture_gates))
        state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert "design-review" in out
        assert "Next gate:" in out

    def test_no_gates_reports_stub(self, prd_frozen_dir, capsys):
        """S1.3 (stub): without --gates, reports 'registry not loaded'."""
        args = _make_args("report", dir=str(prd_frozen_dir), gates=None)
        state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert "registry not loaded" in out

    def test_all_frozen_reports_gates_satisfied(self, tmp_path, fixture_gates, capsys):
        """S1.3: all artifacts frozen → all registered gates satisfied."""
        d = tmp_path / "all-frozen"
        d.mkdir()
        # write dummy artifact files
        for art in ["prd", "design", "impl-plan"]:
            (d / f"{art}.md").write_text(f"# {art}\n")
        sha = hashlib.sha256(b"# prd\n").hexdigest()

        state = {
            "version": 1,
            "feature": "all-frozen",
            "artifacts": {
                art: {
                    "status": "frozen",
                    "gate": f"{art}-review",
                    "at": "2026-06-11",
                    "sha256": hashlib.sha256(f"# {art}\n".encode()).hexdigest(),
                    "signed_off_by": "PR #1",
                }
                for art in ["prd", "design", "impl-plan"]
            },
        }
        (d / "state.json").write_text(json.dumps(state, indent=2) + "\n")

        args = _make_args("report", dir=str(d), gates=str(fixture_gates))
        state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert "all registered gates satisfied" in out


# ---------------------------------------------------------------------------
# S1-edge — UNMANAGED (no state.json)
# ---------------------------------------------------------------------------

class TestS1EdgeUnmanaged:
    def test_missing_state_json_reports_unmanaged(self, tmp_path, capsys):
        """S1-edge: feature dir exists but no state.json → UNMANAGED message."""
        d = tmp_path / "no-state"
        d.mkdir()
        (d / "prd.md").write_text("# PRD\n")

        args = _make_args("report", dir=str(d), gates=None)
        rc = state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert rc == 0
        assert "UNMANAGED" in out
        assert "init" in out

    def test_nonexistent_dir_reports_unmanaged(self, tmp_path, capsys):
        """S1-edge: dir doesn't exist → UNMANAGED (not a crash)."""
        args = _make_args("report", dir=str(tmp_path / "ghost"), gates=None)
        rc = state_tool.cmd_report(args)
        out = capsys.readouterr().out

        assert rc == 0
        assert "UNMANAGED" in out


# ---------------------------------------------------------------------------
# S3 — freeze writes gate / at / sha256 atomically
# ---------------------------------------------------------------------------

class TestS3Freeze:
    def test_freeze_writes_all_evidence_fields(self, initialized_dir: Path):
        """S3: freeze writes status=frozen, gate, at, sha256, signed_off_by."""
        (initialized_dir / "prd.md").write_text("# PRD\nS1 scenario.\n")

        args = _make_args(
            "freeze",
            dir=str(initialized_dir),
            artifact="prd",
            gate="prd-review",
            signoff="PR #99",
        )
        rc = state_tool.cmd_freeze(args)
        assert rc == 0

        state = json.loads((initialized_dir / "state.json").read_text())
        entry = state["artifacts"]["prd"]
        assert entry["status"] == "frozen"
        assert entry["gate"] == "prd-review"
        assert entry["signed_off_by"] == "PR #99"
        assert len(entry["sha256"]) == 64
        assert entry["at"]  # non-empty date

    def test_freeze_sha256_matches_file(self, initialized_dir: Path):
        """S3: stored sha256 must match the actual file bytes at freeze time."""
        content = "# PRD\nContent for hashing.\n"
        prd = initialized_dir / "prd.md"
        prd.write_text(content)
        expected_sha = hashlib.sha256(content.encode()).hexdigest()

        args = _make_args(
            "freeze",
            dir=str(initialized_dir),
            artifact="prd",
            gate="prd-review",
            signoff="user@session 2026-06-11",
        )
        state_tool.cmd_freeze(args)

        state = json.loads((initialized_dir / "state.json").read_text())
        assert state["artifacts"]["prd"]["sha256"] == expected_sha

    def test_freeze_other_artifacts_unchanged(self, initialized_dir: Path):
        """S3: freezing prd leaves design and impl-plan untouched."""
        (initialized_dir / "prd.md").write_text("# PRD\n")
        args = _make_args(
            "freeze",
            dir=str(initialized_dir),
            artifact="prd",
            gate="prd-review",
            signoff="PR #1",
        )
        state_tool.cmd_freeze(args)

        state = json.loads((initialized_dir / "state.json").read_text())
        assert state["artifacts"]["design"]["status"] == "draft"
        assert state["artifacts"]["impl-plan"]["status"] == "draft"


# ---------------------------------------------------------------------------
# S3-edge — torn write: os.replace raises → original state.json intact
# ---------------------------------------------------------------------------

class TestS3EdgeTornWrite:
    def test_torn_write_leaves_original_intact(self, initialized_dir: Path):
        """S3-edge: if os.replace raises between temp-write and rename,
        the original state.json survives unchanged."""
        original_text = (initialized_dir / "state.json").read_text()
        (initialized_dir / "prd.md").write_text("# PRD\n")

        def raise_on_replace(src, dst):
            raise OSError("simulated power failure")

        with patch("os.replace", side_effect=raise_on_replace):
            with pytest.raises(OSError, match="simulated power failure"):
                state_tool._write_state_atomic(str(initialized_dir), {"version": 1, "bad": True})

        # Original must be intact
        surviving = (initialized_dir / "state.json").read_text()
        assert surviving == original_text

    def test_torn_write_leaves_no_temp_file(self, initialized_dir: Path):
        """S3-edge: the .tmp file is cleaned up when os.replace fails."""
        (initialized_dir / "prd.md").write_text("# PRD\n")

        def raise_on_replace(src, dst):
            raise OSError("simulated power failure")

        with patch("os.replace", side_effect=raise_on_replace):
            with pytest.raises(OSError):
                state_tool._write_state_atomic(str(initialized_dir), {"version": 1})

        tmp_files = list(initialized_dir.glob("*.tmp"))
        assert tmp_files == [], f"Stray temp files found: {tmp_files}"


# ---------------------------------------------------------------------------
# Additional coverage: init command
# ---------------------------------------------------------------------------

class TestInit:
    def test_init_creates_state_json(self, feature_dir: Path):
        args = _make_args("init", dir=str(feature_dir))
        rc = state_tool.cmd_init(args)
        assert rc == 0
        state = json.loads((feature_dir / "state.json").read_text())
        assert state["version"] == 1
        assert state["feature"] == feature_dir.name
        for art in ["prd", "design", "impl-plan"]:
            assert state["artifacts"][art]["status"] == "draft"

    def test_init_all_draft_never_frozen(self, feature_dir: Path):
        """init must not write frozen status for any artifact."""
        args = _make_args("init", dir=str(feature_dir))
        state_tool.cmd_init(args)
        state = json.loads((feature_dir / "state.json").read_text())
        for name, entry in state["artifacts"].items():
            assert entry["status"] != "frozen", f"{name} must not be frozen at init"

    def test_init_refuses_overwrite_without_force(self, initialized_dir: Path, capsys):
        args = _make_args("init", dir=str(initialized_dir))
        rc = state_tool.cmd_init(args)
        assert rc != 0

    def test_init_force_overwrites(self, initialized_dir: Path):
        args = _make_args("init", dir=str(initialized_dir), force=True)
        rc = state_tool.cmd_init(args)
        assert rc == 0

    def test_init_custom_feature_name(self, feature_dir: Path):
        args = _make_args("init", dir=str(feature_dir), feature="my-custom-feature")
        state_tool.cmd_init(args)
        state = json.loads((feature_dir / "state.json").read_text())
        assert state["feature"] == "my-custom-feature"

    def test_init_custom_artifacts(self, feature_dir: Path):
        args = _make_args("init", dir=str(feature_dir), artifacts=["prd", "adr"])
        state_tool.cmd_init(args)
        state = json.loads((feature_dir / "state.json").read_text())
        assert set(state["artifacts"].keys()) == {"prd", "adr"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _FakeArgs:
    """Minimal argparse.Namespace stand-in."""
    pass


def _make_args(command: str, **kwargs) -> _FakeArgs:
    a = _FakeArgs()
    a.command = command
    # defaults
    a.dir = kwargs.get("dir", ".")
    a.gates = kwargs.get("gates", None)
    a.artifact = kwargs.get("artifact", None)
    a.gate = kwargs.get("gate", None)
    a.signoff = kwargs.get("signoff", None)
    a.force = kwargs.get("force", False)
    a.feature = kwargs.get("feature", None)
    a.artifacts = kwargs.get("artifacts", None)
    return a
