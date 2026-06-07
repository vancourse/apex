# Impl plan — `autonomous-fix`

**Status:** ❄️ FROZEN 2026-06-06 (user-approved; `impl-plan-review` PASS — all lens blockers closed, anchors re-verified at HEAD) · **Slug:** `autonomous-fix`
**Freeze:** Build per the layered stack (PR-1 L1+L1b → PR-2 L2 → PR-3 L5 → PR-4 L4). Version bump is `release.sh`'s job (feature work adds `## [Unreleased]` only).
**Design:** `design.md` (FROZEN 2026-06-06). **PRD:** `prd.md` (FROZEN 2026-06-06). Built in `skills/autonomous-fix/`.
**Format/depth exemplar:** `docs/incident-retro/impl-plan.md`. **Review method:** `skills/impl-plan-review/SKILL.md` (5 passes + adversarial counter-pass + freeze gate).

This is a **markdown discipline-gate** skill (zero apex runtime) that ships **3 artifacts + 4 doc edits** (design Shape ¶). The plan is a **PR-sized stack in PRD §7 build order**, with the **central de-risking bet (template ↔ lint co-consistency, two-invocation seam expressibility) front-loaded into L2** — the earliest layer that can carry it without violating the §7 "SKILL first, template cites it by AC#" dependency. Each layer is ≤400 LOC, names its test artifact and the PRD scenario(s) it serves, and states rollout + reversibility.

**Layer → PR mapping (stated, per impl-plan-review Pass 1 "≥2 PRs, one architectural layer per PR").** The stack is **4 build layers across 4 PRs**, plus **L1b** which is a *sub-step of L1's PR* (it appends to the same file — see L1b) and a **freeze milestone**, not a separable PR. So: **PR-1 = L1 (incl. L1b appended)**, **PR-2 = L2**, **PR-3 = L5**, **PR-4 = L4** (built last; see §2). L1b is called out as its own *milestone* (the four seams freeze, unblocking the BookBridge §6 refactor) but it is **not** an independent revert unit — it shares `SKILL.md` with L1 (Pass-1 flag, resolved by this relabel; see L1b + §5).

**What "tests" means for a markdown gate (PRD §3 verification layer).** There is no shipped runtime, so the test surface is exactly two things, mirrored to PRD scenarios 1:1:
- **`conformance-lint.py`** (executable; the *only* mechanical-in-CI surface) — tests the **template-shape ACs** (AC2/AC4/AC5/AC6/AC7a/AC9) via green-on-the-template + deliberately-broken negative fixtures, **one negative fixture per failable lint check-leg** (7 checks, one of which — `check_cost_cap_present` — has two independently-failable legs → 8 fixtures; see §3). Tag: `[template-lint]`.
- **`SKILL.md`'s gate-walk worked-example table** — tests the **runtime ACs** (AC1/AC3/AC7b/AC8) as decision-text oracles driven over a fixture issue + fixture diff. Tag: `[gate-walk]`.
- **`[author-validate]`** — the one-shot authoring-time sandbox run of the template against a crafted injection issue, performed at L2 author time (S2/S3). **One-shot, NOT a shipped/maintained harness** (§4 disowns it).
- **`[doc-assert]`** — a doc cross-reference exists unambiguously (S4 edge, S8).

**Live-tree facts re-verified this session at HEAD (post adversarial-pair + new-hooks drift):**
- Plugin version is **`0.3.6`** in BOTH `.claude-plugin/plugin.json:3` and `.claude-plugin/marketplace.json` → this effort releases as **`0.3.7`** (a point release, matching the 0.3.6 precedent that shipped *two whole skills* — `observability-review` + `data-migration-review` — as a patch, additive-only). **The version bump is NOT done in the feature PR — it is performed by `scripts/release.sh 0.3.7` at release time** (see §4 / L5b).
- **`CHANGELOG.md` EXISTS** (≈30 KB, last modified in this session-window) and currently has **no `## [Unreleased]` section** (head is `## [0.3.6] — 2026-06-06`). The L5 CHANGELOG contribution lands under a freshly-created **`## [Unreleased]`** section — NOT a pre-dated `## [0.3.7]` — because `scripts/release.sh:58–62` HARD-REQUIRES `## [Unreleased]` and `:83` dates+renames it at release. This is a **shared-file edit** (revert may need rebase if the file moved underneath), distinct from L2/L4's clean-delete file adds.
- **No `skills/**/reference/` directory exists today** — `reference/` is a genuinely-new apex convention, established by L2.
- **`.github/` EXISTS** (holds `ISSUE_TEMPLATE/` + `pull_request_template.md`); **only `.github/workflows/` is new.** L4 adds `workflows/` under the existing `.github/` — apex's *first CI workflow file*, not a virgin directory (flagged for sign-off).
- **No repo-root `CLAUDE.md`** — design Pass-4 doc-edit #4 targets the user's private `~/.claude/CLAUDE.md`, OUT of this repo; it is a manual user-edit suggestion in the PR description, not part of this effort's diff (honors "apex doesn't self-mutate").
- **Slash-menu count is `14`** at HEAD (verified: `commands/help.md:10,58` say "14 entry-point commands" / "~14 things you drive by hand"; `README.md:221,232` say "14-command" / "14 entry-point commands"; 14 `/apex:` lines in `commands/help.md`). **The 0.3.6 CHANGELOG's "the menu stays 13" prose is STALE** (the menu grew 13→14 when `adversarial-pair` got a slash command after 0.3.6's CHANGELOG text was written). autonomous-fix adds **no** slash command, so the live count stays **14** — the `[0.3.7]` CHANGELOG entry must say "**menu stays 14**", NOT copy the precedent's "13".
- **FLOW.md structure (re-verified — corrects a fact the prior draft got WRONG):** the prose **"## Side paths (not phase-sequential)"** section is at `:254`, containing DEBUG (`:256`) and ADVERSARIAL PAIR (`:258`) as **pure prose, NO code fence**. The **code fence holding the by-name skill footnotes runs from `:264` to its close at `:303`** (the Skill×Phase matrix footnote block); `apex:incident-retro` sits at `:302` **inside that matrix footnote fence**, directly below `apex:cross-artifact-consistency` (`:301`). **There is no "code-fenced side-path block."** The single-line footnote and the prose paragraph go to **two distinct destinations** (see L5 item 1).
- `hooks/guard-security-paths.sh:19` glob list confirmed byte-for-byte (the `SENSITIVE_GLOBS` *documented-superset* claim, design B7, holds): `*/auth/*|*/credentials/*|*/oauth/*|*/oidc/*|*/sso/*|*/secrets/*|*/security/*|*/encryption/*|*/signing/*|*/jwt/*|*/saml/*|*/permissions/*|*/authorization/*`. The hook "Always exits 0" (`:9`) — advisory only.
- `skills/adversarial-pair/SKILL.md` exists; FLOW.md `:258` + `:297–298` already reference **`apex:adversarial-pair`** (not `superpowers:dispatching-parallel-agents`). New hooks confirmed: `apex-primer` (SessionStart, `hooks.json:3,9`), `suggest-review-on-stop` (Stop, `:67,72`). autonomous-fix adds **no** hook (by-name + project-CI-wired), so it slots in alongside them without touching the HOOKS box.

---

## §1 Layered stack (4 PRs + L1b milestone, PRD §7 build order, bet front-loaded into L2)

> **Dependency rationale (Pass 2 preview).** PRD §7 mandates SKILL-first / template-cites-discipline-by-AC#. The template's step names and `# SEAM:` comments cite AC numbers *defined in SKILL.md*, so SKILL.md genuinely must precede the template — not reorderable. The risk-first angle (prove "lint-green-on-template" + "two-invocation seam expressible" before sinking prose) is honored by **co-authoring the template + lint as one bet in L2** with an explicit circuit-breaker back to `design.md`, rather than splitting them across layers. SKILL.md (L1) is the cheap-to-revise definitional layer; if L2's bet fails, L1 is re-opened alongside design.

### L1 — `skills/autonomous-fix/SKILL.md` (the discipline gate) · ~340 LOC body + ~30 LOC L1b = **~370 LOC total in one file** (PR-1)

The one-bug→one-fix→one-draft-PR discipline. Structure per design "SKILL.md structure":
- **frontmatter** `name: autonomous-fix` + `description` carrying the keyword set (unattended, autonomous, bug-fix gate, prompt injection, fenced input, nonce, fail-closed cost cap, reproduce-first, sensitive-path, draft-only, two-invocation runner, parent of a bug-bot).
- **"What this is"** — the rails a runner must satisfy, NOT a runner; apex owns zero runtime.
- **"Distinct from"** — `ai-pre-review-checklist` (human-driven sibling; the confirm step carries its judgement steps) · `security-review`+`threat-model` (REQUIRES the hard-stop/fence/leak *content*; deltas N1/N2/AC8-comment-sink) · `systematic-debugging` (REQUIRES from / invokes — not "composes from") · `pr-discipline` §1+§6 · `incident-retro` (post-escape, AC10) · the two BookBridge children.
- **"The two-invocation runner seam" (B1)** + the test-file-only carve-out (B2): invocation #1 read+test-write → wrapper (`assert-red-test` + `sensitive-route-prewrite`) → invocation #2 write; gate owns the commit. State the portability precondition (a runner that can't accept two allowlists or be paused between phases is not wrappable).
- **"Two modes, one rail set"** — the AC9 parity statement: the ONE legal mode-conditional step is the human-confirm step; any other mode-conditional key is a parity failure.
- **The five-phase rail pipeline P1…P5** — each = its one hard rule + AC + composed gate + STRIDE threat (design Pass 2 MVP cut).
- **The four honest terminal states** — DRAFT-PR / ESCALATE / NOT-REPRO / HALT.
- **The gate-walk worked-situation table** — S1–S11 (the L1 TEST ARTIFACT; see §3). **This table is the single largest element (~50–60 LOC of the L1 budget): each row carries an intake decision AND, for S6/S7, a *second* re-evaluation row (S6 post-root-cause re-route to S2; S7 hard-vs-best-effort per next-op) — sourced from design.md Pass-1 table rows S6/S7 which walk both. See §3 for the per-row commitment.**
- **"Port these seams" (= L1b, see below)** — the four Pass-0 contracts, the freeze-gating sub-section.
- **Operating-prompt template** — the gate-naming block (AC4) + single-block nonce fence incl. title (AC2/U5) + the staged-write directive (AC7b). *Relief valve, flagged: if L1 body overshoots 400 LOC at author time, move this operating-prompt block into `reference/` next to the YAML (it is template content); that is a design-touching call — flag it at freeze, do not improvise mid-build.*
- **Hand-off** — `incident-retro` on recurrence (AC10); the reference template; the BookBridge children.
- **"AC → named mechanism"** map (design's, verbatim-faithful).

**LOC honesty (Pass-1 flag, addressed).** The densest shipped SKILL.md today is `ai-pre-review-checklist` at ~355 LOC, carrying *fewer* structural elements than L1 must (no S1–S11 table, no embedded operating-prompt template, no AC→mechanism map). The honest L1 *body* estimate is therefore **~340 LOC**, and with **L1b appended (~30 LOC) the combined `SKILL.md` lands at ~370 LOC** — under the 400 ceiling but **brushing it, not comfortably below.** A freeze reviewer should expect L1 at ~370, not ~280. L1 is **one coherent concern** (the discipline gate) and must NOT be split across PRs (a skill reads as one document); if it genuinely overshoots 400, use the operating-prompt relief valve above.

**Depends on:** nothing in-stack. **Unblocks:** L2 (the template cites L1's AC numbers), L1b (the seams pointer + section live in this file).

### L1b — "Port these seams" section (the four-seam freeze contract) · ~30 LOC, **appended to L1's `SKILL.md` in the SAME PR-1**

The U1/U2/U5/U9 contract table from design Pass 0 — for each seam: apex default (fail-closed) · project supplies · apex invariant. Plus the B7 superset/floor relationship, the B3 fail-closed `cost_so_far`, the B9 hard-leg escalation, and the T4 named egress residual. This is the **freeze-gating milestone**: the four seam interfaces freezing here is what unblocks the downstream BookBridge refactor (§6).

**Why a sub-step, not a separate layer/PR (Pass-1 fold, applied).** Per `design.md` "SKILL.md structure" node 9, "Port these seams" lives *inside* `SKILL.md` — a separate file would deviate from the frozen design. So L1b is **physically a section of L1's file and ships in PR-1**, with L1 reserving its `## Port these seams` heading + a one-line pointer that L1b fills in. It is **NOT an independent revert unit** (you cannot `git revert` L1b without reverting L1's file, or hand-editing — see §5). It earns its own *milestone* accounting (the contract downstream waits on) and its own *review attention* — but it is **not** a separable PR. (This resolves the prior plan's "L3 is a milestone masquerading as a layer" + "same-file revert contradiction" flags.)

**Write-ordering within PR-1 (resolves the same-file forward-reference hazard).** L1 authors the `## Port these seams` heading with a stub pointer; L1b fills the table into that same heading. Because L1b's prose must describe seams *proven embeddable in the template*, **L1b's content is finalized after L2's bet goes green** (the seam contract and the YAML that ships it must not drift). Mechanically: PR-1 opens with the stub heading, and the table is completed in a PR-1 revision once L2 is green — OR PR-1 lands the full L1+L1b after L2 (author's choice; both keep contract↔YAML in sync). The §2 graph reflects the *content* dependency `L2 → L1b`, even though L1b is *physically* in PR-1's file.

**Depends on:** L1 (its host file/heading) + L2 (the seams are validated as embeddable). **Unblocks:** the downstream BookBridge two-children refactor (§6).

### L2 — `skills/autonomous-fix/reference/` (the template + the lint, co-authored as THE BET) · ~240 LOC (PR-2)

Two files authored together; the layer's exit gate is **the lint runs GREEN over the template** AND **8 deliberately-broken fixtures each go RED on exactly their target check-leg** (one fixture per failable check-leg — see §3). This proves the two high-risk design claims in one shot before any further layer is sunk:
1. **template ↔ lint co-consistency** — the six shape ACs are simultaneously expressible as YAML *and* statically decidable on one file (design B4/B5/B6);
2. **the two-invocation seam is expressible** as two distinct concrete `allowed_tools` arrays + the between-invocation `# SEAM:` comments (design B1).

- **`reference/autonomous-fix.yml`** (~90 LOC) — the ONE commented GH-Action template, exactly the design's "Reference template + lint structure" block: 6 shape-AC steps as executing steps (`assert-branch-protection`, `budget-precheck`, `mint-nonce`, `build-fenced-prompt`, `run-fixer-readonly`, `run-fixer-write`, `open-draft-pr`, `confirm-step`) + the `# SEAM:` comments for the runtime ACs (AC3 assert-red-test, AC1 Stage-A prewrite, AC1 Stage-B postwrite/C5, AC8 leak-scan, S7 in-flight, U5/B9 escalate-hard-leg). Ships the **FULL** `SENSITIVE_GLOBS` superset of the hook (B7 — includes `oauth/oidc/sso/jwt/saml` + `migrations/rls/crypto/*secret*/*credential*/*.pem/*.key/.env*/.github`), `permissions:` default-deny (U9), the GH-native **`concurrency:` block keyed on `github.event.issue.number` with `cancel-in-progress: false`** (AC5 ∩ AC6 / S5.3, design.md:217–219), fail-closed `COST_CAP` (no `continue-on-error`, no `:-0`), and exactly one mode-conditional step. Header comment: "NOT a product; a commented illustration." Each step name cites its AC# (the no-drift loop back to L1).
- **`reference/conformance-lint.py`** (~150 LOC, stdlib + PyYAML) — the **7** checks of the design's lint table: `check_title_in_fence` (AC2), `check_nonce_delimiter` (AC2/N2/S3.4), `check_gate_names` (AC4), `check_cost_cap_present` (AC5/B3 — asserts a `budget-precheck` step exists, **turn + timeout + concurrency present**, and forbids `continue-on-error`/`:-0`), `check_no_merge` (AC6, author-hygiene only), `check_default_deny_allowlist` (AC7a — two concrete arrays, distinct, neither `*`), `check_mode_parity` (AC9 — exactly one mode-conditional step, no budget/allowlist/fence/sensitive key under any conditional). Exit non-zero on any failure. *`check_cost_cap_present`'s "concurrency present" sub-clause is the static surface that makes S5.3's mechanizable leg lint-checkable — see §3 / S5.3.*
- **8 negative fixtures** (tiny broken-template variants) — the executable test oracles, **one per failable check-leg** (see §3 fixture map). The allowlist fixture (collapsed/`*` → RED on `check_default_deny_allowlist`) closes the **AC7a no-negative-fixture gap** (Pass-3/adversarial blocker). The concurrency fixture (missing/`cancel-in-progress: true` → RED on `check_cost_cap_present` concurrency leg) closes the **S5.3 unfixtured-shape gap**.
- **`[author-validate]`** (S2/S3): a **one-shot** run of the template in a throwaway sandbox repo against a crafted injection issue (title-only injection, marker-injection, "paste a secret"), performed at author time to prove the fences hold. Documented as one-shot; **nothing shipped, scheduled, or maintained** (§4).

**CIRCUIT BREAKER (design Pass 2 strike-test made operational).** If lint-green-on-the-template cannot be reached, or the two-invocation seam cannot be expressed as two distinct allowlist arrays + between-invocation comments, **STOP and return to `design.md`** — do not paper over by weakening a check. This is the `impl-plan-review` cancel-by-default circuit breaker applied at the bet layer.

**Depends on:** L1 (cites its AC numbers). **Unblocks:** L4 (the CI step runs this lint), L1b content (the template *embeds* the four seams the L1b prose documents).

### L5 — Wiring (FLOW.md / help.md / README / CHANGELOG / version) — split into L5a + L5b for reversibility · ~45 LOC (PR-3)

`autonomous-fix` is wired as a **DEBUG/fix SIDE-PATH**, NOT a Skill×Phase matrix grid row (it is not a step in the linear new-feature pipeline). All anchors re-located by content at edit time, not by stored line number.

**L5a — freely-revertible doc rows (FLOW.md / help.md / README):**

1. **FLOW.md — TWO distinct destinations (corrects the prior "code-fenced side-path block" fiction):**
   - **(a) Prose paragraph** — a new `**AUTONOMOUS BUG-FIX.**` paragraph in the prose **"## Side paths (not phase-sequential)"** section (header `:254`, alongside DEBUG `:256` and ADVERSARIAL PAIR `:258`). This section is **pure prose with no code fence** — the paragraph is plain markdown, not a fenced line. Multi-sentence characterization: uses **"requires from"** not "composes from"; names the human-confirm-removed delta; hands recurrence to `incident-retro` AC10. (Text per design Pass-4 #1.)
   - **(b) Single-line footnote** — appended directly after the `apex:incident-retro` footnote line at `:302`, which sits **inside the Skill×Phase matrix footnote code fence (`:264`–`:303`)**, as a sibling to the `apex:incident-retro` (`:302`) and `apex:cross-artifact-consistency` (`:301`) lines (single-line-per-entry, matching that fence's geometry): `apex:autonomous-fix    — side path; the rails an unattended/supervised agent must satisfy before a bug-fix PR (wraps any runner; draft-only). Unattended counterpart to ai-pre-review-checklist.`
   - **No Skill×Phase matrix *grid* row, no HOOKS-box entry** (autonomous-fix is a side-path, by-name + project-CI-wired, not phase-sequential and not an apex hook).
2. **commands/help.md** — a **sibling Post-release line** under the existing "I FIRE THESE AUTOMATICALLY based on phase + file paths" header (`:26`), beside the `incident-retro` Post-release entry (`:37–38`), with a *freshly-authored* caveat (autonomous-fix differs from incident-retro by being *also* wireable into a project's CI): `autonomous-fix (run by name, or wire its reference template into your project's CI — not fired by an apex hook — the rails a label/webhook/cron-triggered agent must satisfy: fenced input · fail-closed cost cap · reproduce-first · sensitive-path refuse · draft-only).` **No new slash command** (the live menu stays **14** — see facts block; the 0.3.6 "13" precedent is stale) — so the help.md "14 entry-point commands" count (`:10,58`) and the README slash-count (`:221,232`) are **untouched**.
3. **README skill-table row** after the `incident-retro` row (`:52`): the design Pass-4 #3 row text (unattended/supervised bug-fix gate; five rail phases; ONE template + lint + seams list; composes the named gates; ships the rails NOT a runner).

**L5b — release-coupled, NOT freely revertible (CHANGELOG entry only; NO in-PR version bump):**

4. **CHANGELOG** — add an entry under a **`## [Unreleased]`** section (creating that section if absent — it is absent at HEAD), with a `### Added` subsection describing the skill + the three artifacts + the side-path wiring + (if L4 ships) the new apex-CI lint step, OR a note that L4 was deferred if sign-off cuts it. The entry must say "**menu stays 14**" (NOT 13). `scripts/release.sh:83` dates+renames `## [Unreleased] → ## [0.3.7] — <date>` at release — **do not pre-date it.** `CHANGELOG.md` is a **shared, frequently-touched file** (modified this session-window): its revert is a rebase-prone shared-file edit, not a clean delete.
5. **Version bump — NOT in this PR.** The bump of `plugin.json` + `marketplace.json` to `0.3.7` is performed by **`./scripts/release.sh 0.3.7`** as a **post-merge release step**. `release.sh:67` HARD-ABORTS if the version was already bumped, so pre-bumping in the feature PR would break the release tooling. The concrete "make it live" path after release is `CONTRIBUTING.md:130–141` (pull marketplace clone → `rsync` cache → bump `gitCommitSha` in `installed_plugins.json` → restart), not a bare "reinstall" (per the apex-installed-vs-dev-repo-skew memory).

**Out of this diff (stated, not skipped):** design Pass-4 doc-edit #4 (the user's global `~/.claude/CLAUDE.md` skill-gate row) — not a repo file; emitted as a manual user-edit suggestion in the PR description.

**Depends on:** L1 + L1b (the row/footnote point at a real, seam-complete skill). **Unblocks:** nothing in-stack.

### L4 — `.github/workflows/conformance-lint.yml` (apex's first CI workflow) · ~30 LOC — **built LAST, after L5** (PR-4)

A single GH-Actions workflow that runs `reference/conformance-lint.py` over apex's own shipped `reference/autonomous-fix.yml` **on `push` AND `pull_request`**. Triggering on `push` (not only `pull_request`) is deliberate: `scripts/release.sh:88–92` commits the `release:` bump **directly to `main` and pushes** (no PR), so a PR-only workflow would never lint the release commit — the `push` trigger is what makes "the lint actually fires on apex itself" true for *both* PR traffic and the release commit. **Self-test:** the workflow goes green on apex's own template and the 8 fixtures stay red. **Disjoint path from every other layer** (touches only `.github/workflows/`, no skill file).

**Built last (Pass-2 sequencing flag, applied).** L4 is the **only** sign-off-contingent layer (§7 item 2) and it **unblocks nothing in-stack**. Building it before the terminal wiring would force a CHANGELOG re-edit in L5 if the demote decision lands "cut L4." So L4 is built **after L5**, once its §7 sign-off is resolved, and L5's CHANGELOG is authored once with the L4 outcome known. (It remains *dependency-correct anywhere after L2* — no layer depends on it — but building-last is the clean ordering.)

**Flagged for impl-plan-review sign-off:** this is apex's first CI file and a genuinely-new surface under the existing `.github/`. **If the user prefers apex remain CI-less, L4 demotes to a follow-on** and the lint stays author-validated only — **L1/L1b + L2 + L5 ship unchanged.** Demote-branch effect on §3 (stated so two implementers don't diverge): the §3 **L4 row collapses into L2's row**; `[template-lint]` coverage is **unchanged** because L2's exit gate (lint-green + 8 fixtures) already owns every `[template-lint]` scenario — L4 only changes **where** the lint fires (CI vs author-time), not **what** is covered.

**Depends on:** L2 (the lint + template it runs). **Unblocks:** nothing in-stack.

---

## §2 Sequencing / dependency order

```
L1 SKILL.md ──► L2 template+lint (THE BET) ──┬──► L1b "port these seams" (CONTENT; physically in PR-1's file)
   (PR-1)            (PR-2)                   │
                                             └──► L5 wiring (PR-3) ──► L4 CI workflow (PR-4, built LAST)
                                                  [needs L1+L1b]        [needs L2; sign-off-gated]
```

- **L1 → L2:** the template's step names + `# SEAM:` comments cite AC numbers defined in L1 (PRD §7 "template cites the discipline by AC number").
- **L2 → L1b (content):** L1b's prose documents seams *after* L2 proves them embeddable in the template (no contract↔YAML drift). L1b is *physically* in PR-1's file (a sub-step), but its *content* is finalized post-L2 (see L1b write-ordering).
- **L2 → L4:** L4's CI runs L2's lint over L2's template.
- **L1+L1b → L5:** L5's footnote/README rows must point at a real, seam-complete skill (the `## Port these seams` section must exist before the README summarizes it).
- **L5 → L4 (build order only):** L4 is *built last*, after L5, so the CHANGELOG is authored once with the L4 sign-off outcome known. This is a build-ordering choice, not a dependency edge — L4 depends only on L2 and unblocks nothing, so the DAG stays acyclic.
- **No remaining parallelism:** with L1b folded into PR-1 and L4 built last, the path is effectively serial (L1 → L2 → L5 → L4). The prior plan's "L3 ∥ L4" optimization is gone — L1b is now in L1's file (serial-within-file) and L4 is deliberately terminal. (Diagram-edge honesty: there is **no** L1→L5 bypass edge; L5 depends on L1 *and* L1b — the prior ASCII DAG's direct L1→L5 split was a mis-draw, corrected here.)

**Preconditions per layer:** L1 needs the frozen design only. L2 needs L1 merged (AC numbers stable). L1b's content needs L2's bet green (seams proven embeddable). L5 needs L1+L1b. L4 needs L2's lint + its own §7 sign-off.

---

## §3 Test plan per layer (PRD ↔ test mirror, 1:1)

Each layer names its test artifact and the PRD scenario(s)/use-case(s) it serves. The two test surfaces (gate-walk table + conformance-lint) jointly cover **every** PRD scenario; the mirror is complete both directions (verified at end).

| Layer | Test artifact | Tag | Serves (PRD scenario/use-case) |
|---|---|---|---|
| **L1** SKILL.md | the **gate-walk worked-situation table** (S1–S11 decision rows) — runtime-AC oracle. **S6/S7 each get TWO rows** (S6: intake + post-root-cause re-route to S2; S7: in-flight check + per-next-op hard/best-effort split) — sourced from design.md Pass-1 S6/S7. | `[gate-walk]` | **S1** (S1.1–S1.4 happy-path), **S2.1** (sensitive detect) + **S2.3** (escalation artifact); **S2.2 routing-decision text only** (its no-safe-slice invariant is author-validate-owned — see note), **S3.1** (body injection effect-check), **S3.3** (paste-secret AC8), **S4** (no-repro BLOCK / WAD→NOT-REPRO+hard-leg), **S5.1/S5.4** (turn/timeout halts), **S6** (high-risk routing + post-root-cause re-route, 2 rows), **S7** (in-flight precondition + hard/best-effort split, 2 rows), **S9** (low-risk NOT over-escalated), **S10** (write-before-repro DENIED) |
| **L2** template + lint | **lint green on the template** + **8 negative fixtures** (each RED on exactly one check-leg); **`[author-validate]` — one-shot, not maintained** sandbox run for the injection scenarios | `[template-lint]` (+`[author-validate]` one-shot) | **S1.5** (`check_gate_names`) · **S3.2** (`check_title_in_fence`) · **S3.4** (`check_nonce_delimiter`) · **S5.2-shape** (`check_cost_cap_present` fail-closed leg) · **S5.3-shape** (`check_cost_cap_present` concurrency leg) · **S11** (`check_mode_parity`) · **S3.1-shape/AC7a** (`check_default_deny_allowlist`) · **S1.3-shape** (`check_no_merge`, AC6 backstop) · **S2/S3.1/S3.3 author-validate** (fences hold against a crafted issue at author time) |
| **L1b** port-these-seams | the seam-contract table renders the U1/U2/U5/U9 default·supplies·invariant rows unambiguously | `[doc-assert]` | (contract layer — the downstream-consumer interface; its correctness is exercised by L1's gate-walk rows S2/S5/S6 that walk the seams) |
| **L4** CI workflow | the workflow runs the lint and goes green on apex's own template (and the 8 fixtures stay red as a self-test), on both `push` and `pull_request` | `[template-lint]` (CI-fired) | same `[template-lint]` set as L2, now enforced as a required check on apex itself **on PR traffic AND the `release:` push commit**. *(On L4 demote: this row collapses into L2's; `[template-lint]` coverage unchanged — lint fires at author-time + L2 exit gate instead.)* |
| **L5** wiring | grep-assert: each doc row/footnote names `autonomous-fix` and (FLOW prose) the `incident-retro` hand-off; CHANGELOG `## [Unreleased]` entry exists and says "menu stays 14"; **version files NOT touched in-PR** (bump is `release.sh`'s job) | `[doc-assert]` | **S8** (AC10 escape→`incident-retro` hand-off cross-reference exists in FLOW prose + SKILL hand-off) |

**Negative-fixture → check-leg → scenario oracle map (L2, the executable layer — 8 fixtures, one per failable leg):**
1. fixture: gate name removed from prompt → RED on `check_gate_names` → **S1.5**.
2. fixture: `issue.title` interpolated outside the nonce markers → RED on `check_title_in_fence` → **S3.2**.
3. fixture: close marker ≠ open marker (or marker lacks `${...}`) → RED on `check_nonce_delimiter` → **S3.4**.
4. fixture: budget step carries `continue-on-error: true` or `${running:-0}` → RED on `check_cost_cap_present` (fail-closed leg) → **S5.2** (the fail-closed shape).
5. fixture: missing `concurrency:` block, or `cancel-in-progress: true` → RED on `check_cost_cap_present` (concurrency leg) → **S5.3** (the single-flight shape — see S5.3 note). *(Closes the S5.3 unfixtured-shape gap.)*
6. fixture: a `gh pr merge`/`--auto` step (or no `--draft` open) → RED on `check_no_merge` → **S1.3** shape backstop. *(S1.3's PRD `[gate-walk]` owner is L1 gate-walk; this fixture is an **additional** AC6 mechanical backstop, not the owner.)*
7. fixture: `allowed_tools` collapsed to one array, or an `*`/open-shell allowlist → RED on `check_default_deny_allowlist` → **S3.1** (the AC7a shape leg). *(Closes the AC7a no-negative-fixture gap — the Pass-3/adversarial blocker.)*
8. fixture: a second mode-conditional step (a relaxed budget under `if: mode==autonomous`) → RED on `check_mode_parity` → **S11**.

**S5.3 classification (Pass-3 blocker, resolved).** PRD `:91` tags S5.3 `[gate-walk]`, but single-flight ("exactly one run, no double-PR") is a **GH-native `concurrency:` property**, not a gate *decision* the SKILL.md gate-walk can render — there is no routing to walk. Its enforcement surface is the template's `concurrency:` block (design.md:217–219), a **template-shape** property the lint's `check_cost_cap_present` already asserts ("concurrency present", design.md:272). **Resolution:** S5.3's *mechanizable* leg is owned by **L2 `[template-lint]`** (fixture 5 — missing/`cancel-in-progress:true` concurrency → RED), NOT by L1 gate-walk. The L1 gate-walk row therefore does **not** claim S5.3; it claims only S5.1/S5.4 (turn/timeout — genuine gate decisions). This keeps the tag-to-layer lineage honest: the PRD `[gate-walk]` tag on S5.3 is satisfied for its decision-text, but its load-bearing single-flight property is lint-owned — stated, not papered over.

**S2.2 owner honesty (Pass-3 precision fix).** PRD `:44` labels AC1 **Runtime (advisory at discipline layer), no independent oracle (limit accepted)**. The gate-walk renders S2's *routing-decision text* (sensitive → refuse + escalate), but S2.2's load-bearing invariant — "no partial safe-slice commit that strands the sensitive half" — is a gate-owns-the-commit / Stage-B-discard **runtime** behavior (design.md C5) the gate-walk cannot *verify*. **S2.2's real owner is `[author-validate]` (one-shot, disowned per §4), with the named residual that it has no shipped oracle** (PRD:44). The L1 row above lists S2.1/S2.3 as gate-walk-covered and routes S2.2's verification to author-validate — not implying gate-walk verifies the no-safe-slice invariant.

**AC ↔ scenario ↔ layer completeness (PRD §3 mirror, both directions):**
- AC1→S2,S9 → S2.1/S2.3 + S9 L1 gate-walk; S2.2 author-validate (no shipped oracle, stated). AC2→S3.1–S3.4 → S3.1 L1, S3.2/S3.4 L2. AC3→S1.1,S1.2,S4 → L1. AC4→S1.4,S1.5 → S1.4 L1, S1.5 L2. AC5→S5.1–S5.4 → S5.1/S5.4 L1 gate-walk, S5.2-shape + S5.3-shape L2 lint. AC6→S1.3,S5.3 → S1.3 L1 gate-walk + `check_no_merge` shape backstop; S5.3 L2 lint (concurrency leg). AC7a→S3.1 → L1 + L2 `check_default_deny_allowlist` (fixture 7). AC7b→S10 → L1. AC8→S3.3 → L1. AC9→S11 → L2 `check_mode_parity`. AC10→S8 → L5 + L1 hand-off.
- **Every PRD scenario S1–S11 has an owner layer's test.** S1✓L1, S2✓L1(+author-validate for S2.2), S3✓L1+L2, S4✓L1, S5✓L1(.1/.4)+L2(.2/.3), S6✓L1(2 rows), S7✓L1(2 rows), S8✓L5+L1, S9✓L1, S10✓L1, S11✓L2. ✔ complete both directions.

**N/A passes (stated, not skipped):** no **E2E browser test** (the template is YAML, the gate is markdown — no UI; PRD §3 justifies). No **migration/data-migration** tests (no schema, no data). No **integration-test-across-stack** in the apex-runtime sense (apex ships zero runtime).

---

## §4 Rollout

- **L1/L1b, L2, L5a:** **direct** — markdown + reference files + doc rows activate next session on reinstall. No feature flag, no migration, no cohort. (apex skills have no runtime to gate.)
- **L4:** **direct** — the CI workflow activates on the first push/PR after merge; if it surfaces a lint failure on the shipped template, that is the intended gate firing.
- **L5b / release mechanics (uses the repo's actual scripted path):** The release is **`./scripts/release.sh 0.3.7`**, run post-merge from `main`. It (a) requires the `## [Unreleased]` section L5b added, (b) bumps `plugin.json` + `marketplace.json` to `0.3.7` via `jq` (`:75,79`), (c) dates `## [Unreleased] → ## [0.3.7] — <date>` (`:83`), (d) commits `release: 0.3.7` **directly to main** and pushes (`:88–92`), (e) tags `v0.3.7` + pushes (`:96–97`), (f) builds the zip, (g) cuts the `--latest` GitHub release (`:111–116`). **Do NOT bump versions or pre-date the CHANGELOG in the feature PR** (`release.sh:67` aborts on a pre-bumped version). The live plugin runs the cached build, so the change goes live on **reinstall** per `CONTRIBUTING.md:130–141` (pull marketplace clone → `rsync` cache → bump `gitCommitSha` → restart) — not a bare "reinstall."
- **Cohort / canary / dual-write / expand→migrate→contract:** **N/A** — no data, no schema, no destructive change.

---

## §5 Reversibility (per layer)

- **L1 / L1b** (`SKILL.md`): `git revert` the file reverts **both together** — they share one file, so **L1b has no independent revert** (this is why L1b is a sub-step, not a separable PR). If L1b's seam-contract text is wrong but L1's pipeline is fine, the fix is a **forward-fix edit, not a revert** (the seam contract is the freeze-gating downstream interface — more likely caught at L1b's own review than to need an emergency revert). Fully reversible otherwise — no persistent side effect (the skill writes nothing until invoked; on revert it simply stops being available).
- **L2** (`reference/` + fixtures): `git revert` the directory — a **clean-delete add** (the `reference/` convention is new, self-contained, no consumer in-tree; the BookBridge refactor is a separate repo, downstream, not built here). Fully reversible.
- **L5a** (doc rows: FLOW.md / help.md / README): `git revert` the doc rows. **Shared-file edits** (revert may need rebase if those files moved underneath), but additive in content — freely revertible.
- **L5b** (CHANGELOG `## [Unreleased]` entry; version files untouched in-PR): the CHANGELOG entry `git revert`s freely **before release**; the version files are not touched in-PR so there is nothing to revert there. **The one conditional-rollback step in the entire plan is the RELEASE leg, not the PR:** once `release.sh` runs, it creates an **annotated tag `v0.3.7` pushed to origin** and a **`--latest` GitHub release with an attached zip** (`release.sh:94–116`) — these are **durable, roll-forward-only**. `git revert` of the release commit does NOT delete the tag or un-mark the release. If `0.3.7` is already released and must be undone, **roll forward to `0.3.8`** rather than un-publishing (standard release hygiene). This is the only not-cleanly-revertible artifact class the plan introduces; flag it in the PR/release notes.
- **L4** (CI workflow): `git revert` the `.github/workflows/conformance-lint.yml` file — a **clean-delete add** under the already-existing `.github/` (only `workflows/` is new). Removes apex's first CI check cleanly; no state. **If the lint is wrong:** *too-strict* (false-RED blocks apex CI on a valid template) → **revert L4 to unblock CI**, fix the check, re-add (this is the most operationally-likely rollback trigger for the whole effort); *too-loose* (false-GREEN misses a broken template) → **forward-fix by tightening the check** (a new L2-class edit, NOT a revert).
- **No irreversible operation in the FEATURE PRs** — no destructive migration, no paid-API one-shot, no immutable write. The `[author-validate]` sandbox run is in a throwaway repo (no apex-side state). The durable `incident-retro` lessons class is downstream of *this* gate, not produced by it. The single durable artifact this effort introduces is the **release tag + GitHub release** (release-time, roll-forward-only — above).

---

## §6 Downstream (DOCUMENTED, NOT built in this effort)

Gated on L1b's four seam interfaces (U1/U2/U5/U9) freezing — which they do at this plan's freeze. Lives in the **BookBridge** repo, a separate effort:
- **`auto-fix-bug.yml` adopts the template**, closing its five located holes: title-outside-fence (`:165` vs `:174–176`) → inside the per-run nonce fence (AC2); open `allowed_tools` (`:194`) → two-tier default-deny with staged unlock (AC7a/AC7b); fail-OPEN quota guard (`continue-on-error: true :69`, `running=${running:-0} :88`) → fail-CLOSED `budget_precheck` (AC5/B3); strategy-not-gates prompt (`:162`) → names the apex gates (AC4); suite-not-reproduce (`:186`) → red-before-green via the two-invocation split (AC3). BookBridge keeps its labels/capture-UI/deploy/customer-data paths. *(BookBridge line anchors to be re-verified at refactor time.)*
- **`investigate-bug` invokes the read-only-first rails** — its Rule #1 (read-only-first) + Step 6.5 (in-flight precondition) generalize to AC7b (P2) and S7.

This refactor is the **first conformance test of the seams** (PRD §7 ordering). Tracked as a follow-on, not a layer here.

---

## §7 Open sign-off items for `impl-plan-review`

1. **Version: `0.3.7` (patch), released via `scripts/release.sh`.** Proposed over `0.4.0` on the 0.3.6 precedent (two whole skills shipped as a patch). The bump + dating happen at release time, not in the feature PR. Ratify or override.
2. **L4 — apex's first CI workflow** (under the existing `.github/`). Include in this effort (makes the lint a real required check on apex itself, on push + PR) vs demote to a follow-on (lint stays author-validated only). L1/L1b + L2 + L5 are unaffected either way (demote-branch effect on §3 stated in L4 + the §3 L4 row). Built last so the L5 CHANGELOG is authored once with this resolved.
3. **CLAUDE.md doc-edit (design #4) scoped OUT** — targets the user's private `~/.claude/CLAUDE.md`, not a repo file. Confirm it ships as a manual user-edit suggestion in the PR description, not part of the diff.
4. **L5 anchors re-located by content at edit time**, not by stored line number (the tree drifts; the verified anchors recorded above are a HEAD snapshot — including the corrected FLOW.md two-destination structure).

---

## Plan freeze

**FREEZE-CANDIDATE pending `apex:impl-plan-review` + user sign-off.** On freeze, `superpowers:executing-plans` begins at **L1** (`skills/autonomous-fix/SKILL.md`). The freeze of L1b's four seams (U1/U2/U5/U9) is the contract the BookBridge two-children refactor (§6) waits on.

**Circuit breaker (cancel-by-default).** If implementation runs materially past this 4-PR stack (+ L1b milestone) — meaningfully more layers or scope — without shipping, STOP and re-bet at the design/PRD gate rather than silently extending. The L2 bet carries its own narrower breaker (lint-green-on-template / two-invocation-seam-expressible → return to `design.md` if unreachable).
