---
name: observability-review
description: Per-feature DESIGN-PHASE gate for a feature's OBSERVABILITY CONTRACT — 5-pass (structured logging / metrics + cardinality / tracing + causality / alerting + SLO / privacy in telemetry) asking "when this misbehaves in prod, can an operator SEE why?", anchored on the system-level observability stack + SLO/alerting policy chosen in apex:architecture-design Pass 4. Distinct from apex:architecture-design Pass 4 (which sets that policy system-wide once; this instantiates it per-feature) and apex:security-review Pass 5 (which audits the security-event slice at PR time). Plus inline adversarial counter-pass at every step. Fires during design for any feature with non-trivial runtime behavior — external calls, async/background work, or interesting failure modes. Pairs with apex:design-feature (the per-feature design this attaches to), apex:architecture-design Pass 4 (inherits the stack + conventions), apex:security-review (PR-time audit of the security-event slice), and apex:incident-retro (the future retro this gate gives something to read). Keywords: observability, logging, metrics, tracing, alerting, SLO, cardinality, telemetry, debuggability, runbook, correlation id.
---

# Observability Review

Per-feature observability design at the design phase — the gate between "the feature is designed to *work*" and "the feature is designed to be *operated* when it doesn't." A feature can pass every functional, security, and test gate and still be a black box in production: no log explaining the failure decision, no metric showing the error rate climb, no trace attributing the slow request, no alert that pages before the customer does. This skill designs the feature's **observability contract** — what it logs, measures, traces, and alerts on. The output is an `## Observability` section in the feature's design doc that the implementation builds against and a future `apex:incident-retro` reads.

## When to invoke

- During design for any feature with **non-trivial runtime behavior** — external calls (HTTP, DB, LLM, payment gateway), async / background / queue / cron work, retries, or a state machine
- When `apex:design-feature` Pass 5 (failure modes) names a failure an operator would need to *diagnose live* (external-dependency failure, concurrency, partial-write recovery)
- When a feature adds a new user-visible latency path or a throughput-sensitive hot path

Do **not** invoke for a pure-CRUD endpoint with no external calls and no async work that inherits the architecture's default request log + RED metrics wholesale → the system defaults already cover it; say so and move on.

Pairs with:

- **`apex:architecture-design`** Pass 4 — sets the observability *stack* + SLO/alerting/sampling *policy* system-wide, once, and rehearses debuggability at the system boundary. This skill instantiates that policy for ONE feature (its specific SLIs, its page/ticket assignments, its spans) and re-asks "can I debug *this* feature" against the signals it actually emits. It does not re-pick the framework.
- **`apex:design-feature`** — the per-feature design this section attaches to; Pass 5 failure modes are the input to Pass 1 + Pass 4 here.
- **`apex:security-review`** Pass 5 (downstream, PR-time) — verifies the security-event slice of this contract landed. Security events are one slice this skill defers to that gate.
- **`apex:incident-retro`** (downstream, post-release) — a "couldn't see why" retro finding names this gate as the one that should have caught it.
- **`apex:python-review/rules/logging-observability.md`** (and the `apex:typescript-review` skill — no dedicated logging rule file there today) — the language *tooling* that *implements* the contract. This skill is the contract; that is how you build it. If you can't draw a sharper line than "logging" between this and the rule file, you're at the tooling layer — drop to it instead.
- **`apex:impl-plan-review`** Pass 4 — owns rollout sequencing + feature flags; this owns what the alert *fires on* once deployed.

## Adversarial counter-pass — read this first

Every pass below has an inline adversarial counter-pass. Observability rewards adversarial framing uniquely — the cooperative pass tells you what the design *intends to emit*; the adversarial pass simulates the incident and asks whether what's emitted is *enough to act on*: "it's broken in prod right now — can I find out why in five minutes, from the signals alone?"

## Pre-flight: inherit the stack + policy

Before running the 5 passes, restate (do not re-decide):

- **The observability stack** from `apex:architecture-design` Pass 4 / `docs/adr/0004-observability-and-deploy.md` (log destination + format, metrics backend, tracing system, alert manager) — this feature emits *into* it
- **The log-format + metric-naming + trace-context + SLO/alerting + retention/sampling conventions** the architecture established — this feature's signals conform to them; deviations must be justified
- **The data-classification rules** from `apex:architecture-design` Pass 3 / `docs/adr/0003-auth-and-data-classification.md` — which fields are PII / secret / regulated, so Pass 5 knows what must never reach telemetry

If Pass 4's stack + policy don't exist, the per-feature contract floats untethered → STOP and push back upstream to `apex:architecture-design` before continuing.

## The 5 passes

### Pass 1 — Structured logging: the failure-decision record

**Check:** For each meaningful event and every failure-decision point:

- Logged **structured** (key/value fields), not interpolated into a prose string
- At the right **level** — DEBUG (dev-only detail), INFO (state transition worth keeping), WARN (degraded-but-handled), ERROR (a failure decision a human may act on). No INFO-spam in hot loops; no ERROR for expected conditions.
- Carries the **correlation fields** — request / trace / tenant / job id (from the Pass-4 propagation scheme) — so one request's lines join across services
- **One log per distinct failure decision** — no log-and-rethrow (the same decision re-logged at every frame), no swallowed exception (caught, dropped, or logged at DEBUG and lost)
- Errors log the *decision and its inputs* (what was attempted, with which key params), not just a stack trace

**Why:** The most common observability failure is the swallowed error (`except Exception: log.debug(...); return None`) — it turns a production failure into a silent wrong answer.

**Pass condition:** Every distinct failure decision emits exactly one ERROR/WARN at the layer that *decides* the outcome, structured, correlation-id-tagged. A path with N genuine decisions has N lines, not N×frames. No path catches-and-continues without a line naming the user-visible consequence.

**Adversarial counter-pass:** Pick the most likely failure mode from `apex:design-feature` Pass 5. Walk it from the throw site outward and count the log lines. Zero → it's a silent failure (the worst kind); the same decision logged at multiple frames → that's log-and-rethrow noise, flag the duplicates. Then: with only those lines and a correlation id, can you tell *which* of two similar requests failed?

### Pass 2 — Metrics: what to measure + the cardinality budget

**Check:** Name the metrics this feature emits and what each feeds:

- The **RED/USE basics** for the feature's surface — request **R**ate, **E**rror rate, **D**uration (latency as a histogram, percentiles not a mean); for resources, **U**tilization / **S**aturation (queue depth, pool usage, in-flight count)
- Any **business KPI** the feature owns (signups completed, documents processed, payments settled)
- Each metric names the **SLI** it feeds — a metric with no SLI is a number nobody reads
- **Cardinality budget** — every label has a *bounded* value set. No `user_id`, `request_id`, raw URL path, or error *message* as a label (those belong in logs / traces). Call out tenant id explicitly.

**Why:** Unbounded label cardinality is the classic metrics outage — one `user_id` label on a high-traffic counter creates millions of series and takes down the metrics backend.

**Pass condition:** Latency (histogram) + error rate exist for every external call and user-facing operation; each metric names its SLI; every label has a stated, bounded value set. Zero high-cardinality labels.

**Adversarial counter-pass:** Pick the metric with the most labels. Multiply the realistic distinct-value count of each label; if the product exceeds a few thousand series, you've found a cardinality bomb — name the offending label and push it down to a log field or trace attribute. Separately: name one SLI you could *not* compute from the metrics as specified — that SLI is unmeasured.

### Pass 3 — Tracing + causality: attributing the slow request

**Check:** For features that cross service or external-call boundaries:

- A **span** wraps each external call (DB query, HTTP call, LLM call, queue publish / consume) so a slow request decomposes into where the time went — not just "slow somewhere"
- **Trace context propagates** across every boundary — including async hops (the trace id rides the queue message / background job), so a job triggered by a request stays on the same trace
- Spans carry the same entity ids as the logs (so a trace and its lines join) and causally-useful attributes (operation, target, size — never the payload)

**Why:** Latency is the failure metrics tell you *exists* and only traces tell you *where*; the async gap is the silent killer — a request hands off to a queue, the consumer drops the trace context, and the two halves of one operation can never be joined.

**Pass condition:** Every external call and async hand-off is span-wrapped with context propagated; spans share the log correlation id. A slow request decomposes into per-hop durations from the trace alone.

**Adversarial counter-pass:** Trace the path with the most hops (especially one crossing an async / queue boundary) from entry to its slowest plausible downstream. Drop the trace context at that boundary in your head — can you still attribute the slow / failed downstream step to the originating request? If "no," name the boundary where the trace breaks: that's exactly where the production latency mystery will live.

### Pass 4 — Alerting + SLO: page on symptoms, not causes

**Check:** Page on user-visible **symptoms**, never on causes — then assign every failure a tier:

- **Page** (wake someone) — only symptoms: SLO burn (error rate / latency past the objective), the feature is down. Symptom-based, never cause-based.
- **Ticket** (next business day) — degraded-but-serving, a dependency flapping, a saturation trend
- **Dashboard-only** (no notification) — the rest; available when investigating, silent otherwise
- Every page-class alert names its **runbook** (what the on-call does) and its **owner**
- **Alert-storm guards** — one root cause fires one page, not fifty; alerts deduplicated / grouped
- The feature's **SLO** is stated as a target on the Pass-2 SLI (e.g. "99% of saves < 500ms / 30d") within the system-wide framework from Pass 4; the alert threshold derives from the error budget, not a guessed number

**Why:** Cause-based alerting ("CPU > 80%") pages for things that aren't hurting users and trains responders to mute the pager — so the one alert that matters gets muted too. A page with no runbook is a puzzle, not an action.

**Pass condition:** Every failure has an assigned tier. Every page is symptom-based, tied to an SLO / error-budget threshold, and names a runbook + owner. Cause-only metrics are dashboard-tier, not page-tier.

**Adversarial counter-pass:** Name a way the feature could be fully broken for users while emitting *zero* pages — that's the gap that lets an outage run until a customer reports it. Conversely, take the worst single cause (the primary DB is down) and count how many of this feature's alerts fire from it — more than one or two is an alert storm that buries the signal. Then: a page fires with no runbook — what does the responder actually *do*? If it isn't in the alert, the alert isn't done.

### Pass 5 — Privacy in telemetry: no PII / secrets in logs, metrics, traces

**Check:** Against the data-classification rules from `apex:architecture-design` Pass 3:

- **No secrets / tokens / credentials / keys** in any log line, metric label, span attribute, or error message — including inside logged request bodies, error responses, and exception args
- **No PII / customer data** in telemetry beyond what classification permits; redact / hash / tokenize **at the emission boundary** (a log/metric/span helper that strips), not "we'll scrub it later"
- **No whole-object dumps** (`log.info(request)`, `span.set(user=user)`) — they smuggle whatever fields the object grows later
- **Retention + sampling** inherited from Pass 4, with any per-feature deviation justified; high-volume DEBUG that captures payloads is off in prod by default

**Why:** Telemetry is the back door for data leaks — high-volume, broadly readable (dashboards, log search, third-party APM vendors), and rarely access-controlled like the primary DB; a token in a log line is a credential in your observability vendor's index forever.

**Distinct from `apex:security-review` Pass 1:** this is that gate's redaction drill pulled one phase upstream — design the redaction-at-emission-boundary helper now, at design time, so the PR-time audit has something to verify instead of discovering an un-redacted sink at PR time. Same sinks (logs / traces / exports), earlier phase — the same design-time vs PR-time split as `apex:threat-model` ↔ `apex:security-review`.

**Pass condition:** Every classified field is redacted at the point it would enter telemetry; no whole-object dumps; retention + sample rate stated (or inherited) per signal. Example log lines use synthetic-but-realistic values.

**Adversarial counter-pass:** Pick the most sensitive field this feature handles. Trace every place it could surface — a logged request body, an exception that captures locals, a span attribute, a metric label, an APM payload. Find ONE sink where it reaches a signal un-redacted: the emission-boundary helper has a gap there.

## Adversarial pair pattern (heavier)

For features with high operational blast radius (payment flows, multi-service fan-out, high-throughput async pipelines — anything whose outage is a customer-facing incident), dispatch the review as **two parallel agents** via `apex:adversarial-pair` (apex's canonical dispatch mechanic):

- **Cooperative agent** — runs the 5 passes in steelman mode. Confirms each signal is present and well-placed.
- **Adversarial agent** — runs the same from the on-call seat. Each counter-pass becomes the primary lens: it tries to debug a synthetic incident using *only* the planned telemetry and reports where it goes blind.

Reconcile findings. A contract that reads complete on paper but leaves the adversarial operator blind is exactly the feature that ships and then can't be debugged in prod.

## Output: Observability section in the design doc

The output is an `## Observability` section appended to the feature's design doc:

```markdown
## Observability

**Stack inherited (ADR-0004):** <log dest + format / metrics backend / tracing / alert manager>
**Data classes in telemetry scope (ADR-0003):** <fields that must be redacted>

### Logging
- Events + levels: <key state transitions → level, with correlation fields>

### Metrics + SLIs
- <name | type | bounded labels | feeds SLI / dashboard>
- SLO: <target on the SLI, e.g. 99% < 500ms / 30d>

### Tracing
- Spans: <external calls + async hand-offs, context-propagation note>

### Alerting
- Page: <symptom · runbook · owner>; Ticket / dashboard-only: <...>

### Telemetry privacy
- Redaction-at-boundary: <fields> · Retention: <...> · Sample rate: <...>
```

`apex:security-review` audits the security-event slice at PR time; `apex:incident-retro` reads it when a "couldn't see why" incident maps back to this gate.

## Pass/fail summary

The observability review passes if:

- All 5 passes meet their pass conditions
- Adversarial counter-pass findings are addressed
- Every failure mode from `apex:design-feature` Pass 5 has a detecting signal (a log, metric, trace span, or alert)
- No path can leak a classified field into any signal

"This feature doesn't need observability" is rarely true for anything that qualified under *When to invoke*; if you write it, the adversarial pass should challenge it.

Fail any → revise the design before implementation. Observability gaps caught at design time cost minutes; caught at PR time cost hours; surfaced as "we couldn't tell what was happening" during a production incident cost days + the trust of whoever was paged — and an `apex:incident-retro` that routes the lesson right back to this gate.
