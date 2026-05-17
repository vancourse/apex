---
name: adr-review
description: Review a single Architecture Decision Record (ADR) before locking it in or accepting an amendment. 5-element audit — context, decision, alternatives, consequences (including security + cost + reversibility), status field. Plus adversarial counter-pass. Pairs with apex:architecture-design (produces 7 ADRs at project start) and runs at every amendment. Fires when authoring or reviewing an ADR — initial set, amendment to an existing one, or supersession. Keywords: ADR, architecture decision record, amendment, supersession, decision log.
---

# ADR Review

A single Architecture Decision Record (ADR) review. Used both for the initial set produced by `apex:architecture-design` and for every amendment / supersession after the architecture is frozen.

## When to invoke

- Authoring an ADR from one of `apex:architecture-design`'s 7 passes
- Authoring an amendment ADR when a feature crosses the existing architecture boundary
- Reviewing someone else's ADR before approving
- Auditing the ADR set for completeness

Pairs with `apex:architecture-design` (the producer) and `apex:design-feature` Pass 4 (the trigger for amendments — when a feature doesn't fit the existing architecture, you write an amendment ADR before designing the feature against the new shape).

## ADR canonical structure

```markdown
# ADR-NNNN: <Decision title>

**Status:** Proposed | Accepted | Superseded by ADR-MMMM | Deprecated
**Date:** YYYY-MM-DD
**Deciders:** <names / roles>
**Tags:** persistence | auth | tenancy | observability | ...

## Context

<What's the problem? What constraints apply? What's been tried? What's
already in place? Cite specific files / data / PRs if relevant.>

## Decision

<The decision, stated in one paragraph. Should be readable in isolation.>

## Alternatives considered

1. <Alt 1> — pro / con / why not
2. <Alt 2> — pro / con / why not
3. <Alt 3> — pro / con / why not

## Consequences

### Positive
- <What this decision enables>

### Negative
- <What this decision makes harder or impossible>

### Security implications
- <Effect on attack surface, trust boundaries, data classification — REQUIRED>

### Cost / operational implications
- <Cloud cost, ops burden, vendor lock-in>

### Reversibility
- <How hard is it to undo this? Estimate in days/weeks/months.>

## Compliance / references

- Supersedes: ADR-XXXX (if any)
- Related: ADR-YYYY, ADR-ZZZZ
- External: <RFCs, docs, spec links>
```

## The 5-element audit

### Element 1 — Context: is the problem actually stated?

**Check:** The Context section says *what's the problem and why now*, not *what's the decision*. Distinguishes constraints (immutable) from preferences (mutable).

**Pass condition:** A reader new to the project can understand the problem from Context alone.

**Adversarial counter-pass:** Find a constraint listed as Context that's actually a preference (e.g. "must be JSON-over-HTTP" — is that a hard requirement or a comfort zone?). Find a preference listed as Context that's actually a constraint. Get the categorization right; it changes the alternatives space.

### Element 2 — Decision: stated unambiguously, in one paragraph

**Check:** A single paragraph someone could quote verbatim. No "we will use Postgres, or possibly MySQL." No "we'll figure out tenancy in phase 2."

**Pass condition:** Decision is grep-able and quotable in code review.

**Adversarial counter-pass:** Try to misread the decision. If "we use JWT for auth" is ambiguous about *where* tokens live (cookie / localStorage / header), the decision is under-specified. Fix it.

### Element 3 — Alternatives: ≥2 real alternatives, not strawmen

**Check:** At least 2 alternatives that someone reasonable might have picked. Each with one-line pro, one-line con, one-line "why not."

**Pass condition:** A skeptical reviewer can't immediately think of a 3rd alternative you didn't consider.

**Adversarial counter-pass:** Find a strawman alternative (one obviously dismissed for shallow reasons — "we considered raw socket I/O" when the project is a CRUD web app). Strawmen weaken the ADR; replace with the real contender you didn't list.

### Element 4 — Consequences: enumerated, including the unhappy ones

**Check:** Both Positive AND Negative. Plus **Security implications** (mandatory), **Cost** (mandatory for cloud / vendor decisions), **Reversibility** (mandatory — how hard is undo?).

**Pass condition:** The Negative + Security sections each have ≥1 substantive bullet. "No downsides" = the ADR is lying or hasn't thought hard enough.

**Adversarial counter-pass:** Name a consequence the ADR doesn't list. Especially: a downstream feature this decision makes harder, a class of bug this decision enables, a vendor lock-in this introduces, a security property this weakens.

### Element 5 — Status field: present and current

**Check:** Status is one of Proposed / Accepted / Superseded by ADR-MMMM / Deprecated. Has a date. If amending an existing ADR, the old one is marked Superseded with a forward link.

**Pass condition:** Status reflects the current state. No stale "Proposed" ADRs that have been live for months.

**Adversarial counter-pass:** Find an ADR in this PR's diff whose Status hasn't been updated since the decision was finalized. (Common: ADR shipped as "Proposed", implementation lands, no one bumps to "Accepted".)

## Adversarial pair pattern

For high-stakes ADRs (auth model, tenancy, persistence, deploy shape — anything from `apex:architecture-design` Passes 2 / 3 / 4), dispatch the review as **two parallel agents** via `superpowers:dispatching-parallel-agents`:

- **Cooperative agent** — runs the 5 elements in steelman mode. Confirms the decision is defensible.
- **Adversarial agent** — runs the same in attack mode. Each counter-pass becomes the lens. Finds missing alternatives, hidden constraints, under-stated consequences, residual security risks.

Both agents work with the same ADR text. Reconcile their findings.

## Pass/fail summary

The ADR passes if all 5 elements meet their conditions AND adversarial findings are addressed. Fail any → revise before committing the ADR. ADRs are durable institutional memory — bad ADRs misinform every future amendment.

## Hand-off

Once the ADR passes:

- It's committed to `docs/adr/` (or your project's chosen path)
- The ADR set's `README.md` index is updated
- Downstream gates (`apex:design-feature`, `apex:prd-review`, `apex:threat-model`, `apex:security-review`) reference the ADR's decision as a constraint they must respect
- An amendment ADR also updates the superseded one's Status field
