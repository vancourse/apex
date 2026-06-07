# Design-Review — `autonomous-fix` (cold synthesis + freeze gate)

**Status:** review complete · **Verdict: NOT FREEZE-READY** · **Slug:** `autonomous-fix`
**Design under review:** `design.md` (drafted) · **PRD:** `prd.md` (FROZEN 2026-06-06)
**Method:** six cold lenses dispatched in parallel (AC-coverage / unknowns-resolved / threat-model / MVP-scope / integration / whole-design adversarial), consolidated here with per-pass verdicts, a STRIDE table, an integration verdict, and an explicit freeze-readiness gate. Source-anchored claims were re-verified against the live tree before classification.

---

## Source re-verification (the load-bearing facts four lenses disputed)

Three "mirror / confirmed-at-source" claims in the design were checked against the actual files. Two are **false as written**; one fail-open primitive the design inherits was confirmed:

1. **`guard-security-paths.sh:19`** is literally:
   `*/auth/*|*/credentials/*|*/oauth/*|*/oidc/*|*/sso/*|*/secrets/*|*/security/*|*/encryption/*|*/signing/*|*/jwt/*|*/saml/*|*/permissions/*|*/authorization/*`
   It contains **no** `migrations`, `rls`, `crypto`, `*.pem`, `*.key`, `.env*`, or `.github/`. The design's `DENY_GLOBS` default **adds** all of those. **"Mirrors the hook by construction / they can't drift" is false at design time** — the lists already diverge on the highest-value paths (migrations, RLS — the exact BookBridge customer-data threat). Flagged independently by Reviews 2 (F1), 3 (T6), 4, 5 (Finding 1), 6 (A1). **Confirmed FALSE.**
2. **`BookBridge .github/workflows/auto-fix-bug.yml`** quota guard: line 40 `continue-on-error: true`, line 51 `running=$(gh run list …)`, line 59 `running=${running:-0}`. This is the **fail-OPEN** pattern — a failed/rate-limited `gh` read defaults the budget to 0 and PROCEEDs. The design ships `gh run list` as the **default cost-cap proxy sink** and therefore **inherits the exact fail-open hole it claims AC5 closes**. Flagged by Review 3 (T1). **Confirmed at source.**
3. **`incident-retro/design.md` is 60 lines.** The prompt names it the "depth + format exemplar." The design under review is ~350+ lines. The excess is substantially *repetition* (the five phases are written out 5+ times). Flagged by Reviews 4 (Finding 3) and 6 (D1/D2). **Confirmed.**
4. **`FLOW.md`** side-path footnote block (`:292–301`) is a code-fenced, **single-line-per-entry** grammar (`name — one-clause gloss`); the multi-sentence prose lives in the separate "Side paths (not phase-sequential)" section (`:252–256`). The design's proposed **4-line** matrix-footnote entry breaks the fence grammar. Flagged by Review 5 (Finding 2). **Confirmed.**

These four are not opinion — they are the design's own citations failing against the bytes. Because the design's credibility rests on its line anchors being literally true, a false anchor is a freeze blocker, not a nit.

---

## Per-pass verdicts

### Lens 1 — AC-coverage (does each AC have a buildable mechanism that satisfies its failure oracle?)

| AC | Verdict | Blocking? |
|---|---|---|
| AC1 sensitive-path | MECHANIZED at Stage B (`git diff` + `git reset --hard` + escalate); **Stage A pre-write "gate" has no obtaining-mechanism** under the opaque runner — degenerates to a prompt directive | **B1** (the shared-seam finding) |
| AC2 fence + title + nonce | MECHANIZED (nonce fence + 4 effect-checks). One lint sub-claim over-reaches (see Lens 3 B/L) | partial — see B4 |
| AC3 reproduce-first | MECHANIZED for ordering; **"red-on-`main` is *checked*" has no test-isolation seam**; **test-write-in-read-only-phase contradicts AC7b** | **B1, B2** |
| AC4 gate names | MECHANIZED (grep). Clean. | no |
| AC5 budgets + cost | MECHANIZED ordering (P1-first), **but ships a fail-OPEN proxy** | **B3** |
| AC6 draft-only | MECHANIZED (branch-protection outside agent + no-merge lint). Strongest AC. | no |
| AC7a allowlist | MECHANIZED; lint's "read-only set distinct from write set" has no concrete two-set artifact to check | **B5** |
| AC7b staged unlock | MECHANIZED ordering (two runner steps) — **this is the seam B1 needs but never names** | **B1** |
| AC8 leak-scan | MECHANIZED (3 sinks, hard-fail, fail-closed). Matcher correctly a project seam. | no |
| AC9 parity | **`check_mode_parity` has no second artifact to diff** (interactive is doc-only) | **B6** |
| AC10 retro handoff | doc cross-ref. Clean. | no |

**Headline (Lens 1 + Lens 6 agree):** AC1-Stage-A, AC3-red-on-`main`, and AC7b all depend on the **same two-invocation runner split** (read-only invocation emits artifacts → wrapper gates → write invocation). The template *already encodes the split for AC7b* (`run-fixer-readonly` → … → `run-fixer-write`) but the design never names it as the obtaining-mechanism for AC1/AC3. As written, AC1's pre-write refusal and AC3's red-on-`main` check are **restated as gates, not mechanized** — an implementer finds no runner seam and silently downgrades both to prompt-directives. **VERDICT: FAIL on this lens** (the pre-write halves of two runtime ACs over-claim enforcement). Closable cheaply by naming the seam.

### Lens 2 — Unknowns-resolved (is every U1–U11 genuinely decided, fail-closed, implementable?)

**VERDICT: PASS on decidedness.** 0/11 bounced. The three highest-risk-of-fake-resolution (U3 input-set, U10 wrong-invariant bound, U11 the-rule) are the *cleanest* — each delivers the concrete artifact the PRD demanded (fixed input set / stated bound / decidable per-operation rule). U8's two-point atomic check genuinely resolves the PRD's named "is AC1 implementable?" doubt. Two **implementability-claim** defects (not decidedness): F1 (the hook-mirror claim is false — same as the cross-lens blocker) and F2 (`gh run list` does not trivially expose per-*author* attribution; the *author* bucket needs run→issue-author joining, more than `gh run list` returns — only the repo/day bucket is `gh run list`-trivial). F1 is blocking (factual); F2 is a should-fix caveat.

### Lens 3 — Threat-model (does the gate hold under attack? STRIDE)

**VERDICT: NOT freeze-ready under attack.** See the STRIDE table below. Four findings are blocking-or-elevate: cost-cap fail-open (T1, confirmed), the lint cannot verify title-in-fence under prompt-composition (T2/B4), one-hop import grep is trivially evaded by dynamic/indirect/relative imports (T3 — a *depth-1* hole, not the named depth-≥2 residual), and the Stage-B reset has live exfil sinks (`curl`/`gh`/log) during the write window plus a runner-owns-commit-vs-gate-owns-reset ambiguity (T4). These are not "design is wrong" — most are "asserted closed; must be re-labeled as named/accepted residual OR the dial tightened."

### Lens 4 — MVP-scope (is the MVP genuinely minimal? subtractive ethos?)

**VERDICT: FAIL.** Two scope creeps + one bloat:
- **Finding 1 (major):** the reference template renders **~15 named executing steps**, of which only ~5 carry a template-shape AC the lint checks. The other ~8 (`risk-route`, `assert-red-test`, `sensitive-route-prewrite`, `run-fixer-write`, `sensitive-route-postwrite`, `leak-scan`, `in-flight-precondition`, `git reset`/`git clean` mechanics) are the **runtime ACs the PRD §4 assigns to the project's wired runtime** and the lint explicitly does not touch. Scaffolding them as named steps with behavioral comments converts an *illustration* into a *runner template* apex de-facto owns. By the design's own Pass-2 strike rule, an element backing no lint-checked AC is the project's, not apex's — those steps are strikeable to `# SEAM:` comments.
- **Finding 2 (moderate):** U8's two-phase-commit + destructive `git reset --hard` recovery protocol is built runtime control for a runtime AC apex disowns. The minimal U8 resolution is the seam contract sentence; the two-stage/reset detail belongs in the *project's* implementation.
- **Finding 3 (moderate):** the design is ~6x the cited exemplar, largely via duplication — the "MVP cut + deferral list (consolidated)" section restates Pass 2/3 verbatim; "Port these seams" restates the Pass-0 contracts; the full YAML body and full lint table are inlined (impl material). Plus the "three angle-drafts converged" preamble is process-narration the design-review skill warns against (and A1 survived all three drafts, disproving "convergence = stability").

### Lens 5 — Integration (compose-not-duplicate; correct surface placement)

**VERDICT: PASS on judgments, 2 material fixes.** The *core* integration calls are all correct: DEBUG side-path (not a pipeline grid row), crisp Distinct-from lines for all six composed gates, children-invoke-parent contract gated on the four seams, help/README placement modeled on `incident-retro`. Material fixes: **(M1)** the false hook-mirror claim (= the cross-lens blocker); **(M2)** the FLOW.md edit targets the wrong structure and breaks the single-line code-fence grammar — compress the matrix-footnote entry to one line, keep the prose in the Side-paths section. Minor: the DEBUG-paragraph verb ("composes from `systematic-debugging`" sits awkwardly one clause after "apex deliberately defers / doesn't duplicate" — use "requires from / invokes"); the help.md "I FIRE THESE AUTOMATICALLY" header mis-categorizes a never-hook-fired skill (mirror `incident-retro`'s "run by name" caveat); "all confirmed at source" for BookBridge anchors should be "PRD-inherited, re-verify at refactor time."

### Lens 6 — Whole-design adversarial (over-claims + internal contradictions)

**VERDICT: DO NOT FREEZE.** Confirms the cross-lens blockers (A1 false mirror; A2/A3 lint subjects undefined) and adds **two internal contradictions** the other lenses missed:
- **C3:** U10 lists "minimal flip red→green" as one of four *observable proxies*, but U11 and Deferral #6 say minimality **has no mechanical oracle**. A property cannot be both an observable proxy and a no-oracle trusted-self-report. U10 has **exactly one** mechanical proxy (red-on-`main`) + three advisory directives.
- **C4:** the escalation **decision** is hard-fail but the escalation **channel** is best-effort. On channel failure in an *unattended* run, a refused sensitive bug produces no commit, no comment, no human notified — a **silent drop**, which violates Seam 3b's apex-owned invariant "escalation NEVER silently drops the bug." The channel needs ≥1 durable/hard leg (the non-zero exit surfaced as a required status check counts) or the invariant must be weakened honestly.
- **C5:** N1's `git reset --hard` assumes single-commit-at-end; if the opaque runner commits/pushes per-turn, the sensitive bytes are already in a (readable) branch commit before Stage B — the commit-cadence constraint ("runner MUST NOT push until Stage B passes; pre-Stage-B commits are local-only") is unstated and load-bearing.

---

## STRIDE table (consolidated, with disposition)

| Category | Threat | Design's claim | Review disposition | Fix in revised design |
|---|---|---|---|---|
| **Spoofing** | A1 forges "SYSTEM:" / closes fence early (marker injection) | nonce fence; marker-injection "defeated" | Sound — but nonce must be **secret until run end**, and `HMAC(run_id)` is predictable without a secret key (T5). Label-as-control-flow vs label-as-data: label-derived risk must be **raise-only** too, else A3 applies a low-sev label to downgrade. | Pin `openssl rand` form; HMAC only with a CI-secret key. State nonce-secrecy assumption. Make label-derived risk raise-only. |
| **Tampering** | A2 scope-creeps into sensitive; A1 injects "edit this file"; write before repro | AC1 two-point + AC7b staged unlock | Stage A is **advisory self-report**, not a gate (B1); one-hop grep evaded by dynamic/indirect/relative imports — a **depth-1** hole, not depth-≥2 (T3); the template's *trimmed* `SENSITIVE_GLOBS` drops `oauth/oidc/sso/jwt/saml/…` the full list has (T6). | Name the two-invocation seam (B1). Re-label transitive arm as substring-match with named evasion residual. Make the template carry the **full** list. |
| **Repudiation** | which rail let it through? | structured artifacts per terminal | Sound; apex-owns-no-audit-store is PRD-sanctioned. **WAD/NOT-REPRO is an unguarded agent-self-declared terminal** an attacker can steer to ("close as WAD") — an injection escape sink not connected to the fence (Review 1 Gap-2). | Require NOT-REPRO to emit an escalation artifact (already "never auto-closes"); add to §6 as named residual. |
| **Info-disclosure** | paste secret/customer row into comment; `gh`/`curl` exfil at token scope during write window | AC8 leak-scan on 3 sinks; token-scope min | Leak-scan covers commit/PR/comment but **not** outbound `curl` or `$GITHUB_OUTPUT` during the write window; `git reset` reverts the tree, not data already sent (T4). Token-scope cannot remove `issues: write` or egress. | State egress/`gh`-during-fix as **named accepted residual** (token-scope cannot close it); pin gate-owns-commit so reset is in time. |
| **DoS** | A3 storm; double-webhook; pathological loop; **attacker forces escalate-everything** | AC5 4-budget + concurrency | Cost proxy **fails OPEN** (T1, confirmed). Sockpuppet handled by repo/day bucket. **Attacker stuffing `sev1 payments auth` forces high-risk route → escalation-flood DoS on yield** (T9) — unmodeled. | Fail-CLOSED on unread budget (lint rejects `continue-on-error`/`:-0` on the budget step). Add escalation-flood to DoS pass; reuse per-actor budget to cap escalations. |
| **EoP** | merge/push-to-protected; high-blast bug into cheap path; confused-deputy | AC6 branch-protection outside agent (load-bearing); least-priv token | Strongest part. Residuals: branch-protection-off is unverifiable by shipped artifacts (closable with a startup `gh api …/protection` assertion, T8); deny-list shrinkage is **warn, not hard-fail** — the Goodhart attack is only advisorily mitigated (T7); `check_no_merge` proves the *author* wrote no merge step, not what the agent's `gh` does at runtime (B1-class). | Add the branch-protection startup assertion as a port-these-seams precondition. State deny-list shrinkage hard-fail-vs-warn explicitly. Demote `check_no_merge` to author-hygiene; AC6 enforced solely by branch-protection. |

**Pass condition:** every category carries a named mitigation or an explicitly-accepted residual *after the revised-design fixes*. Before the fixes, four categories (Tampering/Info-disclosure/DoS/EoP) had asserted-closed items that are actually live or advisory — those are the blockers below.

---

## Integration verdict

**PASS on architecture, FAIL on two factual integration claims (both fixed in the revised design).** `autonomous-fix` is correctly a DEBUG side-path (not a linear-pipeline grid row), composes-not-duplicates with crisp Distinct-from lines for all six neighbors, and the children-invoke-parent contract is correctly gated on the four seams freezing. The reusable-primitives audit (security-review/threat-model, ai-pre-review-checklist via the U7 table, pr-discipline, systematic-debugging, incident-retro, adversarial-pair, GH primitives) is genuinely compose-not-duplicate. The two integration *defects* are the false hook-mirror invariant (M1) and the FLOW.md grammar-breaking edit (M2) — both corrected. The `reference/` subdir is a genuinely-new apex convention (verified: no skill ships one today) and the design honestly flags it; the new apex-CI step to run the lint over its own template is a small real new integration surface worth the one-line flag added.

---

## Blocking issues (must clear before freeze)

1. **[B1 — cross-lens, highest leverage] Name the two-invocation runner seam.** The read-only invocation's contract is "emit `PLAN.json` (planned files) + the reproducing test file, **write nothing else**"; the wrapper runs `sensitive-route-prewrite` (AC1 Stage A) + `assert-red-test` (AC3 red-on-`main`, run the committed test against the pre-fix tree) **between** invocations; then the write allowlist unlocks (AC7b). One seam closes the pre-write halves of AC1, AC3, AC7b. Without it, AC1-pre-write and AC3-red-on-`main` are restated-as-gate, not mechanized.
2. **[B2] Resolve the AC3-test-write vs AC7b-read-only contradiction.** Writing the reproducing test is a write, but it must precede write-unlock. State the explicit carve-out: the read-only phase permits **test-file writes only** (path-scoped, e.g. `tests/**`), not source writes — and `check_default_deny_allowlist` must encode this two-tier shape.
3. **[B3 — confirmed at source] Cost-cap must fail CLOSED.** `budget_precheck` returning UNKNOWN (read failed) ⇒ HALT. The lint must reject `continue-on-error: true` and a `:-0`-style default on the budget step — otherwise the design ships the exact fail-open primitive (`auto-fix-bug.yml:40,59`) it claims to fix.
4. **[B4] The lint cannot verify "title inside fence" under prompt-composition.** A grep-class lint cannot prove positional containment across multi-step / `env`-indirected prompt assembly, and "nonce is run-scoped not literal" requires data-flow, not substring match. Either constrain the template to a **single-step, single-block prompt** and have the lint *reject* multi-step/`env`-indirected assembly (making containment decidable), or demote `check_title_in_fence` to best-effort and stop claiming it mechanically closes the `:165` hole. Re-budget the lint honestly.
5. **[B5] `check_default_deny_allowlist` and the template must carry two concrete allowlist arrays** (read-only set, write set) for the "distinct sets" check to run — or the check downgrades to "two distinct named runner steps in order." Pick one and make the artifact match.
6. **[B6] `check_mode_parity` has no second artifact to diff** (interactive is doc-only). Redefine the check as: "exactly one step is mode-conditional (the confirm step, guarded by `if: inputs.mode == 'interactive'`), and no budget/allowlist/fence key sits under any mode conditional" — a single-file check. Reconcile the "doc-only interactive" decision with the "diff autonomous vs interactive template" language.
7. **[B7 — confirmed FALSE] Replace every "mirrors `guard-security-paths.sh:19` / agree by construction / can't drift"** with "documented **superset** of the hook (the hook is the floor), re-tuned for refuse-semantics; the two are independently maintained and may diverge (residual)." Reconcile the template's trimmed `SENSITIVE_GLOBS` to carry the **full** list. Optionally spawn a task to widen the hook to match (the only way "agree by construction" becomes true).
8. **[B8 — internal contradiction] Remove "minimal flip" from U10's observable proxies.** U10 has one mechanical proxy (red-on-`main`) + three advisory directives the human checks at draft review. (Resolves the U10/U11/Deferral-#6 contradiction.)
9. **[B9 — internal contradiction] Give the escalation channel ≥1 hard/durable leg** so a sensitive refusal is never a silent drop (violating Seam 3b). The non-zero exit surfaced as a required status check is the durable signal; the comment/label remain best-effort *on top of* it.
10. **[B10 — scope] Demote the ~8 runtime-AC template steps to `# SEAM:` comment-blocks**; the template contains only the lint-checked steps + seam pointers. Collapse U8 to the seam-contract sentence (move the two-stage/reset detail to a one-line "reference implementations may…" note). Cut the three duplications (consolidated MVP/deferral section, the "Port these seams" re-derivation, the inlined full artifact bodies) and the convergence preamble.

**Should-fix (non-blocking, applied in the revised design where cheap):** F2 (`gh run list` author-keying caveat); T3 import-evasion residual naming; T4 egress residual + commit-cadence (C5); T5 nonce-secrecy + label-raise-only; T7 deny-list-shrinkage hard-fail-vs-warn decision; T8 branch-protection startup assertion; T9 escalation-flood DoS; M2 FLOW.md grammar; the DEBUG verb, help.md category caveat, and "confirmed-at-source" wording.

**Count:** 10 blocking findings (≥3 + multiple broken invariants and false anchors) → per `design-review`'s own gate, **back to design with fixes applied before freeze.** All ten are text/structure fixes — no return to the PRD, no scope change. The revised design below applies all ten plus the cheap should-fixes.

---

## Freeze-readiness

**NOT FREEZE-READY as drafted.** The design's bones are right (seam-first spine, branch-protection-outside-the-agent as the load-bearing AC6 control, the absence-of-effect fence oracle, the three-actor STRIDE model, cost-first ordering) and Lens 2 confirms every unknown is genuinely decided. But three headline safety claims (AC2 lint containment, AC5 cost proxy, AC1 hook-mirror) **assert guarantees the artifacts do not deliver**, two are **factually false at source**, and there are **two internal contradictions** (U10/U11; escalation channel/Seam 3b) plus the **shared two-invocation seam** left unnamed. The revised design (below) applies all ten blocking fixes and the cheap should-fixes; with those applied the design is freeze-candidate, but the **revised** design should be re-confirmed (it has not itself been cold-reviewed). Recommend: apply fixes (done below) → user sign-off on the revised design → freeze → `apex:impl-plan`.


---

## Re-review round 2 — synthesizer verdict + freeze gate

Four re-review lenses (blocker-closure, citation-truth, regression+scope, AC-coverage-reconfirm) consolidated and independently re-verified against the LIVE tree. I read every contested anchor at source before ruling.

### Per-blocker closure verdict (B1–B10)

| # | Blocker | Verdict | Evidence (re-verified) |
|---|---|---|---|
| **B1** | Name the runner seam (mechanize AC1-StageA/AC3-red-on-main/AC7b, don't restate) | **CLOSED** | Pass 0 "The two-invocation runner seam" is a dedicated named subsection (inv #1 read-only+test-only → emit PLAN.json+test → wrapper assert-red-test+sensitive-prewrite → inv #2 write). All three ACs reference the split, not restate it. Portability precondition stated. |
| **B2** | Test-file-write carve-out (resolve AC3↔AC7b contradiction) | **CLOSED** | Inv #1 allowlist = read + write-to-`tests/**`-only; named "the *one* carve-out… without it AC3 and AC7b contradict." Mirrored in P2/S10/template. |
| **B3** | Cost-cap fails closed | **CLOSED** | Seam-2 cites BookBridge fail-open exemplar; AC5 returns HALT on `>= cap` OR UNKNOWN; lint rejects `continue-on-error`/`:-0`. Anchors `:69`/`:88` verified at source. |
| **B4** | Lint scope-honesty (decidable property, no over-claim) | **CLOSED** | Single-step/single-block prompt; `check_title_in_fence` rejects multi-step/`env`-indirection; `check_nonce_delimiter` asserts property (open==close ∧ `${...}`), not provenance. |
| **B5** | Allowlist artifact (one concrete backing artifact) | **CLOSED** | `check_default_deny_allowlist` asserts two concrete `allowed_tools` arrays. (Impl-time note: the YAML stub must carry the arrays literally for the check to fire — design intent unambiguous; not a design-logic gap.) |
| **B6** | Mode-parity as single-file check | **CLOSED** | `check_mode_parity` = exactly one mode-conditional step + no budget/allowlist/fence/sensitive key under any conditional; "no second artifact to diff" framing applied. |
| **B7** | Fix the FALSE citation (the #1 finding) | **CLOSED + byte-verified** | `guard-security-paths.sh:19` quoted verbatim; live bytes match exactly (no migrations/rls/crypto/pem/key/.env/.github). Relationship reframed as "documented SUPERSET / floor / MAY diverge"; "mirrors by construction" abandoned; advisory-only (`:9`/`:25` exit 0) confirmed; template ships FULL list (oauth/oidc/sso/jwt/saml retained). Convergence → Deferral #10. |
| **B8** | Remove minimality from U10 proxies | **CLOSED** | U10 = ONE mechanical proxy (red-on-`main`) + advisory directives; "minimal-flip REMOVED from the proxy set." Deferral #6 keeps minimality no-oracle. P4/ASCII "minimal flip" is the FIX-phase action, not a claimed proxy — consistent. |
| **B9** | Escalation hard leg (no silent drop) | **CLOSED** | Seam-3: unconditional non-zero-exit → required status check; comment/label demoted to best-effort decoration; reconciled with Seam 3b; carried through U5/U11/STRIDE/failure-modes/S4. |
| **B10** | Cut template scope + duplication | **CLOSED on enumerated items** | Template renders only 6 shape-AC steps; ~8 runtime-AC behaviors are `# SEAM:` comments; U8 collapsed to one sentence; convergence preamble + re-derivations removed; lint stable at 7 checks/~150 LOC. *Length caveat:* still well above the 60-line incident-retro exemplar — but every enumerated cut is done and the residual length is irreducible STRIDE/U-resolution/seam content (3 artifacts + 4 doc edits + 4 seams + 11 U-resolutions, all PRD-mandated), not repetition. Rated closed on its enumerated sub-parts; the absolute line-count aspiration is treated as illustrative, not a literal freeze gate.

**All 10 blockers closed on their prescribed, enumerated sub-parts.**

### Citation-truth verdict

The #1 prior defect (B7 false citation) is **genuinely closed and byte-accurate**. All structural citations re-verified TRUE at source: `guard-security-paths.sh:19`, hook advisory-only `:9`/`:25`, BookBridge fail-open `:69`/`:88`, `FLOW.md` Side-paths `:254`/DEBUG `:256`/ADVERSARIAL-PAIR `:258`/incident-retro `:302`, `commands/help.md` 68-line file, `incident-retro/design.md` 60 lines, `reference/` is genuinely new, `apex:adversarial-pair` exists and is correctly subordinated over `superpowers:dispatching-parallel-agents` throughout, `pr-discipline §1`=draft-default / `§6`=tests-same-PR.

**THREE B7-class false citations were present in the handed revised-design text and are FIXED in `final_design_md`** (all re-verified false against the live bytes by me):

1. **help.md (C-1 / R1).** Handed text asserted "there is no 'I FIRE THESE AUTOMATICALLY' header." FALSE — the header is at `commands/help.md:26` and the Post-release line `:37–38` sits *inside* it. This is the exact verify-at-source failure class B7 exists to kill, locally re-introduced. **Fixed:** false parenthetical removed; entry now correctly placed under the existing "I FIRE THESE AUTOMATICALLY → Post-release" header at `:26`/`:37–38` with a freshly-authored caveat (autonomous-fix is *also* CI-wireable, which incident-retro's "run by name after a RESOLVED incident" caveat is not — so the caveat is authored fresh, not copied).
2. **README (C-2 / R2).** Handed text said "after the incident-retro row at `README.md:50`." FALSE — incident-retro is at `README.md:52`; `:50` is the `summarize-changes` row. **Fixed → `:52`.**
3. **ai-pre-review-checklist Step 4 (NEW, caught this round).** Re-review 2 flagged the step-numbers as unverified; I verified them against `skills/ai-pre-review-checklist/SKILL.md`. **Step 6 = Test-Quality** (design cites it correctly) but **Step 4 = Concurrency** (`:162`), NOT reproduce/test — so U7's "Step 4 load-bearing for AC3" was a FALSE step-number anchor. AC3 (reproduce-first / wrong-invariant) maps to the test-quality lens = **Step 6**, which the design already cites correctly elsewhere. **Fixed → Step 6** in U7, reconciling it with the design's own correct Step-6 usage.

On-disk note: the on-disk `docs/autonomous-fix/design.md` is still the OLD draft (it carries `:40/:59` at lines 99 AND 246, plus the false help.md/README anchors). `final_design_md` is the corrected text to write over it; the impl step must overwrite the file, not patch line 99 alone.

### Freeze readiness

All B1–B10 closed; zero false citations remain after the three fixes; no new blocker introduced; scope tight and subtractive; no AC lost its mechanism to the B10 cut; adversarial-pair reference correct. **freeze_ready = true.** The design's own closing note ("not itself cold-reviewed") is now discharged by this round-2 re-review.
