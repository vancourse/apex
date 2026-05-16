# SDLC Flow

How this plugin's skills and hooks compose into a single workflow. Read this when you want to know *which skill fires at which phase* — the README answers "what's installed" and "how do I install it."

## The pipeline

```
                       ┌────────────────────────┐
                       │  USER TASK / PROMPT    │
                       └───────────┬────────────┘
                                   │
                ┌──────────────────▼──────────────────┐
                │  HOOKS (always-on, automatic)       │
                │   • suggest-skill-on-prompt   →     │ injects review-skill reminders
                │   • suggest-skill-on-edit     →     │ on API-surface paths
                │   • guard-security-paths      →     │ on auth/creds/oauth/secrets paths
                │   • guard-dependency-bump     →     │ on lockfiles / dep manifests
                │   • guard-destructive (Bash)  →     │ blocks rm -rf, force-push, --no-verify
                │   • format-on-save (PostEdit) →     │ ruff / prettier
                └──────────────────┬──────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 1. PLAN                                                       │
   │    apex-flow        §1a reconnaissance                 │
   │                              (cost-shape inversion,           │
   │                               codebase recon,                 │
   │                               producer/consumer dual)         │
   │                            §1b adversarial checklist          │
   │                              (min change, alternatives,       │
   │                               critiques, reuse-vs-add)        │
   │    api-surface-review      (if new endpoint/payload/handler   │
   │                              → run against PROPOSED shape)    │
   │    protocol-first-workflow (if starting new Python component) │
   │    verify-ports            (if copying code from another      │
   │                              repository — schema/UX/format    │
   │                              assumptions are stale by default)│
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 2. IMPLEMENT                                                  │
   │    python-review              (Python — routes to topic file) │
   │    typescript-review          (TS / React — same)             │
   │    frontend-design            (UI change)                     │
   │    polymorphic-type-modeling  (new variant / event-type)      │
   │    api-surface-review         (re-run on actual code, not     │
   │                                only the proposed shape)       │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 3. VERIFY                                                     │
   │    verification-before-completion  "Never declare done        │
   │                                     without proof."           │
   │       • run tests                                             │
   │       • check logs                                            │
   │       • exercise the change in a browser (for UI)             │
   │       • cover golden path AND edge cases                      │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 4. PRE-PR ROBUSTNESS GATE                                     │
   │    ai-pre-review-checklist   8 steps: explain, layering,      │
   │                              state ownership, concurrency,    │
   │                              success/failure/fallback,        │
   │                              tests, reviewer-sim, gaps        │
   │    pr-discipline §2          full check suite → squash WIPs   │
   │                              to ONE commit per PR             │
   │    api-surface-review        (if API surface touched)         │
   │    python-review / typescript-review                          │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 5. OPEN PR                                                    │
   │    pr-discipline §1     ASK BEFORE PUSH — draft by default    │
   │    pr-review-primer     description template                  │
   │                          (what / why-this-shape / flow /      │
   │                           state / concurrency / transport /   │
   │                           success-failure-fallback / tests)   │
   │    review-risk rules    risk note if auth / data / concurrency│
   │                          / billing / external-API touched     │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 5b. POST-OPEN — Addressing reviewer comments                  │
   │    responding-to-review  every blocker needs a concrete      │
   │                          artifact; every reply maps to a diff;│
   │                          mechanical flagged-line verification │
   │                          before requesting re-review          │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ 6. REVIEW  (yours or others')                                 │
   │    pr-discipline §4     SINGLE PR scope — no historical crawl │
   │                          target 2-3 min of agent work         │
   │    python-review / typescript-review                          │
   │    api-surface-review   (if API surface in the diff)          │
   └───────────────────────────────┬───────────────────────────────┘
                                   │
   ┌───────────────────────────────▼───────────────────────────────┐
   │ POST-TASK: SELF-IMPROVEMENT LOOP                              │
   │    memory-note   capture surprising / non-obvious lessons     │
   │                  → ~/.claude/.../memory/<name>.md             │
   │                  → ~/.claude/domain-knowledge/<project>.md    │
   └───────────────────────────────────────────────────────────────┘
```

## Skill × Phase matrix

```
                              PLAN  IMPL  VERIFY  PRE-PR  OPEN  POST-OPEN  REVIEW
apex-flow               ✓
api-surface-review             ✓    ✓             ✓                          ✓¹
python-review                       ✓             ✓                          ✓
typescript-review                   ✓             ✓                          ✓
frontend-design                     ✓²
protocol-first-workflow        ✓³   ✓³
polymorphic-type-modeling      ✓⁴   ✓⁴
verify-ports                   ✓⁵   ✓⁵
verification-before-completion              ✓
ai-pre-review-checklist                            ✓
pr-discipline                                      ✓      ✓                  ✓
pr-review-primer                                          ✓
responding-to-review                                                ✓⁶
memory-note                                                                  after
```

¹ if API surface in diff
² UI changes only
³ new Python component
⁴ new variant / event-type / discriminated union
⁵ porting / adapting code from another repository
⁶ when addressing reviewer comments on an open PR

## Five principles overlaid on the pipeline

1. **Plan before coding** — never skip phase 1; re-enter it mid-task if the design breaks.
2. **Multi-phase rule** — `api-surface-review` runs at plan, implement, AND pre-PR. Invoking it once does not discharge later gates. Design intent and code reality diverge between phases; the later passes catch the drift.
3. **Prove it works** — phase 3 is non-negotiable. Verification is what separates "the code exists" from "this is done."
4. **Ask before push** — every transition from local → remote requires explicit user confirmation. Default to `--draft` on PR creation.
5. **Self-improvement loop** — every non-obvious lesson goes into memory or domain-knowledge so the next session starts smarter.

## When to skip phases

The pipeline assumes a non-trivial change. For trivial work, drop phases:

| Change type | Phases that fire |
|---|---|
| Typo / single-line fix / obvious bug | 2, 3, 5 (no plan, no robustness gate) |
| Internal refactor with no API change | 1 (light), 2, 3, 4, 5, 6 (skip api-surface-review) |
| New endpoint / payload / service handler | all phases, all skills |
| Doc / comment update | 5 only (still ask before push) |
| Reviewing someone else's PR | 6 only |

When in doubt, run the gate. The cost is one skill invocation; the cost of skipping is multiple review cycles.
