"""One process per hook event, routing to every gate registered for it.

Replaces up to twelve hook processes per tool call with one. The registry is
``hooks/gates.toml``: a gate that has no row does not run, and a row whose
module cannot be imported produces a loud notice instead of silence —
``RAILS: gate <x> missing; unguarded`` — because a missing check that fails
open silently is indistinguishable from a passing one.

Contract with the harness: always exit 0, always print at most one JSON object,
never let a gate's exception escape. Shadow mode turns a gate's Deny or Block
into a ``would-deny`` / ``would-block`` firing-log line and nothing else; that
is how a new refusal earns its false-positive count before it refuses anyone.
"""

from __future__ import annotations

import datetime as _dt
import importlib
import json
import os
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rails import store
from rails.hookio import Block, Deny, Event, Notice, Outcome, sha256

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = PLUGIN_ROOT / "hooks" / "gates.toml"


@dataclass
class GateRow:
    name: str
    module: str
    events: list[str]
    tools: list[str] = field(default_factory=list)
    mode: str = "enforce"  # enforce | shadow
    shadow_until: str = ""  # ISO date; shadow while today < this
    raw: dict[str, Any] = field(default_factory=dict)

    def matches(self, evt: Event) -> bool:
        if evt.name not in self.events:
            return False
        if self.tools and evt.name in ("PreToolUse", "PostToolUse"):
            return evt.tool_name in self.tools
        return True

    def shadowed(self, today: _dt.date) -> bool:
        if os.environ.get("RAILS_SHADOW_ALL"):
            return True
        if self.mode == "shadow":
            return True
        if self.shadow_until:
            try:
                return today < _dt.date.fromisoformat(self.shadow_until)
            except ValueError:
                return True
        return False


def load_registry(path: Path = REGISTRY) -> list[GateRow]:
    with open(path, "rb") as handle:
        data = tomllib.load(handle)
    rows = []
    for raw in data.get("gate", []):
        rows.append(
            GateRow(
                name=raw["name"],
                module=raw.get("module", raw["name"]),
                events=list(raw.get("events", [])),
                tools=list(raw.get("tools", [])),
                mode=raw.get("mode", "enforce"),
                shadow_until=raw.get("shadow_until", ""),
                raw=raw,
            )
        )
    return rows


def _disabled() -> set[str]:
    return {
        name.strip()
        for name in os.environ.get("RAILS_GATES_OFF", "").split(",")
        if name.strip()
    }


def _log_firing(evt: Event, gate: str, verdict: str, ms: float) -> None:
    """One line per non-silent firing. The command TEXT is never written —
    only its hash — because a command can carry a value that must not persist."""
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return
    row = {
        "ts": int(time.time()),
        "session": evt.session_id[:12],
        "leaf": repo.leaf,
        "event": evt.name,
        "tool": evt.tool_name,
        "gate": gate,
        "verdict": verdict,
        "ms": round(ms, 1),
    }
    if evt.command:
        row["cmd_sha256"] = sha256(evt.command)[:16]
    try:
        store.append_jsonl(repo.dir / "firings.jsonl", row)
    except OSError:
        pass


def dispatch(
    evt: Event, rows: list[GateRow] | None = None, today: _dt.date | None = None
) -> Outcome:
    outcome = Outcome(event=evt.name)
    try:
        rows = load_registry() if rows is None else rows
    except (OSError, tomllib.TOMLDecodeError, KeyError) as exc:
        outcome.notices.append(
            f"RAILS: gate registry unreadable ({type(exc).__name__}); every rails gate is unguarded"
        )
        return outcome
    today = today or _dt.date.today()
    off = _disabled()
    for row in rows:
        if row.name in off or not row.matches(evt):
            continue
        started = time.perf_counter()
        try:
            module = importlib.import_module(f"rails.gates.{row.module}")
        except Exception:  # noqa: BLE001 — a missing module must be loud, never fatal
            outcome.notices.append(f"RAILS: gate {row.name} missing; unguarded")
            _log_firing(evt, row.name, "missing", 0.0)
            continue
        try:
            evt.payload["_rails_shadow"] = row.shadowed(today)
            verdict = module.check(evt)
        except Exception as exc:  # noqa: BLE001
            outcome.notices.append(
                f"RAILS: gate {row.name} crashed ({type(exc).__name__}); unguarded for this call"
            )
            _log_firing(
                evt, row.name, "crashed", (time.perf_counter() - started) * 1000
            )
            continue
        ms = (time.perf_counter() - started) * 1000
        if verdict is None:
            continue
        verdicts = verdict if isinstance(verdict, list) else [verdict]
        for v in verdicts:
            if isinstance(v, Deny):
                if row.shadowed(today):
                    _log_firing(evt, row.name, "would-deny", ms)
                else:
                    outcome.denies.append(v.reason)
                    _log_firing(evt, row.name, "deny", ms)
            elif isinstance(v, Block):
                if row.shadowed(today):
                    _log_firing(evt, row.name, "would-block", ms)
                else:
                    outcome.blocks.append(v.reason)
                    _log_firing(evt, row.name, "block", ms)
            elif isinstance(v, Notice):
                outcome.notices.append(v.text)
                _log_firing(evt, row.name, "notice", ms)
    return outcome


def main(argv: list[str]) -> int:
    event_name = argv[1] if len(argv) > 1 else ""
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    name = str(payload.get("hook_event_name") or event_name)
    evt = Event(name=name, payload=payload)
    try:
        outcome = dispatch(evt)
        text = outcome.render()
    except Exception as exc:  # noqa: BLE001 — the dispatcher itself must never block
        text = json.dumps(
            {
                "systemMessage": f"RAILS: dispatcher crashed ({type(exc).__name__}); rails gates unguarded for this call"
            }
        )
    if text:
        sys.stdout.write(text)
        sys.stdout.flush()
    return 0
