---
name: council-review
description: Bounded three-seat review council for the HIGHEST-stakes freeze decisions only — extends apex:adversarial-pair from two voices to three chartered, context-isolated seats (completeness steelman / security-and-failure adversary / operability-and-simplicity skeptic), each reading ONLY the artifact + its charter, then a cold reconciliation where independent agreement escalates to blocker and explicit disagreement goes to the human with both arguments. One round, no debate loops. Includes the model-routing rule: route each seat to the model class its charter needs (deep-reasoning for the adversary, never a fast model for the freeze decision). Explicitly NOT a persona swarm (the survey-rejected BMAD pattern) — seats are review lenses on one frozen-candidate artifact, never author personas generating content. Reserve for: architecture freeze, security-sensitive design freeze, irreversible data migrations, public API freeze. Default reviews stay single-agent; non-trivial stays apex:adversarial-pair. Pairs with apex:adversarial-pair (the 2-seat mechanic this extends), apex:spec-view (render the artifact for the human tiebreak). Keywords: council, multi-model, ensemble, three reviewers, high stakes, second opinion, model routing, panel review, independent review.
---

# Council Review (three seats, one round)

`adversarial-pair` runs two voices: steelman + attacker. For a small class of decisions — the ones that are expensive or impossible to walk back — two voices share a blind spot: **neither owns operability**, and a single adversary's misses are uncorrelated with nobody. The council adds exactly one seat and exactly zero rounds of debate.

## When (and when NOT) to convene

**Convene for:** architecture freeze (the 7-ADR set) · design freeze of an auth / payment / multi-tenant / crypto feature · an irreversible or destructive data migration plan · a public API freeze (post-1.0 surface someone external will pin).

**Do NOT convene for** anything else. The escalation ladder is: inline counter-pass (every review skill, free) → `adversarial-pair` (non-trivial artifacts) → council (the four cases above). A council on a routine design is ceremony — the exact kitchen-sink reflex apex exists to reject.

**Not a persona swarm.** The survey (docs/research/sdlc-frameworks-survey.md) explicitly rejects BMAD-style persona swarms — many personas *authoring* content. Council seats never author; they review ONE frozen-candidate artifact through assigned lenses, and three is the cap because seats beyond the third add correlation, not coverage.

## The three charters

Each seat receives **only**: the artifact under freeze, its upstream frozen inputs (e.g. the PRD for a design freeze), and its own charter. Seats run context-isolated (separate agents, worktree-isolated when they need the repo — reuse `adversarial-pair`'s dispatch mechanics) and never see each other's findings until reconciliation.

1. **Seat A — Completeness steelman.** Make the artifact's strongest case, then find what's missing from within its own logic: unstated assumptions, scenario gaps, requirements it silently dropped. (The cooperative voice of `adversarial-pair`.)
2. **Seat B — Security + failure adversary.** Attack it: abuse cases, trust-boundary crossings, the failure modes of every external dependency, partial-completion states, the 2am rollback. (The adversarial voice, sharpened to security/failure.)
3. **Seat C — Operability + simplicity skeptic.** The seat the pair lacks. Two questions: *can a person who didn't build this run, debug, and modify it?* and *what here is more design than the problem deserves?* — pure-addition smell, speculative generality, the simpler shape that does 90% (cites `rules/principles.md`).

## Model routing (the "right model for the task" rule)

Route each seat to the model **class** its charter needs — classes, not vendor names, so the rule outlives any pricing page:

| Class | Use for | Never for |
|---|---|---|
| **Deep-reasoning** (strongest available) | Seat B always; Seat A on architecture freezes; the reconciliation | — |
| **Balanced** (default tier) | Seats A and C in the common case | — |
| **Fast/cheap** | Mechanical pre-passes only (lint-style conformance, enumeration) | Any council seat; any freeze decision |

Two rules with teeth: **the adversary is never the cheapest seat** (an attack that costs nothing finds nothing), and **a fast model never decides a freeze**. Genuinely different model *families* per seat add error-decorrelation on top of charter-decorrelation — use it when available; don't block on it.

## Reconciliation (cold, mechanical, one table)

Collect the three reports, then resolve by rule — not by debate:

| Pattern | Resolution |
|---|---|
| ≥2 seats independently raise the same finding | **Blocker by default.** Independent agreement under isolated contexts is the strongest signal this mechanic produces. |
| One seat raises it; the others are silent | Triage on merits — silence is non-overlapping charters, not disagreement. |
| One seat raises it; another **explicitly rejects** it | **To the human, verbatim, both arguments.** Never average a genuine disagreement into a "medium" — disagreement between isolated reviewers is the council's most valuable output. |

Output: one reconciliation table (finding · seats · severity · resolution) appended to the artifact's review section. Then the freeze proceeds, or the artifact reopens at the named upstream gate. **One round** — the council does not iterate; if the artifact changes materially in response, the *changed sections* get a normal `adversarial-pair` pass, not a re-convened council (the Shape-Up-style cap that keeps the council from becoming a committee).
