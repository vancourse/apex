# Draft B — Scaffold first: the process is whatever the kit's CI enforces

Designer B, 2026-10-05. Inputs: `design-brief.md`, `evidence_report.md`, `coverage_matrix.json`, `process_requirements.json`, `anti_patterns.json`, `transcripts_report.md` / `transcript_implications.json` / `transcripts_dedup.json`, `ci_analysis.json`, `harness_inventories.json`, `doc_audits.json`, the three research briefs. Shas and issue numbers are quoted from those files, not re-fetched. No household figure, account, merchant or person name appears here.

---

## 1. Thesis

The 1,007 escaped defects are 35% seams, 19% the harness breaking itself and 18% logic that re-derived a rule it did not own or read the wrong clock; almost none were requirements the operator failed to state. Prose caught none of it (22 of 32 CLAUDE.md rules prose-only; 37% of corrections repeated a written rule; apex nudges followed 13% of the time). What worked fires at the moment of a cheap action or blocks a merge. So the process here is not a document a session reads; it is a **starter kit** whose layout, generated code and CI make the right structure the only one that compiles, boots and merges: one schema source generates wire, typed client and settings; the real composition roots boot in a required job; every screen has a state matrix and a result-typed loader; every domain concept has one owner and a gate; the catalogue and the status are generated or absent. A plugin (`rails`, the reworked apex) binds the session to that structure through a dispatcher that wraps Bash *and* PowerShell, normalises backslashes and announces its own absence, and a one-page contract resolves the rules that conflicted. What the kit cannot carry — what to build, the household's ground truth, whether a seam deserves a design — is named, kept to a 1,500-word CLAUDE.md, and bound at its edges by an intent file the first commit requires and a walk artifact the end of the turn requires. Every mechanism names the facility that makes it fail, its cost per PR and the defect it cites; one that cannot fail, or has no citation, is deleted by a test.

---

## 2. The process on one page

Each step names its gate. A gate is one of four things that can fail: a `PreToolUse` deny (exit 2 or `permissionDecision: deny`), a `Stop` block, a GitHub required check (`gate`), or a git hook. Everything else is stated as prose and marked so.

0. **Session start.** `rails_state.py` (SessionStart) prints ≤600 tokens of *state*, no prose: your claim, the one active front, your open PR and its CI state, receipts pending, finished-but-open milestones. *Gate: none — SessionStart cannot block. Budget is enforced by `ci/test_context_budget.py` (step 12).*
1. **Claim.** `rails claim <#issue|milestone>`. The claim store (`_claimstore.py`, in `CLAUDE_CONFIG_DIR`, keyed on the main checkout) refuses a second app in state `building` while the first has no `used` receipt (layer 6 WIP limit). *Gate: `claim_before_edit` stays advisory at the first Edit (measured 58→90%); the WIP refusal is a hard exit in `claim.py`.*
2. **Read intent back.** Before the first commit on a branch, write `.rails/intent/<branch>.md`: Building / Not building / Retired paths that stay dead / Screen of record (file, with precedence statement) / Acceptance lines, each with `door:` and `instrument:`. The agent writes it from the issue, the milestone demo and the operator's words; the operator corrects the file, not the chat. *Gate: `PreToolUse Bash|PowerShell` denies `git commit` on a branch with no intent file (first commit only); the PR body embeds the file.*
3. **Spec only when ambiguous.** If the solution is not obvious from the intent file, write `docs/<app>/spec.md` (one page, acceptance lines a test could fail) and, for a seam or trust boundary, the two-page `design.md` (Walls / Seams / Roots / Clocks / Concepts / Route×actor matrix). One authoring pass, one cold two-voice pass, then build. *Gate: `acceptance_check.py` (reworked) refuses `gh pr create` whose `Closes #N` issue has an acceptance line missing `door:` or `instrument:`, or whose instrument is `mock | dev-login | standalone | superuser`.*
4. **Walls first.** The first commit of a new seam adds its declaration: a Pydantic model in `contracts/`, a row in `settings.toml`, a row in `auth_matrix.toml`, a row in `rules/registry.toml`, a root entry in `roots/registry.py`. *Gate: the `checks` job fails on codegen diff, settings parity, unlisted route, re-derived concept, or a root missing a seam.*
5. **Build, test red first.** Tests run as the production role by default (`conftest.py`); fixtures come from `fixtures/planted/` (two households, non-UTC, every count above every default limit, landed-count asserted); engines take a typed `Clock`. *Gate: `suite` job; `clock_gate`, `concept_gate` in `checks`; `mutate-changed` job on touched files.*
6. **Validate locally.** `rails check` runs `pre_pr_check` (lint, types, codegen diff, settings parity, gates, selected tests, touched-file tests on the `git merge-tree` of `origin/master`), and on UI or server paths `rails walk` drives the real build against a throwaway Postgres and writes `walk/<sha>/steps.json` + frames. Both write receipts to `.rails/receipts/<sha>/`. *Gate: `Stop` hook `turn_end_gate.py` blocks a done-shaped or offer-shaped ending with no receipt for HEAD; `PreToolUse` denies `gh pr create` with no `check` receipt for HEAD.*
7. **Ship, no ceremony.** `rails ship` pushes, opens **one** PR per worktree (a second open PR from the same claim is denied), fills the body from the template (Intent, Walk link, Mechanisms table generated from receipts), arms `--auto --squash`, binds the PR monitor so the *session* wakes on red or conflict. The operator's only word is `hold`. *Gate: `PreToolUse Bash|PowerShell` deny on a second `gh pr create`; `git push` is not consent-gated (the push-consent `.githooks` gate is deleted, see §6).*
8. **CI judges.** `gate` is the sole required check (`if: always()`, passes on `success|skipped`). Jobs: `checks`, `suite`, `frontend`, `walk`, `boot`, `mutate-changed`, `image`, plus the per-repo extras. Path filters keep the expensive jobs off PRs that cannot affect them. *Gate: GitHub ruleset `required_status_checks: [gate]`.*
9. **Review where it pays.** PRs touching seam paths (`contracts/`, `settings.toml`, `roots/`, `auth_matrix.toml`, `migrations/`, `*/routes/*`, `deploy/`) get a cold two-voice review (cooperative + adversarial, fresh contexts, diff plus primary artifacts, two rounds max, judged against code). Must-fixes land as commits before auto-merge fires. Other PRs get `python-review`/`typescript-review` before commit. *Gate: `PreToolUse` denies `gh pr merge --auto` on a seam-path PR with no review receipt.*
10. **Deploy with a preflight.** `rails deploy <target>` runs `deploy/preflight.py` (every `settings.toml` name present in the rendered env, no extras, image digest = merged SHA, migration head, role posture) then `up`, and comments target/SHA/time on the PR. *Gate: preflight non-zero refuses `up`; the same preflight runs inside `boot`.*
11. **Accept = used.** The operator does one real task on the named target. `rails accept <milestone> --target <t> --sha <sha>` records it; `rails oracle` runs the rule table over the operator's real store locally and writes `rule_id, row_id, pass` (never a value) to `.rails/oracle/<sha>.json` (git-excluded). *Gate: `rails close <milestone>` refuses without both receipts; a scheduled reporter flags any milestone closed by hand without them (report at SessionStart, not a red nobody reads).*
12. **Retro into the ledger.** One finding, routed gate > hook > drop. A new hook, gate or template gets a row in `rails/ledger.toml`: defect cited, planted-defect test, FP count on the tree, Windows fixture, `required_by` date. *Gate: `ci/test_harness_ledger.py` fails on a row missing any field, a job past `required_by` still unrequired, or a hook with no firing in 60 days.*

That is the loop. It is shorter than jarvis's not because it has fewer ideas but because steps 4, 5, 8, 10 and 12 are enforced by files the kit already contains.

---

## 3. Mechanism catalog

Columns: name · layer · kind · stage · enforcement · prevents (root causes / operator-caught classes) · facility · cost per PR · Windows · exists in. "Deny" means `PreToolUse` returning `permissionDecision: deny` with the reason naming the alternative; "required" means in `gate.needs`.

| # | Name | L | Kind | Stage | Enf. | Prevents | Facility | Cost / PR | Win | Exists in |
|---|---|---|---|---|---|---|---|---|---|---|
| M1 | **`rails_hook.py` dispatcher** | 8 | hook | all | n/a (carrier) | 3 inert apex path hooks; 35 missing-script blocks; 11/12 Bash gates not wrapping PowerShell | one `PreToolUse` registration per matcher (`Bash\|PowerShell`, `Edit\|Write\|MultiEdit`, `Read\|Grep\|Glob`), `Stop`, `SessionStart`; routes to `hooks/gates/*.py`; missing gate → `additionalContext: "RAILS: gate X missing at <path>; proceeding unguarded"`, exit 0; `file_path.replace("\\","/")` before any match | 1 Python process per tool call (~150 ms) instead of up to 12 | yes — the point of it | new; absorbs `_hooklib.py` (apex + jarvis) |
| M2 | **Codegen gate** (`rails codegen` + `ci/codegen_gate.py`) | 1 | codegen + ci_gate | build/merge | blocking | contract_drift 8.9% (27/71 static types); #2326 (23 routes bypass response_model); b2b8b3de0b/1f6541bc0c vocab drift | Pydantic `contracts/*.py` → `contracts/wire/frozen.json` (JSON schema) → `frontend/src/gen/{types,client}.ts` (openapi-typescript over FastAPI's OpenAPI, `response_model` required by `ci/test_routes_typed.py`); `checks` job runs generator and `git diff --exit-code`; `wire_contract_baseline_gate.py` diffs merge-base `frozen.json` additive-only | 5–20 s | yes | jarvis `ci/wire_freeze/`, `contracts.ts`, `wire_contract_baseline_gate.py` (keep); client generation new |
| M3 | **Settings declared once** (`settings.toml` → `settings.py`, compose env, renderer manifest, validator) | 1 | codegen + test_pattern | build/merge | blocking | deploy_env_config 10.5%; 9 env fixes/7 days; `--sync` lost 4 then 12 keys; RP id never forwarded; #2234 name collision | `rails codegen` emits pydantic-settings (`extra="forbid"`, required fields required); `ci/test_settings_parity.py` asserts app-read names = compose-forwarded = renderer-written, no `${VAR:-}` for a required var, no name collides with a platform var; in `checks` | <1 s | yes | new; replaces `fleet_secrets.py` / `fleet.py` validator lists (hand-kept) |
| M4 | **Boot smoke, required** (`ci/boot_smoke.py`, job `boot`) | 1 | ci_gate | merge | blocking | wiring 15.7% (42/88 + 41 gaps); e854e76289, c26832080a, d1ad2720b1, #2245, #1064, #2315 Null in prod; data_persistence 10/25 | Boots every root in `roots/registry.py` from the built image, all flags on, as `app_role` NOSUPERUSER NOBYPASSRLS via the production factory, migrates from the previous release tag, boots twice, one request per route/nav/schedule/topic; fails on 5xx, 404 for a registered route, `text/html` on `/api/*`, schedule or topic with no handler, any root composing a Null/no-op seam; asserts CSP/nosniff/Origin refusal; in `gate.needs`, path-filtered to `apps/ toolbox-* runtime/ deploy/ compose*` | 3–5 min runner on those paths; 0 otherwise | n/a (CI Linux); local `rails boot` works under Docker Desktop | jarvis `ci/fleet_smoke.py` (rework: add migrate-from-previous, boot-twice, schedule/topic census, make required) |
| M5 | **Root parity, generated** (`ci/test_root_parity.py`) | 1 | test_pattern | merge | blocking | #2270, #2357, eeae3969c7, #2303, #2295, #2306; anti-pattern "second root without derived parity" | Introspects the fleet root's config fields, Protocol seams, schedules, env names; fails when any other root in `roots/registry.py` omits one not listed in `roots/exclusions.toml` (reason + date); hand lists do not satisfy | <1 s | yes | new |
| M6 | **Reachability catalogue** (`rails catalogue` → `docs/catalogue.json` + `.html`; `ci/test_reachability.py`) | 5, 1 | codegen + ci_gate | merge | blocking | built-not-wired 63 gaps; #2348 (1,175 lines, 0 callers); #2400/#2404 re-export orphans; #2359–#2364 levers with no caller; anti-pattern "satisfied by any `__init__` import" | Walks imports *and call sites* from each root in `roots/registry.py`; a module/route/lever with zero production callers fails unless in `catalogue/unreached.toml` with `expires:`; committed catalogue must match regenerate (`git diff --exit-code`); `reuse_inventory.py` reads it | 5–15 s | yes | jarvis `anatomy.json`, `CAPABILITY_CATALOG.md` (replace: generated, never hand-edited), arch gate `modules-are-consumed` (delete: wrong evidence) |
| M7 | **Production-role test default** (`tests/conftest.py`) | 1 | test_pattern | build | blocking | security 8.5% (19 catchable under prod role); 605eb1fc10, 02feadf311, #2414/#2419 P0, 18bc907fd2, the 2026-08-19 superuser probes | `db` fixture = Testcontainers Postgres created as owner, connected as `app_role` through the production factory; `superuser` fixture requires `@pytest.mark.superuser(reason=)`; every security/tenancy test prints and asserts `current_user, rolsuper, rolbypassrls, app.tenant_id`; `ci/test_no_unmarked_superuser.py` fails a DSN string with the superuser role outside the marker | +5–20 s per session | yes (Docker Desktop) | jarvis has 24 files asserting posture; make it the default (new conftest) |
| M8 | **Auth matrix** (`auth_matrix.toml` + `ci/test_auth_matrix.py`) | 1 | test_pattern | merge | blocking | #2229, #2235, #2384, #2379, #2381, #2359–#2365 offboarding; anti-pattern "category STRIDE instead of per-route matrix" | Route list generated from the composed app at test time; every route must have a row (actor × call/mint/list/revoke/for-whom) or the test fails; parametrised 401 for anonymous, 403 for other-member; member-removal test asserts grants, devices, pairings, schedules, links gone | <1 min | yes | new; replaces design §7 category STRIDE |
| M9 | **Typed clock + clock gate** (`toolbox_clock.Clock{Frontier,Wall,PinnedAsOf,MemberTz}`; `ci/clock_gate.py`; ESLint `no-restricted-globals`) | 1 | code + ci_gate | build | blocking | state_lifecycle 5.7%; clock seam fixed ×7; #1892 (101 reds), #2232, #2286, #2287 | AST gate forbids `datetime.now/utcnow/date.today/time.time` and `Date.now()/new Date()` outside `*/clock.py` and `src/lib/clock.ts`; engines accept a `Clock` parameter with no default; `boot` asserts which clock each root composed; every dated corpus pins as-of in server and runner env via `settings.toml` (one name) | <1 s | yes | new (jarvis `when_for(None)` reads the wall clock) |
| M10 | **Result-typed loader + state matrix** (`src/lib/load.ts`, `src/lib/state.ts`, `screens/*/states.test.tsx`, ESLint rule) | 1 | code + test_pattern | build | blocking | error_handling 6.8% + ux_truthfulness 4.9%; #2240 (42/90 sites), #2238, #2241, #2213, #2219, #2218 | `useLoad` returns `Result<T, LoadError>`; `eslint-plugin-neverthrow/must-use-result` + a rule failing `?? []`/`?? 0`/`?? "ok"` on a load result; `ScreenState` discriminated union `loading\|loaded\|empty\|failed\|write_failed\|unauthenticated\|disabled_503\|not_composed\|partial`, exhaustiveness lint; `rails new-screen` emits `states.test.tsx` driving a stub client that rejects/503s/times out and asserts visible text per state, at 375 px, with back/reload | lint 2 s; matrix 1–2 min in `frontend` | yes | new; Purser `design-gui.md §6` specified it in prose |
| M11 | **Real-backend walk** (`e2e/walk.mjs`, job `walk`) | 1, 9 | ci_gate + script | merge/verify | blocking | e2e earliest catch 13.5%; #2251, #2227, #2249, #2217 (dev vocabulary on household screens); 208 operator catches of done-claims | Playwright against the built bundle served under the real mount, real Postgres, pinned clock; clicks every control from a `controls.json` generated from the screen registry, asserts text and effect after reload; `NOT_FOR_A_HOUSEHOLD` vocabulary ban; writes `walk/<sha>/steps.json` + frames; required on `frontend/** OR apps/*/src/**`; text assertions only, never pixels | 2–6 min on UI/server paths | local needs a `.cmd` wrapper and `Win32_Process Create` (documented traps) | jarvis `apps/purser/frontend/e2e/walkthrough.mjs` (keep shape; generalise); delete `sherpa-geometry` (216 reds, 0 defects) |
| M12 | **Concept registry + gate** (`rules/registry.toml`, `ci/concept_gate.py`) | 4 | ci_gate | build | blocking | domain_rule 5.4%; income ×4, frontier ×6–7, month arithmetic ×8–10, rounding ×10, kinds ×9; 4d4c7e8ade, 0789605f06, 79f9595900 | Each row: concept, owning function, pinning test; AST gate fails arithmetic on period strings, a private `KINDS = {...}` set, `Decimal.quantize` or currency conversion outside the owner; includes a case from outside its own list (planted) | <1 s | yes | new; Purser H1 (milestone 74) census is the seed |
| M13 | **Planted ledger parity + local real-data oracle** (`fixtures/planted/`, `ci/test_surface_parity.py`, `rails oracle`, `.rails/ground-truth.toml`) | 4, 6 | test_pattern + script | build/accept | blocking (CI) / blocking at close (local) | golden real-data diff 5.7% (23/32 domain fixes, 36/159 Purser); #2540, #2215 ($0-satisfiable), 83f2eeec9e; 102 wrong-domain-fact corrections | Every user-visible figure declares an oracle in `rules/registry.toml` (`= sum(drill_rows)`, `= surface X`); CI runs parity over the planted ledger; before close `rails oracle` runs the same checker over the operator's store and writes `rule_id,row_id,pass` only; `.rails/ground-truth.toml` (git-excluded, `.git/info/exclude`) holds operator-stated invariants ("non-zero", "equals", "never negative") the oracle reads | CI 10–30 s; local ~1 min per close | yes | new; jarvis PRD F21 tie-out is the one-lane precedent |
| M14 | **Fixture rules** (`ci/test_fixture_rules.py`) | 1 | test_pattern | build | blocking | 88e3a8a592 (LIMIT 2000), #2220, #2296, aa35c6f224, 4324b7e6ce, #2232, #2338 | Planted fixtures declare `rows >` every `LIMIT`/page-size constant found by AST; each fixture asserts its landed count; a test that `monkeypatch`es a production-supplied value fails unless marked `@pytest.mark.self_supplied(reason=)`; seed has 2 households and a non-UTC offset | <1 s | yes | new |
| M15 | **Mutation on changed lines** (job `mutate-changed`: `mutmut`/StrykerJS `--incremental` on diff files) | 1 | ci_gate | merge | blocking | test_defect 5.0% (41/49 catchable); 2eb1dc8b77, 7d44209e75, c22544ceb2, `status != 404` | Survivors fail unless listed in `mutants.allow.toml` with date + "mutant changes no behaviour" reason; allowlist entries expire (M22) | 1–5 min, only when tests/src changed | CI only | new (jarvis ran planted defects by hand, 19 times) |
| M16 | **Deploy preflight** (`deploy/preflight.py`) | 1 | script | deploy | blocking | deploy_env_config (50/90 preflight-catchable); #1391, #2062, Azure cutover ×11 | Refuses `up` unless rendered env ⊇ `settings.toml` required names, no unknown names, image digest = SHA, migration head matches, role posture queried and printed; also a step in `boot` | ~10 s per deploy | yes (PowerShell `run.ps1` calls it) | jarvis `fleet_secrets.py`/`fleet.py` (rework into one preflight reading `settings.toml`) |
| M17 | **Intent-before-commit** (`hooks/gates/intent_gate.py`) | 9 | hook | plan | blocking | misread intent + built wrong thing 139 (dedup); retired path resurfacing (4 periods); screen-of-record precedence lesson | Deny `git commit` (`Bash\|PowerShell`) when `.rails/intent/<branch>.md` is absent or a required heading is empty; first commit only; `# intent-ok` override written in the command for one-line fixes | ~2 min agent time once per branch | yes (shlex tokenise; backslash-safe) | new; `claim_before_edit.py` first-edit moment reused |
| M18 | **Turn-end receipt gate** (`hooks/gates/turn_end_gate.py`, `Stop`) | 9 | hook | verify | blocking (once per turn) | claimed-done-unverified 58 + verified-on-fixture 25; stopped-early 70; only 4/645 self-catches from a screen | Blocks (`decision: block`) when (a) HEAD or the working tree changed code and `.rails/receipts/<sha>/` has no `check` (and no `walk` when UI/server paths changed), or (b) the final message is offer-shaped ("want me to", "say the word", "let me know") while `.rails/worklist.json` has open items; honours `stop_hook_active`; a real decision passes when the message carries a `DECISION:` brief (problem, options with costs, recommended) | <1 s | yes | apex `suggest-review-on-stop.sh` (rework: 44% follow-through, the only advisory with measured effect) |
| M19 | **One PR per worktree** (`hooks/gates/one_pr_gate.py`) | 9 | hook | ship | blocking | "one PR per line of work" restated 25+ times; duplicate PRs landing empty commits | Deny `gh pr create` when `gh pr list --head <branch>` or the claim store shows an open PR for this worktree/claim; names the open PR; `# second-pr-ok` override | ~1 s (one `gh` call) | yes | new; `merged_pr_push_gate.py` pattern |
| M20 | **`rails ship` + PR monitor** | 9 | script | ship | blocking at merge-arm | ceremony 35%; "how come you were not monitoring"; arm-and-stop vs watch conflict | Runs `rails check`, pushes, `gh pr create --body-file` from template, `gh pr merge --auto --squash`, binds `ccd_pr.set_monitor` so the session wakes on red/conflict; refuses to arm a seam-path PR without a review receipt | ~1 min wall | yes | new; replaces hand ceremony + `.githooks` push-consent gate (deleted) |
| M21 | **Cold two-voice review on seam paths** (`rails review`, agents in plugin) | 2 | subagent | review | blocking on seam paths | code + seam review earliest catch 17.4%; #2413 (9 must-fix), #2223, #2429, #1580 | Two subagents (`reviewer-coop.md`, `reviewer-adversary.md`), `omitClaudeMd: true`, read diff + primary artifacts, no shared context; reconciled list; receipt `.rails/receipts/<sha>/review.json`; two rounds max; `gh pr merge --auto` denied without it when the diff touches seam paths | ~5–10 min wall, ~150–250k tokens on seam PRs; `python-review` only elsewhere | yes | apex `adversarial-pair`, `design-review`, `python-review`, `typescript-review` (keep, trim descriptions) |
| M22 | **Harness ledger** (`rails/ledger.toml`, `ci/test_harness_ledger.py`, scheduled `unread_reds.py`) | 7 | ci_gate | merge/schedule | blocking | harness_self 10.4% + test_defect 5.0%; 44% of CI job failures; 214/0 Sherpa; 20/20 unread completion gate; red stopped meaning anything | Every hook/gate/template/job has a row: `cites` (sha/issue), `planted` (test path), `fp_count`, `fp_measured_on` (sha), `windows_fixture`, `required_by`; test fails on a missing field, a non-required job past `required_by`, a hook with `last_fired` >60 days (from the firing log the dispatcher writes), an allowlist entry past `expires`; scheduled reporter files one issue when a non-required job is red 3 runs running and surfaces it at SessionStart | <1 s | yes | jarvis `mechanism_table.py`/`mechanism_ledger.py` (rework: ledger becomes the source; PR table generated from receipts) |
| M23 | **Context budget test** (`ci/test_context_budget.py`) | 7 | ci_gate | merge | blocking | CLAUDE.md 1,962→9,160 words; first-turn 86k→105k tokens; ETH null result on overviews | CLAUDE.md ≤1,500 words and no CI mechanics or status (regex-pinned), `.claude/rules/*.md` each with `paths:`, `MEMORY.md` ≤25 KB, SessionStart output ≤600 tokens (meta-test runs the hook), skill descriptions ≤1,536 chars total | <1 s | yes | new; `test_ci_lanes.py:1924` pattern |
| M24 | **Acceptance door+instrument** (`ci/acceptance_check.py` reworked; `.github/ISSUE_TEMPLATE/work-item.yml`) | 2, 6 | ci_gate + template_doc | spec/ship | blocking at `gh pr create` | PR-09 11.1%; #2266 (CLI-only door), #2226 (/dev/login), #2227 (dev harness), milestone 39 | Each acceptance line: `door:` (app/fleet/CLI/API) and `instrument:` (role, factory, DB state, data set, client); a line whose instrument is `mock\|dev-login\|standalone\|superuser` cannot close an issue; hook denies `gh pr create` with such `Closes #N` | <1 s | yes | apex/jarvis `acceptance_check.py` (rework) |
| M25 | **Milestone close = receipts** (`rails close`, `rails accept`, scheduled `closed_without_receipt.py`) | 6 | script + ci_gate (report) | accept | blocking in the CLI; report-only on GitHub | R3 #1064, R8/R13/R20 closed unrun; 189 UAT issues days after close; #2215 | `rails close` requires `.rails/receipts/accept/<milestone>.json` (target, SHA, operator task) and an oracle receipt with 0 violations; demo steps with a figure must carry `expect:` (non-zero, equals); hand closes are flagged at SessionStart | one walk per milestone (operator) | yes | apex/jarvis `milestone_completion_gate.py` (keep as report), `milestone.md` (keep) |
| M26 | **Leak check, default on** (`ci/hooks/pre-push`, `purser.cli leak-check` generalised to `rails leak-check`) | privacy | git_hook | push | blocking (exit 3) | #2527 (21 amounts as fixtures), descriptors on master; anti-pattern "pattern scanners for household data" | Pre-push asks the operator's *store* whether any pushed line holds one of its values; prints `path:line kind`, never the value; store path in `.rails/local.toml` (git-excluded); fails open with a loud line only when no store is configured — and `rails adopt` configures it; also runs on `gh issue/pr create --body-file` via the dispatcher | 2–10 s per push | yes (`#!/bin/sh` under Git for Windows; `core.hooksPath` absolute) | jarvis `ci/hooks/pre-push` (opt-in → default) |
| M27 | **Deny hooks for tool hazards** (`pipe_mask`, `secret_env`, `secret_file_touch`, `heredoc_write`, `stash`, `merged_pr_push`, `detached_server`) | 8 | hook | build | blocking | the measured incidents each cites (720/95/26/23/2/2/2 denials) | Ported into `hooks/gates/` under the dispatcher so all match `Bash\|PowerShell` and run from the plugin root (no branch-local gaps) | ~0 (inside M1's one process) | yes | jarvis `.claude/hooks/*` (keep; move) |
| M28 | **Model-in-the-loop declaration** (`model_feature.toml` + `ci/test_model_golden.py`) | 1 | template_code + test_pattern | build | blocking where present | external_integration 4.3%; ~15 prompt commits; e2a9040a26 (mocks green, live 400); watchlist wiped ×3 | Per feature: context inventory, writable stores (user-authored stores read-only in the tool layer, tested), loop budget, code/model boundary, output strip-list; golden set of 5–20 real inputs run against a recorded transcript per configured model, re-recorded by hand | 10–60 s | yes | new; jarvis `toolbox_assistant` mounts |
| M29 | **Second-consumer extraction rule** (`ci/test_toolbox_has_two_consumers.py`) | 1, 6 | ci_gate | merge | blocking | the brief's open question; #2348; Metz "wrong abstraction" | A `toolbox-*` package merges only with two wired consumers in the catalogue (M6) or a row in `catalogue/unreached.toml` with `expires:`; apps may hold a capability until the second consumer exists | <1 s | yes | new; replaces "toolbox-first from birth" prose |
| P1 | *Prose: judgment that stays prose* | 7 | convention_prose | all | prose | what the kit cannot carry (§5.4) | CLAUDE.md ≤1,500 words, `rails/contract.md` one page | reading ~2k tokens | n/a | jarvis CLAUDE.md "Design claims have no oracle" section (keep, cut) |

---

## 4. Templates

### 4.1 The code kit: `rails-kit/` (a template repository; `rails new <app>` copies and renames; `rails adopt` lands it into an existing repo baseline-then-drain)

| Path | Purpose | Contents outline | Replaces |
|---|---|---|---|
| `contracts/` | the one schema source | Pydantic models for every wire DTO, row model and enum; `wire/frozen.json` and `frontend/src/gen/{types,client}.ts` are generated and committed; `test_routes_typed.py` fails a route without `response_model` | per-package DTO copies; hand-written `client.ts`; `contracts.ts` (becomes generated) |
| `settings.toml` | every runtime setting declared once | `[VAR] type owner required envs.{dev,prod}=value\|secret:<ref>`; generated `settings.py`, compose `environment:` block, renderer manifest, preflight list | renderer + compose + validator + settings kept by hand (9 fixes/7 days) |
| `roots/registry.py` + `roots/{fleet,standalone,desktop}.py` | every composition root, introspectable | each root is a function returning a `Composition(config_fields, seams, schedules, topics, env)`; `boot` and `test_root_parity` iterate the registry | roots discovered by reading code; `purser.serve` "is NOT the app" prose |
| `app/clock.py` | typed clocks | `Frontier`, `Wall`, `PinnedAsOf`, `MemberTz`; roots inject; engines take `clock: Clock` with no default | `when_for(None)` and 7 one-caller fixes |
| `rules/registry.toml` + `app/engines/` | one owner per concept with its oracle | `[concept] owner="engines.spend.classified_rows" test="tests/..." oracle="sum(drill)"` | prose definitions re-derived per engine |
| `auth_matrix.toml` | per-route actor × action | generated route list must be fully covered | category STRIDE in `design.md §7` |
| `fixtures/planted/` | the only CI data | two households, non-UTC offset, counts above every default limit, landed-count asserted; builder `rails plant` | hand fixtures that fabricate shapes; any real value in git |
| `tests/conftest.py` | production role by default | Testcontainers Postgres; `db` as `app_role`; `superuser` marker with reason; identity printed beside results | superuser rigs |
| `frontend/src/lib/{load,state,clock,client}.ts` + `screens/<name>/{index.tsx,states.test.tsx,controls.json}` | result-typed loading, state union, per-screen matrix | `rails new-screen` emits all four; `controls.json` feeds the walk | `useLoad` sites ignoring errors; mock-first screens |
| `e2e/walk.mjs` | the walk artifact | drives every screen from `controls.json`; text asserts; vocabulary ban; frames + `steps.json` under `walk/<sha>/` | Purser-only walkthrough; pixel/geometry gates |
| `model_feature.toml` (optional) | model-in-the-loop declaration | five sections + golden set path | prompt tuning by trial |
| `deploy/preflight.py`, `deploy/run.ps1` | preflight then up | reads `settings.toml`, image digest, migration head, role posture | `fleet_secrets.py`/`fleet.py` split |
| `ci/` | the gates named in §3 | `boot_smoke.py`, `codegen_gate.py`, `clock_gate.py`, `concept_gate.py`, `test_settings_parity.py`, `test_root_parity.py`, `test_reachability.py`, `test_auth_matrix.py`, `test_surface_parity.py`, `test_fixture_rules.py`, `test_harness_ledger.py`, `test_context_budget.py`, `acceptance_check.py`, `pre_pr_check.py` (with `LOCAL_COVERAGE`), `run_triage.py`, `hooks/{pre-commit,pre-push}` | jarvis `ci/` 76k lines: the docs-render subsystem, `pr_body_check.py`, `pr_dependency_check.py`, board/plan_train/velocity are not carried |
| `.github/workflows/ci.yml` | the one workflow | `checks`, `suite`, `frontend`, `walk`, `boot`, `mutate-changed`, `image`, `gate` (always; `success\|skipped`); `schedule`: full suite, `boot`, `unread_reds.py`, `closed_without_receipt.py`, `metrics.py` — all report-only, surfaced at SessionStart | 13-job `ci.yml` with `sherpa-geometry`, `generated-docs`, `windows-scheduler`, `classify` |
| `.github/rulesets.json` + `rails adopt --github` | the required check | ruleset: `required_status_checks: [gate]`, linear history, no force-push, `allow_auto_merge`, squash only; `--admin` merges counted by `metrics.py` | hand-configured ruleset |
| `.claude/settings.json`, `.claude/rules/{ci,frontend,db}.md`, `CLAUDE.md` | wiring + budgeted prose | hooks point at `${CLAUDE_PLUGIN_ROOT}/hooks/rails_hook.py`; rules are `paths:`-scoped; CLAUDE.md ≤1,500 words of judgment and commands | 9,160-word CLAUDE.md; three hook stacks |
| `rails/ledger.toml`, `rails/contract.md` | governance + the session contract | one row per mechanism; one page of resolved defaults (§6) | memory notes restating rules; `docs/process/README.md` |
| `.gitignore` / `.git/info/exclude` entries | privacy boundary | `.rails/ground-truth.toml`, `.rails/oracle/`, `.rails/local.toml`, `walk/` frames of real targets | ad-hoc exclusions |

### 4.2 Document templates (four, in `rails/templates/`)

- **`spec.md`** (one page). *Purpose:* the acceptance lines a test could fail, written only when the intent file is not enough. *Outline:* What / Not this / Acceptance (each line `door:` + `instrument:` + observable that could come out the other way) / Figures and their oracle / Clocks used / Verification step (which walk frame or test). *Replaces:* `prd.md` (19k words with 32% preamble), `recon.md` (a subagent output), `impl-plan.md` (the PR's commit list).
- **`design.md`** (two pages, seams only). *Purpose:* the walls before code, for a seam or trust boundary. *Outline:* Walls (the declaration each side imports) / Seams table (value, who stamps, who trusts, the test that holds it) / Roots (which roots compose it) / Clocks / Concepts owned / Route × actor matrix / Behaviour claims each citing a test or marked `UNVERIFIED` / Freeze record (one authoring pass, one two-voice pass, surviving objections → issues). Amendments go to `design.log.md`, dated, each naming the capability it removes. *Replaces:* apex `design.md`, jarvis `docs/templates/design.md` (Walls heading kept), the §11-style amendment logs inside the design.
- **`adr.md`** (one page). *Outline:* Context / Decision / Consequences / **Enforcement** (test, gate, hook, or "by convention", named as the weakest) / Status derived from the enforcement row's existence. *Replaces:* apex `adr.md` (keep its Enforcement section), 17 "Proposed" ADRs that were implemented.
- **`milestone.md`** (kept). *Change:* step 0 becomes "the operator did <task> on <target>; receipt attached"; every figure step carries `expect:`. *Replaces:* nothing — it governs every release today.
- **PR template** (`.github/pull_request_template.md`): Intent (embedded from `.rails/intent/`), Walk (link to `walk/<sha>/`), Mechanisms (generated from receipts by `rails ship`: mechanism, ran, findings, defects), Closes. Hand-written sections removed; the body is never gated on prose (anti-pattern 13).
- **Issue templates** (`work-item.yml`, `defect.yml`): `Done when` lines require `door:`/`instrument:`; defect form keeps "which gate should have caught this" and adds "ledger row".

### 4.3 The plugin: `rails` (apex reworked; local-path marketplace, relative source, loads in place — one copy for every worktree)

`hooks/hooks.json` → five registrations, all to `rails_hook.py`. `hooks/gates/`: M17, M18, M19, M24 (the `gh pr create` half), M27's seven, `artifact_templates` (gh half only), `issue_cap`, `reuse_inventory`, `claim_before_edit`, `context_economy`, `format_on_save`. `agents/`: `recon.md` (Read/Grep/Glob only, `omitClaudeMd: true`), `reviewer-coop.md`, `reviewer-adversary.md`. `skills/` (12): `rails` (the one user-invocable entry: `/rails new|adopt|check|walk|ship|review|accept|close|oracle|metrics`), `release`, `fix`, `retro`, `design-review`, `impl-plan-review` (renamed `plan-review`, used only when a design exists), `adr-review`, `prd-review` (renamed `spec-review`), `threat-model` (route-matrix form), `adversarial-pair`, `python-review`, `typescript-review`. `templates/` as §4.2. `scripts/rails.py` the CLI. `.github/workflows/hook-tests.yml` with backslash-path and PowerShell-payload fixtures and a `windows-latest` job for the hook suite.

---

## 5. Governance

### 5.1 How a mechanism earns its place

A hook, gate, template or CI job exists only as a row in `rails/ledger.toml`:

```toml
[boot]
kind = "ci_job"            # hook | ci_job | git_hook | template | test_pattern
cites = ["e854e76289", "d1ad2720b1", "#2270", "#1064"]
planted = "ci/test_boot_smoke.py::test_unmounted_route_turns_red"
fp_count = 0               # on the tree at fp_measured_on, over N PRs
fp_measured_on = "<sha>"
fp_window_prs = 20
windows_fixture = "ci/fixtures/boot/windows_paths.json"
required_by = "2026-10-26" # a non-required job past this date fails the ledger test
last_fired = "2026-10-05"  # written by the dispatcher's firing log / CI summary
```

`ci/test_harness_ledger.py` fails the PR when a registered hook or `ci.yml` job has no row; a row lacks `cites`, `planted`, `fp_count` or `windows_fixture`; `required_by` has passed and the job is not in `gate.needs`; a hook's `last_fired` is more than 60 days old (delete it or re-justify it with a new citation in the same PR); a `mutants.allow.toml`, `catalogue/unreached.toml` or `roots/exclusions.toml` entry is past `expires`. The ledger is the only place the "planted defects and FP rate first" rule lives, and it is a test, not a sentence. A new gate is landed `required_by` ≤ 21 days out; red on arrival means "make it required and fix it, or delete it", never "leave it reporting" (anti-patterns 1, 13, 25).

### 5.2 Retirement

Anything the ledger cannot justify is deleted in the same PR that fails the test. `unread_reds.py` (schedule, report-only) files one issue when a non-required job is red three consecutive runs and surfaces it at SessionStart; the issue's `Done when` is "required or deleted by <date>". `metrics.py` (schedule) counts fix-share, automation catch rate, ceremony share and `--admin` merges from git, the PR list and the deduplicated transcript classifier, and prints the four numbers at SessionStart once a week. Mechanisms are measured by their own firing log, written by the dispatcher to `${CLAUDE_PLUGIN_DATA}/firings.jsonl` (hook, verdict, override used) so the next inventory does not need a transcript parser.

### 5.3 The context budget

Before the first action a session loads: CLAUDE.md ≤1,500 words (~2,000 tokens), `MEMORY.md` index ≤25 KB but targeted at ≤500 words (~700 tokens; the 427 notes stay on disk, recalled by path), SessionStart state ≤600 tokens, skill names and descriptions (~12 skills, ≤1,536 characters total, ~400 tokens), and `.claude/rules/*.md` only when the touched paths match. **Target: ≤4,500 tokens of harness context**, against 21–24k today (jarvis-specific preload was ~21% of a 105k first turn). `ci/test_context_budget.py` pins each ceiling and regex-rejects CI-lane facts and front/status logs in CLAUDE.md: CI facts live in `.claude/rules/ci.md` (`paths: [.github/**, ci/**]`) and are pinned by `test_ci_lanes.py`; the front lives in the claim store and is printed by `rails_state.py`.

### 5.4 What the kit cannot carry, and how the remainder is enforced

1. **What to build.** The kit cannot know. It forces the intent to be written where the operator can correct it (M17) and makes the acceptance lines name a door (M24). Content is judged by the operator; form is enforced.
2. **The household's ground truth.** Rules and figures the operator knows and the agent cannot infer. `.rails/ground-truth.toml` (git-excluded) holds them as invariants the oracle (M13) reads; the agent asks for them in the intent file's "Figures" section before building money, trip or currency logic; a PR touching `engines/` without an oracle row fails M12.
3. **Whether a seam deserves a design.** Judgment, with a default: a diff touching seam paths gets the two-voice review (M21) whether or not a design exists; a design is written when the review's first round cannot be judged against code.
4. **Statements need receipts.** M18 gates the *done* claim and the *stopping* claim with artifacts. The general rule — a sentence about existence, absence, deploy state or root cause cites what was read this turn — stays prose in CLAUDE.md, with an optional `type: prompt` Stop hook (one model call per turn end, ~30 s) that asks "does the final message assert a fact about the system without naming a command or file read this turn?" and blocks once. It is listed in the ledger as experimental with a `required_by`; if it does not earn a citation in 30 days it is deleted.
5. **Which clock a figure uses.** The kit forces a choice (M9) but not the right one; the design template's Clocks section and the oracle's `as_of` row carry the judgment.
6. **Plain-language briefs to the operator.** `DECISION:` format (problem, options with costs, recommended first) is recognised by M18 as a legitimate stop; the quality of the recommendation is prose.
7. **Reading a multi-file handoff in precedence order.** Prose, one bold line in CLAUDE.md, plus the intent file's "Screen of record (and its precedence statement)" field, which is a required heading.

Everything in this list is in CLAUDE.md; nothing else is.

### 5.5 Anti-pattern check (the 26)

Avoided by construction: 1 (ledger `required_by`), 2 (M7), 3 (M24 instrument rule), 4 (M2, M3, M8 generate the lists), 5 (M22 + M23: a rule is admitted with its gate or not at all), 6 (two-page design, amendments in a log, review judged against code, two rounds), 7 (M25), 8 (M6 walks call sites; M11 clicks; M8 scans mounted routes not `*.py`), 9 (M10 lint), 10 (M14 planted-only fixtures; M11 vocabulary ban), 11 (M9, M3, M12 fix the class with a gate), 12 (M28 golden set; prompt commits without a golden-set change are visible in the PR table), 13 (ledger: planted defect + FP count + Windows fixture before merge), 14 (PR body is never gated on prose; M24 gates an *artifact*: the issue's acceptance line), 15 (every advisory nudge that asked for a heavy action is deleted; the remaining advisories are one-command actions at the moment), 16 (M17 plus `run_triage` before any fix commit; empty-body fix commits are flagged by `metrics.py`), 17 (status, catalogue and front are generated), 18 (M5), 19 (M28 writable-stores test), 20 (M9: as-of pinned in one `settings.toml` name for both envs), 21 (M8), 22 (one plugin copy, repo holds wiring only; `rails adopt --check` fails when a repo carries its own copy of a plugin gate), 23 (M26 asks the store, not a pattern), 24 (M12), 25 (M4 required, path-filtered), 26 (`metrics.py` reads the billing annotation and surfaces "N runs never started" at SessionStart).

Deliberately different: anti-pattern 15 says advisory nudges fail; this design keeps three advisories (`claim_before_edit`, `reuse_inventory`, `artifact_templates` gh half) because each fires at the moment of a one-command action and has a measured or plausible effect, and each has a ledger row that will delete it if `last_fired` goes stale.

---

## 6. The session contract (layer 9)

`rails/contract.md` is one page and the only place these defaults live. It is loaded by CLAUDE.md (`@rails/contract.md`) and counts toward the budget.

**Defaults, resolved.**

1. *Push consent vs autonomy.* Resolved for autonomy: once `rails check` passes, the session pushes and opens the PR without asking. The `.githooks` push-consent gate (`JARVIS_PUSH_OK`) is deleted. What stays blocking at push is the leak check (M26), because data leaving the machine is irreversible and consent is not. The operator's word is `hold`; given in chat it is written into `.rails/hold` by the session, and `rails ship` refuses while the file exists.
2. *Arm-and-stop vs watch CI.* Resolved: arm, then bind the PR monitor (M20). The session is woken by the monitor; it does not poll and the operator does not relay. If the monitor is unavailable, `rails ship` says so in the PR body and the scheduled `stuck_automerge` reporter covers the gap.
3. *One front vs finish everything.* Resolved: one app in `building` (M1 claim store); within that app, finish the worklist. "I stopped because of the one-front posture" is not a legitimate stop unless the worklist is empty; M18 enforces the shape.
4. *One PR per line of work; slices are commits.* M19.
5. *No full suite per commit.* `rails check` runs the selector's set and the merge-tree tests for touched files; the full suite runs once in CI per PR and twice daily. A local `pytest` with no path and no `-k` is denied by a dispatcher gate with the alternative named (`rails check`); override `# full-ok`.
6. *Retired paths stay dead.* The intent file lists them; `ci/test_retired_paths.py` reads `rails/retired.toml` (path globs, date, issue) and fails when a listed path reappears.

**Receipts.** `check`, `walk`, `review`, `accept`, `oracle` receipts are JSON files under `.rails/receipts/<sha>/`, written only by the `rails` CLI (command, exit code, duration, SHA judged). Not committed; `rails ship` copies their summary into the PR's Mechanisms table, so the table is generated and parseable (jarvis's drifted to prose after 09-29).

**Done is a walk artifact on the named target.** "Done", "fixed", "works" require a `walk` receipt for HEAD when UI or server paths changed, and a `check` receipt always (M18). A milestone closes on an `accept` receipt (operator's real task, target, SHA) plus a zero-violation `oracle` receipt (M25). Fixtures, mocks, `/dev/login`, the standalone root and the superuser never appear in a receipt's `instrument`.

**Decisions, not questions.** A legitimate stop before the worklist is empty is a `DECISION:` block — problem in one line, options with costs, recommended option first. M18 passes it; anything else offer-shaped is blocked once.

**Corrections go into the artifact** (intent file, issue, design log, `ground-truth.toml`) in the same turn. Chat dies at compaction (323 in 458 sessions); the file does not.

**Ceremony per PR under this contract:** zero operator messages in the default path. The operator reads the PR if they wish, says `hold` if they must, and does one real task per milestone.

---

## 7. What is deleted, and why

**From apex (becomes `rails`).**
- `hooks/apex-primer.sh` — 373 deliveries, no measurable behaviour change.
- `hooks/suggest-skill-on-prompt.sh` — 13% follow-through.
- `hooks/suggest-skill-on-edit.sh`, `guard-security-paths.sh` — inert on backslash paths for the whole jarvis period; the dispatcher replaces the routing idea.
- `hooks/guard-dependency-bump.sh` — inert; reworked as a dispatcher gate that *asks* on a package name not in the lockfile (slopsquatting), path-normalised.
- `hooks/guard-destructive.sh` — whole-line regex, 33 blocks mostly false; keep the `.env` write, `--no-verify` and force-push-to-default rules, tokenised, inside the dispatcher.
- `hooks/scan-secrets-on-edit.sh` — 0 blocks in 16,276 writes; folded into `secret_env`/`secret_file_touch`.
- `hooks/session_output_gate.py` — 0 firings in 241 sessions.
- `hooks/run-python-hook.sh` deferral shim — the mechanism that produced two sources; the plugin is the only source.
- All 17 `commands/*.md` — 0 typed in 241 sessions; one `/rails` skill is user-invocable.
- Skills: `security-review`, `council-review`, `cross-artifact-consistency` (already `scenario_coverage`/`design_coverage_gate`), `data-migration-review`, `observability-review`, `postgres-review`, `multi-tenancy`, `ui-design-review`, `test-strategy`, `test-coverage-audit`, `verification-before-completion`, `ai-pre-review-checklist`, `release-readiness`, `cicd-review`, `deployment-review`, `project-bootstrap`, `install-gates`, `incident-retro`, `memory-note`, `autonomous-fix`, `investigate-bug`, `detect-stack`, `copilot-review-loop`, `responding-to-review`, `pr-review-primer`, `summarize-changes`, `spec-view`, `apex-flow`, `recon` (skill; the agent stays), `design-feature`, `verify-ports`, `polymorphic-type-modeling`, `protocol-first-workflow`, `pr-discipline` (contradicts the operator's standing rules). 33 of 45.
- `rules/*.md` — `principles.md` folds into the design template's Reuse verdict; `landing-a-component.md` rule 2 becomes `ci/test_design_ahead_of_code.py` (revisions vs package existence); `merge-hygiene.md` folds into `pre_pr_check` replay preflight; `review-risk.md`, `frontend.md`, `responding-to-review.md` deleted.
- `templates/recon.md`, `templates/impl-plan.md`, `templates/gates/pr_body_check.py` (removed from jarvis CI 08-10 for teaching `--admin`; pinned absent by `test_ci_lanes.py:1465`).
- `docs/` (agent-rails, autonomous-fix, cross-artifact-consistency, execution-tiers, incident-retro, stack-adapters, research; 3,776 lines for unbuilt features) — archived to a tag. The one idea lifted: `agent-rails/state.json` → `.rails/receipts/`.
- `graphify-out/`, `output-styles/apex-terse` — unused.
- Un-prefixed duplicates in `~/.claude/skills/` (python-review, typescript-review, ai-pre-review-checklist, pr-review-primer, protocol-first-workflow).

**From jarvis CLAUDE.md** (9,160 → ≤1,500 words): the CI-lane table and every CI mechanic (2,844 words → `.claude/rules/ci.md`, path-scoped, pinned by `test_ci_lanes.py`); the front/status log (1,609 words → claim store, printed by `rails_state.py`); build/test commands beyond the five that matter (→ `rails check`); the secrets-and-redaction history (→ `.claude/rules/db.md` and the ADR); the "Where new code goes" table (→ generated catalogue + `reuse_inventory`); every rule that now has a gate (stash, pipe, push, one PR, one issue, done = demo, planted defects first). What remains: the judgment list in §5.4, the five commands, and `@rails/contract.md`.

**From jarvis hooks and CI.**
- `retro_due.py` — 405 notices of an unpayable debt. The retro stays a skill; the ledger row is the retro's output.
- `discovery_dossier.py` — 1 skill use per 19 nudges. The dossier skill folds into `spec.md`.
- `memory_freshness.py` anchor nag — 21% after seven weeks; replaced by `verified_at` required by the memory-note template and nothing else.
- `session_pickup_gate.py` — overridden 17 of 20 times; its useful half (surface the issue's `path:line` claims) moves into `rails claim` output.
- `session_output_gate.py` — 0 firings.
- User-level `graph_first.py` and the code-review-graph PostToolUse hook — 5% compliance at 0.93 s per Edit/Write; the catalogue (M6) answers "who calls this" from code.
- `.githooks/pre-push` push-consent (`JARVIS_PUSH_OK`) — the contract resolves it; the leak check stays and becomes default-on.
- `ci/pr_body_check.py`, `ci/pr_dependency_check.py` — body gates; `mechanism_table.py`/`mechanism_ledger.py` reworked into `rails/ledger.toml` + generated PR table.
- `sherpa-geometry` job and Gate B — 216 failures, 0 defects.
- `generated-docs` lane, `docs-render-train/publish/staleness` workflows, `generated_docs_gate.py`, `aggregate_binding_gate.py`, `docs_train/` — 186 failures, 0 product defects, manual-only since 08-30 and still taxing every docs PR (622 local runs). The catalogue and status are generated on read; nothing rendered is committed.
- `windows-scheduler` job — 75% harness; the Windows coverage that matters is the hook suite on `windows-latest`.
- `classify` job — the lane split exists only to serve the docs train.
- Arch gate `modules-are-consumed` — satisfied by any `__init__` import; M6 replaces it. The other 26 `check_*` stay, split out of the 6,949-line module by concern.
- `milestone_completion_gate.py` as a CI step — already report-only; keep the SessionStart hook only.
- `docs/process/README.md`, `the-loop.html` — zero Read opens, stale numbers; this document's §2 is the loop and lives in the `rails` skill.
- `scripts/apex-port/` — the two-sources bundle.
- Board, `plan_train.py`, `velocity_sentinel` — no outcome measurement in 10 weeks; kept only if a ledger row with a citation is written for each by the `required_by` date, else deleted.

---

## 8. Rollout

### 8.1 jarvis and Purser

**Week 1 — the carrier and the contract (no product change blocked).**
- Fork apex → `rails` on a branch; apply §7 deletions; write `rails_hook.py` and port the seven deny hooks under it; register `Bash|PowerShell` everywhere; add `hook-tests.yml` backslash and PowerShell fixtures and a `windows-latest` job. Install as a local-path marketplace with a relative source (loads in place, every worktree).
- Land M17 (intent gate), M18 (turn-end gate), M19 (one PR), M20 (`rails ship`), `rails/contract.md`; delete the push-consent `.githooks` gate; make the leak check default-on with `.rails/local.toml`.
- Cut CLAUDE.md to ≤1,500 words; create `.claude/rules/ci.md`; land `test_context_budget.py`.
- Seed `rails/ledger.toml` from `harness_inventories.json` (every surviving mechanism gets its citation row or is deleted); land `test_harness_ledger.py` with `required_by` dates.
- Promote `fleet_smoke` → `boot`: add migrate-from-previous and boot-twice, plant `test_unmounted_route_turns_red`, run on the last 20 PRs for the FP count, path-filter, add to `gate.needs` with `required_by` = day 21.
- *Measured at end of week:* ceremony share from the dedup classifier; hook firings from the dispatcher log; `boot` FP count.

**Weeks 2–4 — the walls, retrofitted into Purser baseline-then-drain.**
- `settings.toml` for the fleet and Purser; `test_settings_parity.py` lands green against a frozen baseline of today's drift, then drains (the `contract_gate` landing pattern: 93 findings → 0).
- `roots/registry.py` for Purser's fleet, standalone and desktop roots; `test_root_parity.py` with `roots/exclusions.toml` seeded from the current gaps (#2270, #2357 class), each with `expires`.
- `rails codegen`: OpenAPI → `frontend/src/gen/client.ts`; `test_routes_typed.py` baseline over the 23 untyped Hearth routes, drained.
- `src/lib/load.ts` + ESLint rule; the 42 `useLoad` sites convert screen by screen, each with `states.test.tsx`; the walk's `controls.json` generated from the screen registry.
- `rules/registry.toml` seeded from the Purser H1 census (income, spend, liquidity, ledger frontier, month arithmetic, account role, currency, settlement) with owners; `concept_gate.py` baseline, drain through H1's PR.
- `toolbox_clock` + `clock_gate.py`; `PURSER_AS_OF` becomes a `settings.toml` row read by server and runner.
- `auth_matrix.toml` for Purser and Hearth; the 401/403 parametrised test; the member-removal test.
- `conftest.py` production-role default; `superuser` marker baseline over the current rigs, drained.
- `rails oracle` over the operator's store with `.rails/ground-truth.toml`; `rails accept`/`rails close`; the first milestone to close under M25 is Purser H1.
- `rails catalogue` + `test_reachability.py` with `catalogue/unreached.toml` seeded from #2348/#2400/#2404 and the 63 built-not-wired gaps, each with `expires`.
- Delete the docs-render subsystem, `sherpa-geometry`, `windows-scheduler`, `classify` per §7; `mutate-changed` lands on Purser only.

**Later (weeks 5–8).**
- `rails new` extracted from the Purser retrofit as the kit; the first new app (or the Pulse remount) is created from it.
- M29 second-consumer rule, baseline over the 38 toolboxes (each with two consumers or an `expires`).
- The `type: prompt` receipts hook as an experiment with a 30-day `required_by`.
- Decide the merge-queue question with the plan in hand; until then `rails check` runs merged-tree tests for touched files.
- Remove or keep the admin bypass actor based on `metrics.py`'s `--admin` count over 30 days.

### 8.2 A new app

`rails new <app>` → a repo with every §4.1 file, `ci.yml`, the ruleset applied by `rails adopt --github`, the plugin enabled in `.claude/settings.json`, and a walking skeleton: one root, one route with a `response_model`, one screen with four states, one planted household, one concept with an owner and an oracle, one schedule with a handler, `boot` green, the walk producing frame 1. The first milestone's demo is "the operator does one real task on the dev target"; nothing else is scaffolded (no dossier stage stubs: 75 of 190 were empty). The kit's own `hook-tests.yml` runs on Windows.

### 8.3 What is measured

`metrics.py` (schedule, report-only, SessionStart once a week) prints four numbers with their current baseline and the eight-week target:

| Metric | Baseline (evidence) | Target by week 8 | Source |
|---|---|---|---|
| Fix share of commits | 36% (391 of 412 jarvis commits were `fix(...)` in one window; 58% rework) | <20% | `git log` classifier (`fix:` + body) |
| Automation catch rate | ~10% (CI 8.3% + e2e 1.7% of 774 fixes) | ≥30% | defect form's "detected by" + CI-first-red join |
| Ceremony share of operator messages | 35% (1,791 of 5,398; 878 approvals + 630 git/PR ops dedup) | <10% | dedup transcript classifier |
| Correction share | 14% (445 corrections of 4,253 unique; 21% with repeats and frustration) | <8% | same |

Secondary: harness-only red runs (41% → <10%), `--admin` merges (0 stays 0), context tokens before first action (21–24k → ≤4.5k), time from merge to first operator catch on the named target.

---

## 9. Requirements coverage

| Req | Status | How / why |
|---|---|---|
| PR-01 boot every root, required | **Met** | M4: all roots, all flags, production role, migrate-from-previous, boot twice, one request per route/nav/schedule/topic, 5xx/404/html/no-handler failures, in `gate.needs`, path-filtered. |
| PR-02 generated root parity | **Met** | M5 introspects `roots/registry.py`; exclusions dated; hand lists cannot satisfy. |
| PR-03 settings declared once | **Met** | M3 generates settings/compose/renderer/preflight from `settings.toml`; parity test; collision check. |
| PR-04 every control has a real-backend e2e step with effect after reload | **Met**, one edge partial | M11 clicks every control from `controls.json`, asserts after reload; "visible from a second session" is covered only by reload, not a second browser context (cheap to add; left out of v1). A control with no production caller renders `not_composed` (M10) and M6 fails the merge otherwise. |
| PR-05 screen state matrix, result-typed loader, `?? []` fails lint | **Met** | M10. |
| PR-06 oracle per figure, planted parity in CI, local real-data checker before close | **Met** | M13 + M25; output is `rule_id,row_id,pass`, never a value; receipt attached to the close. |
| PR-07 concept registry with owner and gate | **Met** | M12. |
| PR-08 typed clock, lint, two pinned clocks, as-of pinned in both envs | **Met** | M9; the two-pinned-clocks test is the engine test pattern emitted by the kit; as-of is one `settings.toml` name. |
| PR-09 acceptance names door and instrument; mock/dev-login/standalone cannot close | **Met** | M24 at `gh pr create`. |
| PR-10 production caller proven by a test that fails when the call site is deleted | **Met** | M6 walks call sites from roots and fails on zero callers; a Null/no-op seam composed by a production root fails M4. The "delete the call site" form is the catalogue diff itself. |
| PR-11 milestone closes only with a demo artifact at the closing SHA; figure steps reconcile | **Met** in the CLI, **partial** on GitHub | M25: `rails close` refuses; a hand close on GitHub cannot be blocked, so it is flagged at SessionStart within a day. |
| PR-12 new gate ships with planted defect, FP count, outside case, OS/shell test, required-by; red 3 runs → issue, 7 days | **Met** | M22 + `unread_reds.py`; the outside-list case is required of every list-shaped gate by `test_fixture_rules`; the Windows fixture is a ledger field. |
| PR-13 production role default; identity printed; vendor premises recorded | **Met** | M7; vendor-semantics premises are a required comment form checked by a small lint (`# measured: pg16 RESET → ''`). |
| PR-14 auth matrix over the composed fleet; 401/403; member-removal; CSP/nosniff/CSRF in boot | **Met** | M8 + M4. |
| PR-15 one declaration per crossing identifier; bidirectional emit/subscribe; unmatched raises | **Partial** | M2 gives one declaration for DTOs, enums, routes and state values (UI state union generated from the engine's enum). The bidirectional event test exists as a kit pattern (`test_events_bidirectional.py`) over a `events/registry.py`, but the kit cannot force every ad-hoc string topic through it; the catalogue (M6) flags a topic with no handler and `boot` fails on it. "Unmatched raises" is a lint on `.get(x, default)` over registry lookups, advisory in v1. |
| PR-16 fixtures exceed limits, assert landed count, supply nothing production does not, two households, non-UTC | **Met** | M14. |
| PR-17 model-in-the-loop declaration + golden set | **Partial** | M28 declares the five things and runs the golden set against a recorded transcript per model; a *live* call per configured model is left to the operator's `rails oracle --live` because it costs money and leaves the machine; the writable-stores rule is a test. |
| PR-18 two-voice review on every source PR; before freeze for seams | **Partial, deliberately** | M21 is required on seam paths and before a seam design freezes; elsewhere a single-voice `python-review`/`typescript-review` before commit. Reason: ~150–250k tokens and 5–10 minutes per PR across many concurrent sessions is the one cost in this design that could make the operator route around it; the evidence's 17.4% is concentrated at seams and trust boundaries, which is where it is required. The ledger measures defects found by the single-voice review on non-seam PRs; if that number is high, the filter widens. |
| PR-19 prose admitted only with its gate; word ceiling; status generated; claims cite a test or UNVERIFIED | **Met**, one part partial | M22, M23, M6 (catalogue), `rails_state.py` (front). "Any document claim cites a test or is UNVERIFIED" is enforced by a lint over `design.md` "Behaviour:" lines only; free prose elsewhere is not scanned. |
| PR-20 second PR to merge runs the file's tests on the merged tree | **Partial** | `rails check` runs touched-file tests on `git merge-tree --write-tree origin/master HEAD` before `rails ship` arms auto-merge, and `boot` runs on the PR head. A server-side guarantee needs `strict` (a rebase per merge) or a merge queue (plan-gated); the twice-daily full suite is the backstop, surfaced at SessionStart. Rejected: `strict` — on a repo merging several PRs an hour with many concurrent sessions it converts every merge into a ceremony round. |

Met 15, partial 5, rejected 0 (one sub-option rejected inside PR-20).

---

## 10. Where this design is weakest

1. **`boot` is the most expensive required job and the one most likely to repeat the fleet-smoke story.** Three to five minutes of Docker on every PR touching app, toolbox, runtime or deploy paths; fleet-smoke was 67% harness-defect when it ran. The ledger's FP window (20 PRs) and `required_by` date are the defence, and the first three weeks will tell whether the Linux runner's Docker is stable enough. If it is not, the fallback is a self-hosted runner on the operator's box, which jarvis tried and retired in three days.
2. **The Stop hook judges shape, not truth.** M18 looks for receipts and for offer-shaped or done-shaped text. An agent can word around the regex; the monitor-evasion result says prose-level detection trained against is beaten. The receipts are the real gate — a `walk` receipt cannot be faked without running the walk — but "work remains" relies on a worklist the agent writes itself, so an agent that writes no worklist is never blocked for stopping early. The `type: prompt` hook is the experiment that could close this; it costs a model call per turn.
3. **Retrofit volume.** Purser alone has 42 loader sites, three roots, settings in four places, 16 semantic entities and a census showing one concept in up to ten places. Baseline-then-drain lets every gate land green, but a baseline is a graveyard unless it drains; the dated `expires` fields are the only pressure, and the operator will be asked to accept a month of drain PRs that add no feature. Angle B's bet is that the drain is cheaper than the next 80 Purser fixes; the evidence (58% rework) supports it but does not prove it.
4. **The seam-path filter on two-voice review may be wrong.** If the next hundred defects cluster in engines rather than seams, PR-18's "every PR" was right and this design under-reviews. The ledger will show it within a month; widening the filter is one line.
5. **Domain truth is only half mechanised.** The oracle (M13) catches what the rule table states and the operator approved. The 102 wrong-domain-fact corrections include facts nobody had stated; the intent file's "Figures" section asks the right question but cannot force the operator to answer it before the build. Nothing published covers this class either (research brief §5.1).
6. **The kit's own harness is a defect source.** Twenty-nine mechanisms is more than apex shipped working. Every one of them is Python or TypeScript that can be wrong on Windows, and the kit's CI runs on Linux. The `windows-latest` hook job covers the hooks; the `ci/` scripts rely on the operator running `rails check` locally, which is the same "developer OS" gap that shipped three inert hooks.
7. **Merge is still bypassable** (`RepositoryRole 5, bypass_mode: always`). Nothing here stops `gh pr merge --admin`; `metrics.py` counts it. Removing the bypass removes the operator's escape hatch, and the evidence says the habit died when the body gate did (49 → 3 → 0). This design relies on that holding.
8. **One schema source stops at the wire.** The DB is still authored as migrations; M2 proves the row models match the DDL after migrate (in `boot`), it does not generate the DDL. Generating DDL from Pydantic was judged a bigger bet than the evidence supports (data_persistence is 3.4%, and its catchable half is migrate-from-previous and boot-twice, which M4 carries).

### Backtest against named defects (which step, which mechanism)

| Defect | Caught at | By |
|---|---|---|
| e854e76289 sub-app lifespans never ran | step 8 | M4 `boot` (route 5xx / no handler) |
| d1ad2720b1 SPA fallback 200 HTML on `/api` | step 8 | M4 (`text/html` on `/api/*`) |
| #2270, #2357 desktop root lacks schedules / seam | step 4 | M5 |
| eeae3969c7 as-of only in standalone root | step 4 | M5 + M3 |
| 7f98347cd3 RP id never forwarded | step 4 / 10 | M3 + M16 |
| 88e3a8a592 LIMIT 2000 dropped 56% | step 5 | M14 (fixture > limit) + M13 oracle |
| #2240 42 loaders ignore errors; #2238 ALL QUIET over 503 | step 5 | M10 lint + state matrix |
| #2235 mint a grant for another member; #2229 anonymous served | step 4 | M8 |
| 605eb1fc10 nine tables without RLS, green under superuser | step 5 | M7 |
| 5f4bc2a10a…9ae818e008 clock seam ×7; #1892 expired corpus | step 5 | M9 |
| 4d4c7e8ade liquidity re-derived; income ×4 | step 5 | M12 |
| #2348 1,175 lines with no caller; #2400 re-export orphans | step 8 | M6 |
| #2225 Ask drawer calls fetch | step 5 | ESLint `no-restricted-imports` in M10's kit lint |
| 1f6541bc0c UI state the engine never writes | step 4 | M2 (UI state union generated from the engine enum) |
| #2217 release ids on household screens | step 6 | M11 vocabulary ban |
| 83f2eeec9e sign inverted on 2,363 rows | step 11 | M13 oracle (sign per account kind) |
| #2527 real amounts committed as fixtures | step 7 | M26 pre-push, default on |
| Sherpa gate B 214/0; completion gate 20/20 unread | step 12 | M22 (`required_by`, FP count; report at SessionStart) |
| ENFORCED/LEGACY two-green-PRs conflict | step 6 / schedule | `rails check` merge-tree tests (partial), schedule backstop |
| "I spent days on the design and you didn't implement it" | step 2 | M17 (screen of record + precedence in the intent file) |
| "when you tested it … when I tested it, it didn't work" | step 6 | M18 + M11 |

Twenty of twenty-one are caught at or before merge by a named mechanism; the cross-PR semantic conflict is the one caught late, and is priced in §9 PR-20.
