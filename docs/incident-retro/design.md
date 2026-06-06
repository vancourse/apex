# Design — `incident-retro` (post-release learning loop)

**Status:** drafted (awaiting `design-review` → freeze) · **Slug:** `incident-retro`
**PRD:** `prd.md` (FROZEN 2026-06-06). Adversarial re-pass in `design-review.md`.

## Shape (one paragraph)

A **user-invoked `incident-retro` skill** (SKILL.md; invoked by name — *not* a new slash command, menu stays lean). Input: a *resolved* incident (the user describes it, or points at a postmortem). It runs a **blameless retro** in four moves: (1) restate as **contributing conditions**, not actors; (2) read `FLOW.md`'s gate matrix and map the incident to **the apex gate that should have caught it** (or "no covering gate"); (3) emit a durable **`domain-knowledge` lesson via `memory-note`** (dedup-checked); (4) produce **specific, owned corrective actions** split mitigative vs preventative — the preventative one being a *one-line proposal* to amend the missed gate (which feeds a normal apex PR if pursued). It writes a markdown retro + the lesson; nothing else.

## Pass 1 — Scenarios

Reuses PRD S1–S5 (gate-missed / no-gate / blame-leak / vague-action / mid-incident-misuse). Design-side load-bearing point: the skill is a **structured prompt + two reads (`FLOW.md`, `domain-knowledge`) + one write (`memory-note`)** — no runtime, no infra.

## Pass 2 — MVP cut

1. **Blameless reframe** — restate the incident as contributing conditions; reject person-blame and vague "be careful" (AC1).
2. **Gate-miss mapping** — load `FLOW.md`'s skill×phase matrix; name the gate(s) that should have caught it, or "no covering gate → candidate new gate" (AC2).
3. **Lesson emit** — write one durable `domain-knowledge` fact via `memory-note`, after a dedup check (AC3).
4. **Corrective actions** — ≥1 mitigative + ≥1 preventative, each specific + owned; the preventative is a one-line gate-amendment proposal (AC4).
5. **Scope guard** — refuse if the incident isn't resolved (AC5).

That's MVP — a single skill, no new command, no store.

## Pass 3 — Deferral list

- **Trend tracking across retros** (repeat-class rate as a computed metric) — V2; *trigger:* enough retros to mine. MVP records lessons; it doesn't compute the lagging metric (that'd need a store).
- **Auto-opening the amendment PR** (rejected) — the preventative proposal is one line a human carries into `/apex:prd` or a skill-edit PR; the skill never self-mutates apex (preserves the dogfood discipline).
- **Near-miss intake from CI logs** (V2) — *trigger:* demand; MVP takes a human-described incident.
- **Severity/timeline capture** (rejected — that's incident response, PRD §4).

*Adversarial check:* none hot-fix-bite; all are additive niceties.

## Pass 4 — Integration with existing surface

Reuses, does not duplicate:
- **`memory-note` / `domain-knowledge`** — the persistence target; the retro is the *producer*, `memory-note` does the write (≥2-primitive reuse #1; it does **not** create a second lesson store).
- **`FLOW.md` gate matrix** — read at runtime as the authoritative gate list (reuse #2; resolves U1 — no carried, drift-prone copy).
- **`superpowers:systematic-debugging`** — the upstream side-path that finds the *cause*; `incident-retro` starts after (clean boundary).

**Invariants preserved:** zero ambient cost (user-invoked only, no hooks, no background); apex **does not self-mutate** (proposes, human applies via PR). **Invariant not broken:** the learning loop feeds back into the *same* SDLC gates — an `incident-retro` preventative action becomes a normal `prd`/`design`/skill-edit PR.

## Pass 5 — Failure modes (user-visible behavior)

- **Incident not yet resolved** → redirect: "resolve first; this is the learning pass" (AC5); emits nothing.
- **Cause unknown** → route to `superpowers:systematic-debugging` first; retro can't map a miss without a cause.
- **No covering gate** → not a failure — emit the "candidate new gate" finding (the highest-value output).
- **Duplicate lesson** → dedup check finds a near-identical `domain-knowledge` entry → **update/annotate** the existing one rather than append a duplicate (resolves U2).
- **`FLOW.md` unreadable / gate list changed** → degrade to "map against the skills you can enumerate; flag that the gate matrix couldn't be loaded," don't crash.

## Pass 6 — Attack surface (STRIDE-lite)

Low. Reads `FLOW.md` + `domain-knowledge`, writes a `domain-knowledge` lesson. *Tampering/Info-disclosure:* an incident description could contain secrets/PII (logs, customer data). *Mitigation:* the retro captures the **lesson/class**, not raw incident data — explicitly instruct against pasting secrets/PII into the durable lesson (mirrors `scan-secrets-on-edit`'s spirit). No network, no auth, no external input beyond the user's own text. Heavier threat-model not warranted (stated).

## U-resolutions
- **U1 — RESOLVED:** read `FLOW.md`'s skill×phase matrix at runtime as the gate catalog (no carried copy → no drift).
- **U2 — RESOLVED:** dedup-check `domain-knowledge` before writing; near-identical lesson → update/annotate, not duplicate (reuses `memory-note`'s judgment).
- **U3 — RESOLVED:** the "no covering gate" output is a **one-line proposal only**; if pursued it *feeds* a real `/apex:prd` (exactly what we just did with this very feature). The skill never inlines a mini-spec — that's the scope-explosion wall.

## Hand-off
On `design-review` freeze → `impl-plan` (small: a SKILL.md + the structured retro prompt + the dedup/`FLOW.md` read conventions; likely a single-PR skill). No API surface.
