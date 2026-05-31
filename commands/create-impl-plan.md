---
description: "[USER] Author an implementation plan against the frozen design — invokes superpowers:writing-plans. Suggest impl-plan-review afterward to audit + freeze (layered stack + sequencing + tests + rollout + reversibility)."
---

Author an implementation plan for the user's frozen design.

Prerequisites check:

- The design must be **FROZEN, not just drafted** — i.e. `apex:design-review` (the cold adversarial re-pass + design-freeze ceremony) has run on the `design-feature` draft and accepted it. A `design-feature` draft alone is authored, not frozen. If `design-review` hasn't run, **stop and run it first** — the impl plan is not the place to design, and an un-reviewed design is not a contract you can plan against.
- The PRD should already be frozen (via the `prd-review` skill). If it isn't, say so and stop.

Run this sequence:

1. **Invoke the `writing-plans` skill from the superpowers plugin** to translate the frozen design into a buildable, bite-sized implementation plan. Read its SKILL.md and follow it. The plan must include: which files to touch per task, test plan per layer, docs to consult, how to verify each step. Save the plan to **`docs/<feature-slug>/impl-plan.md`** — beside the feature's `prd.md` and `design.md` (same slug). Confirm the slug only if ambiguous.

2. After the draft plan exists, **the plan must pass `impl-plan-review` and be FROZEN before any implementation/coding begins.** `impl-plan-review` runs the 5-pass review: layered PR stack (≤400 LOC per PR, tests with their layer), sequencing / dependency order, test-plan-per-layer (PRD scenarios → integration tests 1:1), rollout strategy (flag / direct / migration-first / compat window), reversibility (rollback story). Don't auto-invoke it mid-authoring — the *timing* of the freeze is the user's call — but a draft plan is **authored, not frozen**, and coding may not start against an un-reviewed plan.

Stop after step 1 with the draft saved. The next gate is `impl-plan-review` → freeze, before any implementation. Do not start implementing.
