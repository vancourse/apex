# Stack-adaptive bug loop — refined pre-PRD spec

**Status:** refined brief, PRD-ready (not yet a PRD — feeds `apex:prd` → `apex:prd-review`). Authored 2026-06-07 from the sibling-conversation brief (`/private/tmp/apex-bug-fix-design.md`), reconciled with the shipped `autonomous-fix` gate (v0.3.7) and three user decisions.
**Slug:** `stack-adapters` · **Feeds:** a future `docs/stack-adapters/prd.md`.
**Decisions baked in (2026-06-07):** (1) Stack Profile = in-repo `apex.profile.toml`, routing-only, **no secrets**; (2) **observability adapter first** (generalize from the live BookBridge observability work); (3) `investigate-bug` is **promoted to a generic apex skill; BookBridge's becomes a consumer**.

---

## 0. Where this sits — three concentric layers, composed not duplicated

The sibling brief was written without the shipped `autonomous-fix` gate in full view. The corrected picture is **three concentric layers**:

```
  detect-stack  →  investigate-bug (adapter-routed)  →  autonomous-fix (write gate, v0.3.7)
  [config]         [read / diagnose / route]            [the rails around the WRITE]
```

- **`autonomous-fix`** (SHIPPED) — the **write-safety gate**: sensitive-path hard-stop, nonce fence, fail-closed cost, draft-PR-only, reproduce-first. Already tooling-agnostic (CI template + lint). **This layer does NOT re-implement any of that.**
- **This effort** — the **read / diagnose / route layer**: `detect-stack` + the Stack Profile + the adapters + a generic `investigate-bug`. It runs read-only-first, reproduces the bug, and **hands the reproduced bug to `autonomous-fix`'s write phase**.
- **`detect-stack`** — the config step that writes the profile both consume.

**Hard rule:** generic `investigate-bug` **composes** `autonomous-fix` (it does not bypass or duplicate the write gate). It is the adapter-routed diagnosis that feeds the gate — exactly the `investigate-bug → autonomous-fix` edge the autonomous-fix PRD already names (bead `apex-9lc.9`).

---

## 1. Problem — three independent axes (settled framing)

| Axis | Examples |
|---|---|
| **Issue tracker** | GitHub Issues, Linear, Jira, Notion, Azure Boards, Asana, Sentry-as-tracker |
| **Observability** | Datadog, OTEL+Honeycomb/Tempo/Grafana, Sentry, CloudWatch, Azure Monitor, New Relic, Splunk, ELK, console.log+grep |
| **Reproduce / fix surface** | docker-compose / Make, staging URLs, CI replay, hosted preview env |

8×9×4 = 288 combinations → **abstraction over enumeration**. apex defines the capabilities; users plug in what they have. (Settled — do not re-derive.)

---

## 2. The abstraction — Stack Profile + adapters, with the mode seam baked in

The **skill** describes the workflow generically; the **adapter** is what changes per stack; the **Stack Profile** declares which adapter applies per axis.

### 2a. THE seam the original brief under-specified: interactive vs unattended adapters

`ToolSearch` for `mcp__datadog__*` works **only in an interactive session**. The unattended path `autonomous-fix` targets runs in **CI (GitHub Actions, headless)** where session MCP servers **do not exist**. Therefore each adapter has **two bindings**, and the profile captures both:

| Mode | Binding | Used by |
|---|---|---|
| **interactive** | session MCP (`mcp__<vendor>__*` via ToolSearch) | a dev running `/apex:investigate-bug` locally |
| **unattended** | CLI / HTTP (`gh`, `dd`, Sentry API via curl), creds from CI secrets | the `autonomous-fix` CI path |
| **hard fallback** | ask the user to paste the issue / logs | both, when neither binding resolves |

This maps 1:1 onto `autonomous-fix`'s existing interactive/autonomous two-mode split. **The adapter contract + profile schema are a real API surface → `apex:api-surface-review` runs at design time.**

### 2b. The routing ladder (settled)

1. **Detect** connected MCP servers (interactive) / configured CLIs (unattended).
2. **Route** through whatever's available, per the profile.
3. **Fall back** to CLI when MCP is absent (interactive) — and CLI *is* the unattended default.
4. **Hard fallback** — ask the user to paste.

apex ships **zero** integrations — it discovers and routes. (Settled.)

---

## 3. Stack Profile — in-repo `apex.profile.toml`, routing-only, NO secrets (decided)

The privacy concern dissolves once *routing config* is separated from *secrets*: the profile holds `kind` / MCP prefix / CLI command / service name / repro command — and **never a credential**. Secrets live in MCP-server config / CI secrets; the profile only **references them by name**. Once secrets-free, in-repo wins (onboarding: new contributors don't re-detect, and the CI path can read it).

```toml
# apex.profile.toml — routing config only. NO secrets, ever. (autonomous-fix AC8 territory.)
[tracker]
kind = "github"                 # github | linear | jira | azure-boards | manual
mcp = "mcp__github__*"          # interactive binding (ToolSearch prefix)
cli = "gh"                      # unattended binding
bug_label = "bug"

[observability]                 # FIRST real adapter (decided) — generalize from BookBridge's live obs work
kind = "datadog"                # datadog | sentry | otel-honeycomb | cloudwatch | azure-monitor | console
mcp = "mcp__datadog__*"
cli = "dd"                      # or an HTTP recipe; creds via $DD_API_KEY (referenced, not stored)
service = "api-prod"
log_correlation_field = "trace_id"
secret_ref = "DD_API_KEY"       # NAME of the env/CI secret — never the value

[reproduce]
local = "docker-compose up && make test-e2e"
staging_url = "https://staging.example.com"

[vcs]
host = "github"
repo = "vancourse/apex"
```

**Schema decision (for PRD/design):** the profile is TOML with its **own loader**, *not* the `memory-note`/domain-knowledge schema — different lifecycle (shared, in-repo, machine-written by `detect-stack`) and different shape (structured config vs prose lessons). `detect-stack` auto-fills from project signals (deps, env names, CI configs, MCP probes) and prompts only for what it can't infer.

---

## 4. Skills, once this exists

`apex:investigate-bug <issue-ref>` (generic, promoted):
1. **tracker adapter** → fetch issue body / comments / attachments
2. **observability adapter** → query logs/traces in the failure window
3. **vcs adapter** → recent commits to suspect files
4. **diagnose** → `apex:recon` → reproduce-first (the `autonomous-fix` P2/P3 read-only rails)
5. **hand to `autonomous-fix`** for the gated write → DRAFT PR
6. **tracker adapter** → comment PR link, transition status

`apex:detect-stack` → writes/updates `apex.profile.toml`.
`apex:incident-retro` → retrofitted onto the same adapter shape (PR-E).

**Promote/consume (decided):** BookBridge's `.claude/skills/investigate-bug` becomes a thin consumer — calls generic `apex:investigate-bug` + adds its F-049-specific DB queries + hypothesis matrix. Same parent/child pattern as `autonomous-fix`.

---

## 5. MVP cut + PR series (ruthless — A+B only is the MVP)

apex ethos = don't ship 5 PRs of abstraction before 2 consumers exist. **MVP = PR-A + PR-B.** C/D/E are "grow the catalog," each deferred until a real consumer needs it.

| PR | Scope | Status |
|---|---|---|
| **A** | `apex:detect-stack` skill + `/apex:detect-stack` command — probe deps/env/CI/MCP, write `apex.profile.toml`. **No adapters.** | **MVP** |
| **B** | Generic `apex:investigate-bug` reading the profile + dispatching; **two universal adapters**: GitHub-tracker via `gh`, console-logs via grep. Composes `autonomous-fix` for the write. | **MVP** |
| **C** | First real observability adapter — **Datadog or Sentry** (generalize from BookBridge's live obs work). | defer until obs lands |
| **D** | Second tracker adapter (Linear / Jira) — confirms the abstraction isn't GitHub-shaped. | defer |
| **E** | Retrofit `apex:incident-retro` onto the adapter layer. | defer |

Each ≤400 LOC (`apex:pr-discipline` §3). **Note: the 0.3.x "menu stays 13/14" count is stale — `detect-stack` adds one command; grep the 6+ count sites before claiming a number** (captured lesson, MAINTAINING.md).

---

## 6. Remaining unknowns — for the PRD/design gates to resolve

1. **`detect-stack` MVP output** — probe results only, interactive prompt only, or both? (Lean: probe → fill what's inferable → prompt for the rest.)
2. **Adapter interface shape** — a per-axis capability contract (`fetch_issue`, `query_logs(window)`, `comment(pr)`, …): how thin can it be while covering tracker+obs+vcs? (→ `api-surface-review`.)
3. **Profile freshness/drift** — when is `apex.profile.toml` re-detected? Stale-profile behavior (ask vs proceed)?
4. **Unattended obs creds** — the CI path needs `secret_ref` resolved from CI secrets; confirm the autonomous-fix template's least-priv token model extends to obs API creds without widening scope.
5. **`detect-stack` vs `apex:setup`/`apex:recon` overlap** — Distinct-from lines (setup installs apex's companions; recon gathers code facts; detect-stack profiles the bug-loop tooling).

---

## 7. Settled — do NOT re-derive

- Three-axes framing (tracker / observability / reproduce-surface).
- MCP-first routing, CLI fallback, ask-user hard fallback.
- Stack Profile is per-project, persisted, detection-assisted.
- apex routes through installed integrations; ships none of its own.
- (New, decided 2026-06-07) in-repo `apex.profile.toml` routing-only-no-secrets · observability-first · promote-generic-investigate-bug.

---

## 8. Cross-conversation coordination

- **`autonomous-fix` v0.3.7 shipped** — this layer composes it; don't duplicate the write gate. Bead `apex-9lc.9` (BookBridge `investigate-bug` invokes the read-only rails) is the downstream consumer of *both* this and the gate.
- **BookBridge observability is being built now** (sibling conversation) — the canonical instance to generalize PR-C from.
- **PR #25 in flight** — `MAINTAINING.md` + `hooks/suggest-skill-on-edit.sh`; coordinate if this branch touches that hook or `README.md`.
- **Lessons (`~/.claude/domain-knowledge/apex.md` → MAINTAINING.md):** mechanical global substitutions inject semantic errors (verify each callsite); slash-count claims live in 6+ doc sites (grep before adding a command); the cross-repo agent shared-tree collision note (workflow agents writing the shared tree — isolate or treat as data-return only).

---

## Hand-off

On approval → `apex:prd` (author the PRD for **PR-A + PR-B only**) → `apex:prd-review` (7-pass + freeze). The adapter contract + profile schema get `apex:api-surface-review` at design time. Same gate chain as `autonomous-fix`.
