# Templates

Blank forms for the artifacts apex's gates review. apex has always told you to
write a PRD, a design and an impl-plan; until now it shipped no form for any of
them, so every author invented the shape and every review re-derived what "done"
meant. These are that shape, stated once.

| Template | Written to | Reviewed by |
| --- | --- | --- |
| [`recon.md`](recon.md) | `docs/<feature-slug>/recon.md` | — (feeds design) |
| [`prd.md`](prd.md) | `docs/<feature-slug>/prd.md` | `apex:prd-review` (freezes at Pass 7) |
| [`design.md`](design.md) | `docs/<feature-slug>/design.md` | `apex:design-review` |
| [`impl-plan.md`](impl-plan.md) | `docs/<feature-slug>/impl-plan.md` | `apex:impl-plan-review` |
| [`adr.md`](adr.md) | `docs/adr/00NN-<slug>.md` | `apex:adr-review` |
| [`milestone.md`](milestone.md) | the milestone **description** on the forge — not a repo file | `apex:release-loop` (step 3) |

The lineage runs `recon → prd → design → impl-plan`, one folder per feature, so
the folder holds the whole freeze chain in reading order. See
[`FLOW.md`](../FLOW.md) for where each sits in the pipeline.

`milestone.md` is the odd one out and deliberately so: it shapes a *release*, which
lives on the forge rather than in the tree, and it sits above the lineage rather
than inside it. One milestone wraps however many `recon → … → impl-plan` chains the
release needs. See [`apex:release-loop`](../skills/release-loop/SKILL.md).

`github/` holds the three GitHub templates — a PR template and two issue forms.
They are **not** used from here: `apex:install-gates` copies them into a target
repo's `.github/`, because GitHub only reads them from that path.

`gates/` holds the blocking CI checks, for the same reason and by the same route: a
plugin's hooks fire only inside Claude Code, so anything that must bind every actor
has to be a check running in the target repo. `apex:install-gates` copies these in
and wires them.

| Gate | Lane | Refuses |
| --- | --- | --- |
| [`pre_pr_check.py`](gates/pre_pr_check.py) | pre-PR / local | a branch whose base, scope or replay is wrong |
| [`pr_body_check.py`](gates/pr_body_check.py) | PR | a PR body missing the sections its own diff calls for |
| [`acceptance_check.py`](gates/acceptance_check.py) | PR | a PR that closes an issue without answering its `Done when` |
| [`milestone_completion_gate.py`](gates/milestone_completion_gate.py) | **scheduled** | a finished release left open past its grace period |

The last one is on a scheduled lane rather than a PR lane because the condition it
watches — a milestone whose issues are all closed, still open — becomes true *after*
the final PR merges, when no PR lane is running.

## You should not need to remember this

`hooks/artifact_templates.py` injects the matching form when a session creates one
of these files, and checks `gh pr create` / `gh issue create` bodies against the
repo's `.github/` templates — **naming the sections the body is missing**. GitHub
applies those templates only in its web UI; `gh pr create --body-file …` skips
them entirely, which is how an agent files nearly every PR. For the actor filing
most of a repo's artifacts, an unchecked template is decorative.

The hook is advisory: it injects context, it never denies. It only fires inside
Claude Code — for a check that binds everyone, see `apex:install-gates`.

## Overriding a form

Resolution is **repo first, plugin second**. A repo with its own
`docs/templates/<name>.md` keeps it; every other repo gets apex's the moment the
plugin is installed. The injected message names which one it used, so a reader
who disagrees with the shape knows which file to edit.

## Adding an artifact type

One row in `DOC_RULES` in `hooks/artifact_templates.py`, plus a file here. That is
the design: the shape of a repo's documents is carried by a table, not restated by
a human per feature. `hooks/tests/test_artifact_templates_hook.py` pins that every
rule points at a form that exists — a rule naming a missing skeleton makes the
hook silently useless for that type, and silence is its normal output.
