#!/usr/bin/env python3
"""state_tool.py — machine-decidable pipeline state for apex features.

Subcommands:
  init <dir>                          create all-draft state.json
  report <dir> [--gates <path>]       print status + flags + phase + next gate
  freeze <dir> <artifact> --gate --signoff  atomic frozen transition (lint stub → L2)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path
from typing import Optional

STATE_FILE = "state.json"
SCHEMA_VERSION = 1
EVIDENCE_FIELDS = {"gate", "at", "sha256", "signed_off_by"}
DEFAULT_ARTIFACTS = ["prd", "design", "impl-plan"]


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _state_path(feature_dir: str) -> Path:
    return Path(feature_dir) / STATE_FILE


def _load_state(feature_dir: str) -> Optional[dict]:
    p = _state_path(feature_dir)
    if not p.exists():
        return None
    with open(p) as f:
        return json.load(f)


def _write_state_atomic(feature_dir: str, state: dict) -> None:
    """Atomic write: temp file in same directory + os.replace."""
    p = _state_path(feature_dir)
    dir_path = p.parent
    fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(state, f, indent=2)
            f.write("\n")
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Flag computation (read-time, never stored)
# ---------------------------------------------------------------------------

def _find_artifact_file(artifact: str, feature_dir: str) -> Optional[str]:
    p = Path(feature_dir) / f"{artifact}.md"
    return str(p) if p.exists() else None


def _compute_flags(artifact: str, entry: dict, feature_dir: str) -> list[str]:
    """Compute derived flags for one artifact entry; never stored in state."""
    flags: list[str] = []
    status = entry.get("status", "absent")

    if status != "frozen":
        return flags

    missing = EVIDENCE_FIELDS - entry.keys()
    if missing:
        flags.append(f"MALFORMED-TRANSITION(missing:{','.join(sorted(missing))})")
        return flags  # hash check meaningless without stored sha256

    artifact_path = _find_artifact_file(artifact, feature_dir)
    if artifact_path:
        current_hash = _sha256_file(artifact_path)
        if current_hash != entry.get("sha256"):
            flags.append("POST-FREEZE-DRIFT")

    # DIVERGENCE (prose vs state) is deferred to L5 — requires SKILL.md prose-scan

    return flags


# ---------------------------------------------------------------------------
# Registry join (partial in L1: loads gates.json when --gates supplied)
# ---------------------------------------------------------------------------

def _next_gate(gates_path: Optional[str], artifacts: dict) -> str:
    """Return next required gate from registry, or a stub message."""
    if gates_path is None:
        return "registry not loaded (provide --gates <path>)"

    try:
        with open(gates_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        return f"registry load error: {exc}"

    frozen = {name for name, entry in artifacts.items() if entry.get("status") == "frozen"}

    for gate in data.get("gates", []):
        freezes = gate.get("freezes")
        if not freezes or freezes in frozen:
            continue
        requires = gate.get("requires_frozen", [])
        if all(r in frozen for r in requires):
            phase = gate.get("phases", ["?"])[0]
            skill = gate.get("skill", "?")
            return f"{skill} (phase {phase}, freezes {freezes})"

    return "all registered gates satisfied"


def _current_phase(gates_path: Optional[str], artifacts: dict) -> str:
    """Derive current phase from registry; fall back to naive ordering."""
    if gates_path is None:
        return _naive_phase(artifacts)

    try:
        with open(gates_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return _naive_phase(artifacts)

    frozen = {name for name, entry in artifacts.items() if entry.get("status") == "frozen"}

    for gate in data.get("gates", []):
        freezes = gate.get("freezes")
        if not freezes or freezes in frozen:
            continue
        requires = gate.get("requires_frozen", [])
        if all(r in frozen for r in requires):
            phases = gate.get("phases", [])
            return phases[0] if phases else "UNKNOWN"

    return "IMPL (all planning artifacts frozen)"


def _naive_phase(artifacts: dict) -> str:
    """Best-effort phase from artifact statuses; superseded by registry join in L3."""
    for artifact, phase in [("prd", "SPEC"), ("design", "PLAN"), ("impl-plan", "IMPL-PLAN")]:
        if artifacts.get(artifact, {}).get("status") != "frozen":
            return phase
    return "IMPL (all planning artifacts frozen)"


# ---------------------------------------------------------------------------
# Lint stub (replaced in L2)
# ---------------------------------------------------------------------------

def _freeze_lint_stub(artifact_type: str, artifact_file: str) -> list[str]:
    """No-op — wired to freeze_lint.py in L2."""
    return []


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    feature_dir = args.dir
    p = _state_path(feature_dir)

    if p.exists() and not args.force:
        print(f"ERROR: {p} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    Path(feature_dir).mkdir(parents=True, exist_ok=True)

    artifact_names = args.artifacts if args.artifacts else DEFAULT_ARTIFACTS
    feature_name = args.feature or Path(feature_dir).name

    state: dict = {
        "version": SCHEMA_VERSION,
        "feature": feature_name,
        "artifacts": {name: {"status": "draft"} for name in artifact_names},
    }

    _write_state_atomic(feature_dir, state)
    print(f"Initialized {p} ({len(artifact_names)} artifacts, all draft)")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    feature_dir = args.dir
    gates_path: Optional[str] = getattr(args, "gates", None)

    state = _load_state(feature_dir)
    if state is None:
        print(f"UNMANAGED — {_state_path(feature_dir)} not found.")
        print(f"  Run: state_tool.py init {feature_dir}")
        return 0

    artifacts = state.get("artifacts", {})

    print(f"Feature: {state.get('feature', '(unknown)')}")
    print()

    for name, entry in artifacts.items():
        status = entry.get("status", "absent")
        flags = _compute_flags(name, entry, feature_dir)
        flag_str = f"  [{', '.join(flags)}]" if flags else ""
        print(f"  {name}: {status}{flag_str}")
        if status == "frozen" and not flags:
            sha = entry.get("sha256", "")
            print(f"    gate={entry.get('gate')}  at={entry.get('at')}  "
                  f"sha256={sha[:16]}...  signed_off_by={entry.get('signed_off_by')}")

    print()
    phase = _current_phase(gates_path, artifacts)
    print(f"Phase: {phase}")
    next_g = _next_gate(gates_path, artifacts)
    print(f"Next gate: {next_g}")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    feature_dir = args.dir
    artifact = args.artifact
    gate = args.gate
    signoff = args.signoff

    if not gate:
        print("ERROR: --gate is required", file=sys.stderr)
        return 1
    if not signoff:
        print("ERROR: --signoff is required", file=sys.stderr)
        return 1

    state = _load_state(feature_dir)
    if state is None:
        print(f"ERROR: {_state_path(feature_dir)} not found. Run init first.", file=sys.stderr)
        return 1

    artifacts = state.get("artifacts", {})
    if artifact not in artifacts:
        known = list(artifacts.keys())
        print(f"ERROR: artifact '{artifact}' not in state.json. Known: {known}", file=sys.stderr)
        return 1

    artifact_path = _find_artifact_file(artifact, feature_dir)
    if artifact_path is None:
        print(f"ERROR: {artifact}.md not found in {feature_dir}", file=sys.stderr)
        return 1

    # Lint (no-op stub in L1; freeze_lint.py wired in L2)
    defects = _freeze_lint_stub(artifact, artifact_path)
    if defects:
        print(f"FREEZE REFUSED — {len(defects)} defect(s):")
        for d in defects:
            print(f"  {d}")
        print("State unchanged.")
        return 1

    sha = _sha256_file(artifact_path)
    today = str(date.today())

    artifacts[artifact] = {
        "status": "frozen",
        "gate": gate,
        "at": today,
        "sha256": sha,
        "signed_off_by": signoff,
    }
    state["artifacts"] = artifacts
    _write_state_atomic(feature_dir, state)

    print(f"Frozen: {artifact}")
    print(f"  gate={gate}  at={today}  sha256={sha[:16]}...  signed_off_by={signoff}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="state_tool.py",
        description="apex pipeline state tool",
    )
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Initialize state.json (all-draft)")
    p_init.add_argument("dir")
    p_init.add_argument("--feature", help="Feature name (defaults to dir basename)")
    p_init.add_argument("--artifacts", nargs="+")
    p_init.add_argument("--force", action="store_true")

    p_report = sub.add_parser("report", help="Report pipeline state")
    p_report.add_argument("dir")
    p_report.add_argument("--gates", metavar="PATH", help="Path to gates.json")

    p_freeze = sub.add_parser("freeze", help="Record a freeze transition")
    p_freeze.add_argument("dir")
    p_freeze.add_argument("artifact")
    p_freeze.add_argument("--gate", required=True)
    p_freeze.add_argument("--signoff", required=True)

    args = parser.parse_args()

    dispatch = {"init": cmd_init, "report": cmd_report, "freeze": cmd_freeze}
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 1
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
