---
name: cicd-review
description: Pipeline-as-code authoring + review gate — 5-pass audit whenever CI/CD workflow files are created or edited (.github/workflows/**, .gitlab-ci.yml, Jenkinsfile, azure-pipelines.yml, Dockerfile used in CI): trigger + privilege surface (least-privilege permissions, pull_request_target injection, fork-secret exposure), supply chain (SHA-pinned actions, no curl|bash, cache poisoning), pipeline structure (jobs mapped to apex:test-strategy CI tiers, timeouts, concurrency), secrets + identity (OIDC federation over long-lived cloud keys, no secrets in logs), and determinism + debuggability (lockfile installs, actionable failure output). Treats the pipeline as a PRIVILEGED PROGRAM that runs other people's input. Distinct from apex:security-review (audits the application code the pipeline builds) and apex:deployment-review (audits what the pipeline deploys INTO). Pairs with apex:test-strategy (the tier map Pass 3 enforces) and apex:release-readiness (Pass 4 wants releases to run here). Keywords: CI, CD, pipeline, GitHub Actions, workflow, .github/workflows, gitlab-ci, Jenkinsfile, azure-pipelines, build, runner, OIDC, pinned action.
---

# CI/CD Review (pipeline-as-code gate)

A CI workflow is a **privileged program that executes other people's input** — it holds tokens, runs on every PR including a stranger's fork, and writes to the repo, registries, and clouds. apex reviewed the code the pipeline builds, but never the pipeline. This gate closes that — for authoring a new pipeline and for any edit to an existing one. GitHub Actions is the worked surface; every pass states the platform-neutral rule first.

## Pass 1 — Trigger + privilege surface

- **Least privilege, explicitly:** the workflow (or each job) declares the narrowest token scope — GH Actions: top-level `permissions: contents: read`, widened per-job only where needed. An absent `permissions:` block inherits the repo default — that's a finding, not an omission.
- **The `pull_request_target` / `workflow_run` trap:** any workflow that combines a privileged trigger with a checkout of PR-controlled code is an RCE-with-secrets. Require the split pattern (unprivileged build → privileged comment/label job that checks out nothing of the PR's).
- **Untrusted interpolation:** PR titles, branch names, issue bodies inside `run:` blocks are shell injection (`${{ github.event.pull_request.title }}` is attacker input). Route via `env:` and quote.
- Fork PRs: confirm secrets are NOT available to fork-triggered runs unless explicitly intended and gated by an environment approval.

**Adversarial counter:** *you are a malicious PR author.* What can your PR make this workflow execute, exfiltrate, or write? Walk each job as the attacker before approving.

## Pass 2 — Supply chain

- Third-party actions/orbs/plugins pinned by **full commit SHA** (tag-pinning trusts a movable ref — the tj-actions/changed-files compromise traveled exactly that way). First-party (`actions/*`) may pin major.
- No `curl | bash` of unversioned installers; toolchains via pinned setup actions or locked manifests.
- Cache keys must not let an untrusted branch poison a trusted branch's cache (key on lockfile hash + ref scope).
- Build artifacts that ship to users come from THIS pipeline's checkout of a tag — not from an artifact a previous, less-trusted job uploaded.

**Adversarial counter:** for each external dependency the pipeline pulls at runtime, ask "what happens the day it's compromised?" — every answer of "we'd ship it" needs a pin or a checksum.

## Pass 3 — Pipeline structure (the tier map, mechanized)

- Each job maps to a named `apex:test-strategy` CI tier (PR / 4h / nightly / weekly-drift). A 40-minute suite on the PR tier is a structure defect — split it, don't accept it.
- `timeout-minutes` on **every** job (the default is 6 hours of billed hang).
- `concurrency` group + `cancel-in-progress` for PR-triggered runs; deploy jobs get a concurrency group WITHOUT cancel (a half-cancelled deploy is worse than a queued one).
- Fail fast and loud: no `continue-on-error` masking required checks; matrix jobs that may legitimately fail are explicitly marked experimental.

## Pass 4 — Secrets + identity

- **Cloud auth via OIDC federation, not stored long-lived keys** — GH Actions: `id-token: write` + the cloud's official auth action (AWS `configure-aws-credentials` role-assume / Azure `azure/login` federated credential / GCP workload-identity). A stored `AWS_SECRET_ACCESS_KEY` is a standing finding with a migration path.
- Secrets reach only the jobs that need them (job-level `environment:`, not workflow-global env).
- Nothing echoes secrets: no `env` dumps, no `set -x` in steps that touch them, no secrets in artifact uploads.
- Deploy jobs target a GitHub **environment** with protection rules (required reviewers on prod) — that's where human sign-off lives, not in a chat message.

## Pass 5 — Determinism + debuggability

- Installs are lockfile-driven (`npm ci` not `npm install`; frozen/locked resolution everywhere) — a pipeline that resolves "latest" produces unreproducible greens.
- A failed run tells the operator **what to do** from the log alone — failing test names surfaced, not buried in 10k lines; artifacts (junit, screenshots) uploaded on failure.
- Re-run safety: every job is idempotent (a re-run of a half-failed release job must not double-publish — guard with "does the tag/release already exist?" checks).

**Adversarial counter (whole-pipeline):** simulate the 3 ugliest runs — a malicious fork PR, a re-run after a partial failure, and a green run on a poisoned cache. Name the pass that catches each; a scenario nothing catches is the finding.
