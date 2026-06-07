"""apex:detect-stack detectors — deps / CI / vcs probes + conflict rule + profile builder.

The pure, unit-testable half of detect-stack (design §D.1–D.3). The two parts that
need a live agent — the **connected-MCP probe** (a ToolSearch over `mcp__*` this
session) and **interactive prompting** for un-inferable fields — live in SKILL.md;
this module takes the MCP prefixes as an argument and emits the profile dict plus the
list of fields the agent must prompt for.

3 MVP probes (deps / CI / connected-MCP) + vcs via `git remote`. The env-var-NAMES
probe is PR-C (F3). Stdlib only (json/tomllib/subprocess/re).
"""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

# vendor dependency fingerprints → observability kind (deps probe, §D.1)
_OBS_DEP_FINGERPRINTS = {
    "datadog": ("@datadog/", "datadog", "dd-trace", "ddtrace"),
    "sentry": ("@sentry/", "sentry-sdk", "sentry_sdk", "raven"),
    "otel-honeycomb": ("@opentelemetry/", "opentelemetry", "honeycomb"),
}

# CI config locations → a CI host token (for conflicting-signal detection, §D.2)
_CI_SIGNALS = {
    "github": (".github/workflows",),
    "gitlab": (".gitlab-ci.yml",),
    "circle": (".circleci",),
}


# ── deps probe ────────────────────────────────────────────────────────────────
def _all_dep_strings(repo_root: Path) -> tuple[list[str], list[str]]:
    """Return (dep_tokens, gaps). A malformed manifest is a noted gap, never a crash (S10)."""
    deps: list[str] = []
    gaps: list[str] = []
    pj = repo_root / "package.json"
    if pj.exists():
        try:
            obj = json.loads(pj.read_text(encoding="utf-8"))
            for sect in ("dependencies", "devDependencies", "peerDependencies"):
                deps.extend((obj.get(sect) or {}).keys())
        except (json.JSONDecodeError, OSError, AttributeError):
            gaps.append("package.json: unparseable — skipped")
    pp = repo_root / "pyproject.toml"
    if pp.exists():
        try:
            obj = tomllib.loads(pp.read_text(encoding="utf-8"))
            proj = obj.get("project", {})
            deps.extend(proj.get("dependencies", []) or [])
            for grp in (proj.get("optional-dependencies", {}) or {}).values():
                deps.extend(grp)
        except (tomllib.TOMLDecodeError, OSError, AttributeError):
            gaps.append("pyproject.toml: unparseable — skipped")
    for fname in ("requirements.txt", "Gemfile"):
        f = repo_root / fname
        if f.exists():
            try:
                deps.extend(f.read_text(encoding="utf-8").splitlines())
            except OSError:
                gaps.append(f"{fname}: unreadable — skipped")
    return deps, gaps


def detect_deps(repo_root: Path) -> dict:
    """Infer observability kind from dependency fingerprints. {'observability_kind': str|None, 'gaps': [...]}"""
    deps, gaps = _all_dep_strings(repo_root)
    blob = "\n".join(deps).lower()
    obs_kind = None
    for kind, marks in _OBS_DEP_FINGERPRINTS.items():
        if any(m.lower() in blob for m in marks):
            obs_kind = kind
            break
    return {"observability_kind": obs_kind, "gaps": gaps}


# ── CI probe (for the conflicting-signal rule) ────────────────────────────────
def detect_ci(repo_root: Path) -> set[str]:
    found = set()
    for host, locs in _CI_SIGNALS.items():
        for loc in locs:
            if (repo_root / loc).exists():
                found.add(host)
    return found


# ── vcs probe ─────────────────────────────────────────────────────────────────
def parse_remote_url(url: str) -> dict:
    """Parse host + owner/repo from a git remote URL (https or ssh). Pure + testable."""
    url = url.strip()
    m = re.match(r"git@([^:]+):(.+?)(?:\.git)?$", url)  # ssh
    if not m:
        m = re.match(
            r"(?:https?|ssh)://(?:[^@]+@)?([^/]+)/(.+?)(?:\.git)?$", url
        )  # https/ssh-url
    if not m:
        return {}
    host = m.group(1)
    repo = m.group(2)
    host_kind = (
        "github" if "github" in host else ("gitlab" if "gitlab" in host else host)
    )
    return {"host": host_kind, "repo": repo}


def detect_vcs(repo_root: Path) -> dict:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if out.returncode == 0:
            return parse_remote_url(out.stdout)
    except (OSError, subprocess.SubprocessError):
        pass
    return {}


# ── conflict rule (§D.2) ──────────────────────────────────────────────────────
def resolve_tracker_kind(vcs_host: str | None, ci: set[str]) -> tuple[str, str | None]:
    """Return (kind, conflict_note). Conflicting signals → ("", note) — never silently pick (U7)."""
    hosts = set()
    if vcs_host in ("github", "gitlab"):
        hosts.add(vcs_host)
    hosts |= {c for c in ci if c in ("github", "gitlab")}
    if len(hosts) > 1:
        return "", f"# TODO: resolve (conflicting signals: {', '.join(sorted(hosts))})"
    if len(hosts) == 1:
        return next(iter(hosts)), None
    return "", None  # no signal → un-inferable (D.3)


# ── profile builder (AC7 un-inferable + AC2b no-drop + re-run preservation) ────
def build_profile(
    repo_root: Path,
    mcp_prefixes: list[str] | None = None,
    existing: dict | None = None,
) -> tuple[dict, list[str]]:
    """Assemble the profile dict + the list of un-inferable fields the agent must prompt for.

    mcp_prefixes: connected `mcp__<server>__*` strings (the agent's ToolSearch result;
    None = unattended re-detect, blind to MCP → preserve existing mcp, U8).
    """
    deps = detect_deps(repo_root)
    ci = detect_ci(repo_root)
    vcs = detect_vcs(repo_root)
    existing = existing or {}
    unattended = mcp_prefixes is None
    prompts: list[str] = []

    def mcp_for(vendor_hint: str, prior: str) -> str:
        # AC2b: record an available binding; U8: unattended preserves the prior mcp.
        if unattended:
            return prior
        for pref in mcp_prefixes or []:
            if vendor_hint and vendor_hint in pref:
                return pref
        return prior  # none matched → keep prior (honest-empty if none)

    def cli_for(cmd: str, prior: str) -> str:
        # AC2b no-drop: if the command is on PATH, record it; else honest-empty.
        if _on_path(cmd):
            return cmd
        return prior

    # tracker
    t_prev = existing.get("tracker", {})
    t_kind, t_conflict = resolve_tracker_kind(vcs.get("host"), ci)
    if t_conflict:
        prompts.append("tracker.kind (conflicting signals)")
    elif not t_kind and not t_prev.get("kind"):
        prompts.append("tracker.kind")
    tracker = {
        "kind": t_kind or t_prev.get("kind", ""),
        "mcp": mcp_for("github", t_prev.get("mcp", "")),
        "cli": cli_for("gh", t_prev.get("cli", "")),
    }
    if t_conflict:
        tracker["_conflict"] = t_conflict

    # observability
    o_prev = existing.get("observability", {})
    o_kind = deps["observability_kind"] or o_prev.get("kind", "") or "console"
    # grep is the backend ONLY for the console kind; for a vendor obs kind (datadog/sentry)
    # the MVP ships no adapter (PR-C), so leave cli honest-empty → ask-user, never bind grep
    # to a Datadog axis (the AC7 no-guess / AC2b record-what's-actually-available rule, M2).
    obs_cli = (
        cli_for("grep", o_prev.get("cli", ""))
        if o_kind == "console"
        else o_prev.get("cli", "")
    )
    obs = {
        "kind": o_kind,
        "mcp": mcp_for(o_kind, o_prev.get("mcp", "")),
        "cli": obs_cli,
    }
    if o_kind == "console":
        obs["log_path"] = o_prev.get("log_path", "")
        if not obs["log_path"]:
            prompts.append("observability.log_path")

    profile = {"tracker": tracker, "observability": obs}
    if vcs:
        profile["vcs"] = {"host": vcs.get("host", ""), "repo": vcs.get("repo", "")}
    elif existing.get("vcs"):
        profile["vcs"] = existing["vcs"]
    if existing.get("reproduce"):
        profile["reproduce"] = existing["reproduce"]

    profile["_gaps"] = deps["gaps"]
    return profile, prompts


def _on_path(cmd: str) -> bool:
    import shutil

    return shutil.which(cmd) is not None
