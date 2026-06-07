---
name: detect-stack
description: Profile a project's bug-loop tooling — probe deps / CI configs / connected MCP servers + git remote, then write a routing-only, secret-free `apex.profile.toml` that `apex:investigate-bug` reads to route each axis (issue tracker / observability / reproduce) through whatever the project actually has. Auto-fills what it can infer; prompts (never guesses) for the rest; on conflicting signals it records the conflict and asks, never silently picks. Distinct from `apex:setup` (which installs apex's own companions) and `apex:recon` (which gathers code-graph facts for a design). Fires before the first `apex:investigate-bug` run in a repo, or to refresh the profile when the stack changes. Pairs with apex:investigate-bug (the consumer of the profile) and apex:autonomous-fix (the write gate investigate-bug hands off to). Keywords: detect stack, stack profile, apex.profile.toml, adapter routing, tracker, observability, MCP discovery, bug-loop tooling, routing config.
---

# Detect Stack

Writes the **routing config** the stack-adaptive bug loop runs on. The bug → diagnose → fix loop touches a project's tooling at three independent axes — **issue tracker**, **observability**, **reproduce surface** — and apex can't hardcode the 8×9×4 combinations. So `detect-stack` profiles *this* project once into an in-repo `apex.profile.toml`, and `apex:investigate-bug` routes through whatever's declared. apex ships **zero integrations** — it discovers what's installed and routes (MCP-first interactive, CLI unattended, ask-user hard fallback).

**The profile is routing config, NOT secrets.** It holds `kind` / MCP prefix / CLI command / service name / repo-relative log path — never a credential. The value-shape lint (`reference/profile.py`) makes "no secrets" *decidable* (a token-shaped value in any field is rejected). Secrets stay in MCP-server / CI config; the profile only references an env-var *name* (`secret_ref`, reserved for the PR-C obs adapter).

## When to invoke

- Before the **first** `apex:investigate-bug` run in a repo (no `apex.profile.toml` yet).
- To **refresh** the profile when the stack changes (a new tracker, an obs vendor added) — re-run updates in place, preserving human-edited fields it didn't re-detect.

## The probe set (3 MVP probes + git remote)

| Probe | Reads | Infers |
|---|---|---|
| **deps** | `package.json` / `pyproject.toml` / `requirements.txt` / `Gemfile` | observability `kind` (`@datadog/*` → datadog, `@sentry/*`/`sentry-sdk` → sentry, `@opentelemetry/*` → otel-honeycomb). A malformed manifest is a noted gap, never a crash. |
| **CI configs** | `.github/workflows/` · `.gitlab-ci.yml` · `.circleci/` | the unattended-context host + **conflicting-signal detection** (github remote + `.gitlab-ci.yml`). |
| **connected MCP** | a **ToolSearch** probe for `mcp__<vendor>__*` available **this session** | the `mcp` binding per axis. **Interactive-only** — an unattended re-detect is blind here and preserves the prior `mcp`. |
| **git remote** | `git remote get-url origin` | `vcs.host` + `vcs.repo`. Always inferable; never prompted. |

> The deps/CI/git probes are pure Python in `reference/detect.py`. The **MCP probe and the interactive prompting are YOURS to run** (this skill, as the agent): do a `ToolSearch` for `mcp__*` prefixes, pass them to `build_profile(repo_root, mcp_prefixes=[...])`, and prompt the user for whatever it returns in the `prompts` list. The env-var-NAMES probe (`secret_ref`) is **PR-C**, not here.

## Behavior (AC7 — infer or ask, never guess)

- **Inferable** (a probe produced a value) → auto-fill it.
- **Un-inferable** (no probe produced a value) → **prompt** the user (interactive) or write the honest-empty placeholder `field = "" # TODO: fill` (unattended re-detect). **Never a default, never a guess.**
- **Conflicting signals** (github remote + gitlab CI) → record the conflict (`kind = ""` + a `# TODO: resolve (...)` note) and **ask** — never silently pick one. `investigate-bug` on an unresolved-placeholder axis routes to ask-user, not a guess.
- **AC2 (both bindings)** — every *routed* axis (tracker, observability) carries both `mcp` and `cli` keys (empty allowed); the writer records every binding a probe reports available (a `cli` found on PATH is emitted, not dropped).

## Output

`apex.profile.toml` at the repo root — see `reference/profile.py` for the schema + the value-shape allowlist, and `docs/stack-adapters/design.md` §C for the full contract. Validate any profile with `python reference/profile.py apex.profile.toml`.

## Distinct from

- **`apex:setup`** — *installs apex's own companions* (superpowers / pr-review-toolkit / a codebase-graph tool) and detects which **apex** companions are present. detect-stack *discovers the project's existing tooling*, installs **nothing**, and its MCP probe asks "which vendor servers can I route a bug through" — not "which apex companions are installed." Install-vs-discover.
- **`apex:recon`** — gathers **code-graph facts** in a change's blast radius for a *design*, emitting per-design prose. detect-stack profiles **bug-loop tooling** from routing-relevant config signals (not the code graph) and emits a **machine-written routing TOML**. Different output, lifecycle, and probe target.

## Hand-off

The profile feeds **`apex:investigate-bug`**, which reads it (`reference/profile.py:load_profile`), resolves each axis to a binding by mode (interactive → MCP-first; unattended → CLI-only), runs the read-only diagnosis, and hands a reproduced bug to the **`apex:autonomous-fix`** write gate at its P3→P4 seam.
