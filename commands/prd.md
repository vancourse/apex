---
description: "[USER] Author a new PRD — invokes superpowers:brainstorming (explore intent) → superpowers:writing-plans (draft the spec). Suggest prd-review afterward to audit + freeze."
---

Author a new Product Requirements Document for the user's feature idea.

Run this sequence:

1. **Invoke the `brainstorming` skill from the superpowers plugin** to explore intent, requirements, and design through collaborative dialogue. Read its SKILL.md and follow it. Ask questions one at a time. Don't skip to drafting until the intent is well understood and the user has signaled agreement on the shape.

2. **Invoke the `writing-plans` skill from the superpowers plugin** to translate the agreed intent into a written PRD. Read its SKILL.md and follow it. Save the draft to **`docs/<feature-slug>/prd.md`** (kebab-case slug derived from the feature name; create the folder). This is apex's standard per-feature location — the feature's `design.md` and `impl-plan.md` will live beside it, and `docs/adr/` holds project-wide architecture. Confirm the slug with the user only if the feature name is ambiguous.

3. After the draft exists, **the PRD must pass `prd-review` and be FROZEN before `apex:design-feature` may begin.** `prd-review` runs the 7-pass audit (acceptance criteria, scenarios, scope, unknowns, metric, sequencing, freeze) plus product-overlap + OSS-alternatives scans + adversarial counter-pass. Don't auto-invoke it mid-authoring — the *timing* of the freeze is the user's call — but a drafted PRD is **authored, not frozen**, and design may not start against an un-reviewed PRD.

Stop after step 2 with the draft saved. The next gate is `prd-review` → freeze, before any design. Do not start designing or implementing.
