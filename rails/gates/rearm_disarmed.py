"""PreToolUse: a held PR is not armed or merged until a review covers the head it would merge (p2).

A PR is held when a push no review covers disarmed it, or when `rails ship` declined to arm a
tree no review covers (`githooks.hold`, kept per PR number in the repo's shared state, so an
arm from any folder sees it). `arm_review` and `merge_by_effect` only logged in the shadow week
(to 2026-10-15), and a hand `gh pr merge N --auto` undid the disarm (review of p2). This gate is enforced from
the start. It refuses an arm, or a direct `gh pr merge`, of a held PR unless the worktree
holding it has pushed a head that a review covers; a merge whose PR a folder or branch change
hides, while a PR is held; and any merge naming another repo (`-R`, `--repo`, `GH_REPO`, its
PR URL), and one naming a repo from outside a checkout, since that repo's holds and review
live in its checkout.
"""

from __future__ import annotations

import re
from pathlib import Path

from rails import store
from rails.gates import arm_review
from rails.gates.destructive import command_name, commands
from rails.shell import arguments
from rails.hookio import Deny, Event

NAME = "rearm_disarmed"


def _merge_selectors(command: str, shell: str) -> list[str]:
    """The selector of every `gh pr merge` in the command, `--auto` or not ('' when it names
    none). `--disable-auto` turns auto-merge off and is not a merge."""
    out: list[str] = []
    for _, tokens in commands(command, shell):
        if not tokens or command_name(tokens[0]) != "gh":
            continue
        rest = arguments(tokens[1:], arm_review._MERGE_VALUED)
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
    follow every folder and branch change before it (`git switch`, `gh pr checkout` move the
    branch a merge with no selector resolves)."""
    here, known = evt.cwd, True
    saved: list[Path | None] = []
    try:
        last, restore = None, 0
        for segment, tokens in commands(evt.command or "", evt.shell or "bash"):
            if segment != last:
                # Once per statement: a subshell's `)` restores the folder after its last word,
                # one level per `)`.
                for _ in range(restore):
                    if saved:
                        here = saved.pop()
                nested, opens, restore = arm_review.subshell_scope(segment, evt.shell)
                if opens:
                    saved.append(here)
                last = segment
            change = None if nested else arm_review.moved(here, tokens)
            if change is not None:
                here, known = change[0], known and change[1]
                continue
            name = command_name(tokens[0]) if tokens else ""
            if name == "git" and any(t in ("switch", "checkout") for t in tokens[1:3]):
                if "checkout" in tokens[1:3] and "--" in tokens and tokens.index("--") < len(tokens) - 1:
                    continue  # `git checkout -- src/a.py` restores files; the branch stays
                known = False
                continue
            if name == "gh" and "checkout" in tokens[1:3]:
                known = False
                continue
            if name == "gh" and "merge" in tokens:
                break
    except Exception:  # noqa: BLE001 - unparsable: the folder is unknown
        return evt.cwd, False
    return here, known


_PR_URL_REPO = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/pull/\d+", re.IGNORECASE)


def _repo_name(value: str) -> str:
    """`owner/name` from a -R value or a URL: host, scheme, `.git` and slashes dropped."""
    value = value.strip().lower().rstrip("/")
    value = re.sub(r"^(?:https?://)?(?:www\.)?github\.com/", "", value)
    value = value.removesuffix(".git")
    found = re.match(r"^([\w.-]+/[\w.-]+)(?:/pull/\d+.*)?$", value)
    return found.group(1) if found else value


def _named_repos(evt: Event) -> set[str]:
    """The repos a `gh pr merge` in the command names: its `-R`/`--repo` value, its selector
    when that is another repo's PR URL, and a `GH_REPO` set in unquoted text (lower case
    `owner/name`). A URL in `--body` or `--subject` text names nothing."""
    from rails.shell import scrub

    command = evt.command or ""
    shell = evt.shell or "bash"
    unquoted = scrub(command, shell, comments=True)
    named = {
        _repo_name(m.group(1))
        for m in re.finditer(r"(?:\bGH_REPO=|\$env:GH_REPO\s*=\s*)['\"]?([^\s'\";]+)", command, re.IGNORECASE)
        # only an assignment the shell runs: one in a quote or a comment is blanked there;
        # `$env:GH_REPO = $null` clears it
        if unquoted[m.start()] == command[m.start()] and m.group(1).lower() != "$null"
    }
    for _, tokens in commands(command, shell):
        if not tokens or command_name(tokens[0]) != "gh" or "merge" not in tokens or "--disable-auto" in tokens:
            continue
        args = arguments(tokens[tokens.index("merge") + 1 :], arm_review._MERGE_VALUED)
        i, selector = 0, ""
        while i < len(args):
            tok = args[i]
            if tok in ("-R", "--repo") and i + 1 < len(args):
                named.add(_repo_name(args[i + 1]))
                i += 2
                continue
            if tok.startswith("--repo="):
                named.add(_repo_name(tok.split("=", 1)[1]))
            elif tok in arm_review._MERGE_VALUED:
                i += 2
                continue
            elif not tok.startswith("-") and not selector:
                selector = tok
            i += 1
        found = _PR_URL_REPO.search(selector)
        if found:
            named.add(_repo_name(found.group(1)))
    return named


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
    named_repos = _named_repos(evt)
    if named_repos:
        from rails.gitutil import origin_slug

        mine = (origin_slug(repo.top) or "").lower() if repo is not None else ""
        others = sorted(r for r in named_repos if r != mine)
        if others:
            return Deny(
                f"rails: refused - this merges a PR of {', '.join(others)}, and its holds and review are "
                "judged in a checkout of that repo. Run it from there (`rails ship` there arms it)."
            )
    if repo is None:
        return None
    held = pr_holds(repo)
    if not held:
        return None
    by_branch = {str(e.get("branch")): n for n, e in held.items() if isinstance(e, dict) and e.get("branch")}
    if any(s and not arm_review._selector_number(s) and s not in by_branch and re.search(r"[$<`%(]", s) for s in selectors):
        # `gh pr merge $PR`, `$(gh pr view ...)`, PowerShell `(gh pr view ...)`, `<N>`: which PR
        # it merges cannot be told
        return Deny(
            "rails: refused - a PR is held off auto-merge in this repo, and this command names its PR "
            "through a variable, so which PR it merges cannot be told. Name the PR by number "
            "(`gh pr merge <N> ...`)."
        )
    named = [arm_review._selector_number(s) for s in selectors if arm_review._selector_number(s)]
    named += [by_branch[s] for s in selectors if s and not arm_review._selector_number(s) and s in by_branch]
    if (arms and not selectors) or "" in selectors:
        # No selector: gh merges the PR of the folder's branch.
        if not known:
            return Deny(
                "rails: refused - a PR is held off auto-merge in this repo, and this command changes folder "
                "or branch in a way rails cannot follow, so which PR it merges cannot be told. Name the PR "
                "by number (`gh pr merge <N> ...`)."
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
