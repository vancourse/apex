"""Stop: a turn does not end on a claim the artifacts do not support (design R28).

Artifact conditions, each blocking at most 3 consecutive times; on the fourth
the turn ends and the items are written to ``unverified`` in work.json — a
recorded debt `rails ship` refuses to close over and SessionStart prints:

  A. an ARMED PR (pr.json) to close items whose step has no passing walk receipt;
  B. an armed PR with no monitor bound.

Before blocking on either, the PR is looked up with `merged_pr_push.pull_requests` (`gh pr list
--head <branch> --state all`, 8 s). ``armed`` is set when a PR is armed (`rails ship`, or
`arm_review` for one armed by hand) and nothing cleared it after the merge, so a PR that merged
hours earlier still held turns in its worktree (jarvis #2796, 2026-10-20). A PR GitHub calls
MERGED or CLOSED holds no turn, if the record can be trusted to name it (`_settled`): pr.json
records that state with ``armed: false``, and for a merge, A's items for the issues that PR closes
are written ``unverified`` at once. That is narrower than the fourth block, which writes every
open closing item. An OPEN PR, an untrusted record, a record that changed during the lookup, or
no answer (no `gh`, a timeout, an error) blocks as before. Turns with nothing to block run no
lookup; in shadow pr.json and the items are not written.

Wording condition, blocking once: the last message is offer-shaped ("want me
to", "shall I", "say the word") while items are open and no ``stop_reason`` is
recorded (`rails work stop <kind> "<text>"`).
"""

from __future__ import annotations

import re

from rails import intent, store, work
from rails.gates import merged_pr_push
from rails.hookio import Block, Event

NAME = "turn_end"
MAX_BLOCKS = 3

_OFFER = re.compile(
    r"\b(want me to|shall i|should i (?:go ahead|proceed|start)|say the word|let me know if you(?:'d| would) like|"
    r"would you like me to|if you want, i can|i can also)\b",
    re.IGNORECASE,
)


def _settled(repo: store.RepoId, pr: dict) -> str | None:
    """MERGED or CLOSED when GitHub says the PR this record names is finished AND the record can
    still be trusted to name the armed PR. None blocks as before: the PR is open, not found, or
    nothing can answer, or the record may name the wrong PR.

    A PR armed by hand after a re-cut rides an older record, so trusted means all of:
    - an arm by hand (`arm_review`, which writes ``armed_pr``) named this record's number;
    - the record still says OPEN (an armed record that already says MERGED or CLOSED was re-armed);
    - it names the branch this worktree is on (a record with no branch: the current one);
    - no open PR has that branch as its head (review of 1.6.2)."""
    if "armed_pr" in pr and str(pr.get("armed_pr")) != str(pr.get("number")):
        return None
    if str(pr.get("state") or "OPEN").upper() != "OPEN":
        return None
    current = merged_pr_push.current_branch(repo.top)
    branch = pr.get("branch") or current
    if not branch or branch != current:
        return None
    rows = merged_pr_push.pull_requests(branch, repo.top) or []
    if any(str(r.get("state", "")).upper() == "OPEN" for r in rows):
        return None
    for row in rows:
        if str(row.get("number")) == str(pr.get("number")):
            state = str(row.get("state", "")).upper()
            return state if state in ("MERGED", "CLOSED") else None
    return None


def _settle(repo: store.RepoId, pr: dict, settled: str, unproven: list[dict]) -> bool:
    """Record a finished PR; False when pr.json no longer names it (a `rails ship` or an arm by hand
    recorded another PR during the lookup), and then the turn blocks as before.

    Under pr.json's lock: compare, write the debt, then clear ``armed``. Once ``armed`` is false no
    later Stop looks again, so a debt write that fails leaves pr.json as it was and the next Stop
    tries again (review of 1.6.2)."""
    path = repo.leaf_dir / "pr.json"
    with store.locked(path):
        record = store.read_json(path, None)
        same = (
            isinstance(record, dict)
            and str(record.get("number")) == str(pr.get("number"))
            and record.get("armed")
            and record.get("armed_pr") == pr.get("armed_pr")
        )
        if not same:
            return False
        if settled == "MERGED":
            closes = {str(c).lstrip("#") for c in pr.get("closes") or []}
            debt = {i.get("id") for i in unproven if str(i.get("closes", "")).lstrip("#") in closes}
            if debt:
                with store.updating(work.path(repo), {}) as fresh:
                    for item in fresh.get("items", []):
                        if item.get("status") == "open" and item.get("id") in debt:
                            item["status"] = "unverified"
        store.write_json(path, {**record, "state": settled, "armed": False})
    return True


def check(evt: Event):
    repo = store.find_repo(evt.cwd)
    if repo is None:
        return None
    data = work.load(repo)
    pr = store.read_json(repo.leaf_dir / "pr.json", None)
    problems = []
    unproven = []
    if isinstance(pr, dict) and pr.get("armed"):
        ok = work.passing_steps(repo)
        unproven = [
            i
            for i in data["items"]
            if i.get("status") != "unverified"
            and i.get("step")
            and i["step"] not in ok
            and i.get("closes")
        ]
        if unproven:
            problems.append(
                f"PR #{pr.get('number')} is armed to close {', '.join(sorted({str(i['closes']) for i in unproven}))} but "
                f"step(s) {', '.join(i['step'] for i in unproven)} have no passing walk receipt. Run `rails walk` "
                "until they pass, or disarm (`gh pr merge <n> --disable-auto`)."
            )
        if pr.get("monitor", "unbound") != "bound":
            problems.append(
                f"PR #{pr.get('number')} is armed with no monitor bound. Bind it (ccd_pr bind_pr + set_monitor), "
                "then `rails work monitor-bound`."
            )
    if problems and (settled := _settled(repo, pr)):
        if evt.payload.get("_rails_shadow"):
            problems = []
        elif _settle(repo, pr, settled, unproven):
            data = work.load(repo)  # the wording check below reads the items as now written
            problems = []
    if problems and evt.payload.get("_rails_shadow"):
        return Block(
            "\n".join(problems)
        )  # logged as would-block; no counter, no unverified writes
    if problems:
        blocks = int(data.get("blocks", 0)) + 1
        if blocks > MAX_BLOCKS:
            with store.updating(work.path(repo), {}) as fresh:
                for item in fresh.get("items", []):
                    if item.get("status") == "open" and item.get("closes"):
                        item["status"] = "unverified"
                fresh["blocks"] = 0
            return None
        with store.updating(work.path(repo), {}) as fresh:
            fresh["blocks"] = blocks
        return Block(
            "rails: the turn cannot end yet.\n" + "\n".join(f"- {p}" for p in problems)
        )
    if data.get("blocks"):
        with store.updating(work.path(repo), {}) as fresh:
            fresh["blocks"] = 0
    if (
        work.open_items(data)
        and not data.get("stop_reason")
        and not evt.payload.get("stop_hook_active")
    ):
        last = intent.last_assistant_text(evt.transcript_path)
        if _OFFER.search(last[-1500:]):
            return Block(
                "rails: open items remain and this ending offers instead of doing. Either do the next item, or record why "
                'you are stopping: `rails work stop decision_needed "<problem; options with costs; recommended first>"` '
                "| blocked | hold | wip."
            )
    return None
