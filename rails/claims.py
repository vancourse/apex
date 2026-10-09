"""Claims: what each worktree says it holds (design R23, R18, R30).

Reads and writes the SAME file jarvis's ``.claude/hooks/claim.py`` uses —
``~/.claude/repo-claims/<slug>.json`` = ``{"claims": {leaf: {branch, items, at}}}``
under the same ``<slug>.lock`` — so the two tools see one set of claims while
the repo migrates. Rails-only facts (the claim's kind, an adhoc line, the app
paths it touched) live beside it in ``<store>/<repo>/claim_meta.json``, because
jarvis's writer rewrites every row from its own three fields and would drop
anything extra.

WIP = 1 app: a second ``release`` milestone is refused while another worktree
holds one the operator has not marked ``used``; ``harness``, ``prep`` and
``fix`` claims are exempt, and ``--wip-override "<reason>"`` is logged.
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from rails import store

KINDS = ("release", "harness", "prep", "fix", "adhoc")


def config_home() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".claude"


def slug(path: Path) -> str:
    return "".join(c if c.isalnum() else "-" for c in str(path))


def claims_path(main: Path) -> Path:
    return config_home() / "repo-claims" / f"{slug(main)}.json"


@contextlib.contextmanager
def _lock(main: Path) -> Iterator[None]:
    """The exact lock jarvis's _claimstore takes: byte 0 of `<slug>.lock`."""
    path = claims_path(main).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + 5
    with path.open("a+b") as handle:
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("claim store is busy; retry shortly")
                time.sleep(0.05)
        try:
            yield
        finally:
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def _read(main: Path) -> dict:
    try:
        raw = json.loads(claims_path(main).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return {}
    entries = raw.get("claims") if isinstance(raw, dict) else None
    return entries if isinstance(entries, dict) else {}


def _write(main: Path, entries: dict) -> None:
    path = claims_path(main)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"claims": entries}, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    os.replace(tmp, path)


@dataclass
class Claim:
    leaf: str
    branch: str
    items: list[str]
    at: str
    kind: str = ""
    adhoc: str = ""
    paths: list[str] = field(default_factory=list)


def _meta_path(repo: store.RepoId) -> Path:
    return repo.dir / "claim_meta.json"


def load(repo: store.RepoId) -> list[Claim]:
    meta = store.read_json(_meta_path(repo), {}) or {}
    out = []
    for leaf, body in sorted(_read(repo.main).items()):
        if not isinstance(body, dict) or not isinstance(body.get("items"), list):
            continue
        m = meta.get(leaf, {}) if isinstance(meta, dict) else {}
        out.append(
            Claim(
                leaf=leaf,
                branch=str(body.get("branch") or ""),
                items=[str(i) for i in body["items"]],
                at=str(body.get("at") or ""),
                kind=str(m.get("kind", "")),
                adhoc=str(m.get("adhoc", "")),
                paths=list(m.get("paths", [])),
            )
        )
    return out


def mine(repo: store.RepoId) -> Claim | None:
    for claim in load(repo):
        if claim.leaf == repo.leaf:
            return claim
    return None


def used_milestones(repo: store.RepoId) -> set[str]:
    state = store.read_json(repo.dir / "state.json", {}) or {}
    return {
        str(u.get("milestone")) for u in state.get("used", []) if isinstance(u, dict)
    }


def wip_conflict(repo: store.RepoId, milestone: str) -> Claim | None:
    """Another worktree's unused release milestone, if one blocks this one."""
    used = used_milestones(repo)
    for claim in load(repo):
        if claim.leaf == repo.leaf or claim.kind != "release":
            continue
        for item in claim.items:
            if not item.startswith("#") and item != milestone and item not in used:
                return claim
    return None


def _live_leaves(main: Path) -> set[str] | None:
    """Leaf names of the worktrees git lists; None when git cannot say (then every holder is live)."""
    import subprocess

    try:
        done = subprocess.run(
            ["git", "-C", str(main), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    return {
        Path(line.split(" ", 1)[1].strip()).name
        for line in done.stdout.splitlines()
        if line.startswith("worktree ")
    }


def add(
    repo: store.RepoId,
    branch: str,
    items: list[str],
    *,
    kind: str = "",
    adhoc: str = "",
    wip_override: str = "",
) -> tuple[bool, str]:
    items = [i.strip() for i in items if i.strip()]
    if kind == "release":
        for item in items:
            if item.startswith("#"):
                continue
            blocker = wip_conflict(repo, item)
            if blocker and not wip_override:
                return False, (
                    f"refused: {blocker.leaf} holds release milestone(s) {blocker.items} that the operator has not marked "
                    f"`used`. WIP is one app at a time. Claim this as `--kind prep` (declarations, tests, spec only), "
                    f'or the operator raises the limit with --wip-override "<reason>".'
                )
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    live = _live_leaves(repo.main)
    with _lock(repo.main):
        entries = _read(repo.main)
        # An issue is held by one worktree at a time, as jarvis's claim.py has it: two
        # sessions on one issue is how a finished slice ends up behind a conflict (1.3.0).
        exclusive = {i for i in items if i.startswith("#") and i[1:].isdigit()}
        for leaf, other in entries.items():
            if leaf == repo.leaf or not isinstance(other, dict) or (live is not None and leaf not in live):
                continue
            held = sorted(exclusive & set(other.get("items", [])))
            if held:
                return False, (
                    f"refused: {', '.join(held)} already held by {leaf} (branch {other.get('branch', '?')}). "
                    "Join that worktree, or its owner releases it (`rails claim --release` there)."
                )
        body = (
            entries.get(repo.leaf) if isinstance(entries.get(repo.leaf), dict) else None
        )
        if body is None:
            body = {"branch": branch, "items": [], "at": now}
        # A worktree that switches branch keeps its claim (jarvis #2599): the worktree is the
        # line of work; its owner releases what it no longer holds.
        body["branch"] = branch
        for item in items:
            if item not in body["items"]:
                body["items"].append(item)
        body["at"] = now
        entries[repo.leaf] = body
        _write(repo.main, entries)
    with store.updating(_meta_path(repo), {}) as meta:
        m = meta.setdefault(repo.leaf, {})
        if kind:
            m["kind"] = kind
        if adhoc:
            m["adhoc"] = adhoc
        if wip_override:
            m.setdefault("wip_overrides", []).append({"at": now, "why": wip_override})
    return True, f"{repo.leaf} now holds: {', '.join(body['items'])}"


def release(repo: store.RepoId) -> str:
    with _lock(repo.main):
        entries = _read(repo.main)
        gone = entries.pop(repo.leaf, None)
        _write(repo.main, entries)
    with store.updating(_meta_path(repo), {}) as meta:
        meta.pop(repo.leaf, None)
    return f"released {repo.leaf}" if gone else f"{repo.leaf} held nothing"


def record_paths(repo: store.RepoId, paths: list[str]) -> None:
    with store.updating(_meta_path(repo), {}) as meta:
        m = meta.setdefault(repo.leaf, {})
        known = set(m.get("paths", []))
        for p in paths:
            if p not in known:
                known.add(p)
        m["paths"] = sorted(known)[:500]
