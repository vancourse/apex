"""SessionStart: where this session stands, in at most ~600 tokens (design R30, R20).

Prints only what changes what the session should do: retired history under
this worktree, the main folder's distance from trunk (fast-forwarding it when
rails/mainsync.py says that is safe), its claim (or that it has none), the
operator's hold, its open PR, unverified items, forged receipts, the leak
snapshot's age, gates still in shadow, and CI spend once it passes 70% of the
included minutes. Touches the heartbeat the repo canary reads. No network
calls: everything comes from the local store and local git refs.
"""

from __future__ import annotations

import datetime as _dt
import time

from rails import VERSION, store
from rails.hookio import Event, Notice

NAME = "state"
MAX_CHARS = 2400  # ~600 tokens


def _shadow_rows() -> list[str]:
    from rails.dispatch import load_registry

    today = _dt.date.today()
    try:
        return [
            f"{r.name} (until {r.shadow_until or 'promoted by hand'})"
            for r in load_registry()
            if r.shadowed(today)
        ]
    except Exception:  # noqa: BLE001
        return []


def _history_lines(repo: store.RepoId, session_id: str, act: bool) -> list[str]:
    """Retired history under this worktree, and the main folder's distance from trunk."""
    from rails import history, mainsync

    lines: list[str] = []
    try:
        retired = history.load(repo.top)
        head = history.resolve(repo.top, "HEAD") if retired else None
        if retired and retired.problems:
            lines.append(f"retired history: cannot check ({retired.problems[0]}); pushes refuse")
        elif retired and head and (base := retired.carried_by(head)):
            lines.append(
                f"RETIRED HISTORY: this worktree is built on {base[:12]}, which {retired.trunk} rewrote away. "
                f"Pushes refuse. Cut a fresh worktree from {retired.trunk} and cherry-pick only your own commits."
            )
    except Exception:  # noqa: BLE001 - a notice must never break SessionStart
        pass
    try:
        line = (
            mainsync.at_session_start(repo, session_id)
            if act
            else mainsync.plan(repo, session_id).line
        )
    except Exception:  # noqa: BLE001
        line = None
    if line:
        lines.append(line)
    return lines


def render(repo: store.RepoId, session_id: str = "", act: bool = False) -> str:
    from rails import claims, leak, receipts, work

    lines = [f"RAILS {VERSION} | {repo.main.name} | worktree {repo.leaf}"]
    lines.extend(_history_lines(repo, session_id, act))
    mine = claims.mine(repo)
    if mine and mine.items:
        kind = f" [{mine.kind}]" if mine.kind else ""
        lines.append(f"claim{kind}: {', '.join(mine.items)[:300]}")
    else:
        lines.append(
            'claim: none. Before the first source edit: rails claim "#<issue>" | --milestone "<title>" | --adhoc "<line>"'
        )
    others = [c for c in claims.load(repo) if c.leaf != repo.leaf and c.items]
    if others:
        lines.append(
            f"others: {len(others)} worktree(s) hold claims ({', '.join(c.leaf for c in others[:6])}); `rails claim --list`"
        )
    state = store.read_json(repo.dir / "state.json", {}) or {}
    hold = state.get("hold") or {}
    if hold.get("on"):
        lines.append(
            f"HOLD is on (since {hold.get('since')}): pushes refuse until the operator says `release`"
        )
    pr = store.read_json(repo.leaf_dir / "pr.json", None)
    if isinstance(pr, dict) and pr.get("number"):
        armed = "armed" if pr.get("armed") else "NOT armed"
        lines.append(
            f"PR #{pr['number']} ({armed}; monitor {pr.get('monitor', 'unbound')})"
        )
    data = work.load(repo)
    unverified = [i["id"] for i in data["items"] if i.get("status") == "unverified"]
    opened = [i["id"] for i in data["items"] if i.get("status") == "open"]
    if unverified:
        lines.append(
            f"UNVERIFIED (recorded debt; `rails ship` refuses Closes while these stand): {', '.join(unverified)}"
        )
    if opened:
        lines.append(f"open items: {', '.join(opened[:12])}")
    bad = receipts.forged(repo, since=time.time() - 7 * 86400)
    if bad:
        lines.append(
            f"FORGED receipts in 7 days: {len(bad)} (a receipt no rails command was seen writing)"
        )
    if (repo.top / "rails" / "leak.toml").is_file():
        snap = leak.load_snapshot(repo)
        if snap is None:
            lines.append(
                "leak snapshot: MISSING - the operator runs `rails snapshot` from their own shell (fails closed once shadow ends)"
            )
        elif snap.age_days > leak.MAX_AGE_DAYS - 3:
            lines.append(
                f"leak snapshot: {snap.age_days:.0f} days old (refused at {leak.MAX_AGE_DAYS}); operator: `rails snapshot`"
            )
    shadow = _shadow_rows()
    if shadow:
        lines.append(f"shadow (log, never refuse): {', '.join(shadow)[:300]}")
    metrics = store.read_json(repo.dir / "metrics.json", None)
    if isinstance(metrics, dict) and metrics.get("included_minutes"):
        used = metrics.get("minutes_month", 0)
        cap = metrics["included_minutes"]
        if used > 0.7 * cap:
            lines.append(
                f"CI minutes {used:.0f}/{cap} this month ({used / cap:.0%}); keep work on the laptop lanes"
            )
    lines.append(
        "loop: claim -> intent shown -> commit -> rails check -> push -> rails ship -> walk -> operator `used`"
    )
    text = "\n".join(lines)
    return text[:MAX_CHARS]


def check(evt: Event):
    store.touch_heartbeat()
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    return Notice(render(repo, evt.session_id, act=True))
