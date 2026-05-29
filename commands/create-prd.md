---
description: "[USER] Author a new PRD — invokes superpowers:brainstorming (explore intent) → superpowers:writing-plans (draft the spec). Suggest /apex:prd-review afterward to audit + freeze."
---

Author a new Product Requirements Document for the user's feature idea.

Run this sequence:

1. **Invoke the `brainstorming` skill from the superpowers plugin** to explore intent, requirements, and design through collaborative dialogue. Read its SKILL.md and follow it. Ask questions one at a time. Don't skip to drafting until the intent is well understood and the user has signaled agreement on the shape.

2. **Invoke the `writing-plans` skill from the superpowers plugin** to translate the agreed intent into a written PRD. Read its SKILL.md and follow it. Save the draft to the project's PRD location (ask the user if unclear).

3. After the draft exists, **suggest the user run `/apex:prd-review`** to run the 7-pass audit (acceptance criteria, scenarios, scope, unknowns, metric, sequencing, freeze) plus product-overlap + OSS-alternatives scans + adversarial counter-pass. Do not invoke `prd-review` automatically — let the user choose when to lock the spec.

Stop after step 2 with the draft saved and the `/apex:prd-review` suggestion. Do not start designing or implementing.
