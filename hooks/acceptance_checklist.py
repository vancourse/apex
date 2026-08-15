"""PreToolUse hook: a PR that closes an issue gets that issue's `Done when` injected.

`Closes #N` is what makes a milestone's issue count mean anything, and it is also the
moment nobody re-reads what #N asked for. The criteria were written when the work was
understood least; the PR is filed when it is understood most; nothing in between forces
a comparison. This hook is that comparison, at the only moment it is free — while the
body is still being written.

**Advisory on purpose.** The blocking version of this is
`templates/gates/acceptance_check.py`, and it runs in CI where an author can fix the
body and push. Here, a denial would fire on a body that is one paste away from correct
— and a gate that fires on correct work teaches people to reach for `--admin`, which
skips every *other* check too. So this injects the block and gets out of the way.

**One implementation, not two.** The extraction rules — bullets under the acceptance
heading only, stop at the next heading, prose is not a finding, normalised comparison —
all carry measured reasons, and a hook with its own copy of them is a fork that drifts
until the advisory message and the blocking gate disagree about what the PR needs. This
imports the gate.

**A failed issue read is stated, never swallowed.** "This issue has no criteria" and
"the token could not read this issue" produce identical silence, and the first one is
what the reader will assume. So the message says which issues could not be read.
"""

from __future__ import annotations

import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _hooklib import (  # noqa: E402
    command_key,
    emit,
    fail_open,
    find_repo_root,
    invocation_index,
    plugin_root,
    read_payload,
    run,
    submitted_body,
    warn_once,
)

sys.path.insert(0, str(plugin_root() / "templates" / "gates"))

from acceptance_check import (  # noqa: E402
    ForgeReadError,
    acceptance_criteria,
    check,
    checklist,
    closed_issue_numbers,
    gh_issue_body,
)

#: `edit` as well as `create`: the measured shape is a PR opened early as a draft (see
#: `apex:pr-discipline` §1) and given its real body later, so the create-time body is
#: often a placeholder and the edit is where the closes-line first appears.
INVOCATIONS = (("gh", "pr", "create"), ("gh", "pr", "edit"))

#: Short, because a human is waiting on the `gh` call this runs in front of.
FETCH_TIMEOUT = 15


def collect(numbers: list[int]) -> tuple[dict[int, list[str]], list[int]]:
    """`(criteria by issue, issues that could not be read)`.

    The unreadable list is returned rather than logged so the message can name them.
    """
    criteria: dict[int, list[str]] = {}
    unreadable: list[int] = []
    for number in numbers:
        try:
            criteria[number] = acceptance_criteria(
                gh_issue_body(number, timeout=FETCH_TIMEOUT)
            )
        except ForgeReadError:
            unreadable.append(number)
    return criteria, unreadable


def message(
    criteria: dict[int, list[str]], unreadable: list[int], unanswered: list
) -> str | None:
    """The injected context, or None when there is nothing to inject.

    Silence covers three cases and is right for all of them: every criterion already
    ticked, every closed issue stating acceptance as prose, and no closed issue
    stating criteria at all. This hook runs in front of a `gh pr create` somebody is
    waiting on, so it earns its interruption only by handing over text they need —
    confirming that a correct body is correct is how an advisory hook gets ignored,
    and then it is ignored on the PR where it mattered too.
    """
    if not unanswered and not unreadable:
        return None

    lines = [
        "ACCEPTANCE — this PR body closes issues, so it inherits their criteria.",
        "",
    ]

    if unreadable:
        lines += [
            "Could NOT read "
            + ", ".join(f"#{n}" for n in unreadable)
            + " — so this is not a report that they have no criteria. Check them "
            "yourself.",
            "",
        ]

    if unanswered:
        issues = sorted({finding.issue for finding in unanswered})
        lines += [
            f"{len(unanswered)} criterion/criteria are not ticked in the body you are "
            "about to submit.",
            "Paste this in, and tick what is true:",
            "",
            checklist({number: criteria.get(number, []) for number in issues}),
            "",
            "Tick honestly. A criterion that turned out to be the wrong one is stated in "
            "the body as",
            "wrong — not ticked, and not quietly dropped. That sentence is the most "
            "valuable thing in",
            "the PR, because it is the only record that the issue was re-read at all.",
        ]

    return "\n".join(lines)


def main() -> None:
    payload = read_payload()
    if payload.get("tool_name") != "Bash":
        fail_open()

    command = str(payload.get("tool_input", {}).get("command", ""))
    if not command:
        fail_open()
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        fail_open()

    start = next(
        (
            index
            for invocation in INVOCATIONS
            if (index := invocation_index(tokens, invocation)) is not None
        ),
        None,
    )
    if start is None:
        fail_open()

    root = find_repo_root(Path(str(payload.get("cwd") or Path.cwd())))
    if root is None:
        fail_open()

    body = submitted_body(command, root, start)
    # An unreadable `--body-file` (an unexpanded `$VAR`, which is how a hook sees it)
    # tells us nothing about what the body closes. Guessing "closes nothing" here would
    # be silent and wrong; the artifact-template hook already reports that condition.
    if body is None or body[0] != "text":
        fail_open()

    numbers = closed_issue_numbers(body[1])
    # A cheap early exit, not a guard: with no closed issues the message below would
    # come out None anyway. It is here so a PR that closes nothing does not leave a
    # `warn_once` marker behind, and it is labelled because a reader auditing the
    # guards should not spend time looking for the test that pins it — there isn't
    # one, and removing this line changes no observable behaviour.
    if not numbers:
        fail_open()
    # Keyed on the command so a corrected retry is checked again rather than muted.
    if warn_once(
        str(payload.get("session_id", "nosession")), f"acc-{command_key(command)}"
    ):
        fail_open()

    criteria, unreadable = collect(numbers)
    context = message(criteria, unreadable, check(body[1], criteria))
    if context is None:
        fail_open()
    emit(context)


if __name__ == "__main__":
    run(main)
