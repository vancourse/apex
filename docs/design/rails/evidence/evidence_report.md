# Why the AI-built apps keep shipping basic defects: evidence synthesis

**Inputs.** This synthesis draws on five sources:

- 569 jarvis and 287 nexusiq fix-keyword commits, which become 524 and 250 real fixes once false positives are removed.
- 233 jarvis gap issues from jarvis-uat, Purser UAT and Purser H1.
- 1,000 failed CI runs: 1,295 job failures, every one classified.
- Two harness inventories: the apex plugin, and jarvis's own hooks, skills and CI.
- Four document audits covering about 1.8M words.

**Pool.** Every share below is computed against a pool of **1,007 escaped defects** (524 + 250 + 233) unless it says otherwise.

**Citations.** Shas and issue numbers come from the classifier and audit outputs I was given. I did not re-fetch them for this synthesis.

## Executive summary

- **The "basic bugs" are mostly seam bugs.** 35.2% of the 1,007 are wiring, contract drift or deploy/config defects between pieces that each passed their own tests: wiring 15.7%, deploy/env 10.5%, contract drift 8.9%. Another 18.8% are the process machinery breaking itself: harness 10.4%, broken tests 5.0%, docs drift 3.4%. Domain logic, clocks and error handling together are 17.8%, and GUI behaviour plus UI honesty 8.3%. Among the 233 gaps, 39.5% originate at cross-component integration, and 48% are features that were built but never wired (63), never built (25), or pretend to work (24).
- **Almost nothing was caught automatically before a person hit it.** Of 774 fix commits, a CI gate found 8.3% and an e2e or smoke run 1.7%. The operator using real data found 27.4% and audit sweeps 16.0%; all 233 gaps were found after merge by an audit or UAT. In nexusiq the operator found 49.6% and CI found 2, because nexusiq never had PR CI. The instruments that would have caught these defects first are integration-level: booting the real root, deploy preflight, real-backend e2e, and contract tests or codegen. Together they are 40.2% of earliest catches. In jarvis none of them blocks a merge except a walkthrough that covers Purser only.
- **The harness is jarvis's largest single defect source.** 19.3% of jarvis real fixes (101) are the CI, hooks and docs machinery itself; adding broken tests and docs drift brings it to 30.3%. Of 1,295 CI job failures, 44.0% were harness or gate defects and 18.7% real product defects. Three jobs (Sherpa gate B, generated-docs validation, classify) produced 402 failures and 3 product defects. Red stopped meaning anything: 74 of 74 master pushes were red on 09-02..09-06, and 84.5% of scheduled runs were red.
- **Documents did not turn into checks.** Of 117 defect-to-spec traces, only 30 (26%) had a correct, testable spec that the build missed. 21 (18%) stated the right intent in a form that could not fail, 20 (17%) prescribed the defect, and 46 (39%) were silent or had no spec. Nexusiq carries about 5 words of documentation per line of code. Jarvis's resource dossier is 153k words for about 10k LOC. Sherpa has about 60k words for an app no fleet mounts. The documents that did the work were short and checked against code: the egress §0 threat model, the dataplane A3 reconciliation, the nexusiq 2026-04-10 audit, and the trips-rulebook case table.
- **Prose does not bind, and the same mistakes repeated across both repos.**
  - 22 of the 32 bold rules in CLAUDE.md are prose only. The file was cut to 1,962 words and regrew to 9,160 in seven weeks.
  - Apex's phase nudges were followed 13% of the time. None of its 17 commands was typed in 241 sessions, and three of its path hooks are silently inert on Windows.
  - Nexusiq's own retrospective named "built but never called" on 2026-02-21. Jarvis then shipped 63 built-not-wired gaps.
  - What worked either fires at the moment of a cheap action or blocks a merge: deny hooks, claim-before-edit (58% to 90% of edit sessions), structural census gates, the wire freeze, and cold two-voice review.
  - 58.4% of jarvis fixes and 69.2% of nexusiq fixes repair work from the previous one or two weeks.

## 1. Where defects come from

### 1.1 What the "basic bugs" actually are

| Family | Root causes | Count | Share of 1,007 |
|---|---|---|---|
| Seams: wiring, API contracts, deploy/config | wiring_integration, contract_drift, deploy_env_config | 354 | 35.2% |
| The process breaking itself | harness_self, test_defect, docs_drift | 189 | 18.8% |
| Logic: domain rules, clocks/lifecycle, error handling | domain_rule, state_lifecycle, error_handling | 179 | 17.8% |
| Security and privacy | security_privacy | 86 | 8.5% |
| GUI behaviour and honesty | ui_behavior, ux_truthfulness | 84 | 8.3% |
| External providers and LLM behaviour | external_integration | 43 | 4.3% |
| Persistence | data_persistence | 34 | 3.4% |
| Spec gaps, performance, other | spec_gap, performance, other | 38 | 3.8% |

### 1.2 Root-cause Pareto

| Root cause | jarvis (524) | nexusiq (250) | gaps (233) | combined (1,007) |
|---|---|---|---|---|
| wiring_integration | 58 (11.1%) | 30 (12.0%) | 70 (30.0%) | 158 (15.7%) |
| deploy_env_config | 58 (11.1%) | 32 (12.8%) | 16 (6.9%) | 106 (10.5%) |
| harness_self | 101 (19.3%) | 2 (0.8%) | 2 (0.9%) | 105 (10.4%) |
| contract_drift | 38 (7.3%) | 33 (13.2%) | 19 (8.2%) | 90 (8.9%) |
| security_privacy | 53 (10.1%) | 3 (1.2%) | 30 (12.9%) | 86 (8.5%) |
| error_handling | 22 (4.2%) | 30 (12.0%) | 16 (6.9%) | 68 (6.8%) |
| state_lifecycle | 26 (5.0%) | 17 (6.8%) | 14 (6.0%) | 57 (5.7%) |
| domain_rule | 30 (5.7%) | 2 (0.8%) | 22 (9.4%) | 54 (5.4%) |
| test_defect | 24 (4.6%) | 25 (10.0%) | 1 (0.4%) | 50 (5.0%) |
| ux_truthfulness | 27 (5.2%) | 6 (2.4%) | 16 (6.9%) | 49 (4.9%) |
| external_integration | 12 (2.3%) | 31 (12.4%) | 0 | 43 (4.3%) |
| ui_behavior | 11 (2.1%) | 20 (8.0%) | 4 (1.7%) | 35 (3.5%) |
| docs_drift | 34 (6.5%) | 0 | 0 | 34 (3.4%) |
| data_persistence | 20 (3.8%) | 5 (2.0%) | 9 (3.9%) | 34 (3.4%) |
| spec_gap | 6 (1.1%) | 5 (2.0%) | 11 (4.7%) | 22 (2.2%) |
| other / performance | 4 | 9 | 3 | 16 (1.6%) |

What the table shows:

- **jarvis product fixes.** Exclude harness, test and docs fixes and 365 remain. Of those, wiring (15.9%), deploy (15.9%), security (14.5%) and contract drift (10.4%) make up **56.7%**. The seam family dominates jarvis's product defects.
- **nexusiq.** The distribution is flat: five classes at 12–13% each (contract, deploy, LLM/provider, error handling, wiring). The external-provider share is nexusiq's own: an LLM-in-the-loop design tuned with prompts.
- **Gaps.** Wiring alone is 30%. Security (12.9%) sits at the edge and at seams: CSP and CSRF, per-route authorization, offboarding. Domain (9.4%) is Purser H1: one concept implemented 2 to 10 times.
- **jarvis components.** `ci` is jarvis's largest component (80 fixes, 15.3%). Adding ci, hooks, docs, status and board gives 137 fixes (26.1%) that landed in process tooling rather than in an app. Purser has 76 fixes, fleet 59, extraction 44, hearth 31.

### 1.3 Origin phase

| Origin | jarvis | nexusiq | gaps | combined |
|---|---|---|---|---|
| implementation slip | 239 (45.6%) | 94 (37.6%) | 63 (27.0%) | 396 (39.3%) |
| cross-component integration | 87 (16.6%) | 51 (20.4%) | 92 (39.5%) | 230 (22.8%) |
| design flaw | 103 (19.7%) | 43 (17.2%) | 56 (24.0%) | 202 (20.1%) |
| harness or test | 64 (12.2%) | 26 (10.4%) | 3 (1.3%) | 93 (9.2%) |
| environment/ops | 22 (4.2%) | 30 (12.0%) | 7 (3.0%) | 59 (5.9%) |
| requirements omission | 7 (1.3%) | 6 (2.4%) | 10 (4.3%) | 23 (2.3%) |

Requirements omission is 2.3%: the operator asked for the right things. For gaps, the spec signal splits two ways. In 117 cases (50.2%) the spec was silent; in 108 (46.4%) it covered the behaviour and the build missed it. The silence was about seams rather than features: which composition root, which identity namespace, which clock, and what renders when a backend is off. The commit fixes show the same pattern:

- 82% of wiring defects (72 of 88) originate at cross-component integration.
- 72% of domain-rule defects (23 of 32) are "implementation slips" in which a new engine re-derived a rule that already had an owner.

### 1.4 Who found them

| Detected by | jarvis (524) | nexusiq (250) | combined (774) |
|---|---|---|---|
| operator using real data | 88 (16.8%) | 124 (49.6%) | 212 (27.4%) |
| agent while building | 115 (21.9%) | 43 (17.2%) | 158 (20.4%) |
| audit sweep | 114 (21.8%) | 10 (4.0%) | 124 (16.0%) |
| code review | 59 (11.3%) | 36 (14.4%) | 95 (12.3%) |
| CI gate | 62 (11.8%) | 2 (0.8%) | 64 (8.3%) |
| runtime crash/log | 33 (6.3%) | 22 (8.8%) | 55 (7.1%) |
| operator UAT | 18 (3.4%) | 6 (2.4%) | 24 (3.1%) |
| e2e/smoke | 9 (1.7%) | 4 (1.6%) | 13 (1.7%) |
| unknown | 26 | 3 | 29 |

All 233 gaps were found after merge. 78 of them were filed within 3 minutes on 2026-09-26 by one whole-repo audit, which ran a repo-wide grep for production callers: a cheap static reachability check the build process never ran on itself. Counting operator, audit, runtime crash, UAT and every gap gives 648 of the 1,007 (64.4%) found after merge by a person or an audit. Automated checks found 77 of 774 commit fixes (9.9%).

Jarvis's operator found fewer defects than nexusiq's. The product was not better. Audit sweeps were standing in for use, and several apps were never mounted for anyone to use: Sherpa on no fleet, Workflows and Marshal pinned off.

### 1.5 Severity

| Severity | jarvis | nexusiq | gaps |
|---|---|---|---|
| wrong result, user-visible | 136 (26.0%) | 120 (48.0%) | 135 (57.9%) |
| crash or unusable | 88 (16.8%) | 54 (21.6%) | 27 (11.6%) |
| security | 70 (13.4%) | 3 (1.2%) | 46 (19.7%) |
| dev/CI only | 208 (39.7%) | 56 (22.4%) | 16 (6.9%) |
| cosmetic/copy | 22 (4.2%) | 17 (6.8%) | 9 (3.9%) |

User-impacting share: jarvis 56.1%, nexusiq 70.8%, gaps 89.3%. The trait that cuts across classes is **silent, plausible failure**, an answer that looks settled:

- LIMIT 2000 silently dropped the oldest 56% of 4,548 ledger rows (88e3a8a592).
- The deriver reported "68 written" while the screen still served 97 (4e6fe7d1f5).
- 132 rows were filed as movement and never surfaced (52ca795a1c).
- "Vault looks empty" had at least five distinct causes.
- The header said ALL QUIET over a 503 (#2238).

### 1.6 Rework and fix-of-fix chains

58.4% of jarvis fixes (306/524) and 69.2% of nexusiq fixes (173/250) are rework of work from the prior one or two weeks. Representative chains:

- **jarvis clock seam, about 7 fixes, each patching one caller.** 5f4bc2a10a, 3c6fd79918, 39226fcfbb, eeae3969c7, 3fa83301f6, 445af1719b, 9ae818e008.
- **jarvis fleet env/compose/renderer, 9 fixes in 7 days.** 16bc6e14c5 … 5ed0b7c8fb. --sync then lost 4 keys (ca0371b19c) and 12 more (82188d5caa).
- **jarvis services vs obligations deriver, 6 fixes.** 7008c6147d, 4e6fe7d1f5, 7554a887e6, b287b0af0a, 71c3a44040, 8a71cbd189.
- **jarvis Azure cutover, 11 fixes after two review rounds.** 4fab171e46 … 42f5e75242.
- **jarvis Circles definer/RLS chain.** 796efcd919 → 8ff9065ea3 → f94163e9bf → 4aa90b53c3 → 61dfead5de. The third fix opened a live tenant-isolation exposure.
- **jarvis phone auth, 6 empty-body fixes in 95 minutes.** e5e95fc231 … 7033f8c7f5.
- **jarvis Sherpa gate B, 5 commits and 2 wrong diagnoses.** One wrong diagnosis was written into CLAUDE.md.
- **nexusiq trade analyst, about 15 prompt commits in two days.** The per-tool cap moved 4→2→4 before af3cd63cf6 moved the work into deterministic code.
- **nexusiq provider layer, about 12 fixes in 12 days.**
- **nexusiq launcher scripts, 8 fixes in 5 days** on PowerShell 5.1, then 4 more on macOS bash 3.2.
- **nexusiq module→agent rename, 9 or more fixes over three weeks.**

## 2. What caught what

### 2.1 CI against escapes

- **CI is a structural filter, not a behavioural one.** It caught 181 distinct real defects in 69 days (about 2.6 a day). About 110 came from structural forcing gates (contract_gate, the identity-handle census, arch_gates, the tenancy binder inventory), about 44 were behavioural and about 17 deploy. The behavioural classes escaped in the same window: domain rules, clocks, error states, UI honesty, wiring.
- **push:master runs no Python suite.** Semantic conflicts between two PRs that were each green reach master and are caught only by the twice-daily schedule. Examples: MappingRegistry.register 'ratified_by' on 08-03 (#482), 55e43ead17, and the ENFORCED/LEGACY conflict on 08-25.
- **The only job that boots the real fleet does not gate anything.** fleet-smoke runs on schedule only and is not in gate.needs. It found that registry_meta was never installed (14 failures, 8 branches), that audit_event ownership was wrong, and the create-role privilege defect. It was then red for 37 consecutive scheduled runs while every master push was green.
- **There is no human review.** The last 300 merged PRs have 0 reviews, and auto-squash is armed when each PR opens. The required `gate` is the only reviewer, and it excludes the one instrument aimed at the largest defect class.

### 2.2 Gate precision (1,000 failed runs)

| Job | Failures | Real product % | Harness/gate % | Other | Verdict |
|---|---|---|---|---|---|
| frontend (typecheck + tests) | 15 | 80.0 | 0 | 13.3 lint | high value |
| image (fleet build) | 8 | 75.0 | 0 | 12.5 infra | high value |
| suite-db | 258 | 60.1 | 3.5 | 21.3 lint, 8.1 inherited | high value |
| checks (ruff/pyright) | 40 | 0 | 2.5 | 97.5 genuine lint/type | hygiene; keep |
| suite (legacy) | 48 | 33.3 | 14.6 | 20.8 inherited | mixed |
| purser e2e walkthrough | 135 | 20.0 | 74.8 | | mixed; 101 failures are one expired-corpus time bomb |
| fleet smoke | 73 | 16.4 | 67.1 | 15.1 inherited | the only boot catcher; not blocking |
| build monolith (Aug 4–9) | 122 | 9.8 | 18.9 | 45.9 lint/policy | mixed |
| generated docs validation | 77 | 2.6 | 92.2 | | noise |
| classify lane | 109 | 0 | 71.6 | 28.4 billing | noise |
| Windows scheduler | 12 | 0 | 75.0 | 25 infra | noise |
| sherpa gate B | 216 | 0 | 99.5 | | noise |
| lint/types/select (Jul 28–31) | 157 | 0 | 0 | ~100 billing | never ran |

By job failure: harness/gate 44.0%, real product 18.7%, flaky/infra/billing 17.5%, lint/policy 14.1%, inherited from master 5.6%. By run: 22.4% of red runs contained a real defect, and 41.1% contained nothing but harness defects.

### 2.3 Red stopped carrying information

- 235 of the 1,000 red runs had the required gate green, and 205 of those were harness-only.
- Between 08-17 and 09-08, 283 of 662 completed PR runs (43%) and 85 of 326 master pushes (26%) were red.
- Every master push between 09-02 and 09-06 (74 of 74) was red, 94% of it from two unrequired jobs.
- **Scheduled runs: 98 of 116 red (84.5%).** The streaks:
  - 37 runs: fleet smoke, three layered causes.
  - 33 runs: a milestone-hygiene step, red while 17,452 tests passed.
  - 6 runs: still open at the end of the data. The purser queue does not settle (10 → 10), hearth credential migration fails, and the fleet is unhealthy.
- The completion gate's constant red hid four real failures (#2496).
- Billing and spend limits stopped 85 runs (8.5%) before any step started. With an empty steps list they read like lint failures.
- **Sherpa gate B was never green before #1962:** 214 failures, 0 successes, 56 branches. Every failure was a text line sitting exactly on its wrap point; none was a product defect.
- **purser-e2e was green for about 110 runs, then went 100% red** when its dated corpus expired on 2026-09-02, because `when_for(None)` reads the wall clock. CLAUDE.md recorded it as "101 of 101, never green", which was wrong. A gate's own history is a report, too.
- **New gates were red from their first day.** The Windows scheduler job failed 7 of 7 master pushes on its first day. The Install Chromium step failed 20 PRs in 2 days. The PR-body and Depends-on policy hit 27 branches in a week.

### 2.4 Earliest catch per root cause (commit fixes, both repos)

| Root cause | n | Cheapest instrument that would have caught it first | Share caught by it |
|---|---|---|---|
| wiring_integration | 88 | boot the real root 42, real-backend e2e 23 | 74% |
| deploy_env_config | 90 | deploy preflight 50, boot smoke 16 | 73% |
| contract_drift | 71 | static types/codegen 27, contract test 26 | 75% |
| domain_rule | 32 | golden real-data diff 23 | 72% |
| ui_behavior | 31 | e2e 22 | 71% |
| external_integration | 43 | e2e 16, seam design review 12 | 65% |
| error_handling | 52 | unit test with a raising stub 30 | 58% |
| state_lifecycle | 43 | unit test under pinned clocks 22 | 51% |
| ux_truthfulness | 33 | e2e 15 | 45% |
| security_privacy | 56 | unit test under the production role 19, seam design review 16, code review 15 | spread |
| test_defect | 49 | mutation-checking the test itself 41 | 84% |
| harness_self | 103 | the gate's own planted-defect test 57 | 55% |

Across all 1,007 defects:

| Earliest catch | Share |
|---|---|
| unit test | 26.7% |
| e2e journey | 13.5% |
| boot smoke against real wiring | 12.9% |
| seam design review | 11.1% |
| contract test | 7.2% |
| deploy preflight | 6.6% |
| code review | 6.3% |
| golden real-data diff | 5.7% |
| static types | 4.7% |
| acceptance criteria | 3.1% |
| not preventable | 1.2% |

## 3. Did the documents help?

### 3.1 Spec traces: 117 defects traced to the document in force

| Area | Words audited | Traces | Correct, build missed | Right intent, not falsifiable | Spec prescribed the defect | Silent / no spec |
|---|---|---|---|---|---|---|
| Purser | ~206k (incl. 70k in issues) | 28 | 8 | 6 | 4 | 10 |
| Other jarvis apps | ~485k | 31 | 10 | 6 | 4 | 11 |
| Platform | ~593k | 32 | 8 | 8 | 5 | 11 |
| nexusiq | ~497k in scope (635k total) | 26 | 4 | 1 | 7 | 14 |
| **Total** | **~1.8M** | **117** | **30 (26%)** | **21 (18%)** | **20 (17%)** | **46 (39%)** |

**Correct, missed by the build:**
- PRD F6's runway formula has four inputs; the build shipped two for a month (7de1a0348f, 5857575cd5).
- A paginated read contract was specified, and Transactions capped at 500 rows (#2220).
- ADR-0001 required transaction-scoped tenant binding, and three sites bound at session scope (1a691e7475).
- The never-call-fetch rule had no lint, and the Ask drawer called fetch (#2225).
- nexusiq's TaskStateStore signature was in the spec and wrong in the code (c68025a01a).

**Right intent, not falsifiable:**
- Circles' "migration rehearsal" was a checklist word, not a step (0272d9dc40).
- "Own WebAuthn rp for fleet origins" cannot fail a test (7f98347cd3).
- Desktop-root parity acceptance named two hand-picked fields (#2118, which led to #2270 and #2357).
- Platform R5's "done = delete the allowlist row" is discharged by any import.

**The spec prescribed the defect:**
- nexusiq v2.2 §14.1's event-name table (f8ec8f0a10) and §6.4's subprocess contract (4c6197e890).
- nexusiq's skill-first manifesto, which put fetching and saving into prompts (af3cd63cf6).
- The Hearth handoff literals, plus a design-partner rule to "reuse the Larsen household" (f54578e266).
- The assistant design's "no mapping function to write" (#2244).
- The scheduling design recorded the envelope tenant as intended behaviour (#362, f222ae1d9b).
- ADR-0001's "unbound means NULL means zero rows" was false after RESET (18bc907fd2).
- 'WIRES AT Rn' chips in the household UI (#2217).
- The trips-rulebook R5.5 booking-number fallback (#2222).
- A design claim that refresh_all runs on every ingest; it does not (#2267).

**Silent:**
- No document distinguished data frontier, wall clock, pinned as-of and household timezone. "Wall clock" has 0 hits across the Purser PRD, design and GUI design.
- No document required root parity, a single owner per concept, a feature-off screen state, or per-route authorization.

Only 26% of the traces were a correct, testable spec that the build missed, and even there the missing piece was enforcement, not more words.

### 3.2 Effort against outcome

- **Purser:** about 127k words of markdown. design.md is 70% amendment log (24.9k words) and the PRD 32% preamble. The 80 fixes and 79 gaps landed somewhere else: domain re-derivation (36), wiring (31), UI honesty (14), clocks (12).
- **Other jarvis apps:**
  - Sherpa has about 60k words and is mounted on no fleet (#2245).
  - Workflows (about 52k) and Marshal (about 18k) are pinned off on every fleet (#2247).
  - Pulse has about 60k words, and its index still says "nothing has shipped" after R1 and R3 closed.
  - 23 dossier stage files are unfilled template stubs.
- **Platform:**
  - The resource dossier is 153k words over 47 files for about 10k LOC: 15 words per line, across seven design revisions.
  - The federation design is 40k words, with 15 commits on one day (review rounds 7–12).
  - 75 of 190 dossier files are placeholder stubs.
  - 17 ADRs say Proposed, or have no status, while implemented.
  - 105 of 160 platform defects landed in July, the month of the heaviest frozen-design writing.
- **nexusiq:**
  - About 635k words for about 101k LOC (roughly 5 words per line), and 25% of commits are fixes.
  - 111 of 125 dated defects predate the entire 309k-word superpowers spec corpus.
  - Four hand-maintained status trackers carried false checkmarks.
  - Commits fell from 615 in April to 11 in July, and the project was abandoned.
- **jarvis superpowers folder:** 64 documents and 138k words. 59% is about CI, docs, the board or deploy tooling, and 24 of 29 specs were never referenced again.

### 3.3 What in the documents worked

- **Threat models verified against code with file:line.** The egress PRD §0 found the live hop-0 SSRF and the concurrent double write before implementation (7cda17ba5d, 961f489b71).
- **Reconciliation against the built code.** Dataplane A3's "promises with no enforcing code" found TURN_REGISTER_LIMIT in 0 .py files and AC10 unwired.
- **Rule tables with test cases.** trips-rulebook §15 has Measured-on and Refused-by cases for each rule and an explicit debt count.
- **An oracle per lane.** The PRD F21 tie-out kept parser defects near zero, and bounded the sign fix in 83f2eeec9e with "all 144 statements tie".
- **A known-open finding kept as a strict-xfail test.** The two-lease ADR did this, and the test flipped to pass when the hole was fixed (290fad99b0).
- **An audit against code with a wiring matrix.** Nexusiq's 2026-04-10 audit found 9 CRITICAL dead components behind 470 green tests.
- **Mechanical success criteria.** "git grep returns zero" closed the nexusiq rename after 9 or more fixes.
- **"DONE = THIS DEMO" on real input.** Ontology R1–R5 each closed in one or two days; Tenancy R1 closed in 13.
- **The audit-filed issues #2216–#2248.** Each gives evidence, a search scope, a falsifiable done-when, and "which gate should have caught this". They are the best specs in the corpus, and they were written after the build.

### 3.4 What was noise

No classified defect traces to the presence or absence of any of these:

- Unfilled stage stubs.
- Overlap and OSS-alternative scans.
- Per-revision snapshot files.
- Freeze ceremonies and review logs kept inside designs.
- Hand-maintained status fields.
- Implementation plans containing full code: tenancy's 17.6k words for five PRs; nexusiq's 6.4k-word plan for one partial unique index.
- Vanity success metrics.
- Manifestos.

## 4. The harness: apex and jarvis's own process

### 4.1 Enforced against prose

| Layer | Size | Blocking | Advisory | Prose only |
|---|---|---|---|---|
| jarvis CLAUDE.md | 9,160 words (~15k tokens); cut to 1,962 on 08-14, regrown to 82% of its old size | 5 of 32 bold rules | 5 | 22 |
| jarvis repo hooks | 19 scripts | 8 deny hooks, all guarding tool-call hazards: secrets, shell footguns, git state, session pickup | 11 | n/a |
| loop rules (one front, claim, done-when, design before code, review before commit, retro) | n/a | 0 | claim, templates | the rest |
| jarvis memory | 427 notes, 232k words | 0 | freshness nag | all; 21% anchored |
| jarvis ci/ | 76k Python lines; ~92k lines of enforcement, more than apps/extraction's 60k | the gate | schedule lanes | n/a |
| apex plugin | 45 skills, 17 commands, ~13 hooks | scan-secrets (0 blocks in 16,276 writes); guard-destructive (33 blocks, mostly false positives) | primer, nudges | all skills |

The jarvis-specific context a session loads before doing anything is about 21–24k tokens. Median first-turn context rose from 86k to 105k tokens as CLAUDE.md regrew.

### 4.2 What demonstrably worked

- **Deny hooks on tool hazards:**
  - pipe_mask_gate: 720 denials in 229 sessions.
  - secret_env_gate: 95 denials in 47 sessions, after a live key leaked twice.
  - secret_file_touch_gate: 26 denials, 21 of them inside subagents.
  - heredoc_write_gate: 23 denials.
  - stash_gate: added after a session broke the prose rule four turns after quoting it.
- **claim_before_edit.** The share of edit sessions that claimed their work rose 58% → 82% → 90% (n = 238 / 60 / 39). It fires at the first edit and asks for one command.
- **Structural census tests in suite-db.** contract_gate (38 failures, 27 branches), handle census/read-cut (35, 21), arch_gates (25, 23), tenancy binder inventory (9 branches). Most of CI's 181 real catches come from these.
- **The wire contract baseline gate:** the clearest contract-first win.
- **Cold two-voice adversarial review.** The pattern ran in 49 of 300 agent dispatches; the apex skill for it was called twice.
  - #2413: 46 reviews, 13 must-fixes, 9 distinct defects.
  - #2223: a design pair before code, 24 findings, 3 defects.
  - #2429: caught a grant spent before attestation was verified.
  - #1580: two independent STRIDE passes found three issues neither held alone.
- **python-review before commit.** #2159 found 4 defects, including a broad except filing a TypeError as a provider outage. #2170 found 5.
- **Moving an unread signal to where it is read.** The finished_milestones SessionStart hook replaced a CI step that had failed 20 of 20 runs unread. run_triage.py has 168 uses.
- **The Stop nudge** has 44% follow-through, the only apex hook with measurable follow-through.

### 4.3 What never fired, or became noise

- **The apex primer was delivered 373 times.** On 2026-09-18 the operator still had to ask why apex was not being followed, after a 34-file slice shipped unreviewed.
- **Apex workflow nudges were rarely followed.** Phase-gate nudges: about 13% (6 of 45). The discovery_dossier nudge: 1 of 19. Apex commands typed by hand: 0 of 17 in 241 sessions.
- **Three apex path hooks are inert on Windows.** 98.3% of Edit/Write paths use backslashes. 73 dependency-manifest edits, 166 API-surface edits and 116 workflow edits produced 0 nudges. The hooks fail open, so a dead hook looks healthy.
- **pr_body_check was blocking for 9 days.** It was removed (#1023) after 49 `--admin` merges. The release skill and mechanism_table.py still say it refuses PRs, while test_ci_lanes.py:1366 pins that it does not run.
- **milestone_completion_gate was red on 20 of 20 scheduled runs** and nobody read it. It hid four real failures.
- **Overrides were used routinely.** session_pickup_gate was overridden in 17 of the 20 sessions it denied. The pipe-mask override token appears 1,564 times, in 17 sessions.
- **retro_due posted 405 notices of a debt nobody can pay.** The retro skill runs in 35–44% of edit sessions.
- **The graph-first mandate is followed on about 5% of searches,** while 58,325 graph updates each cost a median of 0.93 s.
- **session_output_gate never fired.** Memory anchoring reached 21% after seven weeks.
- **Apex's build-side ambitions stalled:**
  - agent-rails (machine-decidable freeze state) was designed and frozen on 2026-06-11 and never built.
  - The six wave-1 skills have 0 uses in jarvis.
  - The apex-port copies have drifted 88–450 changed lines from jarvis's copies.
  - Apex has had no commits since 08-15.
- **Coverage holes in the hooks themselves:**
  - Hooks are branch-local. A repair reaches only sessions whose worktree branch already contains it.
  - 11 of 12 Bash-matcher hooks do not wrap the PowerShell tool, which carried 26 of 40 git push and gh pr commands in October.
  - A memory note recommends PowerShell as the workaround when a hook errors.

### 4.4 The harness as a defect source

101 jarvis real fixes (19.3%) are harness_self. The docs render train produced 186 CI job failures and 0 product defects, and one of its bot PRs failed 58 times over 24 days.

The cycle repeats:

1. A gate lands without ever having been green.
2. It is red from its first run.
3. People learn to ignore red.
4. A real failure hides behind it.

CLAUDE.md already says a new gate ships with its planted defects and its false-positive rate measured first. That rule is prose, and the CI data shows it was not applied.

## 5. Same mistakes twice: nexusiq (Feb–Jun 2026), then jarvis (Jul–Oct 2026)

| Failure | nexusiq | jarvis | Written down before jarvis started? |
|---|---|---|---|
| Built but not mounted | Steps 37–45 had 900+ green tests and dead wiring; ca0977324a (merge clobbered endpoints), 233a1a89e0, c5e02130e1 (`callable=lambda: None`) | e854e76289 (sub-app lifespans never ran), c26832080a (empty worker topics), #2245 (Sherpa on no fleet), #2270 (desktop has no schedules), #2348 (1,175 lines with no caller); 63 built-not-wired gaps | Yes: TDD_PROCESS_RETROSPECTIVE.md on 2026-02-21, and an 8-point Wired checklist in CLAUDE.md, both prose |
| Free-text contracts drift | event names (f8ec8f0a10, 7 modules); run() then TOOL_DEFINITION across 4 rounds | health vocabulary b2b8b3de0b + 1f6541bc0c; authority vocabulary 79a91bae01, 8d8eaccdb1; Marshal 6 of 10 signals 9b5a638bab | Partly; jarvis's wire freeze fixed it only where applied |
| Config owned in N places | port 8000 vs 9001 (67de17ab29, 641b093ad9, 1ce78a5ba9); tracked config flip-flops (60cfe71bf6 → 9db68ed327) | renderer/compose/validator/settings: 9 fixes in 7 days; --sync lost 4 then 12 keys | No |
| Mocks and fixtures pass, the real thing fails | e2a9040a26 (mocks green, live Ollama 400); c22544ceb2 bent a test to match the bug | superuser test role hid RLS (605eb1fc10, #2414, #2419 P0); a mock faked FLOWERING → LIVE (6bd453e533); a fixture handed in the schedule member (aa35c6f224) | nexusiq LEARNINGS Rule 8, prose |
| Failure rendered as empty or success | a3331425ec ("silently failed all agent executions"); a78a32f95a (false empty state) | #2240 (42 of ~90 load sites ignore errors); #2238; vault looks empty from 5 causes | No |
| Prose rule with no gate | "full suite green" with no PR CI for 7 weeks; `status != 404` still appears 64 times at HEAD | 22 of 32 CLAUDE.md rules prose-only; stash rule broken 4 turns after being quoted | Both repos wrote this lesson down |
| Narrative fix before the mechanism | flight routing: a prompt rule and a regex (59e15ea46f, b7dfec20f9) before the discarded-events root cause (2641678a20); trade analyst ~15 prompt commits | Sherpa gate B: 5 commits, 2 wrong diagnoses, one written into CLAUDE.md | No |
| Hand-kept status, wrong | 4 trackers with false checkmarks | status yard 31% stale; one stale prompt built CO6c three times; Pulse says nothing shipped | No |
| Production build path first run at release | 5 Docker/release fixes (c274fcf270, 55f87dcb0b, 244659b4af, 22cbda731b, d634e2d733) | Azure cutover: 11 fixes after two review rounds | No |
| Real-input logic tuned by trial | studio planner: 7+ fixes in one day | Purser naming flow: 4 fixes in one day; obligations deriver: 6 fixes | No |
| Rework share | 69.2% | 58.4% | n/a |

**What changed between the repos, and what did not.** Jarvis added CI, deny hooks, structural census gates and adversarial review. The results:

- CI-detected fixes went from 2 to 62.
- Security defects moved from being found by users to being found before merge; most of jarvis's 53 security fixes were latent and found by review.

The seam family did not move:

- nexusiq: wiring, deploy and contract drift are 38.0% of fixes.
- jarvis: they are 42.2% of product fixes.
- gaps: they are 45.1%.

Jarvis also added a new top class, its own harness, at 19.3%.

## 6. Ten lessons, ranked by share of defects addressed

Shares are against the 1,007 pool. Lessons 1, 2, 4, 5 and 7 use the earliest-catch basis; lessons 3, 6, 8, 9 and 10 use root cause or gap kind. Shares overlap.

1. **The cheap test was missing, or written to pass (26.7%: earliest catch is a unit test in 269 cases, 85 of them harness, test or docs fixes).**
   - Examples: self-supplied preconditions (4324b7e6ce), superuser rigs (605eb1fc10, 61dfead5de), fixtures that fabricate shapes (aa35c6f224, be15ae3325), a test bent to the bug (c22544ceb2), and `status != 404` assertions.
   - Fix: a test of a guard ships with a planted mutant. The production DB role is the default. Identity is printed beside the result. Fixtures exceed every limit and assert what actually landed.
2. **Boot every real composition root on every PR (19.5%: boot smoke 130 plus deploy preflight 66).**
   - Every app flag on, the production DB role, migrate from the previous release, boot twice, and one request per route, nav item, schedule and handler.
   - Make the job required. fleet-smoke already finds this class, and it gates nothing.
3. **Treat the harness as product (15.4%: harness_self 105 plus test_defect 50; 44% of CI job failures).**
   - A gate merges only with a planted defect, a measured false-positive rate, a case from outside its own list, a test on the developer's OS and shell, and a date by which it is required or deleted.
   - A red unrequired job escalates automatically.
4. **Drive the real UI against the real backend (13.5%: e2e 136).**
   - Click every control and assert its effect survives a reload.
   - Test a screen-by-state matrix, 375 px width, and back/reload. Grepping for reachability does not count.
5. **One declaration per cross-component identifier (11.9%: contract test 73 plus static types/codegen 47).**
   - Use generated clients and enum registries, with bidirectional emit/subscribe tests.
   - Derive env lists from one source. Unmatched identifiers raise; they do not fall back.
6. **Make failure a type (11.6%: error_handling 68 plus ux_truthfulness 49).**
   - Load hooks return a result whose error branch must be handled. No `?? []`, and no prototype simulation as a catch fallback.
   - Every UI claim ("all set", "ALWAYS ON", "ALL QUIET") cites the production event that makes it true.
7. **Review seams before freeze, against code, with two cold voices (11.1%: seam design review 112).**
   - Keep a seam table: the value, who stamps it, who trusts it, and the test that holds it.
   - Cap reviews at two rounds. Design review against documents has no stopping point; review against code does.
8. **Built is not done (11.1%: gaps built not wired 63, never built 25, fake 24).**
   - Name the production caller, with a test that fails when that call site is deleted.
   - Write acceptance that names the door. Attach a demo artifact produced at the closing SHA.
9. **Real-data oracles, one owner per concept, one clock (11.0%: domain_rule 54 plus state_lifecycle 57).**
   - Run cross-surface parity over a planted ledger in CI, and a local real-data checker before any milestone closes.
   - Keep a concept registry with an arch gate, and pass time as a typed Clock.
10. **Stop writing prose with no gate (3.4% docs_drift directly).** In 17% of the spec traces the document caused the defect, and 22 CLAUDE.md rules have no effect that can be measured.
    - A lesson enters prose only together with its gate.
    - CLAUDE.md gets a word ceiling enforced by a test.
    - Status is generated or deleted.

## Caveats

- **Classification.** Classifications are heuristic, one label per item. Compound commits that bundle 2–4 defects get one label. About 20 nexusiq shas are duplicate twin commits; is_real_fix filters them where they were flagged. earliest_catch is a judgment of the cheapest instrument, not a proof.
- **CI coverage.** The GitHub list API cap means there are no CI failures before 2026-07-28. About 5% of CI attributions are ambiguous: purser locator timeouts, one Gate B "dashboard" red, and a fleet "unhealthy" with no logged cause.
- **Transcript and table data.** Transcript-based counts come from one machine. Mechanisms-table figures are self-reported by the authoring session.
- **Unverified references.** Shas and issue numbers are cited from the upstream classifiers and audits, and were not re-fetched here.
