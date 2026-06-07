"""apex.profile.toml — schema, value-shape lint, loader, and atomic writer.

Routing config only. NO secrets, ever. Machine-written by `detect-stack`, read by
`investigate-bug`. This is the single read/write point and the AC1 enforcement
surface (the value-shape allowlist that makes "no credential in the profile"
*decidable*). Mirrors the autonomous-fix `conformance-lint.py` precedent.

Stdlib only: `tomllib` (read, Python 3.11+) + a hand-formatted writer (no TOML-write
dependency). Run as a CLI to lint a profile:

    python profile.py apex.profile.toml        # exit 0 = clean, 2 = shape/schema violation

See docs/stack-adapters/design.md §C.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# ── Schema: the routed axes (both bindings required, AC2) and their enums ──────
TRACKER_KINDS = ("github", "linear", "jira", "azure-boards", "manual")
OBSERVABILITY_KINDS = (
    "datadog",
    "sentry",
    "otel-honeycomb",
    "cloudwatch",
    "azure-monitor",
    "console",
)
ROUTED_AXES = ("tracker", "observability")  # both require mcp + cli keys present
AXIS_ENUMS = {"tracker": TRACKER_KINDS, "observability": OBSERVABILITY_KINDS}

# ── Error codes (map to the gate's fail-closed terminals) ─────────────────────
MALFORMED = "MALFORMED"
SHAPE_VIOLATION = "SHAPE_VIOLATION"
MISSING_BINDING = "MISSING_BINDING"


@dataclass(frozen=True)
class ProfileError:
    """A load/lint failure. Returned (not raised) so callers branch on the union."""

    code: str
    field: str
    message: str


@dataclass(frozen=True)
class AxisConfig:
    kind: str
    mcp: str  # interactive binding (ToolSearch prefix); MAY be ""
    cli: str  # unattended binding (bare command); MAY be ""
    extras: dict = field(
        default_factory=dict
    )  # bug_label, log_path, (PR-C) service/secret_ref


@dataclass(frozen=True)
class Profile:
    tracker: AxisConfig
    observability: AxisConfig
    vcs: dict
    reproduce: dict


# ── Field-shape validators (the value-shape allowlist, §C.2) ───────────────────
# Each returns None if OK, else a human-readable reason. The descriptor-vs-operation
# distinction: descriptors (kind/mcp/cli/identifier/secret_ref-NAME) are shape-only;
# an *operation* field (repo_path → a file read) gets confinement, not just a charset.

_IDENT_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
_CLI_RE = re.compile(r"^[a-z][a-z0-9_-]*$")  # bare command, no separators/flags
_MCP_RE = re.compile(
    r"^mcp__[A-Za-z0-9_-]+__\*?$"
)  # mcp__<server>__* (server may contain -)
_SECRET_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")  # env-var NAME, never a value

# High-precision known-secret-token prefixes (same family as the autonomous-fix
# scan-secrets hook). A charset-valid identifier can still BE a token (e.g. `ghp_…`
# is alphanumeric), so the descriptor charset check alone can't honour §C.2's
# "rejects a token-shaped value". This decidable prefix denylist closes that — NOT an
# entropy heuristic (the prd-review rejected entropy/regex-length guessing as the
# wrong tool); applied to EVERY string value so no field can carry a secret.
_SECRET_TOKEN_RE = re.compile(
    r"(AKIA[0-9A-Z]{16}"
    r"|ghp_[A-Za-z0-9]{36}|gho_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82}"
    r"|sk-(proj-|svcacct-|admin-)?[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9_-]{20,}"
    r"|xoxb-[0-9]+-[0-9]+-[A-Za-z0-9]+|AIza[0-9A-Za-z_-]{35}"
    r"|-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)


def _v_no_secret_token(value: str) -> str | None:
    return (
        "value matches a known secret-token shape — the profile is routing-only, NO secrets (use secret_ref = an env-var NAME instead)"
        if _SECRET_TOKEN_RE.search(value)
        else None
    )


def _v_enum(value: str, allowed: tuple[str, ...]) -> str | None:
    # "" = the un-inferable / unresolved-conflict placeholder (D.2/D.3) — honest-empty,
    # like mcp/cli. investigate-bug routes an empty-kind axis to ask-user, never a guess.
    if value == "":
        return None
    return None if value in allowed else f"not in enum {allowed!r}"


def _v_mcp(value: str) -> str | None:
    if value == "":
        return None  # present-but-empty is legal (AC2a)
    return None if _MCP_RE.match(value) else "must match mcp__<server>__* or be empty"


def _v_cli(value: str) -> str | None:
    if value == "":
        return None
    if not _CLI_RE.match(value):
        return "must be a bare command [a-z][a-z0-9_-]* (no path separators, no flags) — a value with ';', '/', spaces or flags looks like a smuggled command"
    return None


def _v_identifier(value: str) -> str | None:
    # rejects a token-shaped value (the AC1 "token where an identifier expected" case)
    return (
        None
        if _IDENT_RE.match(value)
        else "must be an identifier [A-Za-z0-9._/-]; a token-shaped value is rejected"
    )


def _v_secret_ref(value: str) -> str | None:
    return (
        None
        if _SECRET_NAME_RE.match(value)
        else "must be an env-var NAME [A-Z][A-Z0-9_]*, never a secret value"
    )


def _v_repo_path(value: str, repo_root: Path) -> str | None:
    """An OPERATION field (the console adapter OPENS it) → confinement, not just shape.

    Repo-relative only: no absolute path, no `..` segment, and the resolved realpath
    must stay under repo_root (rejects an escaping symlink). F1 fix.
    """
    if value == "":
        return None
    p = Path(value)
    if p.is_absolute():
        return "must be repo-relative, not absolute"
    if ".." in p.parts:
        return "must not contain a '..' segment"
    root = Path(os.path.realpath(repo_root))
    resolved = Path(os.path.realpath(root / value))
    try:
        resolved.relative_to(root)
    except ValueError:
        return f"resolves outside the repo root (escaping symlink?): {resolved}"
    return None


# Field-kind → fields, per section
_FREE = {"bug_label", "local", "staging_url"}


def _validate_axis(name: str, tbl: dict, repo_root: Path) -> list[ProfileError]:
    out: list[ProfileError] = []
    enum = AXIS_ENUMS[name]
    kind = tbl.get("kind", "")
    r = _v_enum(kind, enum)
    if r:
        out.append(ProfileError(SHAPE_VIOLATION, f"{name}.kind", r))
    # AC2 field-presence: routed axis must carry BOTH mcp and cli keys (empty allowed)
    for binding in ("mcp", "cli"):
        if binding not in tbl:
            out.append(
                ProfileError(
                    MISSING_BINDING,
                    f"{name}.{binding}",
                    "routed axis must declare both mcp and cli (empty string allowed)",
                )
            )
    if "mcp" in tbl and (r := _v_mcp(str(tbl["mcp"]))):
        out.append(ProfileError(SHAPE_VIOLATION, f"{name}.mcp", r))
    if "cli" in tbl and (r := _v_cli(str(tbl["cli"]))):
        out.append(ProfileError(SHAPE_VIOLATION, f"{name}.cli", r))
    # per-axis extras
    if "bug_label" in tbl:  # free
        pass
    if "log_path" in tbl and (r := _v_repo_path(str(tbl["log_path"]), repo_root)):
        out.append(ProfileError(SHAPE_VIOLATION, f"{name}.log_path", r))
    # PR-C forward-compat fields: validated-if-present (reserved slots)
    if "service" in tbl and (r := _v_identifier(str(tbl["service"]))):
        out.append(ProfileError(SHAPE_VIOLATION, f"{name}.service", r))
    if "secret_ref" in tbl and (r := _v_secret_ref(str(tbl["secret_ref"]))):
        out.append(ProfileError(SHAPE_VIOLATION, f"{name}.secret_ref", r))
    return out


def _validate_descriptor(name: str, tbl: dict) -> list[ProfileError]:
    out: list[ProfileError] = []
    for key, val in tbl.items():
        if key in _FREE:
            continue
        if r := _v_identifier(str(val)):
            out.append(ProfileError(SHAPE_VIOLATION, f"{name}.{key}", r))
    return out


def _scan_secret_tokens(data: dict) -> list[ProfileError]:
    """No value anywhere — string, array element, or nested-table field — may carry a known
    secret-token. Recurses fully so the no-secrets guarantee has no depth/container hole."""
    out: list[ProfileError] = []

    def walk(node, path: str) -> None:
        if isinstance(node, str):
            if r := _v_no_secret_token(node):
                out.append(ProfileError(SHAPE_VIOLATION, path or "<root>", r))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    walk(data, "")
    return out


def validate_profile_dict(data: dict, repo_root: Path) -> list[ProfileError]:
    """The value-shape allowlist (§C.2). Empty list = clean."""
    errs: list[ProfileError] = []
    # No string value anywhere may be a secret token (the no-secrets guarantee).
    errs.extend(_scan_secret_tokens(data))
    for axis in ROUTED_AXES:
        errs.extend(_validate_axis(axis, data.get(axis, {}), repo_root))
    if "vcs" in data:
        errs.extend(_validate_descriptor("vcs", data["vcs"]))
    # reproduce.* are free strings (commands) — no shape rule beyond the secret scan
    return errs


def load_profile(
    path: Path = Path("apex.profile.toml"), repo_root: Path | None = None
) -> Profile | ProfileError:
    """The single read point (§C.3). Shape-validates on read too (catches a hand-edit
    that smuggles a token at investigate time, not silently routed)."""
    repo_root = repo_root or path.resolve().parent
    if not path.exists():
        return ProfileError(
            MALFORMED, str(path), "profile not found — run /apex:detect-stack first"
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        return ProfileError(MALFORMED, str(path), f"invalid TOML: {exc}")
    errs = validate_profile_dict(data, repo_root)
    if errs:
        return errs[0]  # first violation; full list via validate_profile_dict

    def axis(name: str) -> AxisConfig:
        t = data.get(name, {})
        extras = {k: v for k, v in t.items() if k not in ("kind", "mcp", "cli")}
        return AxisConfig(
            kind=t.get("kind", ""),
            mcp=t.get("mcp", ""),
            cli=t.get("cli", ""),
            extras=extras,
        )

    return Profile(
        tracker=axis("tracker"),
        observability=axis("observability"),
        vcs=dict(data.get("vcs", {})),
        reproduce=dict(data.get("reproduce", {})),
    )


# ── Atomic writer (§D.3 invariant: temp-file + rename; never a half-written profile) ──
def _fmt_table(name: str, rows: list[tuple[str, str]]) -> str:
    out = [f"[{name}]"]
    for k, v in rows:
        out.append(f'{k} = "{v}"')
    return "\n".join(out)


def write_profile(data: dict, path: Path = Path("apex.profile.toml")) -> None:
    """Atomic write. Validates first (never writes a shape-violating profile).

    `_`-prefixed meta keys from the builder are NOT written as fields: `_gaps` becomes
    header comments (so a noted malformed-manifest gap reaches the file, not nowhere), and
    a section's `_conflict` becomes a real `# TODO:` comment line above that section."""
    errs = validate_profile_dict(data, path.resolve().parent)
    if errs:
        raise ValueError(f"refusing to write shape-violating profile: {errs[0]}")
    blocks = [
        "# apex.profile.toml — routing config only. NO secrets, ever.",
        "# Written by /apex:detect-stack; read by apex:investigate-bug.",
    ]
    for gap in (
        data.get("_gaps", []) or []
    ):  # surface noted detection gaps (S10), never silently drop
        blocks.append(f"# gap: {gap}")
    blocks.append("")
    order = ["tracker", "observability", "vcs", "reproduce"]
    for sec in order:
        if sec in data:
            tbl = data[sec]
            if tbl.get(
                "_conflict"
            ):  # render the unresolved-conflict TODO as a comment, not a field
                blocks.append(str(tbl["_conflict"]))
            rows = [(k, str(v)) for k, v in tbl.items() if not k.startswith("_")]
            blocks.append(_fmt_table(sec, rows))
            blocks.append("")
    text = "\n".join(blocks).rstrip() + "\n"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)  # atomic on POSIX


def _lint_cli(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: profile.py <path-to-apex.profile.toml>\n")
        return 2
    path = Path(argv[1])
    if not path.exists():
        sys.stderr.write(f"profile.py: not found: {path}\n")
        return 2
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        sys.stderr.write(f"[FAIL] MALFORMED: {exc}\n")
        return 2
    errs = validate_profile_dict(data, path.resolve().parent)
    if not errs:
        print(
            "[PASS] apex.profile.toml: all field values match their declared shape (no secrets)"
        )
        return 0
    for e in errs:
        sys.stderr.write(f"[FAIL] {e.code}: {e.field} — {e.message}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(_lint_cli(sys.argv))
