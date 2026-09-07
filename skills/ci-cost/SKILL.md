---
name: ci-cost
description: CI billing audit — investigative procedure for "the CI bill is too high" / "GitHub Actions minutes are out of control" / runner-spend review: measure real runs against actual wall time via the Actions jobs API, attribute the gap per job and per trigger lane, model cost levers by REPLAYING real runs through each proposed shape rather than estimating, then report the trade (wall-clock, failure-reporting semantics) each lever costs. Core finding this skill teaches: CI platforms round every job's billed time up independently, so job COUNT drives the bill more than job DURATION — consolidating sub-minute jobs into steps is usually the dominant lever, and cutting test CPU after that consolidation rarely moves the number. Distinct from apex:cicd-review, which is a REVIEW GATE fired by editing workflow files (.github/workflows/**) auditing trigger/privilege, supply chain, structure, secrets, determinism — cicd-review's only cost-adjacent line is PR-tier latency, not billing, and it does not fire when no workflow file changed. This skill fires on the billing question itself, whether or not any YAML is being touched, using `gh api` against the Actions runs/jobs endpoints (not a workflow-file read) as its evidence source. Pairs with apex:cicd-review Pass 3 (the CI-tier structure this skill's job-consolidation lever reshapes) and apex:test-strategy (the tier map jobs get folded within). Keywords: CI cost, CI spend, GitHub Actions billing, billable minutes, minute rounding, runner minutes, cost audit, job consolidation, cancel-in-progress, path filtering, workflow cost, Actions API, gh api, committed generated artifacts, merge conflict churn.
---

# CI Cost Audit (billing investigation)

Most CI platforms bill in a fixed rounding quantum per job, not per run — GitHub Actions rounds every job up to the **next whole minute, independently of every other job in the run**. That means job **count** drives the bill at least as much as job **duration**: five 10-second jobs cost 5 billable minutes for 50 seconds of real work. This skill is the procedure for finding and fixing that gap. It is an **investigation**, not a checklist: measure, attribute, model by replay, then report the trade. Skipping the replay step and going straight from measurement to a recommended shape is the most common way this audit goes wrong — an estimate and a replay of the same lever set have landed 17 percentage points apart in practice, in the estimate's favor, which is the expensive direction to be wrong in.

## Step 1 — Measure: billable vs. actual, from the jobs API

Pull every run of the workflow in question, then per-run job timings — page until a response returns fewer than `per_page` runs:

```bash
# every run of a workflow — .event and .head_branch are what Step 2/3 bucket by
gh api "repos/OWNER/REPO/actions/runs?per_page=100&page=N" \
  --jq '.workflow_runs[] | select(.name=="ci") | [.id,.event,.head_branch,.created_at] | @tsv'

# per-job timings AND step shape, for one run — .run_id joins back to the query above
gh api "repos/OWNER/REPO/actions/runs/<id>/jobs?per_page=50" \
  --jq '.jobs[] | [.run_id,.name,.conclusion,.started_at,.completed_at,([.steps[].name]|join("|"))] | @tsv'
```

Join job rows back to their run's `.event`/`.head_branch` by `run_id` — that's what Step 2's trigger-lane buckets and Step 3's cancel-in-progress replay need. The trailing `.steps[].name` join gives Step 2's job-shape heuristic (checkout + one package-manager step, nothing else) without a second query.

Compute `billable = Σ ceil(job_seconds / 60)` (skipped jobs = 0) and `actual = Σ job_seconds`. Report `(billable − actual) / billable` as the **rounding share** of the bill — on one audited repo across 515 runs this was 60% (2,638 billable minutes against 1,056 actual), driven by five jobs averaging 4–19 seconds each that alone burned 1,551 billable minutes.

Two endpoints look tempting and are traps: `/actions/runs/<id>/timing` returns `total_ms: 0` on some plans — don't rely on it, compute from job `started_at`/`completed_at` instead. The org billing endpoint (`/orgs/{org}/settings/billing/actions`) now returns 410, and its replacement needs `admin:org`; the jobs API above is the route that works from a normal repo token.

**Adversarial counter:** *assume the rounding share is small.* If it comes back under ~20%, the bill is duration-dominated, not count-dominated — stop here and profile the slow jobs directly (a `apex:test-strategy` tiering problem) rather than reaching for consolidation, which won't move a duration-dominated bill.

## Step 2 — Attribute: per job, per trigger lane

Bucket the same job data by job name and by triggering event (`pull_request`, `push` to trunk, `merge_group`, `schedule`), using the `run_id` join from Step 1. Sub-minute jobs are the rounding-loss concentration — rank jobs by `actual_seconds` ascending and check their `steps` join for anything doing only checkout + a package-manager step; that's a job-shaped step. Separately, compare the PR lane's job set against the trunk lane's: repos commonly path-filter expensive jobs (frontend, docker builds) on PRs and then run them unconditionally on trunk, paying full cost on every merge for work the PR diff never touched — confirm this with each trunk run's changed files (`gh api repos/OWNER/REPO/commits/<sha>` or the merged PR's `files` endpoint) against the PR lane's existing path filter.

**Adversarial counter:** *assume every job earns its place.* For each job, ask "what does removing this job as a separate job (folding it into a step of another job) break?" — a required-check job that must independently REPORT red/green to the branch-protection rule does NOT fold; everything else is a candidate.

## Step 3 — Model levers by replaying real runs

Don't estimate savings — replay the actual 515 (or however many) real runs through each candidate shape and recompute `billable`. An estimate is a guess about job-boundary crossings; a replay is arithmetic on real timestamps. In measured order of effect:

1. **Consolidate sub-minute jobs into one job, as steps.** Anything needing only checkout + a package manager belongs as a step, not a job. Give each folded step `if: ${{ !cancelled() }}` so one red step doesn't hide the rest, while the job as a whole still reports failed if any step failed. Replay: for each candidate group, sum the group's `actual_seconds` per run and re-`ceil` once instead of per job, then re-sum across all runs. Measured: −29% like-for-like on 18 real runs.
2. **Keep the required check as its own job.** Branch protection's required-status-checks match against a **job's check-run**, not a step inside one — folding the required check into a step of the big job erases its independent check-run identity, so branch protection has nothing named left to gate on, regardless of `if: ${{ !cancelled() }}` keeping the step itself running. This one minute is not the place to economize.
3. **`cancel-in-progress` on the trunk push lane, not just PRs — but exclude `merge_group`.** A newer commit on trunk contains the older one, so the surviving run covers it. Replay: group job rows by `head_branch`, sort by `created_at`, and mark a run "would-cancel" when a later run on the same branch started before it completed — but only its still-in-flight jobs stop; any job that had already completed before cancellation still billed for that time, so sum only the *unbilled remainder* of the cancelled jobs, not the whole run. Cancelling a `merge_group` run instead drops the commit actually being merged, so exclude that event from the grouping entirely.
4. **Path-filter the trunk lane the same way the PR lane is filtered.** If frontend/docker jobs are already path-filtered on `pull_request`, apply the same filter on `push` to trunk. Replay: for each trunk run, pull its changed files (the commits-API call from Step 2) and re-evaluate the PR lane's path filter against them — sum the billable minutes of jobs that would have been skipped.

**The counter-intuitive result:** once everything sub-minute is folded into one job, cutting test CPU barely moves the bill — the saving usually fails to cross a minute boundary. In one modelled case an 18% CPU reduction moved a projection from 3,621 to 3,500 minutes/month. Optimize runtime for **latency**; optimize job **count** for **cost**. Conflating the two wastes the effort spent on whichever one wasn't the actual lever.

**Adversarial counter:** *assume the estimate is close enough to skip the replay.* It wasn't, by 17 percentage points, in the direction that looks like success until the real numbers land. Replay every lever combination that will be recommended before writing the report, not after.

## Step 4 — Report the trade, per lever

Every lever in Step 3 has a cost; state it, don't bury it:

- **Wall-clock rises when steps replace jobs.** Steps inside one job run sequentially; the jobs they replaced may have run in parallel. Billing falls, latency rises — say which one the audience actually asked to fix.
- **A job's `outputs` only exist once the whole job finishes.** A consumer job that depended on one of the folded jobs' outputs now starts later (after the whole consolidated job, not after the sub-step). If the consolidated job fails, the consumer is **SKIPPED**, not run-and-reported — one extra round trip in the case where both a gate and a test are broken at once.

## What doesn't work (state plainly — these are the two people reach for first)

- **Batching CI to a schedule.** If the required check doesn't run per-PR, PRs block forever waiting on a check that never reports against that commit. It also saves nothing — it delays runs, it doesn't remove them; the same jobs still execute, just later.
- **Reducing PR count.** Measure the re-push churn ratio (`runs / distinct branches`) before assuming there's slack here — on one audited repo, 293 PR runs across 195 branches was 1.5 runs/branch, almost no re-push churn to squeeze. Cutting PRs there would have cut throughput, not cost.

## A second, related audit: committed generated artifacts

Separately worth checking — files a build script generates but that got committed anyway. Pick `-<N>` to cover the longest-lived branch's history (a few hundred to a thousand commits is usually enough — this is exploratory ranking, not a threshold gate):

```bash
git log -<N> --format='%H' | while read c; do git show --name-only --format='' $c; done \
  | sort | uniq -c | sort -rn | head -20
```

Generated HTML/JSON views that top this list cost little CI by themselves (their diffs are docs-only and narrow well) but are frequently the top merge-conflict source on long-lived branches. The fix is to `.gitignore` them and build on demand — but check first whether anything **serves** them directly from the repo, and whether a hub/index test asserts their links resolve, before removing them from version control.

## Distinct from / pairs with

- **`apex:cicd-review`** — reviews the pipeline **as code**, fired by editing `.github/workflows/**` (or equivalent), auditing trigger/privilege, supply chain, structure, secrets, determinism. It reads YAML. This skill queries the Actions API and replays real runs; it fires on the billing question, not on a workflow diff. Pass 3 of `cicd-review` maps jobs to CI tiers — this skill's job-consolidation lever reshapes that same tier map, so run them together when a cost fix changes workflow structure.
- **`apex:test-strategy`** — owns which layer of tests runs at which CI tier and the runtime budget per tier. If Step 1's rounding share comes back low (duration-dominated, not count-dominated), the fix is a `test-strategy` tiering problem, not a `ci-cost` consolidation problem.
