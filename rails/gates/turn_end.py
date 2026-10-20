"""Stop: a turn does not end on a claim the artifacts do not support (design R28).

Artifact conditions, each blocking at most 3 consecutive times; on the fourth
the turn ends and the items are written to ``unverified`` in work.json — a
recorded debt `rails ship` refuses to close over and SessionStart prints:

  A. an ARMED PR (pr.json) to close items whose step has no passing walk receipt;
  B. an armed PR with no monitor bound.

Before blocking on either, the PR is looked up (`merged_pr_push.pull_requests`, the one lookup
rails has). `armed` is written once, at ship, and nothing clears it, so a PR that merged hours ago
held every turn that ended in its worktree (jarvis #2796, 2026-10-20). A PR GitHub calls MERGED
or CLOSED holds no turn: pr.json records that state with ``armed: false``, and a merge writes
A's items ``unverified`` at once, as the fourth block would. An OPEN PR, or no answer (no `gh`, a
timeout, an error), blocks as before. Turns with nothing to block run no lookup.

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
    """MERGED or CLOSED when GitHub says the recorded PR is no longer open; None when it is open,
    is not found, or nothing can answer."""
    branch = pr.get("branch") or merged_pr_push.current_branch(repo.top)
    if not branch:
        return None
    for row in merged_pr_push.pull_requests(branch, repo.top) or []:
        if str(row.get("number")) == str(pr.get("number")):
            state = str(row.get("state", "")).upper()
            return state if state in ("MERGED", "CLOSED") else None
    return None


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
        if not evt.payload.get("_rails_shadow"):
            store.write_json(repo.leaf_dir / "pr.json", {**pr, "state": settled, "armed": False})
            if settled == "MERGED" and unproven:
                debt = {i.get("id") for i in unproven}
                with store.updating(work.path(repo), {}) as fresh:
                    for item in fresh.get("items", []):
                        if item.get("status") == "open" and item.get("id") in debt:
                            item["status"] = "unverified"
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
