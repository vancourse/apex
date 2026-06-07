---
name: data-migration-review
description: 5-pass DESIGN-PHASE gate for safely MOVING or TRANSFORMING data that already exists — backfills, bulk updates, re-types, relocations, data-model migrations over tables that already hold rows. Audits the DATA-correctness-and-safety of the move (will it corrupt / lose / leak data, and can we stop it halfway?), distinct from apex:impl-plan-review Pass 4 which sequences the rollout/PR-stack and Pass 5 which asks if each PR is git-revertible, and from apex:postgres-review which checks the schema DDL + index/lock mechanics. Plus inline adversarial counter-pass at every step. Fires during design / impl-plan for any change that backfills, rewrites, relocates, or re-types existing rows, or migrates a data model over a populated table. Pairs with apex:impl-plan-review (the layered migration PR stack this informs), apex:postgres-review (the DDL side of the same change), and apex:multi-tenancy (per-tenant backfill batching). Keywords: data migration, backfill, bulk update, dual-write, dual-read, reconciliation, expand-migrate-contract, idempotent, resumable, checkpoint, throttle, kill-switch, blast radius, corrupted backfill, half-migrated.
---

# Data Migration Review

The gate between "we decided to move / reshape existing data" and "we run the backfill against production rows." Today apex touches this only at the *plan* level — `apex:impl-plan-review` Pass 4 sequences expand → migrate → contract across the PR stack and Pass 5 asks whether each PR is git-revertible, and `apex:postgres-review` checks the schema DDL. Nothing gates the **data move itself**: will this backfill corrupt, lose, or leak rows, and can we stop it at 50% done without a half-migrated table? This skill is the data-correctness-and-safety gate. Picture the 2am page mid-backfill and the corrupted-rows ticket the next morning, and design the passes that would have prevented both — while staying lean. Output is a `## Data Migration Plan` section the impl-plan consumes and reviewers audit against the run.

Distinct from:

- **`apex:impl-plan-review`** Pass 4 — rollout *sequencing* / PR-stack ordering (the expand→migrate→contract phasing at the PR level). This skill audits the DATA correctness + safety *of the move itself* within those phases. The plan says "backfill is its own PR"; this says "and here is why that backfill won't corrupt or strand the data."
- **`apex:impl-plan-review`** Pass 5 — reversibility at the *stack* level ("is each PR git-revertible?"). This skill's Pass 4 is reversibility at the *run* level ("is the table valid if the backfill itself is killed at 50%?"). Pass 5 reverts code; this reverts a half-finished data move.
- **`apex:postgres-review`** — the SQL DDL + index/lock mechanics of the *schema* change (lock strategy, statement timeouts, online-DDL). This skill moves the DATA, not the schema, and hands lock-per-batch strategy to postgres-review. (`ALTER TABLE ADD COLUMN` is postgres-review's; populating that column across 400M rows is this skill's.)
- **`apex:multi-tenancy`** — tenant ISOLATION in general. This skill verifies the backfill *respects* that isolation (per-tenant batching, no cross-tenant bleed) rather than defining the model.
- **`apex:threat-model`** — adversarial STRIDE / security. This gate is data integrity + availability under *operational* failure (crash, restart, saturation), not an attacker.

## When to invoke

- During design / impl-plan for any change that **backfills** a new column/table, **rewrites** existing values, **relocates** data (table → table, DB → DB, column → JSON blob), or **re-types** a column over rows that already exist
- Any data-model migration on a table that already holds production rows (an empty-table migration needs none of this → that's `apex:postgres-review` only)
- When `apex:impl-plan-review` Pass 4 names a "migrate" / "backfill" phase, or Pass 5 flags a data-backfill reversibility question — that's the hand-off into this gate
- When `apex:design-feature` Pass 5 surfaces a "we'll need to migrate existing X" failure mode

Pairs with:

- **`apex:impl-plan-review`** (upstream — Pass 4 decomposes the move into expand/migrate/contract phases this gate assumes are already in place; this skill fills in the data-safety contract the plan then carries)
- **`apex:postgres-review`** (sibling — the DDL + lock-strategy half of the same change; run both, they cover disjoint surfaces)
- **`apex:multi-tenancy`** (the per-tenant batching + isolation this gate's Pass 5 checks)
- **`apex:verification-before-completion`** (downstream — proves the reconciliation actually ran green before contract)

## Adversarial counter-pass — read this first

Every pass below has an inline adversarial counter-pass. Data migrations reward adversarial framing because the happy path always looks fine in a 10-row dev table — the failures only appear at production scale, at the crash mid-run, at the row the validator didn't sample. The cooperative half asks *"does this backfill do the right thing?"*; the adversarial half asks *"what does this backfill do when it's killed at 50%, retried, or hits the one weird row?"*

## Pre-flight: anchor on the move

Before running the 5 passes, restate:

- **Source and target shape** — what rows exist now (count, growth rate), what shape they end in, and the exact per-row transform applied
- **Volume + window** — how many rows *on prod*, not on the dev fixture; how long the backfill runs; what else hits that table during the window
- **Source of truth during the move** — old shape, new shape, or "both, reconciled" (Pass 3 makes this explicit)
- **The phasing** from `apex:impl-plan-review` Pass 4 — where the expand / migrate / contract boundaries already are (this gate audits *within* them; it does not re-derive them)

If the prod row count is "I don't know," that's the first finding — STOP, get the count, then continue; a backfill plan written against an unknown cardinality is a guess. (The "this move isn't decomposed into phases at all" case is Pass 1's fail path, not a separate pre-flight gate.)

## The 5 passes

### Pass 1 — Data-level coexistence within the phasing

**Check:** `apex:impl-plan-review` Pass 4 already decomposed the move into expand / migrate / contract phases — this pass does **not** re-derive that phasing; it audits that the per-row transform respects the coexistence window the phasing assumes.

- Old and new shape genuinely COEXIST at every step at the *row* level — not just "there are three PRs," but: for any row, both old code and new code can read a valid value throughout the window.
- The destructive step (drop / rewrite-in-place) is a separate, later phase gated on validation (Pass 3) — never the step that also transforms the data.
- No reader is deployed that depends on the new shape before the backfill has reached its rows; none depends on the old shape after it's dropped.

**Why:** A migration can have a clean three-PR phasing on paper and still strand a row if the *transform* doesn't honor coexistence — e.g. it rewrites in place inside the "migrate" PR, so a single bad row or a revert leaves readers with neither shape. The canonical loss is "we rewrote the column in place and the parse failed on row 3M."

**Pass condition:** The phasing from impl-plan-review Pass 4 is present (if absent → first finding: STOP and push back to `apex:impl-plan-review` Pass 4 to decompose before this gate can run). Within it, no phase both transforms data and removes its old form; the destructive step is named as a *separate, later* phase gated on validation.

**Adversarial counter-pass:** Find the destructive step. Walk back: is there any *instant* where a deployed reader expects the new shape but the backfill hasn't reached its rows yet — or expects the old shape after it's been dropped? If you can name one row readable in neither shape at some instant, coexistence is broken even if the PR phasing looks right.

### Pass 2 — Backfill design: batched, idempotent, resumable, throttled, observable

**Check:** The backfill itself is operationally safe to run, re-run, and survive.

- **Batched** — bounded batch size (N rows / key range per iteration); never one transaction over the whole table.
- **Idempotent** — safe to re-run from the top; re-processing an already-migrated row is a no-op, not a double-apply (guard on a marker column / `WHERE new IS NULL` / upsert key — no `count = count + 1` that runs twice).
- **Resumable** — checkpointed (last-processed key persisted); a crash mid-run resumes from the checkpoint, not from row 0.
- **Throttled** — paced so it won't saturate the primary (sleep between batches, replica-lag watch). *Per-batch lock strategy and statement timeouts are `apex:postgres-review`'s — this pass only requires that pacing exists; postgres-review sizes it.*
- **Observable** — progress is queryable (rows done / total, ETA, error count) so the operator at 2am can see where it is, and a stuck or erroring backfill is *visible*, not silent.

**Why:** A backfill that isn't idempotent double-applies on retry; one that isn't resumable restarts from zero after an OOM at 90%; one that isn't throttled takes the primary down at peak; one that isn't observable stalls at 30% and nobody knows. Each is its own incident.

**Pass condition:** The backfill names its batch size, its idempotency guard, its checkpoint mechanism, its throttle/pacing rule, and the progress signal an operator reads mid-run. "Run a single UPDATE" fails this pass.

**Adversarial counter-pass:** Kill the backfill at a random batch. Restart it. Does it (a) resume near where it stopped and (b) leave zero rows double-applied or skipped? Then: run two copies concurrently by accident. Does idempotency still hold, or do they race the same rows? If either answer is no, it isn't idempotent + resumable — name the row class that breaks.

### Pass 3 — Consistency model during the window

**Check:** While old and new coexist, the truth and the reconciliation are explicit.

- **Source of truth** named for the window (old / new / both) — and which path serves reads.
- **Dual-write** (if used) — both shapes written in the same transaction, or a compensating reconciliation catches the gap if they diverge.
- **Reconciliation / validation step** that proves `old == new` (or a defined transform holds) across the WHOLE set, not a sample — and runs *before* contract.
- **Drift after backfill** — rows written *during* the backfill window by live traffic are caught (the backfill's `WHERE` re-sweeps them, or dual-write covered them), and a stale transform can't clobber a fresher live write.

**Why:** The backfill that ran clean and the table that's correct are different claims. Live writes during the window, a dual-write that committed one side and crashed, a transform that's wrong for one enum value — all produce a table that *looks* migrated and isn't.

**Pass condition:** Source of truth is named for the window; a reconciliation that compares old vs new across the full set is specified and gates contract; rows mutated mid-window are provably covered.

**Adversarial counter-pass:** A user updates row R *while* the backfill is between "read R's old value" and "write R's new value." Which value wins? Walk the interleaving. If the answer is "the backfill clobbers the user's live write" or "they silently diverge," dual-write/reconciliation has a hole — name it and force a reconcile-late-writes step.

### Pass 4 — Mid-flight reversibility (partial-completion safety)

**Check:** You can stop and abandon the *backfill run itself* at 10% / 50% / 90% done, leaving a valid table. (Distinct from `apex:impl-plan-review` Pass 5, which asks "is each PR git-revertible?" at the stack level — this asks "is the table valid if the backfill is killed mid-run?" at the run level. Pass 1's coexistence + Pass 2's idempotency are the *preconditions*; this pass audits the **abort and the irreversible-step gating** that aren't covered anywhere else.)

- **A stopped backfill is a tested control**, not "Ctrl-C and hope" — Pass 5's kill-switch is the mechanism; this pass requires it actually leaves the table valid (no half-typed rows, no torn dual-write).
- **The destructive contract step is gated on validation passing** (Pass 3) and does **not** auto-fire on backfill completion — a backfill that reaches 100% with a failing reconciliation must NOT drop the old shape.
- **Any genuinely irreversible step** (paid external one-shot, true in-place overwrite with no old shape retained) is named, justified, and sequenced *last* behind a manual gate — these are the only steps Pass 1's coexistence can't protect, so they get explicit sign-off here.

**Why:** Reversibility is the difference between "we aborted the backfill at 40% and nothing broke" and "we're committed, finish it or the table's corrupt." Most useful whole-migrations aren't reversible — which is exactly why the *abort path* and the *irreversible steps* must be named, not assumed.

**Pass condition:** Aborting the backfill at any % leaves a valid table (stated, not assumed). Contract is explicitly gated on a passing reconciliation and never auto-fires on completion. Every irreversible step is named + justified + sequenced last behind a manual gate.

**Adversarial counter-pass:** Abort the backfill at exactly 50% and walk the table: are the migrated rows still readable by old code, and the un-migrated rows still readable by new code? Then: force the reconciliation to FAIL at 100% — does the contract step still fire? If the abort strands a row, or contract auto-drops the old shape on completion regardless of reconciliation, name the gap.

### Pass 5 — Blast radius + isolation

**Check:** The move is bounded so a problem stays small.

- **Per-tenant batching** where multi-tenant — one tenant's backfill can't bleed into another's rows; a bad batch hits one tenant, not all (cross-ref `apex:multi-tenancy`).
- **Kill-switch** — a single operator control that halts the backfill cleanly *now without a deploy* (and, given Pass 2/4, safely resumable or abandonable after).
- **Canary** — run against one tenant / one shard / a sampled key range first; validate; then widen.
- **Error budget** — a per-batch error threshold that auto-pauses (not just continues logging) so a transform wrong for one data shape stops itself instead of corrupting the whole set.

**Why:** Blast radius is what turns "one tenant's batch was wrong" into "we corrupted everyone." An unbounded backfill with no kill-switch and no canary is a self-inflicted outage with no abort. (Lock/contention impact on the live table is real but is `apex:postgres-review`'s surface — size it there.)

**Pass condition:** Multi-tenant backfills batch per-tenant with no cross-tenant write; a no-deploy kill-switch exists; round 1 is a canary (one tenant/shard/sample), not 100%; an error threshold auto-pauses the run.

**Adversarial counter-pass:** The backfill's transform is wrong for one enum value / one tenant's data. With the current batching + canary + error-budget plan, how many rows are corrupted before the run pauses itself? If the answer is "the whole table" (no canary, no per-tenant bound, no error threshold), the blast radius is unbounded — name the missing bound.

## Adversarial pair pattern (heavier — for high-volume / irreversible moves)

The inline counter-passes are the cheap version. For high-blast-radius moves (≥ tens of millions of rows, cross-DB relocation, a re-type with a lossy transform, or any multi-tenant backfill), dispatch the review as **two parallel agents** via `superpowers:dispatching-parallel-agents`:

- **Cooperative agent** — runs the 5 passes in steelman mode. Confirms the coexistence, idempotency, reconciliation, abort path, and bounds are present and well-placed.
- **Adversarial agent** — runs the same in attack mode. Each counter-pass becomes the primary lens: the kill-at-50% abort, the live-write interleaving, the reconciliation that fails but contract fires anyway, the one-weird-row transform, the canary that wasn't.

Reconcile findings. Document accepted residual risk explicitly — a known-lossy transform that's been signed off is fine; a hidden one is the incident.

## Output: Data Migration Plan section

The output is a `## Data Migration Plan` section appended to the feature's `impl-plan.md` (or design doc), which `apex:impl-plan-review` carries and reviewers audit against the actual run:

```markdown
## Data Migration Plan

**Move:** <source shape → target shape; the per-row transform; ~N rows; growth rate>
**Phasing:** expand <PR#> → migrate <PR#> → contract <PR#>   (destructive step: <which>)
**Source of truth during window:** <old / new / both-reconciled>

### Backfill
- Batch size: <N> · Idempotency guard: <how> · Checkpoint: <how> · Throttle: <rule>
- Progress signal: <query / dashboard the operator reads mid-run>

### Reconciliation (gates contract)
- Validation: <old==new across full set, how + where it runs>
- Mid-window drift handling: <re-sweep / dual-write coverage>

### Safety
- Kill-switch: <the control, no-deploy> · Canary: <one tenant/shard/sample first>
- Per-tenant batching: <yes/no — if multi-tenant> · Error threshold: <auto-pause rule>
- Abort at partial completion: <leaves valid table because Y>
- Irreversible steps: <named + sequenced last + signed off> · Accepted residual risk: <if any>
```

## Invariants (do not break)

- **Read-only on the artifacts.** This reports; a human re-opens `apex:impl-plan-review` Pass 4 and amends the plan there (apex's author/review separation). It never edits the impl-plan or the migration code.
- **Audits within the phasing; does not author it.** The expand/migrate/contract decomposition is impl-plan-review Pass 4's; this gate assumes it and verifies data-safety inside it — it does not re-sequence PRs.
- **Schema is not its surface.** Lock strategy, index/online-DDL, and statement timeouts are `apex:postgres-review`'s; this gate moves the data and stops at the schema boundary.
- **Contract is never automatic.** The destructive step is gated on a full-set reconciliation and a human gate — never auto-fired on backfill completion.

## Pass/fail summary

The data migration passes if:

- All 5 passes meet their pass conditions
- Adversarial counter-pass findings are addressed
- The destructive contract step is gated on a full-set reconciliation, every partial-completion point leaves a valid table, and every irreversible step is named + signed off

Fail any → revise before the backfill is written. A corrupted-backfill gap caught at design time costs minutes; caught at run time costs a 2am page; caught after contract costs a restore-from-backup + the rows written since — the one failure class apex can't `git revert`. Findings route back to `apex:impl-plan-review` Pass 4/5 (re-phase / re-sequence) or to this design doc.

## Relationship to other skills

- **`apex:impl-plan-review`** (upstream) — Pass 4 owns the expand/migrate/contract *sequencing* this gate audits within; Pass 5 owns *stack-level* git-revertibility while this owns *run-level* abort safety. Findings route back here to re-phase.
- **`apex:postgres-review`** (sibling) — the DDL + lock-strategy half of the same change; run both, disjoint surfaces.
- **`apex:multi-tenancy`** — per-strategy isolation detail for the per-tenant batching named in Pass 5.
- **`apex:verification-before-completion`** (downstream) — prove the reconciliation ran green *before* contract is allowed.
- **`apex:incident-retro`** — if a migration still escapes to production, map the miss back to whichever pass here didn't fire, closing the loop on apex.
