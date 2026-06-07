---
name: security-review
description: PR-time security audit of the implementation against the threat model. 5-pass — secrets management, authentication + authorization (per-layer, fail-closed), input validation + output encoding, dependency vulnerability scan + supply-chain integrity, audit log + observability for security events. Plus inline adversarial counter-pass at every step. Pairs with apex:threat-model (design-phase threat model produces the contract this audit verifies) and apex:architecture-design Passes 3 + 7 (the system-level security model). Fires at the PRE-PR phase, before opening a PR that touches auth / data access / external input / cryptography / sensitive paths. Keywords: security review, security audit, secrets, authn, authz, OWASP, CVE, supply chain, dependency vuln, audit log.
---

# Security Review

PR-time security audit. Verifies the implementation actually mitigates the threats identified at design time (`apex:threat-model`), against the system-level security model from `apex:architecture-design` Passes 3 + 7.

Distinct from:

- **`apex:python-review/rules/security.md`** and **`apex:typescript-review/rules/security.md`** — language-specific tooling rules; loaded as needed during review
- **`apex:threat-model`** — design-phase modeling; produces the *contract*; this skill verifies adherence
- **`apex:ai-pre-review-checklist`** Step 2 (layering) — touches security at layering level; this skill is the dedicated security gate
- **Claude Code built-in `/security-review`** — file-focused, useful for ad-hoc; this skill is integrated into the apex flow

## When to invoke

- PRE-PR phase, after `apex:ai-pre-review-checklist` and before `apex:pr-discipline` §1 (ask before push)
- ANY PR that touches: auth/credentials/oauth/secrets paths (guard-security-paths hook nudges this), database schema, external-input handling (uploads, webhooks, API endpoints), cryptography, audit-log emission, role/permission checks, environment variables
- Periodically on a tagged "security sweep" — even when the PR doesn't *obviously* touch security paths

Pairs with:

- **`apex:threat-model`** — the design-time output this audit verifies
- **`apex:architecture-design`** Pass 3 + Pass 7 + the resulting ADRs 0003 + 0007 — the system-level invariants
- **`apex:python-review/rules/security.md`** / **`apex:typescript-review/rules/security.md`** — tooling-specific patterns
- **`apex:responding-to-review`** — security findings go through normal review-response discipline

## Adversarial counter-pass — read this first

Every pass below has an inline adversarial counter-pass. Security review without an adversarial frame is a checklist; with adversarial framing, it's a review. Treat the counter-passes as load-bearing, not optional.

## Pre-flight: load the threat model

Before running the 5 passes, load:

- The feature's threat model (from `apex:threat-model` — typically a "Threat Model" section in the design doc)
- ADR-0003 (auth + data classification) and ADR-0007 (system-level threat model)
- Any prior security findings on this feature or adjacent code (search `audit_events`, security tickets)

If the threat model is missing, that's the first finding — STOP and push back upstream to `apex:threat-model` before continuing.

## The 5 passes

### Pass 1 — Secrets management

**Check:**

- No hardcoded secrets in code, configs, comments, test fixtures, or migration files
- Secrets loaded from a designated source (env var, secret manager, encrypted file) — never embedded
- `.env` / `.env.*` files git-ignored AND not committed in any historical commit (check `git log --all -- .env`)
- No secrets in log output, error messages, or HTTP response bodies (incl. error response bodies)
- Secret rotation story exists — when the secret leaks, what's the rotation procedure?
- Test fixtures use synthetic secrets that pattern-match real ones (`AKIA_FAKEEXAMPLE`) so secret scanners don't false-positive

**Why:** Secrets in code = secrets on GitHub = secrets in every clone forever. Even a private repo leaks via fork, accidental public push, or compromised collaborator account.

**Pass condition:** Grep for the canonical secret patterns (AWS `AKIA[0-9A-Z]{16}`, GitHub `ghp_[A-Za-z0-9]{36}`, Stripe `sk_(live|test)_`, JWT-shaped strings, `-----BEGIN.*PRIVATE KEY-----`) in the diff returns zero hits. Log filters redact PII per the data classification ADR.

**Adversarial counter-pass:** Pick the most sensitive secret this feature handles. Trace where it could appear (logs, error responses, audit events, traces, exports). Find one path where it isn't redacted.

### Pass 2 — Authentication + Authorization (per-layer, fail-closed)

**Check:**

- **Authentication** — every endpoint (incl. internal / background / webhook) verifies the principal from a trusted source (signed JWT, session cookie, mTLS). Webhooks have signature verification.
- **Authorization** — per-resource check at the LAYER CLOSEST TO THE ACTION (query, file write, external API). Not just route-level; not just UI-level.
- **Fail closed** — missing auth header → 401 (not 200 with empty data). Missing permission → 403 (not silent no-op).
- **Principal propagation** — background jobs / queue consumers / cron jobs inherit the right principal (no "runs as root" silently)
- **Scope verification** — JWT scope claim checked, not just JWT validity. Per-action scope.
- **Session invalidation** — logout actually revokes the session everywhere it's cached (sessions, CDN, browser, mobile)
- **Anti-impersonation** — admin-acting-as-user features audit the real principal AND the impersonated principal

**Why:** Authorization bugs are the #1 source of breaches. "Confused deputy" — a high-priv service called from a low-priv pathway — is a recurring pattern.

**Pass condition:** Every endpoint in the diff has authn at the framework boundary AND authz at the service / query layer. Fail-closed everywhere. Audit log captures principal for every privileged action.

**Adversarial counter-pass:** As a logged-in low-privilege user, find a path that succeeds without the privilege required. Try the canonical patterns: protected only at the UI (call the API directly), protected only at the route (find a route that bypasses it — admin endpoints, internal endpoints, background jobs), JWT with wrong scope, principal-from-request-body, missing tenant filter on the SQL.

### Pass 3 — Input validation + output encoding

**Check:**

**Input validation (at the boundary):**

- All inputs validated by Pydantic / Zod / equivalent BEFORE reaching business logic
- Validation rejects unknown fields (no silent extra-data pass-through)
- Bounds on numeric fields (no `max_pages=999999` overrides)
- Length limits on string fields (no unbounded user-supplied text)
- Path traversal prevented for filename inputs (`os.path.basename` + resolved-path containment check)
- LLM prompt-injection delimited (untrusted user content wrapped in clear delimiters; system prompt above doesn't trust within-delimiter content)
- SQL parameterized (no string concatenation; no `f"... {user_input} ..."`); ORM safe
- Shell commands: no `shell=True` on Python with user input; argv array on Node

**Output encoding (at the response):**

- HTML output uses framework escaping by default (React's default, Jinja2 autoescape) — NO `dangerouslySetInnerHTML` / `|safe` / `Markup` without explicit justification
- JSON responses don't include sensitive fields (default-deny, opt-in)
- Headers set: `Content-Security-Policy`, `X-Content-Type-Options: nosniff`, `Strict-Transport-Security`, `X-Frame-Options`
- Cookies: `HttpOnly` + `Secure` + `SameSite=Strict` (or `Lax` with explicit justification) for session cookies
- Error responses don't leak existence ("user not found" vs "wrong password" — same generic response)

**Why:** XSS, SQL injection, path traversal, and prompt injection are 4 of the top 10 vulnerability classes. They're all preventable by structural choices (parameterization, escaping, validation) — but only if applied consistently.

**Pass condition:** Every entry point validates inputs structurally (not string-matching) and outputs encode by default.

**Adversarial counter-pass:** Pick the most dangerous output sink (HTML render, SQL query, shell command, file path, LLM prompt). Walk back from the sink to every input that reaches it. Find one path where the input isn't escaped / parameterized / bounded.

### Pass 4 — Dependency vulnerability + supply-chain integrity

**Check:**

- Lockfile committed (`package-lock.json`, `pnpm-lock.yaml`, `uv.lock`, `Cargo.lock`) — pins exact versions
- Lockfile changes in the diff have been reviewed (not just rubber-stamped)
- New dependencies have been evaluated for: license compatibility, recent maintenance, known CVEs (`npm audit`, `pip-audit`, `cargo audit`, GitHub Dependabot)
- Direct dependencies pinned to specific versions (not `^1.0.0` wildcards in production lockfile resolution)
- No deprecated / abandoned packages introduced
- Build / runtime separation — dev-only deps not pulled into production image
- For runtime packages from non-official registries: source verified, signature checked (where available)

**Why:** Supply-chain attacks are exploding (eslint-scope incident, event-stream, ua-parser-js, colors.js). Lockfile diffs are where they enter your codebase.

**Pass condition:** Every new dependency in the lockfile diff has been evaluated. Known-vuln scan runs in CI and is green.

**Adversarial counter-pass:** Pick one new package in the lockfile diff. Read its repo. Has it been touched in the last 12 months? Does the maintainer list have known good actors? Does it pull transitive deps that are themselves abandoned? Most supply-chain compromises hide one level deep.

### Pass 5 — Audit log + observability for security events

**Check:**

- Privileged actions logged: login, logout, password change, role grant, permission grant, API key issuance, impersonation start/end, admin actions, data export, account deletion
- Audit log includes: timestamp, principal (real + impersonated if any), action, target resource, before/after state where applicable, request id / trace id
- Audit log written to a location that's:
  - Append-only or write-once (no UPDATE/DELETE from the app)
  - Replicated externally for tamper evidence
  - Retained per the data-classification retention rules
- Failed auth attempts logged (for detection — not for response leakage)
- Anomaly alerts wired for: failed-auth spikes, privilege escalation patterns, tenant cross-access attempts, dependency-CVE alerts in production

**Why:** Repudiation defense (STRIDE R) lives here. Without audit logs, you can't prove who did what; you can't detect breaches; you can't respond.

**Pass condition:** Every privileged action this feature exposes has an `audit_events` (or equivalent) entry. Detection alerts cover the threat-model's high-risk paths.

**Adversarial counter-pass:** Pick a privileged action this PR adds. Pretend it was abused 3 months ago. Walk the investigation: do we have enough evidence to prove what happened, by whom, against what target? If "we'd need to correlate 4 log sources" — the audit log isn't fit for purpose.

## Adversarial pair pattern (for high-stakes PRs)

For PRs touching auth / payment / multi-tenant data / admin actions / cryptography, dispatch the security review as **two parallel agents** via `apex:adversarial-pair` (apex's canonical dispatch mechanic):

- **Cooperative agent** — runs the 5 passes in defense mode. Confirms mitigations are present.
- **Adversarial agent** — runs the same in attack mode. Each counter-pass becomes the lens. Treats the PR as an unfamiliar code base they're paid to find holes in.

Reconcile findings. High-stakes PRs that pass cooperative review but fail adversarial review are EXACTLY the PRs that ship and cause incidents.

## Pass/fail summary

The security review passes if:

- All 5 passes meet pass conditions
- Adversarial counter-pass findings are addressed
- Every threat from `apex:threat-model`'s output has a corresponding mitigation in the diff (or an explicit accepted residual risk)
- Audit log + alerts cover the high-risk paths

Fail any → fix before opening / re-requesting review on the PR. Security findings are the highest-priority blockers — a failing security review should block merge regardless of other gates.

## Hand-off

After passing:

- `apex:pr-discipline` §1 (ask before push, draft default)
- `apex:pr-review-primer` (description template) — security-relevant findings noted in the PR body
- `apex:copilot-review-loop` — Copilot's pattern-matching catches some classes this gate doesn't; both run as complementary
