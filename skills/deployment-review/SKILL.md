---
name: deployment-review
description: Deploy + infrastructure gate — 5-pass audit when a change alters HOW software reaches an environment (deploy workflows, IaC, environment promotion, runtime infra): deploy identity (OIDC/workload-identity over static keys, least-privilege deploy role, per-cloud worked notes for Azure / AWS / GCP), environment promotion (build once → promote the SAME artifact, config from the environment), rollout shape (health-gated cutover, canary/blue-green justified against all-at-once, sequencing against data migrations), rollback BEFORE deploy (previous artifact retained, time-to-rollback bounded, not-rollback-safe steps flagged), and IaC review (plan-as-review-artifact, state isolation, no secrets in state). Instantiates architecture-design Pass 4's deploy-model decision per-change, the way observability-review instantiates its observability half. Distinct from apex:cicd-review (the pipeline that RUNS the deploy; this is what the deploy does to the world) and apex:data-migration-review (the data inside the window; this is the sequencing around it). Keywords: deploy, deployment, Azure, AWS, GCP, terraform, bicep, pulumi, cloudformation, helm, kubernetes, IaC, environment, staging, production, canary, blue-green, rollback, promote.
---

# Deployment Review (the deploy + infra gate)

`architecture-design` Pass 4 chooses the deploy model once; nothing audited the changes that implement it. This gate fires when a diff alters **how software reaches an environment**: deploy workflow steps, IaC (Terraform / Bicep / CloudFormation / Pulumi / Helm), environment config, runtime infra. Platform-neutral rule first; Azure / AWS / GCP notes where mechanics genuinely differ.

## Pass 1 — Deploy identity + blast radius

- **Workload identity, not static keys:** the deployer authenticates via OIDC federation — AWS: assumed role via OIDC provider; Azure: federated credential on a managed identity / app registration; GCP: workload identity federation. A long-lived cloud key in CI secrets is a standing finding with a migration path.
- **Least-privilege deploy role:** scoped to the resources this pipeline deploys (one role per app/env beats one god-role per org). Ask: *if this role's token leaks, what's the blast radius?* — the answer is the role's review.
- Prod deploys pass a protected environment (required reviewer / approval gate) — sign-off is infrastructure, not a chat message.

**Adversarial counter:** steal the deploy credential on paper and enumerate what you can read, write, and delete with it. Everything beyond "deploy this app to this env" is scope to cut.

## Pass 2 — Environment promotion

- **Build once, promote the same artifact** (image digest / wheel / bundle) through dev → staging → prod. A prod rebuild "from the same commit" is a different artifact — different base-image pull, different dependency resolution that day.
- Config comes from the **environment**, not the build: same artifact + env-supplied config/secrets. A baked-in prod URL is a finding.
- Staging is prod-shaped where it matters (same migration path, same runtime major version); name the known divergences instead of pretending parity.
- Pin by digest/exact version in the deploy spec — `:latest` deploys are unreproducible by construction.

## Pass 3 — Rollout shape

- The cutover is **health-gated**: a real readiness signal (the app answered a meaningful check, not "container started") gates traffic shift; failed health = automatic halt/rollback, not an operator watching a dashboard.
- Canary / blue-green / rolling / all-at-once is a **justified choice** per change, not a default: blast radius × reversibility decides. All-at-once is fine for a stateless low-traffic service; it's a finding for a schema-coupled hot path.
- **Sequencing against data:** deploys interleave with migrations per expand→migrate→contract — expand ships before the code that needs it; contract ships after the compat window closes (`apex:data-migration-review` owns the data inside; this pass owns the ordering around it).
- Feature flags decouple deploy from release where the change is user-visible and risky — deploying dark is cheaper than canarying everything.

## Pass 4 — Rollback (decided before, not during)

1. The previous artifact is retained and **deployable right now** (registry retention; the rollback target named in the deploy PR).
2. Time-to-rollback is bounded and stated ("redeploy previous digest, ~4 min"), not "rebuild old commit" (that's restore-from-source, not rollback).
3. **Not-rollback-safe steps are flagged in the plan:** contracted schema, consumed queue messages, third-party side effects (emails sent, payments captured). Each gets a forward-fix note instead of a pretend-rollback.
4. Rolling back the app does NOT silently roll back data — state the data story for a rollback during the migration window.

**Adversarial counter:** it's 2am, the deploy is bad, the author is asleep. Walk the actual rollback from the runbook/PR text alone. Every step requiring tribal knowledge fails the pass.

## Pass 5 — IaC review (when IaC is in the diff)

- **The plan is the review artifact:** `terraform plan` / `what-if` / `diff` output is posted on the PR; an apply that doesn't match a reviewed plan is the incident. Apply runs in CI (per `apex:cicd-review`), not from a laptop.
- State is remote, locked, and access-controlled — state files contain secrets-in-effect; nobody's laptop holds prod state.
- Resources carry the same least-privilege discipline as Pass 1 (no `*` IAM in checked-in policy documents without a stated reason).
- No secrets in IaC source or state where avoidable — reference the secret manager (Key Vault / Secrets Manager / Secret Manager), don't inline values.
- Destructive plan lines (`destroy`, `replace`) are called out explicitly in the PR description — a replace on a database is a data-migration event wearing an infra costume; route it to `apex:data-migration-review`.

**Adversarial counter:** read the plan output looking only for `destroy`/`replace` and for resources whose disappearance loses data. Then ask what drift exists between state and reality — when did anyone last run a no-change plan?
