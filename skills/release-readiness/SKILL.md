---
name: release-readiness
description: Release gate + mechanics for the USER'S project (not apex's own releases) — 5-pass discipline between "the PRs are merged" and "users are running it": semver decision audited against the actual diff since the last tag, changelog written for users, a release-readiness gate (tests green at the release SHA, migration + config notes present, rollback path stated BEFORE shipping), tag/build/publish mechanics (build from the tag, never the working tree), and a post-release bake watch that feeds apex:incident-retro. Closes the pipeline gap after FLOW.md phase 7 — apex previously had no SHIP phase. Distinct from apex:deployment-review (HOW the artifact reaches an environment; this is WHETHER/WHAT to release) and impl-plan-review Pass 4 (per-feature rollout inside the plan; this is the project-level release event). Pairs with apex:data-migration-review (its notes feed Pass 3), apex:observability-review (its dashboards are the bake watch), and apex:incident-retro (where a bad bake lands). Keywords: release, ship, publish, version, semver, tag, changelog, release notes, rollback, cut a release, bake.
---

# Release Readiness (the SHIP gate)

Merged is not shipped. This skill is the gate between "the PR stack landed" and "users are running it" — the phase apex's pipeline previously ended without. Five passes, each with an inline adversarial counter.

## YAGNI guard

Not every push is a release. A docs fix on a continuously-deployed service doesn't need this ceremony — `apex:deployment-review`'s rollout shape already covers it. This gate fires for **versioned release events**: anything users pin, download, depend on, or must be told about (libraries, plugins, CLIs, APIs with consumers, mobile builds, and milestone releases of services).

## Pass 1 — Version decision (semver against the diff, not the vibe)

Diff the release candidate against the **last tag** (`git log <last-tag>..HEAD`, plus the API surface). Then decide:

- Removed/renamed/retyped anything a consumer could hold? → **MAJOR**.
- New user-visible capability, backward compatible? → **MINOR**.
- Behavior-preserving fixes only? → **PATCH**.

**Adversarial counter:** hunt the diff for the bump's contradiction — a "patch" containing a changed default, a tightened validation, a dropped field. Defaults and error shapes are API. Pre-1.0 is not a semver pass — say what breaks anyway.

## Pass 2 — Changelog + release notes (written for users)

Every user-visible change since the last tag has a line; internal refactors don't. Notes answer the user's three questions: *what's new for me / what breaks for me / what must I do* (migration steps first, not buried). Keep a Changelog format; the `[Unreleased]` section becomes the dated version section at release time.

**Adversarial counter:** read the notes as a user who has NOT seen the PRs. Every sentence that needs repo context to parse gets rewritten. An empty "breaking changes" section on a MAJOR bump is a defect in the notes or in Pass 1 — find which.

## Pass 3 — Readiness gate (the checklist that blocks the tag)

All of, at the **exact SHA to be tagged**:

1. Full suite green at that SHA (not "was green before the last merge").
2. CHANGELOG section dated; version bumped in every manifest that carries it (package.json / pyproject.toml / plugin.json / …) — grep for the OLD version string to catch stragglers.
3. Schema/data migrations documented with their expand→migrate→contract phase noted (from `apex:data-migration-review` if it ran).
4. New/changed config + env vars documented with defaults.
5. **Rollback path stated before shipping:** previous artifact retained and installable? DB rolled forward past the compat window? The release notes' "downgrade" line is written NOW, while sober.

**Adversarial counter:** the 2am question — a critical bug surfaces an hour post-release; walk the actual rollback steps. Any step that reads "figure it out then" fails the gate.

## Pass 4 — Mechanics (tag → build → publish, in that order)

1. Annotated tag at the released SHA (`git tag -a vX.Y.Z`), pushed before the release object exists. **Never delete-recreate a pushed tag** — published releases get knocked into drafts and consumers' caches diverge; a bad tag means a new patch version.
2. **Build from the tag, not the working tree** (`git archive <tag>` or CI checkout of the tag) — working trees carry uncommitted state.
3. Publish the release with the notes + artifacts; verify it landed (correct tag target, assets attached, latest-flag correct).
4. Script it — a release done by hand twice is a script not yet written (apex's own `scripts/release.sh` is the reference shape: validate → bump → commit → tag → build → publish, failing closed at each step). Prefer running it in CI on tag-push (see `apex:cicd-review`) so releases don't depend on one laptop's auth state.

## Pass 5 — Post-release bake

Define **before** shipping: the bake window (e.g. 24h), the 2–3 signals to watch (error rate, latency SLI, install/upgrade failures — from `apex:observability-review`'s contract), and the abort criteria that trigger Pass 3's rollback. Regression during the bake → roll back first, debug second; afterwards route to `apex:incident-retro` with the gate-miss question: which pass should have caught it?

**Adversarial counter:** if the bake watch has no signal that could possibly fire (no telemetry, no error reporting), say so explicitly — "we will learn about breakage from users" is a legitimate but **stated** choice, not a default.
