"""The interactive-vs-unattended two-binding resolver (design §B, AC2 + AC3).

The single most load-bearing runtime mechanic: **MCP-only must be impossible**, because
a session MCP server does not exist in the headless `autonomous-fix` CI path. The profile
carries BOTH bindings per routed axis; the resolver picks by MODE. Pure, unit-testable.

The structural guarantee (S5.2): the UNATTENDED branch never reads `axis_cfg.mcp`.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

# AxisConfig is the loader's dataclass (PR-A1). Import lazily-friendly: the resolver only
# reads .cli and .mcp, so any object with those attrs works (keeps the test deps light).


class Mode(Enum):
    INTERACTIVE = "interactive"  # a dev locally; session MCP may exist
    UNATTENDED = "unattended"  # the gate's CI context; NO session MCP


@dataclass(frozen=True)
class McpBinding:
    prefix: str


@dataclass(frozen=True)
class CliBinding:
    command: str


@dataclass(frozen=True)
class AskUserBinding:
    reason: str  # a real terminal (§B.3) — interactive prompts, unattended escalates


Binding = McpBinding | CliBinding | AskUserBinding


class _AxisLike(Protocol):
    """The two fields the resolver reads — kept structural so it doesn't import the loader's
    AxisConfig (any object exposing cli + mcp resolves)."""

    cli: str
    mcp: str


def cli_on_path(cmd: str) -> bool:
    """True iff the bare command resolves on PATH (shutil.which-shaped). Never executes it."""
    return bool(cmd) and shutil.which(cmd) is not None


def _default_mcp_probe(prefix: str) -> bool:
    # In pure code (no agent / no session) nothing is connected. The agent injects a real
    # ToolSearch-backed probe in interactive use; pure/unattended code is safe by default.
    return False


def resolve(
    axis_cfg: _AxisLike,
    mode: Mode,
    mcp_probe: Callable[[str], bool] = _default_mcp_probe,
) -> Binding:
    """Resolve one routed axis to a binding by mode.

    mcp_probe(prefix) -> bool: True iff an `mcp__<server>__*`-matching tool is schema-loaded
    and CALLABLE this session (the "callable" bar, not the "listed" bar). Only consulted in
    INTERACTIVE mode — the unattended branch must never touch it (AC3 / S5.2).
    """
    if mode is Mode.UNATTENDED:
        # CLI-ONLY. `axis_cfg.mcp` is intentionally NOT read here — the structural guarantee.
        # Fail-CLOSED (design §I): a declared-but-not-on-PATH cli ESCALATES, never proceeds on
        # an assumed-present command (the silent-stub the resolver exists to prevent).
        if axis_cfg.cli and cli_on_path(axis_cfg.cli):
            return CliBinding(axis_cfg.cli)
        return AskUserBinding(
            reason="no usable cli binding on PATH; unattended cannot use mcp"
        )
    # INTERACTIVE — MCP-first, CLI fallback, ask-user last.
    if axis_cfg.mcp and mcp_probe(axis_cfg.mcp):
        return McpBinding(axis_cfg.mcp)
    if axis_cfg.cli and cli_on_path(axis_cfg.cli):
        return CliBinding(axis_cfg.cli)
    return AskUserBinding(reason="paste the issue/logs")
