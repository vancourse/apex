"""Arming auto-merge outside `rails ship` needs the same review receipt (design R26; review of 1.3.0).

`rails ship` will not arm a code diff whose tree has no review receipt (``ship_review``). But
``gh pr merge <n> --auto --squash`` is the arm the merge gate allows - and recommends - so an
agent told "not arming" could arm by hand. This refuses that arm, and the GraphQL
``enablePullRequestAutoMerge`` mutation (inline, in a variable set earlier in the command, in an
``@file`` or ``--input`` file, or piped into ``--input -``; a body it cannot read counts), when:

* the worktree's HEAD tree is a code diff with no review, or a review with open must-fix
  items; or
* HEAD is not what the branch's remote holds: auto-merge merges the pushed head, so a
  review of an unpushed local fix approves nothing GitHub will merge.

It reads the command's words, as ``merge_by_effect`` does (``gh.exe``, ``gh -R o/r pr merge``),
so a commit message or a grep that mentions the command is not an arm. When it allows an arm
it stamps the worktree's ``pr.json`` armed, so ``turn_end`` holds the turn to the PR's steps
as it does after `rails ship`, with the number the command named as ``armed_pr`` (None when it
named none), since the record's own number may belong to an older PR.

Scope: it judges the worktree the command runs in (one PR per line of work). A PR number from
another worktree is refused (p3f): this worktree's ``pr.json`` naming it, or GitHub saying this
branch heads it, is what lets an arm by number through. A `gh alias` hides the words - a known
gap.
"""

from __future__ import annotations

import re
from pathlib import Path

from rails import store
from rails.gates.destructive import command_name, commands
from rails.shell import arguments
from rails.hookio import Deny, Event

NAME = "arm_review"

_MUTATION = "enablePullRequestAutoMerge"
_HTTP = ("gh", "curl", "invoke-restmethod", "invoke-webrequest", "irm", "iwr")
_CD = ("cd", "pushd", "set-location", "sl", "chdir", "push-location")
_CD_PATH_FLAGS = ("-path", "-literalpath")


def subshell_scope(segment: str, shell: str | None) -> tuple[bool, bool, int]:
    """(nested, opens, closes) for a statement from `commands`: a substitution's statement
    (a child shell), a bash `( ...` that opens a subshell, and one whose `)` closes it. A
    `cd` in a child shell does not move the rest of the command."""
    from rails.shell import scrub

    nested = segment.startswith("$(")
    bash = (shell or "bash") != "powershell"
    # Read on the scrubbed text: a `)` in a quote or a comment closes nothing, and the one
    # that does may have a redirect or a pipe after it (`(...) 2>&1`, `) | tail`).
    text = scrub(segment, shell, comments=True)
    opens = bash and not nested and re.match(r"^\s*(?:(?:if|then|else|elif|do|while|until|!)\s+)*\(", text) is not None
    depth = text.count("(") - text.count(")")
    # How many subshells the statement closes: every `)` past its own opening one, so
    # `(git fetch)` closes the one it opens and `(git fetch -q))` closes two.
    closes = max(0, (1 if opens else 0) - depth) if bash and not nested else 0
    return nested, opens, closes


def moved(here: Path | None, tokens: list[str]) -> tuple[Path | None, bool] | None:
    """Where a folder change moves to, as (folder, known); None when ``tokens`` is not one.
    A target rails cannot resolve (`$WT`, `%WT%`, a folder that does not exist, no argument)
    leaves the folder unknown; `~` is the home folder."""
    if not tokens or command_name(tokens[0]) not in _CD:
        return None
    from rails.shell import grouped

    # `cd $(git rev-parse --show-toplevel)` is one argument however the tokenizer split it
    args = grouped([t for t in tokens[1:] if t.lower() not in _CD_PATH_FLAGS])
    if len(args) != 1 or here is None:
        return here, False
    target = args[0]
    if target.startswith("~"):
        target = str(Path.home()) + target[1:]
    if re.fullmatch(r"\$?\(\s*git\s+rev-parse\s+--show-toplevel\s*\)", target):
        # `cd "$(git rev-parse --show-toplevel)"`, PowerShell `Set-Location (git rev-parse
        # --show-toplevel)`: the top of the checkout it runs in
        found = store.find_repo(here)
        return (found.top, True) if found is not None else (here, False)
    if "$" in target or "%" in target:
        return here, False
    folder = (here / _native(target)).resolve()
    return (folder, True) if folder.is_dir() else (here, False)
_PULL_URL = re.compile(r"/pull/(\d+)\b")
#: A body written in the command itself: a heredoc, echo/printf piped in, a PowerShell
#: here-string (piped, or held in a variable that is piped), or a quoted literal piped in.
_INLINE_BODY = re.compile(
    r"<<-?\s*['\"]?\w+|\b(?:echo|printf|write-output)\b[^|]*\||@['\"][ \t]*\r?\n|^\s*(?:'(?:[^'\n]|'')*'|\"(?:[^\"$\n]|\"\")*\")\s*\|",
    re.IGNORECASE | re.MULTILINE,
)


def _file_names_mutation(token: str, cwd: Path | None) -> bool:
    name = token.split("=", 1)[1] if "=" in token else token
    if not name.startswith("@") or len(name) < 2:
        return False
    path = Path(name[1:])
    if not path.is_absolute() and cwd is not None:
        path = cwd / path
    try:
        return _MUTATION in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


_STDIN_SOURCE = re.compile(
    r"(?:\b(?:cat|type|Get-Content|gc)\s+['\"]?([^\s'\"|;]+)['\"]?[^|;\n]*\||(?<!<)<(?![<(])\s*['\"]?([^\s'\"|;<]+))",
    re.IGNORECASE,
)
#: `gh pr merge` options that take a value: the value is not the PR selector.
_MERGE_VALUED = frozenset(
    {"-b", "--body", "-F", "--body-file", "-t", "--subject", "--match-head-commit", "-A", "--author-email", "-R", "--repo"}
)


def _native(path: str) -> str:
    """A Git Bash path (`/c/Users/x`) as Windows reads it (`c:/Users/x`)."""
    from rails.gates.destructive import native_path

    return native_path(path)


def _read(name: str, cwd: Path | None) -> str | None:
    path = Path(name)
    if not path.is_absolute() and cwd is not None:
        path = cwd / path
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _graphql_arms(
    rest: list[str], command: str, cwd: Path | None, unreadable: list[str] | None = None
) -> bool:
    """A GraphQL call arms when the mutation is anywhere it could come from: the command
    text (inline, or a variable set earlier in it), an ``--input`` file, or what is piped into
    ``--input -``. A body it cannot read is recorded in ``unreadable`` (p3h: `check` refuses
    it naming the path, rather than judging a read an arm and stamping the PR armed)."""
    if _MUTATION in command or any(_file_names_mutation(tok, cwd) for tok in rest):
        return True
    missing = unreadable if unreadable is not None else []
    for i, tok in enumerate(rest):
        if tok == "--input" and i + 1 < len(rest) or tok.startswith("--input="):
            name = rest[i + 1] if tok == "--input" else tok.split("=", 1)[1]
            if name == "-":
                sources = [a or b for a, b in _STDIN_SOURCE.findall(command)]
                if not sources and _INLINE_BODY.search(command):
                    # The body is the command text, already searched for the mutation; a
                    # file fed in (`< q.json`) is read even when an echo sits elsewhere.
                    continue
                if not sources:
                    missing.append("the stdin piped into --input -")
                for source in sources:
                    text = _read(source, cwd)
                    if text is None:
                        missing.append(source)
                    elif _MUTATION in text:
                        return True
            else:
                text = _read(name, cwd)
                if text is None:
                    missing.append(name)
                elif _MUTATION in text:
                    return True
    return bool(missing) and unreadable is None


def _arms(
    tokens: list[str], cwd: Path | None, command: str, unreadable: list[str] | None = None
) -> bool:
    name = command_name(tokens[0])
    rest = tokens[1:]
    if name == "gh":
        for i in range(len(rest) - 1):
            if rest[i] == "pr" and rest[i + 1] == "merge":
                return "--auto" in rest[i + 2 :]
        if "api" in rest and "graphql" in rest:
            return _graphql_arms(rest, command, cwd, unreadable)
    if name in _HTTP:
        if any(tok.rstrip("/").endswith("/graphql") for tok in rest) and _graphql_arms(
            rest, command, cwd, unreadable
        ):
            return True
        return any(_MUTATION in tok or _file_names_mutation(tok, cwd) for tok in rest)
    return False


def _merge_selectors(tokens: list[str]) -> list[str]:
    """For each `gh pr merge ... --auto` in one command's words, its selector: the first
    argument that is not a flag or a flag's value (`--subject 12 --auto 15` selects 15; a PR
    URL in `--body` names nothing), or "" when it names none. One reader for `_pr_numbers`,
    `_branch_selectors` and `armed_number`."""
    out: list[str] = []
    if not tokens or command_name(tokens[0]) != "gh":
        return out
    rest = arguments(tokens[1:], _MERGE_VALUED)
    for i in range(len(rest) - 2):
        if rest[i] == "pr" and rest[i + 1] == "merge" and "--auto" in rest[i + 2 :]:
            args, j, selector = rest[i + 2 :], 0, ""
            while j < len(args):
                if args[j] in _MERGE_VALUED:
                    j += 2
                    continue
                if not args[j].startswith("-"):
                    selector = args[j]
                    break
                j += 1
            out.append(selector)
    return out


def _pr_numbers(command: str, shell: str) -> list[str]:
    """The PR numbers a command arms by number (``gh pr merge N --auto``)."""
    out: list[str] = []
    for _, tokens in commands(command, shell):
        for selector in _merge_selectors(tokens):
            number = _selector_number(selector) if selector else ""
            if number:
                out.append(number)
    return out


def armed_number(segments: list[list[str]]) -> int | None:
    """The PR number the first `gh pr merge <n> --auto` names, or None (no argument, a branch
    name, a GraphQL arm). `turn_end` settles a record only when this matches its number."""
    for tokens in segments:
        selectors = _merge_selectors(tokens)
        if selectors:
            number = _selector_number(selectors[0]) if selectors[0] else ""
            return int(number) if number else None
    return None


def _branch_selectors(command: str, shell: str) -> list[str]:
    """The branch names a command arms by (``gh pr merge feat --auto``)."""
    out: list[str] = []
    for _, tokens in commands(command, shell):
        for selector in _merge_selectors(tokens):
            if selector and not _selector_number(selector):
                out.append(selector)
    return out


def arming(evt: Event) -> tuple[bool, Path | None, list[str]]:
    """Whether the command arms auto-merge, the folder it arms from (after any `cd`), and
    the bodies it could not read."""
    shell = evt.shell
    command = evt.command or ""
    unreadable: list[str] = []
    arm_here: Path | None = None
    try:
        arms = False
        here = evt.cwd
        saved: list[Path | None] = []
        last, restore = None, 0
        for segment, tokens in commands(command, shell or "bash"):
            if segment != last:
                # Once per statement: a subshell's `)` restores the folder after its last word,
                # one level per `)` (`(cd wt && (git fetch) && gh pr merge ...)`).
                for _ in range(restore):
                    if saved:
                        here = saved.pop()
                nested, opens, restore = subshell_scope(segment, shell)
                if opens:
                    saved.append(here)
                last = segment
            # `cd sub && gh api graphql --input q.json` reads sub/q.json (p3h), and
            # `cd <worktree> && gh pr merge --auto` arms that worktree's PR.
            change = None if nested else moved(here, tokens)
            if change is not None:
                here = change[0]
            elif _arms(tokens, here, command, unreadable):
                arms, arm_here = True, here
    except Exception:  # noqa: BLE001 - an unparsable command is judged by text
        arms = ("--auto" in command and "merge" in command) or "automerge" in command.lower()
    return arms, arm_here, unreadable


def _selector_number(token: str) -> str:
    """A PR number from a `gh pr merge` selector: `12`, `#12`, or a `.../pull/12` URL."""
    bare = token.lstrip("#")
    if bare.isdigit():
        return bare
    found = _PULL_URL.search(token)
    return found.group(1) if found else ""


def _foreign_pr(repo: store.RepoId, number: str, branch: str) -> str | None:
    """Why PR ``number`` is not this worktree's to arm, or None (p3f). This worktree's
    ``pr.json`` naming it settles it; otherwise GitHub says which branch it heads."""
    pr = store.read_json(repo.leaf_dir / "pr.json", None)
    # pr.json settles it only for the branch it was opened from: a worktree that switched
    # branch holds a record of another branch's PR.
    if isinstance(pr, dict) and str(pr.get("number", "")) == number and pr.get("branch") in (None, branch):
        return None
    from rails.gitutil import GitError, gh

    try:
        import json as _json

        head = _json.loads(gh(repo.top, "pr", "view", number, "--json", "headRefName", timeout=15))
        head_branch = str(head.get("headRefName", ""))
    except (GitError, ValueError, OSError):
        return f"which branch PR #{number} heads could not be read"
    if head_branch != branch:
        return f"PR #{number} heads {head_branch or 'another branch'}, not this worktree's {branch}"
    return None


def _stamp_armed(repo: store.RepoId, branch: str, numbers: list[str]) -> None:
    """Stamp pr.json armed, with the number the arm named (``armed_pr``, None when it named
    none), and release its hold, when pr.json is the PR this arm armed: the one on this branch,
    and the one the command named (if it named one). Under the lock `turn_end` settles under,
    so a stamp cannot land between its compare and its write (review of 1.6.2)."""
    path = repo.leaf_dir / "pr.json"
    with store.locked(path):
        pr = store.read_json(path, None)
        if not (
            isinstance(pr, dict)
            and pr.get("branch") in (None, branch)
            and (not numbers or str(pr.get("number", "")) in numbers)
        ):
            return
        pr["armed"] = True
        pr["armed_pr"] = int(numbers[0]) if numbers else None
        pr.pop("disarmed_by", None)  # armed past every check: a review covers it now
        store.write_json(path, pr)
    from rails.githooks import release_pr_hold

    release_pr_hold(repo, pr.get("number"))


def check(evt: Event):
    shell = evt.shell
    command = evt.command or ""
    if shell is None:
        return None
    words = ("merge", _MUTATION, "@", "graphql")
    if not any(w in command for w in words):
        # A gh alias hides the words (`gh am 12`): the parser expands it (p3e).
        from rails.gates.destructive import gh_aliases

        if not any(re.search(rf"\bgh(?:\.exe)?\s+{re.escape(a)}\b", command) for a in gh_aliases()):
            return None
    arms, arm_here, unreadable = arming(evt)
    if not arms and unreadable:
        return Deny(
            "rails: refused - this GraphQL call's body cannot be read, so whether it arms "
            f"auto-merge cannot be told: {', '.join(unreadable)}. Fix the path (it is read "
            "relative to the command's folder) or pass the query inline."
        )
    if not arms:
        return None
    # The folder the arm runs in, after any `cd`: the review judged is that worktree's.
    repo = store.find_repo(arm_here or evt.cwd)
    if repo is None:
        return None
    from rails import review, ship
    from rails.gitutil import GitError, git, head, tree

    try:
        local = head(repo.top)
        br = git(repo.top, "rev-parse", "--abbrev-ref", "HEAD", check=False).strip()
        if br in ("", "HEAD"):
            return Deny("rails: not arming auto-merge from a detached HEAD: check out the PR's branch first.")
        # The PR's head is origin/<branch>; a branch cut from origin/master tracks that as
        # @{u}, so either one holding HEAD counts as pushed.
        pr_head = git(repo.top, "rev-parse", "--verify", "-q", f"origin/{br}", check=False).strip()
        # origin/<branch> is the PR's head when it exists; @{u} only stands in when it does not
        # (a HEAD reset to origin/master must not count as the PR's head, review of 1.3.0)
        remotes = {pr_head} if pr_head else {git(repo.top, "rev-parse", "--verify", "-q", "@{u}", check=False).strip()}
        if local not in remotes:
            return Deny(
                "rails: not arming auto-merge: HEAD is not what the branch's remote holds, and auto-merge merges "
                "the pushed head. Push first (the pre-push hook checks this tree's review), then arm."
            )
        if ship.needs_review(repo.top, None):
            numbers = _pr_numbers(command, shell)
            # No selector arms the branch's own PR: this worktree's pr.json names it.
            from rails.githooks import _pr_number

            target = numbers[0] if numbers else _pr_number(repo)
            problem = review.arming_problem(review.covering(repo, repo.top, "HEAD"), repo, target)
            if problem:
                return Deny(f"rails: not arming auto-merge: {problem}")
    except Exception as exc:  # noqa: BLE001 - an arm it cannot check is refused, like pre-push
        return Deny(f"rails: not arming auto-merge: the review could not be checked ({type(exc).__name__})")
    from rails.gates.rearm_disarmed import _merge_folder

    followed = _merge_folder(evt)[1]
    if not followed and not _pr_numbers(command, shell):
        # `gh pr checkout 13 && gh pr merge --auto`: the review judged the tree from before the
        # switch, and the PR a selector-less arm picks is the one after it.
        return Deny(
            "rails: not arming auto-merge: the command changes branch (or folder) before the arm in a "
            "way rails cannot follow, so the PR it arms is not the tree reviewed here. Name the PR by "
            "number (`gh pr merge <n> --auto`), or switch first and arm in a separate call."
        )
    # The review judged THIS worktree's tree: a PR number from another worktree would arm a
    # head nobody judged here (p3f).
    for number in _pr_numbers(command, shell):
        why = _foreign_pr(repo, number, br)
        if why:
            return Deny(
                f"rails: not arming auto-merge: {why}. The review here judged this worktree's tree; "
                "arm a PR from the worktree that holds its branch (`rails ship` there)."
            )
    for selector in _branch_selectors(command, shell):
        if selector != br:
            return Deny(
                f"rails: not arming auto-merge: `{selector}` selects another branch's PR, and the review "
                f"here judged this worktree's {br}. Arm it from the worktree that holds it (`rails ship` there)."
            )
    if followed:
        # Not across a branch or folder change rails cannot follow: which PR gh armed is
        # then not this worktree's to stamp.
        _stamp_armed(repo, br, _pr_numbers(command, shell))
    return None
