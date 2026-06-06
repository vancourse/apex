# Impl plan — `incident-retro`

**Status:** FROZEN as of 2026-06-06 · **Slug:** `incident-retro`
**Design:** `design.md` (FROZEN). Built in `skills/incident-retro/SKILL.md`.

A markdown-procedure skill — **single-layer** build; migration / rollout-cohort /
dependency-sequencing passes are N/A. Recorded tightly per "skip gates for small
work."

## §1 Layered stack (single layer)

- **L1 — the skill** `skills/incident-retro/SKILL.md` (frontmatter + the four
  moves: blameless reframe → gate-miss mapping via `FLOW.md` → durable lesson via
  `memory-note` → specific/owned corrective actions). Registered via `description`
  frontmatter; surfaced in README + FLOW.md. **User-invoked by name** — no slash
  command, no hook (zero ambient cost is an invariant).

## §3 Test plan (scenario lineage)

Manual exercise against fixture incident descriptions. Validation owners by
frozen-PRD scenario:

- **serves S1** (gate existed & missed → lesson + action) · **serves S2** (no
  covering gate → candidate gate) · **serves S3** (blame leak rejected) · **serves
  S4** (vague action rejected) · **serves S5** (mid-incident misuse redirected).
- No **E2E** owner — no UI surface (justified).

## §4 Rollout

Direct (activates next session). No flag, no migration.

## §5 Reversibility

Fully reversible — `git revert` the SKILL.md + registry rows. The only persistent
side effect is the `domain-knowledge` lessons it writes (intentional, durable —
not rolled back; that's the point of the loop).

## Plan freeze

FROZEN. Build complete (`skills/incident-retro/SKILL.md`).
