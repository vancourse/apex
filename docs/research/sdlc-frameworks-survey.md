# SDLC frameworks & AI-coding harnesses — survey for apex (2026-06)

Provenance for the dogfooded specs in `docs/cross-artifact-consistency/` and
`docs/incident-retro/`. A 5-angle deep-research pass mined other SDLC
frameworks, AI-coding harnesses, and methodology systems for ideas apex could
incorporate, filtered against apex's **lean + adversarial, zero-ambient-cost,
no-kitchen-sink** thesis and against what apex *already* does.

## Top adopts (ranked, on-thesis)

1. **Cross-artifact consistency analyzer** (GitHub Spec Kit `/analyze`) — the single biggest *structural* gap. apex reviews each artifact vertically; nothing checks the frozen PRD↔design↔impl-plan still **agree**. → dogfooded in `docs/cross-artifact-consistency/`.
2. **Expand/Contract (parallel-change) migration discipline** (gh-ost / Fowler) — apex's reversibility pass is thinnest exactly where data lives. → amend `impl-plan-review` Pass 4+5.
3. **`incident-retro` learning loop** (blameless postmortems, Google SRE) — apex learns from reviews/designs, never from production incidents. → dogfooded in `docs/incident-retro/`.
4. **Pre-mortem** (Gary Klein) — attacks the *project's success premise* (distinct from `threat-model` attacking the system). → small skill / design-freeze counter-pass.
5. **AI-code supply-chain pass** — slopsquatting (hallucinated-package check) + OWASP LLM Top-10 (prompt injection / excessive agency / untrusted output). Uniquely apex-relevant. → extend `guard-dependency-bump`; conditional `security-review` pass.
6. **Appetite + circuit-breaker** (Shape Up) — apex's one structural lack: a budget constraint + a default-to-kill gate. → amend PRD/design + `impl-plan-review` §5.
7. **Per-feature observability gate + LINDDUN-GO privacy branch** — both conditional (PII-/LLM-gated) design questions apex's once-at-arch / STRIDE-only model misses. → `design-feature` Pass 5 / `threat-model`.
8. **WCAG 2.2 testable a11y checklist** — turn the a11y vibe into a Definition-of-Done gate (keyboard, visible focus, 24×24px targets, no drag-only). → amend `rules/frontend.md`.

## Cheap one-line tightenings
"Won't-have this cycle" list + Assumptions line (MoSCoW/RAID) · Definition-of-Ready 4-item "ready to build?" assertion · per-repo `constitution.md` of hard constraints (Spec Kit/Kiro) · C4 Context+Container diagrams in `spec-view` (levels 1–2 only) · feature-flag lifecycle (owner/expiry/cleanup-PR) · success-metric→emitted-signal traceability · attacker-motivation prime in `threat-model` (PASTA atom) · API expand-contract/tolerant-reader in `api-surface-review` · cite 2024 DORA "AI→bigger batches→worse stability" in `pr-discipline`.

## Rejected (tempting but off-thesis)
- **BMAD persona-swarm / ECC 249-skill catalog** — the kitchen sink apex exists to reject.
- **SBOM generation / Sigstore signing / SLSA attestation tooling; DORA/SPACE measurement + dashboards + error-budget-burn gates** — build/CI/runtime infra apex doesn't own (keep only the *review questions*).
- **Full ASVS (350 reqs), PASTA's 7 stages, SAMM, NIST SSDF, SAFe/WSJF** — org-altitude governance or anti-lean ceremony.
- **Full PRFAQ ritual; full C4/arc42 templates** — incubation / always-stale-diagram ceremony (pre-mortem and C4-L1-2 deliver the atoms cheaper).
- **Tessl spec-registry, beads-as-orchestrator dependency, Kiro on-save auto-editing** — external products / autonomous mutation that violate apex's deliberate-freeze model.

## Meta-finding
apex is **vertically** excellent (each artifact author→review→freeze) but has two genuine holes: a **horizontal** consistency layer (#1) and a **post-release** learning loop (#3) — plus data-migration reversibility (#2) is thin where it's riskiest. The two new-skill holes are dogfooded here through apex's own gates.

## Key sources
Spec Kit https://github.com/github/spec-kit/blob/main/spec-driven.md · Parallel Change https://martinfowler.com/bliki/ParallelChange.html · gh-ost https://github.com/github/gh-ost · Google SRE postmortems https://sre.google/sre-book/postmortem-culture/ · Pre-mortem https://www.gary-klein.com/premortem · OWASP LLM Top 10 https://genai.owasp.org/resource/owasp-top-10-for-llm-applications-2025/ · slopsquatting https://www.bleepingcomputer.com/news/security/ai-hallucinated-code-dependencies-become-new-supply-chain-risk/ · Shape Up https://basecamp.com/shapeup · LINDDUN https://linddun.org/ · WCAG 2.2 https://www.w3.org/WAI/standards-guidelines/wcag/new-in-22/ · C4 https://c4model.com/ · DORA 2024 https://getdx.com/blog/2024-dora-report/
