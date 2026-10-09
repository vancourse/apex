"""PreToolUse: a held PR is not armed or merged until a review covers the head it would merge (p2).

A PR is held when a push no review covers disarmed it, or when `rails ship` declined to arm a
tree no review covers (`githooks.hold`, kept per PR number in the repo's shared state, so an
arm from any folder sees it). `arm_review` and `merge_by_effect` only log in the shadow week,
and a hand `gh pr merge N --auto` undid the disarm (review of p2). This gate is enforced from
the start, and refuses only that: an arm, or a direct `gh pr merge`, of a held PR, unless the
worktree holding it has pushed a head that a review covers. A PR nothing held never reaches it.
"""

from __future__ import annotations

from pathlib import Path

from rails import store
from rails.gates import arm_review
from rails.gates.destructive import command_name, commands
from rails.hookio import Deny, Event

NAME = "rearm_disarmed"


def _merge_selectors(command: str, shell: str) -> list[str]:
    """The selector of every `gh pr merge` in the command, `--auto` or not ('' when it names
    none). `--disable-auto` turns auto-merge off and is not a merge."""
    out: list[str] = []
    for _, tokens in commands(command, shell):
        if not tokens or command_name(tokens[0]) != "gh":
            continue
        rest = tokens[1:]
        for i in range(len(rest) - 1):
            if rest[i] == "pr" and rest[i + 1] == "merge":
                args = rest[i + 2 :]
                if "--disable-auto" in args:
                    break
                selector, j = "", 0
                while j < len(args):
                    if args[j] in arm_review._MERGE_VALUED:
                        j += 2
                        continue
                    if not args[j].startswith("-"):
                        selector = args[j]
                        break
                    j += 1
                out.append(selector)
                break
    return out


def _merge_folder(evt: Event) -> tuple[Path | None, bool]:
    """The folder the first merge or arm in the command runs in, and whether rails could
    follow every folder change before it."""
    here, known = evt.cwd, True
    try:
        for _, tokens in commands(evt.command or "", evt.shell or "bash"):
            change = arm_review.moved(here, tokens)
            if change is not None:
                here, known = change[0], known and change[1]
                continue
            if tokens and command_name(tokens[0]) == "gh" and "merge" in tokens:
                break
    except Exception:  # noqa: BLE001 - unparsable: the folder is unknown
        return evt.cwd, False
    return here, known


def check(evt: Event):
    if evt.shell is None:
        return None
    from rails.githooks import pr_holds
    from rails.gitutil import git

    command = evt.command or ""
    arms, _, _ = arm_review.arming(evt)
    selectors = _merge_selectors(command, evt.shell)
    if not arms and not selectors:
        return None
    here, known = _merge_folder(evt)
    repo = store.find_repo(here or evt.cwd)
    if repo is None:
        return None
    held = pr_holds(repo)
    if not held:
        return None
    by_branch = {str(e.get("branch")): n for n, e in held.items() if isinstance(e, dict) and e.get("branch")}
    named = [arm_review._selector_number(s) for s in selectors if arm_review._selector_number(s)]
    named += [by_branch[s] for s in selectors if s and not arm_review._selector_number(s) and s in by_branch]
    if (arms and not selectors) or "" in selectors:
        # No selector: gh merges the PR of the folder's branch.
        if not known:
            return Deny(
                "rails: refused - a PR is held off auto-merge in this repo, and this command changes folder "
                "in a way rails cannot follow, so which PR it merges cannot be told. Name the PR by number "
                "(`gh pr merge <N> ...`)."
            )
        branch = git(repo.top, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
        if branch in by_branch:
            named.append(by_branch[branch])
        pr = store.read_json(repo.leaf_dir / "pr.json", None)
        if isinstance(pr, dict) and pr.get("number") and pr.get("branch") in (None, branch):
            named.append(str(pr["number"]))
    for number in dict.fromkeys(named):
        entry = held.get(number)
        if not isinstance(entry, dict):
            continue
        why = str(entry.get("why", "held"))
        if entry.get("leaf") != repo.leaf:
            return Deny(
                f"rails: refused - PR #{number} is held off auto-merge ({why}), and this folder does not "
                "hold its branch. Review it in the worktree that does, record the review, then `rails ship` there."
            )
        problem = _unreviewed_head(repo, number, str(entry.get("branch") or ""))
        if problem:
            return Deny(f"rails: refused - PR #{number} is held off auto-merge ({why}): {problem}")
    return None


def _unreviewed_head(repo: store.RepoId, number: str, held_branch: str = "") -> str | None:
    """Why the head GitHub would merge is not reviewed, or None. That head is
    `origin/<branch>` of the PR's own branch: a review of an unpushed commit, or of another
    branch this worktree switched to, does not cover it."""
    from rails import review
    from rails.gitutil import git, head

    branch = git(repo.top, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
    if branch in ("", "HEAD"):
        return "HEAD is detached; check out the PR's branch"
    if held_branch and branch != held_branch:
        return f"its branch is {held_branch}, and this worktree is on {branch}. Check out {held_branch} first"
    pushed = git(repo.top, "rev-parse", "--verify", "-q", f"origin/{branch}", check=False).strip()
    if not pushed or pushed != head(repo.top):
        return "HEAD is not what the PR's branch holds on origin. Push, then arm: GitHub merges the pushed head"
    problem = review.arming_problem(review.covering(repo, repo.top, "HEAD"), repo, number)
    if problem:
        return f"{problem} Then `rails ship`."
    return None
