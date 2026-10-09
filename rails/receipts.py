"""Receipts: what a rails command observed, written by the command, sealed with an HMAC.

Design R25. A receipt is integrity against rewording and accidental overwrite,
**not** proof against a deliberate agent: on a single-user box the key is one
indirection away. So forging is made *detectable*: every receipt written from
inside a Claude Code tool call (``CLAUDECODE=1``) is expected to have a matching
``rails-cmd`` line in the firing log, written by the PostToolUse hook from the
command it watched run. A receipt with no such line is reported ``forged``.

Markers are the receipts' summary for the push gate: ``check-<sha>.ok`` exists
only when every lane the diff selected passed at that commit.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from rails import store
from rails.gitutil import in_agent


def _key() -> bytes:
    path = store.data_root() / "receipts.key"
    try:
        return bytes.fromhex(path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        with store.locked(path):
            if not path.exists():
                path.write_text(key, encoding="ascii")
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
        return bytes.fromhex(path.read_text(encoding="ascii").strip())


def _canonical(body: dict[str, Any]) -> bytes:
    return json.dumps(
        {k: v for k, v in body.items() if k != "hmac"},
        sort_keys=True,
        ensure_ascii=True,
    ).encode()


def seal(body: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(body)
    sealed["hmac"] = hmac.new(_key(), _canonical(body), hashlib.sha256).hexdigest()
    return sealed


def valid(body: dict[str, Any]) -> bool:
    claimed = body.get("hmac")
    if not isinstance(claimed, str):
        return False
    expected = hmac.new(_key(), _canonical(body), hashlib.sha256).hexdigest()
    return hmac.compare_digest(claimed, expected)


def write(repo: store.RepoId, kind: str, **fields: Any) -> dict[str, Any]:
    body = {
        **fields,
        "kind": kind,
        "ts": int(time.time()),
        "leaf": repo.leaf,
        "via_agent": in_agent(),
    }
    sealed = seal(body)
    store.append_jsonl(repo.leaf_dir / "receipts.jsonl", sealed)
    return sealed


def read(
    repo: store.RepoId, kind: str | None = None, **match: Any
) -> list[dict[str, Any]]:
    rows = store.read_jsonl(repo.leaf_dir / "receipts.jsonl")
    out = []
    for row in rows:
        if kind and row.get("kind") != kind:
            continue
        if any(row.get(k) != v for k, v in match.items()):
            continue
        out.append(row)
    return out


def latest_by(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[str(row.get(key))] = row  # rows are append-ordered, so the last one wins
    return out


# --- markers --------------------------------------------------------------------


def marker_path(repo: store.RepoId, sha: str, quick: bool) -> Path:
    suffix = "quick.ok" if quick else "ok"
    return repo.leaf_dir / "markers" / f"check-{sha}.{suffix}"


def write_marker(
    repo: store.RepoId, sha: str, tree: str, lanes: list[str], quick: bool
) -> Path:
    path = marker_path(repo, sha, quick)
    body = seal(
        {
            "sha": sha,
            "tree": tree,
            "lanes": sorted(lanes),
            "quick": quick,
            "ts": int(time.time()),
        }
    )
    store.write_json(path, body)
    return path


def read_marker(repo: store.RepoId, sha: str, quick: bool) -> dict[str, Any] | None:
    """The marker for `sha`, only if its seal holds and it names `sha`."""
    body = store.read_json(marker_path(repo, sha, quick))
    if not isinstance(body, dict) or not valid(body) or body.get("sha") != sha:
        return None
    return body


def has_marker(repo: store.RepoId, sha: str, *, full: bool) -> bool:
    """A full marker satisfies a quick requirement; a quick one never satisfies full."""
    if read_marker(repo, sha, quick=False):
        return True
    return not full and read_marker(repo, sha, quick=True) is not None


def forged(
    repo: store.RepoId, since: float, window: float = 4 * 3600
) -> list[dict[str, Any]]:
    """Agent-written receipts with no rails-cmd firing within `window` seconds after them.

    The PostToolUse firing lands when the command ENDS, so for a long `rails
    check` it can follow the receipt by the whole lane runtime.
    """
    firings = [
        f
        for f in store.read_jsonl(repo.dir / "firings.jsonl")
        if f.get("gate") == "receipt_writer" and f.get("leaf") == repo.leaf
    ]
    times = sorted(int(f.get("ts", 0)) for f in firings)
    bad = []
    for row in read(repo):
        if not row.get("via_agent") or row.get("ts", 0) < since:
            continue
        ts = int(row.get("ts", 0))
        # The PostToolUse firing lands AFTER the command ends, so it follows the receipt.
        if not any(ts - 5 <= t <= ts + window for t in times):
            bad.append(row)
    return bad
