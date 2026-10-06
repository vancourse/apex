"""`rails metrics`: what the harness costs and what it catches (design R22).

CI spend comes from GitHub's billing usage API
(``orgs/<org>/settings/billing/usage?year=&month=``, or the user endpoint for a
personal repo), filtered to this repo's Actions minutes. Gate firings, the
ceremony log and forged receipts come from the local store. Nothing is read
from the transcript jsonl.

The result is cached in ``<store>/<repo>/metrics.json``; SessionStart prints a
line from it once month-to-date minutes pass 70% of the budget's
``included_minutes`` (``[budget]`` in the repo's ``rails/gates.toml``).
"""

from __future__ import annotations

import argparse
import collections
import datetime as _dt
import sys
import time
import tomllib
from pathlib import Path
from typing import Any

from rails import receipts, store
from rails.gitutil import GitError, gh_api, origin_slug


def budget(top: Path) -> dict[str, Any]:
    path = top / "rails" / "gates.toml"
    try:
        return tomllib.loads(path.read_text(encoding="utf-8")).get("budget", {})
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def summarise_usage(items: list[dict[str, Any]], repo_name: str) -> dict[str, float]:
    minutes = 0.0
    gross = 0.0
    net = 0.0
    for item in items:
        if item.get("product") != "actions" or item.get("repositoryName") != repo_name:
            continue
        if item.get("unitType") == "Minutes":
            minutes += float(item.get("quantity", 0))
        gross += float(item.get("grossAmount", 0))
        net += float(item.get("netAmount", 0))
    return {
        "minutes_month": round(minutes, 1),
        "gross_month": round(gross, 2),
        "net_month": round(net, 2),
    }


def line_for(metrics: dict[str, Any]) -> str | None:
    cap = metrics.get("included_minutes")
    used = metrics.get("minutes_month", 0)
    if not cap or used <= 0.7 * cap:
        return None
    return f"CI minutes {used:.0f}/{cap} this month ({used / cap:.0%}); keep work on the laptop lanes"


def collect(
    top: Path, repo: store.RepoId, today: _dt.date | None = None
) -> dict[str, Any]:
    today = today or _dt.date.today()
    slug = origin_slug(top) or "/"
    owner, _, name = slug.partition("/")
    out: dict[str, Any] = {
        "repo": slug,
        "month": f"{today:%Y-%m}",
        "at": int(time.time()),
    }
    for endpoint in (
        f"orgs/{owner}/settings/billing/usage",
        f"users/{owner}/settings/billing/usage",
    ):
        try:
            data = gh_api(top, f"{endpoint}?year={today.year}&month={today.month}")
        except GitError:
            continue
        out.update(summarise_usage(data.get("usageItems", []), name))
        out["source"] = endpoint
        break
    else:
        out["source"] = "unavailable (needs a token that can read billing usage)"
    b = budget(top)
    if b:
        out["included_minutes"] = b.get("included_minutes")
        out["spend_limit"] = b.get("spend_limit")
    if today.day > 0 and out.get("minutes_month"):
        days = (
            _dt.date(today.year + (today.month == 12), today.month % 12 + 1, 1)
            - _dt.timedelta(days=1)
        ).day
        out["projected_month"] = round(out["minutes_month"] / today.day * days)
    firings = store.read_jsonl(repo.dir / "firings.jsonl")
    since = time.time() - 30 * 86400
    counter: collections.Counter = collections.Counter()
    for f in firings:
        if f.get("ts", 0) >= since and f.get("verdict") in (
            "deny",
            "would-deny",
            "block",
            "would-block",
            "missing",
            "crashed",
        ):
            counter[f"{f.get('gate')}:{f.get('verdict')}"] += 1
    out["firings_30d"] = dict(counter.most_common())
    ceremony = [
        c
        for c in store.read_jsonl(repo.dir / "ceremony.jsonl")
        if c.get("ts", 0) >= since
    ]
    if ceremony:
        kinds = collections.Counter(c.get("class") for c in ceremony)
        ceremonial = sum(kinds[k] for k in ("approve", "push", "merge"))
        out["ceremony_30d"] = {
            "messages": len(ceremony),
            "ceremony_share": round(ceremonial / len(ceremony), 3),
            **dict(kinds),
        }
    out["forged_30d"] = len(receipts.forged(repo, since=since))
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="rails metrics")
    ap.parse_args(argv)
    top = Path.cwd()
    repo = store.find_repo(top)
    if repo is None:
        print("rails metrics: not inside a git checkout")
        return 2
    metrics = collect(repo.top, repo)
    store.write_json(repo.dir / "metrics.json", metrics)
    print(
        f"rails metrics for {metrics['repo']} ({metrics['month']}), source: {metrics['source']}"
    )
    if "minutes_month" in metrics:
        print(
            f"  Actions minutes this month: {metrics['minutes_month']:.0f} (net ${metrics.get('net_month', 0):.2f})"
        )
        if metrics.get("projected_month"):
            print(f"  projected for the month: {metrics['projected_month']} min")
        if metrics.get("included_minutes"):
            print(f"  included: {metrics['included_minutes']} min")
    for key, value in metrics.get("firings_30d", {}).items():
        print(f"  firing (30d) {key}: {value}")
    if metrics.get("ceremony_30d"):
        print(
            f"  ceremony share (30d): {metrics['ceremony_30d']['ceremony_share']:.0%} of {metrics['ceremony_30d']['messages']} messages"
        )
    print(f"  forged receipts (30d): {metrics['forged_30d']}")
    line = line_for(metrics)
    if line:
        print("  " + line)
    return 0
