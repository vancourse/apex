"""The design's four numbers (section 11.1), before the cut and since, by one method.

"Did the harness help?" needs a before and an after measured the SAME way. The
evidence report's baselines (rework 58.4%, automation catch ~10%, harness 44% of red
CI jobs) came from a model classifying commits and logs, which no script reproduces;
they are printed beside these as a different instrument, never compared with them.

The cut is the trunk commit that added ``rails/lanes.toml`` (the day the repo started
running its lanes on the laptop). "before" is the 30 days before it; "since" is the cut
to now, capped at the last 30 days.

* **Rework (code churn)** - of the lines trunk commits landed, the share rewritten or
  deleted within 14 days: each commit's added lines, blamed at the last trunk commit 14
  days later (``git blame --since`` the commit, so older history is never walked). Did
  the work land right the first time. Squash merges make one PR one commit, so iteration
  inside a PR is not churn; a later PR redoing it is. Lock files and any file with more
  than 1,000 lines added in one commit (generated or vendored) are skipped, and so is a
  file gone by then (renamed or deleted: no line-level answer). A commit counts once it
  is 14 days old, so "since" first reads 14 days after the cut. git only.
  (Measured 2026-10-06 and dropped: "commits that rewrite a line younger than 14 days"
  read 87% before the cut on jarvis - nearly every commit touches recent code, so it
  could not move.)
* **Automation catch rate** - of merged PRs carrying ``Detected-by:`` (``rails ship
  --detected-by``), the share whose value is an automated instrument. Nothing carried
  it before the cut, so "before" is the evidence report's figure, labelled as such.
* **Ceremony share** - the existing ``UserPromptSubmit`` log (rails/gates/prompt_words.py).
* **Harness share of red CI jobs** - of failed Actions jobs (an aggregating ``gate``
  job is skipped when another job of the same attempt failed: it only mirrors it), the
  share NOT caused by the code: the job never got past runner setup, or the same
  workflow passed on the same commit (a re-run or a later run: same code, other
  result). A gate wrong on every run (the sherpa-geometry kind) counts as code here;
  the number is a floor on harness noise, not the whole of it.

Everything slow is cached per commit / per run in ``<store>/<repo>/numbers_cache.json``:
a commit's blame and a completed run's jobs never change.
"""

from __future__ import annotations

import concurrent.futures
import datetime as _dt
import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rails import history, store

WINDOW_DAYS = 30
CHURN_DAYS = 14
MAX_ADDED_PER_FILE = 1000
AUTOMATED = ("ci", "lane", "hook", "walk", "boot")
DETECTED_BY = (*AUTOMATED, "review", "audit", "operator", "agent")
DETECTED_RE = re.compile(r"(?im)^detected-by:\s*([a-z-]+)")
LOCKFILE_RE = re.compile(
    r"(^|/)(uv\.lock|pnpm-lock\.yaml|package-lock\.json|poetry\.lock|Cargo\.lock|yarn\.lock)$"
)
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,(\d+))? @@")
MAX_FILES = 25
SETUP_STEPS = ("set up job", "set up runner")


@dataclass
class Window:
    label: str
    start: float
    end: float

    @property
    def days(self) -> float:
        return max((self.end - self.start) / 86400, 0.0)

    def iso(self, ts: float) -> str:
        return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(top: Path, *args: str, timeout: float = 120) -> tuple[int, str]:
    return history._git(top, *args, timeout=timeout)


def cut(top: Path, trunk: str) -> float | None:
    code, out = _git(top, "log", "--diff-filter=A", "--format=%ct", trunk, "--", "rails/lanes.toml")
    stamps = [int(x) for x in out.split()] if code == 0 else []
    return float(min(stamps)) if stamps else None


def windows(cut_ts: float, now: float) -> tuple[Window, Window]:
    span = WINDOW_DAYS * 86400
    return (
        Window("before", cut_ts - span, cut_ts),
        Window("since", max(cut_ts, now - span), now),
    )


# --- rework (code churn) -------------------------------------------------------------------


def trunk_commits(top: Path, trunk: str, w: Window) -> list[tuple[str, int]]:
    code, out = _git(
        top,
        "log",
        "--first-parent",
        "--format=%H %ct",
        f"--since={w.iso(w.start)}",
        f"--until={w.iso(w.end)}",
        trunk,
    )
    rows = []
    for line in out.splitlines() if code == 0 else []:
        sha, _, ct = line.partition(" ")
        if ct.isdigit() and w.start <= int(ct) < w.end:
            rows.append((sha, int(ct)))
    return rows


def _iso(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def added_lines(top: Path, sha: str) -> dict[str, int]:
    """Lines each file gained in `sha` (lock files and >MAX_ADDED_PER_FILE generated files skipped)."""
    code, out = _git(top, "diff", "-U0", "--no-color", "--no-renames", "--no-ext-diff", f"{sha}^", sha)
    added: dict[str, int] = {}
    path = None
    for line in out.splitlines() if code == 0 else []:
        if line.startswith("+++ "):
            name = line[4:]
            path = name[2:] if name.startswith("b/") and not LOCKFILE_RE.search(name[2:]) else None
        elif line.startswith("@@ ") and path:
            m = HUNK_RE.match(line)
            if m:
                count = int(m.group(1)) if m.group(1) is not None else 1
                if count:
                    added[path] = added.get(path, 0) + count
    return {p: n for p, n in added.items() if n <= MAX_ADDED_PER_FILE}


def revision_at(top: Path, trunk: str, ts: float) -> str | None:
    code, out = _git(top, "rev-list", "-1", "--first-parent", f"--before={_iso(ts)}", trunk)
    return (out or None) if code == 0 else None


def churn_of(top: Path, trunk: str, sha: str, ct: int) -> list[int] | None:
    """[lines added, of them rewritten or deleted within CHURN_DAYS], or None if nothing countable."""
    added = added_lines(top, sha)
    if not added:
        return None
    at = revision_at(top, trunk, ct + CHURN_DAYS * 86400) or sha
    total = churned = 0
    for path, count in list(added.items())[:MAX_FILES]:
        code, out = _git(top, "blame", "--porcelain", f"--since={_iso(ct - 1)}", at, "--", path)
        if code != 0:
            continue  # renamed or deleted by then: no line-level answer either way
        survived = sum(1 for line in out.splitlines() if line.startswith(sha + " "))
        total += count
        churned += max(count - survived, 0)
    return [total, churned] if total else None


def churn_share(
    top: Path, trunk: str, w: Window, cache: dict[str, Any], now: float | None = None
) -> dict[str, Any]:
    now = time.time() if now is None else now
    memo: dict[str, Any] = cache.setdefault("churn", {})
    commits = trunk_commits(top, trunk, w)
    matured = [(sha, ct) for sha, ct in commits if ct + CHURN_DAYS * 86400 <= now]
    todo = [(sha, ct) for sha, ct in matured if sha not in memo]
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for (sha, _), result in zip(todo, pool.map(lambda r: churn_of(top, trunk, *r), todo)):
                memo[sha] = result
    rows = [memo[sha] for sha, _ in matured if memo.get(sha)]
    added = sum(r[0] for r in rows)
    churned = sum(r[1] for r in rows)
    first = min((ct for sha, ct in commits if (sha, ct) not in matured), default=None)
    return {
        "share": round(churned / added, 3) if added else None,
        "churned": churned,
        "added": added,
        "commits": len(rows),
        "pending": len(commits) - len(matured),
        "first_reading": _iso(first + CHURN_DAYS * 86400)[:10] if first and not rows else None,
    }


# --- automation catch rate ----------------------------------------------------


def merged_prs(top: Path, w: Window) -> list[dict[str, Any]] | None:
    day = lambda ts: _dt.datetime.fromtimestamp(ts, _dt.timezone.utc).strftime("%Y-%m-%d")  # noqa: E731
    try:
        done = subprocess.run(
            [
                "gh", "pr", "list", "--state", "merged", "--limit", "500",
                "--search", f"merged:{day(w.start)}..{day(w.end)}",
                "--json", "number,title,body,mergedAt",
            ],
            cwd=str(top), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    try:
        rows = json.loads(done.stdout or "[]")
    except ValueError:
        return None
    out = []
    for row in rows:
        stamp = _dt.datetime.fromisoformat(str(row.get("mergedAt", "")).replace("Z", "+00:00")).timestamp()
        if w.start <= stamp < w.end:
            out.append(row)
    return out


def catch_rate(prs: list[dict[str, Any]]) -> dict[str, Any]:
    tagged = []
    for pr in prs:
        m = DETECTED_RE.search(pr.get("body") or "")
        if m:
            tagged.append(m.group(1).lower())
    automated = sum(1 for t in tagged if t in AUTOMATED)
    return {
        "share": round(automated / len(tagged), 3) if tagged else None,
        "automated": automated,
        "tagged": len(tagged),
        "merged": len(prs),
    }


# --- harness share of red CI jobs ---------------------------------------------


def _gh_json(top: Path, path: str) -> Any:
    try:
        done = subprocess.run(
            ["gh", "api", path], cwd=str(top), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout or "null")
    except ValueError:
        return None


def runs(top: Path, slug: str, w: Window) -> list[dict[str, Any]] | None:
    """Every workflow run created in the window (7-day slices: the API caps a query at 1,000)."""
    out: list[dict[str, Any]] = []
    t = w.start
    while t < w.end:
        end = min(t + 7 * 86400, w.end)
        a = _dt.datetime.fromtimestamp(t, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        b = _dt.datetime.fromtimestamp(end, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for page in range(1, 11):
            data = _gh_json(top, f"repos/{slug}/actions/runs?created={a}..{b}&per_page=100&page={page}")
            if data is None:
                return None
            batch = data.get("workflow_runs", [])
            out.extend(
                {
                    "id": r["id"],
                    "workflow_id": r.get("workflow_id"),
                    "head_sha": r.get("head_sha"),
                    "status": r.get("status"),
                    "conclusion": r.get("conclusion"),
                    "run_attempt": r.get("run_attempt", 1),
                }
                for r in batch
            )
            if len(batch) < 100:
                break
        t = end
    return out


def failed_jobs(top: Path, slug: str, run: dict[str, Any], memo: dict[str, Any]) -> list[dict[str, Any]] | None:
    key = f"{run['id']}:{run['run_attempt']}"
    if key in memo:
        return memo[key]
    data = _gh_json(top, f"repos/{slug}/actions/runs/{run['id']}/jobs?filter=all&per_page=100")
    if data is None:
        return None
    jobs = [
        {
            "name": j.get("name", ""),
            "attempt": j.get("run_attempt", 1),
            "setup_only": not any(
                s.get("conclusion") in ("success", "failure")
                and not str(s.get("name", "")).lower().startswith(SETUP_STEPS)
                for s in (j.get("steps") or [])
            ),
        }
        for j in data.get("jobs", [])
        if j.get("conclusion") == "failure"
    ]
    if run.get("status") == "completed":
        memo[key] = jobs
    return jobs


def harness_share(top: Path, slug: str, w: Window, cache: dict[str, Any]) -> dict[str, Any] | None:
    found = runs(top, slug, w)
    if found is None:
        return None
    passed = {(r["workflow_id"], r["head_sha"]) for r in found if r["conclusion"] == "success"}
    memo = cache.setdefault("jobs", {})
    candidates = [r for r in found if r["conclusion"] == "failure" or (r["run_attempt"] or 1) > 1]
    harness = code = 0
    for run in candidates:
        jobs = failed_jobs(top, slug, run, memo)
        if jobs is None:
            return None
        per_attempt: dict[int, int] = {}
        for job in jobs:
            per_attempt[job["attempt"]] = per_attempt.get(job["attempt"], 0) + 1
        for job in jobs:
            if job["name"].strip().lower() == "gate" and per_attempt[job["attempt"]] > 1:
                continue  # the aggregator only mirrors a sibling's failure
            same_code_passed = (run["workflow_id"], run["head_sha"]) in passed
            if job["setup_only"] or same_code_passed:
                harness += 1
            else:
                code += 1
    total = harness + code
    return {
        "share": round(harness / total, 3) if total else None,
        "harness": harness,
        "red_jobs": total,
        "per_day": round(total / w.days, 1) if w.days >= 1 else None,
        "runs": len(found),
    }


# --- CI minutes per day -------------------------------------------------------


def minutes_per_day(top: Path, owner: str, name: str, cut_ts: float, now: float) -> dict[str, Any]:
    """Billed Actions minutes per day, before the cut and on full days since."""
    cut_day = _dt.datetime.fromtimestamp(cut_ts, _dt.timezone.utc).date()
    first = cut_day - _dt.timedelta(days=WINDOW_DAYS)
    months = sorted({(first.year, first.month), (cut_day.year, cut_day.month)} | {
        (_dt.date.fromtimestamp(now).year, _dt.date.fromtimestamp(now).month)
    })
    by_day: dict[_dt.date, float] = {}
    for year, month in months:
        data = None
        for endpoint in (f"orgs/{owner}/settings/billing/usage", f"users/{owner}/settings/billing/usage"):
            data = _gh_json(top, f"{endpoint}?year={year}&month={month}")
            if data is not None:
                break
        for item in (data or {}).get("usageItems", []):
            if (
                item.get("product") == "actions"
                and item.get("repositoryName") == name
                and item.get("unitType") == "Minutes"
            ):
                day = _dt.date.fromisoformat(str(item.get("date", ""))[:10])
                by_day[day] = by_day.get(day, 0.0) + float(item.get("quantity", 0))
    before = [v for d, v in by_day.items() if first <= d < cut_day]
    since_days = [d for d in by_day if d > cut_day]
    since = [by_day[d] for d in since_days]
    return {
        "before_per_day": round(sum(before) / WINDOW_DAYS, 1) if by_day else None,
        "since_per_day": round(sum(since) / len(since_days), 1) if since_days else None,
        "since_days": len(since_days),
    }


# --- all four -----------------------------------------------------------------


def collect(top: Path, repo: store.RepoId, slug: str, ceremony: dict[str, Any] | None) -> dict[str, Any]:
    trunk = history.trunk(top) or "origin/main"
    cut_ts = cut(top, trunk)
    if cut_ts is None:
        return {"cut": None, "why": f"no commit on {trunk} adds rails/lanes.toml"}
    now = time.time()
    before, since = windows(cut_ts, now)
    cache_path = repo.dir / "numbers_cache.json"
    cache = store.read_json(cache_path, {}) or {}
    owner, _, name = slug.partition("/")
    out: dict[str, Any] = {
        "cut": _dt.datetime.fromtimestamp(cut_ts, _dt.timezone.utc).strftime("%Y-%m-%d"),
        "trunk": trunk,
    }
    try:
        for w in (before, since):
            out[w.label] = {
                "rework": churn_share(top, trunk, w, cache, now),
                "harness": harness_share(top, slug, w, cache),
                "catch": (lambda prs: catch_rate(prs) if prs is not None else None)(merged_prs(top, w)),
            }
        out["since"]["ceremony"] = ceremony
        out["minutes"] = minutes_per_day(top, owner, name, cut_ts, now)
    finally:
        store.write_json(cache_path, cache)
    return out


def _pct(part: dict[str, Any] | None, num: str, den: str) -> str:
    if not part:
        return "could not look"
    if part.get("share") is None:
        return f"-- (n={part.get(den, 0)})"
    return f"{part['share']:.0%} ({part[num]}/{part[den]})"


def _churn(part: dict[str, Any] | None) -> str:
    if not part:
        return "could not look"
    if part.get("share") is None:
        if part.get("first_reading"):
            return f"-- ({part['pending']} commit(s) still inside their 14 days; first reading {part['first_reading']})"
        return "-- (n=0)"
    return f"{part['share']:.0%} ({part['churned']:,}/{part['added']:,} lines, {part['commits']} commits)"


def _red(part: dict[str, Any] | None) -> str:
    text = _pct(part, "harness", "red_jobs")
    if part and part.get("per_day") is not None:
        text += f", {part['per_day']} red jobs/day"
    return text


def render(n: dict[str, Any]) -> list[str]:
    if not n.get("cut"):
        return [f"  the four numbers: no cut yet ({n.get('why', '?')})"]
    b, s = n["before"], n["since"]
    cer = s.get("ceremony")
    minutes = n.get("minutes", {})
    return [
        f"  the four numbers - before = 30 days before the cut ({n['cut']}), since = the cut to now:",
        f"    rework (landed lines rewritten or deleted within 14 days): before {_churn(b['rework'])} | since {_churn(s['rework'])}",
        "    automation catch rate (Detected-by on merged PRs): "
        f"before n/a (nothing carried it; evidence report ~10%, another instrument) | since {_pct(s['catch'], 'automated', 'tagged')}",
        "    ceremony share of operator messages: before n/a (evidence report 35%, another instrument) | since "
        + (f"{cer['ceremony_share']:.0%} (n={cer['messages']})" if cer else "-- (n=0)"),
        f"    harness share of red CI jobs (not the code): before {_red(b['harness'])} | since {_red(s['harness'])}",
        "  CI minutes per day: before "
        + (f"{minutes['before_per_day']:.0f}" if minutes.get("before_per_day") is not None else "?")
        + " | since "
        + (
            f"{minutes['since_per_day']:.0f} (over {minutes['since_days']} full day(s))"
            if minutes.get("since_per_day") is not None
            else "-- (billing has no full day since the cut yet)"
        ),
    ]
