---
description: "[USER] Author an implementation plan against the frozen design — invokes superpowers:writing-plans. Suggest /apex:impl-plan-review afterward to audit + freeze (layered stack + sequencing + tests + rollout + reversibility)."
---

Author an implementation plan for the user's frozen design.

Prerequisites check:

- The design should already be frozen (via `/apex:design-feature` or equivalent). If it isn't, say so and stop — the impl plan is not the place to design.
- The PRD should already be frozen (via `/apex:prd-review`). If it isn't, say so and stop.

Run this sequence:

1. **Invoke the `writing-plans` skill from the superpowers plugin** to translate the frozen design into a buildable, bite-sized implementation plan. Read its SKILL.md and follow it. The plan must include: which files to touch per task, test plan per layer, docs to consult, how to verify each step. Save the plan to the project's plan location (ask the user if unclear).

2. After the draft plan exists, **suggest the user run `/apex:impl-plan-review`** to run the 5-pass review: layered PR stack (≤400 LOC per PR, tests with their layer), sequencing / dependency order, test-plan-per-layer (PRD scenarios → integration tests 1:1), rollout strategy (flag / direct / migration-first / compat window), reversibility (rollback story). Do not invoke `impl-plan-review` automatically — let the user choose when to freeze the plan.

Stop after step 1 with the draft saved and the `/apex:impl-plan-review` suggestion. Do not start implementing.
