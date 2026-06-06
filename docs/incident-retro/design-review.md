# design-review — `incident-retro`

Applied `apex:design-review` (5+1 passes, adversarial lens, cold) to `design.md`, plus freeze. **[FIXED]** folded in before freeze; **[ACCEPTED]** = explicit residual.

**Pass 1 — Scenarios.** Walked S1–S5.
- *Missing flow:* what if the **cause is unknown** when the retro is invoked? The mapping ("which gate should have caught it") is impossible without a cause. **[FIXED]** — design Pass 5 routes cause-unknown to `superpowers:systematic-debugging` first; the retro starts after the cause is known.

**Pass 2 — MVP cut.** Struck each element:
- Strike blameless-reframe → AC1 fails. Strike gate-mapping → AC2 fails (the whole point). Strike lesson-emit → AC3 fails. Strike corrective-actions → AC4 fails. Strike scope-guard → becomes incident-response. Irreducible.
- *Added-beyond-PRD:* nothing — MVP is exactly the 5 AC checks. No scope creep found.

**Pass 3 — Deferral list.** Trend-metric, auto-PR, near-miss-from-CI, severity/timeline — none hot-fix-bite. *Confirmed* two correct rejections (not just deferrals): **auto-opening the amendment PR** (would break "apex doesn't self-mutate") and **severity/timeline** (would make it an incident-response tool — the PRD's core scope wall).

**Pass 4 — Integration.**
- *Duplication risk:* a second lesson store competing with `domain-knowledge`. **[FIXED]** — design makes the retro the *producer* that calls `memory-note`; no second store. Dedup-check prevents `domain-knowledge` bloat.
- *Broken invariant:* none — zero-ambient-cost (user-invoked, no hooks) and no-self-mutation both preserved.
- *Adversarial — the loop's own risk:* could `incident-retro` propose amendments that contradict a *frozen* apex design? **[ACCEPTED]** — the proposal feeds a normal PR which goes through the gates (including, once built, the cross-artifact-consistency analyzer) — so the loop is self-policing.

**Pass 5 — Failure modes.** Each has stated user-visible behavior (unresolved → redirect; cause-unknown → debugging; no-gate → candidate-gate finding; duplicate → annotate; `FLOW.md` unreadable → degrade).
- *Feature-unique mode:* **secrets/PII in the incident description** leaking into the durable lesson. **[FIXED]** — Pass 6 instructs capturing the *class/lesson*, not raw data; mirrors `scan-secrets-on-edit`'s intent.

**Pass 6 — Attack surface.** STRIDE-lite present; the real risk (PII/secrets in the persisted lesson) has a mitigation. No network/auth/external-input beyond user text. Heavier two-agent threat-model omission justified (local read/write learning tool).

**Overlap + OSS.** Audited: `memory-note` reuse (not a second store); blameless-postmortem templates referenced, platforms (incident.io/Rootly) rejected. No synonym-grade internal miss. **[PASS]**

**Adversarial-pair omission.** Single-agent — justified (no security-critical surface; design-doc artifact; the one control is the PII-in-lesson guard).

## Freeze verdict

**FROZEN (2026-06-06).** One Pass-1 fix (cause-unknown → debugging boundary) and one Pass-5/6 fix (PII-in-lesson guard) applied — minor, not a reshape. All adversarial findings resolved or accepted; PRD U1–U3 resolved.

**Self-referential note:** the loop is satisfyingly closed — a future `incident-retro` "no covering gate" finding would feed a `/apex:prd` exactly as *this* feature was authored, and its preventative amendments would be checked by the *other* feature frozen today (`cross-artifact-consistency`). The two dogfooded skills reinforce each other.

**Next:** `impl-plan` → `impl-plan-review` (single-PR skill, no API surface).
