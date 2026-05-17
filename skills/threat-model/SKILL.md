---
name: threat-model
description: Per-feature STRIDE-style threat modeling at the design phase. 6-pass (Spoofing / Tampering / Repudiation / Information disclosure / Denial of service / Elevation of privilege) against the feature's attack surface, anchored on the trust boundaries + data classification + system-level threat model from apex:architecture-design Passes 3 and 7. Plus inline adversarial counter-pass at every step. Pairs with apex:design-feature (per-feature design) and apex:security-review (PR-time security gate). Fires during design phase for any feature that handles data, accepts input from outside the trust boundary, or changes a privilege transition. Keywords: threat model, STRIDE, attack surface, trust boundary, spoofing, tampering, information disclosure, privilege escalation.
---

# Threat Model

Per-feature threat modeling at the design phase. Identifies the attack surface of THIS feature, classifies threats by STRIDE category, and names mitigations (or accepts the residual risk explicitly). The output is a "Threat Model" section in the feature's design doc that `apex:security-review` (PR-time) audits against the implementation.

## When to invoke

- Any feature that accepts input from outside the system's trust boundary (web endpoint, webhook, file upload, message-queue consumer, CLI command-line)
- Any feature that handles classified data (PII, PHI, financial, secrets, regulated)
- Any feature that changes a privilege transition (login, role grant, API key issuance, impersonation)
- Any feature that crosses a trust boundary defined in `apex:architecture-design` Pass 3
- Any feature where `apex:design-feature` Pass 5 (failure modes) surfaces a permission / external-dependency / concurrency failure mode

Pairs with:

- **`apex:architecture-design`** Pass 3 (trust boundaries + data classification) + Pass 7 (system-level STRIDE) — the load-bearing inputs to this skill. If those don't exist, the per-feature threat model floats untethered.
- **`apex:design-feature`** — feature design as a whole. This skill is the security-specific lens applied to the design.
- **`apex:security-review`** — PR-time audit that the implementation actually mitigates the threats this skill identified.
- **`apex:python-review/rules/security.md`** + **`apex:typescript-review/rules/security.md`** — language-specific tooling for the mitigations this skill names.

## Adversarial counter-pass — read this first

Every pass below has an inline adversarial counter-pass. Threat modeling rewards adversarial framing more than any other gate — the cooperative pass tells you what the design *intends*; the adversarial pass tells you what an attacker can *actually do*.

## Pre-flight: anchor on the architecture

Before running the 6 STRIDE passes, restate:

- **Trust boundaries** this feature crosses (from `apex:architecture-design` Pass 3 / `docs/adr/0003-auth-and-data-classification.md`)
- **Data classes** this feature handles (PII / PHI / financial / public; from the same ADR)
- **System-level mitigations** already in place that this feature inherits (from `docs/adr/0007-system-threat-model.md`)
- **The actor model** — who's the attacker? External anonymous? Authenticated low-privilege user trying to escalate? Insider threat? Compromised dependency?

If any of these aren't crisp, push back upstream — `apex:architecture-design` is missing or stale.

## The 6 STRIDE passes

### Pass 1 — Spoofing (S): impersonating a principal

**Check:** Can an attacker pose as a legitimate principal to this feature?

- Are there auth-required endpoints? Is the principal extracted from a verified source (signed JWT, session cookie, mTLS cert) — not from a request body or query parameter?
- For webhooks / inbound integrations: is the source authenticated (HMAC signature, mutual TLS, IP allowlist)?
- For impersonation features (admin acting as user): is the privilege check at the right layer?

**Why:** Spoofing is the easiest attack to enable accidentally — a "user_id" query parameter, a self-issued bearer token, a webhook with no signature.

**Pass condition:** Every principal-bearing surface names where the principal comes from + where it's verified. Audit log captures the real principal AND any impersonation chain.

**Adversarial counter-pass:** Pick a request shape. Forge it as if you were an attacker on the network. What stops you from claiming to be `user_id=1`? If the answer is "the application code checks the cookie" — is that check at every entry point including background jobs / cron / queue consumers?

### Pass 2 — Tampering (T): modifying data at rest or in transit

**Check:** Can an attacker modify data they shouldn't?

- Inputs validated at the boundary (Pydantic / Zod) AND constrained at the DB (CHECK / FK / NOT NULL)?
- Writes authorized per-resource (not just per-endpoint)?
- Transit encryption (TLS) end-to-end including any intermediate hops?
- At-rest encryption for sensitive fields (column-level for secrets, plus full-disk for the underlying volume)?
- Idempotency keys on writes that must not double-apply?

**Why:** Tampering covers the entire write path. A feature that validates at the API but accepts arbitrary modifications via a background job has a tampering hole.

**Pass condition:** Every write surface validated at boundary + authorized per-resource + idempotent where required. Sensitive data encrypted at rest.

**Adversarial counter-pass:** Pick the most sensitive field this feature writes. Walk back from the DB schema through every write path. Find one path where the field could be modified without the boundary validator running.

### Pass 3 — Repudiation (R): denying you did something

**Check:** Can a principal claim "I didn't do that" and have us unable to prove otherwise?

- Audit log for every privileged action — what / who / when / from where?
- Audit log entries immutable (append-only, signed, or replicated externally)?
- Logs retained long enough to satisfy investigation + regulatory requirements?
- Logs include enough context to reconstruct user intent (request id, session id, correlated trace)?

**Why:** Repudiation matters most in financial / regulated systems but applies whenever blame allocation matters (security incidents, customer disputes, compliance audits).

**Pass condition:** Every privileged action this feature exposes has an audit-log entry with principal + action + before/after state. Audit log writable from the feature but tampering-resistant from outside.

**Adversarial counter-pass:** A user does X. We discover it 3 months later and need to prove it was them (not a hacker). What evidence do we have? Walk the audit-log query. If the answer is "we'd have to correlate 4 different log sources" — the audit log isn't fit for purpose.

### Pass 4 — Information disclosure (I): reading data you shouldn't

**Check:** Can an attacker (or a benign-but-bug'd request) read data they shouldn't?

- RLS / tenancy enforced at every read path (including background jobs, exports, search indexes)?
- Authorization checked per-resource (the `firm_id` from the JWT matches the row's `firm_id`)?
- API responses redact sensitive fields by default; opt-in to include them?
- Error messages don't leak existence ("user not found" vs "wrong password" — same response)?
- Logs redact PII per the data classification ADR?
- Search indexes / caches inherit the same isolation as the primary DB?

**Why:** Information disclosure is the most common breach class. Multi-tenant systems fail here when a request path skips the tenancy filter (export jobs, admin endpoints, full-text search).

**Pass condition:** Every read path enforces the same isolation as the primary DB. Sensitive fields opt-in. Errors don't leak existence.

**Adversarial counter-pass:** As a logged-in user of tenant A, find a path that reads tenant B's data. Try: ID-guessing on an endpoint, broad-export with implicit `WHERE firm_id`, full-text search across tenants, an admin endpoint that forgets the tenant filter, a background job that runs as a privileged role.

### Pass 5 — Denial of service (D): exhausting resources

**Check:** Can an attacker make the feature unavailable?

- Rate limiting at the edge (per-IP and per-principal)?
- Quotas per tenant / per resource (max-N rows per query, max-K requests per minute)?
- Pagination on every list endpoint (no unbounded results)?
- Timeouts on every external call (no hanging requests)?
- Circuit breakers on flaky dependencies (LLMs, payment gateways)?
- Bounded retries (no infinite retry storms)?
- Resource limits on file uploads / parsing (max file size, max parse depth)?

**Why:** Even small features can DoS the system if they don't have bounds. A "show me all transactions" endpoint without pagination + a curious user with 100M rows = downtime.

**Pass condition:** Every input is bounded. Every external call is timeout-wrapped. Every list result is paginated. Quotas applied per tenant.

**Adversarial counter-pass:** As a paying user, find a request shape that costs the system 100× what it costs you. (CSV upload with a billion rows. Search query with no filter. Export job that scans the world.) Those are the DoS amplifiers.

### Pass 6 — Elevation of privilege (E): becoming higher-privilege

**Check:** Can an attacker (or bug'd request) gain privilege they shouldn't have?

- Role / permission check at the **right layer** (not just the UI; not just the route; the service or query itself)?
- Privilege transitions audited and reversible (an admin can grant; can they revoke? does it propagate?)?
- "Confused deputy" patterns avoided — a high-priv service called via a low-priv pathway?
- JWT scope checked, not just JWT validity (scope = "read:transactions" not "admin")?
- File path / URL path / SQL parameter checks for traversal / injection?

**Why:** Privilege escalation is the highest-impact attack class. The "I'm authenticated, therefore I can do anything" bug is shockingly common.

**Pass condition:** Every privilege transition has an explicit check at the layer closest to the action (the SQL query, the file write, the external API call). No transitive trust ("the service is internal, so it must be allowed").

**Adversarial counter-pass:** As a logged-in regular user, find a request path that succeeds despite needing admin role. Try: a route that's only protected at the UI; a service method called from both a privileged and an unprivileged route; a JWT with the right `iss` but the wrong `scope`; a SQL parameter that drops the role check.

## Adversarial pair pattern (heavier)

For features with high blast radius (payment, auth, multi-tenant data export, admin actions), dispatch the threat model as **two parallel agents** via `superpowers:dispatching-parallel-agents`:

- **Cooperative agent** — runs the 6 passes in steelman mode. Confirms mitigations are present and well-placed.
- **Adversarial agent** — runs the same in attack mode. Each counter-pass becomes the primary lens. Tries to break the design.

Reconcile findings. Document residual risks explicitly — every system has them; hidden residual risk is the dangerous kind.

## Output: Threat Model section in the design doc

The output of this skill is a `## Threat Model` section appended to the feature's design doc, with one subsection per STRIDE category:

```markdown
## Threat Model

**Trust boundaries crossed:** <list from ADR-0003>
**Data classes handled:** <list from ADR-0003>
**Actor model:** <external anonymous / authenticated low-priv / insider / dep compromise>

### Spoofing
- Mitigation: <how>
- Residual risk: <if any, accepted because Y>

### Tampering
- Mitigation: <how>
- Residual risk: <...>

### Repudiation
- Mitigation: <how (audit log location, retention)>
- Residual risk: <...>

### Information disclosure
- Mitigation: <how (RLS, redaction, opt-in)>
- Residual risk: <...>

### Denial of service
- Mitigation: <how (rate limit, quota, bounds)>
- Residual risk: <...>

### Elevation of privilege
- Mitigation: <how (per-layer checks, scope verification)>
- Residual risk: <...>
```

`apex:security-review` audits the implementation against this output at PR time.

## Pass/fail summary

The threat model passes if all 6 STRIDE categories have either a named mitigation OR a documented + accepted residual risk. "No threat in this category" is rarely true; if you write it, the adversarial pass should challenge it.

Fail any → revise before continuing to implementation. Threat-model gaps caught at design time cost minutes; caught at PR time cost hours; caught in production cost days + customer trust.
