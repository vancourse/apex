"""Deny every agent merge path except arming auto-merge (design R2, decision 13.1).

The repository keeps its admin bypass actor (``RepositoryRole 5, bypass_mode:
always`` on ruleset 20597822), because removing it also removes the operator's
own escape when ``gate`` is red for a harness reason. That leaves nothing but
habit between an agent and ``gh pr merge --admin`` — which ran 49 times in 9
days while a PR-body gate was teaching people to route around it (#1023). So
the refusal is keyed on the EFFECT, whatever the spelling:

* ``gh api`` on ``/pulls/<n>/merge`` or ``/repos/<o>/<r>/merges`` (an explicit
  ``GET`` with no body is a read and passes), a GraphQL ``mergePullRequest`` /
  ``mergeBranch`` mutation, or ``curl``/``Invoke-RestMethod`` on a merge URL;
* ``gh pr merge`` with anything but ``--auto``, ``--squash``,
  ``--delete-branch``, ``-d``, ``-s``, the PR number or URL (and ``-R``/
  ``--repo`` naming it) — and without ``--auto`` it merges now, so that is
  refused too;
* ``git push`` whose refspec lands on ``master``/``main`` (``HEAD:master``,
  ``+master``, ``origin master``, ``refs/heads/main``, ``--delete main``), a
  bare push or ``HEAD`` while the default branch is checked out, and
  ``--all``/``--mirror``. ``--dry-run`` / ``-n`` pass.

Ships in SHADOW until 2026-10-13: it logs ``would-deny`` and refuses nothing
until its false-positive count is measured. The only switch is
``RAILS_MERGE_BY_EFFECT_OK`` in the hook's own environment.
"""

from __future__ import annotations

import re

from rails.gates.destructive import (
    DEFAULT_BRANCHES,
    command_name,
    commands,
    git_subcommand,
    push_targets,
)
from rails.hookio import Deny, Event
from rails.shell.override import in_environment

NAME = "merge_by_effect"

OVERRIDES = ("RAILS_MERGE_BY_EFFECT_OK",)

_MERGE_PATH = re.compile(
    r"(?:^|/)pulls/[^/\s?]+/merge(?:$|[/?])|(?:^|/)repos/[^/\s]+/[^/\s]+/merges(?:$|[/?])"
)
_MERGE_MUTATION = re.compile(r"\b(?:mergePullRequest|mergeBranch)\b")
_HTTP_CLIENTS = frozenset(
    {"curl", "wget", "http", "invoke-restmethod", "irm", "invoke-webrequest", "iwr"}
)
_ALLOWED_MERGE_FLAGS = frozenset({"--auto", "--squash", "--delete-branch", "-d", "-s", "--disable-auto"})
_PR_REF = re.compile(r"^(?:#?\d+|https?://\S+/pull/\d+/?)$")
_API_BODY_FLAGS = ("-f", "-F", "--field", "--raw-field", "--input")


def _api_method(args: list[str]) -> str:
    for index, tok in enumerate(args):
        if tok in ("-X", "--method") and index + 1 < len(args):
            return args[index + 1].upper()
        if tok.startswith("--method="):
            return tok.split("=", 1)[1].upper()
        if tok.startswith("-X") and len(tok) > 2:
            return tok[2:].upper()
    return ""


def _has_body(args: list[str]) -> bool:
    return any(
        tok in _API_BODY_FLAGS
        or tok.startswith(("--field=", "--raw-field=", "--input="))
        or (tok[:2] in ("-f", "-F") and len(tok) > 2)
        for tok in args
    )


def _gh_api(args: list[str]) -> str | None:
    if _api_method(args) == "GET" and not _has_body(args):
        return None
    if any(_MERGE_PATH.search(tok) for tok in args):
        return "merges through the REST API"
    if "graphql" in args and any(_MERGE_MUTATION.search(tok) for tok in args):
        return "merges through a GraphQL mutation"
    return None


def _gh_pr_merge(args: list[str]) -> str | None:
    refs = 0
    skip = False
    for index, tok in enumerate(args):
        if skip:
            skip = False
            continue
        if tok in _ALLOWED_MERGE_FLAGS:
            continue
        if tok in ("-R", "--repo") and index + 1 < len(args):
            skip = True
            continue
        if tok.startswith("--repo="):
            continue
        if not tok.startswith("-") and _PR_REF.match(tok) and refs == 0:
            refs += 1
            continue
        return f"`gh pr merge` with `{tok}`"
    if "--disable-auto" in args:
        return None  # turns auto-merge off: the disarm's own remedy, never a merge
    if "--auto" not in args:
        return "`gh pr merge` without `--auto` merges now instead of arming"
    return None


def _git_push(tokens: list[str], evt: Event) -> str | None:
    sub, args, where = git_subcommand(tokens, evt.cwd)
    if sub != "push":
        return None
    targets, flags = push_targets(args, where)
    if flags["dry_run"]:
        return None
    if flags["all"]:
        return "`git push --all/--mirror` would move the default branch"
    hit = DEFAULT_BRANCHES.intersection(targets)
    if hit:
        return f"pushes straight onto `{sorted(hit)[0]}`"
    return None


def _offence(tokens: list[str], evt: Event) -> str | None:
    name = command_name(tokens[0])
    if name == "gh" and len(tokens) > 1:
        if tokens[1] == "api":
            return _gh_api(tokens[2:])
        if tokens[1] == "pr" and len(tokens) > 2 and tokens[2] == "merge":
            return _gh_pr_merge(tokens[3:])
        return None
    if name in _HTTP_CLIENTS:
        if any(_MERGE_PATH.search(tok) for tok in tokens[1:]):
            return "merges through the REST API"
        return None
    if name == "git":
        return _git_push(tokens, evt)
    return None


def check(evt: Event) -> Deny | None:
    shell = evt.shell
    if shell is None:
        return None
    command = evt.command
    if not command or in_environment(*OVERRIDES):
        return None
    for segment, tokens in commands(command, shell):
        why = _offence(tokens, evt)
        if why:
            shown = " ".join(segment.split())[:160]
            return Deny(
                f"Agents do not merge; they arm auto-merge and let the required\n"
                f"checks decide. This {why}:\n"
                f"    {shown}\n\n"
                f"Arm it instead:\n"
                f"    gh pr merge <n> --auto --squash\n\n"
                f"The merge then happens when the required check is green, with\n"
                f"nothing bypassed. Every other route (`--admin`, the merge API, a\n"
                f"push onto the default branch) is what 49 `--admin` merges in 9 days\n"
                f"were made of. If a merge by hand is genuinely needed, the operator\n"
                f"does it."
            )
    return None
