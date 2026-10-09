"""`rails close <milestone number>`: a milestone closes when the operator used it (design R18).

Done is not "the issues are closed". A milestone's description is its demo, and its step 0
is the operator doing a real task with it. So `rails close` closes milestone N on GitHub
only when:

  * the operator recorded ``used #N <task>`` (their own words, from a prompt or their shell -
    `rails used` refuses inside an agent);
  * the milestone has no open issues.

Not checked yet (design R16/R18, tracked for Rails R2): the real-data oracle receipt and a
rulebook ``approve`` for each concept the milestone changed.

Closing by hand around this (``gh api .../milestones/N -X PATCH -f state=closed``) is what
the ``milestone_close`` gate refuses in an agent's command.
"""

from __future__ import annotations

from pathlib import Path

from rails import store
from rails.gitutil import GitError, gh_api, origin_slug


def used_records(repo: store.RepoId, number: str) -> list[dict]:
    """`used #N` rows the operator typed in a prompt. A row from a shell (`rails used`) is kept
    but does not close: nothing on a command line tells the operator from an agent (1.3.0)."""
    state = store.read_json(repo.dir / "state.json", {}) or {}
    want = number.lstrip("#")
    return [
        u
        for u in state.get("used", [])
        if str(u.get("milestone", "")).lstrip("#") == want and u.get("by") == "prompt"
    ]


def close(cwd: Path, number: str) -> tuple[int, str]:
    repo = store.find_repo(cwd)
    if repo is None:
        return 2, "rails close: not inside a git checkout"
    slug = origin_slug(repo.top)
    if not slug:
        return 2, "rails close: origin is not a GitHub remote"
    n = number.lstrip("#")
    used = used_records(repo, n)
    if not used:
        return 1, (
            f"rails close: milestone {n} has no `used` record. Done is the operator using it for a real "
            f"task: they say `used #{n} <task>` in a prompt."
        )
    try:
        ms = gh_api(repo.top, f"repos/{slug}/milestones/{n}")
    except GitError as exc:
        return 2, f"rails close: cannot read milestone {n}: {exc}"
    if ms.get("state") == "closed":
        return 0, f"rails close: milestone {n} is already closed"
    if int(ms.get("open_issues", 0)):
        return 1, f"rails close: milestone {n} still has {ms['open_issues']} open issue(s)"
    try:
        gh_api(repo.top, f"repos/{slug}/milestones/{n}", method="PATCH", payload={"state": "closed"})
    except GitError as exc:
        return 2, f"rails close: GitHub refused: {exc}"
    return 0, f"rails close: milestone {n} '{ms.get('title', '')}' closed (used: {used[-1].get('task', '')[:80]})"
