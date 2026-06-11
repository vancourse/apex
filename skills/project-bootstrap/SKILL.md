---
name: project-bootstrap
description: Greenfield project creation gate — take an idea from "empty directory" to "running repo with apex discipline pre-wired" in one guided pass; scaffold via the stack's OFFICIAL generator (never hand-rolled), wire the docs/ artifact convention + CLAUDE.md skill gates + a least-privilege CI baseline, then hand off to apex:architecture-design (the 7-ADR foundation) and /apex:prd for the first walking-skeleton feature. Also runs in ADOPT mode for an existing repo (wire apex in, skip the scaffold). Distinct from /apex:setup (installs apex's own companions into Claude Code) and apex:architecture-design (the decisions; this is the surrounding rig). Pairs with apex:cicd-review (audits the CI baseline it writes) and apex:detect-stack (profile the tooling once it exists). Keywords: new project, from scratch, greenfield, scaffold, bootstrap, init, create app, empty repo, adopt apex, brownfield.
---

# Project Bootstrap (Greenfield + Adopt)

apex's pipeline starts at "PRD on an existing repo" — this skill builds the repo the pipeline assumes. One pass, two modes:

- **GREENFIELD** — empty (or nearly empty) directory → scaffolded, git-initialized, CI'd, apex-wired project with the first feature queued.
- **ADOPT** — existing project → apex's artifact convention + gates wired in, nothing else touched.

**Mode detection:** source files already exist + git history → ADOPT (confirm with the user). Otherwise GREENFIELD.

## YAGNI guard

A throwaway script, a one-file tool, or an experiment does **not** get the ceremony: scaffold (P2) and stop. The full pass is for software that will have users, releases, and a second contributor — when in doubt, ask "will this outlive the week?"

## GREENFIELD — the five steps

### P0 — Intake (one paragraph, not a workshop)

Capture in ≤1 paragraph: what is being built, for whom, the appetite (time budget — Shape Up framing: what is this worth?), and the 2–3 hard constraints (compliance, platform, existing systems it must talk to). Do NOT design here. If the user can't answer "for whom," stop — that's a `superpowers:brainstorming` conversation, not a bootstrap.

### P1 — Architecture foundation

Route to **`apex:architecture-design`** — the existing 7-ADR gate (framework / persistence + tenancy / auth + data classification / observability + deploy / design system / branch + release / threat model). Bootstrap does not duplicate one line of it. The stack chosen in ADR-1 drives P2.

*Lightweight variant:* for a small single-tenant tool, the user may accept the 7 answers as one short `docs/adr/0001-foundations.md` instead of 7 files — the questions are mandatory, the ceremony is not.

### P2 — Scaffold (official generator, never hand-rolled)

Scaffold with the stack's **official generator** at its current defaults — `npm create vite@latest` / `npx create-next-app@latest` / `uv init` / `cargo new` / `dotnet new` / framework equivalent. Never hand-write the skeleton a generator maintains: hand-rolled skeletons fossilize the generator's last-known state (the `verify-ports` staleness problem, applied to project shape).

Then: `git init` + first commit of the pristine scaffold (so every later diff is readable), `.gitignore` from the generator plus secrets patterns (`.env*`, key material), README stub with the P0 paragraph.

### P3 — apex wiring

- `docs/adr/` (from P1) and the per-feature `docs/<feature-slug>/` convention (see FLOW.md "Where artifacts live").
- A project `CLAUDE.md` declaring the skill gates: plan-before-code, the freeze chain (PRD → design → impl-plan), prove-it-works, and any stack-specific review skill (`python-review` / `typescript-review` / `postgres-review`).
- Run `/apex:detect-stack` once tooling exists (tracker / observability / reproduce), or note it as a TODO in CLAUDE.md.

### P4 — CI baseline (small, least-privilege, day one)

One workflow: lint + typecheck + test on PR, `permissions: contents: read` at the top, third-party actions pinned by full SHA, a timeout on every job. Nothing else — no deploy job before there is something to deploy (that arrives with `apex:deployment-review` when the time comes). Hand the file to **`apex:cicd-review`** before the commit that adds it.

### P5 — First feature: the walking skeleton

Queue exactly **one** feature via `/apex:prd`: the thinnest end-to-end slice that proves the architecture (one request through every layer to persistence and back). Resist seeding a backlog — the walking skeleton IS the backlog until it ships.

## ADOPT — existing repo

Run only P3 (+ P4 if no CI exists; if CI exists, offer `apex:cicd-review` on it instead). Do not scaffold, restructure, or "clean up" — adoption earns trust by touching nothing. If the project has no ADRs, offer a single retroactive `docs/adr/0001-as-built.md` capturing the 7 answers **as they already are** (descriptive, not aspirational).

## Adversarial counter-pass

Before declaring bootstrap done, attack the output:

1. **Speculative-structure smell** — every empty directory, placeholder module, and "we'll need this later" file is a defect. The scaffold should contain only what the generator emitted plus what P3–P5 require. Delete the rest.
2. **Generator fidelity** — did anything get hand-edited that the generator owns (build config, tsconfig)? Each such edit needs a one-line justification or a revert.
3. **Day-two test** — could a second contributor clone, run the test suite, and find the next task (the queued PRD) inside 15 minutes using only the README + CLAUDE.md? Walk it.
