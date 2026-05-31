# apex × Spec Kit / BMAD — interop guide

apex is the **adversarial review + freeze layer**. It doesn't author specs from
scratch as well as the dedicated spec-driven tools do — and it doesn't need to.
[GitHub **Spec Kit**](https://github.com/github/spec-kit) and
[**BMAD-METHOD**](https://github.com/bmad-code-org/BMAD-METHOD) are excellent at
*generating* artifacts (spec → plan → tasks) with a polished slash-command UX.
What they deliberately stop short of is the thing apex exists for: the **cold,
adversarial review** of each artifact before it becomes a contract for the next
phase.

So the integration is composition, not competition:

> **Author with Spec Kit / BMAD. Review and freeze with apex.**

Both tools produce **files**, and every apex gate operates on a file. That
artifact symmetry is the whole bridge — no plugin-to-plugin wiring required.

## The mapping

### Spec Kit → apex

| Spec Kit step / artifact | Run this apex gate before moving on |
|---|---|
| `/speckit.constitution` → `.specify/memory/constitution.md` | `apex:arch` + `apex:adr-review` (the constitution *is* a set of architecture decisions — audit each) |
| `/speckit.specify` → `specs/NNN-feature/spec.md` | **`apex:prd-review`** — 7-pass audit + overlap/OSS scans + adversarial counter-pass; freeze before `/speckit.plan` |
| `/speckit.plan` → `plan.md`, `data-model.md`, `contracts/` | **`apex:design-review`** (cold adversarial re-pass + freeze) + `apex:api-surface-review` on `contracts/` + `apex:threat-model` |
| `/speckit.tasks` → `tasks.md` | **`apex:impl-plan-review`** — layered PR stack, sequencing, test-plan-per-layer, rollout, reversibility |
| `/speckit.implement` | apex's `[AUTO]` gates fire by file path (`python-review` / `typescript-review` / `security-review`) + `apex:verification-before-completion` |

> Spec Kit's optional `/speckit.analyze` and `/speckit.checklist` are exactly
> the "external reviewer" slots — point them at apex.

### BMAD → apex

| BMAD artifact | Run this apex gate |
|---|---|
| `docs/prd.md` (PM agent) | **`apex:prd-review`** |
| `docs/architecture.md` (Architect agent) | **`apex:arch` / `apex:adr-review`** + system-level `apex:threat-model` |
| Story files (per feature) | **`apex:design-review`** then **`apex:impl-plan-review`** |
| `project-context.md` ("constitution") | `apex:adr-review` lens — are these decisions justified, with alternatives + reversibility? |

## The workflow, concretely

A Spec-Kit-driven feature with apex gates interleaved:

```
/speckit.specify          # Spec Kit authors specs/NNN/spec.md
apex:prd-review           # apex audits it — 7 passes + adversarial counter-pass
  → fix findings, FREEZE the spec
/speckit.plan             # Spec Kit authors plan.md + contracts/
apex:design-review        # apex re-walks it from the attack lens + freeze ceremony
apex:api-surface-review   # on contracts/ (consumer's perspective)
apex:threat-model         # STRIDE on the feature's attack surface
  → fix findings, FREEZE the design
/speckit.tasks            # Spec Kit authors tasks.md
apex:impl-plan-review     # apex audits the task breakdown (layering, tests, rollout)
  → fix findings, FREEZE the plan
/speckit.implement        # Spec Kit executes; apex's [AUTO] review gates fire by file path
apex:verification-before-completion   # prove it works before "done"
```

The rule that makes this coherent is apex's own: **a drafted artifact is
authored, not frozen.** Spec Kit / BMAD do the authoring; apex supplies the
review-and-freeze gate that neither tool ships.

## Don't double-author

The one thing to avoid: re-writing with apex what the other tool already wrote.

- Spec Kit's `spec.md` ≈ apex's PRD. **Don't** also run `/apex:prd` to author a
  second PRD — run `apex:prd-review` *on their `spec.md`*.
- Spec Kit's `plan.md` ≈ apex's design doc. **Don't** also run `/apex:design` —
  run `apex:design-review` *on their `plan.md`*.
- Spec Kit's constitution / BMAD's `architecture.md` ≈ apex's ADRs. Review them,
  don't re-derive them.

Use apex's authoring commands (`/apex:prd`, `/apex:design`, `/apex:impl-plan`)
**only** when you are *not* using a spec-driven tool to author. When you are,
apex contributes its review skills (`prd-review`, `design-review`,
`impl-plan-review`, `adr-review`, `threat-model`, `security-review`) and
`apex:spec-view` (render their artifact as a freeze-review dashboard for a human).

## Why this split is the honest one

apex's differentiator is the **cooperative + adversarial pair** — running the
attack review *cold, in a separate cognitive step* so the author voice doesn't
grade its own work. Spec Kit and BMAD lead on **generation, orchestration, and
slash-command UX**; apex leads on **adversarial design-quality review**. Bolting
apex's review gates onto their generation gives you both, with neither tool
doing the other's job badly.
