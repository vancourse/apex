# `apex:impl-plan-review` — `autonomous-fix` impl plan

**Role:** synthesizer of 6 lenses (Pass 1–5 + whole-plan adversarial) + plan-freeze gate.
**Inputs:** frozen `design.md`, frozen `prd.md`, exemplar `docs/incident-retro/impl-plan.md`, method `skills/impl-plan-review/SKILL.md`.
**Verdict:** **FREEZE-READY** — all blockers from the six lenses resolved in the final plan; every disputed fact re-verified at HEAD this session. The two lenses that contradicted each other on load-bearing facts (FLOW.md structure; release path) were adjudicated against the bytes, not the reviews.

---

## Decisive fact re-verification (where reviews disagreed)

I re-read the live tree because Review 2 ("Pass 2 PASS") and Review 6 ("BLOCKER 1") contradicted each other on the FLOW.md anchor, and Review 4 raised a release-path blocker the plan never cited. Bytes settle it:

| Disputed fact | Verdict at HEAD | Who was right |
|---|---|---|
| Is `:302` (`apex:incident-retro`) in a "code-fenced side-path block"? | **No.** `:254` "## Side paths" is pure prose (DEBUG `:256`, ADVERSARIAL PAIR `:258`), **no fence**. The fence holding by-name footnotes is the **matrix footnote block `:264`–`:303`**; `:302` is *inside it*. | **Review 6 (B1) correct; Review 2 misread it.** |
| Does the feature PR bump versions + author `## [0.3.7]`? | **Must NOT.** `release.sh:58–62` HARD-REQUIRES `## [Unreleased]`; `:67` ABORTS on a pre-bumped version. No `[Unreleased]` exists at HEAD. | **Review 4 (B1) correct.** |
| Slash count? | **14** live (`help.md:10,58`; `README:221,232`). 0.3.6 CHANGELOG's "menu stays 13" is **stale** (adversarial-pair added a command after). | **Review 6 (B2) correct.** |
| Lint checks vs fixtures? | **7 checks, plan said "6 fixtures."** `check_default_deny_allowlist` (AC7a) had no negative fixture. | **Reviews 3 (B1) + 6 (Major 4) correct.** |
| S5.3 covered? | PRD tags `[gate-walk]` but single-flight is a GH `concurrency:` shape; the design's `check_cost_cap_present` asserts "concurrency present" — lint-checkable, but unmapped + unfixtured in the plan. | **Review 3 (B2) correct.** |
| `.github/` net-new? | **No** — `ISSUE_TEMPLATE/` + `pull_request_template.md` exist; only `workflows/` is new. | **Review 5 (NIT 3) correct.** |
| `CHANGELOG.md` a new file? | **No** — exists (≈30 KB); L5's edit is a shared-file edit. | **Review 5 (SHOULD-FIX 2) correct.** |

Also re-confirmed (plan was right): both version files `0.3.6`; no `skills/**/reference/`; no repo-root `CLAUDE.md`; `guard-security-paths.sh:19` superset-floor; `adversarial-pair` skill exists; new hooks `apex-primer`(SessionStart)/`suggest-review-on-stop`(Stop).

---

## PASS 1 — Layered PR stack (≤400 LOC, one concern, independently reviewable)

**Verdict: PASS (after fixes).** Cooperative + adversarial lenses both landed two real structural flags; both applied.

- **FLAG 1 (L3 not a separable layer) — FIXED.** The prior L3 ("Port these seams") lived *inside* L1's `SKILL.md` and §5 reverted it *with* L1 — a sub-PR masquerading as a layer. Design node 9 places it inside SKILL.md, so a separate file would deviate from frozen scope → **fold, not split.** Relabeled **L3 → L1b**: a sub-step of PR-1, an explicit *freeze milestone* (the four seams), NOT an independent revert unit. The "L1+L3 same revert unit" contradiction (also Review 6 Major 5) dissolves — §5 now states L1b has no independent revert and a wrong seam table is a **forward-fix, not a revert.**
- **FLAG 2 (L1 budget understated) — FIXED.** Prior ~280 LOC was optimistic vs the densest existing SKILL.md (`ai-pre-review-checklist` ~355) which carries *fewer* elements. Plan now states the honest combined budget: **~340 body + ~30 L1b = ~370 LOC**, explicitly "brushing, not far below" 400, with a named relief valve (move the operating-prompt block to `reference/` if it overshoots, flagged as design-touching).
- **Layer→PR mapping now explicit** (Review 6 Minor 6): 4 PRs (PR-1=L1+L1b, PR-2=L2, PR-3=L5, PR-4=L4) + L1b milestone.
- **What's right (steelmanned):** L2 co-authoring template+lint+fixtures is the correct tested-unit pair, not a concern-mix (the model layer). L5 bundling 5 doc edits is correct registration granularity. L4 is a clean disjoint-path single-concern layer.

## PASS 2 — Sequencing / dependency order

**Verdict: PASS (after fixes).** DAG is acyclic; no layer depends on a later one; wiring is last.

- **L1→L2 hard edge confirmed** (template cites L1's AC#s; PRD §7). **L2→L1b(content)** correctly orders the seam prose after the bet proves embeddability (no contract↔YAML drift). **L1+L1b→L5** keeps the footnote/README pointing at a seam-complete skill.
- **L4-position flag — FIXED.** L4 is the only sign-off-contingent layer and unblocks nothing in-stack; building it before L5 would force a CHANGELOG re-edit on demote. **L4 is now built LAST (PR-4), after L5**, so the CHANGELOG is authored once with the sign-off outcome known. Still dependency-correct (depends only on L2).
- **Cosmetic L1→L5 DAG mis-draw — FIXED.** The ASCII graph no longer shows an L1→L5 bypass; L5 depends on L1 *and* L1b, stated in the diagram-honesty note.
- **Drift honored:** the FLOW.md edit references `apex:adversarial-pair` (not `superpowers:dispatching-parallel-agents`); no HOOKS-box entry added (autonomous-fix is by-name/CI-wired, not a hook), slotting cleanly alongside `apex-primer`/`suggest-review-on-stop`.

## PASS 3 — Test plan per layer (PRD↔test mirror 1:1)

**Verdict: PASS (after fixes).** Two blockers from the adversarial Pass-3 lens were real and are closed; the mirror is now complete both directions.

- **B1 (AC7a no negative fixture) — FIXED.** 7 checks now get one fixture each; the 7th fixture (`allowed_tools` collapsed/`*` → RED on `check_default_deny_allowlist`) maps to S3.1's AC7a leg. Exit gate changed "6"→ **8** (the 8th because `check_cost_cap_present` has two failable legs).
- **B2 (S5.3 unwalkable + unfixtured) — FIXED.** S5.3's single-flight is a GH `concurrency:` *shape*, not a gate decision. Re-classified its mechanizable leg to `[template-lint]` with its own fixture (missing/`cancel-in-progress:true` → RED on the concurrency leg of `check_cost_cap_present`); the L1 gate-walk row no longer claims S5.3 (claims only S5.1/S5.4). Tag lineage now honest.
- **B3/precision (S2.2 owner) — FIXED.** S2.2's no-safe-slice invariant is a runtime behavior (design C5) gate-walk cannot verify; it is now owned by `[author-validate]` with the named no-shipped-oracle residual (PRD:44), not implied as gate-walk-verified.
- **S6/S7 two-row commitment added** (Review 3 B5): the gate-walk table commits to a *second* re-evaluation row for S6 (post-root-cause re-route) and S7 (hard/best-effort per next-op), sourced from design Pass-1.
- **S1.3 labeled "additional shape backstop,"** not owner (PRD `[gate-walk]` owner preserved — Review 3 B4).
- **Lint is concrete-enough-to-run:** stdlib + PyYAML sufficient; each check names a decidable assertion traceable to design.md:267–275.

## PASS 4 — Rollout (release/reinstall path; draft-default / no-auto-merge)

**Verdict: PASS (after the release-path blocker fix).**

- **B1 (in-PR version bump collides with `release.sh`) — FIXED.** L5 split into **L5a** (freely-revertible doc rows) + **L5b** (release-coupled). The CHANGELOG now lands under **`## [Unreleased]`** (created if absent), version bump **deferred to `./scripts/release.sh 0.3.7`** (which `jq`-bumps both files, dates `[Unreleased]`, commits/tags/releases), and the concrete reinstall path is cited as `CONTRIBUTING.md:130–141`, not a bare "reinstall." The `release.sh:67` pre-bump-abort hazard is named.
- **B2 (L4 self-enforcement only on PR) — FIXED.** L4 now triggers on **`push` AND `pull_request`**, because `release.sh:88–92` pushes the `release:` commit directly to main (no PR) — the push trigger is what makes "fires on apex itself" true for the release commit.
- **Draft-default / no-auto-merge: CLEAN, unchanged.** AC6 carried end-to-end (design Deferral #8 "forbidden permanently," `check_no_merge`, `open-draft-pr`). The plan's own PR posture opens nothing without sign-off.
- **Flag/cohort/canary: correctly N/A** for a zero-runtime markdown gate (stated, not skipped).

## PASS 5 — Reversibility / rollback

**Verdict: PASS (after fixes).** No reversibility blocker; the additivity claim holds.

- **SHOULD-FIX 1 (L5 reversibility-class mix) — FIXED.** L5a doc rows revert freely; L5b is release-coupled. The **one conditional-rollback step in the whole plan** is now named: the **release tag `v0.3.7` + `--latest` GitHub release** (`release.sh:94–116`) is durable, roll-forward-only (→ 0.3.8, never un-publish). §5 no longer frames everything as `git revert`-clean.
- **SHOULD-FIX 2 (CHANGELOG fact + shared-file) — FIXED.** Facts block records CHANGELOG.md exists; §5 marks the CHANGELOG/doc-row edits as shared-file (rebase-on-revert), distinct from L2/L4 clean-delete adds.
- **NIT (lint-is-wrong rollback) — FIXED.** §5 L4 now distinguishes too-strict (revert L4 to unblock apex CI) vs too-loose (forward-fix by tightening — no revert).
- **NIT (`.github/` not virgin) — FIXED.** Plan states only `workflows/` is new under the existing `.github/`.

## ADVERSARIAL COUNTER-PASS (whole-plan: dropped frozen mechanisms? citations re-verified?)

**Verdict: PASS.** No frozen-design mechanism was dropped — independently re-audited:
- Two-invocation seam (B1) → survives into L1 + L2 (two distinct `allowed_tools` arrays + between-invocation `# SEAM:` comments) + `check_default_deny_allowlist`. ✔
- Fail-closed cost (B3) → `check_cost_cap_present` forbids `continue-on-error`/`:-0`; template `COST_CAP`. ✔
- Escalation hard leg (B9) → `# SEAM:` comment + L1b seam contract + terminal states (a comment, not a lint check — correct per Deferral #9). ✔
- Sensitive superset (B7) → FULL `SENSITIVE_GLOBS`; `guard-security-paths.sh:19` byte-confirmed as the floor. ✔
- AC9 parity, AC8 comment-sink, AC1 Stage-A/B, AC3 red-on-main, AC7b staged unlock → all survive (lint or `# SEAM:`, correctly). ✔

The two adversarial blockers (phantom side-path block; 13-vs-14 count) and two majors (AC7a fixture; L1/L1b same-file revert) are all closed. Minors 6/7 (layer→PR map; author-validate one-shot qualifier) applied.

---

## Plan-freeze readiness

**freeze_ready = TRUE.** Every blocker and should-fix across the six lenses is applied to the final plan; every disputed fact was re-verified at HEAD and adjudicated against the bytes. The plan now:
- has an honest layer count (4 PRs + L1b milestone) and honest LOC budgets (~370 combined SKILL.md);
- has a complete, both-directions PRD↔test mirror (8 fixtures, one per failable lint check-leg; S5.3/S2.2 ownership corrected);
- uses the repo's actual scripted release path (`## [Unreleased]` + `scripts/release.sh`, no in-PR bump);
- names the single roll-forward-only artifact (the release tag/GH release);
- corrects the FLOW.md two-destination wiring fact the prior draft got wrong.

**On freeze:** `superpowers:executing-plans` begins at **L1** (`skills/autonomous-fix/SKILL.md`). The freeze of L1b's four seams (U1/U2/U5/U9) is the contract the downstream BookBridge two-children refactor waits on. Two items remain for **user sign-off** (not blocking, by design — they are open *decisions*, not unresolved defects): the `0.3.7`-vs-`0.4.0` version call (§7.1) and the L4 ship-vs-defer call (§7.2, with the demote branch fully specified).
