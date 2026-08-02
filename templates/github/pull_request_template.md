<!--
Front-load reviewer-facing intent. A reviewer who has to reconstruct WHY from the
diff reviews the diff; a reviewer who is told why reviews the decision.
Delete any section that genuinely does not apply — an empty heading is noise.
-->

Closes #

## What this does

<!-- One paragraph. The change, not the changelog. -->

## Why this shape

<!-- The alternative you rejected and the reason. If there was no alternative, say so. -->

### Reuse verdict

<!--
For each NEW capability this PR introduces, name the existing primitive you
checked and the verdict. Delete this block only if the PR introduces no new
capability.
-->

| New capability | Existing primitive checked | Verdict |
| --- | --- | --- |
|  |  | USE / EXTEND / JUSTIFIED-NEW |

## Wiring

<!--
The repo's most-repeated defect is code that is built, tested, green — and
imported by nothing. Answer both, even when the answer is "nothing yet".
-->

- **Production callers:** <!-- who imports this from apps/ or a deployed process? -->
- **Ships inert?** <!-- no | yes, gated on <condition> — and where the un-gating is tracked -->

## How it flows

<!-- The path through the change: entry point -> what happens -> where it lands. -->

## State, concurrency, transport

<!-- Delete the lines that do not apply. -->

- **Who owns the state:**
- **What runs concurrently, and what serialises it:**
- **Transport / queue choice, and why that one:**

## Success, failure, fallback

- **Success:**
- **Failure:**
- **Fallback:**

## Test plan

<!-- Which layer each test sits at, and which scenario it mirrors. Paste the run. -->

```
```

## Risk note

<!--
Required if this touches auth, data access, concurrency, billing, migrations, or
an external API. Name the blast radius and the rollback.
-->

- **Blast radius:**
- **Rollback:**

---

- [ ] `python ci/pre_pr_check.py` passes locally
- [ ] Docs updated where the change makes existing prose wrong (CLAUDE.md, ADRs, READMEs)
